"""Shared chess engine: search, players, and the game controller."""
from .evaluation import EvalFn, MATE_SCORE, PIECE_VALUES, material
from .search import SearchResult, find_best_move, terminal_score
from .agent import Agent, HumanPlayer, MinimaxAgent, Player, RandomAgent
from .game import (Game, GameError, GameOverError, IllegalMoveError, MoveRecord)

__all__ = [
    "EvalFn", "MATE_SCORE", "PIECE_VALUES", "material",
    "SearchResult", "find_best_move", "terminal_score",
    "Agent", "HumanPlayer", "MinimaxAgent", "Player", "RandomAgent",
    "Game", "GameError", "GameOverError", "IllegalMoveError", "MoveRecord",
]
