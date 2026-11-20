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
* Quiescence search at the horizon to resolve captures and check evasions.
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
# Bound extensions through long checking sequences.
_MAX_QUIESCENCE_PLY = 4

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
    randomization_margin: float = 0.0,
) -> SearchResult:
    """Search `depth` plies and return a best or near-best move.

    NOTE: this pushes/pops moves on `board` while searching (it is restored
    before returning). Pass a copy if another thread is reading the board.
    When `rng` and a positive `randomization_margin` are provided, choose
    randomly among moves within that margin of the best root score.
    """
    if depth < 1:
        raise ValueError("depth must be >= 1")
    if not math.isfinite(randomization_margin) or randomization_margin < 0:
        raise ValueError("randomization_margin must be a finite non-negative score")
    searcher = _Searcher(eval_fn, use_alpha_beta, order_moves)
    start = time.perf_counter()
    move, score = searcher.search_root(board, depth, rng, randomization_margin)
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
            or board.is_seventyfive_moves()
            or board.is_fivefold_repetition()):
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

    def _moves(self, board: chess.Board, tactical_only: bool = False) -> List[chess.Move]:
        moves = list(board.legal_moves)
        if tactical_only:
            moves = [move for move in moves
                     if board.is_capture(move) or move.promotion]
        if self.order:
            moves.sort(key=lambda m: _move_priority(board, m), reverse=True)
        return moves

    def search_root(self, board, depth, rng, randomization_margin=0.0):
        """Root of the search: also tracks ties so we can pick among them."""
        self.nodes += 1
        done = terminal_score(board, 0)
        if done is not None:
            return None, done

        maximizing = board.turn == chess.WHITE
        if randomization_margin > 0 and rng:
            scored_moves = []
            for move in self._moves(board):
                board.push(move)
                score = self._value(board, depth - 1, -math.inf, math.inf, 1)
                board.pop()
                scored_moves.append((move, score))

            best_score = (
                max(score for _, score in scored_moves)
                if maximizing else min(score for _, score in scored_moves)
            )
            if maximizing:
                near_best = [
                    (move, score) for move, score in scored_moves
                    if score >= best_score - randomization_margin
                ]
            else:
                near_best = [
                    (move, score) for move, score in scored_moves
                    if score <= best_score + randomization_margin
                ]
            chosen_move, chosen_score = rng.choice(near_best)
            return chosen_move, chosen_score

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
        if depth == 0:
            return self._quiescence(board, alpha, beta, ply, 0)

        self.nodes += 1
        done = terminal_score(board, ply)
        if done is not None:
            return done

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

    def _quiescence(self, board, alpha, beta, ply, qply):
        """Search captures and promotions until the position is quiet."""
        self.nodes += 1
        done = terminal_score(board, ply)
        if done is not None:
            return done

        in_check = board.is_check()
        maximizing = board.turn == chess.WHITE
        stand_pat = None if in_check else self.eval_fn(board)

        if stand_pat is not None:
            if maximizing:
                if self.use_ab and stand_pat >= beta:
                    return stand_pat
                alpha = max(alpha, stand_pat)
                value = stand_pat
            else:
                if self.use_ab and stand_pat <= alpha:
                    return stand_pat
                beta = min(beta, stand_pat)
                value = stand_pat
        else:
            value = -math.inf if maximizing else math.inf

        moves = self._moves(board, tactical_only=not in_check)

        if qply >= _MAX_QUIESCENCE_PLY:
            if not in_check:
                return value

            # At the safety limit, still make a legal check evasion before
            # falling back to static evaluation.
            for move in moves:
                board.push(move)
                self.nodes += 1
                done = terminal_score(board, ply + 1)
                score = done if done is not None else self.eval_fn(board)
                board.pop()
                if maximizing:
                    value = max(value, score)
                    alpha = max(alpha, value)
                else:
                    value = min(value, score)
                    beta = min(beta, value)
                if self.use_ab and alpha >= beta:
                    break
            return value

        for move in moves:
            board.push(move)
            score = self._quiescence(board, alpha, beta, ply + 1, qply + 1)
            board.pop()
            if maximizing:
                value = max(value, score)
                alpha = max(alpha, value)
            else:
                value = min(value, score)
                beta = min(beta, value)
            if self.use_ab and alpha >= beta:
                break
        return value
