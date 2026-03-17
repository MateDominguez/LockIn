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
    # Mock agents (Phase 1 stubs)
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


def __getattr__(name: str):
    """Lazy-import agent modules to break circular imports.

    Mock agents import lockin.graph.state; graph.state imports lockin.agents.types.
    By deferring mock/llm/base imports until first attribute access, we allow
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
    raise AttributeError(f"module 'lockin.agents' has no attribute {name!r}")
