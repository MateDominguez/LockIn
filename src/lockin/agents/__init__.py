"""lockin.agents — Agent functions for the investment swarm."""

from lockin.agents.base import BASE_RATE_TABLE, invoke_agent
from lockin.agents.llm import MODEL_FLASH, MODEL_PRO, get_llm
from lockin.agents.mock import (
    MOCK_AGENTS,
    mock_bear,
    mock_guardian,
    mock_judge,
    mock_macro_oracle,
    mock_optimizer,
    mock_strategist,
    mock_value_hunter,
)
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
