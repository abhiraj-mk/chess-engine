# Terminal Chess Engine

A chess engine built from scratch in Python. Uses bitboard representation for the board, alpha-beta search with iterative deepening for move selection, and a multi-factor evaluation function.

## Features

- **Bitboard representation** - each piece type stored as a 64-bit integer for fast bit manipulation
- **Full move generation** - all legal moves including castling, en passant, promotions, pins/checks
- **Alpha-beta search** with iterative deepening, quiescence search, null move pruning, and late move reductions
- **Transposition table** with Zobrist hashing for position caching
- **Evaluation function** covering material, piece-square tables, pawn structure, king safety, mobility, bishop pair, rooks on open files
- **Move ordering** - MVV-LVA for captures, killer moves, history heuristic
- **FEN support** - load/save any position
- **PGN support** - save and load complete games
- **Terminal UI** with Unicode pieces, colored board, eval display

## Setup

No dependencies needed - pure Python 3.6+. Just clone and run:

```bash
python main.py
```

## How to Play

Run `main.py` and pick from the menu:

1. **Play as White** - you play white, engine plays black
2. **Play as Black** - engine plays white, you play black  
3. **Engine vs Engine** - watch the engine play itself
4. **Analyze** - paste a FEN and the engine will find the best move
5. **Load PGN** - replay a saved game
6. **Perft** - test move generation correctness

### Move Input

You can enter moves in two formats:
- **UCI**: `e2e4`, `g1f3`, `e7e8q` (with promotion)
- **Algebraic**: `e4`, `Nf3`, `O-O`, `Qxd5`

Other commands during a game:
- `moves` - show all legal moves
- `hint` - ask the engine for a suggestion
- `undo` - take back the last move pair
- `fen` - show current FEN
- `quit` - exit the game

## Project Structure

```
chess-engine/
├── engine/
│   ├── bitboard.py    # board representation, move/undo, bit helpers
│   ├── move_gen.py    # pseudo-legal and legal move generation
│   ├── search.py      # alpha-beta, iterative deepening, quiescence
│   ├── eval.py        # position evaluation (material, PST, structure)
│   └── zobrist.py     # hashing and transposition table
├── ui/
│   └── terminal.py    # terminal display, input handling, colors
├── formats/
│   ├── fen.py         # FEN parsing and generation
│   └── pgn.py         # PGN save/load, SAN notation
├── tests/
│   └── test_positions.py  # perft tests, tactical puzzles, benchmarks
├── main.py            # entry point and game loop
└── README.md
```

## Running Tests

```bash
python -m tests.test_positions
```

This runs:
- **Perft tests** - verifies move generation produces correct node counts for known positions
- **Tactical tests** - checks if the engine finds mates, forks, and avoids stalemate
- **Benchmark** - measures search speed in nodes per second

## How It Works

### Bitboards

Instead of an 8x8 array, the board is represented using twelve 64-bit integers (one per piece type per color). Each bit corresponds to a square. This allows very fast move generation using bitwise operations.

```
bit 0  = a1    bit 7  = h1
bit 8  = a2    bit 15 = h2
...
bit 56 = a8    bit 63 = h8
```

### Search

The engine uses iterative deepening with alpha-beta pruning. It starts by searching 1 move deep, then 2, then 3, etc. Each iteration uses results from the previous one for better move ordering.

Key optimizations:
- **Quiescence search**: at leaf nodes, keep searching captures to avoid the "horizon effect"
- **Null move pruning**: skip a turn and see if the position is still winning (reduces search tree)
- **Late move reductions**: search later moves at reduced depth
- **Killer moves**: remember moves that caused beta cutoffs at each ply
- **History heuristic**: track which moves tend to be good globally

### Evaluation

The evaluation scores positions in centipawns (100 = 1 pawn advantage):

| Feature | Description |
|---------|-------------|
| Material | Piece values: P=100, N=320, B=330, R=500, Q=900 |
| Piece-square tables | Bonus/penalty based on piece position |
| Pawn structure | Doubled (-15), isolated (-10), passed (+10-70) |
| King safety | Pawn shield bonus in middlegame |
| Mobility | 3cp per available square |
| Bishop pair | +30cp for having both bishops |
| Rook on open file | +15cp open, +8cp semi-open |

## Limitations

- Python is slow for chess engines - expect depth 5-6 in reasonable time
- No opening book (plays from scratch every game)
- No endgame tablebases
- No pondering (doesn't think on opponent's time)

For serious engine development you'd want to use C/C++ or Rust, but this is a great learning project.

## Engine Strength

Roughly 1200-1500 Elo depending on time control. It will beat casual players but lose to serious club players and any modern engine. The main bottleneck is Python's speed - the same algorithm in C would be ~100x faster and much stronger.

## License

MIT - do whatever you want with it.
