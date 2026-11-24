"""
Baseline reference agent that counts material and nothing else.

Used as an example of the module convention for every agent:
    NAME            display name shown in the GUI / match logs
    DESCRIPTION     one-line plain-language strategic identity
    DEFAULT_DEPTH   search depth used unless the caller overrides it
    evaluate(board) White-perspective score for a NON-terminal position
"""
import chess

from engine.evaluation import material

NAME = "Material"
DESCRIPTION = "Baseline: values only the material on the board."
DEFAULT_DEPTH = 3


def evaluate(board: chess.Board) -> float:
    return material(board)
