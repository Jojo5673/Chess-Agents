"""
Locks in the match log format so report/chart scripts don't silently break.
If you change a column or key on purpose, update the expectations here.
"""
import csv
import json
import tempfile
import unittest
from pathlib import Path

import chess.pgn

from agents import create_agent
from match import run_match

CSV_COLUMNS = ["game", "ply", "color", "side", "player", "san", "uci", "source",
               "score", "depth", "nodes", "time_s"]
SUMMARY_KEYS = {"games", "a_wins", "b_wins", "draws", "a_points", "b_points",
                "a_as_white", "a_as_black", "avg_plies", "depth_a", "depth_b",
                "stats_a", "stats_b"}
GAME_KEYS = {"game_no", "a_is_white", "white", "black", "result", "termination",
             "winner", "plies", "duration_s", "opening", "moves", "pgn"}
MOVE_KEYS = {"ply", "color", "player", "uci", "san", "source", "score", "depth",
             "nodes", "time_s", "fen_after"}
GAMES = 4


class MatchOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.result = run_match(create_agent("material", 1, seed=1),
                               create_agent("random", seed=2),
                               games=GAMES, max_plies=60, opening_plies=4, seed=3,
                               out_dir=cls.tmp.name, quiet=True)
        cls.folder = cls.result.out_dir

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_all_four_files_are_written(self):
        names = {p.name for p in Path(self.folder).iterdir()}
        self.assertEqual(names, {"summary.txt", "moves.csv", "games.json", "games.pgn"})

    def test_csv_columns_and_row_count(self):
        with open(Path(self.folder) / "moves.csv", newline="") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0], CSV_COLUMNS)
        total_moves = sum(len(r.moves) for r in self.result.records)
        self.assertEqual(len(rows) - 1, total_moves)
        side_col = CSV_COLUMNS.index("side")
        self.assertTrue({row[side_col] for row in rows[1:]} <= {"A", "B"})

    def test_json_structure(self):
        data = json.loads((Path(self.folder) / "games.json").read_text())
        self.assertEqual(set(data), {"summary", "games"})
        self.assertEqual(set(data["summary"]), SUMMARY_KEYS)
        self.assertEqual(len(data["games"]), GAMES)
        for game in data["games"]:
            self.assertEqual(set(game), GAME_KEYS)
            for move in game["moves"]:
                self.assertEqual(set(move), MOVE_KEYS)

    def test_pgn_contains_every_game(self):
        with open(Path(self.folder) / "games.pgn") as f:
            games = []
            while (g := chess.pgn.read_game(f)) is not None:
                games.append(g)
        self.assertEqual(len(games), GAMES)
        self.assertEqual({g.headers["White"] for g in games} |
                         {g.headers["Black"] for g in games}, {"Material", "Random"})

    def test_summary_is_consistent(self):
        s = self.result.summary
        self.assertEqual(s["a_wins"] + s["b_wins"] + s["draws"], GAMES)
        self.assertAlmostEqual(s["a_points"] + s["b_points"], GAMES)
        self.assertEqual(s["a_as_white"]["games"] + s["a_as_black"]["games"], GAMES)
        text = (Path(self.folder) / "summary.txt").read_text()
        self.assertIn("Scoreline", text)

    def test_openings_use_the_agents_assigned_to_each_game(self):
        agent_a = create_agent("material", 1, seed=1)
        agent_b = create_agent("structure", 1, seed=2)
        agent_a.opening_move = lambda board, rng: chess.Move.from_uci(
            "e2e4" if board.turn == chess.WHITE else "e7e5")
        agent_b.opening_move = lambda board, rng: chess.Move.from_uci(
            "d2d4" if board.turn == chess.WHITE else "d7d5")

        result = run_match(
            agent_a,
            agent_b,
            games=2,
            max_plies=4,
            opening_plies=2,
            opening_margin_cp=40,
            seed=7,
            out_dir=None,
            quiet=True,
        )

        self.assertEqual(result.records[0].opening, ["e2e4", "d7d5"])
        self.assertEqual(result.records[1].opening, ["d2d4", "e7e5"])
        for record in result.records:
            board = chess.Board()
            for uci in record.opening:
                move = chess.Move.from_uci(uci)
                self.assertIn(move, board.legal_moves)
                board.push(move)
            self.assertEqual(
                [move["source"] for move in record.moves[:2]],
                ["opening", "opening"],
            )


if __name__ == "__main__":
    unittest.main()
