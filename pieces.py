"""Chess primitives and the piece-class hierarchy.

This module is the foundation of the engine. It defines:

* :class:`Color`            -- the two sides.
* square helpers            -- a square is a plain integer ``0..63`` (a1 = 0,
                               h8 = 63). Helper functions convert to and from
                               file/rank and algebraic names.
* :class:`Move`             -- an immutable value object describing one move.
* :class:`Piece`            -- the abstract base class, plus the six concrete
                               subclasses ``Pawn, Knight, Bishop, Rook, Queen,
                               King``.

Design note -- why squares are integers and not a ``Square`` class.
Our first draft used a ``Square`` value object (file, rank). We switched to a
single integer index because move generation and ``is_attacked`` are called
hundreds of thousands of times in perft and in the search, and allocating a
small object per square dominated the run time. Integers keep the board a flat
list and make the hot path allocation-free. The OOP that the project is really
about -- the *piece* hierarchy and the *player* strategy -- is untouched by this
choice.

Design note -- why a piece does not store its own square.
A piece object only knows its colour. The :class:`~board.Board` is the single
source of truth for *where* pieces are. ``pseudo_legal_moves`` therefore takes
the square the piece sits on as an argument. Storing the square inside the piece
as well would mean keeping two copies of the same fact in sync across every
``make_move`` / ``unmake_move`` -- a classic source of bugs that this split
avoids.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


# --------------------------------------------------------------------------- #
# Colours
# --------------------------------------------------------------------------- #
class Color(Enum):
    """The side a piece belongs to."""

    WHITE = "w"
    BLACK = "b"

    @property
    def other(self) -> "Color":
        """The opposing colour."""
        return Color.BLACK if self is Color.WHITE else Color.WHITE


WHITE = Color.WHITE
BLACK = Color.BLACK


# --------------------------------------------------------------------------- #
# Squares (a square is just an int 0..63; a1 = 0, b1 = 1, ..., h8 = 63)
# --------------------------------------------------------------------------- #
def make_square(file: int, rank: int) -> int:
    """Build a square index from a 0-based *file* (a..h) and *rank* (1..8)."""
    return rank * 8 + file


def file_of(square: int) -> int:
    """0-based file (a = 0 ... h = 7)."""
    return square & 7


def rank_of(square: int) -> int:
    """0-based rank (rank 1 = 0 ... rank 8 = 7)."""
    return square >> 3


def square_name(square: int) -> str:
    """Algebraic name of a square, e.g. ``e4``."""
    return "abcdefgh"[file_of(square)] + str(rank_of(square) + 1)


def parse_square(name: str) -> int:
    """Parse an algebraic square name such as ``e4`` into an index."""
    name = name.strip().lower()
    if len(name) != 2 or name[0] not in "abcdefgh" or name[1] not in "12345678":
        raise ValueError(f"invalid square: {name!r}")
    return make_square(ord(name[0]) - ord("a"), int(name[1]) - 1)


# Frequently used squares, named for readability (mainly for castling).
A1, B1, C1, D1, E1, F1, G1, H1 = range(0, 8)
A8, B8, C8, D8, E8, F8, G8, H8 = range(56, 64)


# --------------------------------------------------------------------------- #
# Direction tables (file delta, rank delta)
# --------------------------------------------------------------------------- #
KNIGHT_DELTAS = [(1, 2), (2, 1), (2, -1), (1, -2),
                 (-1, -2), (-2, -1), (-2, 1), (-1, 2)]
KING_DELTAS = [(-1, -1), (-1, 0), (-1, 1), (0, -1),
               (0, 1), (1, -1), (1, 0), (1, 1)]
BISHOP_DIRS = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
ROOK_DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1)]
QUEEN_DIRS = BISHOP_DIRS + ROOK_DIRS


# --------------------------------------------------------------------------- #
# Moves
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Move:
    """An immutable description of a single move.

    Only the *intent* of the move is stored here (origin, destination and the
    special-move flags). Everything needed to *undo* a move -- the captured
    piece and the previous game state -- lives in :class:`board.Undo`, so that
    a ``Move`` stays a pure value: hashable, comparable, safe to keep in a move
    list, and independent of the board it is played on.
    """

    from_sq: int
    to_sq: int
    promotion: Optional[str] = None      # 'Q', 'R', 'B' or 'N'
    is_en_passant: bool = False
    is_castle: bool = False

    def uci(self) -> str:
        """Long-algebraic / UCI string, e.g. ``e2e4`` or ``e7e8q``."""
        text = square_name(self.from_sq) + square_name(self.to_sq)
        if self.promotion:
            text += self.promotion.lower()
        return text

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.uci()


# --------------------------------------------------------------------------- #
# Pieces
# --------------------------------------------------------------------------- #
class Piece(ABC):
    """Abstract base class for all chess pieces.

    Subclasses declare two class attributes -- ``LETTER`` (its FEN letter,
    upper-case) and ``VALUE`` (material value used by the engine) -- and
    implement :meth:`pseudo_legal_moves`.
    """

    LETTER: str = "?"
    VALUE: int = 0

    def __init__(self, color: Color) -> None:
        self.color = color

    def symbol(self) -> str:
        """FEN/ASCII symbol: upper-case for White, lower-case for Black."""
        return self.LETTER.upper() if self.color is WHITE else self.LETTER.lower()

    @abstractmethod
    def pseudo_legal_moves(self, board, frm: int) -> List[Move]:
        """Moves that respect this piece's geometry, *ignoring* king safety.

        Pseudo-legal means: correct movement pattern, captures of enemy pieces
        only, special moves where applicable -- but the move may still leave
        the mover's own king in check. The legality filter in
        :meth:`board.Board.legal_moves` removes those.
        """
        raise NotImplementedError

    # -- shared move-generation helpers ------------------------------------- #
    def _slide(self, board, frm: int, directions) -> List[Move]:
        """Generate moves for a sliding piece along *directions* until blocked."""
        squares = board.squares
        f0, r0 = file_of(frm), rank_of(frm)
        moves: List[Move] = []
        for df, dr in directions:
            f, r = f0 + df, r0 + dr
            while 0 <= f < 8 and 0 <= r < 8:
                to = r * 8 + f
                target = squares[to]
                if target is None:
                    moves.append(Move(frm, to))
                else:
                    if target.color is not self.color:
                        moves.append(Move(frm, to))
                    break
                f += df
                r += dr
        return moves

    def _step(self, board, frm: int, deltas) -> List[Move]:
        """Generate single-step moves (knight, king) from a delta table."""
        squares = board.squares
        f0, r0 = file_of(frm), rank_of(frm)
        moves: List[Move] = []
        for df, dr in deltas:
            f, r = f0 + df, r0 + dr
            if 0 <= f < 8 and 0 <= r < 8:
                to = r * 8 + f
                target = squares[to]
                if target is None or target.color is not self.color:
                    moves.append(Move(frm, to))
        return moves

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{type(self).__name__}({self.color.name})"


class Pawn(Piece):
    LETTER = "P"
    VALUE = 1

    def pseudo_legal_moves(self, board, frm: int) -> List[Move]:
        squares = board.squares
        f, r = file_of(frm), rank_of(frm)
        moves: List[Move] = []

        if self.color is WHITE:
            forward, start_rank, last_rank, cap_rank = 8, 1, 7, r + 1
        else:
            forward, start_rank, last_rank, cap_rank = -8, 6, 0, r - 1

        # Single (and double) forward push -- never a capture.
        one = frm + forward
        if 0 <= one < 64 and squares[one] is None:
            if rank_of(one) == last_rank:
                moves += [Move(frm, one, promotion=p) for p in "QRBN"]
            else:
                moves.append(Move(frm, one))
                if r == start_rank:
                    two = frm + 2 * forward
                    if squares[two] is None:
                        moves.append(Move(frm, two))

        # Diagonal captures, including en passant and capture-promotions.
        for df in (-1, 1):
            cf = f + df
            if not (0 <= cf < 8 and 0 <= cap_rank < 8):
                continue
            to = cap_rank * 8 + cf
            target = squares[to]
            if target is not None and target.color is not self.color:
                if cap_rank == last_rank:
                    moves += [Move(frm, to, promotion=p) for p in "QRBN"]
                else:
                    moves.append(Move(frm, to))
            elif to == board.ep_square:
                moves.append(Move(frm, to, is_en_passant=True))

        return moves


class Knight(Piece):
    LETTER = "N"
    VALUE = 3

    def pseudo_legal_moves(self, board, frm: int) -> List[Move]:
        return self._step(board, frm, KNIGHT_DELTAS)


class Bishop(Piece):
    LETTER = "B"
    VALUE = 3

    def pseudo_legal_moves(self, board, frm: int) -> List[Move]:
        return self._slide(board, frm, BISHOP_DIRS)


class Rook(Piece):
    LETTER = "R"
    VALUE = 5

    def pseudo_legal_moves(self, board, frm: int) -> List[Move]:
        return self._slide(board, frm, ROOK_DIRS)


class Queen(Piece):
    LETTER = "Q"
    VALUE = 9

    def pseudo_legal_moves(self, board, frm: int) -> List[Move]:
        return self._slide(board, frm, QUEEN_DIRS)


class King(Piece):
    LETTER = "K"
    VALUE = 0  # the king is never "won"; mate ends the game instead

    def pseudo_legal_moves(self, board, frm: int) -> List[Move]:
        moves = self._step(board, frm, KING_DELTAS)
        moves += self._castling_moves(board, frm)
        return moves

    def _castling_moves(self, board, frm: int) -> List[Move]:
        """Fully-legal castling moves.

        Castling is the one move whose legality depends on squares *other* than
        the destination (the king may not start in, pass through, or land on an
        attacked square). Rather than bolt those conditions onto the generic
        legality filter, we check them here, where the rule lives.
        """
        from board import WK, WQ, BK, BQ  # local import avoids a cycle

        result: List[Move] = []
        color = self.color
        opp = color.other

        if color is WHITE:
            if frm != E1:
                return result
            # King-side: f1, g1 empty; rook on h1; king safe on e1, f1, g1.
            if (board.castling & WK
                    and board.squares[F1] is None and board.squares[G1] is None
                    and _is_rook(board.squares[H1], WHITE)
                    and not board.is_attacked(E1, opp)
                    and not board.is_attacked(F1, opp)
                    and not board.is_attacked(G1, opp)):
                result.append(Move(E1, G1, is_castle=True))
            # Queen-side: b1, c1, d1 empty; rook on a1; king safe on e1, d1, c1.
            if (board.castling & WQ
                    and board.squares[D1] is None and board.squares[C1] is None
                    and board.squares[B1] is None
                    and _is_rook(board.squares[A1], WHITE)
                    and not board.is_attacked(E1, opp)
                    and not board.is_attacked(D1, opp)
                    and not board.is_attacked(C1, opp)):
                result.append(Move(E1, C1, is_castle=True))
        else:
            if frm != E8:
                return result
            if (board.castling & BK
                    and board.squares[F8] is None and board.squares[G8] is None
                    and _is_rook(board.squares[H8], BLACK)
                    and not board.is_attacked(E8, opp)
                    and not board.is_attacked(F8, opp)
                    and not board.is_attacked(G8, opp)):
                result.append(Move(E8, G8, is_castle=True))
            if (board.castling & BQ
                    and board.squares[D8] is None and board.squares[C8] is None
                    and board.squares[B8] is None
                    and _is_rook(board.squares[A8], BLACK)
                    and not board.is_attacked(E8, opp)
                    and not board.is_attacked(D8, opp)
                    and not board.is_attacked(C8, opp)):
                result.append(Move(E8, C8, is_castle=True))
        return result


def _is_rook(piece: Optional[Piece], color: Color) -> bool:
    return isinstance(piece, Rook) and piece.color is color


# Map a promotion letter to the class that implements it.
PROMOTION_CLASSES = {"Q": Queen, "R": Rook, "B": Bishop, "N": Knight}

# Map a FEN letter (case-insensitive) to its piece class.
LETTER_TO_CLASS = {"P": Pawn, "N": Knight, "B": Bishop,
                   "R": Rook, "Q": Queen, "K": King}
