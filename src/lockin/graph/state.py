"""
InvestmentState TypedDict — Central state schema for the LangGraph StateGraph.

Using total=False so LangGraph can merge partial state updates from each agent.
Each agent returns only the fields it owns; LangGraph merges them into the full state.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TypedDict


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
    bull_valuation_distribution: dict
    bull_thesis: str
    bull_refined_thesis: str
    bull_defense: str
    bull_confidence: float
    quality_metrics: dict

    # Bear outputs
    bear_challenges: list
    bear_valuation_distribution: dict
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

    # -----------------------------------------------------------------------
    # Risk management  (Guardian)
    # -----------------------------------------------------------------------
    guardian_risk_report: dict
    guardian_veto: bool
    guardian_veto_reason: str
    guardian_sizing: float
    guardian_margin_adjustments: dict

    # -----------------------------------------------------------------------
    # Consensus  (Judge)
    # -----------------------------------------------------------------------
    judge_consensus_distribution: dict
    judge_recommendation: str
    judge_conviction: float
    judge_margin: float
    judge_price_target: float
    judge_narrative: str
    judge_hitl: bool
    judge_hitl_reason: str

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
