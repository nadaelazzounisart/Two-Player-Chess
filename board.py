"""The board and the position state it owns.

A :class:`Board` holds everything a FEN string holds -- the piece placement
plus the side to move, castling rights, en-passant target, the half-move clock
and the full-move number -- because all of these change together when a move is
made and unmade. Keeping them in one place is what makes ``make_move`` /
``unmake_move`` reliable.

``make_move`` pushes an :class:`Undo` record onto an internal stack;
``unmake_move`` pops it and restores the previous state exactly. This
reversible design is used everywhere: the legality filter plays a move, asks
"is my king attacked?", and takes it back; the search does the same thing
recursively. Crucially, even the awkward en-passant "discovered check" case
needs no special handling -- because make/unmake removes the captured pawn from
its real square, the ordinary king-safety check sees the newly opened line.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Tuple

from pieces import (
    BISHOP_DIRS, KING_DELTAS, KNIGHT_DELTAS, ROOK_DIRS,
    Bishop, Color, King, Knight, LETTER_TO_CLASS, Move, Pawn,
    PROMOTION_CLASSES, Piece, Queen, Rook, WHITE, BLACK,
    file_of, make_square, parse_square, rank_of, square_name,
    A1, A8, H1, H8, E1, E8,
)

# Castling-right bit flags.
WK, WQ, BK, BQ = 1, 2, 4, 8

# castle_keep[sq] gives the rights to *keep* when a piece moves from or to sq.
# Moving the king clears both of that colour's rights; moving (or capturing) a
# rook on its home corner clears that one right.
_castle_keep = [WK | WQ | BK | BQ] * 64
_castle_keep[E1] &= ~(WK | WQ)
_castle_keep[H1] &= ~WK
_castle_keep[A1] &= ~WQ
_castle_keep[E8] &= ~(BK | BQ)
_castle_keep[H8] &= ~BK
_castle_keep[A8] &= ~BQ

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


@dataclass
class Undo:
    """Everything needed to reverse one :class:`Move`."""

    move: Move
    moved_piece: Piece
    captured: Optional[Piece]
    captured_sq: int
    prev_castling: int
    prev_ep: Optional[int]
    prev_halfmove: int
    prev_fullmove: int


class Board:
    """An 8x8 chess position."""

    def __init__(self) -> None:
        self.squares: List[Optional[Piece]] = [None] * 64
        self.side_to_move: Color = WHITE
        self.castling: int = 0
        self.ep_square: Optional[int] = None
        self.halfmove_clock: int = 0
        self.fullmove_number: int = 1
        self.king_square: Dict[Color, int] = {WHITE: E1, BLACK: E8}
        self._undo_stack: List[Undo] = []

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    @classmethod
    def starting_position(cls) -> "Board":
        return cls.from_fen(START_FEN)

    @classmethod
    def from_fen(cls, fen: str) -> "Board":
        """Build a board from a FEN string."""
        board = cls()
        parts = fen.split()
        if len(parts) < 4:
            raise ValueError("FEN needs at least 4 fields")
        placement, side, castling, ep = parts[0], parts[1], parts[2], parts[3]
        halfmove = parts[4] if len(parts) > 4 else "0"
        fullmove = parts[5] if len(parts) > 5 else "1"

        rank = 7
        file = 0
        for ch in placement:
            if ch == "/":
                rank -= 1
                file = 0
            elif ch.isdigit():
                file += int(ch)
            else:
                piece = LETTER_TO_CLASS[ch.upper()](WHITE if ch.isupper() else BLACK)
                sq = make_square(file, rank)
                board.squares[sq] = piece
                if isinstance(piece, King):
                    board.king_square[piece.color] = sq
                file += 1

        board.side_to_move = WHITE if side == "w" else BLACK
        board.castling = 0
        if "K" in castling:
            board.castling |= WK
        if "Q" in castling:
            board.castling |= WQ
        if "k" in castling:
            board.castling |= BK
        if "q" in castling:
            board.castling |= BQ
        board.ep_square = None if ep == "-" else parse_square(ep)
        board.halfmove_clock = int(halfmove)
        board.fullmove_number = int(fullmove)
        return board

    def to_fen(self) -> str:
        """Serialise the position to a FEN string."""
        rows = []
        for rank in range(7, -1, -1):
            row, empty = "", 0
            for file in range(8):
                piece = self.squares[make_square(file, rank)]
                if piece is None:
                    empty += 1
                else:
                    if empty:
                        row += str(empty)
                        empty = 0
                    row += piece.symbol()
            if empty:
                row += str(empty)
            rows.append(row)
        placement = "/".join(rows)

        side = "w" if self.side_to_move is WHITE else "b"
        rights = "".join(c for bit, c in
                         ((WK, "K"), (WQ, "Q"), (BK, "k"), (BQ, "q"))
                         if self.castling & bit) or "-"
        ep = square_name(self.ep_square) if self.ep_square is not None else "-"
        return f"{placement} {side} {rights} {ep} {self.halfmove_clock} {self.fullmove_number}"

    # ------------------------------------------------------------------ #
    # Simple queries
    # ------------------------------------------------------------------ #
    def piece_at(self, square: int) -> Optional[Piece]:
        return self.squares[square]

    def iter_pieces(self) -> Iterator[Tuple[int, Piece]]:
        """Yield ``(square, piece)`` for every occupied square."""
        for sq, piece in enumerate(self.squares):
            if piece is not None:
                yield sq, piece

    def position_key(self) -> Tuple[str, str, int, Optional[int]]:
        """Key used for threefold-repetition counting.

        Two positions repeat only if the placement, the side to move, the
        castling rights *and* the en-passant target all match -- otherwise the
        set of available moves differs and it is not the same position. (We key
        on the raw ep square, the common simplification; strictly, ep only
        counts when a capture is actually possible.)
        """
        placement = "".join(p.symbol() if p else "." for p in self.squares)
        return (placement, self.side_to_move.value, self.castling, self.ep_square)

    # ------------------------------------------------------------------ #
    # Attack detection
    # ------------------------------------------------------------------ #
    def is_attacked(self, square: int, by_color: Color) -> bool:
        """Is *square* attacked by any piece of *by_color* in this position?

        We look *outward* from the target square: knight jumps, king steps,
        pawn diagonals, then sliding rays. This is far cheaper than generating
        every enemy move, and it is the single most-called function in the
        engine.
        """
        squares = self.squares
        f0, r0 = file_of(square), rank_of(square)

        # Knights.
        for df, dr in KNIGHT_DELTAS:
            f, r = f0 + df, r0 + dr
            if 0 <= f < 8 and 0 <= r < 8:
                p = squares[r * 8 + f]
                if p is not None and p.color is by_color and isinstance(p, Knight):
                    return True

        # Enemy king.
        for df, dr in KING_DELTAS:
            f, r = f0 + df, r0 + dr
            if 0 <= f < 8 and 0 <= r < 8:
                p = squares[r * 8 + f]
                if p is not None and p.color is by_color and isinstance(p, King):
                    return True

        # Pawns. A pawn attacks diagonally "forward" for its colour, so an
        # attacking pawn sits one rank toward its own side of the target.
        pawn_rank = r0 - 1 if by_color is WHITE else r0 + 1
        if 0 <= pawn_rank < 8:
            for df in (-1, 1):
                f = f0 + df
                if 0 <= f < 8:
                    p = squares[pawn_rank * 8 + f]
                    if p is not None and p.color is by_color and isinstance(p, Pawn):
                        return True

        # Sliding pieces: diagonals (bishop/queen) and orthogonals (rook/queen).
        for dirs, sliders in ((BISHOP_DIRS, (Bishop, Queen)),
                              (ROOK_DIRS, (Rook, Queen))):
            for df, dr in dirs:
                f, r = f0 + df, r0 + dr
                while 0 <= f < 8 and 0 <= r < 8:
                    p = squares[r * 8 + f]
                    if p is not None:
                        if p.color is by_color and isinstance(p, sliders):
                            return True
                        break
                    f += df
                    r += dr

        return False

    def is_in_check(self, color: Color) -> bool:
        """Is *color*'s king currently attacked?"""
        return self.is_attacked(self.king_square[color], color.other)

    # ------------------------------------------------------------------ #
    # Move generation
    # ------------------------------------------------------------------ #
    def generate_pseudo_legal_moves(self) -> List[Move]:
        """All pseudo-legal moves for the side to move (may leave king in check)."""
        side = self.side_to_move
        moves: List[Move] = []
        for sq, piece in self.iter_pieces():
            if piece.color is side:
                moves += piece.pseudo_legal_moves(self, sq)
        return moves

    def legal_moves(self) -> List[Move]:
        """All fully legal moves for the side to move."""
        mover = self.side_to_move
        legal: List[Move] = []
        for move in self.generate_pseudo_legal_moves():
            self.make_move(move)
            if not self.is_attacked(self.king_square[mover], self.side_to_move):
                legal.append(move)
            self.unmake_move()
        return legal

    # ------------------------------------------------------------------ #
    # Making and unmaking moves
    # ------------------------------------------------------------------ #
    def make_move(self, move: Move) -> None:
        """Apply *move*, recording an :class:`Undo` so it can be reversed."""
        squares = self.squares
        frm, to = move.from_sq, move.to_sq
        piece = squares[frm]

        # Work out what (if anything) is captured.
        captured_sq = to
        if move.is_en_passant:
            captured_sq = to - 8 if piece.color is WHITE else to + 8
        captured = squares[captured_sq]

        self._undo_stack.append(Undo(
            move=move, moved_piece=piece, captured=captured,
            captured_sq=captured_sq, prev_castling=self.castling,
            prev_ep=self.ep_square, prev_halfmove=self.halfmove_clock,
            prev_fullmove=self.fullmove_number,
        ))

        # Remove any captured piece (its square may differ from `to`).
        if captured is not None:
            squares[captured_sq] = None

        # Move the piece, promoting if required.
        squares[frm] = None
        squares[to] = PROMOTION_CLASSES[move.promotion](piece.color) \
            if move.promotion else piece

        # King bookkeeping and the rook hop of a castle.
        if isinstance(piece, King):
            self.king_square[piece.color] = to
            if move.is_castle:
                if to > frm:                       # king-side
                    rook_from, rook_to = frm + 3, frm + 1
                else:                              # queen-side
                    rook_from, rook_to = frm - 4, frm - 1
                squares[rook_to] = squares[rook_from]
                squares[rook_from] = None

        # Castling rights: clear any affected by the from- or to-square.
        self.castling &= _castle_keep[frm] & _castle_keep[to]

        # En-passant target: set only after a pawn's two-square advance.
        self.ep_square = (frm + to) // 2 \
            if isinstance(piece, Pawn) and abs(to - frm) == 16 else None

        # Half-move clock (for the 50-move rule).
        self.halfmove_clock = 0 if (isinstance(piece, Pawn) or captured is not None) \
            else self.halfmove_clock + 1

        if self.side_to_move is BLACK:
            self.fullmove_number += 1
        self.side_to_move = self.side_to_move.other

    def unmake_move(self) -> None:
        """Reverse the most recently made move."""
        undo = self._undo_stack.pop()
        move = undo.move
        piece = undo.moved_piece
        frm, to = move.from_sq, move.to_sq
        squares = self.squares

        # Put the moving piece back (a promoted piece becomes its pawn again).
        squares[frm] = piece
        squares[to] = None
        if undo.captured is not None:
            squares[undo.captured_sq] = undo.captured

        if isinstance(piece, King):
            self.king_square[piece.color] = frm
            if move.is_castle:
                if to > frm:
                    rook_from, rook_to = frm + 3, frm + 1
                else:
                    rook_from, rook_to = frm - 4, frm - 1
                squares[rook_from] = squares[rook_to]
                squares[rook_to] = None

        self.castling = undo.prev_castling
        self.ep_square = undo.prev_ep
        self.halfmove_clock = undo.prev_halfmove
        self.fullmove_number = undo.prev_fullmove
        self.side_to_move = self.side_to_move.other

    # ------------------------------------------------------------------ #
    # End-of-game predicates that depend only on the position
    # ------------------------------------------------------------------ #
    def is_checkmate(self) -> bool:
        return self.is_in_check(self.side_to_move) and not self.legal_moves()

    def is_stalemate(self) -> bool:
        return (not self.is_in_check(self.side_to_move)) and not self.legal_moves()

    def is_fifty_move_rule(self) -> bool:
        return self.halfmove_clock >= 100

    def is_insufficient_material(self) -> bool:
        """The four FIDE "dead position by material" cases.

        K vs K, K+B vs K, K+N vs K, and K+B vs K+B with both bishops on
        same-coloured squares. Anything with a pawn, rook or queen can mate.
        """
        bishops: List[Tuple[Color, int]] = []   # (owner, square colour)
        knights = 0
        for sq, p in self.iter_pieces():
            if isinstance(p, King):
                continue
            if isinstance(p, Bishop):
                bishops.append((p.color, (file_of(sq) + rank_of(sq)) & 1))
            elif isinstance(p, Knight):
                knights += 1
            else:
                return False  # a pawn, rook or queen is sufficient

        minors = len(bishops) + knights
        if minors <= 1:
            return True  # bare kings, or king + a single minor
        if minors == 2 and knights == 0:
            (c0, s0), (c1, s1) = bishops
            return c0 is not c1 and s0 == s1  # opposite kings, same-colour bishops
        return False

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #
    def __str__(self) -> str:
        lines = []
        for rank in range(7, -1, -1):
            cells = []
            for file in range(8):
                piece = self.squares[make_square(file, rank)]
                cells.append(piece.symbol() if piece else ".")
            lines.append(f"{rank + 1}  " + " ".join(cells))
        lines.append("\n   " + " ".join("abcdefgh"))
        return "\n".join(lines)
