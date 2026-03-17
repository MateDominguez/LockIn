"""
Bear adversarial agent for the AI-Investment Swarm.

The Bear is a Distribution agent (Family 1 in the Notion Judge spec). It
receives only the asset ticker and independently fetches raw fundamental data.
It does NOT read the Bull's thesis or valuation distribution — the two agents
are structurally blind to each other to ensure independent, adversarial analysis.

Bear's purpose:
  - Challenge every positive assumption in the bull case
  - Detect accounting red flags, margin deterioration, debt escalation
  - Produce a pessimistic ValueDistribution (lower mu, wider sigma than Bull)
  - Increment bull_iteration to drive the dialectical routing edge

Output contract (all fields are InvestmentState keys):
  bear_challenges:              list[str]
  bear_valuation_distribution:  ValueDistribution
  bear_thesis:                  str
  bear_red_flags:               list[str]
  bear_conviction:              float (0.0-1.0)
  bull_iteration:               int   (incremented — CRITICAL for graph routing)
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

import numpy as np
from langchain_core.runnables import RunnableConfig
from scipy.stats import lognorm

from lockin.agents.base import invoke_agent
from lockin.agents.llm import MODEL_PRO, get_llm
from lockin.agents.types import DataCoverage, ValueDistribution
from lockin.data import get_fundamentals
from lockin.graph.state import InvestmentState

# ---------------------------------------------------------------------------
# EPV pessimistic parameters
# ---------------------------------------------------------------------------

_WACC_PESSIMISTIC = 0.12          # higher risk premium than Bull (~0.10)
_TAX_RATE_PESSIMISTIC = 0.25      # conservative tax assumption
_EBIT_HAIRCUT = 0.20              # 20 % haircut for margin-compression scenario
_SIGMA = 0.25                     # wider uncertainty band than Bull's ~0.20

# ---------------------------------------------------------------------------
# Red-flag thresholds
# ---------------------------------------------------------------------------

_DEBT_EQUITY_THRESHOLD = 2.0      # total_debt / total_equity — danger zone
_ACCRUAL_GAP_THRESHOLD = 0.50     # abs(net_income - FCF) / abs(net_income)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe(value: Any, fallback: float = 0.0) -> float:
    """Return float or fallback when value is None / NaN."""
    if value is None:
        return fallback
    try:
        f = float(value)
        return fallback if (f != f) else f  # NaN check
    except (TypeError, ValueError):
        return fallback


def _compute_red_flags(data: dict) -> list[str]:
    """Derive deterministic red-flag signals from fundamentals data.

    Returns a list of human-readable flag strings. Empty list = no flags.
    """
    flags: list[str] = []

    total_revenue = _safe(data.get("total_revenue"))
    operating_income = _safe(data.get("operating_income"))
    total_debt = _safe(data.get("total_debt"))
    total_equity = _safe(data.get("total_equity"), fallback=1.0)
    free_cash_flow = _safe(data.get("free_cash_flow"))
    net_income = _safe(data.get("net_income"))

    # 1. Revenue decline (compared against zero as proxy when prior year absent)
    if total_revenue < 0:
        flags.append("revenue_negative: total revenue is negative")

    # 2. Margin compression proxy: operating_income / total_revenue
    if total_revenue > 0:
        operating_margin = operating_income / total_revenue
        if operating_margin < 0.05:
            flags.append(
                f"margin_compression: operating margin {operating_margin:.1%} < 5 %"
            )
    elif operating_income < 0:
        flags.append("margin_compression: negative operating income with no revenue base")

    # 3. Debt escalation
    if total_equity > 0:
        debt_ratio = total_debt / total_equity
        if debt_ratio > _DEBT_EQUITY_THRESHOLD:
            flags.append(
                f"debt_escalation: debt/equity ratio {debt_ratio:.2f} > {_DEBT_EQUITY_THRESHOLD}"
            )
    elif total_debt > 0:
        flags.append("debt_escalation: positive debt with zero or negative equity")

    # 4. Cash burn
    if free_cash_flow < 0:
        flags.append(
            f"free_cash_flow_negative: FCF is {free_cash_flow:,.0f} (cash burn)"
        )

    # 5. Earnings quality / accrual gap
    abs_net = abs(net_income)
    if abs_net > 0:
        accrual_gap = abs(net_income - free_cash_flow) / abs_net
        if accrual_gap > _ACCRUAL_GAP_THRESHOLD:
            flags.append(
                f"accrual_gap: |NI - FCF| / |NI| = {accrual_gap:.2f} "
                f"(earnings quality risk)"
            )

    return flags


def _compute_pessimistic_epv(data: dict) -> float:
    """Compute a pessimistic Earnings Power Value.

    Formula: EPV = EBIT * (1 - tax_rate) * (1 - haircut) / WACC

    If EBIT is not available we fall back to operating_income or a proxy
    based on net_income + a rough 30 % tax gross-up.
    """
    # Prefer operating_income as EBIT proxy (already available in FundamentalsResult)
    ebit = _safe(data.get("operating_income"))

    # Fallback: gross-up net income if operating_income is absent
    if ebit == 0.0:
        net_income = _safe(data.get("net_income"))
        ebit = net_income / (1.0 - _TAX_RATE_PESSIMISTIC) if net_income != 0.0 else 0.0

    # Apply hair-cut for margin compression scenario
    ebit_haircut = ebit * (1.0 - _EBIT_HAIRCUT)

    # EPV (intrinsic business value, pre-cash/debt adjustment)
    nopat = ebit_haircut * (1.0 - _TAX_RATE_PESSIMISTIC)
    epv = nopat / _WACC_PESSIMISTIC

    # Net cash adjustment (subtract net debt to get equity value)
    cash = _safe(data.get("cash_and_equivalents"))
    debt = _safe(data.get("total_debt"))
    epv_equity = epv + cash - debt

    # Guard: EPV must be a positive number for log-normal parametrization
    return max(epv_equity, 1.0)


def _build_distribution(pessimistic_value: float) -> tuple[ValueDistribution, float]:
    """Build log-normal ValueDistribution centred on pessimistic_value.

    Returns (ValueDistribution, bear_confidence).
    """
    mu = np.log(max(pessimistic_value, 1.0))
    sigma = _SIGMA

    dist = lognorm(s=sigma, scale=np.exp(mu))
    p10 = float(dist.ppf(0.10))
    p50 = float(dist.ppf(0.50))
    p90 = float(dist.ppf(0.90))

    # Confidence: moderate by default; we acknowledge pessimistic assumptions
    bear_confidence = 0.55

    data_coverage = DataCoverage(
        available=["income_statement", "balance_sheet", "cash_flow"],
        missing=["competitive_threat_detail", "regulatory_risk", "insider_sentiment"],
        confidence_impact=-0.10 * 3 / (3 + 3),  # 3 missing / 6 total
    )

    value_dist = ValueDistribution(
        expected_value=pessimistic_value,
        std_dev=pessimistic_value * sigma,
        p10=p10,
        p50=p50,
        p90=p90,
        confidence=bear_confidence,
        methods_used=["EPV_pessimistic"],
        data_coverage=data_coverage,
        thesis="",    # filled in after LLM call
        key_assumptions=[
            f"WACC={_WACC_PESSIMISTIC:.0%}",
            f"EBIT_haircut={_EBIT_HAIRCUT:.0%}",
            f"tax_rate={_TAX_RATE_PESSIMISTIC:.0%}",
            "log_normal_sigma=0.25",
        ],
    )
    return value_dist, bear_confidence


def _parse_llm_response(raw: str) -> dict:
    """Extract JSON from LLM response (handles markdown code fences)."""
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()

    # Find first { … } block
    start = cleaned.find("{")
    end = cleaned.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(cleaned[start:end])
        except json.JSONDecodeError:
            pass

    # Fallback: return safe defaults
    return {
        "challenges": ["Unable to parse LLM response — raw data analysis required"],
        "thesis": "Bearish analysis pending — LLM response parsing failed",
        "red_flags": [],
        "conviction": 0.50,
    }


# ---------------------------------------------------------------------------
# Bear agent
# ---------------------------------------------------------------------------


def bear(state: InvestmentState, config: RunnableConfig) -> dict:
    """Adversarial Bear agent — independent from Bull.

    CRITICAL: This function NEVER reads state["bull_thesis"] or
    state["bull_valuation_distribution"].  Bear builds its thesis entirely
    from raw fundamental data fetched directly from the data layer.

    Args:
        state: Current InvestmentState.  Only state["asset_ticker"] and
               state["bull_iteration"] are read; all Bull outputs are ignored.
        config: LangGraph RunnableConfig (thread_id, etc.).

    Returns:
        Partial state dict with Bear outputs + incremented bull_iteration.
    """
    # ------------------------------------------------------------------
    # 1. Read inputs — ticker and iteration counter ONLY (no Bull data)
    # ------------------------------------------------------------------
    ticker: str = state["asset_ticker"]
    current_iteration: int = state.get("bull_iteration", 0)

    # ------------------------------------------------------------------
    # 2. Fetch fundamentals independently (store=False — read-only)
    # ------------------------------------------------------------------
    data: dict = {}
    try:
        data = dict(get_fundamentals(ticker, store=False))
    except Exception as exc:  # noqa: BLE001
        print(f"bear: data fetch error for {ticker}: {exc}", file=sys.stderr)
        # Continue with empty data — red flags and EPV will produce safe defaults

    # ------------------------------------------------------------------
    # 3. Deterministic red-flag signals
    # ------------------------------------------------------------------
    red_flags = _compute_red_flags(data)

    # ------------------------------------------------------------------
    # 4. Pessimistic EPV and ValueDistribution
    # ------------------------------------------------------------------
    pessimistic_value = _compute_pessimistic_epv(data)
    value_dist, bear_confidence = _build_distribution(pessimistic_value)

    # ------------------------------------------------------------------
    # 5. LLM for bearish thesis and structured challenges
    # ------------------------------------------------------------------
    system_prompt = (
        "You are a short-seller and forensic accountant. "
        "Your job is to find every reason NOT to invest. "
        "Analyze financial data for: "
        "1) Revenue sustainability risks, "
        "2) Margin compression threats, "
        "3) Competitive moat deterioration, "
        "4) Accounting red flags (accrual gaps, inventory build-up), "
        "5) Macro headwinds. "
        "Be specific with numbers. "
        'Respond ONLY with valid JSON in this exact format: '
        '{"challenges": ["..."], "thesis": "...", "red_flags": ["..."], '
        '"conviction": 0.0}'
    )

    # Compose human prompt: raw financials + computed red flags + macro context
    macro_context = {}
    macro_regime = state.get("macro_regime")
    if macro_regime:
        macro_context = macro_regime

    financial_summary = {k: v for k, v in data.items() if not callable(v)}
    human_prompt = (
        f"Ticker: {ticker}\n\n"
        f"Financial data:\n{json.dumps(financial_summary, default=str, indent=2)}\n\n"
        f"Computed red flags:\n{json.dumps(red_flags, indent=2)}\n\n"
        f"Macro context:\n{json.dumps(macro_context, indent=2)}\n\n"
        "Provide your bearish investment analysis."
    )

    challenges: list[str] = red_flags.copy()
    bear_thesis = "Bearish analysis based on pessimistic EPV and identified red flags."
    llm_red_flags: list[str] = red_flags.copy()
    llm_conviction: float = bear_confidence

    try:
        llm = get_llm(model=MODEL_PRO, temperature=0.1)
        raw_response = invoke_agent(
            llm, system_prompt, human_prompt, agent_name="bear"
        )
        parsed = _parse_llm_response(raw_response)

        challenges = parsed.get("challenges", challenges)
        bear_thesis = parsed.get("thesis", bear_thesis)
        llm_red_flags = parsed.get("red_flags", llm_red_flags)
        llm_conviction = float(parsed.get("conviction", llm_conviction))

    except Exception as exc:  # noqa: BLE001
        print(f"bear: LLM invocation failed for {ticker}: {exc}", file=sys.stderr)
        # Fallback values already set above

    # Merge LLM red flags with deterministic flags (de-duplicate)
    all_red_flags = list(dict.fromkeys(red_flags + llm_red_flags))

    # Update thesis on the distribution now that we have the LLM text
    value_dist.thesis = bear_thesis

    # ------------------------------------------------------------------
    # 6. Return partial state update
    # ------------------------------------------------------------------
    return {
        "bear_challenges": challenges,
        "bear_valuation_distribution": value_dist,
        "bear_thesis": bear_thesis,
        "bear_red_flags": all_red_flags,
        "bear_conviction": llm_conviction,
        # CRITICAL: increment counter — drives conditional edge routing in graph
        "bull_iteration": current_iteration + 1,
    }
