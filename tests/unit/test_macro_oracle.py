"""
Unit tests for the Macro Oracle agent.

All external dependencies are mocked:
  - get_macro_indicators: returns a fixed MacroResult dict
  - get_llm: returns a mock LLM that produces fixed JSON responses

Tests verify:
  - Regime detection (phase, yield curve, fed stance) from FRED data
  - ConfidenceModifier output contract (circuit_breaker=False, signals with base rates)
  - Fallback behaviour when FRED is unavailable (DataUnavailableError)
  - Margin adjustments for extreme regimes (greed / fear)
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from lockin.agents.macro_oracle import macro_oracle
from lockin.agents.types import ConfidenceModifier, Signal
from lockin.data.exceptions import DataUnavailableError


# ---------------------------------------------------------------------------
# Fixtures and shared helpers
# ---------------------------------------------------------------------------


def _make_macro_result(**overrides) -> dict:
    """Return a minimal MacroResult-compatible dict for test setup."""
    defaults = {
        "gdp": 2.5,
        "cpi": 3.1,
        "core_pce": 2.7,
        "fed_funds": 5.25,
        "yield_10y_2y": 0.8,   # positive = normal curve
        "yield_10y_3m": 1.2,
        "unemployment": 3.8,
        "source": "FRED",
        "fetched_at": datetime.now(),
        "as_of_date": "live",
        "data_freshness": "FRESH",
    }
    defaults.update(overrides)
    return defaults


def _make_llm_response(
    phase: str = "expansion",
    risk_appetite: str = "risk_on",
    yield_curve: str = "normal",
    fed_stance: str = "hawkish",
    reasoning: str = "Solid expansion with elevated rates.",
) -> str:
    """Return a JSON string as the mock LLM would produce."""
    import json
    return json.dumps({
        "phase": phase,
        "risk_appetite": risk_appetite,
        "yield_curve": yield_curve,
        "fed_stance": fed_stance,
        "reasoning": reasoning,
    })


def _make_mock_llm(response_json: str) -> MagicMock:
    """Construct a mock ChatGoogleGenerativeAI that returns a fixed response."""
    mock_llm = MagicMock()
    mock_message = MagicMock()
    mock_message.content = response_json
    mock_llm.invoke.return_value = mock_message
    return mock_llm


# ---------------------------------------------------------------------------
# LangGraph config fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def thread_config() -> dict:
    return {"configurable": {"thread_id": "test-macro-oracle"}}


@pytest.fixture
def initial_state() -> dict:
    return {"asset_ticker": "AAPL", "bull_iteration": 0}


# ---------------------------------------------------------------------------
# Test 1: Expansion regime — verify regime dict fields
# ---------------------------------------------------------------------------


def test_macro_oracle_expansion(initial_state, thread_config):
    """Macro Oracle returns expected regime fields in expansion."""
    macro_data = _make_macro_result()  # positive GDP, fed_funds=5.25, normal curve
    llm_response = _make_llm_response(
        phase="expansion",
        risk_appetite="risk_on",
        yield_curve="normal",
        fed_stance="hawkish",
    )
    mock_llm = _make_mock_llm(llm_response)

    with (
        patch("lockin.agents.macro_oracle.get_macro_indicators", return_value=macro_data),
        patch("lockin.agents.macro_oracle.get_llm", return_value=mock_llm),
    ):
        result = macro_oracle(initial_state, thread_config)

    assert "macro_regime" in result
    regime = result["macro_regime"]
    assert regime["phase"] == "expansion"
    assert regime["risk_appetite"] == "risk_on"
    # Deterministic: fed_funds=5.25 > 4.0 → hawkish
    assert regime["fed_stance"] == "hawkish"
    # Deterministic: yield_10y_2y=0.8 > 0.5 → normal
    assert regime["yield_curve"] == "normal"

    assert "macro_confidence" in result
    assert 0.0 < result["macro_confidence"] <= 1.0

    assert "macro_narrative" in result
    assert isinstance(result["macro_narrative"], str)
    assert len(result["macro_narrative"]) > 0


# ---------------------------------------------------------------------------
# Test 2: Inverted yield curve — verify yield_curve="inverted"
# ---------------------------------------------------------------------------


def test_macro_oracle_inverted_yield_curve(initial_state, thread_config):
    """When yield_10y_2y is negative, yield_curve must be 'inverted'."""
    macro_data = _make_macro_result(
        yield_10y_2y=-0.5,  # inverted!
        yield_10y_3m=-0.3,
        fed_funds=5.25,
    )
    llm_response = _make_llm_response(
        phase="late_expansion",
        risk_appetite="neutral",
        yield_curve="inverted",  # LLM agrees
        fed_stance="hawkish",
    )
    mock_llm = _make_mock_llm(llm_response)

    with (
        patch("lockin.agents.macro_oracle.get_macro_indicators", return_value=macro_data),
        patch("lockin.agents.macro_oracle.get_llm", return_value=mock_llm),
    ):
        result = macro_oracle(initial_state, thread_config)

    regime = result["macro_regime"]
    # Deterministic rule must fire: yield_10y_2y=-0.5 < 0 → inverted
    assert regime["yield_curve"] == "inverted", (
        f"Expected 'inverted' but got '{regime['yield_curve']}'"
    )


# ---------------------------------------------------------------------------
# Test 3: FRED data unavailable → fallback with macro_confidence <= 0.3
# ---------------------------------------------------------------------------


def test_macro_oracle_data_unavailable(initial_state, thread_config):
    """When FRED raises DataUnavailableError, agent returns fallback with low confidence."""
    with patch(
        "lockin.agents.macro_oracle.get_macro_indicators",
        side_effect=DataUnavailableError(ticker="FRED", source="fred", message="API key missing"),
    ):
        result = macro_oracle(initial_state, thread_config)

    assert "macro_confidence" in result
    assert result["macro_confidence"] <= 0.3, (
        f"Expected macro_confidence <= 0.3 in fallback but got {result['macro_confidence']}"
    )
    assert "oracle_modifier" in result
    modifier = result["oracle_modifier"]
    assert isinstance(modifier, ConfidenceModifier)
    # Fallback must never trigger circuit breaker
    assert modifier.circuit_breaker is False


# ---------------------------------------------------------------------------
# Test 4: Returns ConfidenceModifier with correct contract
# ---------------------------------------------------------------------------


def test_macro_oracle_returns_confidence_modifier(initial_state, thread_config):
    """oracle_modifier must be ConfidenceModifier, circuit_breaker=False, with macro_base_rate signal."""
    macro_data = _make_macro_result()
    llm_response = _make_llm_response()
    mock_llm = _make_mock_llm(llm_response)

    with (
        patch("lockin.agents.macro_oracle.get_macro_indicators", return_value=macro_data),
        patch("lockin.agents.macro_oracle.get_llm", return_value=mock_llm),
    ):
        result = macro_oracle(initial_state, thread_config)

    assert "oracle_modifier" in result, "oracle_modifier key missing from result"
    modifier = result["oracle_modifier"]

    # Type contract
    assert isinstance(modifier, ConfidenceModifier), (
        f"Expected ConfidenceModifier, got {type(modifier)}"
    )

    # Oracle NEVER triggers circuit breaker
    assert modifier.circuit_breaker is False, (
        "circuit_breaker must always be False for Macro Oracle"
    )

    # Must have signals list
    assert isinstance(modifier.signals, list)
    assert len(modifier.signals) > 0

    # macro_base_rate signal with has_base_rate=True must be present
    signal_names = [s.name for s in modifier.signals]
    assert "macro_base_rate" in signal_names, (
        f"macro_base_rate signal not found. Signals: {signal_names}"
    )

    macro_base_rate_signal = next(s for s in modifier.signals if s.name == "macro_base_rate")
    assert macro_base_rate_signal.has_base_rate is True, (
        "macro_base_rate signal must have has_base_rate=True"
    )
    assert macro_base_rate_signal.base_rate is not None


# ---------------------------------------------------------------------------
# Test 5: Extreme greed → margin_adjustment in [+0.15, +0.20]
# ---------------------------------------------------------------------------


def test_macro_oracle_extreme_greed_margin(initial_state, thread_config):
    """In extreme greed (expansion + risk_on + normal curve), margin_adjustment ∈ [+0.15, +0.20]."""
    macro_data = _make_macro_result(
        gdp=3.5,
        yield_10y_2y=1.5,   # normal curve
        yield_10y_3m=2.0,
        fed_funds=2.5,       # neutral Fed
    )
    llm_response = _make_llm_response(
        phase="expansion",
        risk_appetite="risk_on",
        yield_curve="normal",
        fed_stance="neutral",
    )
    mock_llm = _make_mock_llm(llm_response)

    with (
        patch("lockin.agents.macro_oracle.get_macro_indicators", return_value=macro_data),
        patch("lockin.agents.macro_oracle.get_llm", return_value=mock_llm),
    ):
        result = macro_oracle(initial_state, thread_config)

    modifier = result["oracle_modifier"]
    assert 0.15 <= modifier.margin_adjustment <= 0.20, (
        f"Expected margin_adjustment in [0.15, 0.20] for extreme greed, "
        f"got {modifier.margin_adjustment}"
    )


# ---------------------------------------------------------------------------
# Test 6: Extreme fear → margin_adjustment is negative
# ---------------------------------------------------------------------------


def test_macro_oracle_extreme_fear_margin(initial_state, thread_config):
    """In extreme fear (contraction + risk_off + inverted), margin_adjustment must be negative."""
    macro_data = _make_macro_result(
        gdp=-1.2,            # contraction
        yield_10y_2y=-0.8,  # inverted
        yield_10y_3m=-0.5,
        fed_funds=5.50,      # hawkish
    )
    llm_response = _make_llm_response(
        phase="contraction",
        risk_appetite="risk_off",
        yield_curve="inverted",
        fed_stance="hawkish",
        reasoning="Recession indicators: inverted curve, negative GDP, risk-off sentiment.",
    )
    mock_llm = _make_mock_llm(llm_response)

    with (
        patch("lockin.agents.macro_oracle.get_macro_indicators", return_value=macro_data),
        patch("lockin.agents.macro_oracle.get_llm", return_value=mock_llm),
    ):
        result = macro_oracle(initial_state, thread_config)

    modifier = result["oracle_modifier"]
    assert modifier.margin_adjustment < 0, (
        f"Expected negative margin_adjustment for extreme fear, "
        f"got {modifier.margin_adjustment}"
    )
    # Per spec: should be -0.05 for pure extreme fear
    assert modifier.margin_adjustment <= -0.03, (
        f"Expected margin_adjustment <= -0.03 for contraction+risk_off+inverted, "
        f"got {modifier.margin_adjustment}"
    )
