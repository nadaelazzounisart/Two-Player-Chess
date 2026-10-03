"""High-level game state on top of a :class:`~board.Board`.

The board knows everything about a single *position*. A :class:`Game` adds the
things that depend on the *history* of the game: the list of moves played, the
repetition counts needed for the threefold rule, and the final result and how
it was reached (checkmate, resignation, one of the draw rules, ...).

This split keeps position-only logic (move generation, check, mate, stalemate,
insufficient material, the 50-move clock) on the board, and history-dependent
logic here.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from board import Board
from pieces import Color, Move, WHITE


class Game:
    """A full game: a board, its move history, and the result."""

    def __init__(self, board: Optional[Board] = None) -> None:
        self.board = board if board is not None else Board.starting_position()
        self.history: List[Move] = []
        self.result: Optional[str] = None       # '1-0', '0-1' or '1/2-1/2'
        self.termination: Optional[str] = None   # human-readable reason
        self._counts: Dict[object, int] = {self.board.position_key(): 1}

    # ------------------------------------------------------------------ #
    # Playing and taking back moves
    # ------------------------------------------------------------------ #
    def push(self, move: Move) -> None:
        """Play *move* and update the history and repetition counts."""
        self.board.make_move(move)
        self.history.append(move)
        key = self.board.position_key()
        self._counts[key] = self._counts.get(key, 0) + 1

    def pop(self) -> Move:
        """Take back the most recent move."""
        key = self.board.position_key()
        self._counts[key] -= 1
        if self._counts[key] == 0:
            del self._counts[key]
        self.board.unmake_move()
        return self.history.pop()

    def legal_moves(self) -> List[Move]:
        return self.board.legal_moves()

    # ------------------------------------------------------------------ #
    # Draw conditions / result
    # ------------------------------------------------------------------ #
    def is_threefold_repetition(self) -> bool:
        return self._counts.get(self.board.position_key(), 0) >= 3

    def update_result(self, legal: Optional[List[Move]] = None) -> Optional[str]:
        """Set ``result`` / ``termination`` if the game has ended naturally.

        Pass the already-computed legal move list to avoid generating it twice.
        """
        if self.result is not None:
            return self.result
        if legal is None:
            legal = self.board.legal_moves()
        stm = self.board.side_to_move

        if not legal:
            if self.board.is_in_check(stm):
                winner = stm.other
                self.result = "1-0" if winner is WHITE else "0-1"
                self.termination = "checkmate"
            else:
                self.result, self.termination = "1/2-1/2", "stalemate"
        elif self.board.is_insufficient_material():
            self.result, self.termination = "1/2-1/2", "insufficient material"
        elif self.board.is_fifty_move_rule():
            self.result, self.termination = "1/2-1/2", "fifty-move rule"
        elif self.is_threefold_repetition():
            self.result, self.termination = "1/2-1/2", "threefold repetition"
        return self.result

    def resign(self, color: Color) -> None:
        """*color* resigns; the opponent wins."""
        self.result = "0-1" if color is WHITE else "1-0"
        self.termination = "resignation"

    def agree_draw(self) -> None:
        self.result, self.termination = "1/2-1/2", "draw by agreement"

    @property
    def is_over(self) -> bool:
        return self.result is not None
