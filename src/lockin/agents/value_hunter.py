"""
Value Hunter (Bull) agent for the AI-Investment Swarm.

Implements the Bull side of the dialectical debate:
  1. Fetches fundamental financial data (via lockin.data public API)
  2. Selects the most appropriate valuation model heuristically
  3. Builds a log-normal ValueDistribution over intrinsic value
  4. Computes quality filters (Piotroski F-Score, Magic Formula)
  5. Invokes LLM (MODEL_PRO) to generate a structured bullish thesis
  6. On refinement passes (bull_iteration > 0), incorporates bear challenges

Output fields returned to InvestmentState:
  - bull_valuation_distribution: ValueDistribution (log-normal parametrized)
  - bull_thesis: str   (initial) or empty on first pass (thesis is in distribution.thesis)
  - bull_refined_thesis: str  (only on bull_iteration > 0)
  - bull_confidence: float  [0, 1]
  - quality_metrics: dict
"""

from __future__ import annotations

import sys

import numpy as np
from langchain_core.runnables import RunnableConfig
from scipy.stats import lognorm

from lockin.agents.base import invoke_agent
from lockin.agents.llm import MODEL_PRO, get_llm
from lockin.agents.types import DataCoverage, ValueDistribution
from lockin.agents.valuations import (
    calculate_epv,
    calculate_eva,
    calculate_rim,
    magic_formula_metrics,
    piotroski_f_score,
)
from lockin.data import get_fundamentals
from lockin.graph.state import InvestmentState

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_WACC = 0.10
DEFAULT_TAX_RATE = 0.21
DEFAULT_COE = 0.10       # cost of equity for RIM
DEFAULT_GROWTH = 0.03    # perpetuity growth rate
DEFAULT_SIGMA = 0.20     # log-normal width (epistemic uncertainty)

# Minimum intrinsic value to feed into log-normal (avoids log(<=0))
_MIN_POSITIVE_VALUE = 0.01


# ---------------------------------------------------------------------------
# Company type heuristic
# ---------------------------------------------------------------------------


def _classify_company(data: dict) -> str:
    """Heuristic company classifier to select the most appropriate valuation model.

    Classification order (first match wins):
      - "financial"  → companies where book equity drives value (banks, insurance)
      - "tech"       → asset-light, high-ROE firms — RIM captures franchise premium
      - "mature"     → capital-intensive or moderate ROE — EVA captures reinvestment
      - default      → EPV (no-growth, conservative)

    Returns
    -------
    str
        One of: "financial", "tech", "mature", "default"
    """
    total_assets = data.get("total_assets") or 0
    total_equity = data.get("total_equity") or 0
    total_debt = data.get("total_debt") or 0
    net_income = data.get("net_income") or 0

    # Financial: high leverage ratio (assets >> equity + debt)
    if total_equity > 0:
        leverage = total_assets / total_equity
        if leverage > 8:
            return "financial"

    # Tech/High-quality: very high ROE
    if total_equity > 0 and net_income > 0:
        roe = net_income / total_equity
        if roe > 0.20:
            return "tech"

    # Mature / capital-intensive: moderate ROE
    if total_equity > 0 and net_income > 0:
        roe = net_income / total_equity
        if roe > 0.10:
            return "mature"

    return "default"


# ---------------------------------------------------------------------------
# Per-model intrinsic value calculations
# ---------------------------------------------------------------------------


def _intrinsic_value_epv(data: dict) -> tuple[float, str]:
    """EPV model — best for asset-heavy, stable-earnings businesses."""
    operating_income = data.get("operating_income") or 0
    shares_out = _safe_shares(data)
    if shares_out <= 0 or abs(operating_income) < _MIN_POSITIVE_VALUE:
        return _MIN_POSITIVE_VALUE, "EPV"
    try:
        per_share = calculate_epv(
            ebit_5y_avg=operating_income,
            tax_rate=DEFAULT_TAX_RATE,
            wacc=DEFAULT_WACC,
            shares_outstanding=shares_out,
        )
        return max(_MIN_POSITIVE_VALUE, per_share), "EPV"
    except ValueError:
        return _MIN_POSITIVE_VALUE, "EPV"


def _intrinsic_value_eva(data: dict) -> tuple[float, str]:
    """EVA model — best for mature firms with stable capital structures."""
    operating_income = data.get("operating_income") or 0
    total_assets = data.get("total_assets") or 0
    # Use total_assets - current_liabilities as proxy for invested capital
    # We don't have current_liabilities in FundamentalsResult, so approximate
    # with total_assets - total_equity (rough: funded by debt + equity)
    total_equity = data.get("total_equity") or 0
    invested_capital = max(total_assets - total_equity * 0.3, _MIN_POSITIVE_VALUE)

    nopat = operating_income * (1 - DEFAULT_TAX_RATE)
    eva_total = calculate_eva(nopat=nopat, wacc=DEFAULT_WACC, invested_capital=invested_capital)

    # Convert EVA to per-share value: EV = IC + EVA / WACC (simplified)
    # Then subtract net debt to get equity value
    ev = invested_capital + (eva_total / DEFAULT_WACC if DEFAULT_WACC > 0 else 0)
    net_debt = (data.get("total_debt") or 0) - (data.get("cash_and_equivalents") or 0)
    equity_value = ev - net_debt

    shares_out = _safe_shares(data)
    if shares_out <= 0:
        return _MIN_POSITIVE_VALUE, "EVA"

    per_share = equity_value / shares_out
    return max(_MIN_POSITIVE_VALUE, per_share), "EVA"


def _intrinsic_value_rim(data: dict) -> tuple[float, str]:
    """RIM model — best for high-quality franchises where ROE > COE."""
    total_equity = data.get("total_equity") or 0
    net_income = data.get("net_income") or 0
    shares_out = _safe_shares(data)

    if total_equity <= 0 or shares_out <= 0:
        return _MIN_POSITIVE_VALUE, "RIM"

    roe = net_income / total_equity
    try:
        per_share = calculate_rim(
            book_value=total_equity,
            roe=roe,
            cost_of_equity=DEFAULT_COE,
            growth_rate=DEFAULT_GROWTH,
            shares_outstanding=shares_out,
        )
        return max(_MIN_POSITIVE_VALUE, per_share), "RIM"
    except ValueError:
        # Falls back if COE <= growth_rate (shouldn't happen with defaults)
        return max(_MIN_POSITIVE_VALUE, total_equity / shares_out), "RIM"


def _safe_shares(data: dict) -> float:
    """Extract shares outstanding from fundamentals, returning 0 if unavailable.

    FundamentalsResult doesn't carry shares_outstanding as a top-level field.
    We approximate from diluted_eps and net_income if both are present.
    """
    net_income = data.get("net_income") or 0
    eps = data.get("diluted_eps") or 0
    if eps != 0 and net_income != 0:
        return abs(net_income / eps)
    return 1.0  # return 1 share as fallback — caller guards against division


# ---------------------------------------------------------------------------
# Quality metrics computation
# ---------------------------------------------------------------------------


def _compute_quality_metrics(data: dict) -> dict:
    """Compute Piotroski F-Score and Magic Formula metrics from fundamentals.

    Since FundamentalsResult only carries current-year data (no prior-year dict),
    we build a synthetic prior by scaling down current metrics by 10% as a
    conservative proxy.  This is documented in the quality_metrics dict.
    """
    # Build synthetic prior (conservative approximation)
    current = {
        "net_income": data.get("net_income") or 0,
        "operating_cf": data.get("free_cash_flow") or 0,
        "roa": (
            (data.get("net_income") or 0) / (data.get("total_assets") or 1)
        ),
        "total_assets": data.get("total_assets") or 0,
        "long_term_debt": (data.get("total_debt") or 0),
        "current_ratio": 1.5,  # no current_liabilities in FundamentalsResult
        "shares_outstanding": _safe_shares(data),
        "gross_profit": data.get("gross_profit") or 0,
        "total_revenue": data.get("total_revenue") or 1,
        "asset_turnover": (
            (data.get("total_revenue") or 0) / max(data.get("total_assets") or 1, 1)
        ),
    }

    # Synthetic prior: 90% of current (implies slight improvement year-over-year)
    prior = {k: v * 0.90 for k, v in current.items()}

    f_score = piotroski_f_score(current, prior)

    # Magic Formula metrics
    ebit = data.get("operating_income") or 0
    total_assets = data.get("total_assets") or 0
    total_debt = data.get("total_debt") or 0
    cash = data.get("cash_and_equivalents") or 0

    # Enterprise value proxy: use total_assets - cash (simplified)
    # (Ideally market_cap + debt - cash, but no market cap in FundamentalsResult)
    ev_proxy = total_assets + total_debt - cash

    # Net fixed assets = total_assets * 0.3 (rough for non-financial)
    nfa = total_assets * 0.30
    wc = (total_assets * 0.15)  # current assets proxy - current liabilities proxy

    mf_metrics = magic_formula_metrics(
        ebit=ebit,
        enterprise_value=ev_proxy,
        net_fixed_assets=nfa,
        working_capital=wc,
    )

    return {
        "piotroski_f": f_score,
        "magic_formula": mf_metrics,
        "synthetic_prior": True,  # flag that prior is approximated
    }


# ---------------------------------------------------------------------------
# Log-normal distribution builder
# ---------------------------------------------------------------------------


def _build_distribution(
    intrinsic_value: float,
    method: str,
    data_coverage: DataCoverage,
    quality_metrics: dict,
    thesis: str,
) -> ValueDistribution:
    """Build a log-normal ValueDistribution centred on the intrinsic value estimate.

    The distribution sigma (width) is DEFAULT_SIGMA=0.20 by default, representing
    epistemic uncertainty in the single-year point estimate.  Higher Piotroski
    scores narrow sigma slightly (better data quality = less uncertainty).

    Parameters
    ----------
    intrinsic_value : float
        Point estimate of intrinsic value per share (must be > 0).
    method : str
        Valuation method used ("EPV" | "EVA" | "RIM").
    data_coverage : DataCoverage
        Tracks which data fields were available vs missing.
    quality_metrics : dict
        Contains piotroski_f score (0-9) for sigma adjustment.
    thesis : str
        LLM-generated bullish thesis to embed in distribution.

    Returns
    -------
    ValueDistribution
        Fully populated with log-normal percentiles and metadata.
    """
    f_score = quality_metrics.get("piotroski_f", 0)

    # Tighten sigma for high quality (>= 7) companies
    if f_score >= 7:
        sigma = DEFAULT_SIGMA * 0.85
    elif f_score <= 3:
        sigma = DEFAULT_SIGMA * 1.20
    else:
        sigma = DEFAULT_SIGMA

    mu = np.log(intrinsic_value)
    dist = lognorm(s=sigma, scale=np.exp(mu))

    p10 = float(dist.ppf(0.10))
    p50 = float(dist.ppf(0.50))
    p90 = float(dist.ppf(0.90))

    # Confidence: base from F-score, penalised by data coverage gaps
    base_confidence = 0.50 + (f_score / 9) * 0.30  # 0.50..0.80
    missing_penalty = len(data_coverage.missing) * 0.03
    confidence = max(0.10, min(0.95, base_confidence - missing_penalty))

    # Standard deviation of the log-normal
    mean_val = float(np.exp(mu + sigma**2 / 2))
    variance = (np.exp(sigma**2) - 1) * np.exp(2 * mu + sigma**2)
    std_dev = float(np.sqrt(variance))

    return ValueDistribution(
        expected_value=mean_val,
        std_dev=std_dev,
        p10=p10,
        p50=p50,
        p90=p90,
        confidence=confidence,
        methods_used=[method],
        data_coverage=data_coverage,
        thesis=thesis,
        key_assumptions=[
            f"WACC={DEFAULT_WACC:.0%}",
            f"tax_rate={DEFAULT_TAX_RATE:.0%}",
            f"growth_rate={DEFAULT_GROWTH:.0%}",
            f"sigma={sigma:.2f} (log-normal width)",
            f"method={method}",
        ],
    )


# ---------------------------------------------------------------------------
# Data coverage tracker
# ---------------------------------------------------------------------------


def _build_data_coverage(data: dict) -> DataCoverage:
    """Inspect FundamentalsResult and report which fields are available vs missing."""
    key_fields = [
        "operating_income",
        "net_income",
        "total_assets",
        "total_equity",
        "total_debt",
        "gross_profit",
        "total_revenue",
        "free_cash_flow",
        "cash_and_equivalents",
        "diluted_eps",
    ]
    available = [f for f in key_fields if data.get(f) is not None]
    missing = [f for f in key_fields if data.get(f) is None]
    confidence_impact = -0.02 * len(missing)
    return DataCoverage(
        available=available,
        missing=missing,
        confidence_impact=confidence_impact,
    )


# ---------------------------------------------------------------------------
# LLM thesis generation
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are the Value Hunter agent in an AI investment analysis system.
Your role: build the strongest possible bullish investment thesis based on fundamental analysis.
You must:
1. Identify the primary source of intrinsic value (EPV/EVA/RIM result)
2. Highlight quality indicators (Piotroski F-Score, Magic Formula)
3. Articulate the competitive moat and durable advantages
4. Quantify the margin of safety vs current intrinsic value estimate
5. Be specific, analytical, and data-driven — avoid vague statements
Output: 3-5 sentences, crisp and investment-grade quality."""

_SYSTEM_PROMPT_REFINED = """You are the Value Hunter agent defending and refining your bull thesis.
Bear has raised specific challenges. Your role: directly address each challenge, strengthen your
thesis with additional evidence where available, and recalibrate confidence appropriately.
Be intellectually honest — if a bear concern is valid, acknowledge it while explaining why it
doesn't change your overall recommendation.
Output: 3-5 sentences addressing bear challenges directly."""


def _build_human_prompt(
    ticker: str,
    company_type: str,
    method: str,
    intrinsic_value: float,
    quality_metrics: dict,
    data: dict,
) -> str:
    """Format the human-turn prompt for the LLM thesis generation."""
    f_score = quality_metrics.get("piotroski_f", "N/A")
    mf = quality_metrics.get("magic_formula", {})
    ey = mf.get("earnings_yield", 0)
    roic = mf.get("roic", 0)

    return (
        f"Ticker: {ticker}\n"
        f"Company type heuristic: {company_type}\n"
        f"Valuation model: {method}\n"
        f"Intrinsic value estimate (per share): ${intrinsic_value:.2f}\n"
        f"Piotroski F-Score: {f_score}/9\n"
        f"Magic Formula — Earnings Yield: {ey:.1%}, ROIC: {roic:.1%}\n"
        f"Operating Income: {data.get('operating_income', 'N/A')}\n"
        f"Net Income: {data.get('net_income', 'N/A')}\n"
        f"Total Equity: {data.get('total_equity', 'N/A')}\n"
        f"Total Assets: {data.get('total_assets', 'N/A')}\n"
        f"Free Cash Flow: {data.get('free_cash_flow', 'N/A')}\n"
        f"\nGenerate a compelling bullish investment thesis for this company."
    )


def _build_refinement_prompt(
    ticker: str,
    original_thesis: str,
    bear_challenges: list,
    intrinsic_value: float,
    quality_metrics: dict,
) -> str:
    """Format refinement prompt incorporating bear challenges."""
    challenges_text = "\n".join(f"  - {c}" for c in bear_challenges)
    return (
        f"Ticker: {ticker}\n"
        f"Original bull thesis:\n{original_thesis}\n\n"
        f"Bear's challenges:\n{challenges_text}\n\n"
        f"Intrinsic value (maintained): ${intrinsic_value:.2f}\n"
        f"Piotroski F-Score: {quality_metrics.get('piotroski_f', 'N/A')}/9\n"
        f"\nRefine the bull thesis addressing each bear challenge."
    )


# ---------------------------------------------------------------------------
# Main agent function
# ---------------------------------------------------------------------------


def value_hunter(state: InvestmentState, config: RunnableConfig) -> dict:
    """Value Hunter (Bull) agent — produces ValueDistribution with bullish thesis.

    Fetches fundamental data, selects the best valuation model heuristically,
    builds a log-normal distribution over intrinsic value, computes quality
    filters, and invokes an LLM to generate a structured bullish thesis.

    On refinement passes (bull_iteration > 0), the agent incorporates bear
    challenges into a refined thesis while maintaining the same valuation model.

    Parameters
    ----------
    state : InvestmentState
        Current graph state. Reads: asset_ticker, bull_iteration, bear_challenges.
    config : RunnableConfig
        LangGraph execution config (thread_id, etc.).

    Returns
    -------
    dict
        Partial InvestmentState update with:
          - bull_valuation_distribution: ValueDistribution
          - bull_thesis: str
          - bull_refined_thesis: str  (only when bull_iteration > 0)
          - bull_confidence: float
          - quality_metrics: dict
    """
    ticker = state.get("asset_ticker", "UNKNOWN")
    bull_iteration = state.get("bull_iteration", 0)

    # Step 1: Fetch fundamentals (store=False — agents are read-only)
    try:
        data = get_fundamentals(ticker, store=False)
    except Exception as exc:
        print(f"value_hunter: get_fundamentals failed for {ticker}: {exc}", file=sys.stderr)
        # Return a low-confidence distribution on data failure
        data = {
            "ticker": ticker,
            "operating_income": None,
            "net_income": None,
            "total_assets": None,
            "total_equity": None,
            "total_debt": None,
            "gross_profit": None,
            "total_revenue": None,
            "free_cash_flow": None,
            "cash_and_equivalents": None,
            "diluted_eps": None,
        }

    # Step 2: Build data coverage tracker
    data_coverage = _build_data_coverage(data)

    # Step 3: Classify company to select valuation model
    company_type = _classify_company(data)

    # Step 4: Calculate intrinsic value with selected model
    if company_type == "financial":
        intrinsic_value, method = _intrinsic_value_rim(data)
    elif company_type == "tech":
        intrinsic_value, method = _intrinsic_value_rim(data)
    elif company_type == "mature":
        intrinsic_value, method = _intrinsic_value_eva(data)
    else:
        intrinsic_value, method = _intrinsic_value_epv(data)

    # Step 5: Compute quality filters
    quality_metrics = _compute_quality_metrics(data)

    # Step 6: Build initial thesis via LLM
    llm = get_llm(model=MODEL_PRO, temperature=0.2)

    initial_thesis = invoke_agent(
        llm=llm,
        system_prompt=_SYSTEM_PROMPT,
        human_prompt=_build_human_prompt(
            ticker=ticker,
            company_type=company_type,
            method=method,
            intrinsic_value=intrinsic_value,
            quality_metrics=quality_metrics,
            data=data,
        ),
        agent_name="value_hunter",
    )

    # Step 7: Build log-normal ValueDistribution
    distribution = _build_distribution(
        intrinsic_value=intrinsic_value,
        method=method,
        data_coverage=data_coverage,
        quality_metrics=quality_metrics,
        thesis=initial_thesis,
    )

    # Step 8: Assemble result
    result: dict = {
        "bull_valuation_distribution": distribution,
        "bull_thesis": initial_thesis,
        "bull_confidence": distribution.confidence,
        "quality_metrics": quality_metrics,
    }

    # Step 9: Refinement pass — incorporate bear challenges
    if bull_iteration > 0:
        bear_challenges = state.get("bear_challenges") or []
        if bear_challenges:
            refined_thesis = invoke_agent(
                llm=llm,
                system_prompt=_SYSTEM_PROMPT_REFINED,
                human_prompt=_build_refinement_prompt(
                    ticker=ticker,
                    original_thesis=initial_thesis,
                    bear_challenges=bear_challenges,
                    intrinsic_value=intrinsic_value,
                    quality_metrics=quality_metrics,
                ),
                agent_name="value_hunter_refined",
            )
            result["bull_refined_thesis"] = refined_thesis

    return result
