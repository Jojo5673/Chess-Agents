"""Run from the project root:  python -m unittest discover -v"""
import math
import random
import time
import unittest

import chess

from agents import available_agents, create_agent
from engine import (Game, GameOverError, HumanPlayer, IllegalMoveError,
                    MATE_SCORE, MinimaxAgent, RandomAgent, find_best_move, material)
from engine.search import _Searcher, _static_exchange_eval
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

    def test_static_exchange_estimates_a_losing_capture(self):
        board = chess.Board("2n4k/4r3/8/8/8/8/4Q3/K7 w - - 0 1")
        capture = chess.Move.from_uci("e2e7")

        self.assertEqual(_static_exchange_eval(board, capture), -400)

    def test_quiescence_does_not_prune_a_checking_capture(self):
        board = chess.Board("2nk4/4r3/8/8/8/8/4Q3/K7 w - - 0 1")
        capture = chess.Move.from_uci("e2e7")
        searcher = _Searcher(material, True, True)

        self.assertIn(capture, board.legal_moves)
        self.assertTrue(board.gives_check(capture))
        self.assertFalse(searcher._prune_quiescence_capture(board, capture))

    def test_transposition_table_reuses_exact_search_result(self):
        board = chess.Board()
        searcher = _Searcher(material, True, True)
        searcher._initialize_history(board)

        first = searcher._value(board, 2, -math.inf, math.inf, 0)
        searched_nodes = searcher.nodes
        second = searcher._value(board, 2, -math.inf, math.inf, 0)

        self.assertEqual(first, second)
        self.assertEqual(searcher.nodes, searched_nodes + 1)

    def test_transposition_keys_include_repetition_history(self):
        first = chess.Board()
        second = chess.Board()
        for uci in ("g1f3", "g8f6", "f3g1", "f6g8"):
            first.push_uci(uci)
        for uci in ("b1c3", "b8c6", "c3b1", "c6b8"):
            second.push_uci(uci)

        first_searcher = _Searcher(material, True, True)
        second_searcher = _Searcher(material, True, True)
        first_searcher._initialize_history(first)
        second_searcher._initialize_history(second)

        self.assertEqual(first._transposition_key(), second._transposition_key())
        self.assertNotEqual(
            first_searcher._tt_key(first), second_searcher._tt_key(second))

    def test_time_limit_returns_last_completed_iteration(self):
        board = chess.Board()
        initial_fen = board.fen()

        def slow_deeper_eval(position):
            if len(position.move_stack) >= 2:
                time.sleep(0.002)
            return material(position)

        result = find_best_move(board, 4, slow_deeper_eval, time_limit_s=0.05)

        self.assertEqual(result.depth, 1)
        self.assertIn(result.move, board.legal_moves)
        self.assertEqual(board.fen(), initial_fen)

    def test_tiny_time_limit_returns_a_legal_fallback(self):
        board = chess.Board()
        result = find_best_move(board, 4, material, time_limit_s=1e-12)

        self.assertEqual(result.depth, 0)
        self.assertIn(result.move, board.legal_moves)

    def test_time_limit_must_be_positive_or_none(self):
        with self.assertRaises(ValueError):
            find_best_move(chess.Board(), 1, material, time_limit_s=0)

    def test_randomization_margin_selects_only_near_best_moves_for_both_sides(self):
        white_board = chess.Board()
        white_scores = {"e2e4": 0.0, "d2d4": -30.0}
        white_choices = set()
        for seed in range(20):
            result = find_best_move(
                white_board, 1,
                lambda position: white_scores.get(position.peek().uci(), -500.0),
                rng=random.Random(seed),
                randomization_margin=40,
            )
            white_choices.add(result.move)
            self.assertIn(result.move, {
                chess.Move.from_uci("e2e4"), chess.Move.from_uci("d2d4"),
            })
        self.assertEqual(white_choices, {
            chess.Move.from_uci("e2e4"), chess.Move.from_uci("d2d4"),
        })

        black_board = chess.Board()
        black_board.turn = chess.BLACK
        black_scores = {"e7e5": 0.0, "d7d5": 30.0}
        black_choices = set()
        for seed in range(20):
            result = find_best_move(
                black_board, 1,
                lambda position: black_scores.get(position.peek().uci(), 500.0),
                rng=random.Random(seed),
                randomization_margin=40,
            )
            black_choices.add(result.move)
            self.assertIn(result.move, {
                chess.Move.from_uci("e7e5"), chess.Move.from_uci("d7d5"),
            })
        self.assertEqual(black_choices, {
            chess.Move.from_uci("e7e5"), chess.Move.from_uci("d7d5"),
        })

    def test_randomization_margin_must_be_non_negative(self):
        with self.assertRaises(ValueError):
            find_best_move(chess.Board(), 1, material, randomization_margin=-1)

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
        self.assertEqual([r.moves[-1]["fen_after"] for r in first.records],
                         [r.moves[-1]["fen_after"] for r in second.records])
        self.assertEqual(
            [record.opening for record in first.records],
            [record.opening for record in second.records],
        )
        s = first.summary
        self.assertEqual(s["a_wins"] + s["b_wins"] + s["draws"], 4)


if __name__ == "__main__":
    unittest.main()
