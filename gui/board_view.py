"""
The board canvas: squares, coordinates, highlights, pieces, click/drag input,
the promotion chooser and the game-over banner.

It never stores a board between redraws: every redraw asks `get_game()` for the
current Game and reads `game.board` fresh (Game swaps in a new board on every move).
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable, List, Optional, Sequence, Tuple

import chess

from . import theme
from .widgets import FlatButton, draw_piece

PROMOTION_CHOICES = (chess.QUEEN, chess.KNIGHT, chess.ROOK, chess.BISHOP)
DRAG_THRESHOLD = 4


class BoardView(tk.Canvas):
    def __init__(self, master, *, get_game: Callable[[], Optional[object]],
                 can_move: Callable[[], bool],
                 on_move: Callable[[chess.Square, chess.Square], None], size: int = 560):
        super().__init__(master, width=size, height=size, bg=theme.BG,
                         highlightthickness=0, bd=0)
        self.get_game = get_game
        self.can_move = can_move
        self.on_move = on_move
        self.white_bottom = True
        self.selected: Optional[chess.Square] = None
        self._drag: Optional[dict] = None
        self._promo: Optional[Tuple[chess.Square, chess.Color, Callable]] = None
        self._banner: Optional[Tuple[str, str, Sequence[Tuple[str, Callable]]]] = None
        self._banner_widgets: List[tk.Widget] = []
        # Set by the app while reviewing a finished game; None = live board.
        self.display_board: Optional[chess.Board] = None

        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_motion)
        self.bind("<ButtonRelease-1>", self._on_release)

    # ---- geometry ----------------------------------------------------------
    @property
    def sq(self) -> int:
        w = self.winfo_width() if self.winfo_width() > 1 else int(self["width"])
        h = self.winfo_height() if self.winfo_height() > 1 else int(self["height"])
        return max(10, min(w, h) // 8)

    def square_origin(self, square: chess.Square) -> Tuple[int, int]:
        """Top-left pixel of a square in the current orientation."""
        file, rank = chess.square_file(square), chess.square_rank(square)
        col = file if self.white_bottom else 7 - file
        row = 7 - rank if self.white_bottom else rank
        return col * self.sq, row * self.sq

    def square_at(self, x: float, y: float) -> Optional[chess.Square]:
        sq = self.sq
        col, row = int(x // sq), int(y // sq)
        if not (0 <= col < 8 and 0 <= row < 8):
            return None
        file = col if self.white_bottom else 7 - col
        rank = 7 - row if self.white_bottom else row
        return chess.square(file, rank)

    # ---- public API --------------------------------------------------------
    def set_orientation(self, white_bottom: bool):
        self.white_bottom = white_bottom
        self.redraw()

    def clear_selection(self):
        self.selected = None
        self._drag = None

    @property
    def promotion_pending(self) -> bool:
        return self._promo is not None

    def ask_promotion(self, to_square: chess.Square, color: chess.Color,
                      callback: Callable[[Optional[chess.PieceType]], None]):
        """Show the chooser over `to_square`; callback(piece_type or None if cancelled)."""
        self._promo = (to_square, color, callback)
        self.redraw()

    def choose_promotion(self, piece_type: Optional[chess.PieceType]):
        """Resolve the pending promotion (also used by tests)."""
        if self._promo is None:
            return
        callback = self._promo[2]
        self._promo = None
        self.redraw()
        callback(piece_type)

    def cancel_promotion(self):
        """Drop a pending chooser without calling its callback (new game / undo)."""
        if self._promo is not None:
            self._promo = None
            self.redraw()

    def show_banner(self, title: str, subtitle: str,
                    buttons: Sequence[Tuple[str, Callable[[], None]]]):
        self._banner = (title, subtitle, buttons)
        self.redraw()

    def hide_banner(self):
        self._banner = None
        self.redraw()

    @property
    def banner_visible(self) -> bool:
        return self._banner is not None

    # ---- drawing -----------------------------------------------------------
    def redraw(self):
        self.delete("all")
        for w in self._banner_widgets:
            w.destroy()
        self._banner_widgets = []

        game = self.get_game()
        if self.display_board is not None:
            board = self.display_board
        else:
            board = game.board if game is not None else chess.Board()
        last = board.peek() if board.move_stack else None
        sq = self.sq

        targets = self._targets(game)
        check_sq = board.king(board.turn) if board.is_check() else None
        # Tk has no alpha, so overlays "dim" the board by darkening what is drawn under them.
        dim = 0.45 if (self._promo is not None or self._banner is not None) else 0.0

        for square in chess.SQUARES:
            x, y = self.square_origin(square)
            light = (chess.square_file(square) + chess.square_rank(square)) % 2 == 1
            base = theme.LIGHT_SQ if light else theme.DARK_SQ
            colour = base
            if last is not None and square in (last.from_square, last.to_square):
                colour = theme.blend(base, theme.LAST_MOVE, 0.5)
            if square == self.selected:
                colour = theme.blend(base, theme.SELECTED, 0.55)
            if square == check_sq:
                colour = self._draw_check_glow(x, y, sq, colour, dim)
            else:
                self.create_rectangle(x, y, x + sq, y + sq,
                                      fill=theme.blend(colour, "#000000", dim), width=0)
        self._draw_coordinates(sq, dim)

        # Legal-move markers (dots on empty squares, rings on captures).
        for target in targets:
            x, y = self.square_origin(target)
            light = (chess.square_file(target) + chess.square_rank(target)) % 2 == 1
            base = theme.LIGHT_SQ if light else theme.DARK_SQ
            marker = theme.blend(base, theme.MARKER, 0.2)
            cx, cy = x + sq / 2, y + sq / 2
            if board.piece_at(target) is not None or (
                    board.ep_square == target and self.selected is not None
                    and board.piece_type_at(self.selected) == chess.PAWN):
                r, w = sq * 0.46, max(3, sq // 12)
                self.create_oval(cx - r, cy - r, cx + r, cy + r, outline=marker, width=w)
            else:
                r = sq * 0.16
                self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=marker, width=0)

        dragging = self._drag["square"] if self._drag and self._drag["moved"] else None
        for square, piece in board.piece_map().items():
            x, y = self.square_origin(square)
            tags = ("piece", f"sq{square}")
            if square == dragging:
                continue
            draw_piece(self, x + sq / 2, y + sq / 2 + sq * 0.02, piece.piece_type,
                       piece.color, int(sq * 0.8), tags, shade=dim * 0.6)
        if dragging is not None:
            piece = board.piece_at(dragging)
            if piece is not None:
                px, py = self._drag["pos"]
                draw_piece(self, px, py, piece.piece_type, piece.color,
                           int(sq * 0.85), ("drag",))

        if self._promo is not None:
            self._draw_promotion(sq)
        if self._banner is not None:
            self._draw_banner(sq)

    def _draw_check_glow(self, x, y, sq, base, dim):
        # Radial red glow: concentric ovals fading into the square colour.
        base = theme.blend(base, "#000000", dim)
        self.create_rectangle(x, y, x + sq, y + sq, fill=base, width=0)
        steps = 6
        for i in range(steps):
            frac = 1 - i / steps
            r = sq * 0.5 * (0.55 + 0.45 * frac)
            colour = theme.blend(base, theme.CHECK, 0.25 + 0.6 * (i / steps))
            cx, cy = x + sq / 2, y + sq / 2
            self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=colour, width=0)
        return base

    def _draw_coordinates(self, sq, dim=0.0):
        font = (theme.UI_FAMILY, -max(9, sq // 6), "bold")
        pad = max(2, sq // 22)
        for i in range(8):
            # Rank numbers down the left edge, file letters along the bottom edge.
            rank = 7 - i if self.white_bottom else i
            left_file = 0 if self.white_bottom else 7
            light_left = (left_file + rank) % 2 == 1
            self.create_text(pad, i * sq + pad, text=str(rank + 1), anchor="nw", font=font,
                             fill=theme.blend(theme.DARK_SQ if light_left else theme.LIGHT_SQ,
                                              "#000000", dim))
            file = i if self.white_bottom else 7 - i
            bottom_rank = 0 if self.white_bottom else 7
            light_bottom = (file + bottom_rank) % 2 == 1
            self.create_text((i + 1) * sq - pad, 8 * sq - pad, text=chess.FILE_NAMES[file],
                             anchor="se", font=font,
                             fill=theme.blend(theme.DARK_SQ if light_bottom else theme.LIGHT_SQ,
                                              "#000000", dim))

    def _promotion_cells(self, sq) -> List[Tuple[Optional[int], Tuple[int, int, int, int]]]:
        """(piece_type, or None for the cancel cell, (x0, y0, x1, y1)) for each cell."""
        to_square, _, _ = self._promo
        x, y = self.square_origin(to_square)
        down = y == 0                       # promoting at the top edge: open downwards
        step = sq if down else -sq
        cells = [(pt, (x, y + i * step, x + sq, y + i * step + sq))
                 for i, pt in enumerate(PROMOTION_CHOICES)]
        half = sq // 2
        cy = y + 4 * sq if down else y - 3 * sq - half
        cells.append((None, (x, cy, x + sq, cy + half)))
        return cells

    def _draw_promotion(self, sq):
        _, color, _ = self._promo
        cells = self._promotion_cells(sq)
        x0 = min(r[0] for _, r in cells)
        y0 = min(r[1] for _, r in cells)
        x1 = max(r[2] for _, r in cells)
        y1 = max(r[3] for _, r in cells)
        self.create_rectangle(x0 - 3, y0 - 3, x1 + 3, y1 + 3, fill=theme.ACCENT, width=0)
        for pt, (cx0, cy0, cx1, cy1) in cells:
            if pt is None:
                self.create_rectangle(cx0, cy0, cx1, cy1, fill="#e9e6e1", width=0)
                self.create_text((cx0 + cx1) / 2, (cy0 + cy1) / 2, text="✕",
                                 fill="#6b6762",
                                 font=(theme.UI_FAMILY, -max(10, sq // 4), "bold"))
            else:
                self.create_rectangle(cx0, cy0, cx1, cy1, fill="#ffffff", width=0)
                draw_piece(self, (cx0 + cx1) / 2, (cy0 + cy1) / 2, pt, color, int(sq * 0.78))

    def _promotion_hit(self, px, py) -> Tuple[bool, Optional[int]]:
        for pt, (x0, y0, x1, y1) in self._promotion_cells(self.sq):
            if x0 <= px < x1 and y0 <= py < y1:
                return True, pt
        return False, None

    def _draw_banner(self, sq):
        title, subtitle, buttons = self._banner
        size = 8 * sq
        w, h = min(size - 40, max(260, sq * 4)), max(170, int(sq * 2.6))
        x0, y0 = (size - w) / 2, (size - h) / 2
        self.create_rectangle(x0 + 4, y0 + 6, x0 + w + 4, y0 + h + 6, fill="#141311", width=0)
        self.create_rectangle(x0, y0, x0 + w, y0 + h, fill=theme.PANEL, outline=theme.BORDER)
        self.create_rectangle(x0, y0, x0 + w, y0 + 6, fill=theme.ACCENT, width=0)
        self.create_text(size / 2, y0 + h * 0.26, text=title, fill=theme.TEXT,
                         font=theme.ui_font(18, "bold"))
        self.create_text(size / 2, y0 + h * 0.46, text=subtitle, fill=theme.MUTED,
                         font=theme.ui_font(11), width=w - 30, justify="center")
        n = len(buttons)
        for i, (text, command) in enumerate(buttons):
            btn = FlatButton(self, text, command, style="primary" if i == 0 else "secondary")
            self._banner_widgets.append(btn)
            bx = x0 + w * (i + 1) / (n + 1)
            self.create_window(bx, y0 + h * 0.76, window=btn)

    # ---- input -------------------------------------------------------------
    def _targets(self, game) -> List[chess.Square]:
        if game is None or self.selected is None:
            return []
        return sorted({m.to_square for m in game.legal_moves_from(self.selected)})

    def _on_press(self, event):
        if self._promo is not None:
            hit, choice = self._promotion_hit(event.x, event.y)
            self.choose_promotion(choice if hit else None)
            return
        if self._banner is not None:
            return
        game = self.get_game()
        if game is None or not self.can_move():
            self.clear_selection()
            self.redraw()
            return
        square = self.square_at(event.x, event.y)
        if square is None:
            return
        if self.selected is not None and square in self._targets(game):
            src = self.selected
            self.clear_selection()
            self.on_move(src, square)
            return
        piece = game.board.piece_at(square)
        if piece is not None and piece.color == game.board.turn:
            reselect = square == self.selected
            self.selected = square
            self._drag = {"square": square, "start": (event.x, event.y),
                          "pos": (event.x, event.y), "moved": False, "reselect": reselect}
        else:
            self.clear_selection()
        self.redraw()

    def _on_motion(self, event):
        drag = self._drag
        if drag is None:
            return
        sx, sy = drag["start"]
        if not drag["moved"] and abs(event.x - sx) + abs(event.y - sy) < DRAG_THRESHOLD:
            return
        if not drag["moved"]:
            drag["moved"] = True
            drag["pos"] = (event.x, event.y)
            self.redraw()
            return
        px, py = drag["pos"]
        self.move("drag", event.x - px, event.y - py)
        self.tag_raise("drag")
        drag["pos"] = (event.x, event.y)

    def _on_release(self, event):
        drag, self._drag = self._drag, None
        if drag is None:
            return
        game = self.get_game()
        if drag["moved"]:
            target = self.square_at(event.x, event.y)
            if game is not None and self.can_move() and target in self._targets(game):
                self.clear_selection()
                self.on_move(drag["square"], target)
                return
        elif drag["reselect"]:
            self.selected = None                    # second click on the same piece
        self.redraw()
