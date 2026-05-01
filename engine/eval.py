"""
eval.py - position evaluation

this is where the engine's "understanding" of chess lives.
a better eval = stronger play. we use a combination of:

1. material counting (obvious)
2. piece-square tables (position matters a lot)
3. king safety (pawn shield, etc.)
4. pawn structure (doubled, isolated, passed pawns)
5. mobility (how many squares can your pieces reach)

all scores are in centipawns from white's perspective.
positive = white is better, negative = black is better.
"""

from engine.bitboard import (
    Board, bit, lsb, iter_bits, popcount, file_of, rank_of, sq,
    PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING,
    WHITE, BLACK,
    FILE_A, FILE_B, FILE_C, FILE_D, FILE_E, FILE_F, FILE_G, FILE_H,
    RANK_1, RANK_2, RANK_3, RANK_4, RANK_5, RANK_6, RANK_7, RANK_8,
    FILES,
)
from engine.move_gen import (
    KNIGHT_ATTACKS, KING_ATTACKS, bishop_attacks, rook_attacks,
    queen_attacks, is_in_check,
)


# --- material values ---
PIECE_VALUES = {
    PAWN: 100,
    KNIGHT: 320,
    BISHOP: 330,
    ROOK: 500,
    QUEEN: 900,
    KING: 20000,
}


# --- piece-square tables ---
# these are from white's perspective, indexed 0-63 (a1=0 ... h8=63)
# for black, we mirror them vertically

# pawns want to push forward and control the center
PAWN_TABLE = [
     0,  0,  0,  0,  0,  0,  0,  0,
     5, 10, 10,-20,-20, 10, 10,  5,
     5, -5,-10,  0,  0,-10, -5,  5,
     0,  0,  0, 20, 20,  0,  0,  0,
     5,  5, 10, 25, 25, 10,  5,  5,
    10, 10, 20, 30, 30, 20, 10, 10,
    50, 50, 50, 50, 50, 50, 50, 50,
     0,  0,  0,  0,  0,  0,  0,  0,
]

# knights love the center, hate the edges
KNIGHT_TABLE = [
    -50,-40,-30,-30,-30,-30,-40,-50,
    -40,-20,  0,  5,  5,  0,-20,-40,
    -30,  5, 10, 15, 15, 10,  5,-30,
    -30,  0, 15, 20, 20, 15,  0,-30,
    -30,  5, 15, 20, 20, 15,  5,-30,
    -30,  0, 10, 15, 15, 10,  0,-30,
    -40,-20,  0,  0,  0,  0,-20,-40,
    -50,-40,-30,-30,-30,-30,-40,-50,
]

# bishops like long diagonals
BISHOP_TABLE = [
    -20,-10,-10,-10,-10,-10,-10,-20,
    -10,  5,  0,  0,  0,  0,  5,-10,
    -10, 10, 10, 10, 10, 10, 10,-10,
    -10,  0, 10, 10, 10, 10,  0,-10,
    -10,  5,  5, 10, 10,  5,  5,-10,
    -10,  0,  5, 10, 10,  5,  0,-10,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -20,-10,-10,-10,-10,-10,-10,-20,
]

# rooks want open files and the 7th rank
ROOK_TABLE = [
     0,  0,  0,  5,  5,  0,  0,  0,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
     5, 10, 10, 10, 10, 10, 10,  5,
     0,  0,  0,  0,  0,  0,  0,  0,
]

# queen is fine almost anywhere, slight center preference
QUEEN_TABLE = [
    -20,-10,-10, -5, -5,-10,-10,-20,
    -10,  0,  5,  0,  0,  0,  0,-10,
    -10,  5,  5,  5,  5,  5,  0,-10,
      0,  0,  5,  5,  5,  5,  0, -5,
     -5,  0,  5,  5,  5,  5,  0, -5,
    -10,  0,  5,  5,  5,  5,  0,-10,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -20,-10,-10, -5, -5,-10,-10,-20,
]

# king middlegame - stay castled and safe
KING_TABLE_MG = [
     20, 30, 10,  0,  0, 10, 30, 20,
     20, 20,  0,  0,  0,  0, 20, 20,
    -10,-20,-20,-20,-20,-20,-20,-10,
    -20,-30,-30,-40,-40,-30,-30,-20,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
]

# king endgame - should be active and centralized
KING_TABLE_EG = [
    -50,-30,-30,-30,-30,-30,-30,-50,
    -30,-30,  0,  0,  0,  0,-30,-30,
    -30,-10, 20, 30, 30, 20,-10,-30,
    -30,-10, 30, 40, 40, 30,-10,-30,
    -30,-10, 30, 40, 40, 30,-10,-30,
    -30,-10, 20, 30, 30, 20,-10,-30,
    -30,-20,-10,  0,  0,-10,-20,-30,
    -50,-40,-30,-20,-20,-30,-40,-50,
]

PST = {
    PAWN: PAWN_TABLE,
    KNIGHT: KNIGHT_TABLE,
    BISHOP: BISHOP_TABLE,
    ROOK: ROOK_TABLE,
    QUEEN: QUEEN_TABLE,
}


def mirror_square(s):
    """flip a square vertically (for black's perspective)"""
    return sq(file_of(s), 7 - rank_of(s))


def is_endgame(board):
    """
    rough endgame detection.
    if both sides have no queens, or if every side with a queen
    has at most one minor piece, it's probably endgame.
    """
    white_queens = popcount(board.pieces[WHITE][QUEEN])
    black_queens = popcount(board.pieces[BLACK][QUEEN])

    if white_queens == 0 and black_queens == 0:
        return True

    white_minors = (popcount(board.pieces[WHITE][KNIGHT]) +
                    popcount(board.pieces[WHITE][BISHOP]))
    black_minors = (popcount(board.pieces[BLACK][KNIGHT]) +
                    popcount(board.pieces[BLACK][BISHOP]))
    white_rooks = popcount(board.pieces[WHITE][ROOK])
    black_rooks = popcount(board.pieces[BLACK][ROOK])

    # if both sides have queen + at most 1 minor and no rooks
    white_heavy = white_queens > 0 and white_minors <= 1 and white_rooks == 0
    black_heavy = black_queens > 0 and black_minors <= 1 and black_rooks == 0

    if white_heavy and black_heavy:
        return True

    # total material check
    total = (white_minors + black_minors +
             white_rooks + black_rooks +
             white_queens * 2 + black_queens * 2)
    return total <= 4


def eval_material(board):
    """basic material count"""
    score = 0
    for pt in range(5):  # skip king
        white_count = popcount(board.pieces[WHITE][pt])
        black_count = popcount(board.pieces[BLACK][pt])
        score += (white_count - black_count) * PIECE_VALUES[pt]
    return score


def eval_pst(board):
    """piece-square table evaluation"""
    score = 0
    endgame = is_endgame(board)

    for pt in range(5):  # non-king pieces
        table = PST[pt]
        for s in iter_bits(board.pieces[WHITE][pt]):
            score += table[s]
        for s in iter_bits(board.pieces[BLACK][pt]):
            score -= table[mirror_square(s)]

    # king uses different table based on game phase
    king_table = KING_TABLE_EG if endgame else KING_TABLE_MG

    wk = board.king_sq(WHITE)
    bk = board.king_sq(BLACK)
    if wk >= 0:
        score += king_table[wk]
    if bk >= 0:
        score -= king_table[mirror_square(bk)]

    return score


def eval_pawn_structure(board):
    """
    evaluate pawn structure:
    - doubled pawns (bad)
    - isolated pawns (bad)
    - passed pawns (good)
    """
    score = 0

    for color in (WHITE, BLACK):
        sign = 1 if color == WHITE else -1
        pawns = board.pieces[color][PAWN]
        enemy_pawns = board.pieces[1 - color][PAWN]

        for f in range(8):
            file_mask = FILES[f]
            our_on_file = popcount(pawns & file_mask)

            # doubled pawns penalty
            if our_on_file > 1:
                score += sign * (-15 * (our_on_file - 1))

            # isolated pawns - no friendly pawns on adjacent files
            if our_on_file > 0:
                adj_files = 0
                if f > 0:
                    adj_files |= FILES[f - 1]
                if f < 7:
                    adj_files |= FILES[f + 1]

                if not (pawns & adj_files):
                    score += sign * (-10 * our_on_file)

            # passed pawns - no enemy pawns on this file or adjacent
            # files that can block or capture our pawn
            for s in iter_bits(pawns & file_mask):
                r = rank_of(s)
                is_passed = True

                # check files ahead for enemy pawns
                check_files = file_mask
                if f > 0:
                    check_files |= FILES[f - 1]
                if f < 7:
                    check_files |= FILES[f + 1]

                if color == WHITE:
                    # check ranks above
                    for rr in range(r + 1, 8):
                        ahead_mask = check_files & (0xFF << (rr * 8))
                        if enemy_pawns & ahead_mask:
                            is_passed = False
                            break
                else:
                    # check ranks below
                    for rr in range(0, r):
                        ahead_mask = check_files & (0xFF << (rr * 8))
                        if enemy_pawns & ahead_mask:
                            is_passed = False
                            break

                if is_passed:
                    # bonus based on how far advanced
                    if color == WHITE:
                        score += sign * (10 + r * 10)
                    else:
                        score += sign * (10 + (7 - r) * 10)

    return score


def eval_king_safety(board):
    """
    basic king safety: check pawn shield in front of king.
    only matters in middlegame.
    """
    if is_endgame(board):
        return 0

    score = 0

    for color in (WHITE, BLACK):
        sign = 1 if color == WHITE else -1
        king = board.king_sq(color)
        if king < 0:
            continue

        kf = file_of(king)
        kr = rank_of(king)
        our_pawns = board.pieces[color][PAWN]

        # check the 3 squares in front of the king for pawns
        shield_bonus = 0
        pawn_dir = 1 if color == WHITE else -1

        for df in [-1, 0, 1]:
            sf = kf + df
            if sf < 0 or sf > 7:
                continue

            # check one and two squares ahead
            sr1 = kr + pawn_dir
            sr2 = kr + 2 * pawn_dir

            if 0 <= sr1 <= 7 and (our_pawns & bit(sq(sf, sr1))):
                shield_bonus += 10
            elif 0 <= sr2 <= 7 and (our_pawns & bit(sq(sf, sr2))):
                shield_bonus += 5

        score += sign * shield_bonus

    return score


def eval_mobility(board):
    """
    count available squares for each piece.
    more mobility = more flexibility = better position.
    we use a simplified version - just count attacked squares.
    """
    score = 0
    occ = board.all_occupancy()

    for color in (WHITE, BLACK):
        sign = 1 if color == WHITE else -1
        our_pieces = board.occupancy(color)

        mobility = 0

        # knight mobility
        for s in iter_bits(board.pieces[color][KNIGHT]):
            moves = popcount(KNIGHT_ATTACKS[s] & ~our_pieces)
            mobility += moves

        # bishop mobility
        for s in iter_bits(board.pieces[color][BISHOP]):
            moves = popcount(bishop_attacks(s, occ) & ~our_pieces)
            mobility += moves

        # rook mobility
        for s in iter_bits(board.pieces[color][ROOK]):
            moves = popcount(rook_attacks(s, occ) & ~our_pieces)
            mobility += moves

        # queen mobility (weighted less to avoid queen wandering)
        for s in iter_bits(board.pieces[color][QUEEN]):
            moves = popcount(queen_attacks(s, occ) & ~our_pieces)
            mobility += moves // 2

        score += sign * mobility * 3  # 3 centipawns per square

    return score


def eval_bishop_pair(board):
    """
    bishop pair bonus - two bishops work together really well
    """
    score = 0
    if popcount(board.pieces[WHITE][BISHOP]) >= 2:
        score += 30
    if popcount(board.pieces[BLACK][BISHOP]) >= 2:
        score -= 30
    return score


def eval_rook_on_open_file(board):
    """
    rooks are stronger on open/semi-open files
    """
    score = 0
    all_pawns = board.pieces[WHITE][PAWN] | board.pieces[BLACK][PAWN]

    for color in (WHITE, BLACK):
        sign = 1 if color == WHITE else -1
        for s in iter_bits(board.pieces[color][ROOK]):
            f = file_of(s)
            file_mask = FILES[f]

            if not (all_pawns & file_mask):
                score += sign * 15  # fully open file
            elif not (board.pieces[color][PAWN] & file_mask):
                score += sign * 8   # semi-open file

    return score


def evaluate(board):
    """
    main evaluation function.
    returns score in centipawns from the side to move's perspective.
    """
    # check for checkmate/stalemate - these are handled in search
    # so we just do a static eval here

    score = 0
    score += eval_material(board)
    score += eval_pst(board)
    score += eval_pawn_structure(board)
    score += eval_king_safety(board)
    score += eval_mobility(board)
    score += eval_bishop_pair(board)
    score += eval_rook_on_open_file(board)

    # return from side to move's perspective
    if board.side == BLACK:
        score = -score

    return score


# this gets used by move ordering
MVV_LVA = [
    # victim:  P    N    B    R    Q    K
    [0] * 6,   # attacker: P  (not used this way)
    [0] * 6,   # N
    [0] * 6,   # B
    [0] * 6,   # R
    [0] * 6,   # Q
    [0] * 6,   # K
]

# fill in MVV-LVA table
# most valuable victim - least valuable attacker
_victim_scores = {PAWN: 10, KNIGHT: 30, BISHOP: 30, ROOK: 50, QUEEN: 90, KING: 0}
_attacker_scores = {PAWN: 1, KNIGHT: 2, BISHOP: 3, ROOK: 4, QUEEN: 5, KING: 6}

for _attacker in range(6):
    for _victim in range(6):
        MVV_LVA[_attacker][_victim] = (
            _victim_scores.get(_victim, 0) * 10 - _attacker_scores.get(_attacker, 0)
        )
