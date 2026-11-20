#!/usr/bin/env python3
"""
Agent-vs-agent match harness.

Plays N games between agent A and agent B, alternating colours, and writes a
full log for the match report.

    python match.py --list
    python match.py --a material --b random --games 6 --depth 3
    python match.py --a material --b material --depth-a 2 --depth-b 4

Output folder (default match_logs/<timestamp>_<A>_vs_<B>/):
    summary.txt   scoreline, per-colour results, per-agent search stats
    moves.csv     every move: score, depth, nodes, time (for charts/analysis)
    games.json    full structured records
    games.pgn     all games, openable in any chess viewer

Why random openings? Both agents are (nearly) deterministic, so without any
variation every game would repeat. The first --opening-plies half-moves are
random (seeded, so reproducible). Each opening is played twice with the
colours swapped, which keeps the comparison fair.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import chess
import chess.pgn

from agents import available_agents, create_agent
from engine import Agent, Game


@dataclass
class GameRecord:
    game_no: int                 # 1-based
    a_is_white: bool
    white: str
    black: str
    result: str                  # '1-0', '0-1', '1/2-1/2'
    termination: str
    winner: Optional[str]        # 'A', 'B' or None (draw)
    plies: int
    duration_s: float
    opening: List[str]           # UCI moves of the random opening
    moves: List[dict] = field(default_factory=list)
    pgn: str = ""


@dataclass
class MatchResult:
    name_a: str
    name_b: str
    records: List[GameRecord]
    summary: Dict
    out_dir: Optional[Path] = None


# ---------------------------------------------------------------- one game --
def random_opening(rng: random.Random, plies: int) -> List[chess.Move]:
    """`plies` random legal half-moves, restarting if the game ends early."""
    while True:
        board = chess.Board()
        moves: List[chess.Move] = []
        for _ in range(plies):
            move = rng.choice(list(board.legal_moves))
            board.push(move)
            moves.append(move)
        # Reject openings that are already over, or hand the side to move a
        # mate in one (e.g. 1.f3 e5 2.g4 ... Qh4#) -- those make dull games.
        if board.is_game_over():
            continue
        if any(_gives_mate(board, m) for m in board.legal_moves):
            continue
        return moves


def _gives_mate(board: chess.Board, move: chess.Move) -> bool:
    board.push(move)
    mate = board.is_checkmate()
    board.pop()
    return mate


def play_game(white: Agent, black: Agent, *, game_no: int, a_is_white: bool,
              max_plies: int = 300, opening: Sequence[chess.Move] = (),
              verbose: bool = False) -> GameRecord:
    """Play one full game between two agents and return its record."""
    game = Game(white, black, max_plies=max_plies)
    start = time.perf_counter()
    for move in opening:
        game.play_move(move, source="opening")
    while not game.is_over:
        rec = game.play_agent_move()
        if verbose:
            print(f"  {rec.ply:3d}. {rec.color:5s} {rec.player:<12s} {rec.san:<7s}"
                  f" score={rec.score:+8.0f} nodes={rec.nodes:7d} {rec.time_s:5.2f}s")
    duration = time.perf_counter() - start

    result = game.result
    if result == "1-0":
        winner = "A" if a_is_white else "B"
    elif result == "0-1":
        winner = "B" if a_is_white else "A"
    else:
        winner = None

    pgn = chess.pgn.Game()
    pgn.headers.update({"Event": "COMP3220 Chess Match", "Round": str(game_no),
                        "White": white.name, "Black": black.name, "Result": result,
                        "Termination": game.termination})
    node = pgn
    for move in game.board.move_stack:
        node = node.add_variation(move)

    return GameRecord(
        game_no=game_no, a_is_white=a_is_white, white=white.name, black=black.name,
        result=result, termination=game.termination, winner=winner,
        plies=len(game.history), duration_s=round(duration, 2),
        opening=[m.uci() for m in opening],
        moves=[r.to_dict() for r in game.history], pgn=str(pgn),
    )


# ------------------------------------------------------------------- match --
def run_match(agent_a: Agent, agent_b: Agent, *, games: int = 6,
              max_plies: int = 300, opening_plies: int = 4, seed: int = 0,
              out_dir: Optional[str] = "match_logs", verbose: bool = False,
              quiet: bool = False) -> MatchResult:
    """Play `games` games, alternating colours; returns records + summary."""
    # Same opening for each colour-swapped pair of games.
    openings = [random_opening(random.Random(seed * 1000 + i), opening_plies)
                if opening_plies else []
                for i in range((games + 1) // 2)]
    records: List[GameRecord] = []
    for i in range(games):
        a_is_white = (i % 2 == 0)
        white, black = (agent_a, agent_b) if a_is_white else (agent_b, agent_a)
        rec = play_game(white, black, game_no=i + 1, a_is_white=a_is_white,
                        max_plies=max_plies, opening=openings[i // 2],
                        verbose=verbose)
        records.append(rec)
        if not quiet:
            who = {"A": "A wins", "B": "B wins", None: "draw"}[rec.winner]
            print(f"Game {rec.game_no}/{games}: A={'White' if a_is_white else 'Black'} "
                  f"-> {rec.result} ({who}, {rec.termination}, {rec.plies} plies, "
                  f"{rec.duration_s:.1f}s)")

    summary = summarize(records, agent_a, agent_b)
    result = MatchResult(agent_a.name, agent_b.name, records, summary)
    if out_dir:
        result.out_dir = write_logs(result, Path(out_dir), agent_a, agent_b)
    if not quiet:
        print("\n" + summary_text(result, agent_a, agent_b))
        if result.out_dir:
            print(f"\nLogs written to {result.out_dir}")
    return result


# --------------------------------------------------------------- reporting --
def _agent_stats(records: List[GameRecord], label: str) -> Dict:
    """Average search effort for agent `label` ('A' or 'B') over all its moves."""
    nodes, times = [], []
    for rec in records:
        color = "white" if (rec.a_is_white == (label == "A")) else "black"
        for m in rec.moves:
            if m["source"] == "agent" and m["color"] == color:
                nodes.append(m["nodes"])
                times.append(m["time_s"])
    n = len(nodes) or 1
    return {"moves": len(nodes), "avg_nodes": sum(nodes) / n,
            "avg_time_s": sum(times) / n, "max_time_s": max(times, default=0.0)}


def summarize(records: List[GameRecord], agent_a: Agent, agent_b: Agent) -> Dict:
    a_wins = sum(r.winner == "A" for r in records)
    b_wins = sum(r.winner == "B" for r in records)
    draws = sum(r.winner is None for r in records)
    return {
        "games": len(records), "a_wins": a_wins, "b_wins": b_wins, "draws": draws,
        "a_points": a_wins + 0.5 * draws, "b_points": b_wins + 0.5 * draws,
        "a_as_white": _tally(records, True), "a_as_black": _tally(records, False),
        "avg_plies": sum(r.plies for r in records) / max(len(records), 1),
        "depth_a": getattr(agent_a, "depth", None),
        "depth_b": getattr(agent_b, "depth", None),
        "stats_a": _agent_stats(records, "A"), "stats_b": _agent_stats(records, "B"),
    }


def _tally(records: List[GameRecord], a_is_white: bool) -> Dict:
    rs = [r for r in records if r.a_is_white == a_is_white]
    return {"games": len(rs), "wins": sum(r.winner == "A" for r in rs),
            "losses": sum(r.winner == "B" for r in rs),
            "draws": sum(r.winner is None for r in rs)}


def summary_text(result: MatchResult, agent_a: Agent, agent_b: Agent) -> str:
    s = result.summary
    lines = [
        f"MATCH: A = {agent_a.name} (depth {s['depth_a']})  vs  "
        f"B = {agent_b.name} (depth {s['depth_b']})",
        f"Games: {s['games']}   Scoreline: A {s['a_wins']} - {s['b_wins']} B   "
        f"Draws: {s['draws']}   Points: A {s['a_points']} / B {s['b_points']}",
        f"A as White: {_fmt(s['a_as_white'])}    A as Black: {_fmt(s['a_as_black'])}",
        f"Average game length: {s['avg_plies']:.1f} plies",
    ]
    for label, name, key in (("A", agent_a.name, "stats_a"), ("B", agent_b.name, "stats_b")):
        st = s[key]
        lines.append(f"{label} ({name}): {st['moves']} moves, "
                     f"avg {st['avg_nodes']:.0f} nodes/move, "
                     f"avg {st['avg_time_s']:.2f}s/move (max {st['max_time_s']:.2f}s)")
    lines.append("")
    for r in result.records:
        lines.append(f"  Game {r.game_no}: W={r.white:<10s} B={r.black:<10s} "
                     f"{r.result:<8s} {r.termination:<20s} {r.plies} plies")
    return "\n".join(lines)


def _fmt(t: Dict) -> str:
    return f"{t['wins']}W-{t['losses']}L-{t['draws']}D"


def write_logs(result: MatchResult, base: Path, agent_a: Agent, agent_b: Agent) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = lambda s: "".join(c if c.isalnum() else "_" for c in s)
    folder = base / f"{stamp}_{safe(agent_a.name)}_vs_{safe(agent_b.name)}"
    folder.mkdir(parents=True, exist_ok=True)

    (folder / "summary.txt").write_text(summary_text(result, agent_a, agent_b) + "\n")
    (folder / "games.pgn").write_text("\n\n".join(r.pgn for r in result.records) + "\n")
    (folder / "games.json").write_text(json.dumps(
        {"summary": result.summary,
         "games": [asdict(r) for r in result.records]}, indent=2))

    cols = ["game", "ply", "color", "side", "player", "san", "uci", "source",
            "score", "depth", "nodes", "time_s"]
    with open(folder / "moves.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        for r in result.records:
            for m in r.moves:
                a_color = "white" if r.a_is_white else "black"
                side = "A" if m["color"] == a_color else "B"
                writer.writerow([r.game_no, m["ply"], m["color"], side, m["player"],
                                 m["san"], m["uci"], m["source"], m["score"],
                                 m["depth"], m["nodes"], m["time_s"]])
    return folder


# --------------------------------------------------------------------- CLI --
def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--list", action="store_true", help="list registered agents and exit")
    p.add_argument("--a", default="material", help="agent A key (default: material)")
    p.add_argument("--b", default="random", help="agent B key (default: random)")
    p.add_argument("--games", type=int, default=6, help="number of games (default 6)")
    p.add_argument("--depth", type=int, help="search depth for both agents")
    p.add_argument("--depth-a", type=int, help="search depth for A (overrides --depth)")
    p.add_argument("--depth-b", type=int, help="search depth for B (overrides --depth)")
    p.add_argument("--opening-plies", type=int, default=0,
                   help="random opening half-moves per game pair (default 4, 0 = none)")
    p.add_argument("--max-plies", type=int, default=300,
                   help="declare a draw after this many half-moves (default 300)")
    p.add_argument("--seed", type=int, default=0, help="random seed (default 0)")
    p.add_argument("--out", default="match_logs", help="log folder ('' to disable)")
    p.add_argument("--verbose", action="store_true", help="print every move")
    args = p.parse_args()

    if args.list:
        for spec in available_agents():
            print(f"{spec.key:<12s} {spec.name:<12s} depth {spec.default_depth}  "
                  f"{spec.description}")
        return

    agent_a = create_agent(args.a, args.depth_a or args.depth, seed=args.seed)
    agent_b = create_agent(args.b, args.depth_b or args.depth, seed=args.seed + 1)
    run_match(agent_a, agent_b, games=args.games, max_plies=args.max_plies,
              opening_plies=args.opening_plies, seed=args.seed,
              out_dir=args.out or None, verbose=args.verbose)


if __name__ == "__main__":
    main()
