import unittest

import chess

from agents import create_agent
from agents.structure_agent import (
    backward_pawns,
    bishop_pair,
    backward_pawns,
    central_king_penalty,
    doubled_pawns,
    evaluate,
    game_phase,
    isolated_pawns,
    king_safety,
    open_king_files,
    passed_pawns,
    pawn_shields,
    piece_protection,
    piece_square_score,
    protected_pawns,
    rook_file_score,
    safe_king_corners,
)
from engine.search import terminal_score


def board(fen):
    return chess.Board(fen)


class StructureFeatureTests(unittest.TestCase):
    def test_doubled_pawns_score_below_separated_pawns(self):
        doubled = board("4k3/8/8/8/8/4P3/4P3/4K3 w - - 0 1")
        separated = board("4k3/8/8/8/8/3P4/4P3/4K3 w - - 0 1")
        self.assertLess(doubled_pawns(doubled), doubled_pawns(separated))

    def test_isolated_pawn_scores_below_supported_pawn(self):
        isolated = board("4k3/8/8/8/4P3/8/8/4K3 w - - 0 1")
        supported = board("4k3/8/8/8/3PP3/8/8/4K3 w - - 0 1")
        self.assertLess(isolated_pawns(isolated), isolated_pawns(supported))

    def test_backward_pawn_penalty_is_removed_by_neighbor_support(self):
        backward = board("4k3/8/2p5/8/3P4/8/8/4K3 w - - 0 1")
        supported = board("4k3/8/2p5/8/2PP4/8/8/4K3 w - - 0 1")
        self.assertLess(backward_pawns(backward), backward_pawns(supported))

    def test_passed_pawn_beats_blocked_and_bonus_grows_with_rank(self):
        blocked = board("k7/8/4p3/4P3/8/8/8/4K3 w - - 0 1")
        advanced = board("k7/8/8/4P3/8/8/8/4K3 w - - 0 1")
        farther_advanced = board("k7/4P3/8/8/8/8/8/4K3 w - - 0 1")
        self.assertGreater(passed_pawns(advanced), passed_pawns(blocked))
        self.assertGreater(passed_pawns(farther_advanced), passed_pawns(advanced))

    def test_protected_pawn_scores_higher_than_unprotected(self):
        unprotected = board("4k3/8/8/8/4P3/8/8/4K3 w - - 0 1")
        protected = board("4k3/8/8/8/4P3/3P4/8/4K3 w - - 0 1")
        self.assertGreater(protected_pawns(protected), protected_pawns(unprotected))

    def test_castled_king_scores_above_central_king_without_rights(self):
        castled = board("k2q4/8/8/8/8/8/PPPPPPPP/Q5K1 w - - 0 1")
        central = board("k2q4/8/8/8/8/8/PPPPPPPP/Q3K3 w - - 0 1")
        self.assertGreater(king_safety(castled), king_safety(central))

    def test_missing_shield_pawn_lowers_shield_score(self):
        intact = board("4k3/8/8/8/8/8/PPPPPPPP/6K1 w - - 0 1")
        missing = board("4k3/8/8/8/8/8/PPPP1PP1/6K1 w - - 0 1")
        self.assertLess(pawn_shields(missing), pawn_shields(intact))

    def test_bishop_pair_beats_bishop_and_knight(self):
        pair = board("2b1k1n1/8/8/8/8/8/8/2B1KB2 w - - 0 1")
        mixed = board("2b1k1n1/8/8/8/8/8/8/2B1KN2 w - - 0 1")
        self.assertGreater(bishop_pair(pair), bishop_pair(mixed))

    def test_rook_on_open_file_beats_rook_on_closed_file(self):
        open_file = board("4k3/8/8/8/8/8/8/R3K3 w - - 0 1")
        closed_file = board("4k3/8/8/8/8/8/P7/R3K3 w - - 0 1")
        self.assertGreater(rook_file_score(open_file), rook_file_score(closed_file))

    def test_defended_piece_scores_above_hanging_piece(self):
        hanging = board("4r1k1/8/8/8/4N3/8/8/4K3 w - - 0 1")
        defended = board("4r1k1/8/8/8/4N3/3P4/8/4K3 w - - 0 1")
        self.assertGreater(piece_protection(defended), piece_protection(hanging))

    def test_central_knight_scores_above_rim_knight(self):
        central = board("4k3/8/8/8/3N4/8/8/4K3 w - - 0 1")
        rim = board("4k3/8/8/8/8/8/8/N3K3 w - - 0 1")
        self.assertGreater(piece_square_score(central), piece_square_score(rim))

    def test_king_square_table_tapers_from_corner_to_centre(self):
        endgame_center = board("4k3/8/8/8/4K3/8/P6p/8 w - - 0 1")
        endgame_corner = board("4k3/8/8/8/8/8/P6p/K7 w - - 0 1")
        middlegame_center = board("q2rk1r1/8/8/8/4K3/8/8/3QRR2 w - - 0 1")
        middlegame_corner = board("q2rk1r1/8/8/8/8/8/8/K2QRR2 w - - 0 1")
        self.assertGreater(piece_square_score(endgame_center), piece_square_score(endgame_corner))
        self.assertGreater(piece_square_score(middlegame_corner), piece_square_score(middlegame_center))

    def test_phase_extremes(self):
        self.assertEqual(game_phase(chess.Board()), 24)
        self.assertEqual(game_phase(board("4k3/pp6/8/8/8/8/PP6/4K3 w - - 0 1")), 0)

    def test_claimable_threefold_repetition_is_terminal_to_search(self):
        repeated = board("4k3/3r1q2/p3p3/2p5/2B5/4P2Q/PPP3PP/1K3R2 w - - 5 34")
        cycle = ("h3h8", "e8e7", "h8h4", "e7e8")
        for move in cycle:
            repeated.push_uci(move)
        self.assertIsNone(terminal_score(repeated, 0))
        for move in ("h4h8", "e8e7", "h8h4", "e7e8"):
            repeated.push_uci(move)
        self.assertTrue(repeated.is_repetition(2))
        self.assertFalse(repeated.is_repetition(3))
        self.assertTrue(repeated.can_claim_threefold_repetition())
        self.assertEqual(terminal_score(repeated, 0), 0)

    def test_winning_structure_agent_breaks_repetition_cycle(self):
        position = board("4k3/3r1q2/p3p3/2p5/2B5/4P2Q/PPP3PP/1K3R2 w - - 5 34")
        for move in ("h3h8", "e8e7", "h8h4", "e7e8", "h4h8", "e8e7"):
            position.push_uci(move)
        self.assertTrue(position.is_repetition(2))
        self.assertFalse(position.can_claim_threefold_repetition())

        agent = create_agent("structure", depth=3, seed=1)
        self.assertNotEqual(agent.choose_move(position).move, chess.Move.from_uci("h8h4"))

    def test_each_scoring_feature_is_mirror_symmetric(self):
        features = (
            piece_square_score, doubled_pawns, isolated_pawns, backward_pawns,
            passed_pawns, protected_pawns, safe_king_corners, pawn_shields,
            open_king_files, central_king_penalty, king_safety,
            piece_protection, bishop_pair, rook_file_score, evaluate,
        )
        positions = (
            board("r2q1rk1/ppp2ppp/2np1n2/2b1p1B1/2B1P1b1/2NP1N2/PPP2PPP/R2Q1RK1 w - - 0 8"),
            board("8/P6k/8/8/8/8/p6K/8 w - - 0 1"),
        )
        for feature in features:
            for position in positions:
                with self.subTest(feature=feature.__name__, fen=position.fen()):
                    self.assertAlmostEqual(
                        feature(position), -feature(position.mirror()), places=9
                    )


if __name__ == "__main__":
    unittest.main()
