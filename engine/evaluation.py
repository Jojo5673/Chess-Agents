"""
Shared evaluation vocabulary for every agent.

CONVENTION (both partners must follow this):
    An evaluation function takes a chess.Board and returns a number from
    WHITE's perspective:  positive = good for White, negative = good for Black.
    It is only called on NON-terminal positions. Checkmate, stalemate and draw
    detection are handled by the search, so evaluations never need to deal
    with them.
"""
from typing import Callable

import chess

# An evaluation function: board -> score (White's perspective).
EvalFn = Callable[[chess.Board], float]

# Score magnitude for a forced checkmate. The search subtracts the ply count
# so that faster mates score higher than slower ones.
MATE_SCORE = 100_000

# Standard centipawn-style piece values. Shared so both agents agree on material.
PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,  # the king is never captured, so it carries no material value
}


def material(board: chess.Board) -> int:
    """Material balance from White's perspective (White minus Black)."""
    total = 0
    for piece_type, value in PIECE_VALUES.items():
        if value:
            white = len(board.pieces(piece_type, chess.WHITE))
            black = len(board.pieces(piece_type, chess.BLACK))
            total += value * (white - black)
    return total
