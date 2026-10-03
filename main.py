"""Entry point: pick the two players and start a game.

Run with::

    python main.py

You will be asked to choose a game mode. For a non-interactive demo of the
engine playing itself, see ``benchmark.py`` and ``replay_deep_blue.py``.
"""

from __future__ import annotations

from interface import play_game
from players import HumanPlayer, MinimaxPlayer, RandomPlayer

MENU = """\
Two-Player Chess
================
  1) Human vs Human
  2) Human (White) vs Random engine
  3) Human (White) vs Minimax engine
  4) Random vs Random        (demo, no board spam)
  5) Minimax vs Minimax      (demo)
"""


def main() -> None:
    print(MENU)
    choice = input("Choose 1-5 [1]: ").strip() or "1"

    if choice == "1":
        play_game(HumanPlayer("Player 1"), HumanPlayer("Player 2"))
    elif choice == "2":
        play_game(HumanPlayer("You"), RandomPlayer("Random engine"))
    elif choice == "3":
        depth = _ask_depth()
        play_game(HumanPlayer("You"), MinimaxPlayer(depth=depth))
    elif choice == "4":
        play_game(RandomPlayer("Random A", seed=1),
                  RandomPlayer("Random B", seed=2), show_board=False)
    elif choice == "5":
        depth = _ask_depth()
        play_game(MinimaxPlayer(depth=depth, name="Minimax A", seed=1),
                  MinimaxPlayer(depth=depth, name="Minimax B", seed=2),
                  show_board=False)
    else:
        print("Unknown choice; defaulting to Human vs Human.")
        play_game(HumanPlayer("Player 1"), HumanPlayer("Player 2"))


def _ask_depth() -> int:
    raw = input("Engine search depth 1-3 [2]: ").strip() or "2"
    try:
        return max(1, min(3, int(raw)))
    except ValueError:
        return 2


if __name__ == "__main__":
    main()
