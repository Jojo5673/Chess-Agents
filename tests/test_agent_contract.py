"""
Contract tests that EVERY registered agent must pass.

They loop over the agent registry, so a new agent is
tested automatically as soon as it is registered in agents/__init__.py.
"""
import time
import unittest

import chess

from agents import available_agents, create_agent
from engine import MinimaxAgent, material

# Deliberately varied: both sides to move, asymmetric material, and the
# unusual positions that evaluation features (king distance, attack maps,
# pawn structure) tend to crash on.
SAMPLE_FENS = [
    chess.STARTING_FEN,
    "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
    "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 4 4",
    "r2q1rk1/ppp2ppp/2np1n2/2b1p1B1/2B1P1b1/2NP1N2/PPP2PPP/R2Q1RK1 w - - 0 8",
    "8/5pk1/6p1/8/3K4/8/5PP1/8 w - - 0 1",                    # pawn endgame
    "4k3/8/8/8/8/8/8/R3K3 w - - 0 1",                         # rook endgame, no queens
    "8/P6k/8/8/8/8/p6K/8 w - - 0 1",                          # pawns on the 7th / 2nd rank
    "4k3/8/8/8/8/8/8/4K2r w - - 0 1",                         # side to move in check
    "r3k2r/8/8/8/8/8/8/R3K2R w - - 0 1",                      # no castling rights
    "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1",                   # castling available
    "4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1",                      # en passant available
    "4k3/pppppppp/8/8/8/8/PPPPPPPP/4K3 b - - 0 1",           # no minor/major pieces
]

# Positions where one side is clearly ahead on material.
WHITE_UP_QUEEN = "4k3/8/8/8/8/8/8/Q3K3 w - - 0 1"
BLACK_UP_QUEEN = "q3k3/8/8/8/8/8/8/4K3 w - - 0 1"

EPS = 1e-9


def eval_agents():
    """(key, eval_fn) for every registered agent that has an evaluation function."""
    out = []
    for spec in available_agents():
        agent = create_agent(spec.key, depth=1 if spec.default_depth else None)
        if isinstance(agent, MinimaxAgent):
            out.append((spec.key, agent.eval_fn))
    return out


def mirror_violations(eval_fn):
    """FENs where evaluate(board) != -evaluate(board.mirror()). Empty = good."""
    bad = []
    for fen in SAMPLE_FENS:
        board = chess.Board(fen)
        if abs(eval_fn(board) + eval_fn(board.mirror())) > EPS:
            bad.append(fen)
    return bad


class EvaluationContractTests(unittest.TestCase):
    def test_at_least_one_eval_agent_is_registered(self):
        self.assertTrue(eval_agents())

    def test_mirror_symmetry(self):
        """Swapping colours must negate the score (catches a missing sign flip)."""
        for key, fn in eval_agents():
            with self.subTest(agent=key):
                self.assertEqual(mirror_violations(fn), [],
                                 f"{key}: evaluate(board) != -evaluate(board.mirror())")

    def test_material_sanity(self):
        for key, fn in eval_agents():
            with self.subTest(agent=key):
                self.assertGreater(fn(chess.Board(WHITE_UP_QUEEN)), 0,
                                   f"{key}: White up a queen should score > 0")
                self.assertLess(fn(chess.Board(BLACK_UP_QUEEN)), 0,
                                f"{key}: Black up a queen should score < 0")

    def test_returns_finite_number_on_edge_positions(self):
        for key, fn in eval_agents():
            for fen in SAMPLE_FENS:
                with self.subTest(agent=key, fen=fen):
                    score = fn(chess.Board(fen))
                    self.assertIsInstance(score, (int, float))
                    self.assertEqual(score, score, "NaN returned")          # NaN != NaN
                    self.assertNotIn(score, (float("inf"), float("-inf")))

    def test_evaluate_does_not_modify_the_board(self):
        for key, fn in eval_agents():
            for fen in SAMPLE_FENS:
                with self.subTest(agent=key, fen=fen):
                    board = chess.Board(fen)
                    board.push(next(iter(board.legal_moves)))   # give it a real move stack
                    before = (board.fen(), list(board.move_stack))
                    fn(board)
                    self.assertEqual((board.fen(), list(board.move_stack)), before)

    def test_checker_catches_a_sign_bug(self):
        """Meta-test: prove the mirror check really fails on a buggy evaluation."""
        def forgets_black(board):          # counts White's material only
            return material(board) + 0 if board.turn == chess.WHITE else abs(material(board))
        self.assertNotEqual(mirror_violations(forgets_black), [])


class AgentBehaviourTests(unittest.TestCase):
    def test_every_agent_returns_a_legal_move_everywhere(self):
        for spec in available_agents():
            agent = create_agent(spec.key, depth=1 if spec.default_depth else None)
            for fen in SAMPLE_FENS:
                board = chess.Board(fen)
                if board.is_game_over():
                    continue
                with self.subTest(agent=spec.key, fen=fen):
                    move = agent.choose_move(board).move
                    self.assertIn(move, board.legal_moves)

    def test_speed_budget_at_default_depth(self):
        """A slow evaluation makes matches unusable; flag it early."""
        limit_s = 10.0
        for spec in available_agents():
            agent = create_agent(spec.key)              # default depth
            for fen in SAMPLE_FENS[:2] + SAMPLE_FENS[3:4]:
                with self.subTest(agent=spec.key, fen=fen):
                    start = time.perf_counter()
                    agent.choose_move(chess.Board(fen))
                    took = time.perf_counter() - start
                    self.assertLess(took, limit_s,
                                    f"{spec.key} took {took:.1f}s at depth "
                                    f"{spec.default_depth} (limit {limit_s}s)")

    def test_agents_obey_depth_attribute(self):
        """The GUI's difficulty setting: changing .depth changes the next search."""
        for spec in available_agents():
            if not spec.default_depth:
                continue
            agent = create_agent(spec.key, depth=1)
            if hasattr(agent, "use_book"):
                agent.use_book = False   # this test is about search depth, not books
            board = chess.Board(SAMPLE_FENS[1])
            shallow = agent.choose_move(board)
            agent.depth = 2
            deeper = agent.choose_move(board)
            with self.subTest(agent=spec.key):
                self.assertEqual((shallow.depth, deeper.depth), (1, 2))
                self.assertGreater(deeper.nodes, shallow.nodes)


if __name__ == "__main__":
    unittest.main()
