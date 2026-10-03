"""The text interface and the game loop.

Rendering is intentionally simple ASCII: ranks 8 down to 1, files a-h, White in
upper case and Black in lower case. The loop drives any two :class:`Player`
objects -- human or engine -- through a full game, handles the human commands
(resign / draw / undo / quit) and announces the result.
"""

from __future__ import annotations

from typing import Dict, Optional

from game import Game
from pieces import Color, WHITE, BLACK
from players import (
    DrawOfferCommand, HumanPlayer, Player, QuitCommand, ResignCommand,
    UndoCommand,
)


def render(board) -> str:
    """Return the ASCII rendering of *board* (a thin wrapper over ``str``)."""
    return str(board)


def play_game(white: Player, black: Player, game: Optional[Game] = None,
              show_board: bool = True) -> Game:
    """Play one game between *white* and *black*; return the finished game."""
    game = game if game is not None else Game()
    players: Dict[Color, Player] = {WHITE: white, BLACK: black}

    if show_board:
        print(render(game.board))

    while True:
        legal = game.board.legal_moves()
        game.update_result(legal)
        if game.is_over:
            break

        mover = game.board.side_to_move
        player = players[mover]
        if game.board.is_in_check(mover):
            print(f"** {mover.name.title()} is in check.")

        try:
            move = player.choose_move(game)
        except ResignCommand:
            game.resign(mover)
            break
        except QuitCommand:
            print("\nGame abandoned.")
            return game
        except DrawOfferCommand:
            opponent = players[mover.other]
            print(f"{player.name} offers a draw.")
            if opponent.accepts_draw(game):
                game.agree_draw()
                break
            print("Draw declined.\n")
            continue
        except UndoCommand:
            if not game.history:
                print("Nothing to undo.\n")
                continue
            for _ in range(min(2, len(game.history))):
                game.pop()
            print("Move(s) taken back.\n")
            if show_board:
                print(render(game.board))
            continue

        game.push(move)
        label = "castles" if move.is_castle else f"plays {move.uci()}"
        print(f"{player.name} ({mover.name.lower()}) {label}.")
        if show_board:
            print(render(game.board))

    _announce(game)
    return game


def _announce(game: Game) -> None:
    score, reason = game.result, game.termination
    if score == "1/2-1/2":
        print(f"\n== Draw ({reason}). [{score}]")
    else:
        winner = "White" if score == "1-0" else "Black"
        print(f"\n== {winner} wins by {reason}. [{score}]")
