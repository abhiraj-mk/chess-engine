"""
main.py - entry point for the chess engine

run this to play chess in your terminal.
usage: python main.py
"""

import sys
import time

from engine.bitboard import WHITE, BLACK, SQUARE_NAMES
from engine.move_gen import generate_legal_moves, is_in_check, perft
from engine.search import find_best_move, tt, MATE_THRESHOLD
from engine.eval import evaluate
from engine.zobrist import compute_hash
from formats.fen import parse_fen, to_fen, setup_start_position, STARTING_FEN
from formats.pgn import save_pgn, move_to_san, load_pgn, san_to_move
from ui.terminal import (
    print_board, print_eval, print_material, print_game_info,
    get_player_move, print_header, print_menu, get_menu_choice,
    print_result, colorize, Colors,
)


def play_game(player_color, engine_depth=5, engine_time=5.0):
    """
    play a game between human and engine.
    player_color: WHITE or BLACK
    """
    board = setup_start_position()
    board.hash_key = compute_hash(board)

    moves_san = []
    last_move = None
    game_over = False
    result = "*"

    while not game_over:
        print_board(board, last_move, flipped=(player_color == BLACK))
        print_game_info(board)
        print_eval(board)
        print_material(board)
        print()

        legal = generate_legal_moves(board)

        # check for game over
        if len(legal) == 0:
            if is_in_check(board, board.side):
                if board.side == WHITE:
                    result = "0-1"
                else:
                    result = "1-0"
                print_result(result)
            else:
                result = "1/2-1/2"
                print_result("Stalemate - " + result)
            game_over = True
            break

        # 50-move rule
        if board.halfmove >= 100:
            result = "1/2-1/2"
            print_result("Draw by 50-move rule")
            game_over = True
            break

        # repetition
        if board.is_repetition():
            result = "1/2-1/2"
            print_result("Draw by repetition")
            game_over = True
            break

        if board.side == player_color:
            # human's turn
            move = get_player_move(board)

            if move is None:
                # player wants to quit
                print(colorize("  game abandoned.", Colors.WARN))
                result = "*"
                game_over = True
                break
            elif move == 'hint':
                print(colorize("  thinking...", Colors.INFO))
                hint, score = find_best_move(board, depth=engine_depth,
                                            time_limit=engine_time, verbose=False)
                if hint:
                    san = move_to_san(board, hint)
                    sc = score / 100.0
                    print(colorize(f"  suggestion: {san} ({sc:+.2f})", Colors.GOOD))
                continue
            elif move == 'undo':
                # undo two moves (opponent's + ours)
                if len(board.move_history) >= 2:
                    board.unmake_move()
                    board.unmake_move()
                    if len(moves_san) >= 2:
                        moves_san.pop()
                        moves_san.pop()
                    last_move = board.move_history[-1] if board.move_history else None
                    print(colorize("  undone.", Colors.INFO))
                else:
                    print(colorize("  nothing to undo.", Colors.WARN))
                continue

            san = move_to_san(board, move)
            moves_san.append(san)
            board.make_move(move)
            board.hash_key = compute_hash(board)
            last_move = move

        else:
            # engine's turn
            print(colorize("  engine thinking...", Colors.INFO))
            move, score = find_best_move(board, depth=engine_depth,
                                        time_limit=engine_time, verbose=True)

            if move is None:
                print(colorize("  engine has no moves?!", Colors.BAD))
                game_over = True
                break

            san = move_to_san(board, move)
            moves_san.append(san)
            board.make_move(move)
            board.hash_key = compute_hash(board)
            last_move = move

            print(colorize(f"  engine plays: {san}", Colors.HEADER))

    # show final position
    print_board(board, last_move, flipped=(player_color == BLACK))

    # offer to save the game
    if moves_san:
        try:
            save_choice = input(colorize("  save game as PGN? (y/n): ", Colors.INFO)).strip()
            if save_choice.lower() == 'y':
                fname = input(colorize("  filename (default: game.pgn): ", Colors.INFO)).strip()
                if not fname:
                    fname = "game.pgn"
                if not fname.endswith('.pgn'):
                    fname += '.pgn'

                headers = {
                    'White': 'Human' if player_color == WHITE else 'Engine',
                    'Black': 'Engine' if player_color == WHITE else 'Human',
                }
                save_pgn(fname, moves_san, headers=headers, result=result)
                print(colorize(f"  saved to {fname}", Colors.GOOD))
        except (EOFError, KeyboardInterrupt):
            pass


def engine_vs_engine(depth=4, time_limit=3.0, max_moves=200):
    """watch two engine instances play each other"""
    board = setup_start_position()
    board.hash_key = compute_hash(board)

    moves_san = []
    last_move = None
    result = "*"

    for move_num in range(max_moves):
        print_board(board, last_move)
        print_game_info(board)
        print_eval(board)
        print()

        legal = generate_legal_moves(board)

        if len(legal) == 0:
            if is_in_check(board, board.side):
                result = "0-1" if board.side == WHITE else "1-0"
            else:
                result = "1/2-1/2"
            break

        if board.halfmove >= 100:
            result = "1/2-1/2"
            break

        if board.is_repetition():
            result = "1/2-1/2"
            break

        side_name = "White" if board.side == WHITE else "Black"
        print(colorize(f"  {side_name} thinking...", Colors.INFO))

        move, score = find_best_move(board, depth=depth,
                                    time_limit=time_limit, verbose=True)

        if move is None:
            break

        san = move_to_san(board, move)
        moves_san.append(san)
        board.make_move(move)
        board.hash_key = compute_hash(board)
        last_move = move

        print(colorize(f"  {side_name} plays: {san}", Colors.HEADER))

        # small delay so you can actually watch
        time.sleep(0.5)

    print_board(board, last_move)
    print_result(result)

    # save automatically
    if moves_san:
        headers = {'White': 'Engine (white)', 'Black': 'Engine (black)'}
        save_pgn("engine_game.pgn", moves_san, headers=headers, result=result)
        print(colorize("  saved to engine_game.pgn", Colors.GOOD))


def analyze_position():
    """analyze a FEN position"""
    print()
    default_fen = STARTING_FEN
    try:
        fen = input(colorize("  enter FEN (or press enter for start pos): ", Colors.INFO)).strip()
    except (EOFError, KeyboardInterrupt):
        return

    if not fen:
        fen = default_fen

    try:
        board = parse_fen(fen)
    except ValueError as e:
        print(colorize(f"  bad FEN: {e}", Colors.BAD))
        return

    board.hash_key = compute_hash(board)

    print_board(board)
    print_game_info(board)
    print_eval(board)
    print_material(board)
    print()

    try:
        depth_str = input(colorize("  search depth (default 6): ", Colors.INFO)).strip()
        depth = int(depth_str) if depth_str else 6
    except (ValueError, EOFError, KeyboardInterrupt):
        depth = 6

    print(colorize("  analyzing...", Colors.INFO))
    print()

    move, score = find_best_move(board, depth=depth, time_limit=30.0, verbose=True)

    print()
    if move:
        san = move_to_san(board, move)
        sc = score / 100.0
        print(colorize(f"  best move: {san}", Colors.GOOD + Colors.BOLD))
        print(colorize(f"  evaluation: {sc:+.2f}", Colors.INFO))

        if abs(score) >= MATE_THRESHOLD:
            if score > 0:
                mate_in = (100000 - abs(score) + 1) // 2
                print(colorize(f"  forced mate in {mate_in}!", Colors.GOOD))
            else:
                mate_in = (100000 - abs(score) + 1) // 2
                print(colorize(f"  getting mated in {mate_in}!", Colors.BAD))
    else:
        print(colorize("  no legal moves!", Colors.WARN))

    # show top moves
    print()
    print(colorize("  FEN: " + to_fen(board), Colors.DIM))


def load_pgn_game():
    """load and replay a PGN file"""
    try:
        fname = input(colorize("  PGN filename: ", Colors.INFO)).strip()
    except (EOFError, KeyboardInterrupt):
        return

    if not fname:
        print(colorize("  no filename given.", Colors.WARN))
        return

    try:
        headers, moves, result = load_pgn(fname)
    except FileNotFoundError:
        print(colorize(f"  file not found: {fname}", Colors.BAD))
        return
    except Exception as e:
        print(colorize(f"  error reading PGN: {e}", Colors.BAD))
        return

    # print headers
    print()
    for key, val in headers.items():
        print(colorize(f"  {key}: {val}", Colors.INFO))
    print()

    # replay the game
    board = setup_start_position()
    board.hash_key = compute_hash(board)
    last_move = None

    for san in moves:
        move = san_to_move(board, san)
        if move is None:
            print(colorize(f"  couldn't parse move: {san}", Colors.BAD))
            break

        board.make_move(move)
        board.hash_key = compute_hash(board)
        last_move = move

    print_board(board, last_move)
    print_game_info(board)
    print_eval(board)
    print()
    print(colorize(f"  result: {result}", Colors.HEADER))
    print(colorize(f"  FEN: {to_fen(board)}", Colors.DIM))


def run_perft():
    """run perft tests to verify move generation"""
    print()
    try:
        fen = input(colorize("  FEN (enter for start pos): ", Colors.INFO)).strip()
        if not fen:
            fen = STARTING_FEN

        depth_str = input(colorize("  depth (default 4): ", Colors.INFO)).strip()
        depth = int(depth_str) if depth_str else 4
    except (ValueError, EOFError, KeyboardInterrupt):
        return

    try:
        board = parse_fen(fen)
    except ValueError as e:
        print(colorize(f"  bad FEN: {e}", Colors.BAD))
        return

    print()
    print(colorize(f"  running perft to depth {depth}...", Colors.INFO))
    print()

    for d in range(1, depth + 1):
        start = time.time()
        nodes = perft(board, d)
        elapsed = time.time() - start
        nps = int(nodes / elapsed) if elapsed > 0.001 else 0
        print(f"  depth {d}: {nodes:>12,} nodes  ({elapsed:.2f}s, {nps:,} nps)")

    print()


def main():
    """main entry point"""
    # clear transposition table at start
    tt.clear()

    print_header()

    while True:
        print_menu()
        choice = get_menu_choice()

        if choice == 1:
            play_game(WHITE)
        elif choice == 2:
            play_game(BLACK)
        elif choice == 3:
            engine_vs_engine()
        elif choice == 4:
            analyze_position()
        elif choice == 5:
            load_pgn_game()
        elif choice == 6:
            run_perft()
        elif choice == 7:
            print(colorize("  bye!", Colors.INFO))
            break

        print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n  interrupted. bye!")
        sys.exit(0)
