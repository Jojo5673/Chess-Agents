"""
template for a new agent. 
Copy this file, fill in NAME / DESCRIPTION and write `evaluate`, 
then register it in agents/__init__.py 
eg. register_eval_agent("structure", structure_agent)

Rules for `evaluate(board)`:
  * Return a score from WHITE's perspective (positive = good for White).
    For a feature you compute per side, do  (white_value - black_value).
  * Do not worry about checkmate/stalemate/draws; the search handles them.
  * Never modify `board` (no push/pop). Read-only helpers like
    board.pieces(), board.attackers(), board.is_attacked_by() are fine.
  * Speed matters: it is called at every leaf of the search tree.
"""
import chess

from engine.evaluation import material

NAME = "Template"
DESCRIPTION = "Describe this agent's strategic identity here."
DEFAULT_DEPTH = 3

# EXAMPLE_WEIGHT = 10


def evaluate(board: chess.Board) -> float:
    score = material(board)
    # TODO: add this agent's own features here, e.g.
    # score += EXAMPLE_WEIGHT * (white_feature - black_feature)
    return score
