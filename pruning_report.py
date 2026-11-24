#!/usr/bin/env python3
"""
Measures how much Alpha-Beta pruning and move ordering saves.
Used to explain minimax and alpha beta implementation in documentation.
See instructions to reproduce documentation results in documentation

Usage:
    python pruning_report.py            # depths 1-3
    python pruning_report.py --max-depth 4

Prints nodes visited by: plain minimax, alpha-beta, alpha-beta + move ordering.
"""
import argparse

import chess

from engine import find_best_move, material

POSITIONS = {
    "start position": chess.STARTING_FEN,
    "middlegame": "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
    "endgame": "8/5pk1/6p1/8/3K4/8/5PP1/8 w - - 0 1",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-depth", type=int, default=3)
    args = parser.parse_args()

    print(f"{'position':<16}{'depth':>5}{'minimax':>11}{'alpha-beta':>12}"
          f"{'+ordering':>11}{'saved':>8}")
    for name, fen in POSITIONS.items():
        for depth in range(1, args.max_depth + 1):
            plain = find_best_move(chess.Board(fen), depth, material,
                                   use_alpha_beta=False, order_moves=False)
            ab = find_best_move(chess.Board(fen), depth, material,
                                use_alpha_beta=True, order_moves=False)
            ordered = find_best_move(chess.Board(fen), depth, material,
                                     use_alpha_beta=True, order_moves=True)
            assert plain.score == ab.score == ordered.score, "pruning changed the result!"
            saved = 100 * (1 - ordered.nodes / plain.nodes)
            print(f"{name:<16}{depth:>5}{plain.nodes:>11,}{ab.nodes:>12,}"
                  f"{ordered.nodes:>11,}{saved:>7.0f}%")


if __name__ == "__main__":
    main()
