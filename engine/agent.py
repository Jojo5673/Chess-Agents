"""
Players and agents.

Everything that can sit on one side of the board is a `Player`:
    HumanPlayer   - moves come from the GUI (the engine never asks it to move)
    Agent         - computer player; implements choose_move(board) -> SearchResult
    MinimaxAgent  - Agent = shared minimax/alpha-beta search + a pluggable eval function
    RandomAgent   - plays random legal moves (a sanity-check opponent)

To create a new strategy you normally do NOT subclass anything: write an
evaluation function and wrap it in a MinimaxAgent (see agents/).
"""
from __future__ import annotations

import random
import time
from typing import Optional

import chess

from .evaluation import EvalFn
from .search import SearchResult, find_best_move


class Player:
    """Anything that can play one colour."""
    is_human = False

    def __init__(self, name: str):
        self.name = name

    def __repr__(self):
        return f"<{type(self).__name__} {self.name!r}>"


class HumanPlayer(Player):
    """Placeholder for a human; the GUI supplies their moves via Game.play_move."""
    is_human = True


class Agent(Player):
    """A computer player."""
    description = ""

    def choose_move(self, board: chess.Board) -> SearchResult:
        raise NotImplementedError


class MinimaxAgent(Agent):
    """
    Minimax + alpha-beta agent whose personality is entirely its `eval_fn`.

    `depth` is a normal public attribute: a GUI can change it at any time to
    implement difficulty levels.
    """

    def __init__(
        self,
        name: str,
        eval_fn: EvalFn,
        depth: int = 3,
        *,
        use_alpha_beta: bool = True,
        order_moves: bool = True,
        seed: Optional[int] = None,
        description: str = "",
        time_limit_s: Optional[float] = None,
    ):
        super().__init__(name)
        self.eval_fn = eval_fn
        self.depth = depth
        self.use_alpha_beta = use_alpha_beta
        self.order_moves = order_moves
        self.time_limit_s = time_limit_s
        self.description = description
        self.rng = random.Random(seed)   # tie-breaking among equal root moves

    def choose_move(self, board: chess.Board) -> SearchResult:
        # Search a copy so a GUI thread can keep drawing the real board.
        return find_best_move(
            board.copy(), self.depth, self.eval_fn,
            use_alpha_beta=self.use_alpha_beta,
            order_moves=self.order_moves,
            rng=self.rng,
            time_limit_s=self.time_limit_s,
        )


class RandomAgent(Agent):
    """Picks a uniformly random legal move. Useful as a sanity-check baseline."""

    def __init__(self, name: str = "Random", seed: Optional[int] = None):
        super().__init__(name)
        self.depth = 0
        self.description = "Plays random legal moves."
        self.rng = random.Random(seed)

    def choose_move(self, board: chess.Board) -> SearchResult:
        start = time.perf_counter()
        move = self.rng.choice(list(board.legal_moves))
        return SearchResult(move, 0.0, 0, 1, time.perf_counter() - start)
