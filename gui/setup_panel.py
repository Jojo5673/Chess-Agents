"""
New-game setup (shown in the right-hand panel, like chess.com's "Play" tab).

The agent lists come from `agents.available_agents()`, so newly registered
agents appear here automatically.
"""
from __future__ import annotations

import random
import tkinter as tk
from typing import Callable, List, Optional

from agents import AgentSpec, available_agents

from . import theme
from .config import (DEFAULT_TIME_LIMIT, DEPTH_CHOICES, TIME_CHOICES, GameConfig,
                     SideConfig, clamp_depth)
from .widgets import FlatButton, PillGroup


def time_label(seconds: float) -> str:
    return f"{seconds:g}s"


def section_label(master, text: str) -> tk.Label:
    return tk.Label(master, text=text.upper(), bg=theme.PANEL, fg=theme.MUTED,
                    font=theme.ui_font(8, "bold"), anchor="w")


class AgentChooser(tk.Frame):
    """Agent picker + depth + time limit for one side."""

    def __init__(self, master, specs: List[AgentSpec], default_key: str, title: str):
        super().__init__(master, bg=theme.PANEL)
        self.specs = {s.key: s for s in specs}
        section_label(self, title).pack(fill="x", pady=(0, 3))
        self.agent = PillGroup(self, [(s.key, s.name) for s in specs], default_key,
                               columns=min(3, len(specs)), on_change=self._on_agent)
        self.agent.pack(fill="x")
        self.description = tk.Label(self, text="", bg=theme.PANEL, fg=theme.MUTED,
                                    font=theme.ui_font(9), anchor="w", justify="left",
                                    wraplength=300)
        self.description.pack(fill="x", pady=(3, 6))
        row = tk.Frame(self, bg=theme.PANEL)
        row.pack(fill="x")
        tk.Label(row, text="Depth", width=6, anchor="w", bg=theme.PANEL, fg=theme.TEXT,
                 font=theme.ui_font(9)).pack(side="left")
        self.depth = PillGroup(row, [(d, str(d)) for d in DEPTH_CHOICES], 3, pady=3)
        self.depth.pack(side="left", fill="x", expand=True)
        row = tk.Frame(self, bg=theme.PANEL)
        row.pack(fill="x", pady=(2, 0))
        tk.Label(row, text="Think", width=6, anchor="w", bg=theme.PANEL, fg=theme.TEXT,
                 font=theme.ui_font(9)).pack(side="left")
        self.time = PillGroup(row, [(t, time_label(t)) for t in TIME_CHOICES],
                              DEFAULT_TIME_LIMIT, pady=3)
        self.time.pack(side="left", fill="x", expand=True)
        self._on_agent(default_key)

    def _on_agent(self, key):
        spec = self.specs[key]
        self.description.config(text=spec.description)
        searches = spec.default_depth > 0
        if searches:
            self.depth.select(clamp_depth(spec.default_depth))
        self.depth.set_enabled(searches)
        self.time.set_enabled(searches)

    def side_config(self) -> SideConfig:
        return SideConfig(self.agent.value, self.depth.value, self.time.value)


class SetupPanel(tk.Frame):
    def __init__(self, master, *, on_start: Callable[[GameConfig], None],
                 on_back: Optional[Callable[[], None]] = None):
        super().__init__(master, bg=theme.PANEL)
        self.on_start = on_start
        self.on_back = on_back
        specs = available_agents()
        searching = [s for s in specs if s.default_depth > 0]
        default = (searching[0] if searching else specs[0]).key
        second = (searching[1] if len(searching) > 1 else specs[0]).key

        header = tk.Frame(self, bg=theme.PANEL)
        header.pack(fill="x", padx=16, pady=(16, 8))
        tk.Label(header, text="♞  New Game", bg=theme.PANEL, fg=theme.TEXT,
                 font=theme.ui_font(15, "bold")).pack(side="left")
        self.back = FlatButton(header, "Back to game", self._back, style="ghost",
                               font=theme.ui_font(9, "bold"), padx=6, pady=3)

        self.mode = PillGroup(self, [("hva", "Play vs Agent"), ("ava", "Agent vs Agent")],
                              "hva", on_change=lambda v: self._show_mode(), pady=7)
        self.mode.pack(fill="x", padx=14, pady=(0, 10))

        # Human vs agent.
        self.hva = tk.Frame(self, bg=theme.PANEL)
        self.opponent = AgentChooser(self.hva, specs, default, "Opponent")
        self.opponent.pack(fill="x")
        section_label(self.hva, "Play as").pack(fill="x", pady=(12, 3))
        self.colour = PillGroup(self.hva, [("white", "♔ White"), ("random", "Random"),
                                           ("black", "♚ Black")], "white", pady=6)
        self.colour.pack(fill="x")

        # Agent vs agent.
        self.ava = tk.Frame(self, bg=theme.PANEL)
        self.white_agent = AgentChooser(self.ava, specs, default, "White")
        self.white_agent.pack(fill="x")
        tk.Frame(self.ava, bg=theme.BORDER, height=1).pack(fill="x", pady=10)
        self.black_agent = AgentChooser(self.ava, specs, second, "Black")
        self.black_agent.pack(fill="x")

        self.start_button = FlatButton(self, "Play", self.start, style="primary",
                                       font=theme.ui_font(13, "bold"), pady=10)
        self.start_button.pack(side="bottom", fill="x", padx=14, pady=16)
        self._show_mode()

    def set_back_enabled(self, enabled: bool):
        if enabled:
            self.back.pack(side="right")
        else:
            self.back.pack_forget()

    def _back(self):
        if self.on_back:
            self.on_back()

    def _show_mode(self):
        if self.mode.value == "hva":
            self.ava.pack_forget()
            self.hva.pack(fill="x", padx=14)
        else:
            self.hva.pack_forget()
            self.ava.pack(fill="x", padx=14)

    def config_from_ui(self) -> GameConfig:
        if self.mode.value == "ava":
            return GameConfig(self.white_agent.side_config(), self.black_agent.side_config())
        colour = self.colour.value
        if colour == "random":
            colour = random.choice(("white", "black"))
        agent = self.opponent.side_config()
        human = SideConfig(None)
        return GameConfig(human, agent) if colour == "white" else GameConfig(agent, human)

    def start(self):
        self.on_start(self.config_from_ui())
