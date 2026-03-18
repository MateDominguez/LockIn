"""
Judge agent — Phase 3, Plan 08.

The Judge is the consensus builder in the AI-Investment Swarm.  It operates on two
independent axes from the Notion Judge spec v1.0:
  (1) How much is it worth?  — via Log Pool of Bull/Bear ValueDistributions
  (2) How likely is the thesis correct?  — via empirical base rate probability

Design decisions:
  - Pure math delegated entirely to judge_math.py (no algorithm logic here).
  - LLM (MODEL_PRO) used ONLY for narrative synthesis — not for scoring.
  - HITL triggers: p_final < 0.40 OR circuit_breaker (NOT < 0.50 — see note below).
  - RAG citations: retrieve_with_citations(k=3), wrapped in try/except for graceful
    degradation when Supabase is not configured.
  - yfinance current_price: falls back to valor_mediano if unavailable.
  - Default ConfidenceModifier (margin=0, variance=0, circuit_breaker=False) used
    when any modifier is missing from state.

HITL threshold note:
  The old Foundation scaffold used conviction < 0.50 as the HITL trigger (plan 01-03).
  The real Judge uses p_final < 0.40 per Notion spec v1.0.  This is intentional and
  has an explicit regression guard in test_judge.py (test_judge_no_hitl_p_045).
"""

from __future__ import annotations

import sys
from typing import Any

import yfinance as yf
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from lockin.agents.judge_math import run_judge_algorithm
from lockin.agents.llm import MODEL_PRO, get_llm
from lockin.agents.types import ConfidenceModifier, DataCoverage, JudgeOutput, ValueDistribution
from lockin.graph.state import InvestmentState
from lockin.rag.retriever import retrieve_with_citations


# ---------------------------------------------------------------------------
# HITL threshold (Notion spec v1.0 — do NOT change without spec update)
# ---------------------------------------------------------------------------

_HITL_PROBABILITY_THRESHOLD = 0.40  # p_final < 0.40 triggers HITL


# ---------------------------------------------------------------------------
# Default ConfidenceModifier (neutral — no adjustments)
# ---------------------------------------------------------------------------

def _neutral_modifier() -> ConfidenceModifier:
    """Return a neutral ConfidenceModifier for missing state fields."""
    return ConfidenceModifier(
        margin_adjustment=0.0,
        variance_adjustment=0.0,
        circuit_breaker=False,
        signals=[],
        data_coverage=DataCoverage(),
    )


# ---------------------------------------------------------------------------
# System prompt for LLM narrative synthesis
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a judicial investment analyst synthesizing Bull and Bear arguments "
    "per the Bayesian Consensus framework. "
    "Your analysis must be objective, evidence-driven, and traceable. "
    "Provide:\n"
    "  1) Your recommendation (BUY / HOLD / PASS) with concrete reasoning\n"
    "  2) Key factors from the Bull case that support investment\n"
    "  3) Key factors from the Bear case that represent risks\n"
    "  4) What specific developments would change your recommendation\n"
    "  5) Map of Ignorance summary — the known unknowns that could invalidate the thesis\n\n"
    "Be direct and data-driven. Maximum 4 paragraphs. Do not recalculate any numbers."
)


# ---------------------------------------------------------------------------
# Main agent function
# ---------------------------------------------------------------------------


def judge(state: InvestmentState, config: RunnableConfig) -> dict:
    """Judge agent — synthesize Bull/Bear debate into a Bayesian consensus.

    Reads typed inputs from state, delegates math to run_judge_algorithm(),
    determines HITL triggers, retrieves RAG citations, and calls the LLM for
    a narrative synthesis.

    Steps:
      1. Extract typed inputs from state (ValueDistribution, ConfidenceModifier).
      2. Get current_price from yfinance (fallback to valor_mediano).
      3. Call run_judge_algorithm() — pure math, no side effects.
      4. Determine HITL: p_final < 0.40 OR circuit_breaker.
      5. Retrieve RAG citations (graceful degradation if Supabase missing).
      6. Call LLM (MODEL_PRO) for narrative synthesis.
      7. Return state update dict.

    Args:
        state:  InvestmentState TypedDict.
        config: LangGraph RunnableConfig (unused but required by contract).

    Returns:
        Partial state dict with all judge_* fields populated.
    """
    ticker = state.get("asset_ticker", "UNKNOWN")

    # ------------------------------------------------------------------
    # Step 1: Extract typed inputs from state
    # ------------------------------------------------------------------
    bull_dist: ValueDistribution | None = state.get("bull_valuation_distribution")
    bear_dist: ValueDistribution | None = state.get("bear_valuation_distribution")
    oracle_mod: ConfidenceModifier = state.get("oracle_modifier") or _neutral_modifier()
    guardian_mod: ConfidenceModifier = state.get("guardian_modifier") or _neutral_modifier()
    strategist_mod: ConfidenceModifier = state.get("strategist_modifier") or _neutral_modifier()

    # Fallback distributions if agents haven't run (safety net)
    if bull_dist is None:
        bull_dist = ValueDistribution(
            expected_value=100.0, std_dev=20.0, p10=70.0, p50=100.0, p90=130.0,
            confidence=0.5,
        )
    if bear_dist is None:
        bear_dist = ValueDistribution(
            expected_value=80.0, std_dev=20.0, p10=50.0, p50=80.0, p90=110.0,
            confidence=0.5,
        )

    # ------------------------------------------------------------------
    # Step 2: Get current_price from yfinance
    # ------------------------------------------------------------------
    current_price: float | None = None
    try:
        yf_ticker = yf.Ticker(ticker)
        info = yf_ticker.info or {}
        raw_price = info.get("currentPrice") or info.get("regularMarketPrice")
        if raw_price is not None:
            current_price = float(raw_price)
    except Exception as exc:  # noqa: BLE001
        print(
            f"judge: yfinance price fetch failed for {ticker} — {exc}",
            file=sys.stderr,
        )

    # ------------------------------------------------------------------
    # Step 3: Run the 7-step algorithm
    # ------------------------------------------------------------------
    # We need a preliminary valor_mediano for current_price fallback.
    # Run algorithm with placeholder price first if needed.
    import math
    _placeholder = math.exp(
        0.5 * (
            (math.log(bull_dist.expected_value) if bull_dist.expected_value > 0 else 0)
            + (math.log(bear_dist.expected_value) if bear_dist.expected_value > 0 else 0)
        )
    )
    if current_price is None or current_price <= 0:
        current_price = _placeholder  # best estimate when yfinance unavailable

    result: JudgeOutput = run_judge_algorithm(
        bull_dist=bull_dist,
        bear_dist=bear_dist,
        oracle_modifier=oracle_mod,
        guardian_modifier=guardian_mod,
        strategist_modifier=strategist_mod,
        current_price=current_price,
    )

    # ------------------------------------------------------------------
    # Step 4: Determine HITL triggers
    # HITL fires when p_final < 0.40 OR circuit_breaker is True.
    # It does NOT fire when p_final >= 0.40 and circuit_breaker is False.
    # ------------------------------------------------------------------
    hitl_triggered = False
    hitl_reason: str = ""

    if result.circuit_breaker:
        hitl_triggered = True
        hitl_reason = (
            f"Circuit breaker triggered: {guardian_mod.circuit_breaker_reason or 'severe risk detected'}. "
            f"Human review required before proceeding."
        )
    elif result.p_success < _HITL_PROBABILITY_THRESHOLD:
        hitl_triggered = True
        hitl_reason = (
            f"p_final={result.p_success:.3f} < {_HITL_PROBABILITY_THRESHOLD} "
            f"(HOLD territory). Recommendation: HOLD. Human confirmation required."
        )

    # ------------------------------------------------------------------
    # Step 5: RAG citations (graceful degradation)
    # ------------------------------------------------------------------
    citations: list[dict] = []
    try:
        rag_query = f"{ticker} valuation intrinsic value"
        citations = retrieve_with_citations(rag_query, k=3)
    except Exception as exc:  # noqa: BLE001
        print(
            f"judge: RAG retrieval failed for {ticker} — {exc}",
            file=sys.stderr,
        )

    # ------------------------------------------------------------------
    # Step 6: LLM narrative synthesis (MODEL_PRO)
    # ------------------------------------------------------------------
    bull_thesis = state.get("bull_thesis") or state.get("bull_refined_thesis") or "Not available."
    bear_thesis = state.get("bear_thesis") or "Not available."

    human_prompt = (
        f"ASSET: {ticker}\n\n"
        f"JUDGE ALGORITHM RESULTS:\n"
        f"  Recommendation: {result.recommendation}\n"
        f"  Consensus intrinsic value (median): ${result.valor_mediano:.2f}\n"
        f"  Price target (with margin of safety): ${result.precio_target:.2f}\n"
        f"  Margin of safety: {result.margin_of_safety:.1%}\n"
        f"  p_success: {result.p_success:.3f} (base: {result.p_base:.3f})\n"
        f"  Kelly fraction: {result.kelly_fraction:.3f}\n"
        f"  Bull weight: {result.bull_weight:.3f}, Bear weight: {result.bear_weight:.3f}\n"
        f"  Circuit breaker: {result.circuit_breaker}\n"
        f"  Known unknowns: {', '.join(result.known_unknowns) or 'none'}\n"
        f"  Convergence score: {result.convergence_score:.3f} "
        f"(alert: {result.convergence_alert})\n\n"
        f"BULL THESIS:\n{bull_thesis}\n\n"
        f"BEAR THESIS:\n{bear_thesis}\n\n"
        f"MODIFIER SUMMARY:\n"
        f"  Oracle margin adj: {oracle_mod.margin_adjustment:+.3f}\n"
        f"  Guardian margin adj: {guardian_mod.margin_adjustment:+.3f}\n"
        f"  Strategist margin adj: {strategist_mod.margin_adjustment:+.3f}\n\n"
        "Synthesize the above into a judicial narrative (max 4 paragraphs)."
    )

    narrative: str = ""
    try:
        llm = get_llm(model=MODEL_PRO, temperature=0.1)
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=human_prompt),
        ]
        response = llm.invoke(messages)
        narrative = response.content
    except Exception as exc:  # noqa: BLE001
        print(
            f"judge: LLM narrative failed for {ticker} — {exc}. Using deterministic fallback.",
            file=sys.stderr,
        )
        narrative = (
            f"{ticker} consensus: {result.recommendation}. "
            f"Intrinsic value (median): ${result.valor_mediano:.2f}, "
            f"target: ${result.precio_target:.2f} "
            f"(margin={result.margin_of_safety:.1%}). "
            f"p_success={result.p_success:.3f}, Kelly={result.kelly_fraction:.3f}. "
            "LLM narrative unavailable — algorithmic output used."
        )

    # ------------------------------------------------------------------
    # Step 7: Return state update
    # ------------------------------------------------------------------
    return {
        "judge_consensus_distribution": {
            "mu": result.consensus_distribution[0],
            "sigma": result.consensus_distribution[1],
            "valor_mediano": result.valor_mediano,
        },
        "judge_recommendation": result.recommendation,
        "judge_conviction": result.p_success,
        "judge_margin": result.margin_of_safety,
        "judge_price_target": result.precio_target,
        "judge_narrative": narrative,
        "judge_hitl": hitl_triggered,
        "judge_hitl_reason": hitl_reason,
        "judge_output": result,
        "citations": citations,
    }
