"""
fen.py - FEN (Forsyth-Edwards Notation) support

FEN is the standard way to describe a chess position in a single line.
example starting position:
  rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1

fields:
  1. piece placement (rank 8 to rank 1, separated by /)
  2. active color (w or b)
  3. castling availability (KQkq or -)
  4. en passant target square (or -)
  5. halfmove clock
  6. fullmove number
"""

from engine.bitboard import (
    Board, sq, file_of, rank_of, bit, SQUARE_NAMES,
    PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING,
    WHITE, BLACK,
    CASTLE_WK, CASTLE_WQ, CASTLE_BK, CASTLE_BQ,
    CHAR_TO_PIECE, PIECE_CHARS,
)


STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def parse_fen(fen_string):
    """
    parse a FEN string and return a Board.
    """
    board = Board()
    board.castling = 0  # clear defaults, we'll set from FEN

    parts = fen_string.strip().split()
    if len(parts) < 4:
        raise ValueError(f"bad FEN: need at least 4 fields, got {len(parts)}")

    # 1. piece placement
    rank_strs = parts[0].split('/')
    if len(rank_strs) != 8:
        raise ValueError(f"bad FEN: expected 8 ranks, got {len(rank_strs)}")

    for rank_idx, rank_str in enumerate(rank_strs):
        r = 7 - rank_idx  # FEN starts from rank 8
        f = 0
        for ch in rank_str:
            if ch.isdigit():
                f += int(ch)
            elif ch in CHAR_TO_PIECE:
                color, piece_type = CHAR_TO_PIECE[ch]
                board.put_piece(color, piece_type, sq(f, r))
                f += 1
            else:
                raise ValueError(f"bad FEN: unknown piece char '{ch}'")

    # 2. active color
    if len(parts) > 1:
        if parts[1] == 'w':
            board.side = WHITE
        elif parts[1] == 'b':
            board.side = BLACK
        else:
            raise ValueError(f"bad FEN: unknown color '{parts[1]}'")

    # 3. castling
    if len(parts) > 2:
        castle_str = parts[2]
        if castle_str != '-':
            if 'K' in castle_str:
                board.castling |= CASTLE_WK
            if 'Q' in castle_str:
                board.castling |= CASTLE_WQ
            if 'k' in castle_str:
                board.castling |= CASTLE_BK
            if 'q' in castle_str:
                board.castling |= CASTLE_BQ

    # 4. en passant
    if len(parts) > 3:
        ep_str = parts[3]
        if ep_str != '-':
            from engine.bitboard import sq_from_name
            board.ep_square = sq_from_name(ep_str)

    # 5. halfmove clock
    if len(parts) > 4:
        board.halfmove = int(parts[4])

    # 6. fullmove number
    if len(parts) > 5:
        board.fullmove = int(parts[5])

    return board


def to_fen(board):
    """
    convert board state to FEN string.
    """
    parts = []

    # 1. piece placement
    ranks = []
    for r in range(7, -1, -1):
        empty = 0
        rank_str = ""
        for f in range(8):
            piece = board.piece_at(sq(f, r))
            if piece is None:
                empty += 1
            else:
                if empty > 0:
                    rank_str += str(empty)
                    empty = 0
                color, pt = piece
                rank_str += PIECE_CHARS[(color, pt)]
        if empty > 0:
            rank_str += str(empty)
        ranks.append(rank_str)
    parts.append('/'.join(ranks))

    # 2. active color
    parts.append('w' if board.side == WHITE else 'b')

    # 3. castling
    castle = ""
    if board.castling & CASTLE_WK:
        castle += 'K'
    if board.castling & CASTLE_WQ:
        castle += 'Q'
    if board.castling & CASTLE_BK:
        castle += 'k'
    if board.castling & CASTLE_BQ:
        castle += 'q'
    parts.append(castle if castle else '-')

    # 4. en passant
    if board.ep_square >= 0:
        parts.append(SQUARE_NAMES[board.ep_square])
    else:
        parts.append('-')

    # 5. halfmove clock
    parts.append(str(board.halfmove))

    # 6. fullmove number
    parts.append(str(board.fullmove))

    return ' '.join(parts)


def setup_start_position():
    """convenience: create a board with the starting position"""
    return parse_fen(STARTING_FEN)
