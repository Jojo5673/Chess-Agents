"""Tkinter desktop GUI for the chess agents (run with ``python -m gui``)."""
from .app import ChessApp, main
from .config import GameConfig, SideConfig

__all__ = ["ChessApp", "GameConfig", "SideConfig", "main"]
