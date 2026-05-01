"""
move_gen.py - move generation

this is the hardest part of any chess engine. we generate
pseudo-legal moves first, then the caller filters out ones
that leave the king in check.

for sliding pieces (bishop, rook, queen) we use a simple
ray-tracing approach. not as fast as magic bitboards but
way easier to get right, and for python it doesn't matter
that much anyway.
"""

from engine.bitboard import (
    Board, Move, bit, lsb, iter_bits, popcount, file_of, rank_of, sq,
    PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING,
    WHITE, BLACK,
    FILE_A, FILE_H, NOT_FILE_A, NOT_FILE_H, NOT_FILE_AB, NOT_FILE_GH,
    RANK_1, RANK_2, RANK_3, RANK_4, RANK_5, RANK_6, RANK_7, RANK_8,
    CASTLE_WK, CASTLE_WQ, CASTLE_BK, CASTLE_BQ,
    SQUARE_NAMES, FULL_BOARD,
)


# --- precomputed attack tables ---
# these get filled in at import time

KNIGHT_ATTACKS = [0] * 64
KING_ATTACKS = [0] * 64
PAWN_ATTACKS = [[0] * 64, [0] * 64]  # [color][square]


def _init_knight_attacks():
    """precompute knight attack bitboards"""
    for s in range(64):
        f, r = file_of(s), rank_of(s)
        attacks = 0
        # all 8 possible knight jumps
        for df, dr in [(-2,-1),(-2,1),(-1,-2),(-1,2),
                       (1,-2),(1,2),(2,-1),(2,1)]:
            nf, nr = f + df, r + dr
            if 0 <= nf <= 7 and 0 <= nr <= 7:
                attacks |= bit(sq(nf, nr))
        KNIGHT_ATTACKS[s] = attacks


def _init_king_attacks():
    """precompute king attack bitboards"""
    for s in range(64):
        f, r = file_of(s), rank_of(s)
        attacks = 0
        for df in [-1, 0, 1]:
            for dr in [-1, 0, 1]:
                if df == 0 and dr == 0:
                    continue
                nf, nr = f + df, r + dr
                if 0 <= nf <= 7 and 0 <= nr <= 7:
                    attacks |= bit(sq(nf, nr))
        KING_ATTACKS[s] = attacks


def _init_pawn_attacks():
    """precompute pawn attack bitboards (captures only, not pushes)"""
    for s in range(64):
        f, r = file_of(s), rank_of(s)

        # white pawn attacks (going up)
        w_atk = 0
        if r < 7:
            if f > 0:
                w_atk |= bit(sq(f - 1, r + 1))
            if f < 7:
                w_atk |= bit(sq(f + 1, r + 1))
        PAWN_ATTACKS[WHITE][s] = w_atk

        # black pawn attacks (going down)
        b_atk = 0
        if r > 0:
            if f > 0:
                b_atk |= bit(sq(f - 1, r - 1))
            if f < 7:
                b_atk |= bit(sq(f + 1, r - 1))
        PAWN_ATTACKS[BLACK][s] = b_atk


# init everything on module load
_init_knight_attacks()
_init_king_attacks()
_init_pawn_attacks()


# --- sliding piece attack generation ---

# direction deltas: (file_delta, rank_delta)
BISHOP_DIRS = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
ROOK_DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1)]
QUEEN_DIRS = BISHOP_DIRS + ROOK_DIRS


def sliding_attacks(square, occupancy, directions):
    """
    trace rays in given directions, stopping at blockers.
    returns the attack bitboard including the first blocker
    in each direction (so we can capture it).
    """
    attacks = 0
    f, r = file_of(square), rank_of(square)

    for df, dr in directions:
        cf, cr = f + df, r + dr
        while 0 <= cf <= 7 and 0 <= cr <= 7:
            target_sq = sq(cf, cr)
            attacks |= bit(target_sq)
            if occupancy & bit(target_sq):
                break  # hit a piece, stop the ray
            cf += df
            cr += dr

    return attacks


def bishop_attacks(square, occupancy):
    return sliding_attacks(square, occupancy, BISHOP_DIRS)


def rook_attacks(square, occupancy):
    return sliding_attacks(square, occupancy, ROOK_DIRS)


def queen_attacks(square, occupancy):
    return sliding_attacks(square, occupancy, QUEEN_DIRS)


# --- attack detection ---

def is_square_attacked(board, square, by_color):
    """
    check if a square is attacked by any piece of 'by_color'.
    this is used for check detection and castling legality.
    """
    occ = board.all_occupancy()

    # knight attacks
    if KNIGHT_ATTACKS[square] & board.pieces[by_color][KNIGHT]:
        return True

    # king attacks (for adjacent king detection)
    if KING_ATTACKS[square] & board.pieces[by_color][KING]:
        return True

    # pawn attacks - use the OPPOSITE color's pawn attack from our square
    # because if a white pawn on e5 attacks f6, then from f6's perspective
    # a black pawn attack pattern points to e5
    defender_color = 1 - by_color
    if PAWN_ATTACKS[defender_color][square] & board.pieces[by_color][PAWN]:
        return True

    # bishop/queen (diagonal)
    diag = bishop_attacks(square, occ)
    if diag & (board.pieces[by_color][BISHOP] | board.pieces[by_color][QUEEN]):
        return True

    # rook/queen (straight lines)
    straight = rook_attacks(square, occ)
    if straight & (board.pieces[by_color][ROOK] | board.pieces[by_color][QUEEN]):
        return True

    return False


def is_in_check(board, color):
    """is the king of 'color' currently in check?"""
    king = board.king_sq(color)
    if king < 0:
        return False
    return is_square_attacked(board, king, 1 - color)


# --- move generation ---

def generate_pawn_moves(board, moves):
    """generate all pseudo-legal pawn moves"""
    us = board.side
    them = 1 - us
    our_pawns = board.pieces[us][PAWN]
    occ = board.all_occupancy()
    their_pieces = board.occupancy(them)

    if us == WHITE:
        push_dir = 8
        start_rank = RANK_2
        promo_rank = RANK_8
        double_rank = RANK_4
    else:
        push_dir = -8
        start_rank = RANK_7
        promo_rank = RANK_1
        double_rank = RANK_5

    for from_sq in iter_bits(our_pawns):
        # single push
        to_sq = from_sq + push_dir
        if 0 <= to_sq <= 63 and not (occ & bit(to_sq)):
            if bit(to_sq) & promo_rank:
                # promotion - generate all 4 options
                for promo in [QUEEN, ROOK, BISHOP, KNIGHT]:
                    moves.append(Move(from_sq, to_sq, PAWN, promotion=promo))
            else:
                moves.append(Move(from_sq, to_sq, PAWN))

                # double push (only if single push was possible)
                if bit(from_sq) & start_rank:
                    to_sq2 = from_sq + 2 * push_dir
                    if not (occ & bit(to_sq2)):
                        moves.append(Move(from_sq, to_sq2, PAWN,
                                         is_double_push=True))

        # captures
        atk = PAWN_ATTACKS[us][from_sq]
        captures = atk & their_pieces
        for to_sq in iter_bits(captures):
            target = board.piece_at(to_sq)
            cap_type = target[1] if target else None
            if bit(to_sq) & promo_rank:
                for promo in [QUEEN, ROOK, BISHOP, KNIGHT]:
                    moves.append(Move(from_sq, to_sq, PAWN,
                                     captured=cap_type, promotion=promo))
            else:
                moves.append(Move(from_sq, to_sq, PAWN, captured=cap_type))

        # en passant
        if board.ep_square >= 0:
            if PAWN_ATTACKS[us][from_sq] & bit(board.ep_square):
                moves.append(Move(from_sq, board.ep_square, PAWN,
                                 captured=PAWN, is_ep=True))


def generate_knight_moves(board, moves):
    us = board.side
    our_pieces = board.occupancy(us)
    knights = board.pieces[us][KNIGHT]

    for from_sq in iter_bits(knights):
        targets = KNIGHT_ATTACKS[from_sq] & ~our_pieces
        for to_sq in iter_bits(targets):
            target = board.piece_at(to_sq)
            cap = target[1] if target else None
            moves.append(Move(from_sq, to_sq, KNIGHT, captured=cap))


def generate_bishop_moves(board, moves):
    us = board.side
    our_pieces = board.occupancy(us)
    occ = board.all_occupancy()
    bishops = board.pieces[us][BISHOP]

    for from_sq in iter_bits(bishops):
        targets = bishop_attacks(from_sq, occ) & ~our_pieces
        for to_sq in iter_bits(targets):
            target = board.piece_at(to_sq)
            cap = target[1] if target else None
            moves.append(Move(from_sq, to_sq, BISHOP, captured=cap))


def generate_rook_moves(board, moves):
    us = board.side
    our_pieces = board.occupancy(us)
    occ = board.all_occupancy()
    rooks = board.pieces[us][ROOK]

    for from_sq in iter_bits(rooks):
        targets = rook_attacks(from_sq, occ) & ~our_pieces
        for to_sq in iter_bits(targets):
            target = board.piece_at(to_sq)
            cap = target[1] if target else None
            moves.append(Move(from_sq, to_sq, ROOK, captured=cap))


def generate_queen_moves(board, moves):
    us = board.side
    our_pieces = board.occupancy(us)
    occ = board.all_occupancy()
    queens = board.pieces[us][QUEEN]

    for from_sq in iter_bits(queens):
        targets = queen_attacks(from_sq, occ) & ~our_pieces
        for to_sq in iter_bits(targets):
            target = board.piece_at(to_sq)
            cap = target[1] if target else None
            moves.append(Move(from_sq, to_sq, QUEEN, captured=cap))


def generate_king_moves(board, moves):
    us = board.side
    them = 1 - us
    our_pieces = board.occupancy(us)
    king = board.king_sq(us)
    if king < 0:
        return

    # normal moves
    targets = KING_ATTACKS[king] & ~our_pieces
    for to_sq in iter_bits(targets):
        target = board.piece_at(to_sq)
        cap = target[1] if target else None
        moves.append(Move(king, to_sq, KING, captured=cap))

    # castling
    occ = board.all_occupancy()

    if us == WHITE:
        # kingside
        if (board.castling & CASTLE_WK and
            not (occ & (bit(sq(5, 0)) | bit(sq(6, 0)))) and
            not is_square_attacked(board, sq(4, 0), them) and
            not is_square_attacked(board, sq(5, 0), them) and
            not is_square_attacked(board, sq(6, 0), them)):
            moves.append(Move(king, sq(6, 0), KING, is_castle=True))

        # queenside
        if (board.castling & CASTLE_WQ and
            not (occ & (bit(sq(1, 0)) | bit(sq(2, 0)) | bit(sq(3, 0)))) and
            not is_square_attacked(board, sq(4, 0), them) and
            not is_square_attacked(board, sq(3, 0), them) and
            not is_square_attacked(board, sq(2, 0), them)):
            moves.append(Move(king, sq(2, 0), KING, is_castle=True))
    else:
        # kingside
        if (board.castling & CASTLE_BK and
            not (occ & (bit(sq(5, 7)) | bit(sq(6, 7)))) and
            not is_square_attacked(board, sq(4, 7), them) and
            not is_square_attacked(board, sq(5, 7), them) and
            not is_square_attacked(board, sq(6, 7), them)):
            moves.append(Move(king, sq(6, 7), KING, is_castle=True))

        # queenside
        if (board.castling & CASTLE_BQ and
            not (occ & (bit(sq(1, 7)) | bit(sq(2, 7)) | bit(sq(3, 7)))) and
            not is_square_attacked(board, sq(4, 7), them) and
            not is_square_attacked(board, sq(3, 7), them) and
            not is_square_attacked(board, sq(2, 7), them)):
            moves.append(Move(king, sq(2, 7), KING, is_castle=True))


def generate_pseudo_legal(board):
    """
    generate all pseudo-legal moves. these might leave the
    king in check - caller needs to validate.
    """
    moves = []
    generate_pawn_moves(board, moves)
    generate_knight_moves(board, moves)
    generate_bishop_moves(board, moves)
    generate_rook_moves(board, moves)
    generate_queen_moves(board, moves)
    generate_king_moves(board, moves)
    return moves


def generate_legal_moves(board):
    """
    generate all legal moves. we do this by generating
    pseudo-legal moves, making each one, and checking
    if our king is in check afterwards. if it is, the
    move is illegal.
    """
    legal = []
    pseudo = generate_pseudo_legal(board)
    us = board.side

    for move in pseudo:
        board.make_move(move)
        # after make_move, board.side is flipped, so 'us' king
        # should not be in check
        if not is_in_check(board, us):
            legal.append(move)
        board.unmake_move()

    return legal


def generate_captures(board):
    """
    generate only capture moves (for quiescence search).
    still pseudo-legal - caller should verify legality.
    """
    moves = generate_pseudo_legal(board)
    return [m for m in moves if m.captured is not None]


def generate_legal_captures(board):
    """legal captures only"""
    legal = []
    captures = generate_captures(board)
    us = board.side

    for move in captures:
        board.make_move(move)
        if not is_in_check(board, us):
            legal.append(move)
        board.unmake_move()

    return legal


def perft(board, depth):
    """
    performance test - count leaf nodes at given depth.
    useful for verifying move generation correctness.
    """
    if depth == 0:
        return 1

    nodes = 0
    moves = generate_legal_moves(board)

    for move in moves:
        board.make_move(move)
        nodes += perft(board, depth - 1)
        board.unmake_move()

    return nodes
