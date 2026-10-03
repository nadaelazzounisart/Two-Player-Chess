"""Performance and correctness metrics for the report.

Three measurements, all suggested by the project review:

* **Perft** -- node counts at increasing depth, with timing. Doubles as a
  correctness check (the depth 1-4 counts from the initial position are known
  exactly: 20, 400, 8902, 197281).
* **Move-generation throughput** -- legal moves produced per second on a fixed
  position. A crude but honest measure of how fast the generator is.
* **Branching factor** -- the average and maximum number of legal moves per
  position, measured over a sample of random games. Connects to the
  complexity discussion (the game tree grows like b^d).

Run with::

    python benchmark.py
    python benchmark.py --json metrics.json    # also dump machine-readable
"""

from __future__ import annotations

import json
import random
import sys
import time
from typing import Dict, List, Tuple

from board import Board

KIWIPETE = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"


def perft(board: Board, depth: int) -> int:
    if depth == 0:
        return 1
    total = 0
    for move in board.legal_moves():
        board.make_move(move)
        total += perft(board, depth - 1)
        board.unmake_move()
    return total


def measure_perft(max_depth: int = 4) -> List[Dict]:
    board = Board.starting_position()
    rows = []
    for depth in range(1, max_depth + 1):
        t0 = time.perf_counter()
        nodes = perft(board, depth)
        dt = time.perf_counter() - t0
        rows.append({"depth": depth, "nodes": nodes, "seconds": dt,
                     "nodes_per_sec": nodes / dt if dt else 0.0})
    return rows


def measure_movegen_throughput(fen: str, seconds: float = 1.0) -> Dict:
    board = Board.from_fen(fen)
    n_moves = len(board.legal_moves())
    calls = 0
    total_moves = 0
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < seconds:
        total_moves += len(board.legal_moves())
        calls += 1
    dt = time.perf_counter() - t0
    return {"fen": fen, "legal_moves": n_moves, "calls": calls,
            "moves_per_sec": total_moves / dt, "calls_per_sec": calls / dt}


def measure_branching_factor(num_games: int = 40, max_plies: int = 200,
                             seed: int = 2026) -> Dict:
    rng = random.Random(seed)
    counts: List[int] = []
    for _ in range(num_games):
        board = Board.starting_position()
        for _ in range(max_plies):
            legal = board.legal_moves()
            if not legal:
                break
            counts.append(len(legal))
            board.make_move(rng.choice(legal))
    return {"positions": len(counts),
            "avg": sum(counts) / len(counts),
            "max": max(counts),
            "games": num_games}


def collect_metrics() -> Dict:
    return {
        "perft": measure_perft(4),
        "throughput_start": measure_movegen_throughput(Board().starting_position().to_fen()),
        "throughput_kiwipete": measure_movegen_throughput(KIWIPETE),
        "branching": measure_branching_factor(),
    }


def _print(metrics: Dict) -> None:
    print("Perft from the initial position")
    print(f"  {'depth':>5}  {'nodes':>10}  {'time (s)':>9}  {'nodes/s':>10}")
    for row in metrics["perft"]:
        print(f"  {row['depth']:>5}  {row['nodes']:>10}  "
              f"{row['seconds']:>9.3f}  {row['nodes_per_sec']:>10,.0f}")

    print("\nMove-generation throughput")
    for key in ("throughput_start", "throughput_kiwipete"):
        t = metrics[key]
        label = "start" if key.endswith("start") else "kiwipete"
        print(f"  {label:<9} {t['legal_moves']:>3} legal moves, "
              f"{t['moves_per_sec']:>10,.0f} moves/s "
              f"({t['calls_per_sec']:,.0f} generations/s)")

    b = metrics["branching"]
    print("\nBranching factor over random games")
    print(f"  {b['positions']:,} positions from {b['games']} games: "
          f"average {b['avg']:.1f}, maximum {b['max']}")


def main() -> int:
    args = sys.argv[1:]
    metrics = collect_metrics()
    _print(metrics)
    if "--json" in args:
        path = args[args.index("--json") + 1]
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(metrics, fh, indent=2)
        print(f"\nWrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
