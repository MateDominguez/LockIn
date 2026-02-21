"""
Mock agent functions for Phase 1 integration testing.

Each function has the standard LangGraph node signature:
    (state: InvestmentState, config: RunnableConfig) -> dict

Agents return ONLY the fields they own (partial state update).
LangGraph merges the returned dict into the full InvestmentState.

These stubs let the graph compile and run end-to-end without real LLM calls.
They are replaced by real agents in Phase 3.
"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from lockin.graph.state import InvestmentState


# ---------------------------------------------------------------------------
# 1. Macro Oracle
# ---------------------------------------------------------------------------


def mock_macro_oracle(state: InvestmentState, config: RunnableConfig) -> dict:
    """Analyse macro regime and market cycle phase."""
    return {
        "macro_regime": {
            "phase": "expansion",
            "risk_appetite": "on",
            "yield_curve": "normal",
            "fed_stance": "neutral",
        },
        "macro_confidence": 0.75,
        "macro_narrative": (
            "Mock: expansion regime detected — yield curve normal, risk appetite on, "
            "Fed stance neutral.  Conditions broadly supportive for equities."
        ),
    }


# ---------------------------------------------------------------------------
# 2. Value Hunter  (Bull)
# ---------------------------------------------------------------------------


def mock_value_hunter(state: InvestmentState, config: RunnableConfig) -> dict:
    """Produce bullish valuation distribution and investment thesis."""
    result: dict = {
        "bull_valuation_distribution": {
            "mean": 185.0,
            "median": 180.0,
            "std_dev": 25.0,
            "P10": 145.0,
            "P25": 160.0,
            "P50": 180.0,
            "P75": 205.0,
            "P90": 225.0,
        },
        "bull_thesis": (
            "Mock: undervalued based on EPV and Magic Formula screening.  "
            "Strong free cash flow yield, durable competitive moat, and "
            "Piotroski F-Score of 7 indicate financial strength."
        ),
        "bull_confidence": 0.72,
        "quality_metrics": {
            "piotroski_f": 7,
            "magic_formula_rank": 85,
            "roic": 0.22,
            "fcf_yield": 0.058,
        },
    }

    # After the Bear has challenged the thesis (iteration > 0), include refined output.
    if state.get("bull_iteration", 0) > 0:
        result["bull_refined_thesis"] = (
            "Mock: refined after bear challenge — EPV margin of safety remains intact "
            "despite bear's revenue deceleration concern; reaffirm BUY with tighter "
            "P10/P90 spread."
        )
        result["bull_defense"] = (
            "Mock: defense of thesis — competitive moat widening in services segment "
            "offsets hardware cycle slowdown; ROIC trend inflecting upward."
        )

    return result


# ---------------------------------------------------------------------------
# 3. Bear
# ---------------------------------------------------------------------------


def mock_bear(state: InvestmentState, config: RunnableConfig) -> dict:
    """Challenge the bull thesis and produce bearish valuation distribution.

    CRITICAL: increments bull_iteration so the conditional edge can count rounds.
    """
    current_iteration = state.get("bull_iteration", 0)

    return {
        "bear_challenges": [
            "Mock: revenue growth deceleration in core hardware segment",
            "Mock: competitive moat narrowing due to Android ecosystem catch-up",
            "Mock: rising R&D costs compressing near-term free cash flow",
        ],
        "bear_valuation_distribution": {
            "mean": 135.0,
            "median": 130.0,
            "std_dev": 30.0,
            "P10": 90.0,
            "P25": 110.0,
            "P50": 130.0,
            "P75": 155.0,
            "P90": 180.0,
        },
        "bear_thesis": (
            "Mock: overvalued considering hardware cycle headwinds and deteriorating "
            "ROIC trend.  Current price embeds unrealistic growth assumptions."
        ),
        "bear_red_flags": [
            "Mock: declining ROIC trend (22% → 18% over 3 years)",
            "Mock: inventory build-up suggesting demand softness",
        ],
        "bear_conviction": 0.65,
        # Increment iteration counter — drives conditional edge routing
        "bull_iteration": current_iteration + 1,
    }


# ---------------------------------------------------------------------------
# 4. Strategist
# ---------------------------------------------------------------------------


def mock_strategist(state: InvestmentState, config: RunnableConfig) -> dict:
    """Overlay strategic context: sentiment, insider activity, ESG signals."""
    return {
        "strategist_veto": 0.0,
        "strategist_sentiment": 0.62,
        "strategic_signals": {
            "earnings_sentiment": "positive",
            "insider_activity": "neutral",
            "analyst_revision_trend": "up",
            "short_interest": "low",
        },
        "strategist_narrative": (
            "Mock: strategic context broadly positive — earnings sentiment up, "
            "no insider selling detected, analyst revisions trending upward.  "
            "No veto triggered."
        ),
        "strategist_confidence": 0.68,
    }


# ---------------------------------------------------------------------------
# 5. Guardian
# ---------------------------------------------------------------------------


def mock_guardian(state: InvestmentState, config: RunnableConfig) -> dict:
    """Assess risk, flag red flags, and determine position sizing."""
    return {
        "guardian_risk_report": {
            "altman_z": 3.2,          # >3.0 = safe zone
            "beneish_m": -2.8,        # < -2.22 = likely not manipulating
            "debt_ebitda": 1.5,       # <2.0 = conservative
            "vomc_fragility": 0.3,    # <0.5 = low fragility
            "current_ratio": 1.4,
        },
        "guardian_veto": False,
        "guardian_veto_reason": "",
        "guardian_sizing": 0.08,      # 8% of portfolio
        "guardian_margin_adjustments": {
            "base": 0.25,
            "adjusted": 0.28,
            "rationale": "Mock: slight upward adjustment — macro tailwind.",
        },
    }


# ---------------------------------------------------------------------------
# 6. Judge
# ---------------------------------------------------------------------------


def mock_judge(state: InvestmentState, config: RunnableConfig) -> dict:
    """Produce Bayesian consensus across bull, bear, and strategic distributions."""
    return {
        "judge_consensus_distribution": {
            "mean": 160.0,
            "median": 155.0,
            "std_dev": 20.0,
            "P10": 125.0,
            "P25": 142.0,
            "P50": 155.0,
            "P75": 175.0,
            "P90": 195.0,
        },
        "judge_recommendation": "BUY",
        "judge_conviction": 0.70,
        "judge_margin": 0.28,           # 28% margin of safety
        "judge_price_target": 160.0,
        "judge_narrative": (
            "Mock: Bayesian synthesis weights bull (60%) vs bear (40%) distributions.  "
            "Consensus mean $160 with conviction 0.70.  Recommend BUY with 8% sizing."
        ),
        "judge_hitl": False,
        "judge_hitl_reason": "",
    }


# ---------------------------------------------------------------------------
# 7. Optimizer
# ---------------------------------------------------------------------------


def mock_optimizer(state: InvestmentState, config: RunnableConfig) -> dict:
    """Translate judge recommendation into portfolio-level allocation."""
    ticker = state.get("asset_ticker", "UNKNOWN")

    return {
        "optimizer_portfolio": {ticker: 0.08},
        "optimizer_sectors": {"technology": 0.08},
        "optimizer_rebalancing": [],   # No existing positions to rebalance
        "optimizer_metrics": {
            "expected_return": 0.12,
            "portfolio_risk": 0.15,
            "sharpe": 0.80,
            "max_drawdown": -0.18,
        },
        "optimizer_narrative": (
            "Mock: Kelly sizing suggests 8% position.  "
            "Sharpe 0.80, expected return 12%, portfolio risk 15%.  "
            "No rebalancing of existing positions required."
        ),
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

MOCK_AGENTS: dict[str, object] = {
    "macro_oracle": mock_macro_oracle,
    "value_hunter": mock_value_hunter,
    "bear": mock_bear,
    "strategist": mock_strategist,
    "guardian": mock_guardian,
    "judge": mock_judge,
    "optimizer": mock_optimizer,
}
