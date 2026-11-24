"""
Agent registry that everything references to know which agents exist
"""
from dataclasses import dataclass
from types import ModuleType
from typing import Callable, Dict, List, Optional

from engine.agent import Agent, MinimaxAgent, RandomAgent

from . import aggression_agent, material_agent, structure_agent


@dataclass(frozen=True)
class AgentSpec:
    key: str                      # short id used on the command line / in code
    name: str                     # display name
    description: str              # strategic identity in plain language
    default_depth: int            # 0 for agents that don't search
    factory: Callable[[int, Optional[int], Optional[float]], Agent]


_REGISTRY: Dict[str, AgentSpec] = {}


def register(spec: AgentSpec) -> None:
    _REGISTRY[spec.key] = spec


def register_eval_agent(key: str, module: ModuleType) -> None:
    """Register an agent module that contains a NAME, DESCRIPTION, DEFAULT_DEPTH and evaluate(board) function."""
    def factory(
        depth: int,
        seed: Optional[int],
        time_limit_s: Optional[float],
    ) -> Agent:
        return MinimaxAgent(module.NAME, module.evaluate, depth,
                            seed=seed, description=module.DESCRIPTION,
                            time_limit_s=time_limit_s)
    register(AgentSpec(key, module.NAME, module.DESCRIPTION,
                       module.DEFAULT_DEPTH, factory))


def available_agents() -> List[AgentSpec]:
    return list(_REGISTRY.values())


def create_agent(key: str, depth: Optional[int] = None,
                 seed: Optional[int] = None,
                 time_limit_s: Optional[float] = None) -> Agent:
    """Build a fresh agent instance. `depth` overrides the agent's default."""
    if key not in _REGISTRY:
        raise KeyError(f"Unknown agent {key!r}. Available: {', '.join(_REGISTRY)}")
    spec = _REGISTRY[key]
    return spec.factory(
        depth if depth is not None else spec.default_depth, seed, time_limit_s)


# ---- registrations --------------------------------------------------------
register(AgentSpec("random", "Random", "Plays random legal moves.", 0,
                   lambda depth, seed, time_limit_s: RandomAgent("Random", seed=seed)))
register_eval_agent("material", material_agent)
register_eval_agent("structure", structure_agent)
register(AgentSpec("aggression", aggression_agent.NAME, aggression_agent.DESCRIPTION,
                   aggression_agent.DEFAULT_DEPTH, aggression_agent.create))
