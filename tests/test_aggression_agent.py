"""Feature and opening-book tests for the Aggression agent."""
import random
import unittest

import chess

from agents import aggression_agent as ag
from agents import create_agent
from match import evaluated_opening


def _after(san_line: str) -> chess.Board:
    board = chess.Board()
    for san in san_line.split():
        board.push_san(san)
    return board


def _book_moves(board: chess.Board) -> set:
    return {board.san(m) for m in ag.BOOK[board.turn].get(board.epd(), {})}


class OpeningBookTests(unittest.TestCase):
    def test_elephant_gambit_as_black(self):
        self.assertIn("d5", _book_moves(_after("e4 e5 Nf3")))

    def test_alien_gambit_as_white(self):
        self.assertIn("Ng5", _book_moves(_after("e4 c6 d4 d5 Nc3 dxe4 Nxe4 Nf6")))
        self.assertIn("Nxf7", _book_moves(_after("e4 c6 d4 d5 Nc3 dxe4 Nxe4 Nf6 Ng5 h6")))

    def test_martian_gambit_as_white(self):
        self.assertIn("Ng5", _book_moves(_after("e4 c6 d4 d5 Nc3 dxe4 Nxe4 Bf5")))
        self.assertIn("Ne6", _book_moves(
            _after("e4 c6 d4 d5 Nc3 dxe4 Nxe4 Bf5 Ng5 Bg6 N1f3 h6")))

    def test_agent_plays_book_move(self):
        agent = create_agent("aggression", depth=1, seed=0)
        result = agent.choose_move(_after("e4 e5 Nf3"))
        self.assertEqual(result.move, chess.Move.from_uci("d7d5"))
        self.assertEqual(result.depth, 0)

    def test_out_of_book_falls_back_to_search(self):
        agent = create_agent("aggression", depth=1, seed=0)
        result = agent.choose_move(_after("a3 h6 h3"))
        self.assertEqual(result.depth, 1)

    def test_book_can_be_disabled(self):
        agent = create_agent("aggression", depth=1, seed=0)
        agent.use_book = False
        self.assertEqual(agent.choose_move(chess.Board()).depth, 1)

    def test_match_openings_use_the_book(self):
        black = create_agent("aggression", depth=1, seed=0)
        white = create_agent("material", depth=1, seed=0)
        board = _after("e4 e5 Nf3")
        self.assertEqual(black.opening_move(board, random.Random(0)), chess.Move.from_uci("d7d5"))
        moves = evaluated_opening(black, white, random.Random(0), 1, 50)
        self.assertEqual(moves, [chess.Move.from_uci("e2e4")])   # White book is always 1.e4


class FeatureTests(unittest.TestCase):
    def _sides(self, board):
        return ag._SideInfo(board, chess.WHITE), ag._SideInfo(board, chess.BLACK)

    def test_concentrated_attack_is_superlinear(self):
        # Queen and knight both hitting the black king zone vs. the queen alone.
        both = chess.Board("6k1/5ppp/8/6N1/8/8/5Q2/6K1 w - - 0 1")
        queen = chess.Board("6k1/5ppp/8/8/8/8/5Q2/1N4K1 w - - 0 1")
        w_both, _ = self._sides(both)
        w_queen, _ = self._sides(queen)
        self.assertGreater(ag.king_attack(both, chess.WHITE, w_both),
                           2 * ag.king_attack(queen, chess.WHITE, w_queen))

    def test_open_king_is_penalised(self):
        sheltered = chess.Board("q5k1/8/8/8/8/8/5PPP/6K1 w - - 0 1")
        open_king = chess.Board("q5k1/8/8/8/8/8/8/6K1 w - - 0 1")
        self.assertGreater(ag.king_exposure(open_king, chess.WHITE),
                           ag.king_exposure(sheltered, chess.WHITE))

    def test_pawn_threat_on_piece(self):
        board = chess.Board("4k3/8/8/3n4/4P3/8/8/4K3 w - - 0 1")
        white, _ = self._sides(board)
        self.assertGreater(ag.threats(board, chess.WHITE, white), 0)

    def test_development(self):
        self.assertEqual(ag.undeveloped_minors(chess.Board(), chess.WHITE), 4)
        board = _after("Nf3 Nf6 Nc3")
        self.assertEqual(ag.undeveloped_minors(board, chess.WHITE), 2)

    def test_each_feature_is_mirror_symmetric(self):
        fens = [chess.STARTING_FEN,
                "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
                "6k1/5ppp/8/6N1/8/8/5Q2/6K1 w - - 0 1"]
        for fen in fens:
            board, mirror = chess.Board(fen), chess.Board(fen).mirror()
            bw, bb = self._sides(board)
            mw, mb = self._sides(mirror)
            with self.subTest(fen=fen):
                self.assertEqual(ag.king_attack(board, chess.WHITE, bw),
                                 ag.king_attack(mirror, chess.BLACK, mb))
                self.assertEqual(ag.king_exposure(board, chess.WHITE),
                                 ag.king_exposure(mirror, chess.BLACK))
                self.assertEqual(ag.threats(board, chess.WHITE, bw),
                                 ag.threats(mirror, chess.BLACK, mb))
                self.assertEqual(ag.mobility(board, chess.WHITE, bw, bb),
                                 ag.mobility(mirror, chess.BLACK, mb, mw))
                self.assertAlmostEqual(ag.evaluate(board), -ag.evaluate(mirror))


if __name__ == "__main__":
    unittest.main()
