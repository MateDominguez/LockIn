"""
InvestmentState TypedDict — Central state schema for the LangGraph StateGraph.

Using total=False so LangGraph can merge partial state updates from each agent.
Each agent returns only the fields it owns; LangGraph merges them into the full state.

Typed agent output fields (oracle_modifier, guardian_modifier, strategist_modifier,
judge_output, bull_valuation_distribution, bear_valuation_distribution) use
TYPE_CHECKING-guarded forward references so the dataclasses are only resolved
by type checkers (mypy/pyright) and not at runtime, avoiding circular imports.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, TypedDict

# Runtime imports — safe because lockin.graph.__init__ uses lazy __getattr__
# for builder symbols, breaking the circular dependency chain.
from lockin.agents.types import ConfidenceModifier, JudgeOutput, ValueDistribution


class InvestmentState(TypedDict, total=False):
    # -----------------------------------------------------------------------
    # Request metadata
    # -----------------------------------------------------------------------
    request_id: str
    timestamp: str
    asset_ticker: str

    # -----------------------------------------------------------------------
    # Macro context  (Macro Oracle)
    # -----------------------------------------------------------------------
    macro_regime: dict
    macro_confidence: float
    macro_narrative: str

    # -----------------------------------------------------------------------
    # Bull-Bear dialectic  (Value Hunter + Bear)
    # -----------------------------------------------------------------------
    bull_iteration: int

    # Value Hunter outputs
    bull_valuation_distribution: Optional[ValueDistribution]
    bull_thesis: str
    bull_refined_thesis: str
    bull_defense: str
    bull_confidence: float
    quality_metrics: dict

    # Bear outputs
    bear_challenges: list
    bear_valuation_distribution: Optional[ValueDistribution]
    bear_thesis: str
    bear_red_flags: list
    bear_conviction: float

    # -----------------------------------------------------------------------
    # Strategic analysis  (Strategist)
    # -----------------------------------------------------------------------
    strategist_veto: float
    strategist_sentiment: float
    strategic_signals: dict
    strategist_narrative: str
    strategist_confidence: float
    strategist_modifier: Optional[ConfidenceModifier]

    # -----------------------------------------------------------------------
    # Risk management  (Guardian)
    # -----------------------------------------------------------------------
    guardian_risk_report: dict
    guardian_veto: bool
    guardian_veto_reason: str
    guardian_sizing: float
    guardian_margin_adjustments: dict
    guardian_modifier: Optional[ConfidenceModifier]

    # -----------------------------------------------------------------------
    # Consensus  (Judge)
    # -----------------------------------------------------------------------
    oracle_modifier: Optional[ConfidenceModifier]
    judge_consensus_distribution: dict
    judge_recommendation: str
    judge_conviction: float
    judge_margin: float
    judge_price_target: float
    judge_narrative: str
    judge_hitl: bool
    judge_hitl_reason: str
    judge_output: Optional[JudgeOutput]

    # -----------------------------------------------------------------------
    # Portfolio construction  (Optimizer)
    # -----------------------------------------------------------------------
    optimizer_portfolio: dict
    optimizer_sectors: dict
    optimizer_rebalancing: list
    optimizer_metrics: dict
    optimizer_narrative: str

    # -----------------------------------------------------------------------
    # Audit trail
    # -----------------------------------------------------------------------
    citations: list
    human_review: dict


def create_initial_state(ticker: str) -> InvestmentState:
    """Return a minimal valid initial InvestmentState for a given ticker.

    LangGraph merges agent outputs on top of this starting dict, so only the
    fields required before the first agent runs need to be set here.
    """
    return InvestmentState(
        request_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        asset_ticker=ticker,
        bull_iteration=0,
    )
