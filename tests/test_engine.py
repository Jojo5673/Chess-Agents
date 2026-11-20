"""Run from the project root:  python -m unittest discover -v"""
import math
import random
import unittest

import chess

from agents import available_agents, create_agent
from engine import (Game, GameOverError, HumanPlayer, IllegalMoveError,
                    MATE_SCORE, MinimaxAgent, RandomAgent, find_best_move, material)
from engine.search import _Searcher
from match import run_match

POSITIONS = [
    chess.STARTING_FEN,
    "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
    "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 4 4",
    "8/5pk1/6p1/8/3K4/8/5PP1/8 w - - 0 1",
]


class SearchTests(unittest.TestCase):
    def test_alpha_beta_matches_plain_minimax(self):
        """Pruning must never change the value of the search."""
        for fen in POSITIONS:
            for depth in (1, 2):
                plain = find_best_move(chess.Board(fen), depth, material,
                                       use_alpha_beta=False, order_moves=False)
                pruned = find_best_move(chess.Board(fen), depth, material)
                self.assertEqual(plain.score, pruned.score, (fen, depth))
        plain = find_best_move(chess.Board(POSITIONS[0]), 3, material,
                               use_alpha_beta=False, order_moves=False)
        pruned = find_best_move(chess.Board(POSITIONS[0]), 3, material)
        self.assertEqual(plain.score, pruned.score, (POSITIONS[0], 3))

    def test_pruning_reduces_nodes(self):
        fen = POSITIONS[0]
        plain = find_best_move(chess.Board(fen), 3, material, use_alpha_beta=False)
        pruned = find_best_move(chess.Board(fen), 3, material)
        self.assertLess(pruned.nodes, plain.nodes)

    def test_finds_mate_in_one_for_white(self):
        board = chess.Board("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1")
        res = find_best_move(board, 2, material)
        self.assertEqual(res.move, chess.Move.from_uci("a1a8"))
        self.assertEqual(res.score, MATE_SCORE - 1)

    def test_finds_mate_in_one_for_black(self):
        board = chess.Board("r5k1/5ppp/8/8/8/8/5PPP/6K1 b - - 0 1")
        res = find_best_move(board, 2, material)
        self.assertEqual(res.move, chess.Move.from_uci("a8a1"))
        self.assertEqual(res.score, -(MATE_SCORE - 1))   # White perspective

    def test_quiescence_sees_recapture_before_committing_capture(self):
        board = chess.Board("2n4k/4r3/8/8/8/8/4Q3/K7 w - - 0 1")
        losing_capture = chess.Move.from_uci("e2e7")

        self.assertIn(losing_capture, board.legal_moves)
        result = find_best_move(board, 1, material)

        self.assertNotEqual(result.move, losing_capture)

    def test_quiescence_searches_legal_evasions_when_in_check(self):
        board = chess.Board("4k3/8/8/8/8/8/8/K3R3 b - - 0 1")
        searcher = _Searcher(
            lambda position: -100 if position.is_check() else 0,
            use_alpha_beta=True,
            order_moves=True,
        )

        self.assertTrue(board.is_check())
        self.assertEqual(
            searcher._quiescence(board, -math.inf, math.inf, ply=0, qply=0),
            0,
        )

    def test_search_restores_board(self):
        board = chess.Board(POSITIONS[1])
        fen, stack = board.fen(), list(board.move_stack)
        find_best_move(board, 3, material)
        self.assertEqual(board.fen(), fen)
        self.assertEqual(list(board.move_stack), stack)

    def test_agent_does_not_touch_the_real_board(self):
        board = chess.Board(POSITIONS[1])
        fen = board.fen()
        create_agent("material", 2).choose_move(board)
        self.assertEqual(board.fen(), fen)

    def test_score_sign_convention(self):
        black_up_a_queen = chess.Board("4k3/8/8/8/8/8/8/q3K3 w - - 0 1")
        self.assertLess(material(black_up_a_queen), 0)

    def test_random_tiebreak_varies_but_is_seed_reproducible(self):
        def pick(seed):
            agent = MinimaxAgent("m", material, 1, seed=seed)
            return agent.choose_move(chess.Board()).move
        self.assertEqual(pick(5), pick(5))
        self.assertGreater(len({pick(s) for s in range(20)}), 1)

    def test_stalemate_scores_zero(self):
        board = chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")  # black stalemated
        res = find_best_move(board, 1, material)
        self.assertIsNone(res.move)
        self.assertEqual(res.score, 0)


class GameTests(unittest.TestCase):
    def test_human_flow_and_history(self):
        game = Game(HumanPlayer("You"), create_agent("material", 1))
        self.assertTrue(game.is_human_turn)
        move = game.move_from_squares(chess.E2, chess.E4)
        rec = game.play_move(move)
        self.assertEqual((rec.san, rec.color, rec.source), ("e4", "white", "human"))
        self.assertTrue(game.is_agent_turn)
        reply = game.play_agent_move()
        self.assertEqual((reply.color, reply.source), ("black", "agent"))
        self.assertIsNotNone(reply.nodes)
        self.assertEqual(len(game.history), 2)

    def test_illegal_move_rejected(self):
        game = Game(HumanPlayer("You"), HumanPlayer("Me"))
        self.assertIsNone(game.move_from_squares(chess.E2, chess.E5))
        with self.assertRaises(IllegalMoveError):
            game.play_move(chess.Move.from_uci("e2e5"))

    def test_undo(self):
        game = Game(HumanPlayer("a"), HumanPlayer("b"))
        game.play_move(game.move_from_squares(chess.E2, chess.E4))
        game.undo()
        self.assertEqual(game.board.fen(), chess.STARTING_FEN)
        self.assertEqual(game.history, [])

    def test_auto_queen_and_underpromotion(self):
        board = chess.Board("8/P6k/8/8/8/8/8/K7 w - - 0 1")
        game = Game(HumanPlayer("a"), HumanPlayer("b"), board=board)
        self.assertTrue(game.is_promotion(chess.A7, chess.A8))
        self.assertEqual(game.move_from_squares(chess.A7, chess.A8).promotion, chess.QUEEN)
        self.assertEqual(game.move_from_squares(chess.A7, chess.A8, chess.KNIGHT).promotion,
                         chess.KNIGHT)

    def test_game_over_and_result(self):
        game = Game(HumanPlayer("w"), HumanPlayer("b"))
        for uci in ("f2f3", "e7e5", "g2g4", "d8h4"):          # fool's mate
            game.play_move(chess.Move.from_uci(uci))
        self.assertTrue(game.is_over)
        self.assertEqual(game.result, "0-1")
        self.assertEqual(game.termination, "checkmate")
        self.assertEqual(game.winner, chess.BLACK)
        self.assertIn("wins", game.status_text())
        with self.assertRaises(GameOverError):
            game.play_move(chess.Move.from_uci("a2a3"))

    def test_max_plies_draw(self):
        game = Game(create_agent("random", seed=1), create_agent("random", seed=2),
                    max_plies=6)
        while not game.is_over:
            game.play_agent_move()
        self.assertLessEqual(len(game.history), 6)

    def test_on_move_callback(self):
        seen = []
        game = Game(HumanPlayer("a"), HumanPlayer("b"), on_move=seen.append)
        game.play_move(game.move_from_squares(chess.D2, chess.D4))
        self.assertEqual([r.san for r in seen], ["d4"])


class RegistryAndMatchTests(unittest.TestCase):
    def test_registry_builds_every_agent(self):
        for spec in available_agents():
            agent = create_agent(spec.key, depth=1 if spec.default_depth else None)
            self.assertTrue(agent.choose_move(chess.Board()).move)

    def test_match_alternates_colours_and_is_reproducible(self):
        def play():
            a, b = create_agent("material", 1, seed=1), create_agent("random", seed=2)
            return run_match(a, b, games=4, max_plies=60, opening_plies=4,
                             seed=7, out_dir=None, quiet=True)
        first, second = play(), play()
        self.assertEqual([r.a_is_white for r in first.records], [True, False, True, False])
        # colour-swapped pairs share the same random opening
        self.assertEqual(first.records[0].opening, first.records[1].opening)
        self.assertEqual([r.moves[-1]["fen_after"] for r in first.records],
                         [r.moves[-1]["fen_after"] for r in second.records])
        s = first.summary
        self.assertEqual(s["a_wins"] + s["b_wins"] + s["draws"], 4)


if __name__ == "__main__":
    unittest.main()
