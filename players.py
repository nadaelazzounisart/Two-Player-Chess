"""Players -- the Strategy pattern in action.

The game loop never asks *how* a move is chosen; it just calls
``player.choose_move(game)``. That single abstraction lets a human, a random
mover and a minimax engine all be dropped into the same loop interchangeably.
This is the same pattern we used for the sorting / Blackjack strategies in the
Course 2 lab.

A human can also issue *commands* (resign, offer a draw, take back a move,
quit). Those are not moves, so :class:`HumanPlayer` signals them by raising a
small control exception that the game loop catches -- keeping ``choose_move``'s
return type cleanly "a Move" on the normal path.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import List, Optional

from notation import parse_move
from pieces import Move, WHITE


# --------------------------------------------------------------------------- #
# Control signals raised by a human player
# --------------------------------------------------------------------------- #
class PlayerCommand(Exception):
    """Base class for non-move commands a human can issue."""


class ResignCommand(PlayerCommand):
    pass


class DrawOfferCommand(PlayerCommand):
    pass


class UndoCommand(PlayerCommand):
    pass


class QuitCommand(PlayerCommand):
    pass


# --------------------------------------------------------------------------- #
# The strategy interface
# --------------------------------------------------------------------------- #
class Player(ABC):
    """Abstract player. Subclasses decide how a move is chosen."""

    def __init__(self, name: str = "Player") -> None:
        self.name = name

    @abstractmethod
    def choose_move(self, game) -> Move:
        """Return a legal move for the side to move in *game*."""
        raise NotImplementedError

    def accepts_draw(self, game) -> bool:
        """Whether this player accepts a draw offer. Default: no."""
        return False


# --------------------------------------------------------------------------- #
# Human
# --------------------------------------------------------------------------- #
class HumanPlayer(Player):
    """Reads moves and commands from the console."""

    def __init__(self, name: str = "Human") -> None:
        super().__init__(name)

    def choose_move(self, game) -> Move:
        while True:
            raw = input(f"{self.name} ({game.board.side_to_move.name.lower()}) > ").strip()
            cmd = raw.lower()
            if cmd in ("resign",):
                raise ResignCommand
            if cmd in ("draw", "offer draw"):
                raise DrawOfferCommand
            if cmd in ("undo", "takeback"):
                raise UndoCommand
            if cmd in ("quit", "exit"):
                raise QuitCommand
            if cmd in ("help", "?"):
                _print_help()
                continue
            if cmd in ("moves",):
                print("  " + " ".join(sorted(m.uci() for m in game.board.legal_moves())))
                continue
            if cmd in ("fen",):
                print("  " + game.board.to_fen())
                continue
            if cmd in ("board",):
                print(game.board)
                continue

            move = parse_move(game.board, raw)
            if move is None:
                print("  Illegal or unrecognised move. Type 'moves' to list "
                      "legal moves, or 'help'.")
                continue
            return move

    def accepts_draw(self, game) -> bool:
        answer = input(f"{self.name}, accept the draw? [y/N] ").strip().lower()
        return answer in ("y", "yes")


# --------------------------------------------------------------------------- #
# Random engine (bonus)
# --------------------------------------------------------------------------- #
class RandomPlayer(Player):
    """Plays a uniformly random legal move. Trivial once the Player interface
    exists -- which is the point of the Strategy pattern."""

    def __init__(self, name: str = "Random", seed: Optional[int] = None) -> None:
        super().__init__(name)
        self._rng = random.Random(seed)

    def choose_move(self, game) -> Move:
        return self._rng.choice(game.board.legal_moves())


# --------------------------------------------------------------------------- #
# Minimax engine (bonus)
# --------------------------------------------------------------------------- #
MATE_SCORE = 1_000_000


class MinimaxPlayer(Player):
    """A negamax search with alpha-beta pruning and a material-only evaluation.

    Depth 1 is the trivial version from the brief: it just grabs the most
    material on this move, so it will happily hang pieces because it never looks
    at the reply. Depth 2+ adds alpha-beta, which is the sensible next step. We
    deliberately stop there -- no piece-square tables, no opening book, no
    transposition tables. Those belong to a different course; the value here is
    a clean, correct search built on the reversible move objects.
    """

    def __init__(self, depth: int = 2, name: Optional[str] = None,
                 seed: Optional[int] = None) -> None:
        super().__init__(name or f"Minimax(d={depth})")
        self.depth = depth
        self._rng = random.Random(seed)

    def choose_move(self, game) -> Move:
        board = game.board
        legal = board.legal_moves()
        # Shuffle so equal-valued moves are not always played in the same order.
        self._rng.shuffle(legal)

        best_move, best_score = legal[0], -MATE_SCORE - 1
        alpha, beta = -MATE_SCORE - 1, MATE_SCORE + 1
        for move in self._ordered(board, legal):
            board.make_move(move)
            score = -self._negamax(board, self.depth - 1, -beta, -alpha)
            board.unmake_move()
            if score > best_score:
                best_score, best_move = score, move
            if score > alpha:
                alpha = score
        return best_move

    def _negamax(self, board, depth: int, alpha: int, beta: int) -> int:
        if depth == 0:
            return self._evaluate(board)

        legal = board.legal_moves()
        if not legal:                       # terminal node
            if board.is_in_check(board.side_to_move):
                return -MATE_SCORE          # side to move is checkmated
            return 0                        # stalemate

        best = -MATE_SCORE - 1
        for move in self._ordered(board, legal):
            board.make_move(move)
            score = -self._negamax(board, depth - 1, -beta, -alpha)
            board.unmake_move()
            if score > best:
                best = score
            if best > alpha:
                alpha = best
            if alpha >= beta:               # beta cut-off
                break
        return best

    @staticmethod
    def _evaluate(board) -> int:
        """Material balance from the point of view of the side to move."""
        stm = board.side_to_move
        score = 0
        for _, piece in board.iter_pieces():
            score += piece.VALUE if piece.color is stm else -piece.VALUE
        return score

    @staticmethod
    def _ordered(board, moves: List[Move]) -> List[Move]:
        """Try captures first -- cheap move ordering that helps alpha-beta."""
        return sorted(moves,
                      key=lambda m: board.squares[m.to_sq] is not None
                      or m.is_en_passant,
                      reverse=True)


def _print_help() -> None:
    print("""
  Commands:
    e2e4            move in long algebraic notation
    e7e8q           promotion (q/r/b/n; defaults to queen if omitted)
    O-O / O-O-O     castle king-side / queen-side
    moves           list all legal moves
    board / fen     show the board / the FEN string
    undo            take back your last move (reverts the last two half-moves)
    draw            offer a draw
    resign          resign the game
    quit            abandon the game
""")
