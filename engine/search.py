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
* Conservative static-exchange pruning and a repetition-aware transposition table.
* Optional iterative deepening with a per-search time limit.
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
from typing import Dict, List, Optional, Tuple

import chess

from .evaluation import EvalFn, MATE_SCORE, PIECE_VALUES

# Root moves within this margin of the best score count as ties.
_TIE_EPS = 1e-6
# Bound extensions through long checking sequences.
_MAX_QUIESCENCE_PLY = 4
_SEE_PRUNE_MARGIN = 150
_MAX_TT_ENTRIES = 50_000

_TT_EXACT = 0
_TT_LOWER = 1
_TT_UPPER = 2
_MATE_TT_THRESHOLD = MATE_SCORE - 1_000

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


@dataclass
class _TTEntry:
    depth: int
    score: float
    bound: int
    best_move: Optional[chess.Move]


class _SearchTimeout(Exception):
    pass


def find_best_move(
    board: chess.Board,
    depth: int,
    eval_fn: EvalFn,
    *,
    use_alpha_beta: bool = True,
    order_moves: bool = True,
    rng: Optional[random.Random] = None,
    randomization_margin: float = 0.0,
    time_limit_s: Optional[float] = None,
) -> SearchResult:
    """Search `depth` plies and return a best or near-best move.

    NOTE: this pushes/pops moves on `board` while searching (it is restored
    before returning). Pass a copy if another thread is reading the board.
    When `rng` and a positive `randomization_margin` are provided, choose
    randomly among moves within that margin of the best root score.
    With `time_limit_s`, return the last completed depth; if even depth 1
    cannot finish, return a legal fallback with depth 0.
    """
    if depth < 1:
        raise ValueError("depth must be >= 1")
    if not math.isfinite(randomization_margin) or randomization_margin < 0:
        raise ValueError("randomization_margin must be a finite non-negative score")
    if (time_limit_s is not None
            and (not math.isfinite(time_limit_s) or time_limit_s <= 0)):
        raise ValueError("time_limit_s must be a finite positive number or None")

    start = time.perf_counter()
    deadline = start + time_limit_s if time_limit_s is not None else None
    searcher = _Searcher(eval_fn, use_alpha_beta, order_moves, deadline)
    searcher._initialize_history(board)
    if deadline is None:
        move, score = searcher.search_root(board, depth, rng, randomization_margin)
        completed_depth = depth
    else:
        move, score, completed_depth = searcher.search_iterative(
            board, depth, rng, randomization_margin)
    return SearchResult(
        move, score, completed_depth, searcher.nodes, time.perf_counter() - start,
    )


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


def _static_exchange_eval(board: chess.Board, move: chess.Move) -> int:
    """Estimate the material balance of a capture sequence on its target square."""
    if not board.is_capture(move):
        return 0

    exchange = board.copy(stack=False)
    target = move.to_square
    victim_type = board.piece_type_at(target) or chess.PAWN
    gains = [PIECE_VALUES[victim_type]]
    if move.promotion:
        gains[0] += PIECE_VALUES[move.promotion] - PIECE_VALUES[chess.PAWN]

    exchange.push(move)
    occupant_type = move.promotion or board.piece_type_at(move.from_square)
    if occupant_type is None:
        return gains[0]

    while len(gains) < 32:
        least_attacker = None
        least_value = math.inf
        for from_square in exchange.attackers(exchange.turn, target):
            attacker_type = exchange.piece_type_at(from_square)
            promotion = (
                chess.QUEEN
                if attacker_type == chess.PAWN
                and chess.square_rank(target) in (0, 7)
                else None
            )
            recapture = chess.Move(from_square, target, promotion=promotion)
            if (PIECE_VALUES[attacker_type] < least_value
                    and exchange.is_legal(recapture)):
                least_attacker = recapture
                least_value = PIECE_VALUES[attacker_type]

        if least_attacker is None:
            break

        gains.append(PIECE_VALUES[occupant_type] - gains[-1])
        if least_attacker.promotion:
            gains[-1] += (
                PIECE_VALUES[least_attacker.promotion] - PIECE_VALUES[chess.PAWN])
        occupant_type = (
            least_attacker.promotion
            or exchange.piece_type_at(least_attacker.from_square)
        )
        exchange.push(least_attacker)

    for index in range(len(gains) - 1, 0, -1):
        gains[index - 1] = -max(-gains[index - 1], gains[index])
    return gains[0]


class _Searcher:
    def __init__(
        self,
        eval_fn: EvalFn,
        use_alpha_beta: bool,
        order_moves: bool,
        deadline: Optional[float] = None,
    ):
        self.eval_fn = eval_fn
        self.use_ab = use_alpha_beta
        self.order = order_moves
        self.nodes = 0
        self.deadline = deadline
        self._timeout_enabled = False
        self._repetition_counts: Dict[tuple, int] = {}
        self._repetition_stack: List[Tuple[bool, Dict[tuple, int], tuple, int]] = []
        self._tt: Dict[tuple, _TTEntry] = {}

    def _initialize_history(self, board: chess.Board) -> None:
        replay = board.root()
        counts = {replay._transposition_key(): 1}
        for move in board.move_stack:
            irreversible = replay.is_irreversible(move)
            replay.push(move)
            key = replay._transposition_key()
            if irreversible:
                counts = {key: 1}
            else:
                counts[key] = counts.get(key, 0) + 1
        self._repetition_counts = counts

    def _push(self, board: chess.Board, move: chess.Move) -> None:
        irreversible = board.is_irreversible(move)
        previous_counts = self._repetition_counts
        if irreversible:
            self._repetition_counts = {}
        board.push(move)
        key = board._transposition_key()
        previous_count = self._repetition_counts.get(key, 0)
        self._repetition_counts[key] = previous_count + 1
        self._repetition_stack.append(
            (irreversible, previous_counts, key, previous_count))

    def _pop(self, board: chess.Board) -> None:
        board.pop()
        irreversible, previous_counts, key, previous_count = self._repetition_stack.pop()
        if irreversible:
            self._repetition_counts = previous_counts
        elif previous_count:
            self._repetition_counts[key] = previous_count
        else:
            del self._repetition_counts[key]

    def _tt_key(self, board: chess.Board) -> tuple:
        history = frozenset(self._repetition_counts.items())
        return board._transposition_key(), board.halfmove_clock, history

    def _check_time(self) -> None:
        if (self._timeout_enabled and self.deadline is not None
                and time.perf_counter() >= self.deadline):
            raise _SearchTimeout

    def _visit_node(self) -> None:
        self.nodes += 1
        if self.nodes % 64 == 0:
            self._check_time()

    def _evaluate(self, board: chess.Board) -> float:
        self._check_time()
        score = self.eval_fn(board)
        self._check_time()
        return score

    @staticmethod
    def _score_to_tt(score: float, ply: int) -> float:
        if score >= _MATE_TT_THRESHOLD:
            return score + ply
        if score <= -_MATE_TT_THRESHOLD:
            return score - ply
        return score

    @staticmethod
    def _score_from_tt(score: float, ply: int) -> float:
        if score >= _MATE_TT_THRESHOLD:
            return score - ply
        if score <= -_MATE_TT_THRESHOLD:
            return score + ply
        return score

    def _store_tt(self, key: tuple, entry: _TTEntry) -> None:
        current = self._tt.get(key)
        if current is None and len(self._tt) >= _MAX_TT_ENTRIES:
            return
        if current is None or entry.depth >= current.depth:
            self._tt[key] = entry

    def search_iterative(self, board, depth, rng, randomization_margin):
        """Return the last completed iteration or a legal fallback."""
        self._timeout_enabled = True
        done = terminal_score(board, 0)
        if done is not None:
            return None, done, 0

        fallback = self._moves(board)[0]
        move, score, completed_depth = fallback, 0.0, 0
        for current_depth in range(1, depth + 1):
            try:
                self._check_time()
                move, score = self.search_root(
                    board, current_depth, rng, randomization_margin)
                completed_depth = current_depth
            except _SearchTimeout:
                break

        return move, score, completed_depth

    def _moves(
        self,
        board: chess.Board,
        tactical_only: bool = False,
        tt_move: Optional[chess.Move] = None,
    ) -> List[chess.Move]:
        moves = list(board.legal_moves)
        if tactical_only:
            moves = [move for move in moves
                     if board.is_capture(move) or move.promotion]
        if self.order:
            moves.sort(
                key=lambda m: (m == tt_move, _move_priority(board, m)),
                reverse=True,
            )
        return moves

    def search_root(self, board, depth, rng, randomization_margin=0.0):
        """Root of the search: also tracks ties so we can pick among them."""
        self._visit_node()
        done = terminal_score(board, 0)
        if done is not None:
            return None, done

        maximizing = board.turn == chess.WHITE
        root_key = self._tt_key(board)
        root_entry = self._tt.get(root_key)
        tt_move = root_entry.best_move if root_entry else None
        moves = self._moves(board, tt_move=tt_move)
        if randomization_margin > 0 and rng:
            scored_moves = []
            for move in moves:
                self._check_time()
                self._push(board, move)
                try:
                    score = self._value(board, depth - 1, -math.inf, math.inf, 1)
                finally:
                    self._pop(board)
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
            best_move = next(
                move for move, score in scored_moves if score == best_score)
            self._store_tt(root_key, _TTEntry(
                depth, self._score_to_tt(best_score, 0), _TT_EXACT, best_move))
            return chosen_move, chosen_score

        alpha, beta = -math.inf, math.inf
        best_score = -math.inf if maximizing else math.inf
        best_moves: List[chess.Move] = []

        for move in moves:
            self._check_time()
            self._push(board, move)
            try:
                score = self._value(board, depth - 1, alpha, beta, 1)
            finally:
                self._pop(board)

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
        self._store_tt(root_key, _TTEntry(
            depth, self._score_to_tt(best_score, 0), _TT_EXACT, best_moves[0]))
        return chosen, best_score

    def _value(self, board, depth, alpha, beta, ply):
        """Recursive minimax with alpha-beta; White maximizes, Black minimizes."""
        if depth == 0:
            return self._quiescence(board, alpha, beta, ply, 0)

        self._visit_node()
        done = terminal_score(board, ply)
        if done is not None:
            return done

        alpha_original, beta_original = alpha, beta
        key = self._tt_key(board)
        entry = self._tt.get(key)
        tt_move = entry.best_move if entry else None
        if entry is not None and entry.depth >= depth:
            tt_score = self._score_from_tt(entry.score, ply)
            if entry.bound == _TT_EXACT:
                return tt_score
            if self.use_ab:
                if entry.bound == _TT_LOWER:
                    alpha = max(alpha, tt_score)
                else:
                    beta = min(beta, tt_score)
                if alpha >= beta:
                    return tt_score

        best_move = None
        if board.turn == chess.WHITE:           # maximizing node
            value = -math.inf
            for move in self._moves(board, tt_move=tt_move):
                self._push(board, move)
                try:
                    child = self._value(board, depth - 1, alpha, beta, ply + 1)
                finally:
                    self._pop(board)
                if child > value:
                    value, best_move = child, move
                alpha = max(alpha, value)
                if self.use_ab and alpha >= beta:
                    break                        # beta cut-off
        else:                                    # minimizing node
            value = math.inf
            for move in self._moves(board, tt_move=tt_move):
                self._push(board, move)
                try:
                    child = self._value(board, depth - 1, alpha, beta, ply + 1)
                finally:
                    self._pop(board)
                if child < value:
                    value, best_move = child, move
                beta = min(beta, value)
                if self.use_ab and alpha >= beta:
                    break                        # alpha cut-off

        if not self.use_ab:
            bound = _TT_EXACT
        elif value <= alpha_original:
            bound = _TT_UPPER
        elif value >= beta_original:
            bound = _TT_LOWER
        else:
            bound = _TT_EXACT
        self._store_tt(key, _TTEntry(
            depth, self._score_to_tt(value, ply), bound, best_move))
        return value

    def _prune_quiescence_capture(self, board, move):
        if move.promotion or board.gives_check(move):
            return False
        return _static_exchange_eval(board, move) < -_SEE_PRUNE_MARGIN

    def _quiescence(self, board, alpha, beta, ply, qply):
        """Search captures and promotions until the position is quiet."""
        self._visit_node()
        done = terminal_score(board, ply)
        if done is not None:
            return done

        in_check = board.is_check()
        maximizing = board.turn == chess.WHITE
        stand_pat = None if in_check else self._evaluate(board)

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
                self._push(board, move)
                try:
                    self._visit_node()
                    done = terminal_score(board, ply + 1)
                    score = done if done is not None else self._evaluate(board)
                finally:
                    self._pop(board)
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
            if (not in_check and board.is_capture(move)
                    and self._prune_quiescence_capture(board, move)):
                continue
            self._push(board, move)
            try:
                score = self._quiescence(board, alpha, beta, ply + 1, qply + 1)
            finally:
                self._pop(board)
            if maximizing:
                value = max(value, score)
                alpha = max(alpha, value)
            else:
                value = min(value, score)
                beta = min(beta, value)
            if self.use_ab and alpha >= beta:
                break
        return value
