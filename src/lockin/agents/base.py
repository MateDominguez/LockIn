"""
Agent base utilities for the AI-Investment Swarm.

Provides:
  - invoke_agent(): structured prompt construction + LLM invocation with retry
  - BASE_RATE_TABLE: academic base rates for Bayesian priors used by agents

These utilities are shared across all real agents in Wave 2 (plans 03-02..03-08).
"""

from __future__ import annotations

import sys

import tenacity
from langchain_core.messages import HumanMessage, SystemMessage


def invoke_agent(
    llm,
    system_prompt: str,
    human_prompt: str,
    agent_name: str = "agent",
) -> str:
    """Invoke an LLM agent with structured system + human messages.

    Constructs the standard two-message format (SystemMessage + HumanMessage)
    used consistently across all agents, then calls llm.invoke() and returns
    the response content as a plain string.

    Wraps the call in a tenacity retry policy to handle transient rate-limit
    errors from the Gemini API without crashing the pipeline.

    Args:
        llm: A LangChain chat model instance (e.g. ChatGoogleGenerativeAI).
        system_prompt: Role and task instructions for the agent.
        human_prompt: The specific request/data for this invocation.
        agent_name: Name used in retry log messages (helps debugging).

    Returns:
        The LLM response as a plain string (response.content).

    Raises:
        tenacity.RetryError: After 3 failed attempts with rate-limit errors.
        Any other exceptions from llm.invoke() propagate immediately.
    """
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt),
    ]

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_fixed(30),
        retry=tenacity.retry_if_exception_message(match=r"(?i)(rate.?limit|quota|429)"),
        before_sleep=lambda retry_state: print(
            f"Rate limited on {agent_name}, retrying "
            f"(attempt {retry_state.attempt_number})...",
            file=sys.stderr,
        ),
        reraise=True,
    )
    def _invoke():
        response = llm.invoke(messages)
        return response.content

    return _invoke()


# ---------------------------------------------------------------------------
# Base rate table
#
# Placeholder academic base rates used by agents to ground Bayesian priors.
# Values marked None are to be filled in from backtesting during Phase 5
# (Validation). Sources cited where a published paper defines the statistic.
#
# Structure per entry:
#   threshold      — the condition that activates this entry
#   success_rate   — empirical win rate from live data (None = TBD)
#   academic_default — from published academic paper (None if no paper)
#   source         — citation
# ---------------------------------------------------------------------------

BASE_RATE_TABLE: dict[str, dict] = {
    "piotroski_high": {
        "threshold": ">=7",
        "success_rate": None,
        "source": "Piotroski (2000)",
        "academic_default": 0.62,
    },
    "piotroski_low": {
        "threshold": "<=3",
        "success_rate": None,
        "source": "backtest",
        "academic_default": None,
    },
    "zscore_safe": {
        "threshold": ">2.99",
        "success_rate": None,
        "source": "backtest",
        "academic_default": None,
    },
    "zscore_danger": {
        "threshold": "<1.81",
        "success_rate": None,
        "source": "backtest",
        "academic_default": None,
    },
    "mscore_clean": {
        "threshold": "<-2.22",
        "success_rate": None,
        "source": "Beneish (1999)",
        "academic_default": 0.55,
    },
    "mscore_suspicious": {
        "threshold": ">-2.22",
        "success_rate": None,
        "source": "backtest",
        "academic_default": None,
    },
    "vix_extreme_fear": {
        "threshold": ">30",
        "fwd_12m_positive": None,
        "source": "FRED",
        "academic_default": None,
    },
    "vix_extreme_greed": {
        "threshold": "<15",
        "fwd_12m_positive": None,
        "source": "FRED",
        "academic_default": None,
    },
    "expansion_regime": {
        "threshold": "GDP>0",
        "success_rate": None,
        "source": "FRED",
        "academic_default": 0.55,
    },
    "analyst_upgrade": {
        "threshold": "net>0",
        "success_rate": None,
        "source": "Jegadeesh (2004)",
        "academic_default": None,
    },
}
