"""Tests for the parts of Game that a GUI relies on."""
import threading
import unittest

import chess

from agents import create_agent
from engine import Game, HumanPlayer


class SpecialMoveTests(unittest.TestCase):
    def test_castling_by_king_click(self):
        board = chess.Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
        game = Game(HumanPlayer("w"), HumanPlayer("b"), board=board)
        move = game.move_from_squares(chess.E1, chess.G1)
        self.assertIsNotNone(move)
        self.assertEqual(game.play_move(move).san, "O-O")
        self.assertEqual(game.board.piece_at(chess.F1).piece_type, chess.ROOK)
        queen_side = game.move_from_squares(chess.E8, chess.C8)
        self.assertEqual(game.play_move(queen_side).san, "O-O-O")

    def test_castling_blocked_through_check_is_rejected(self):
        board = chess.Board("4k3/8/8/8/8/8/5r2/R3K2R w KQ - 0 1")   # rook attacks f1
        game = Game(HumanPlayer("w"), HumanPlayer("b"), board=board)
        self.assertIsNone(game.move_from_squares(chess.E1, chess.G1))
        self.assertIsNotNone(game.move_from_squares(chess.E1, chess.C1))

    def test_en_passant_by_pawn_click(self):
        board = chess.Board("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
        game = Game(HumanPlayer("w"), HumanPlayer("b"), board=board)
        move = game.move_from_squares(chess.E5, chess.D6)
        self.assertIsNotNone(move)
        self.assertEqual(game.play_move(move).san, "exd6")
        self.assertIsNone(game.board.piece_at(chess.D5))     # captured pawn removed

    def test_black_promotion_and_underpromotion(self):
        board = chess.Board("4k3/8/8/8/8/8/p7/4K3 b - - 0 1")
        game = Game(HumanPlayer("w"), HumanPlayer("b"), board=board)
        self.assertEqual(game.move_from_squares(chess.A2, chess.A1).promotion, chess.QUEEN)
        self.assertEqual(game.move_from_squares(chess.A2, chess.A1, chess.ROOK).promotion,
                         chess.ROOK)

    def test_legal_moves_from_square(self):
        game = Game(HumanPlayer("w"), HumanPlayer("b"))
        targets = {m.to_square for m in game.legal_moves_from(chess.E2)}
        self.assertEqual(targets, {chess.E3, chess.E4})
        self.assertEqual(game.legal_moves_from(chess.E5), [])   # empty square

    def test_status_text_tracks_the_game(self):
        game = Game(HumanPlayer("Alice"), HumanPlayer("Bob"))
        self.assertIn("White to move (Alice)", game.status_text())
        game.play_move(game.move_from_squares(chess.E2, chess.E4))
        self.assertIn("Black to move (Bob)", game.status_text())


class ThreadingTests(unittest.TestCase):
    def test_board_stays_consistent_while_agent_thinks_in_a_thread(self):
        """The GUI reads game.board on the UI thread while a worker searches."""
        board = chess.Board("r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
        game = Game(create_agent("material", depth=3, seed=1), HumanPlayer("b"), board=board)
        before = game.board.fen()
        worker = threading.Thread(target=game.play_agent_move)
        seen = set()
        worker.start()
        while worker.is_alive():
            seen.add(game.board.fen())          # must never be a half-searched position
        worker.join()
        after = game.board.fen()
        self.assertNotEqual(before, after)
        self.assertLessEqual(seen, {before, after})

    def test_difficulty_change_between_moves(self):
        agent = create_agent("material", depth=1, seed=3)
        game = Game(agent, create_agent("random", seed=4))
        game.play_agent_move()
        agent.depth = 2
        game.play_agent_move()
        game.play_agent_move()
        self.assertEqual([r.depth for r in game.history if r.player == "Material"], [1, 2])


if __name__ == "__main__":
    unittest.main()
