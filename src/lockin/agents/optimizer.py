"""
Optimizer agent for the AI-Investment Swarm.

Implements portfolio position sizing using the Kelly Criterion (Kelly/3) with
hard caps per the Notion spec:

  - KELLY_FRACTION = 0.33  (Kelly/3, NOT Kelly/4)
  - MAX_POSITION_SIZE = 0.10  (10% hard cap per position)
  - MAX_SECTOR_ALLOCATION = 0.325  (30-35% midpoint for sector concentration)
  - CIRCUIT_BREAKER_OVERRIDE_CAP = 0.02  (1-2% max when circuit breaker overridden)

Decision table:
  - BUY → apply Kelly/3 fraction, cap at 10%, cap by sector
  - HOLD → 0 new allocation (position already held, no new capital)
  - PASS → 0 position
  - circuit_breaker=True, no override → 0 position
  - circuit_breaker_override=True → min(position, 2% cap)

The optimizer reads JudgeOutput from state (preferred path) or falls back to
individual state fields for backward compatibility.

An LLM narrative (MODEL_FLASH) explains position sizing rationale in plain text.
"""

from __future__ import annotations

import sys

import yfinance as yf
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from lockin.agents.llm import MODEL_FLASH, get_llm
from lockin.agents.types import JudgeOutput
from lockin.graph.state import InvestmentState

# ---------------------------------------------------------------------------
# Constants per Notion spec
# ---------------------------------------------------------------------------

MAX_POSITION_SIZE = 0.10             # 10% hard cap per position
MAX_SECTOR_ALLOCATION = 0.325        # 30-35% midpoint for sector concentration
KELLY_FRACTION = 0.33                # Kelly/3 (NOT 0.25)
CIRCUIT_BREAKER_OVERRIDE_CAP = 0.02  # 1-2% max when circuit breaker overridden


# ---------------------------------------------------------------------------
# Kelly Criterion formula
# ---------------------------------------------------------------------------


def kelly_criterion(win_prob: float, win_loss_ratio: float) -> float:
    """Compute Kelly fraction: f* = (p*b - q) / b where q = 1 - p.

    Args:
        win_prob: Probability of a win (0.0 to 1.0).
        win_loss_ratio: Ratio of average gain to average loss (b in Kelly formula).
            Must be positive. Typically (target_price / current_price - 1) /
            (1 - floor_price / current_price).

    Returns:
        Optimal Kelly fraction clamped to [0, 1]. Returns 0.0 when the edge
        is negative (expected value is non-positive) or when win_loss_ratio <= 0.
    """
    if win_loss_ratio <= 0:
        return 0.0
    f_star = (win_prob * win_loss_ratio - (1 - win_prob)) / win_loss_ratio
    return max(0.0, f_star)


# ---------------------------------------------------------------------------
# Optimizer node
# ---------------------------------------------------------------------------


def optimizer(state: InvestmentState, config: RunnableConfig) -> dict:
    """Compute portfolio position size for the target asset.

    Reads JudgeOutput from state.judge_output (preferred) or falls back to
    individual state fields. Applies Kelly/3 sizing with hard caps.

    Args:
        state: Current InvestmentState (ticker, judge_output, etc.)
        config: LangGraph RunnableConfig (unused but required by node signature).

    Returns:
        Partial state update with optimizer_* keys.
    """
    ticker = state["asset_ticker"]

    # ------------------------------------------------------------------
    # 1. Extract judge outputs — prefer structured JudgeOutput dataclass
    # ------------------------------------------------------------------
    judge_output = state.get("judge_output")
    if judge_output and isinstance(judge_output, JudgeOutput):
        recommendation = judge_output.recommendation
        # kelly_fraction is already Kelly/3 as set by judge_math
        kelly_fraction = judge_output.kelly_fraction
        p_success = judge_output.p_success
        precio_target = judge_output.precio_target
        valor_mediano = judge_output.valor_mediano
        circuit_breaker = judge_output.circuit_breaker
        circuit_breaker_override = judge_output.circuit_breaker_override
    else:
        # Fallback to individual state fields (legacy or missing judge run)
        recommendation = state.get("judge_recommendation", "PASS")
        kelly_fraction = 0.0
        p_success = state.get("judge_conviction", 0.0)
        precio_target = state.get("judge_price_target", 0.0)
        valor_mediano = 0.0
        circuit_breaker = False
        circuit_breaker_override = False

    # ------------------------------------------------------------------
    # 2. Position sizing decision table (per Notion spec)
    # ------------------------------------------------------------------
    position_size = 0.0

    if recommendation == "PASS" or (circuit_breaker and not circuit_breaker_override):
        # Hard stop — no position
        position_size = 0.0
    elif recommendation == "HOLD":
        # Maintain existing position, no new capital allocated
        position_size = 0.0
    elif recommendation == "BUY":
        # Apply Kelly/3 fraction (already computed by judge_math)
        position_size = kelly_fraction
        # Hard cap: 10% maximum per position (Notion spec)
        position_size = min(position_size, MAX_POSITION_SIZE)

    # Circuit breaker override: extreme caution path — cap at 1-2%
    if circuit_breaker_override:
        position_size = min(position_size, CIRCUIT_BREAKER_OVERRIDE_CAP)

    # ------------------------------------------------------------------
    # 3. Fetch sector info via yfinance (best-effort, never crashes)
    # ------------------------------------------------------------------
    sector = "Unknown"
    current_price = valor_mediano if valor_mediano > 0 else 100.0
    try:
        info = yf.Ticker(ticker).info
        sector = info.get("sector", "Unknown") or "Unknown"
        fetched_price = info.get("currentPrice") or info.get("regularMarketPrice")
        if fetched_price:
            current_price = fetched_price
    except Exception:
        pass  # network failure — use fallback values silently

    # ------------------------------------------------------------------
    # 4. Sector concentration cap (simplified for v1 single-asset pipeline)
    # ------------------------------------------------------------------
    # In v1 the pipeline processes one asset at a time, so sector allocation ==
    # position_size. The cap is still enforced for multi-asset future use.
    position_size = min(position_size, MAX_SECTOR_ALLOCATION)

    # ------------------------------------------------------------------
    # 5. Portfolio metrics
    # ------------------------------------------------------------------
    expected_return = 0.0
    portfolio_risk = 0.0
    sharpe = 0.0

    if current_price > 0 and valor_mediano > 0:
        # Simple single-asset expected return and risk
        expected_return = position_size * (valor_mediano / current_price - 1)
        # Use consensus sigma from JudgeOutput if available
        if judge_output and judge_output.consensus_distribution:
            consensus_sigma = judge_output.consensus_distribution[1]
        else:
            consensus_sigma = 0.20  # default annual volatility
        portfolio_risk = position_size * consensus_sigma
        sharpe = expected_return / portfolio_risk if portfolio_risk > 0 else 0.0

    position_cap_applied = (
        recommendation == "BUY"
        and kelly_fraction > MAX_POSITION_SIZE
        and position_size <= MAX_POSITION_SIZE
    )

    # ------------------------------------------------------------------
    # 6. LLM narrative (MODEL_FLASH — cost-efficient for summary prose)
    # ------------------------------------------------------------------
    narrative = (
        f"{ticker}: {recommendation}, position={position_size:.1%}, "
        f"kelly_fraction={kelly_fraction:.3f}, "
        f"cap_applied={position_cap_applied}"
    )
    try:
        llm = get_llm(MODEL_FLASH)
        msg = llm.invoke([
            SystemMessage(
                content=(
                    "You are a portfolio optimizer. "
                    "Explain position sizing rationale concisely in 2-3 sentences."
                )
            ),
            HumanMessage(
                content=(
                    f"Ticker: {ticker}, "
                    f"Recommendation: {recommendation}, "
                    f"Kelly/3: {kelly_fraction:.3f}, "
                    f"Final position: {position_size:.1%}, "
                    f"P(success): {p_success:.2f}, "
                    f"Circuit breaker override: {circuit_breaker_override}"
                )
            ),
        ])
        narrative = msg.content
    except Exception as exc:
        print(f"optimizer: LLM narrative failed — {exc}", file=sys.stderr)

    # ------------------------------------------------------------------
    # 7. Return partial state update
    # ------------------------------------------------------------------
    return {
        "optimizer_portfolio": {ticker: position_size},
        "optimizer_sectors": {sector: position_size},
        "optimizer_rebalancing": [],
        "optimizer_metrics": {
            "kelly_fraction": kelly_fraction,
            "position_size": position_size,
            "position_cap_applied": position_cap_applied,
            "circuit_breaker_override_applied": circuit_breaker_override,
            "expected_return": expected_return,
            "portfolio_risk": portfolio_risk,
            "sharpe": sharpe,
            "max_drawdown_estimate": -portfolio_risk * 2 if portfolio_risk > 0 else 0.0,
        },
        "optimizer_narrative": narrative,
    }
