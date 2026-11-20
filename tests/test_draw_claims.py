import unittest

import chess

from engine import Game, HumanPlayer
from engine.search import terminal_score


class DrawClaimTests(unittest.TestCase):
    def setUp(self):
        self.white = HumanPlayer("White")
        self.black = HumanPlayer("Black")

    def _knight_cycle(self, board, repetitions):
        cycle = ("a1b3", "h8g8", "b3a1", "g8h8")
        for _ in range(repetitions):
            for uci in cycle:
                board.push_uci(uci)
        return board

    def test_claimable_threefold_does_not_end_game_or_search(self):
        board = chess.Board("7k/4p3/8/8/8/8/3P4/N5K1 w - - 0 1")
        self._knight_cycle(board, 2)

        self.assertTrue(board.can_claim_threefold_repetition())
        self.assertFalse(board.is_fivefold_repetition())
        self.assertIsNone(terminal_score(board, 0))
        game = Game(self.white, self.black, board=board)
        self.assertFalse(game.is_over)
        self.assertEqual(game.result, "*")

    def test_fivefold_repetition_ends_game_and_search(self):
        board = chess.Board("7k/4p3/8/8/8/8/3P4/N5K1 w - - 0 1")
        self._knight_cycle(board, 4)

        self.assertTrue(board.is_fivefold_repetition())
        self.assertEqual(terminal_score(board, 0), 0)
        game = Game(self.white, self.black, board=board)
        self.assertTrue(game.is_over)
        self.assertEqual(game.result, "1/2-1/2")

    def test_fifty_move_claim_is_not_automatic_but_seventyfive_moves_is(self):
        position = "4k3/8/8/8/4P3/8/8/4K3 w - - {} 51"
        claimable = chess.Board(position.format(100))
        automatic = chess.Board(position.format(150))

        self.assertTrue(claimable.is_fifty_moves())
        self.assertFalse(claimable.is_seventyfive_moves())
        self.assertIsNone(terminal_score(claimable, 0))
        self.assertFalse(Game(self.white, self.black, board=claimable).is_over)

        self.assertTrue(automatic.is_seventyfive_moves())
        self.assertEqual(terminal_score(automatic, 0), 0)
        self.assertTrue(Game(self.white, self.black, board=automatic).is_over)


if __name__ == "__main__":
    unittest.main()