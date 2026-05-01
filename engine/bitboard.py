"""
bitboard.py - core board representation using 64-bit integers

each square maps to a bit:
  a1=0, b1=1, ... h1=7
  a2=8, b2=9, ... h2=15
  ...
  a8=56, b8=57, ... h8=63

this is the standard mapping used by most engines.
we keep 12 bitboards (one per piece-type per color).
"""


# piece type constants
PAWN = 0
KNIGHT = 1
BISHOP = 2
ROOK = 3
QUEEN = 4
KING = 5

PIECE_NAMES = ['pawn', 'knight', 'bishop', 'rook', 'queen', 'king']
PIECE_CHARS = {
    (0, PAWN): 'P', (0, KNIGHT): 'N', (0, BISHOP): 'B',
    (0, ROOK): 'R', (0, QUEEN): 'Q', (0, KING): 'K',
    (1, PAWN): 'p', (1, KNIGHT): 'n', (1, BISHOP): 'b',
    (1, ROOK): 'r', (1, QUEEN): 'q', (1, KING): 'k',
}
CHAR_TO_PIECE = {v: k for k, v in PIECE_CHARS.items()}

# side constants
WHITE = 0
BLACK = 1

# square name lookup - handy for debugging
SQUARE_NAMES = []
for _r in range(8):
    for _f in range(8):
        SQUARE_NAMES.append(chr(ord('a') + _f) + str(_r + 1))


def sq(file, rank):
    """file and rank (0-7 each) -> square index"""
    return rank * 8 + file


def file_of(square):
    return square & 7


def rank_of(square):
    return square >> 3


def sq_from_name(name):
    """parse algebraic like 'e4' into square index"""
    f = ord(name[0]) - ord('a')
    r = int(name[1]) - 1
    return sq(f, r)


# --- bitmask constants ---
FILE_A = 0x0101010101010101
FILE_B = FILE_A << 1
FILE_C = FILE_A << 2
FILE_D = FILE_A << 3
FILE_E = FILE_A << 4
FILE_F = FILE_A << 5
FILE_G = FILE_A << 6
FILE_H = FILE_A << 7

RANK_1 = 0xFF
RANK_2 = RANK_1 << 8
RANK_3 = RANK_1 << 16
RANK_4 = RANK_1 << 24
RANK_5 = RANK_1 << 32
RANK_6 = RANK_1 << 40
RANK_7 = RANK_1 << 48
RANK_8 = RANK_1 << 56

FILES = [FILE_A, FILE_B, FILE_C, FILE_D, FILE_E, FILE_F, FILE_G, FILE_H]
RANKS = [RANK_1, RANK_2, RANK_3, RANK_4, RANK_5, RANK_6, RANK_7, RANK_8]

NOT_FILE_A = ~FILE_A & 0xFFFFFFFFFFFFFFFF
NOT_FILE_H = ~FILE_H & 0xFFFFFFFFFFFFFFFF
NOT_FILE_AB = ~(FILE_A | FILE_B) & 0xFFFFFFFFFFFFFFFF
NOT_FILE_GH = ~(FILE_G | FILE_H) & 0xFFFFFFFFFFFFFFFF

FULL_BOARD = (1 << 64) - 1


# --- bit manipulation helpers ---

def bit(s):
    """single bit set at square s"""
    return 1 << s


def lsb(bb):
    """index of least significant set bit, -1 if empty"""
    if bb == 0:
        return -1
    return (bb & -bb).bit_length() - 1


def pop_lsb(bb):
    """returns (bit_index, remaining_bb)"""
    s = lsb(bb)
    return s, bb & (bb - 1)


def popcount(bb):
    """number of set bits"""
    cnt = 0
    while bb:
        bb &= bb - 1
        cnt += 1
    return cnt


def iter_bits(bb):
    """yield each set bit index one by one"""
    while bb:
        s = lsb(bb)
        yield s
        bb &= bb - 1


# --- castling flags ---
CASTLE_WK = 1   # white O-O
CASTLE_WQ = 2   # white O-O-O
CASTLE_BK = 4   # black O-O
CASTLE_BQ = 8   # black O-O-O


class Move:
    """
    represents a single chess move.
    kept simple on purpose - no bitpacking, just store the fields.
    """

    __slots__ = ['from_sq', 'to_sq', 'piece', 'captured', 'promotion',
                 'is_castle', 'is_ep', 'is_double_push']

    def __init__(self, from_sq, to_sq, piece, captured=None, promotion=None,
                 is_castle=False, is_ep=False, is_double_push=False):
        self.from_sq = from_sq
        self.to_sq = to_sq
        self.piece = piece
        self.captured = captured
        self.promotion = promotion
        self.is_castle = is_castle
        self.is_ep = is_ep
        self.is_double_push = is_double_push

    def uci(self):
        """UCI notation, e.g. 'e2e4', 'e7e8q'"""
        s = SQUARE_NAMES[self.from_sq] + SQUARE_NAMES[self.to_sq]
        if self.promotion is not None:
            promo_map = {KNIGHT: 'n', BISHOP: 'b', ROOK: 'r', QUEEN: 'q'}
            s += promo_map[self.promotion]
        return s

    def __repr__(self):
        return f"Move({self.uci()})"

    def __eq__(self, other):
        if not isinstance(other, Move):
            return False
        return (self.from_sq == other.from_sq and
                self.to_sq == other.to_sq and
                self.promotion == other.promotion)

    def __hash__(self):
        return hash((self.from_sq, self.to_sq, self.promotion))


class UndoInfo:
    """everything we need to undo a move"""
    __slots__ = ['castling', 'ep_square', 'halfmove', 'captured_piece',
                 'captured_sq', 'hash_key']

    def __init__(self):
        self.castling = 0
        self.ep_square = -1
        self.halfmove = 0
        self.captured_piece = None
        self.captured_sq = -1
        self.hash_key = 0


class Board:
    """
    the main board state.
    pieces[color][piece_type] = bitboard for those pieces.
    """

    def __init__(self):
        # 2x6 array of bitboards
        self.pieces = [[0] * 6, [0] * 6]

        self.side = WHITE
        self.castling = CASTLE_WK | CASTLE_WQ | CASTLE_BK | CASTLE_BQ
        self.ep_square = -1

        self.halfmove = 0
        self.fullmove = 1

        # for undo
        self.history = []

        # move list for pgn export
        self.move_history = []

        # zobrist hash - gets set after zobrist module loads
        self.hash_key = 0

    def occupancy(self, color):
        """combined bitboard for all pieces of one side"""
        occ = 0
        for pt in range(6):
            occ |= self.pieces[color][pt]
        return occ

    def all_occupancy(self):
        return self.occupancy(WHITE) | self.occupancy(BLACK)

    def piece_at(self, square):
        """returns (color, piece_type) or None if empty"""
        b = bit(square)
        for color in (WHITE, BLACK):
            for pt in range(6):
                if self.pieces[color][pt] & b:
                    return (color, pt)
        return None

    def king_sq(self, color):
        """find the king square for given color"""
        bb = self.pieces[color][KING]
        if bb == 0:
            return -1  # shouldn't happen in normal game
        return lsb(bb)

    def put_piece(self, color, piece_type, square):
        self.pieces[color][piece_type] |= bit(square)

    def remove_piece(self, color, piece_type, square):
        self.pieces[color][piece_type] &= ~bit(square)

    def make_move(self, move):
        """
        apply move, push undo info onto stack.
        doesn't check legality - caller should do that.
        """
        undo = UndoInfo()
        undo.castling = self.castling
        undo.ep_square = self.ep_square
        undo.halfmove = self.halfmove
        undo.hash_key = self.hash_key

        us = self.side
        them = 1 - us

        # handle captures
        if move.captured is not None:
            cap_sq = move.to_sq
            if move.is_ep:
                # en passant pawn is behind the landing square
                cap_sq = move.to_sq + (-8 if us == WHITE else 8)
            undo.captured_piece = move.captured
            undo.captured_sq = cap_sq
            self.remove_piece(them, move.captured, cap_sq)

        # remove piece from origin, place at destination
        self.remove_piece(us, move.piece, move.from_sq)
        landing = move.promotion if move.promotion is not None else move.piece
        self.put_piece(us, landing, move.to_sq)

        # castling: gotta move the rook too
        if move.is_castle:
            if move.to_sq == sq(6, 0):     # white O-O
                self.remove_piece(WHITE, ROOK, sq(7, 0))
                self.put_piece(WHITE, ROOK, sq(5, 0))
            elif move.to_sq == sq(2, 0):   # white O-O-O
                self.remove_piece(WHITE, ROOK, sq(0, 0))
                self.put_piece(WHITE, ROOK, sq(3, 0))
            elif move.to_sq == sq(6, 7):   # black O-O
                self.remove_piece(BLACK, ROOK, sq(7, 7))
                self.put_piece(BLACK, ROOK, sq(5, 7))
            elif move.to_sq == sq(2, 7):   # black O-O-O
                self.remove_piece(BLACK, ROOK, sq(0, 7))
                self.put_piece(BLACK, ROOK, sq(3, 7))

        # update castling rights
        if move.piece == KING:
            if us == WHITE:
                self.castling &= ~(CASTLE_WK | CASTLE_WQ)
            else:
                self.castling &= ~(CASTLE_BK | CASTLE_BQ)

        # rook moved or captured? remove that castling right
        if move.from_sq == sq(0, 0) or move.to_sq == sq(0, 0):
            self.castling &= ~CASTLE_WQ
        if move.from_sq == sq(7, 0) or move.to_sq == sq(7, 0):
            self.castling &= ~CASTLE_WK
        if move.from_sq == sq(0, 7) or move.to_sq == sq(0, 7):
            self.castling &= ~CASTLE_BQ
        if move.from_sq == sq(7, 7) or move.to_sq == sq(7, 7):
            self.castling &= ~CASTLE_BK

        # en passant square
        if move.is_double_push:
            self.ep_square = (move.from_sq + move.to_sq) // 2
        else:
            self.ep_square = -1

        # clocks
        if move.piece == PAWN or move.captured is not None:
            self.halfmove = 0
        else:
            self.halfmove += 1

        if us == BLACK:
            self.fullmove += 1

        self.side = them
        self.history.append(undo)
        self.move_history.append(move)

    def unmake_move(self):
        """pop the last move off the stack and restore state"""
        if not self.history:
            return

        move = self.move_history.pop()
        undo = self.history.pop()

        them = self.side
        us = 1 - them
        self.side = us

        # undo the piece movement
        landing = move.promotion if move.promotion is not None else move.piece
        self.remove_piece(us, landing, move.to_sq)
        self.put_piece(us, move.piece, move.from_sq)

        # put captured piece back
        if undo.captured_piece is not None:
            self.put_piece(them, undo.captured_piece, undo.captured_sq)

        # undo castling rook
        if move.is_castle:
            if move.to_sq == sq(6, 0):
                self.remove_piece(WHITE, ROOK, sq(5, 0))
                self.put_piece(WHITE, ROOK, sq(7, 0))
            elif move.to_sq == sq(2, 0):
                self.remove_piece(WHITE, ROOK, sq(3, 0))
                self.put_piece(WHITE, ROOK, sq(0, 0))
            elif move.to_sq == sq(6, 7):
                self.remove_piece(BLACK, ROOK, sq(5, 7))
                self.put_piece(BLACK, ROOK, sq(7, 7))
            elif move.to_sq == sq(2, 7):
                self.remove_piece(BLACK, ROOK, sq(3, 7))
                self.put_piece(BLACK, ROOK, sq(0, 7))

        self.castling = undo.castling
        self.ep_square = undo.ep_square
        self.halfmove = undo.halfmove
        self.hash_key = undo.hash_key

        if us == BLACK:
            self.fullmove -= 1

    def is_repetition(self):
        """check if current position has occurred before (simplified)"""
        if len(self.history) < 4:
            return False
        current = self.hash_key
        count = 0
        for undo in self.history:
            if undo.hash_key == current:
                count += 1
                if count >= 2:
                    return True
        return False
