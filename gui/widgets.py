"""Small flat widgets (tk's native buttons can't be themed on Windows) and piece drawing."""
from __future__ import annotations

import tkinter as tk
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

import chess

from . import theme


class FlatButton(tk.Label):
    """A label that behaves like a flat button with hover and disabled states."""

    STYLES = {
        "primary": (theme.ACCENT, theme.ACCENT_HOVER, theme.ACCENT_TEXT),
        "secondary": (theme.CARD_ALT, theme.CARD_HOVER, theme.TEXT),
        "ghost": (theme.PANEL, theme.CARD, theme.MUTED),
    }

    def __init__(self, master, text: str, command: Optional[Callable[[], None]] = None, *,
                 style: str = "secondary", font=None, padx: int = 12, pady: int = 7, **kw):
        self._bg, self._hover, self._fg = self.STYLES[style]
        super().__init__(master, text=text, bg=self._bg, fg=self._fg,
                         font=font or theme.ui_font(10, "bold"), padx=padx, pady=pady,
                         cursor="hand2", **kw)
        self.command = command
        self.enabled = True
        self.bind("<Enter>", lambda e: self.enabled and self.config(bg=self._hover))
        self.bind("<Leave>", lambda e: self.config(bg=self._bg if self.enabled else theme.CARD))
        self.bind("<ButtonRelease-1>", self._on_click)

    def _on_click(self, event):
        # Only fire if released over the button (like a real button).
        if 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height():
            self.invoke()

    def invoke(self):
        if self.enabled and self.command:
            self.command()

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        self.config(bg=self._bg if enabled else theme.CARD,
                    fg=self._fg if enabled else theme.FAINT,
                    cursor="hand2" if enabled else "arrow")


class PillGroup(tk.Frame):
    """A row (or grid) of toggle pills; exactly one is selected."""

    def __init__(self, master, options: Sequence[Tuple[object, str]], value=None, *,
                 on_change: Optional[Callable[[object], None]] = None, columns: int = 0,
                 font=None, bg: str = theme.PANEL, pady: int = 5):
        super().__init__(master, bg=bg)
        self.on_change = on_change
        self.enabled = True
        self._pills: List[Tuple[object, tk.Label]] = []
        self.value = value if value is not None else (options[0][0] if options else None)
        columns = columns or len(options)
        for i, (val, label) in enumerate(options):
            pill = tk.Label(self, text=label, font=font or theme.ui_font(9, "bold"),
                            padx=8, pady=pady, cursor="hand2")
            pill.grid(row=i // columns, column=i % columns, sticky="nsew", padx=2, pady=2)
            pill.bind("<Button-1>", lambda e, v=val: self.select(v, notify=True))
            pill.bind("<Enter>", lambda e, p=pill, v=val: self._hover(p, v, True))
            pill.bind("<Leave>", lambda e, p=pill, v=val: self._hover(p, v, False))
            self._pills.append((val, pill))
        for c in range(columns):
            self.grid_columnconfigure(c, weight=1, uniform="pill")
        self._paint()

    def _hover(self, pill, val, inside):
        if self.enabled and val != self.value:
            pill.config(bg=theme.CARD_HOVER if inside else theme.CARD_ALT)

    def _paint(self):
        for val, pill in self._pills:
            if not self.enabled:
                pill.config(bg=theme.CARD, fg=theme.FAINT, cursor="arrow")
            elif val == self.value:
                pill.config(bg=theme.ACCENT, fg=theme.ACCENT_TEXT, cursor="hand2")
            else:
                pill.config(bg=theme.CARD_ALT, fg=theme.TEXT, cursor="hand2")

    def select(self, value, notify: bool = False):
        if not self.enabled and notify:
            return
        self.value = value
        self._paint()
        if notify and self.on_change:
            self.on_change(value)

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        self._paint()


def glyph(piece_type: chess.PieceType) -> str:
    """The filled (silhouette) glyph for a piece type, used for both colours."""
    return chess.Piece(piece_type, chess.BLACK).unicode_symbol()


def draw_piece(canvas: tk.Canvas, x: float, y: float, piece_type: chess.PieceType,
               color: chess.Color, size: int, tags: Iterable[str] = (),
               shade: float = 0.0) -> None:
    """
    Draw a piece centred on (x, y) from the filled Unicode glyph: eight copies
    nudged around the centre in the outline colour, then the glyph itself in the
    side's fill colour. The glyph's thin cut-outs fill with the outline colour,
    so they read as inner detail lines.
    """
    font = (theme.piece_family(canvas), -max(6, int(size)))
    text = glyph(piece_type)
    tags = tuple(tags)
    if color == chess.WHITE:
        fill, line = theme.WHITE_PIECE_FILL, theme.WHITE_PIECE_LINE
    else:
        fill, line = theme.BLACK_PIECE_FILL, theme.BLACK_PIECE_LINE
    if shade:
        fill, line = theme.blend(fill, "#000000", shade), theme.blend(line, "#000000", shade)
    d = max(1, round(size / 30))
    for dx, dy in ((-d, 0), (d, 0), (0, -d), (0, d), (-d, -d), (d, -d), (-d, d), (d, d)):
        canvas.create_text(x + dx, y + dy, text=text, font=font, fill=line, tags=tags)
    canvas.create_text(x, y, text=text, font=font, fill=fill, tags=tags)
