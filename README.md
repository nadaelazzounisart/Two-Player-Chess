# Two-Player Chess (Project #4)

A complete two-player chess engine in pure Python, written as an exercise in
object-oriented design (Course 2 — Advanced OOP & Design Patterns). It enforces
**all** the rules: every piece's moves, the three special moves (castling, en
passant, promotion), check, checkmate, stalemate, and all three draw conditions
(50-move rule, threefold repetition, insufficient material), plus resignation
and draw offers. A text interface lets two humans play a full game; an optional
weak engine (random or minimax) can take one side.

No third-party chess library is used. The move generator, the legality filter,
the special-move handling and the end-of-game detection are all hand-written —
that is the heart of the project. The only standard-library dependencies are
`unittest` (tests) and, for regenerating the figures/report, `matplotlib`,
`reportlab` and Graphviz (`dot`).

## Requirements

* Python 3.10+ (uses `from __future__ import annotations`; developed on 3.12).
* Nothing else to *play* or to *test*.
* To regenerate the diagram and the PDF report: `pip install reportlab`, and the
  Graphviz `dot` binary on your `PATH`.

## How to run

Play a game (you will be asked to pick a mode):

```bash
python main.py
```

Modes: Human vs Human, Human vs the random engine, Human vs the minimax engine,
and two self-play demos. At the prompt you type moves in **long algebraic
notation** and can also issue commands:

```
e2e4            a normal move            O-O / O-O-O   castle
e7e8q           promotion (q/r/b/n)      moves         list legal moves
exd6            a capture (e.p. too)     board / fen   show board / FEN
undo            take back your move      draw          offer a draw
resign          resign                   quit          abandon
```

### Sample command to reproduce a result

Replay (and validate) Deep Blue vs Kasparov, Philadelphia 1996, Game 1:

```bash
python replay_deep_blue.py
```

Expected output ends with:

```
Moves replayed: 73 half-moves
VALIDATION PASSED: every move legal, checks/mates confirmed, final position matches.
```

### Tests and benchmarks

```bash
python -m unittest -v        # 25 tests: perft, every rule, every edge case
python benchmark.py          # perft throughput, move-gen speed, branching factor
```

## Project layout

```
pieces.py        Color, square helpers, Move, and the Piece hierarchy
board.py         Board: position state, make/unmake, is_attacked, legal moves, FEN
game.py          Game: move history, threefold repetition, result
players.py       Player strategy: Human, Random, Minimax (+ control commands)
notation.py      parse long-algebraic (interface) and SAN (PGN) into Moves
interface.py     ASCII board rendering and the game loop
main.py          entry point / mode menu

test_chess.py            the test suite
replay_deep_blue.py      replays + validates the 1996 game (integration test)
benchmark.py             perft / throughput / branching-factor metrics
deep_blue_1996_game1.pgn the game score

docs/make_uml.py         regenerates the UML diagram (Graphviz)
docs/build_report.py     regenerates report.pdf (reportlab)
report.pdf               the short written report
```

## Design in one paragraph

Two abstractions carry the design. `Piece` is an abstract base class; each of
the six pieces implements its own `pseudo_legal_moves`, so the board and game
never test a piece's concrete type — they just ask. `Player` is the **Strategy**
pattern: human, random and minimax players are interchangeable in the game loop.
Moves are **reversible** value objects: `Board.make_move` / `unmake_move` apply
and undo a move exactly, which keeps the legality filter trivial ("play it, is
my king attacked?, take it back") and makes the minimax search fall out for
free. Correctness is anchored by **perft** — the node counts from the start
position match the known values 20 / 400 / 8902 / 197281 — and by replaying a
real master/computer game move by move.

## A note on LLM use

An assistant was used for ancillary tasks only: tidying docstrings and this
README, and explaining a couple of error messages while debugging. The
algorithmic core — move generation, the pseudo-legal/legal split, all three
special moves, check detection and the end-of-game conditions — is our own work,
and we can each walk through any of it (for example, `Bishop.pseudo_legal_moves`,
or how the en-passant "discovered check" case is handled).
