"""
Game controller: the single object a GUI or match harness talks to.

It owns the board, knows who plays each colour, validates moves, keeps a move
log, and reports the result

"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, List, Optional

import chess

from .agent import Agent, Player
from .search import SearchResult


class GameError(Exception):
    pass


class IllegalMoveError(GameError):
    pass


class GameOverError(GameError):
    pass


@dataclass
class MoveRecord:
    """One move in the log (also what gets written to the match CSV/JSON)."""
    ply: int                       # 1-based half-move number
    color: str                     # "white" or "black"
    player: str                    # player's name
    uci: str
    san: str
    source: str                    # "agent", "human" or "opening"
    score: Optional[float] = None  # agent's evaluation (White's perspective)
    depth: Optional[int] = None
    nodes: Optional[int] = None
    time_s: Optional[float] = None
    fen_after: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class Game:
    def __init__(
        self,
        white: Player,
        black: Player,
        *,
        board: Optional[chess.Board] = None,
        max_plies: int = 300,
        on_move: Optional[Callable[[MoveRecord], None]] = None,
    ):
        """
        max_plies: agent games can shuffle forever; after this many half-moves
                   played in this Game the game is declared drawn.
        on_move:   optional callback fired after every move (handy for a GUI).
        """
        self.white = white
        self.black = black
        self.board = board.copy() if board is not None else chess.Board()
        self.max_plies = max_plies
        self.on_move = on_move
        self.history: List[MoveRecord] = []

    # ---- whose turn --------------------------------------------------------
    @property
    def current_player(self) -> Player:
        return self.white if self.board.turn == chess.WHITE else self.black

    @property
    def is_human_turn(self) -> bool:
        return (not self.is_over) and self.current_player.is_human

    @property
    def is_agent_turn(self) -> bool:
        return (not self.is_over) and not self.current_player.is_human

    @property
    def last_move(self) -> Optional[chess.Move]:
        return self.board.peek() if self.board.move_stack else None

    # ---- game state --------------------------------------------------------
    def _outcome(self):
        return self.board.outcome(claim_draw=False)

    @property
    def is_over(self) -> bool:
        return self._outcome() is not None or len(self.history) >= self.max_plies

    @property
    def result(self) -> str:
        """'1-0', '0-1', '1/2-1/2', or '*' while the game is in progress."""
        outcome = self._outcome()
        if outcome is not None:
            return outcome.result()
        return "1/2-1/2" if len(self.history) >= self.max_plies else "*"

    @property
    def winner(self) -> Optional[chess.Color]:
        outcome = self._outcome()
        return outcome.winner if outcome is not None else None

    @property
    def termination(self) -> str:
        """e.g. 'checkmate', 'stalemate', 'threefold_repetition', 'max_plies'."""
        outcome = self._outcome()
        if outcome is not None:
            return outcome.termination.name.lower()
        return "max_plies" if len(self.history) >= self.max_plies else ""

    def status_text(self) -> str:
        """Human-readable status line for a GUI label."""
        if self.is_over:
            if self.winner is None:
                return f"Draw ({self.termination.replace('_', ' ')})"
            side = "White" if self.winner == chess.WHITE else "Black"
            winner_name = (self.white if self.winner == chess.WHITE else self.black).name
            return f"{side} ({winner_name}) wins by {self.termination.replace('_', ' ')}"
        side = "White" if self.board.turn == chess.WHITE else "Black"
        check = " - check!" if self.board.is_check() else ""
        return f"{side} to move ({self.current_player.name}){check}"

    # ---- helpers for click-to-move GUIs ----------------------------------
    def legal_moves_from(self, square: chess.Square) -> List[chess.Move]:
        """Legal moves starting on `square` (for highlighting targets)."""
        return [m for m in self.board.legal_moves if m.from_square == square]

    def is_promotion(self, from_sq: chess.Square, to_sq: chess.Square) -> bool:
        piece = self.board.piece_at(from_sq)
        return bool(piece and piece.piece_type == chess.PAWN
                    and chess.square_rank(to_sq) in (0, 7))

    def move_from_squares(self, from_sq, to_sq, promotion=None) -> Optional[chess.Move]:
        """
        Build the legal Move for a click-from/click-to, or None if illegal.
        A pawn reaching the last rank auto-promotes to a queen unless
        `promotion` (e.g. chess.KNIGHT) is given. Castling = king moves two squares.
        """
        if promotion is None and self.is_promotion(from_sq, to_sq):
            promotion = chess.QUEEN
        move = chess.Move(from_sq, to_sq, promotion)
        return move if move in self.board.legal_moves else None

    # ---- making moves ------------------------------------------------------
    def play_move(self, move: chess.Move, *, source: str = "human",
                  search: Optional[SearchResult] = None) -> MoveRecord:
        """Validate and play a move for whoever's turn it is."""
        if self.is_over:
            raise GameOverError("The game is already over.")
        if move not in self.board.legal_moves:
            raise IllegalMoveError(f"Illegal move: {move.uci()}")

        player = self.current_player
        color = "white" if self.board.turn == chess.WHITE else "black"
        next_board = self.board.copy()
        san = next_board.san(move)
        next_board.push(move)
        self.board = next_board

        record = MoveRecord(
            ply=len(self.history) + 1, color=color, player=player.name,
            uci=move.uci(), san=san, source=source,
            score=search.score if search else None,
            depth=search.depth if search else None,
            nodes=search.nodes if search else None,
            time_s=search.time_s if search else None,
            fen_after=self.board.fen(),
        )
        self.history.append(record)
        if self.on_move:
            self.on_move(record)
        return record

    def play_agent_move(self) -> MoveRecord:
        """
        Ask the current agent for a move and play it. BLOCKS while the agent
        searches, so GUIs should call this from a worker thread.
        """
        if self.is_over:
            raise GameOverError("The game is already over.")
        player = self.current_player
        if player.is_human or not isinstance(player, Agent):
            raise GameError(f"{player.name} is not an agent; use play_move().")
        result = player.choose_move(self.board)
        return self.play_move(result.move, source="agent", search=result)

    def undo(self) -> Optional[MoveRecord]:
        """Take back the last half-move (e.g. a GUI 'undo' button)."""
        if not self.history:
            return None
        self.board.pop()
        return self.history.pop()
