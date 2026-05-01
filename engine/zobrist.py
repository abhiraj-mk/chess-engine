"""
zobrist.py - zobrist hashing for transposition tables

basic idea: assign a random 64-bit number to every possible
(piece, color, square) combo. XOR them all together to get
a hash of the position. castling rights and en passant file
also get their own random numbers.

the beauty of XOR: making/unmaking a move just XORs the
changed pieces in/out. super fast.
"""

import random

from engine.bitboard import WHITE, BLACK, PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING


# we use a fixed seed so hashes are consistent across runs
_RNG = random.Random(42)

def _rand64():
    return _RNG.randint(0, (1 << 64) - 1)


# piece-square keys: PIECE_KEYS[color][piece_type][square]
PIECE_KEYS = [[[_rand64() for _ in range(64)] for _ in range(6)] for _ in range(2)]

# castling keys (16 possible states, but we just xor individual rights)
CASTLE_KEYS = [_rand64() for _ in range(16)]

# en passant file keys (a-h = 0-7, plus one for "no ep")
EP_KEYS = [_rand64() for _ in range(9)]  # index 8 = no en passant

# side to move
SIDE_KEY = _rand64()


def compute_hash(board):
    """
    compute zobrist hash from scratch.
    slow but correct - used for initialization and debugging.
    """
    from engine.bitboard import iter_bits

    h = 0

    # hash all pieces
    for color in (WHITE, BLACK):
        for pt in range(6):
            bb = board.pieces[color][pt]
            for sq in iter_bits(bb):
                h ^= PIECE_KEYS[color][pt][sq]

    # castling
    h ^= CASTLE_KEYS[board.castling]

    # en passant
    if board.ep_square >= 0:
        ep_file = board.ep_square & 7
        h ^= EP_KEYS[ep_file]
    else:
        h ^= EP_KEYS[8]

    # side
    if board.side == BLACK:
        h ^= SIDE_KEY

    return h


def update_hash_move(board, move, old_castling, old_ep):
    """
    incrementally update the hash after a move.
    this is faster than recomputing from scratch every time.
    """
    from engine.bitboard import file_of

    h = board.hash_key

    us = 1 - board.side  # side that just moved (board.side already flipped)
    them = board.side

    # flip side
    h ^= SIDE_KEY

    # remove piece from origin
    h ^= PIECE_KEYS[us][move.piece][move.from_sq]

    # add piece at destination (might be promoted)
    landing = move.promotion if move.promotion is not None else move.piece
    h ^= PIECE_KEYS[us][landing][move.to_sq]

    # handle capture
    if move.captured is not None:
        cap_sq = move.to_sq
        if move.is_ep:
            cap_sq = move.to_sq + (-8 if us == 0 else 8)
        h ^= PIECE_KEYS[them][move.captured][cap_sq]

    # castling rook
    if move.is_castle:
        from engine.bitboard import sq as make_sq
        if move.to_sq == make_sq(6, 0):
            h ^= PIECE_KEYS[WHITE][ROOK][make_sq(7, 0)]
            h ^= PIECE_KEYS[WHITE][ROOK][make_sq(5, 0)]
        elif move.to_sq == make_sq(2, 0):
            h ^= PIECE_KEYS[WHITE][ROOK][make_sq(0, 0)]
            h ^= PIECE_KEYS[WHITE][ROOK][make_sq(3, 0)]
        elif move.to_sq == make_sq(6, 7):
            h ^= PIECE_KEYS[BLACK][ROOK][make_sq(7, 7)]
            h ^= PIECE_KEYS[BLACK][ROOK][make_sq(5, 7)]
        elif move.to_sq == make_sq(2, 7):
            h ^= PIECE_KEYS[BLACK][ROOK][make_sq(0, 7)]
            h ^= PIECE_KEYS[BLACK][ROOK][make_sq(3, 7)]

    # update castling hash
    h ^= CASTLE_KEYS[old_castling]
    h ^= CASTLE_KEYS[board.castling]

    # update en passant hash
    if old_ep >= 0:
        h ^= EP_KEYS[file_of(old_ep)]
    else:
        h ^= EP_KEYS[8]

    if board.ep_square >= 0:
        h ^= EP_KEYS[file_of(board.ep_square)]
    else:
        h ^= EP_KEYS[8]

    return h


# --- transposition table ---

# entry types
TT_EXACT = 0
TT_ALPHA = 1   # upper bound (failed low)
TT_BETA = 2    # lower bound (failed high)


class TTEntry:
    """one entry in the transposition table"""
    __slots__ = ['hash_key', 'depth', 'score', 'flag', 'best_move']

    def __init__(self, hash_key, depth, score, flag, best_move=None):
        self.hash_key = hash_key
        self.depth = depth
        self.score = score
        self.flag = flag
        self.best_move = best_move


class TranspositionTable:
    """
    simple hash table for storing searched positions.
    uses a dict with size limit - not the fastest but
    good enough for a python engine.
    """

    def __init__(self, max_size=1_000_000):
        self.table = {}
        self.max_size = max_size
        self.hits = 0
        self.misses = 0

    def probe(self, hash_key):
        """look up a position. returns TTEntry or None"""
        entry = self.table.get(hash_key)
        if entry is not None:
            self.hits += 1
        else:
            self.misses += 1
        return entry

    def store(self, hash_key, depth, score, flag, best_move=None):
        """store a position. replace if deeper or same depth"""
        existing = self.table.get(hash_key)
        if existing is not None and existing.depth > depth:
            return  # don't overwrite deeper searches

        # crude size management - just clear half when full
        if len(self.table) >= self.max_size:
            keys = list(self.table.keys())
            for k in keys[:len(keys) // 2]:
                del self.table[k]

        self.table[hash_key] = TTEntry(hash_key, depth, score, flag, best_move)

    def clear(self):
        self.table.clear()
        self.hits = 0
        self.misses = 0
