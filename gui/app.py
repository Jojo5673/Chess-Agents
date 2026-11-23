"""
Main window and controller.

Threading rule: the only code that changes `self.game` runs on the Tk thread
(human moves, AgentRunner.poll, undo). Agent searches run in AgentRunner's
worker thread on a board copy. Nothing keeps a reference to `game.board`;
every redraw reads it fresh.
"""
from __future__ import annotations

import time
import tkinter as tk
from typing import Optional

import chess

from agents import create_agent
from engine.agent import HumanPlayer, Player
from engine.game import Game, MoveRecord

from . import theme
from .board_view import BoardView
from .config import GameConfig, SideConfig
from .eval_bar import EVAL_WIDTH, EvalBar
from .player_bar import BAR_HEIGHT, PlayerBar
from .runner import AgentRunner
from .setup_panel import SetupPanel, time_label
from .side_panel import DEFAULT_DELAY_MS, GamePanel

TICK_MS = 40
PANEL_WIDTH = 360
GAP = 6


def _pretty(termination: str) -> str:
    return termination.replace("_", " ").replace("seventyfive", "75-move rule").strip()


class ChessApp:
    def __init__(self, root: tk.Tk, config: Optional[GameConfig] = None, *,
                 board: Optional[chess.Board] = None):
        self.root = root
        root.title("Chess Agents")
        root.configure(bg=theme.BG)
        root.geometry("1120x780")
        root.minsize(900, 640)

        self.game: Optional[Game] = None
        self.config: Optional[GameConfig] = None
        self.runner = AgentRunner()
        self.autoplay = False
        self.delay_ms = DEFAULT_DELAY_MS
        self.resigned: Optional[chess.Color] = None
        self.last_move_at = 0.0
        self.error: Optional[str] = None
        self._over_announced = False
        self._tick_id = None

        self._build()
        self._bind_keys()
        if config is not None:
            self.new_game(config, board=board)
        else:
            self.show_setup()
        self._tick_id = root.after(TICK_MS, self._tick)
        root.protocol("WM_DELETE_WINDOW", self.close)

    # ---- layout ------------------------------------------------------------
    def _build(self):
        self.side = tk.Frame(self.root, bg=theme.PANEL, width=PANEL_WIDTH)
        self.side.pack(side="right", fill="y")
        self.side.pack_propagate(False)

        self.area = tk.Frame(self.root, bg=theme.BG)
        self.area.pack(side="left", fill="both", expand=True)
        self.top_bar = PlayerBar(self.area)
        self.bottom_bar = PlayerBar(self.area)
        self.eval_bar = EvalBar(self.area)
        self.board_view = BoardView(self.area, get_game=lambda: self.game,
                                    can_move=self.human_can_move, on_move=self.on_board_move)
        self.area.bind("<Configure>", self._layout)

        self.game_panel = GamePanel(
            self.side, on_new_game=self.show_setup, on_undo=self.undo, on_flip=self.flip,
            on_resign=self.resign, on_step=self.step, on_toggle_autoplay=self.toggle_autoplay,
            on_delay=self.set_delay, on_difficulty=self.set_difficulty)
        self.setup_panel = SetupPanel(self.side, on_start=self.new_game,
                                      on_back=self.show_game_panel)
        self._layout()

    def _layout(self, event=None):
        """Keep the board square and as large as the area allows (place = no feedback loops)."""
        w = self.area.winfo_width() if self.area.winfo_width() > 1 else 760
        h = self.area.winfo_height() if self.area.winfo_height() > 1 else 780
        margin = 18
        size = min(w - 2 * margin - EVAL_WIDTH - GAP, h - 2 * margin - 2 * (BAR_HEIGHT + GAP))
        size = max(240, size // 8 * 8)
        total_w = EVAL_WIDTH + GAP + size
        x0 = max(margin, (w - total_w) // 2)
        y0 = max(margin, (h - size - 2 * (BAR_HEIGHT + GAP)) // 2)
        bx = x0 + EVAL_WIDTH + GAP
        self.top_bar.place(x=bx, y=y0, width=size, height=BAR_HEIGHT)
        by = y0 + BAR_HEIGHT + GAP
        self.eval_bar.place(x=x0, y=by, width=EVAL_WIDTH, height=size)
        self.board_view.place(x=bx, y=by, width=size, height=size)
        self.board_view.config(width=size, height=size)
        self.eval_bar.config(height=size)
        self.bottom_bar.place(x=bx, y=by + size + GAP, width=size, height=BAR_HEIGHT)

    def _bind_keys(self):
        r = self.root
        r.bind("<Control-n>", lambda e: self.show_setup())
        r.bind("<Control-z>", lambda e: self.undo())
        r.bind("<Key-f>", lambda e: self.flip())
        r.bind("<space>", lambda e: self.toggle_autoplay())
        r.bind("<Right>", lambda e: self.step())
        r.bind("<Escape>", lambda e: self._escape())

    def _escape(self):
        if self.board_view.promotion_pending:
            self.board_view.choose_promotion(None)
        elif self.board_view.banner_visible:
            self.board_view.hide_banner()
        else:
            self.board_view.clear_selection()
            self.board_view.redraw()

    # ---- panels ------------------------------------------------------------
    def show_setup(self):
        self.autoplay = False
        self.game_panel.pack_forget()
        self.setup_panel.set_back_enabled(self.game is not None)
        self.setup_panel.pack(fill="both", expand=True)
        self.refresh()

    def show_game_panel(self):
        if self.game is None:
            return
        self.setup_panel.pack_forget()
        self.game_panel.pack(fill="both", expand=True)
        self.refresh()

    @property
    def setup_visible(self) -> bool:
        return bool(self.setup_panel.winfo_manager())

    # ---- game lifecycle ----------------------------------------------------
    def _make_player(self, side: SideConfig) -> Player:
        if side.is_human:
            return HumanPlayer("You")
        return create_agent(side.agent_key, depth=side.depth, time_limit_s=side.time_limit_s)

    def new_game(self, config: GameConfig, *, board: Optional[chess.Board] = None):
        self.runner.cancel()
        self.config = config
        self.game = Game(self._make_player(config.white), self._make_player(config.black),
                         board=board)
        self.resigned = None
        self.autoplay = False
        self.error = None
        self._over_announced = False
        self.last_move_at = time.monotonic()
        self.board_view.clear_selection()
        self.board_view.hide_banner()
        self.board_view.cancel_promotion()
        self.board_view.white_bottom = config.human_color != chess.BLACK
        self.game_panel.configure_for_game(self.game, agent_vs_agent=self.agent_vs_agent)
        self.show_game_panel()

    @property
    def agent_vs_agent(self) -> bool:
        return self.config is not None and self.config.mode == "ava"

    @property
    def is_over(self) -> bool:
        return self.game is not None and (self.game.is_over or self.resigned is not None)

    def human_can_move(self) -> bool:
        return (self.game is not None and not self.is_over and self.game.is_human_turn
                and not self.runner.busy and not self.board_view.promotion_pending)

    # ---- human input ---------------------------------------------------------
    def on_board_move(self, from_sq: chess.Square, to_sq: chess.Square):
        """Called by the board view with a legal from/to pair."""
        if not self.human_can_move():
            return
        game = self.game
        if game.is_promotion(from_sq, to_sq):
            color = game.board.turn

            def chosen(piece_type):
                if piece_type is not None and self.game is game and self.human_can_move():
                    self._play_human(game.move_from_squares(from_sq, to_sq, piece_type))
                else:
                    self.refresh()
            self.board_view.ask_promotion(to_sq, color, chosen)
            return
        self._play_human(game.move_from_squares(from_sq, to_sq))

    def _play_human(self, move: Optional[chess.Move]):
        if move is None:
            self.refresh()
            return
        self.game.play_move(move)
        self.last_move_at = time.monotonic()
        self.refresh()

    # ---- controls --------------------------------------------------------------
    def undo(self):
        game = self.game
        if game is None or not game.history:
            return
        self.runner.cancel()
        self.autoplay = False
        self.resigned = None
        self.error = None
        self.board_view.cancel_promotion()
        self.board_view.clear_selection()
        self.board_view.hide_banner()
        self._over_announced = False
        if self.agent_vs_agent:
            game.undo()
        else:
            # Take back to the human's previous turn (usually the human's move + the reply).
            game.undo()
            while game.history and not game.current_player.is_human:
                game.undo()
        self.last_move_at = time.monotonic()
        self.refresh()

    def flip(self):
        self.board_view.white_bottom = not self.board_view.white_bottom
        self.refresh()

    def resign(self):
        if self.game is None or self.is_over or self.agent_vs_agent:
            return
        self.runner.cancel()
        self.resigned = self.config.human_color
        self.refresh()

    def step(self):
        if (self.game is None or not self.agent_vs_agent or self.is_over
                or self.runner.busy or self.setup_visible):
            return
        self.autoplay = False
        self.runner.start(self.game)
        self.refresh()

    def toggle_autoplay(self):
        if self.game is None or not self.agent_vs_agent or self.is_over:
            return
        self.autoplay = not self.autoplay
        self.last_move_at = 0.0               # first auto move starts right away
        self.refresh()

    def set_delay(self, ms: int):
        self.delay_ms = int(ms)

    def set_difficulty(self, color: chess.Color, what: str, value):
        """Bound to the difficulty pills; takes effect on that agent's next search."""
        if self.game is None:
            return
        agent = self.game.white if color == chess.WHITE else self.game.black
        side = self.config.side(color)
        if what == "depth":
            agent.depth = side.depth = int(value)
        else:
            agent.time_limit_s = side.time_limit_s = float(value)
        self.refresh()

    def close(self):
        self.runner.cancel()
        if self._tick_id is not None:
            try:
                self.root.after_cancel(self._tick_id)
            except tk.TclError:
                pass
            self._tick_id = None
        self.root.destroy()

    # ---- the timer loop ------------------------------------------------------
    def _tick(self):
        self._tick_id = None
        try:
            self.tick()
        finally:
            try:
                self._tick_id = self.root.after(TICK_MS, self._tick)
            except tk.TclError:                    # window already destroyed
                self._tick_id = None

    def tick(self) -> Optional[MoveRecord]:
        """One scheduler step (public so tests can drive it without mainloop)."""
        record = None
        if self.game is not None:
            try:
                record = self.runner.poll(self.game)
            except Exception as exc:  # an agent crashed: stop instead of looping
                self.autoplay = False
                self.error = f"{type(exc).__name__}: {exc}"
            if record is not None:
                self.last_move_at = time.monotonic()
                self.refresh()
            self._maybe_start_agent()
            if self.runner.busy:
                self._refresh_thinking()
        return record

    def _maybe_start_agent(self):
        game = self.game
        if (game is None or self.is_over or self.runner.busy or self.error
                or not game.is_agent_turn or self.setup_visible
                or self.board_view.promotion_pending):
            return
        if self.agent_vs_agent:
            if not self.autoplay:
                return
            if (time.monotonic() - self.last_move_at) * 1000 < self.delay_ms:
                return
        self.runner.start(game)
        self.refresh()

    # ---- drawing ---------------------------------------------------------------
    def _thinking_text(self) -> str:
        if self.error:
            return f"Agent error: {self.error}"
        agent = self.runner.agent
        if not self.runner.busy or agent is None:
            return ""
        depth = getattr(agent, "depth", 0)
        limit = getattr(agent, "time_limit_s", None)
        cap = f" (depth ≤ {depth}, ≤ {time_label(limit)})" if depth else ""
        return f"{agent.name} is thinking… {self.runner.elapsed:.1f}s{cap}"

    def _refresh_thinking(self):
        self.game_panel.thinking.config(text=self._thinking_text())

    def _status_text(self) -> str:
        game = self.game
        if self.resigned is not None:
            loser = "White" if self.resigned == chess.WHITE else "Black"
            return f"{loser} resigned. {self._result_string()}"
        return game.status_text()

    def _result_string(self) -> str:
        if self.resigned is not None:
            return "0-1" if self.resigned == chess.WHITE else "1-0"
        return self.game.result if self.game.is_over else ""

    def _winner(self) -> Optional[chess.Color]:
        if self.resigned is not None:
            return not self.resigned
        return self.game.winner

    def _player_detail(self, player: Player) -> str:
        if player.is_human:
            return ""
        depth = getattr(player, "depth", 0)
        if not depth:
            return "random"
        return f"depth {depth} · {time_label(player.time_limit_s)}"

    def refresh(self):
        game = self.game
        self.board_view.redraw()
        if game is None:
            self.eval_bar.set(None, True)
            return
        board = game.board
        white_bottom = self.board_view.white_bottom
        over = self.is_over
        result = self._result_string()

        last_eval = next((r.score for r in reversed(game.history)
                          if r.source == "agent" and r.depth), None)
        self.eval_bar.set(last_eval, white_bottom)

        for bar, color in ((self.bottom_bar, chess.WHITE if white_bottom else chess.BLACK),
                           (self.top_bar, chess.BLACK if white_bottom else chess.WHITE)):
            player = game.white if color == chess.WHITE else game.black
            side_result = ""
            if over:
                winner = self._winner()
                side_result = "½" if winner is None else ("Won" if winner == color
                                                              else "Lost")
            thinking = self.runner.busy and self.runner.agent is player
            bar.update_bar(board, color, player.name, self._player_detail(player),
                           to_move=not over and board.turn == color, thinking=thinking,
                           is_human=player.is_human, result=side_result)

        self.game_panel.update_view(
            game, status=self._status_text(), over=over, thinking=self._thinking_text(),
            autoplay=self.autoplay, can_step=(self.agent_vs_agent and not over
                                              and not self.runner.busy),
            can_undo=bool(game.history), result=result)

        if over and not self._over_announced:
            self._over_announced = True
            self.autoplay = False
            self._announce_result()

    def _announce_result(self):
        game = self.game
        winner = self._winner()
        human = self.config.human_color
        if winner is None:
            title = "Draw"
        elif human is None:
            title = f"{'White' if winner == chess.WHITE else 'Black'} wins"
        else:
            winner_name = (game.white if winner == chess.WHITE else game.black).name
            title = "You won!" if winner == human else f"{winner_name} won"
        how = "resignation" if self.resigned is not None else _pretty(game.termination)
        subtitle = f"{self._result_string()}  ·  by {how}"
        self.board_view.show_banner(title, subtitle, [
            ("New Game", self._banner_new_game),
            ("Review", self.board_view.hide_banner),
        ])

    def _banner_new_game(self):
        self.board_view.hide_banner()
        self.show_setup()


def main():
    try:
        from ctypes import windll                 # crisp rendering on high-DPI Windows
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    ChessApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
