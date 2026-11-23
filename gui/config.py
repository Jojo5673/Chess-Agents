"""What the setup panel produces and the app consumes: who plays each colour."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import chess

DEPTH_CHOICES = (1, 2, 3, 4, 5)
TIME_CHOICES = (1.0, 3.0, 5.0, 10.0, 30.0)   # always a cap: the UI must never stall
DEFAULT_TIME_LIMIT = 5.0


@dataclass
class SideConfig:
    agent_key: Optional[str] = None          # None = human
    depth: int = 3
    time_limit_s: float = DEFAULT_TIME_LIMIT

    @property
    def is_human(self) -> bool:
        return self.agent_key is None


@dataclass
class GameConfig:
    white: SideConfig
    black: SideConfig

    @property
    def mode(self) -> str:
        """'hva' (human vs agent) or 'ava' (agent vs agent)."""
        return "ava" if not (self.white.is_human or self.black.is_human) else "hva"

    @property
    def human_color(self) -> Optional[chess.Color]:
        if self.white.is_human:
            return chess.WHITE
        if self.black.is_human:
            return chess.BLACK
        return None

    def side(self, color: chess.Color) -> SideConfig:
        return self.white if color == chess.WHITE else self.black


def clamp_depth(depth: int) -> int:
    return max(DEPTH_CHOICES[0], min(DEPTH_CHOICES[-1], int(depth or 3)))
