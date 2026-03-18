"""
Unit tests for the Judge agent in lockin.agents.judge.

These tests mock all external dependencies (LLM, yfinance, RAG retriever)
so no network calls are made.

Key assertions:
  - HITL triggers when p_final < 0.40 OR circuit_breaker=True
  - HITL does NOT trigger when p_final=0.45 and circuit_breaker=False
    (regression guard against old conviction<0.50 threshold from plan 01-03)
  - Recommendation matches run_judge_algorithm output
  - Missing modifiers in state -> default ConfidenceModifier used
  - Returned dict keys are all valid InvestmentState fields
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lockin.agents.types import (
    ConfidenceModifier,
    DataCoverage,
    JudgeOutput,
    Signal,
    ValueDistribution,
)
from lockin.graph.state import InvestmentState


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _make_coverage() -> DataCoverage:
    return DataCoverage(available=["revenue", "earnings"], missing=[])


def _make_bull_dist(expected_value: float = 200.0, confidence: float = 0.8) -> ValueDistribution:
    return ValueDistribution(
        expected_value=expected_value,
        std_dev=40.0,
        p10=expected_value * 0.7,
        p50=expected_value,
        p90=expected_value * 1.3,
        confidence=confidence,
        data_coverage=_make_coverage(),
    )


def _make_bear_dist(expected_value: float = 100.0, confidence: float = 0.5) -> ValueDistribution:
    return ValueDistribution(
        expected_value=expected_value,
        std_dev=25.0,
        p10=expected_value * 0.6,
        p50=expected_value,
        p90=expected_value * 1.2,
        confidence=confidence,
        data_coverage=_make_coverage(),
    )


def _make_oracle_modifier(base_rate: float = 0.55) -> ConfidenceModifier:
    signal = Signal(
        name="macro_base_rate",
        value=base_rate,
        category="macro",
        has_base_rate=True,
        base_rate=base_rate,
    )
    return ConfidenceModifier(
        margin_adjustment=0.0,
        variance_adjustment=0.0,
        circuit_breaker=False,
        signals=[signal],
        data_coverage=_make_coverage(),
    )


def _neutral_modifier(
    circuit_breaker: bool = False,
    circuit_breaker_reason: str | None = None,
) -> ConfidenceModifier:
    return ConfidenceModifier(
        margin_adjustment=0.0,
        variance_adjustment=0.0,
        circuit_breaker=circuit_breaker,
        circuit_breaker_reason=circuit_breaker_reason,
        signals=[],
        data_coverage=_make_coverage(),
    )


def _build_state(
    ticker: str = "AAPL",
    oracle_modifier: ConfidenceModifier | None = None,
    guardian_modifier: ConfidenceModifier | None = None,
    strategist_modifier: ConfidenceModifier | None = None,
    bull_dist: ValueDistribution | None = None,
    bear_dist: ValueDistribution | None = None,
    bull_thesis: str = "Bull thesis here.",
    bear_thesis: str = "Bear thesis here.",
) -> InvestmentState:
    state: InvestmentState = {
        "asset_ticker": ticker,
        "bull_valuation_distribution": bull_dist or _make_bull_dist(),
        "bear_valuation_distribution": bear_dist or _make_bear_dist(),
        "bull_thesis": bull_thesis,
        "bear_thesis": bear_thesis,
    }
    if oracle_modifier is not None:
        state["oracle_modifier"] = oracle_modifier
    if guardian_modifier is not None:
        state["guardian_modifier"] = guardian_modifier
    if strategist_modifier is not None:
        state["strategist_modifier"] = strategist_modifier
    return state


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

_MOCK_NARRATIVE = "Mock judicial narrative."
_MOCK_CITATIONS: list[dict] = [{"content": "Valuation report", "source_type": "10k", "source_id": "DOC-1"}]


def _mock_llm_response(content: str = _MOCK_NARRATIVE) -> MagicMock:
    """Return a mock LLM that returns content when invoked."""
    response = MagicMock()
    response.content = content
    llm = MagicMock()
    llm.invoke.return_value = response
    return llm


def _mock_yf_ticker(current_price: float = 80.0) -> MagicMock:
    """Return a mock yf.Ticker with a controlled current price."""
    ticker_obj = MagicMock()
    ticker_obj.info = {"currentPrice": current_price}
    return ticker_obj


# ---------------------------------------------------------------------------
# Test: judge calls run_judge_algorithm and surfaces its results
# ---------------------------------------------------------------------------


@patch("lockin.agents.judge.retrieve_with_citations", return_value=_MOCK_CITATIONS)
@patch("lockin.agents.judge.get_llm")
@patch("lockin.agents.judge.yf.Ticker")
def test_judge_calls_algorithm(mock_ticker_cls, mock_get_llm, mock_rag):
    """Judge agent must return fields derived from run_judge_algorithm output."""
    mock_ticker_cls.return_value = _mock_yf_ticker(current_price=80.0)
    mock_get_llm.return_value = _mock_llm_response()

    from lockin.agents.judge import judge

    state = _build_state(
        oracle_modifier=_make_oracle_modifier(base_rate=0.60),
        guardian_modifier=_neutral_modifier(),
        strategist_modifier=_neutral_modifier(),
    )
    result = judge(state, config={})

    # Core fields must be present
    assert "judge_recommendation" in result
    assert "judge_conviction" in result
    assert "judge_margin" in result
    assert "judge_price_target" in result
    assert "judge_output" in result
    assert isinstance(result["judge_output"], JudgeOutput)


# ---------------------------------------------------------------------------
# Test: HITL triggers when p_final < 0.40
# ---------------------------------------------------------------------------


@patch("lockin.agents.judge.retrieve_with_citations", return_value=[])
@patch("lockin.agents.judge.get_llm")
@patch("lockin.agents.judge.yf.Ticker")
def test_judge_hitl_low_probability(mock_ticker_cls, mock_get_llm, mock_rag):
    """p_final < 0.40 -> judge_hitl=True.

    Uses a low current_price well below precio_target so the overvaluation
    check does not fire, ensuring the HOLD path (not PASS) is reached.
    """
    # current_price=10 — far below any reasonable precio_target (which will be
    # around valor_mediano * 0.70 = ~115), so compute_recommendation reaches
    # the p_final < 0.40 check.
    mock_ticker_cls.return_value = _mock_yf_ticker(current_price=10.0)
    mock_get_llm.return_value = _mock_llm_response()

    from lockin.agents.judge import judge

    # Force low probability: base_rate=0.25 + guardian distress signal
    # margin_adjustment=0.0 to keep precio_target high above current_price=10
    oracle = _make_oracle_modifier(base_rate=0.25)
    distress_signal = Signal(
        name="z_score",
        value=1.0,
        category="bankruptcy_risk",
        has_base_rate=True,
        base_rate=0.20,
    )
    guardian = ConfidenceModifier(
        margin_adjustment=0.0,   # no margin increase — keeps target price above 10
        variance_adjustment=0.10,
        circuit_breaker=False,
        signals=[distress_signal],
        data_coverage=_make_coverage(),
    )

    state = _build_state(oracle_modifier=oracle, guardian_modifier=guardian)
    result = judge(state, config={})

    assert result["judge_hitl"] is True
    assert result["judge_conviction"] < 0.40
    assert result["judge_recommendation"] == "HOLD"
    assert len(result["judge_hitl_reason"]) > 0


# ---------------------------------------------------------------------------
# Test: HITL triggers when circuit_breaker=True
# ---------------------------------------------------------------------------


@patch("lockin.agents.judge.retrieve_with_citations", return_value=[])
@patch("lockin.agents.judge.get_llm")
@patch("lockin.agents.judge.yf.Ticker")
def test_judge_hitl_circuit_breaker(mock_ticker_cls, mock_get_llm, mock_rag):
    """circuit_breaker=True -> judge_hitl=True, recommendation='PASS'."""
    mock_ticker_cls.return_value = _mock_yf_ticker(current_price=80.0)
    mock_get_llm.return_value = _mock_llm_response()

    from lockin.agents.judge import judge

    guardian = _neutral_modifier(
        circuit_breaker=True,
        circuit_breaker_reason="Z-Score 0.8 < 1.0 AND Debt/EBITDA 5.2x",
    )
    state = _build_state(
        oracle_modifier=_make_oracle_modifier(base_rate=0.60),  # high p — doesn't matter
        guardian_modifier=guardian,
    )
    result = judge(state, config={})

    assert result["judge_hitl"] is True
    assert result["judge_recommendation"] == "PASS"
    assert "circuit breaker" in result["judge_hitl_reason"].lower()


# ---------------------------------------------------------------------------
# CRITICAL: HITL regression guard — p=0.45 must NOT trigger HITL
# This guards against regression to the old conviction<0.50 threshold (plan 01-03).
# ---------------------------------------------------------------------------


@patch("lockin.agents.judge.retrieve_with_citations", return_value=[])
@patch("lockin.agents.judge.get_llm")
@patch("lockin.agents.judge.yf.Ticker")
def test_judge_no_hitl_p_045(mock_ticker_cls, mock_get_llm, mock_rag):
    """p_final=0.45 and circuit_breaker=False -> judge_hitl MUST be False.

    REGRESSION GUARD: the old Foundation scaffold used conviction < 0.50.
    Notion spec v1.0 sets threshold at 0.40.  This test will FAIL if the
    threshold is accidentally reverted to 0.50.
    """
    mock_ticker_cls.return_value = _mock_yf_ticker(current_price=80.0)
    mock_get_llm.return_value = _mock_llm_response()

    from lockin.agents.judge import judge

    # Craft inputs that produce p_final around 0.45.
    # Oracle base_rate=0.45, no guardian adjustments -> p_final ~ 0.45
    oracle = _make_oracle_modifier(base_rate=0.45)
    guardian = _neutral_modifier(circuit_breaker=False)
    strategist = _neutral_modifier()

    state = _build_state(
        oracle_modifier=oracle,
        guardian_modifier=guardian,
        strategist_modifier=strategist,
    )
    result = judge(state, config={})

    # p_success should be around 0.45 (above the 0.40 HITL threshold)
    assert result["judge_conviction"] >= 0.40, (
        f"Expected p_final >= 0.40, got {result['judge_conviction']}"
    )
    assert result["judge_hitl"] is False, (
        f"REGRESSION: HITL triggered at p={result['judge_conviction']:.3f} "
        f"(threshold should be 0.40, not 0.50)"
    )


# ---------------------------------------------------------------------------
# Test: recommendation matches algorithm output
# ---------------------------------------------------------------------------


@patch("lockin.agents.judge.retrieve_with_citations", return_value=[])
@patch("lockin.agents.judge.get_llm")
@patch("lockin.agents.judge.yf.Ticker")
def test_judge_recommendation_from_math(mock_ticker_cls, mock_get_llm, mock_rag):
    """judge_recommendation must equal result.recommendation from run_judge_algorithm."""
    mock_ticker_cls.return_value = _mock_yf_ticker(current_price=80.0)
    mock_get_llm.return_value = _mock_llm_response()

    from lockin.agents.judge import judge
    from lockin.agents.judge_math import run_judge_algorithm

    oracle = _make_oracle_modifier(base_rate=0.60)
    guardian = _neutral_modifier()
    strategist = _neutral_modifier()
    bull = _make_bull_dist()
    bear = _make_bear_dist()

    state = _build_state(
        oracle_modifier=oracle,
        guardian_modifier=guardian,
        strategist_modifier=strategist,
        bull_dist=bull,
        bear_dist=bear,
    )
    agent_result = judge(state, config={})

    # Independently run the algorithm to verify alignment
    algo_result = run_judge_algorithm(
        bull_dist=bull,
        bear_dist=bear,
        oracle_modifier=oracle,
        guardian_modifier=guardian,
        strategist_modifier=strategist,
        current_price=80.0,
    )
    assert agent_result["judge_recommendation"] == algo_result.recommendation


# ---------------------------------------------------------------------------
# Test: returned keys are valid InvestmentState fields
# ---------------------------------------------------------------------------


@patch("lockin.agents.judge.retrieve_with_citations", return_value=[])
@patch("lockin.agents.judge.get_llm")
@patch("lockin.agents.judge.yf.Ticker")
def test_judge_state_compatible(mock_ticker_cls, mock_get_llm, mock_rag):
    """All returned dict keys must be declared fields in InvestmentState."""
    mock_ticker_cls.return_value = _mock_yf_ticker(current_price=80.0)
    mock_get_llm.return_value = _mock_llm_response()

    from lockin.agents.judge import judge

    state = _build_state(
        oracle_modifier=_make_oracle_modifier(),
        guardian_modifier=_neutral_modifier(),
        strategist_modifier=_neutral_modifier(),
    )
    result = judge(state, config={})

    # Get all declared InvestmentState fields
    state_fields = set(InvestmentState.__annotations__.keys())

    for key in result:
        assert key in state_fields, (
            f"Key '{key}' returned by judge() is not in InvestmentState."
        )


# ---------------------------------------------------------------------------
# Test: missing modifiers in state -> default ConfidenceModifier used
# ---------------------------------------------------------------------------


@patch("lockin.agents.judge.retrieve_with_citations", return_value=[])
@patch("lockin.agents.judge.get_llm")
@patch("lockin.agents.judge.yf.Ticker")
def test_judge_default_modifiers(mock_ticker_cls, mock_get_llm, mock_rag):
    """If oracle_modifier, guardian_modifier, strategist_modifier are missing
    from state, judge must use default neutral ConfidenceModifier and not crash."""
    mock_ticker_cls.return_value = _mock_yf_ticker(current_price=80.0)
    mock_get_llm.return_value = _mock_llm_response()

    from lockin.agents.judge import judge

    # State deliberately missing all modifiers
    state: InvestmentState = {
        "asset_ticker": "TSLA",
        "bull_valuation_distribution": _make_bull_dist(),
        "bear_valuation_distribution": _make_bear_dist(),
    }
    result = judge(state, config={})

    # Should succeed with defaults
    assert "judge_recommendation" in result
    assert result["judge_recommendation"] in ("BUY", "HOLD", "PASS")
    # With neutral modifiers, p_base defaults to 0.50, no adjustments
    # p_final should be 0.50 -> above HITL threshold -> hitl=False
    assert result["judge_hitl"] is False


# ---------------------------------------------------------------------------
# Test: RAG citations appear in returned citations field
# ---------------------------------------------------------------------------


@patch("lockin.agents.judge.retrieve_with_citations", return_value=_MOCK_CITATIONS)
@patch("lockin.agents.judge.get_llm")
@patch("lockin.agents.judge.yf.Ticker")
def test_judge_rag_citations_included(mock_ticker_cls, mock_get_llm, mock_rag):
    """citations field must contain whatever retrieve_with_citations returns."""
    mock_ticker_cls.return_value = _mock_yf_ticker(current_price=80.0)
    mock_get_llm.return_value = _mock_llm_response()

    from lockin.agents.judge import judge

    state = _build_state(
        oracle_modifier=_make_oracle_modifier(),
        guardian_modifier=_neutral_modifier(),
        strategist_modifier=_neutral_modifier(),
    )
    result = judge(state, config={})

    assert result["citations"] == _MOCK_CITATIONS
