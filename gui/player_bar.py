"""Player strip above/below the board: avatar, name, captured pieces, material, status."""
from __future__ import annotations

import tkinter as tk
from typing import Dict

import chess

from . import theme
from .widgets import draw_piece

BAR_HEIGHT = 46
_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
_START = {chess.PAWN: 8, chess.KNIGHT: 2, chess.BISHOP: 2, chess.ROOK: 2, chess.QUEEN: 1}
_ORDER = (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)


def captured_by(board: chess.Board, color: chess.Color) -> Dict[chess.PieceType, int]:
    """Opponent pieces `color` has captured (start count minus what is left)."""
    enemy = not color
    return {pt: max(0, _START[pt] - len(board.pieces(pt, enemy))) for pt in _ORDER}


def material_balance(board: chess.Board) -> int:
    """White material minus Black material, in pawns (1/3/3/5/9)."""
    return sum(v * (len(board.pieces(pt, chess.WHITE)) - len(board.pieces(pt, chess.BLACK)))
               for pt, v in _VALUES.items())


class PlayerBar(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg=theme.BG, height=BAR_HEIGHT)
        self.pack_propagate(False)
        self.avatar = tk.Canvas(self, width=36, height=36, bg=theme.BG, highlightthickness=0)
        self.avatar.pack(side="left", padx=(0, 10))
        info = tk.Frame(self, bg=theme.BG)
        info.pack(side="left", fill="y")
        top = tk.Frame(info, bg=theme.BG)
        top.pack(side="top", anchor="w")
        self.name = tk.Label(top, text="", bg=theme.BG, fg=theme.TEXT,
                             font=theme.ui_font(11, "bold"))
        self.name.pack(side="left")
        self.detail = tk.Label(top, text="", bg=theme.BG, fg=theme.MUTED, font=theme.ui_font(9))
        self.detail.pack(side="left", padx=(6, 0))
        self.captures = tk.Canvas(info, height=20, width=260, bg=theme.BG, highlightthickness=0)
        self.captures.pack(side="top", anchor="w", pady=(1, 0))
        self.status = tk.Label(self, text="", bg=theme.BG, fg=theme.MUTED, width=12,
                               font=theme.ui_font(10, "bold"), padx=10, pady=6)
        self.status.pack(side="right")

    def update_bar(self, board: chess.Board, color: chess.Color, name: str, detail: str,
                   *, to_move: bool, thinking: bool, is_human: bool, result: str = ""):
        self.name.config(text=name)
        self.detail.config(text=detail)

        # Avatar: rounded tile in the side's colour with a king (human) or knight (agent).
        a = self.avatar
        a.delete("all")
        fill = "#e9e5df" if color == chess.WHITE else "#46423d"
        a.create_rectangle(1, 1, 35, 35, fill=fill, outline=theme.ACCENT if to_move else fill,
                           width=2)
        draw_piece(a, 18, 19, chess.KING if is_human else chess.KNIGHT,
                   chess.BLACK if color == chess.WHITE else chess.WHITE, 28)

        # Captured enemy pieces, grouped by type, plus the material lead.
        c = self.captures
        c.delete("all")
        x = 2
        for pt, n in captured_by(board, color).items():
            for _ in range(n):
                draw_piece(c, x + 8, 10, pt, not color, 18)
                x += 10 if pt == chess.PAWN else 12
            if n:
                x += 8
        lead = material_balance(board) * (1 if color == chess.WHITE else -1)
        if lead > 0:
            c.create_text(x + 6, 9, text=f"+{lead}", anchor="w", fill=theme.MUTED,
                          font=theme.ui_font(9, "bold"))

        if result:
            self.status.config(text=result, bg=theme.CARD, fg=theme.TEXT)
        elif thinking:
            self.status.config(text="Thinking…", bg=theme.ACCENT, fg=theme.ACCENT_TEXT)
        elif to_move:
            self.status.config(text="To move", bg=theme.ACCENT_DARK, fg=theme.ACCENT_TEXT)
        else:
            self.status.config(text="", bg=theme.BG, fg=theme.MUTED)
