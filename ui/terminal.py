"""
terminal.py - terminal-based chess UI

features:
- unicode chess pieces (looks nice on most terminals)
- colored board (ANSI escape codes)
- shows evaluation score
- shows best move suggestion
- input validation

note: colors might not work on older windows terminals.
on windows 10+ and most linux/mac terminals it's fine.
"""

import os
import sys

from engine.bitboard import (
    Board, sq, file_of, rank_of, bit, SQUARE_NAMES,
    PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING,
    WHITE, BLACK,
)
from engine.move_gen import generate_legal_moves, is_in_check
from engine.eval import evaluate, PIECE_VALUES
from formats.fen import to_fen


# --- unicode piece symbols ---
UNICODE_PIECES = {
    (WHITE, KING):   '♔',
    (WHITE, QUEEN):  '♕',
    (WHITE, ROOK):   '♖',
    (WHITE, BISHOP): '♗',
    (WHITE, KNIGHT): '♘',
    (WHITE, PAWN):   '♙',
    (BLACK, KING):   '♚',
    (BLACK, QUEEN):  '♛',
    (BLACK, ROOK):   '♜',
    (BLACK, BISHOP): '♝',
    (BLACK, KNIGHT): '♞',
    (BLACK, PAWN):   '♟',
}

# fallback ASCII pieces for terminals that don't support unicode
ASCII_PIECES = {
    (WHITE, KING):   'K',
    (WHITE, QUEEN):  'Q',
    (WHITE, ROOK):   'R',
    (WHITE, BISHOP): 'B',
    (WHITE, KNIGHT): 'N',
    (WHITE, PAWN):   'P',
    (BLACK, KING):   'k',
    (BLACK, QUEEN):  'q',
    (BLACK, ROOK):   'r',
    (BLACK, BISHOP): 'b',
    (BLACK, KNIGHT): 'n',
    (BLACK, PAWN):   'p',
}


# --- ANSI color codes ---
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

    # piece colors
    WHITE_PIECE = '\033[97m'      # bright white
    BLACK_PIECE = '\033[30m'      # black

    # square colors
    LIGHT_SQ = '\033[48;5;180m'   # light tan
    DARK_SQ = '\033[48;5;95m'     # dark brown

    # highlights
    HIGHLIGHT = '\033[48;5;228m'  # yellow for last move
    CHECK = '\033[48;5;196m'      # red for check

    # UI colors
    HEADER = '\033[38;5;39m'      # blue
    INFO = '\033[38;5;246m'       # gray
    GOOD = '\033[38;5;82m'        # green
    BAD = '\033[38;5;196m'        # red
    WARN = '\033[38;5;214m'       # orange


def _supports_color():
    """rough check for ANSI color support"""
    if os.name == 'nt':
        # enable ANSI on windows
        try:
            os.system('')  # this enables ANSI escape codes on win10+
            return True
        except Exception:
            return False
    return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()


USE_COLOR = _supports_color()
USE_UNICODE = True  # set to False if your terminal can't handle it


def colorize(text, color):
    if USE_COLOR:
        return color + text + Colors.RESET
    return text


def print_board(board, last_move=None, flipped=False):
    """
    print the board to terminal with colors and unicode pieces.
    """
    print()

    # figure out if king is in check (for highlighting)
    check_sq = -1
    if is_in_check(board, board.side):
        check_sq = board.king_sq(board.side)

    # highlight squares for last move
    highlight_sqs = set()
    if last_move:
        highlight_sqs.add(last_move.from_sq)
        highlight_sqs.add(last_move.to_sq)

    ranks = range(8) if flipped else range(7, -1, -1)
    files = range(7, -1, -1) if flipped else range(8)

    pieces = UNICODE_PIECES if USE_UNICODE else ASCII_PIECES

    for r in ranks:
        # rank number on the left
        rank_label = colorize(f" {r + 1} ", Colors.DIM)
        print(rank_label, end='')

        for f in files:
            s = sq(f, r)
            piece = board.piece_at(s)

            # determine square color
            is_light = (f + r) % 2 == 1
            if s == check_sq:
                bg = Colors.CHECK
            elif s in highlight_sqs:
                bg = Colors.HIGHLIGHT
            elif is_light:
                bg = Colors.LIGHT_SQ
            else:
                bg = Colors.DARK_SQ

            if piece is not None:
                color, pt = piece
                symbol = pieces[(color, pt)]
                fg = Colors.WHITE_PIECE if color == WHITE else Colors.BLACK_PIECE
                if USE_COLOR:
                    cell = f"{bg}{fg} {symbol} {Colors.RESET}"
                else:
                    cell = f" {symbol} "
            else:
                if USE_COLOR:
                    cell = f"{bg}   {Colors.RESET}"
                else:
                    cell = " . "

            print(cell, end='')

        print()

    # file labels at bottom
    file_chars = 'hgfedcba' if flipped else 'abcdefgh'
    file_label = "    " + "  ".join(file_chars)
    print(colorize(file_label, Colors.DIM))
    print()


def print_eval(board):
    """show current evaluation"""
    score = evaluate(board)

    # convert to white's perspective for display
    display_score = score if board.side == WHITE else -score

    if display_score > 100:
        color = Colors.GOOD
        indicator = "+"
    elif display_score < -100:
        color = Colors.BAD
        indicator = ""
    else:
        color = Colors.INFO
        indicator = "+" if display_score >= 0 else ""

    pawns = display_score / 100.0
    print(colorize(f"  eval: {indicator}{pawns:.2f}", color))


def print_material(board):
    """show material count"""
    white_mat = 0
    black_mat = 0
    from engine.bitboard import popcount

    for pt in range(5):  # skip king
        w = popcount(board.pieces[WHITE][pt])
        b = popcount(board.pieces[BLACK][pt])
        white_mat += w * PIECE_VALUES[pt]
        black_mat += b * PIECE_VALUES[pt]

    diff = (white_mat - black_mat) / 100.0
    if diff > 0:
        print(colorize(f"  material: white +{diff:.1f}", Colors.GOOD))
    elif diff < 0:
        print(colorize(f"  material: black +{-diff:.1f}", Colors.BAD))
    else:
        print(colorize("  material: equal", Colors.INFO))


def print_game_info(board):
    """show turn, castling rights, etc."""
    side_str = "White" if board.side == WHITE else "Black"
    print(colorize(f"  {side_str} to move", Colors.BOLD))

    # castling
    castle = ""
    if board.castling & 1: castle += "K"
    if board.castling & 2: castle += "Q"
    if board.castling & 4: castle += "k"
    if board.castling & 8: castle += "q"
    if not castle: castle = "-"
    print(colorize(f"  castling: {castle}", Colors.INFO))

    print(colorize(f"  move: {board.fullmove}", Colors.INFO))

    if is_in_check(board, board.side):
        print(colorize("  *** CHECK ***", Colors.BAD + Colors.BOLD))


def get_player_move(board):
    """
    get a move from the player via text input.
    accepts UCI format (e2e4) or algebraic (e4, Nf3, etc.)
    """
    from formats.pgn import san_to_move
    from engine.bitboard import sq_from_name

    legal = generate_legal_moves(board)

    while True:
        try:
            raw = input(colorize("  your move: ", Colors.HEADER)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None

        if not raw:
            continue

        # special commands
        if raw.lower() in ('quit', 'exit', 'q'):
            return None
        if raw.lower() == 'moves':
            print("  legal moves:", ' '.join(m.uci() for m in legal))
            continue
        if raw.lower() == 'fen':
            print(f"  {to_fen(board)}")
            continue
        if raw.lower() == 'help':
            print("  enter moves in UCI (e2e4) or algebraic (Nf3) format")
            print("  commands: moves, fen, hint, undo, quit")
            continue
        if raw.lower() in ('hint', 'suggest'):
            return 'hint'
        if raw.lower() == 'undo':
            return 'undo'

        # try UCI format first (e.g., e2e4, e7e8q)
        if len(raw) in (4, 5):
            try:
                from_sq = sq_from_name(raw[0:2])
                to_sq = sq_from_name(raw[2:4])
                promo = None
                if len(raw) == 5:
                    promo_map = {'q': QUEEN, 'r': ROOK, 'b': BISHOP, 'n': KNIGHT}
                    promo = promo_map.get(raw[4].lower())

                for m in legal:
                    if (m.from_sq == from_sq and m.to_sq == to_sq and
                        m.promotion == promo):
                        return m
            except (ValueError, IndexError):
                pass

        # try SAN format
        move = san_to_move(board, raw)
        if move:
            return move

        print(colorize("  invalid move. type 'moves' for legal moves.", Colors.WARN))


def print_header():
    """show a nice header"""
    print()
    print(colorize("  ╔═══════════════════════════════════╗", Colors.HEADER))
    print(colorize("  ║        ♔ CHESS ENGINE ♚           ║", Colors.HEADER))
    print(colorize("  ║     terminal edition v1.0         ║", Colors.HEADER))
    print(colorize("  ╚═══════════════════════════════════╝", Colors.HEADER))
    print()


def print_menu():
    """show the main menu"""
    print(colorize("  [1] Play vs Engine (white)", Colors.INFO))
    print(colorize("  [2] Play vs Engine (black)", Colors.INFO))
    print(colorize("  [3] Engine vs Engine", Colors.INFO))
    print(colorize("  [4] Analyze position (FEN)", Colors.INFO))
    print(colorize("  [5] Load PGN file", Colors.INFO))
    print(colorize("  [6] Perft test", Colors.INFO))
    print(colorize("  [7] Quit", Colors.INFO))
    print()


def get_menu_choice():
    """get menu selection"""
    while True:
        try:
            choice = input(colorize("  select: ", Colors.HEADER)).strip()
        except (EOFError, KeyboardInterrupt):
            return 7
        if choice in ('1', '2', '3', '4', '5', '6', '7'):
            return int(choice)
        print(colorize("  pick 1-7", Colors.WARN))


def print_result(result_str):
    """show game result"""
    print()
    print(colorize("  ═══════════════════════════════", Colors.HEADER))
    if result_str == "1-0":
        print(colorize("  White wins!", Colors.GOOD + Colors.BOLD))
    elif result_str == "0-1":
        print(colorize("  Black wins!", Colors.BAD + Colors.BOLD))
    elif result_str == "1/2-1/2":
        print(colorize("  Draw!", Colors.WARN + Colors.BOLD))
    else:
        print(colorize(f"  Game over: {result_str}", Colors.INFO))
    print(colorize("  ═══════════════════════════════", Colors.HEADER))
    print()
