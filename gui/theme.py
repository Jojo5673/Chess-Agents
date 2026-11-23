"""Colours, fonts and small colour helpers (chess.com-like layout, orange accent)."""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont

# ---- app chrome ------------------------------------------------------------
BG = "#262421"            # window background (dark charcoal)
PANEL = "#1f1e1c"         # side panel
CARD = "#2c2a27"          # cards / rows inside the panel
CARD_ALT = "#34312d"      # alternate move-list rows, pill background
CARD_HOVER = "#3d3a35"
BORDER = "#3a3733"
TEXT = "#ece9e4"
MUTED = "#9d9893"
FAINT = "#6f6a65"

ACCENT = "#f08a24"        # orange (in place of chess.com's green)
ACCENT_HOVER = "#ff9f40"
ACCENT_DARK = "#b9651a"
ACCENT_TEXT = "#ffffff"
DANGER = "#e05a47"

# ---- board -----------------------------------------------------------------
LIGHT_SQ = "#f1dcc0"      # cream
DARK_SQ = "#c27a43"       # warm orange-brown
LAST_MOVE = "#f7c64a"     # blended onto the square
SELECTED = "#f08a24"
CHECK = "#e8402f"
MARKER = "#000000"        # legal-move dots / capture rings (blended)

WHITE_PIECE_FILL = "#fbfaf7"
WHITE_PIECE_LINE = "#2a2724"
BLACK_PIECE_FILL = "#3b3733"
BLACK_PIECE_LINE = "#121110"

EVAL_WHITE = "#f4f2ee"
EVAL_BLACK = "#3b3835"

# ---- fonts -----------------------------------------------------------------
UI_FAMILY = "Segoe UI"
_PIECE_FAMILY_CANDIDATES = ("Segoe UI Symbol", "DejaVu Sans", "Noto Sans Symbols2",
                            "Arial Unicode MS", "FreeSerif", "Symbola")
_piece_family = None


def ui_font(size: int = 10, weight: str = "normal"):
    return (UI_FAMILY, size, weight)


def piece_family(root: tk.Misc) -> str:
    """First installed font that has chess glyphs (falls back to Tk's default)."""
    global _piece_family
    if _piece_family is None:
        installed = set(tkfont.families(root))
        _piece_family = next((f for f in _PIECE_FAMILY_CANDIDATES if f in installed),
                             "TkDefaultFont")
    return _piece_family


# ---- colour helpers --------------------------------------------------------
def _rgb(hex_colour: str):
    hex_colour = hex_colour.lstrip("#")
    return tuple(int(hex_colour[i:i + 2], 16) for i in (0, 2, 4))


def blend(base: str, over: str, alpha: float) -> str:
    """`over` painted on `base` with opacity `alpha` (Tk has no real alpha)."""
    b, o = _rgb(base), _rgb(over)
    return "#%02x%02x%02x" % tuple(round(bc + (oc - bc) * alpha) for bc, oc in zip(b, o))
