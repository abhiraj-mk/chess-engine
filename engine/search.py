"""
search.py - the engine's brain

this is where minimax + alpha-beta pruning happens.
we also do:
- iterative deepening (search depth 1, then 2, then 3...)
- quiescence search (keep searching captures to avoid horizon effect)
- transposition table lookups
- move ordering (critical for alpha-beta performance)
- killer move heuristic

the search returns a score and the best move found.
"""

import time

from engine.bitboard import (
    Board, Move, PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING,
    WHITE, BLACK, SQUARE_NAMES, popcount,
)
from engine.move_gen import (
    generate_legal_moves, generate_legal_captures, is_in_check,
)
from engine.eval import evaluate, MVV_LVA, PIECE_VALUES
from engine.zobrist import (
    TranspositionTable, TT_EXACT, TT_ALPHA, TT_BETA,
    compute_hash, update_hash_move,
)


# big numbers for mate scores
INFINITY = 999999
MATE_SCORE = 100000
MATE_THRESHOLD = MATE_SCORE - 500  # anything above this is a forced mate


class SearchInfo:
    """tracks search statistics and controls"""

    def __init__(self):
        self.nodes = 0
        self.depth = 0
        self.best_move = None
        self.best_score = 0
        self.start_time = 0
        self.time_limit = 0   # in seconds, 0 = no limit
        self.max_depth = 64
        self.stopped = False

        # killer moves (2 per ply)
        self.killers = [[None, None] for _ in range(64)]

        # history heuristic
        self.history = [[0] * 64 for _ in range(64)]

    def check_time(self):
        """see if we ran out of time"""
        if self.time_limit > 0:
            elapsed = time.time() - self.start_time
            if elapsed >= self.time_limit:
                self.stopped = True

    def reset(self):
        self.nodes = 0
        self.stopped = False
        self.killers = [[None, None] for _ in range(64)]
        self.history = [[0] * 64 for _ in range(64)]


# global transposition table (persists between searches)
tt = TranspositionTable(max_size=500_000)


def _make(board, move):
    """make a move and update the zobrist hash"""
    board.make_move(move)
    board.hash_key = compute_hash(board)


def _unmake(board):
    """unmake a move - hash restored from undo stack automatically"""
    board.unmake_move()


def order_moves(board, moves, info, ply, tt_move=None):
    """
    order moves to improve alpha-beta cutoffs.
    good ordering makes alpha-beta WAY faster.

    priority:
    1. transposition table move (if any)
    2. captures sorted by MVV-LVA
    3. killer moves
    4. history heuristic
    5. everything else
    """
    scored = []

    for move in moves:
        score = 0

        # tt move gets highest priority
        if tt_move and move == tt_move:
            score = 10000000
        elif move.captured is not None:
            # MVV-LVA: most valuable victim, least valuable attacker
            score = 1000000 + MVV_LVA[move.piece][move.captured]
        elif move.promotion is not None:
            score = 900000 + PIECE_VALUES.get(move.promotion, 0)
        elif ply < 64 and info.killers[ply][0] == move:
            score = 800000
        elif ply < 64 and info.killers[ply][1] == move:
            score = 700000
        else:
            # history heuristic
            score = info.history[move.from_sq][move.to_sq]

        scored.append((score, move))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored]


def quiescence(board, alpha, beta, info):
    """
    quiescence search - keep searching captures until position
    is "quiet". this prevents the horizon effect where the engine
    thinks a position is good because it doesn't see the recapture.
    """
    info.nodes += 1

    # check time every 2048 nodes
    if info.nodes & 2047 == 0:
        info.check_time()
    if info.stopped:
        return 0

    stand_pat = evaluate(board)

    if stand_pat >= beta:
        return beta

    if stand_pat > alpha:
        alpha = stand_pat

    # only search captures
    captures = generate_legal_captures(board)

    # basic ordering - MVV-LVA
    captures.sort(
        key=lambda m: MVV_LVA[m.piece][m.captured] if m.captured is not None else 0,
        reverse=True
    )

    for move in captures:
        # delta pruning - skip captures that can't possibly raise alpha
        # (unless we're in check, then search everything)
        if not is_in_check(board, board.side):
            if move.captured is not None:
                gain = PIECE_VALUES.get(move.captured, 0)
                if move.promotion:
                    gain += PIECE_VALUES.get(move.promotion, 0) - PIECE_VALUES[PAWN]
                if stand_pat + gain + 200 < alpha:
                    continue

        _make(board, move)
        score = -quiescence(board, -beta, -alpha, info)
        _unmake(board)

        if info.stopped:
            return 0

        if score > alpha:
            alpha = score
            if score >= beta:
                return beta

    return alpha


def alpha_beta(board, depth, alpha, beta, info, ply, do_null=True):
    """
    alpha-beta search with transposition table.

    alpha: best score we can guarantee (lower bound)
    beta: opponent's best guaranteed score (upper bound)
    ply: current ply from root (for killer moves etc.)
    do_null: whether to try null move pruning
    """
    info.nodes += 1

    if info.nodes & 2047 == 0:
        info.check_time()
    if info.stopped:
        return 0

    # check for draw by repetition or 50-move rule
    if ply > 0 and (board.is_repetition() or board.halfmove >= 100):
        return 0

    # transposition table lookup
    original_alpha = alpha
    entry = tt.probe(board.hash_key)
    tt_move = None

    if entry is not None and entry.depth >= depth:
        tt_move = entry.best_move
        if entry.flag == TT_EXACT:
            return entry.score
        elif entry.flag == TT_ALPHA:
            if entry.score <= alpha:
                return alpha
        elif entry.flag == TT_BETA:
            if entry.score >= beta:
                return beta
    elif entry is not None:
        tt_move = entry.best_move

    # leaf node - drop into quiescence
    if depth <= 0:
        return quiescence(board, alpha, beta, info)

    in_check = is_in_check(board, board.side)

    # check extension - if we're in check, search one ply deeper
    if in_check:
        depth += 1

    # null move pruning
    # skip a turn and see if opponent can still not beat beta
    # don't do this in check or in endgame (zugzwang risk)
    if (do_null and not in_check and depth >= 3 and
        not _is_endgame_for_null(board)):
        # save state we're about to mess with
        saved_ep = board.ep_square
        saved_hash = board.hash_key

        board.side = 1 - board.side
        board.ep_square = -1
        board.hash_key = compute_hash(board)

        score = -alpha_beta(board, depth - 3, -beta, -beta + 1, info, ply + 1, False)

        # restore everything
        board.side = 1 - board.side
        board.ep_square = saved_ep
        board.hash_key = saved_hash

        if info.stopped:
            return 0
        if score >= beta:
            return beta

    moves = generate_legal_moves(board)

    # checkmate or stalemate
    if len(moves) == 0:
        if in_check:
            return -MATE_SCORE + ply  # checkmate
        return 0  # stalemate

    # order moves
    moves = order_moves(board, moves, info, ply, tt_move)

    best_move = moves[0]
    best_score = -INFINITY
    moves_searched = 0

    for move in moves:
        _make(board, move)

        # late move reduction (LMR)
        # search later moves with reduced depth
        if (moves_searched >= 3 and depth >= 3 and
            not in_check and move.captured is None and
            move.promotion is None):
            # reduced depth search
            score = -alpha_beta(board, depth - 2, -alpha - 1, -alpha,
                               info, ply + 1, True)
            # if it looks promising, re-search at full depth
            if score > alpha:
                score = -alpha_beta(board, depth - 1, -beta, -alpha,
                                   info, ply + 1, True)
        else:
            score = -alpha_beta(board, depth - 1, -beta, -alpha,
                               info, ply + 1, True)

        _unmake(board)

        if info.stopped:
            return 0

        moves_searched += 1

        if score > best_score:
            best_score = score
            best_move = move

            if score > alpha:
                alpha = score

                # update history for quiet moves
                if move.captured is None:
                    info.history[move.from_sq][move.to_sq] += depth * depth

                if score >= beta:
                    # beta cutoff - store killer move
                    if move.captured is None and ply < 64:
                        info.killers[ply][1] = info.killers[ply][0]
                        info.killers[ply][0] = move

                    # store in TT
                    tt.store(board.hash_key, depth, beta, TT_BETA, best_move)
                    return beta

    # store result in TT
    if best_score <= original_alpha:
        flag = TT_ALPHA
    else:
        flag = TT_EXACT

    tt.store(board.hash_key, depth, best_score, flag, best_move)

    return alpha


def _is_endgame_for_null(board):
    """check if it's too late in the game for null move pruning"""
    us = board.side
    # if we only have king and pawns, don't do null move
    non_pawn = (board.pieces[us][KNIGHT] | board.pieces[us][BISHOP] |
                board.pieces[us][ROOK] | board.pieces[us][QUEEN])
    return non_pawn == 0


def iterative_deepening(board, max_depth=64, time_limit=0, verbose=True):
    """
    iterative deepening - search depth 1, 2, 3, etc.
    each iteration uses results from previous one for move ordering.

    returns (best_move, best_score, depth_reached)
    """
    info = SearchInfo()
    info.start_time = time.time()
    info.time_limit = time_limit
    info.max_depth = max_depth

    # make sure hash is set
    board.hash_key = compute_hash(board)

    best_move = None
    best_score = 0

    for depth in range(1, max_depth + 1):
        info.depth = depth
        info.reset()

        score = alpha_beta(board, depth, -INFINITY, INFINITY, info, 0)

        if info.stopped:
            break

        # grab the best move from the TT
        entry = tt.probe(board.hash_key)
        if entry and entry.best_move:
            best_move = entry.best_move
            best_score = score

        elapsed = time.time() - info.start_time

        if verbose:
            # format score
            if abs(score) >= MATE_THRESHOLD:
                if score > 0:
                    mate_in = (MATE_SCORE - score + 1) // 2
                    score_str = f"mate {mate_in}"
                else:
                    mate_in = (MATE_SCORE + score + 1) // 2
                    score_str = f"mate -{mate_in}"
            else:
                score_str = f"cp {score}"

            nps = int(info.nodes / elapsed) if elapsed > 0.001 else 0
            print(f"info depth {depth} score {score_str} "
                  f"nodes {info.nodes} nps {nps} "
                  f"time {int(elapsed * 1000)} "
                  f"pv {best_move.uci() if best_move else '(none)'}")

        # if we found a forced mate, no need to search deeper
        if abs(score) >= MATE_THRESHOLD:
            break

    return best_move, best_score, depth


def find_best_move(board, depth=5, time_limit=5.0, verbose=True):
    """
    convenience function - find best move with given constraints.
    """
    move, score, d = iterative_deepening(
        board, max_depth=depth, time_limit=time_limit, verbose=verbose
    )
    return move, score
