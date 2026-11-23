"""Right-hand game panel: status, search info, move list, playback and difficulty controls."""
from __future__ import annotations

import tkinter as tk
from typing import Callable, Dict, List, Optional

import chess

from engine.game import Game, MoveRecord

from . import theme
from .config import DEPTH_CHOICES, TIME_CHOICES, clamp_depth
from .eval_bar import format_score
from .setup_panel import section_label, time_label
from .widgets import FlatButton, PillGroup

DELAY_CHOICES = ((0, "0s"), (250, "¼s"), (500, "½s"), (1000, "1s"), (2000, "2s"))
DEFAULT_DELAY_MS = 500


def describe_search(rec: Optional[MoveRecord]) -> str:
    if rec is None:
        return "—"
    dot = "  ·  "
    if not rec.depth:
        return f"{rec.san}{dot}no search"
    return (f"{rec.san}{dot}{format_score(rec.score)}{dot}depth {rec.depth}{dot}"
            f"{rec.nodes:,} nodes{dot}{rec.time_s:.2f}s")


def side_name(color: chess.Color) -> str:
    return "White" if color == chess.WHITE else "Black"


class GamePanel(tk.Frame):
    def __init__(self, master, *, on_new_game: Callable, on_undo: Callable, on_flip: Callable,
                 on_resign: Callable, on_step: Callable, on_toggle_autoplay: Callable,
                 on_delay: Callable[[int], None],
                 on_difficulty: Callable[[chess.Color, str, float], None]):
        super().__init__(master, bg=theme.PANEL)
        self.on_difficulty = on_difficulty

        # Header + status.
        self.title = tk.Label(self, text="", bg=theme.PANEL, fg=theme.TEXT, anchor="w",
                              font=theme.ui_font(14, "bold"))
        self.title.pack(fill="x", padx=16, pady=(14, 0))
        self.status = tk.Label(self, text="", bg=theme.PANEL, fg=theme.MUTED, anchor="w",
                               font=theme.ui_font(10), justify="left", wraplength=300)
        self.status.pack(fill="x", padx=16, pady=(2, 8))

        # Bottom action bar (packed first so it keeps its space).
        actions = tk.Frame(self, bg=theme.PANEL)
        actions.pack(side="bottom", fill="x", padx=12, pady=12)
        self.new_button = FlatButton(actions, "➕ New", on_new_game, style="primary")
        self.undo_button = FlatButton(actions, "↶ Undo", on_undo)
        self.flip_button = FlatButton(actions, "⇅ Flip", on_flip)
        self.resign_button = FlatButton(actions, "⚑ Resign", on_resign)
        for i, b in enumerate((self.new_button, self.undo_button, self.flip_button,
                               self.resign_button)):
            b.config(padx=4)
            b.grid(row=0, column=i, sticky="ew", padx=2)
            actions.grid_columnconfigure(i, weight=1, uniform="act")

        # Difficulty (one row group per agent), above the actions.
        self.difficulty = tk.Frame(self, bg=theme.PANEL)
        self.difficulty.pack(side="bottom", fill="x", padx=14, pady=(4, 0))

        # Agent-vs-agent playback controls.
        self.playback = tk.Frame(self, bg=theme.PANEL)
        row = tk.Frame(self.playback, bg=theme.PANEL)
        row.pack(fill="x")
        self.step_button = FlatButton(row, "⏭ Step", on_step)
        self.step_button.pack(side="left", fill="x", expand=True, padx=(0, 2))
        self.play_button = FlatButton(row, "▶ Auto-play", on_toggle_autoplay,
                                      style="primary")
        self.play_button.pack(side="left", fill="x", expand=True, padx=(2, 0))
        row = tk.Frame(self.playback, bg=theme.PANEL)
        row.pack(fill="x", pady=(6, 0))
        tk.Label(row, text="Delay", width=6, anchor="w", bg=theme.PANEL, fg=theme.TEXT,
                 font=theme.ui_font(9)).pack(side="left")
        self.delay = PillGroup(row, DELAY_CHOICES, DEFAULT_DELAY_MS, on_change=on_delay, pady=3)
        self.delay.pack(side="left", fill="x", expand=True)

        # Search info card.
        card = tk.Frame(self, bg=theme.CARD)
        card.pack(fill="x", padx=14, pady=(0, 8))
        self.search_lines: Dict[chess.Color, tk.Label] = {}
        for color in (chess.WHITE, chess.BLACK):
            line = tk.Label(card, text="", bg=theme.CARD, fg=theme.TEXT, anchor="w",
                            font=theme.ui_font(9), justify="left", wraplength=300)
            line.pack(fill="x", padx=10, pady=(6 if color == chess.WHITE else 0, 2))
            self.search_lines[color] = line
        self.thinking = tk.Label(card, text="", bg=theme.CARD, fg=theme.ACCENT, anchor="w",
                                 font=theme.ui_font(9, "bold"))
        self.thinking.pack(fill="x", padx=10, pady=(0, 6))

        # Move list.
        section_label(self, "Moves").pack(fill="x", padx=16)
        frame = tk.Frame(self, bg=theme.CARD)
        frame.pack(fill="both", expand=True, padx=14, pady=(3, 8))
        self.moves = tk.Text(frame, bg=theme.CARD, fg=theme.TEXT, bd=0, highlightthickness=0,
                             font=theme.ui_font(10), wrap="none", cursor="arrow",
                             tabs=(44, 140), padx=8, pady=4, height=8, width=30,
                             spacing1=3, spacing3=3)
        scroll = tk.Scrollbar(frame, command=self.moves.yview, width=10)
        self.moves.config(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.moves.pack(side="left", fill="both", expand=True)
        self.moves.tag_config("num", foreground=theme.FAINT)
        self.moves.tag_config("alt", background=theme.CARD_ALT)
        self.moves.tag_config("last", background=theme.ACCENT_DARK, foreground="#ffffff",
                              font=theme.ui_font(10, "bold"))
        self.moves.tag_config("result", foreground=theme.ACCENT, font=theme.ui_font(10, "bold"))
        self.moves.config(state="disabled")
        self._move_count = None
        self._resign_allowed = True

    # ---- set up for a new game -------------------------------------------
    def configure_for_game(self, game: Game, *, agent_vs_agent: bool):
        self._move_count = None
        if agent_vs_agent:
            self.title.config(text=f"{game.white.name} vs {game.black.name}")
            self.playback.pack(side="bottom", fill="x", padx=14, pady=(4, 4),
                               before=self.difficulty)
        else:
            agent = game.black if game.white.is_human else game.white
            self.title.config(text=f"You vs {agent.name}")
            self.playback.pack_forget()
        self._resign_allowed = not agent_vs_agent
        self.resign_button.set_enabled(self._resign_allowed)

        for child in self.difficulty.winfo_children():
            child.destroy()
        section_label(self.difficulty, "Difficulty").pack(fill="x", pady=(0, 2))
        for color in (chess.WHITE, chess.BLACK):
            player = game.white if color == chess.WHITE else game.black
            if player.is_human:
                continue
            self._difficulty_rows(color, player)

    def _difficulty_rows(self, color, agent):
        searches = getattr(agent, "depth", 0) > 0
        box = tk.Frame(self.difficulty, bg=theme.PANEL)
        box.pack(fill="x", pady=(2, 4))
        tk.Label(box, text=f"{agent.name} ({side_name(color)})", bg=theme.PANEL, fg=theme.TEXT,
                 anchor="w", font=theme.ui_font(9, "bold")).pack(fill="x")
        if not searches:
            tk.Label(box, text="Plays random moves: no depth or time setting.",
                     bg=theme.PANEL, fg=theme.MUTED, anchor="w",
                     font=theme.ui_font(9)).pack(fill="x")
            return
        row = tk.Frame(box, bg=theme.PANEL)
        row.pack(fill="x")
        tk.Label(row, text="Depth", width=6, anchor="w", bg=theme.PANEL, fg=theme.MUTED,
                 font=theme.ui_font(9)).pack(side="left")
        PillGroup(row, [(d, str(d)) for d in DEPTH_CHOICES], clamp_depth(agent.depth), pady=2,
                  on_change=lambda v, c=color: self.on_difficulty(c, "depth", v)
                  ).pack(side="left", fill="x", expand=True)
        row = tk.Frame(box, bg=theme.PANEL)
        row.pack(fill="x")
        tk.Label(row, text="Think", width=6, anchor="w", bg=theme.PANEL, fg=theme.MUTED,
                 font=theme.ui_font(9)).pack(side="left")
        current = agent.time_limit_s if agent.time_limit_s in TIME_CHOICES else TIME_CHOICES[2]
        PillGroup(row, [(t, time_label(t)) for t in TIME_CHOICES], current, pady=2,
                  on_change=lambda v, c=color: self.on_difficulty(c, "time", v)
                  ).pack(side="left", fill="x", expand=True)

    # ---- refresh -----------------------------------------------------------
    def update_view(self, game: Game, *, status: str, over: bool, thinking: str,
                    autoplay: bool, can_step: bool, can_undo: bool, result: str,
                    current_ply: Optional[int] = None):
        self.status.config(text=status,
                           fg=theme.ACCENT if over or game.board.is_check() else theme.MUTED)
        for color in (chess.WHITE, chess.BLACK):
            player = game.white if color == chess.WHITE else game.black
            last = next((r for r in reversed(game.history)
                         if r.color == ("white" if color == chess.WHITE else "black")
                         and r.source == "agent"), None)
            label = f"{side_name(color)} · {player.name}:  "
            if player.is_human:
                self.search_lines[color].config(text=label + "human player", fg=theme.MUTED)
            else:
                self.search_lines[color].config(text=label + describe_search(last),
                                                fg=theme.TEXT)
        self.thinking.config(text=thinking)
        self.play_button.config(text="⏸ Pause" if autoplay else "▶ Auto-play")
        self.play_button.set_enabled(not over)
        self.step_button.set_enabled(can_step)
        self.undo_button.set_enabled(can_undo)
        self.resign_button.set_enabled(self._resign_allowed and not over)
        self._render_moves(game.history, result, current_ply)

    def _render_moves(self, history: List[MoveRecord], result: str,
                      current_ply: Optional[int] = None):
        # current_ply = number of moves shown on the board (None = all of them).
        shown = len(history) if current_ply is None else current_ply
        key = (len(history), result, history[-1].uci if history else None, shown)
        if key == self._move_count:
            return
        self._move_count = key
        t = self.moves
        t.config(state="normal")
        t.delete("1.0", "end")
        # A game can start with Black to move only from a custom position; handle it anyway.
        offset = 1 if history and history[0].color == "black" else 0
        plies = [None] * offset + list(history)
        for i in range(0, len(plies), 2):
            line_tags = ("alt",) if (i // 2) % 2 == 1 else ()
            t.insert("end", f"{i // 2 + 1}.", ("num",) + line_tags)
            for j in (0, 1):
                t.insert("end", "\t", line_tags)
                if i + j < len(plies) and plies[i + j] is not None:
                    is_current = i + j - offset == shown - 1
                    tags = line_tags + (("last", "current") if is_current else ())
                    t.insert("end", f" {plies[i + j].san} ", tags)
                elif i + j < len(plies):
                    t.insert("end", "...", line_tags)
            t.insert("end", "\n", line_tags)
        if result:
            t.insert("end", f"  {result}\n", ("result",))
        if current_ply is None or not t.tag_ranges("current"):
            t.see("end")
        else:
            t.see("current.first")
        t.config(state="disabled")
