"""
pgn.py - PGN (Portable Game Notation) support

PGN is the standard format for recording chess games.
we support both saving and loading games.

example:
  [Event "Casual Game"]
  [Site "Terminal"]
  [Date "2024.01.15"]
  [White "Human"]
  [Black "Engine"]
  [Result "0-1"]

  1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 0-1
"""

import datetime

from engine.bitboard import (
    PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING,
    WHITE, BLACK, SQUARE_NAMES, file_of, rank_of,
)
from engine.move_gen import generate_legal_moves, is_in_check


PIECE_LETTERS = {
    KNIGHT: 'N',
    BISHOP: 'B',
    ROOK: 'R',
    QUEEN: 'Q',
    KING: 'K',
}


def move_to_san(board, move):
    """
    convert a move to Standard Algebraic Notation (SAN).
    this is trickier than it sounds because we need to handle
    disambiguation (e.g. Rae1 vs Rfe1 when both rooks can go to e1).
    """
    # castling
    if move.is_castle:
        if file_of(move.to_sq) == 6:
            san = "O-O"
        else:
            san = "O-O-O"
    elif move.piece == PAWN:
        san = ""
        # pawn captures include the departure file
        if move.captured is not None:
            san += chr(ord('a') + file_of(move.from_sq)) + 'x'
        san += SQUARE_NAMES[move.to_sq]
        if move.promotion is not None:
            san += '=' + PIECE_LETTERS.get(move.promotion, 'Q')
    else:
        san = PIECE_LETTERS.get(move.piece, '?')

        # disambiguation - check if another piece of same type
        # can also move to the same square
        legal = generate_legal_moves(board)
        ambiguous = [m for m in legal
                     if m.piece == move.piece and
                     m.to_sq == move.to_sq and
                     m.from_sq != move.from_sq]

        if ambiguous:
            same_file = any(file_of(m.from_sq) == file_of(move.from_sq)
                           for m in ambiguous)
            same_rank = any(rank_of(m.from_sq) == rank_of(move.from_sq)
                           for m in ambiguous)

            if not same_file:
                san += chr(ord('a') + file_of(move.from_sq))
            elif not same_rank:
                san += str(rank_of(move.from_sq) + 1)
            else:
                san += SQUARE_NAMES[move.from_sq]

        if move.captured is not None:
            san += 'x'
        san += SQUARE_NAMES[move.to_sq]

    # check / checkmate indicator
    board.make_move(move)
    if is_in_check(board, board.side):
        legal_after = generate_legal_moves(board)
        if len(legal_after) == 0:
            san += '#'
        else:
            san += '+'
    board.unmake_move()

    return san


def save_pgn(filename, moves_san, headers=None, result="*"):
    """
    save a game to PGN format.

    moves_san: list of SAN strings already computed
    headers: dict of PGN headers (Event, Site, etc.)
    result: game result string ("1-0", "0-1", "1/2-1/2", or "*")
    """
    if headers is None:
        headers = {}

    # default headers
    defaults = {
        'Event': 'Casual Game',
        'Site': 'Terminal Chess Engine',
        'Date': datetime.date.today().strftime('%Y.%m.%d'),
        'Round': '-',
        'White': 'Player',
        'Black': 'Engine',
        'Result': result,
    }

    for key, val in defaults.items():
        if key not in headers:
            headers[key] = val
    headers['Result'] = result

    with open(filename, 'w') as f:
        # write headers
        for key, val in headers.items():
            f.write(f'[{key} "{val}"]\n')
        f.write('\n')

        # write moves
        line = ""
        for i, san in enumerate(moves_san):
            move_num = i // 2 + 1
            if i % 2 == 0:
                token = f"{move_num}. {san}"
            else:
                token = san

            if len(line) + len(token) + 1 > 78:
                f.write(line + '\n')
                line = token
            else:
                if line:
                    line += ' ' + token
                else:
                    line = token

        if line:
            f.write(line + ' ')
        f.write(result + '\n')


def load_pgn(filename):
    """
    load a PGN file and return headers and move text.
    note: this returns the raw SAN moves as strings.
    actually replaying them on a board requires the
    move generation to find matching moves.

    returns (headers_dict, list_of_san_moves, result)
    """
    headers = {}
    movetext = ""

    with open(filename, 'r') as f:
        in_headers = True

        for line in f:
            line = line.strip()
            if not line:
                if in_headers:
                    in_headers = False
                continue

            if in_headers and line.startswith('['):
                # parse header
                line = line.strip('[]')
                parts = line.split(' ', 1)
                if len(parts) == 2:
                    key = parts[0]
                    val = parts[1].strip('"')
                    headers[key] = val
            else:
                in_headers = False
                movetext += ' ' + line

    # parse movetext into individual SAN moves
    moves = []
    result = "*"
    tokens = movetext.split()

    for token in tokens:
        token = token.strip()
        if not token:
            continue
        # skip move numbers
        if token[0].isdigit() and '.' in token:
            # could be "1." or "1..." - skip it
            after_dots = token.split('.')[-1]
            if after_dots:
                moves.append(after_dots)
            continue
        # check for result
        if token in ('1-0', '0-1', '1/2-1/2', '*'):
            result = token
            continue
        # skip annotations
        if token.startswith('{') or token.startswith('('):
            continue
        moves.append(token)

    return headers, moves, result


def san_to_move(board, san_str):
    """
    find the legal move that matches a SAN string.
    returns the Move object or None if not found.
    """
    legal = generate_legal_moves(board)

    for move in legal:
        if move_to_san(board, move) == san_str:
            return move

    # try without check/mate symbols
    clean = san_str.rstrip('+#')
    for move in legal:
        move_san = move_to_san(board, move).rstrip('+#')
        if move_san == clean:
            return move

    return None
