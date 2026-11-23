"""Vertical evaluation bar beside the board (White's share grows from White's side)."""
from __future__ import annotations

import math
import tkinter as tk
from typing import Optional

from engine.evaluation import MATE_SCORE

from . import theme

EVAL_WIDTH = 22


def format_score(score: Optional[float]) -> str:
    """Centipawn score (White's perspective) as '+0.35', '-1.20', 'M3', '-M2'."""
    if score is None:
        return "—"
    if abs(score) >= MATE_SCORE - 1000:
        plies = int(MATE_SCORE - abs(score))
        moves = max(1, (plies + 1) // 2)
        return f"{'' if score > 0 else '-'}M{moves}"
    return f"{score / 100:+.2f}"


def white_share(score: Optional[float]) -> float:
    if score is None:
        return 0.5
    if abs(score) >= MATE_SCORE - 1000:
        return 1.0 if score > 0 else 0.0
    return 1 / (1 + math.exp(-score / 400))


class EvalBar(tk.Canvas):
    def __init__(self, master, height: int = 560):
        super().__init__(master, width=EVAL_WIDTH, height=height, bg=theme.EVAL_BLACK,
                         highlightthickness=0, bd=0)
        self.score: Optional[float] = None
        self.white_bottom = True
        self.bind("<Configure>", lambda e: self.redraw())

    def set(self, score: Optional[float], white_bottom: bool):
        self.score, self.white_bottom = score, white_bottom
        self.redraw()

    def redraw(self):
        self.delete("all")
        h = self.winfo_height() if self.winfo_height() > 1 else int(self["height"])
        w = EVAL_WIDTH
        share = white_share(self.score)
        white_h = h * share
        if self.white_bottom:
            self.create_rectangle(0, 0, w, h - white_h, fill=theme.EVAL_BLACK, width=0)
            self.create_rectangle(0, h - white_h, w, h, fill=theme.EVAL_WHITE, width=0)
        else:
            self.create_rectangle(0, 0, w, white_h, fill=theme.EVAL_WHITE, width=0)
            self.create_rectangle(0, white_h, w, h, fill=theme.EVAL_BLACK, width=0)
        self.create_line(0, h / 2, w, h / 2, fill=theme.ACCENT, width=1)
        if self.score is not None:
            text = format_score(self.score).lstrip("+-")
            if not text.startswith("M"):
                text = f"{abs(self.score) / 100:.1f}"
            white_ahead = share >= 0.5
            at_bottom = white_ahead == self.white_bottom
            y = h - 8 if at_bottom else 8
            self.create_text(w / 2, y, text=text, font=theme.ui_font(7, "bold"),
                             fill=theme.EVAL_BLACK if white_ahead else theme.EVAL_WHITE)
