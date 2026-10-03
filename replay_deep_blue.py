"""Replay Deep Blue vs Kasparov, 1996, Game 1, as an integration test.

This is the validation the brief asks for. We read the PGN, and for every move
we check three things against our own engine:

1. the move is present in the engine's legal-move list at that turn;
2. our check / checkmate detection agrees with the PGN's ``+`` / ``#`` marks;
3. at the end, the position reached matches a known reference FEN.

If our move generator, legality filter or check detection had a bug, one of
these would fail. (Game scores are facts, not copyrightable text; this one is
taken from the public record at chessgames.com, game id 1070874.)

Usage::

    python replay_deep_blue.py            # uses the bundled PGN
    python replay_deep_blue.py game.pgn   # any other PGN file
    python replay_deep_blue.py --boards   # also print the board after each move
    python replay_deep_blue.py --quiet    # only print the verdict
"""

from __future__ import annotations

import re
import sys
from typing import List, Tuple

from game import Game
from notation import parse_san

PGN_FILE = "deep_blue_1996_game1.pgn"

# Position after 37.Rxh7+ (Black resigned here, 1-0).
EXPECTED_FINAL_FEN = "8/7R/5q1k/3Q2N1/3p4/PP3pPP/5n1K/4r3 b - - 0 37"


def read_pgn_moves(path: str) -> List[str]:
    """Return the SAN move tokens from a PGN file (headers/results stripped)."""
    text = "".join(line for line in open(path, encoding="utf-8")
                    if not line.startswith("["))
    text = re.sub(r"\{[^}]*\}", " ", text)          # drop comments
    text = re.sub(r"\d+\.(\.\.)?", " ", text)        # drop move numbers
    tokens = text.split()
    results = {"1-0", "0-1", "1/2-1/2", "*"}
    return [t for t in tokens if t not in results]


def replay(path: str, quiet: bool = False, boards: bool = False) -> Tuple[bool, Game]:
    """Replay the game; return ``(ok, game)``."""
    moves = read_pgn_moves(path)
    game = Game()
    ok = True

    for ply, san in enumerate(moves, start=1):
        wants_mate = san.endswith("#")
        wants_check = san.endswith("+")

        move = parse_san(game.board, san)
        if move is None:
            print(f"  FAIL ply {ply}: '{san}' is not legal in this position.")
            return False, game

        game.push(move)

        # Cross-check our check / mate detection against the notation.
        in_check = game.board.is_in_check(game.board.side_to_move)
        is_mate = in_check and not game.board.legal_moves()
        if wants_mate and not is_mate:
            print(f"  FAIL ply {ply}: '{san}' marked mate but engine disagrees.")
            ok = False
        if wants_check and not wants_mate and not in_check:
            print(f"  FAIL ply {ply}: '{san}' marked check but engine disagrees.")
            ok = False

        if not quiet:
            mover = "White" if ply % 2 == 1 else "Black"
            num = (ply + 1) // 2
            print(f"  {num:>2}{'.' if ply % 2 else '...'} {san:<7} -> {move.uci()}")
            if boards:
                print(game.board)
                print()

    final = game.board.to_fen()
    if final != EXPECTED_FINAL_FEN:
        print("  FAIL: final position does not match the reference.")
        print(f"        got      {final}")
        print(f"        expected {EXPECTED_FINAL_FEN}")
        ok = False

    return ok, game


def main() -> int:
    args = sys.argv[1:]
    quiet = "--quiet" in args
    boards = "--boards" in args
    files = [a for a in args if not a.startswith("--")]
    path = files[0] if files else PGN_FILE

    print(f"Replaying {path} ...\n")
    ok, game = replay(path, quiet=quiet, boards=boards)
    print()
    print(game.board)
    print(f"\nMoves replayed: {len(game.history)} half-moves")
    print("Historical result: Deep Blue (White) won 1-0; Kasparov resigned "
          "after 37.Rxh7+.")
    if ok:
        print("\nVALIDATION PASSED: every move legal, checks/mates confirmed, "
              "final position matches.")
        return 0
    print("\nVALIDATION FAILED (see messages above).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
