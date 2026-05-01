"""
test_positions.py - engine testing

run known test positions to verify:
1. move generation (perft counts)
2. tactical ability (mate in N, win material)
3. positional understanding

usage: python -m tests.test_positions
"""

import time
import sys
import os

# add parent dir to path so imports work when run as module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.bitboard import WHITE, BLACK, SQUARE_NAMES
from engine.move_gen import generate_legal_moves, is_in_check, perft
from engine.search import find_best_move, tt, MATE_THRESHOLD
from engine.zobrist import compute_hash
from formats.fen import parse_fen, STARTING_FEN
from formats.pgn import move_to_san


# --- perft test positions ---
# these are well-known positions with verified node counts
# source: https://www.chessprogramming.org/Perft_Results

PERFT_TESTS = [
    {
        'name': 'Starting position',
        'fen': STARTING_FEN,
        'results': {
            1: 20,
            2: 400,
            3: 8902,
            4: 197281,
            # 5: 4865609,  # takes too long in python
        }
    },
    {
        'name': 'Kiwipete',
        'fen': 'r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1',
        'results': {
            1: 48,
            2: 2039,
            3: 97862,
            # 4: 4085603,
        }
    },
    {
        'name': 'Position 3',
        'fen': '8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1',
        'results': {
            1: 14,
            2: 191,
            3: 2812,
            4: 43238,
        }
    },
    {
        'name': 'Position 4',
        'fen': 'r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1',
        'results': {
            1: 6,
            2: 264,
            3: 9467,
            # 4: 422333,
        }
    },
    {
        'name': 'Position 5',
        'fen': 'rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8',
        'results': {
            1: 44,
            2: 1486,
            3: 62379,
        }
    },
]


# --- tactical test positions ---
# the engine should find specific moves

TACTICAL_TESTS = [
    {
        'name': 'Mate in 1 (back rank)',
        'fen': '6k1/5ppp/8/8/8/8/8/R3K3 w Q - 0 1',
        'best_move': 'a1a8',  # Ra8#
        'description': 'simple back rank mate',
    },
    {
        'name': 'Mate in 1 (queen)',
        'fen': 'k7/8/1K6/8/8/8/8/1Q6 w - - 0 1',
        'best_move': 'b1a2',  # Qa2# (or other mate)
        'description': 'queen delivers checkmate',
        'check_mate': True,  # just check that engine finds any mate
    },
    {
        'name': 'Win the queen',
        'fen': 'r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4',
        'best_move': 'h5f7',  # Qxf7# (scholars mate)
        'description': 'scholars mate',
    },
    {
        'name': 'Knight fork',
        'fen': 'r1bqkb1r/pppppppp/5n2/8/3nP3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1',
        'best_move': 'd4c2',  # Nc2+ forking king and rook
        'description': 'knight fork wins the rook',
    },
    {
        'name': 'Avoid stalemate',
        'fen': '7k/8/6K1/8/8/8/8/1Q6 w - - 0 1',
        'description': 'should NOT stalemate (find a check or non-stalemate move)',
        'avoid_draw': True,
    },
]


def run_perft_tests(max_depth=None):
    """run perft tests and report pass/fail"""
    print("\n=== PERFT TESTS ===\n")

    total = 0
    passed = 0

    for test in PERFT_TESTS:
        print(f"  {test['name']}")
        print(f"  FEN: {test['fen']}")

        board = parse_fen(test['fen'])

        for depth, expected in sorted(test['results'].items()):
            if max_depth and depth > max_depth:
                continue

            total += 1
            start = time.time()
            result = perft(board, depth)
            elapsed = time.time() - start

            status = "PASS" if result == expected else "FAIL"
            if result == expected:
                passed += 1

            print(f"    depth {depth}: {result:>10,} "
                  f"(expected {expected:>10,}) "
                  f"[{status}] ({elapsed:.2f}s)")

        print()

    print(f"  Results: {passed}/{total} passed\n")
    return passed == total


def run_tactical_tests(depth=5, time_limit=10.0):
    """run tactical test positions"""
    print("\n=== TACTICAL TESTS ===\n")

    total = 0
    passed = 0

    for test in TACTICAL_TESTS:
        total += 1
        print(f"  {test['name']}")
        print(f"  {test.get('description', '')}")
        print(f"  FEN: {test['fen']}")

        board = parse_fen(test['fen'])
        board.hash_key = compute_hash(board)
        tt.clear()

        move, score = find_best_move(board, depth=depth,
                                    time_limit=time_limit, verbose=False)

        if move is None:
            print(f"    result: no move found [FAIL]")
            print()
            continue

        san = move_to_san(board, move)
        uci = move.uci()

        # check various conditions
        test_passed = False

        if test.get('check_mate'):
            # just verify engine finds a mating move
            if score >= MATE_THRESHOLD:
                test_passed = True
        elif test.get('avoid_draw'):
            # verify score is not 0 (draw)
            if score != 0 and abs(score) > 50:
                test_passed = True
        elif 'best_move' in test:
            if uci == test['best_move']:
                test_passed = True

        if test_passed:
            passed += 1

        status = "PASS" if test_passed else "FAIL"
        sc = score / 100.0
        print(f"    found: {san} ({uci}) score: {sc:+.2f} [{status}]")

        if not test_passed and 'best_move' in test:
            print(f"    expected: {test['best_move']}")

        print()

    print(f"  Results: {passed}/{total} passed\n")
    return passed == total


def run_benchmark():
    """simple benchmark - nodes per second"""
    print("\n=== BENCHMARK ===\n")

    board = parse_fen(STARTING_FEN)
    board.hash_key = compute_hash(board)
    tt.clear()

    print("  searching starting position to depth 5...")
    start = time.time()
    move, score = find_best_move(board, depth=5, time_limit=60.0, verbose=True)
    elapsed = time.time() - start

    print(f"\n  time: {elapsed:.2f}s")
    if move:
        print(f"  best: {move.uci()} ({score / 100.0:+.2f})")

    # also test a midgame position
    print("\n  searching midgame position to depth 5...")
    mid_fen = "r1bq1rk1/ppp2ppp/2np1n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQ1RK1 w - - 0 6"
    board = parse_fen(mid_fen)
    board.hash_key = compute_hash(board)
    tt.clear()

    start = time.time()
    move, score = find_best_move(board, depth=5, time_limit=60.0, verbose=True)
    elapsed = time.time() - start

    print(f"\n  time: {elapsed:.2f}s")
    if move:
        print(f"  best: {move.uci()} ({score / 100.0:+.2f})")
    print()


def main():
    print("\n" + "=" * 50)
    print("  CHESS ENGINE TEST SUITE")
    print("=" * 50)

    all_passed = True

    # perft (limit to depth 3 for speed)
    if not run_perft_tests(max_depth=3):
        all_passed = False

    # tactics
    if not run_tactical_tests(depth=5, time_limit=10.0):
        all_passed = False

    # benchmark
    run_benchmark()

    print("=" * 50)
    if all_passed:
        print("  ALL TESTS PASSED!")
    else:
        print("  SOME TESTS FAILED - check output above")
    print("=" * 50)


if __name__ == '__main__':
    main()
