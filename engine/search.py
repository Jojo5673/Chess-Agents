"""
Minimax search with Alpha-Beta pruning.

The search is evaluation-agnostic: it is handed an `eval_fn` (see
evaluation.py) and uses it at the leaves. It always scores from WHITE's
perspective: White nodes maximize, Black nodes minimize.

Features
--------
* Alpha-Beta pruning (can be switched off, to measure how much it saves).
* Move ordering (captures by MVV-LVA, promotions, checks first) so that
  pruning cuts off earlier.
* Terminal detection (mate / stalemate / draws) handled here, not by agents.
* Mate-distance scoring: faster mates are preferred, slower losses are
  preferred over faster ones.
* Optional random choice among equally good root moves, so that two
  deterministic agents don't replay the exact same game every time.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import List, Optional

import chess

from .evaluation import EvalFn, MATE_SCORE

# Root moves within this margin of the best score count as ties.
_TIE_EPS = 1e-6

# Values used only to ORDER moves (not for evaluation).
_ORDER_VALUE = {
    chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
    chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100,
}


@dataclass
class SearchResult:
    """What a search (or any agent) returns for one decision."""
    move: Optional[chess.Move]   # chosen move (None only if the game is over)
    score: float                 # score from White's perspective
    depth: int                   # search depth used (0 for non-searching agents)
    nodes: int                   # positions visited
    time_s: float                # wall-clock seconds spent


def find_best_move(
    board: chess.Board,
    depth: int,
    eval_fn: EvalFn,
    *,
    use_alpha_beta: bool = True,
    order_moves: bool = True,
    rng: Optional[random.Random] = None,
) -> SearchResult:
    """
    Search `depth` plies ahead and return the best move for the side to move.

    NOTE: this pushes/pops moves on `board` while searching (it is restored
    before returning). Pass a copy if another thread is reading the board.
    """
    if depth < 1:
        raise ValueError("depth must be >= 1")
    searcher = _Searcher(eval_fn, use_alpha_beta, order_moves)
    start = time.perf_counter()
    move, score = searcher.search_root(board, depth, rng)
    return SearchResult(move, score, depth, searcher.nodes, time.perf_counter() - start)


def terminal_score(board: chess.Board, ply: int) -> Optional[float]:
    """
    Score of a finished game (White's perspective), or None if play continues.
    `ply` is the distance from the root, used so that quicker mates score better.
    """
    if board.is_checkmate():
        # The side to move has been mated.
        return -(MATE_SCORE - ply) if board.turn == chess.WHITE else (MATE_SCORE - ply)
    if (board.is_stalemate() or board.is_insufficient_material()
            or board.is_fifty_moves() or board.is_repetition(3)
            or (board.is_repetition(2) and board.can_claim_threefold_repetition())):
        return 0
    return None


def _move_priority(board: chess.Board, move: chess.Move) -> int:
    """Heuristic priority for move ordering: higher = search earlier."""
    priority = 0
    if board.is_capture(move):
        # Most Valuable Victim - Least Valuable Attacker.
        victim = board.piece_type_at(move.to_square) or chess.PAWN  # en passant
        attacker = board.piece_type_at(move.from_square)
        priority += 10_000 + 10 * _ORDER_VALUE[victim] - _ORDER_VALUE[attacker]
    if move.promotion:
        priority += 5_000 + _ORDER_VALUE[move.promotion]
    if board.gives_check(move):
        priority += 50
    return priority


class _Searcher:
    def __init__(self, eval_fn: EvalFn, use_alpha_beta: bool, order_moves: bool):
        self.eval_fn = eval_fn
        self.use_ab = use_alpha_beta
        self.order = order_moves
        self.nodes = 0

    def _moves(self, board: chess.Board) -> List[chess.Move]:
        moves = list(board.legal_moves)
        if self.order:
            moves.sort(key=lambda m: _move_priority(board, m), reverse=True)
        return moves

    def search_root(self, board, depth, rng):
        """Root of the search: also tracks ties so we can pick among them."""
        self.nodes += 1
        done = terminal_score(board, 0)
        if done is not None:
            return None, done

        maximizing = board.turn == chess.WHITE
        alpha, beta = -math.inf, math.inf
        best_score = -math.inf if maximizing else math.inf
        best_moves: List[chess.Move] = []

        for move in self._moves(board):
            board.push(move)
            score = self._value(board, depth - 1, alpha, beta, 1)
            board.pop()

            if maximizing:
                if score > best_score:
                    best_score, best_moves = score, [move]
                elif score == best_score:
                    best_moves.append(move)
                # Keep the window just below the best so equal moves are
                # still searched exactly (needed to detect ties).
                alpha = max(alpha, best_score - _TIE_EPS)
            else:
                if score < best_score:
                    best_score, best_moves = score, [move]
                elif score == best_score:
                    best_moves.append(move)
                beta = min(beta, best_score + _TIE_EPS)

        chosen = rng.choice(best_moves) if rng else best_moves[0]
        return chosen, best_score

    def _value(self, board, depth, alpha, beta, ply):
        """Recursive minimax with alpha-beta; White maximizes, Black minimizes."""
        self.nodes += 1
        done = terminal_score(board, ply)
        if done is not None:
            return done
        if depth == 0:
            return self.eval_fn(board)

        if board.turn == chess.WHITE:           # maximizing node
            value = -math.inf
            for move in self._moves(board):
                board.push(move)
                value = max(value, self._value(board, depth - 1, alpha, beta, ply + 1))
                board.pop()
                alpha = max(alpha, value)
                if self.use_ab and alpha >= beta:
                    break                        # beta cut-off
            return value
        else:                                    # minimizing node
            value = math.inf
            for move in self._moves(board):
                board.push(move)
                value = min(value, self._value(board, depth - 1, alpha, beta, ply + 1))
                board.pop()
                beta = min(beta, value)
                if self.use_ab and alpha >= beta:
                    break                        # alpha cut-off
            return value
