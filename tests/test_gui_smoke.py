"""
Headless-ish smoke test for the tkinter GUI: builds the app with the window
withdrawn, drives it through its public methods (no mainloop), and checks that
human moves, promotion, agent moves via the worker thread, agent-vs-agent
stepping/auto-play, undo and resign all work. Skipped when Tk has no display.
"""
import time
import unittest

import chess

try:
    import tkinter as tk
except ImportError:  # pragma: no cover
    tk = None


def make_root():
    if tk is None:
        raise unittest.SkipTest("tkinter not available")
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # no display
        raise unittest.SkipTest(f"Tk unavailable: {exc}")
    root.withdraw()
    return root


class GuiSmokeTest(unittest.TestCase):
    def setUp(self):
        from gui.app import ChessApp
        from gui.config import GameConfig, SideConfig
        self.GameConfig, self.SideConfig = GameConfig, SideConfig
        self.root = make_root()
        self.app = ChessApp(self.root)            # starts on the setup panel

    def tearDown(self):
        self.app.close()                          # cancels the timer, destroys the root

    def pump_until(self, predicate, timeout=20.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.app.tick()
            self.root.update()
            if predicate():
                return True
            time.sleep(0.01)
        self.fail("timed out waiting for the GUI")

    def human_vs(self, agent_key="random", human=chess.WHITE, board=None):
        agent = self.SideConfig(agent_key, depth=1, time_limit_s=1.0)
        you = self.SideConfig(None)
        cfg = (self.GameConfig(you, agent) if human == chess.WHITE
               else self.GameConfig(agent, you))
        self.app.new_game(cfg, board=board)
        return self.app.game

    def test_setup_panel_lists_registered_agents(self):
        from agents import available_agents
        keys = [v for v, _ in self.app.setup_panel.opponent.agent._pills]
        self.assertEqual(keys, [s.key for s in available_agents()])
        cfg = self.app.setup_panel.config_from_ui()
        self.assertEqual(cfg.mode, "hva")
        self.assertIsNotNone(cfg.human_color)

    def test_human_move_then_agent_reply(self):
        game = self.human_vs("material")
        self.assertTrue(self.app.human_can_move())
        self.app.on_board_move(chess.E2, chess.E4)
        self.assertEqual(game.history[0].san, "e4")
        self.pump_until(lambda: len(game.history) == 2)
        self.assertEqual(game.history[1].source, "agent")
        self.assertTrue(self.app.human_can_move())
        self.assertIs(self.app.game.board, game.board)

    def test_human_as_black_agent_moves_first_and_board_flips(self):
        game = self.human_vs("random", human=chess.BLACK)
        self.assertFalse(self.app.board_view.white_bottom)
        self.pump_until(lambda: len(game.history) == 1)
        self.assertTrue(game.is_human_turn)

    def test_promotion_chooser(self):
        board = chess.Board("8/P5k1/8/8/8/8/5PPP/6K1 w - - 0 1")
        game = self.human_vs("random", board=board)
        self.app.on_board_move(chess.A7, chess.A8)
        self.assertTrue(self.app.board_view.promotion_pending)
        self.assertEqual(len(game.history), 0)
        self.app.board_view.choose_promotion(chess.KNIGHT)
        self.assertEqual(game.history[0].uci, "a7a8n")

    def test_undo_returns_to_human_turn(self):
        game = self.human_vs("random")
        self.app.on_board_move(chess.E2, chess.E4)
        self.pump_until(lambda: len(game.history) == 2)
        self.app.undo()
        self.assertEqual(len(game.history), 0)
        self.assertTrue(game.is_human_turn)

    def test_resign_ends_game(self):
        game = self.human_vs("random")
        self.app.resign()
        self.assertTrue(self.app.is_over)
        self.assertTrue(self.app.board_view.banner_visible)
        self.assertEqual(self.app._result_string(), "0-1")
        self.assertFalse(self.app.human_can_move())

    def _finished_game(self):
        """Human (White) mates the random agent in a fixed mate-in-one position."""
        board = chess.Board("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1")
        game = self.human_vs("random", board=board)
        self.app.on_board_move(chess.A1, chess.A8)          # Ra8#
        self.assertTrue(self.app.is_over)
        return game

    def test_undo_disabled_after_game_over(self):
        game = self._finished_game()
        self.app.board_view.hide_banner()                     # "Review"
        self.app.undo()
        self.assertEqual(len(game.history), 1)
        self.assertTrue(self.app.is_over)
        self.assertFalse(self.app.game_panel.undo_button.enabled)

    def test_undo_disabled_after_resign(self):
        game = self.human_vs("random")
        self.app.on_board_move(chess.E2, chess.E4)
        self.pump_until(lambda: len(game.history) == 2)
        self.app.resign()
        self.app.undo()
        self.assertTrue(self.app.is_over)
        self.assertEqual(len(game.history), 2)

    def test_arrow_keys_review_finished_game(self):
        game = self._finished_game()
        final_fen = game.board.fen()
        start_fen = chess.Board("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1").fen()
        self.app.review_step(-1)                              # Left
        self.assertFalse(self.app.board_view.banner_visible)
        self.assertEqual(self.app.view_ply, 0)
        self.assertEqual(self.app.board_view.display_board.fen(), start_fen)
        self.assertEqual(game.board.fen(), final_fen)         # the game itself is untouched
        self.app.review_step(-1)                              # clamps at the start
        self.assertEqual(self.app.view_ply, 0)
        self.app._right_key()                                 # Right
        self.assertIsNone(self.app.view_ply)
        self.assertIsNone(self.app.board_view.display_board)
        self.app.review_to(0)                                 # Home
        self.app.review_to(None)                              # End
        self.assertIsNone(self.app.view_ply)

    def test_review_keys_ignored_during_play(self):
        self.human_vs("random")
        self.app.review_step(-1)
        self.assertIsNone(self.app.view_ply)

    def test_agent_vs_agent_step_and_autoplay(self):
        cfg = self.GameConfig(self.SideConfig("material", 1, 1.0),
                              self.SideConfig("random", 1, 1.0))
        self.app.new_game(cfg)
        game = self.app.game
        self.app.step()
        self.pump_until(lambda: len(game.history) == 1)
        self.assertEqual(game.history[0].depth, 1)
        # Difficulty pills write straight through to the agent.
        self.app.set_difficulty(chess.WHITE, "depth", 2)
        self.app.set_difficulty(chess.WHITE, "time", 3.0)
        self.assertEqual((game.white.depth, game.white.time_limit_s), (2, 3.0))
        self.app.set_delay(0)
        self.app.toggle_autoplay()
        self.pump_until(lambda: len(game.history) >= 4)
        self.app.toggle_autoplay()
        self.assertFalse(self.app.autoplay)

    def test_stale_search_result_is_discarded(self):
        cfg = self.GameConfig(self.SideConfig("random", 1, 1.0),
                              self.SideConfig("random", 1, 1.0))
        self.app.new_game(cfg)
        game = self.app.game
        self.app.step()
        self.app.runner.cancel()                   # e.g. user pressed Undo / New Game
        time.sleep(0.2)
        self.assertIsNone(self.app.runner.poll(game))
        self.assertEqual(len(game.history), 0)

    def test_board_square_mapping_respects_orientation(self):
        view = self.app.board_view
        view.config(width=400, height=400)
        sq = view.sq
        view.white_bottom = True
        self.assertEqual(view.square_at(1, 8 * sq - 1), chess.A1)
        self.assertEqual(view.square_origin(chess.H8), (7 * sq, 0))
        view.white_bottom = False
        self.assertEqual(view.square_at(1, 8 * sq - 1), chess.H8)
        self.assertEqual(view.square_origin(chess.A1), (7 * sq, 0))


if __name__ == "__main__":
    unittest.main()
