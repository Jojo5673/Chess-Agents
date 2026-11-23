"""
Run an agent's search off the UI thread (pattern from the partner guide, 6.4).

The worker only *reads*: it searches a private copy of the board. The result is
handed back through a queue and applied to the Game on the UI thread by poll().
Each search carries a generation number so a result that arrives after Undo /
New Game / Resign (cancel()) is silently discarded instead of being played on
the wrong position.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Optional

from engine.game import Game, MoveRecord


class AgentRunner:
    def __init__(self):
        self._results: "queue.Queue" = queue.Queue()
        self._generation = 0
        self._expected_fen: Optional[str] = None
        self.busy = False
        self.started_at: Optional[float] = None
        self.agent = None

    def start(self, game: Game) -> None:
        if self.busy:
            raise RuntimeError("An agent search is already running.")
        if not game.is_agent_turn:
            raise RuntimeError("It is not an agent's turn.")
        agent = game.current_player
        board = game.board.copy()                  # snapshot for the worker
        generation = self._generation
        self._expected_fen = board.fen()
        self.busy = True
        self.agent = agent
        self.started_at = time.monotonic()

        def work():
            try:
                self._results.put((generation, agent.choose_move(board), None))
            except Exception as exc:               # surfaced on the UI thread
                self._results.put((generation, None, exc))

        threading.Thread(target=work, name=f"search-{agent.name}", daemon=True).start()

    def cancel(self) -> None:
        """Forget the running search; its result will be ignored when it arrives."""
        self._generation += 1
        self.busy = False
        self.agent = None
        self.started_at = None

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at if self.started_at else 0.0

    def poll(self, game: Game) -> Optional[MoveRecord]:
        """
        Call from the UI thread on a timer. Plays and returns the MoveRecord if a
        search just finished; re-raises an exception the agent raised.
        """
        while True:
            try:
                generation, result, error = self._results.get_nowait()
            except queue.Empty:
                return None
            if generation != self._generation:
                continue                           # stale (cancelled) search
            self.busy = False
            self.agent = None
            self.started_at = None
            if error is not None:
                raise error
            if game.board.fen() != self._expected_fen or result.move is None:
                return None                        # position changed under us
            return game.play_move(result.move, source="agent", search=result)
