"""lockin.agents — Agent functions for the investment swarm.

Imports are lazy via __getattr__ to avoid the circular import that arises from:
  lockin.agents.__init__
    -> lockin.agents.mock
      -> lockin.graph.state
        -> lockin.agents.types
          -> lockin.agents.__init__  (not yet ready)

Types and utilities are always importable directly from their submodules
(lockin.agents.types, lockin.agents.llm, lockin.agents.base) without triggering
this init and therefore without the circular reference.
"""

from __future__ import annotations

# Eagerly import types — they have no dependencies on graph or mock modules.
from lockin.agents.types import (
    ConfidenceModifier,
    DataCoverage,
    JudgeOutput,
    Signal,
    ValueDistribution,
)

__all__ = [
    # Real agent functions (Phase 3 implementations)
    "macro_oracle",
    "value_hunter",
    "bear",
    "strategist",
    "guardian",
    "judge",
    "optimizer",
    # Real agent registry (maps names to callables)
    "REAL_AGENTS",
    # Mock agents (Phase 1 stubs — backward compatibility)
    "MOCK_AGENTS",
    "mock_macro_oracle",
    "mock_value_hunter",
    "mock_bear",
    "mock_strategist",
    "mock_guardian",
    "mock_judge",
    "mock_optimizer",
    # LLM factory
    "get_llm",
    "MODEL_PRO",
    "MODEL_FLASH",
    # Agent base utilities
    "invoke_agent",
    "BASE_RATE_TABLE",
    # Typed output contracts
    "ValueDistribution",
    "ConfidenceModifier",
    "Signal",
    "DataCoverage",
    "JudgeOutput",
]

_MOCK_NAMES = {
    "MOCK_AGENTS",
    "mock_macro_oracle",
    "mock_value_hunter",
    "mock_bear",
    "mock_strategist",
    "mock_guardian",
    "mock_judge",
    "mock_optimizer",
}

_LLM_NAMES = {"get_llm", "MODEL_PRO", "MODEL_FLASH"}

_BASE_NAMES = {"invoke_agent", "BASE_RATE_TABLE"}

# Real agent names — deferred to break circular imports (same pattern as mocks)
_REAL_AGENT_NAMES = {
    "macro_oracle",
    "value_hunter",
    "bear",
    "strategist",
    "guardian",
    "judge",
    "optimizer",
    "REAL_AGENTS",
}


def __getattr__(name: str):
    """Lazy-import agent modules to break circular imports.

    Mock agents import lockin.graph.state; graph.state imports lockin.agents.types.
    By deferring mock/llm/base/real-agent imports until first attribute access, we allow
    types to be fully initialised before mock or graph modules are touched.
    """
    if name in _MOCK_NAMES:
        from lockin.agents import mock as _mock
        return getattr(_mock, name)
    if name in _LLM_NAMES:
        from lockin.agents import llm as _llm
        return getattr(_llm, name)
    if name in _BASE_NAMES:
        from lockin.agents import base as _base
        return getattr(_base, name)
    if name in _REAL_AGENT_NAMES:
        if name == "REAL_AGENTS":
            # Build registry from all real agent modules
            from lockin.agents.macro_oracle import macro_oracle as _macro_oracle
            from lockin.agents.value_hunter import value_hunter as _value_hunter
            from lockin.agents.bear import bear as _bear
            from lockin.agents.strategist import strategist as _strategist
            from lockin.agents.guardian import guardian as _guardian
            from lockin.agents.judge import judge as _judge
            from lockin.agents.optimizer import optimizer as _optimizer
            return {
                "macro_oracle": _macro_oracle,
                "value_hunter": _value_hunter,
                "bear": _bear,
                "strategist": _strategist,
                "guardian": _guardian,
                "judge": _judge,
                "optimizer": _optimizer,
            }
        # Individual real agent imports
        if name == "macro_oracle":
            from lockin.agents.macro_oracle import macro_oracle as _fn
            return _fn
        if name == "value_hunter":
            from lockin.agents.value_hunter import value_hunter as _fn
            return _fn
        if name == "bear":
            from lockin.agents.bear import bear as _fn
            return _fn
        if name == "strategist":
            from lockin.agents.strategist import strategist as _fn
            return _fn
        if name == "guardian":
            from lockin.agents.guardian import guardian as _fn
            return _fn
        if name == "judge":
            from lockin.agents.judge import judge as _fn
            return _fn
        if name == "optimizer":
            from lockin.agents.optimizer import optimizer as _fn
            return _fn
    raise AttributeError(f"module 'lockin.agents' has no attribute {name!r}")
