"""
Unit tests for the Strategist agent.

All external dependencies are mocked:
  - httpx.get: returns a fake FMP transcript response
  - yf.Ticker().recommendations_summary: returns analyst data DataFrame
  - get_llm: returns a mock LLM producing fixed JSON responses

Tests verify the critical design constraints from the Notion Judge spec:
  - VeTO signal has has_base_rate=False and base_rate=None
  - VeTO adjusts variance ONLY (+0.10 when score < 0.4, 0.0 when score >= 0.4)
  - VeTO does NOT adjust margin_adjustment (deferred to Phase 4)
  - analyst_momentum has has_base_rate=True, base_rate_source="Jegadeesh (2004)"
  - margin_adjustment comes from analyst downgrades only (+0.05 for net downgrades)
  - circuit_breaker is always False regardless of inputs
  - Graceful degradation when FMP key is absent
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from lockin.agents.strategist import strategist
from lockin.agents.types import ConfidenceModifier, Signal


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_llm_response(
    overall_sentiment: float = 0.6,
    veto_score: float = 0.7,
    sentiment_label: str = "bullish",
    narrative: str = "Management tone is constructive with clear guidance.",
) -> str:
    """Return a JSON string as the mock LLM would produce."""
    return json.dumps({
        "overall_sentiment": overall_sentiment,
        "veto_score": veto_score,
        "sentiment_label": sentiment_label,
        "narrative": narrative,
    })


def _make_mock_llm(veto_score: float = 0.7, sentiment: float = 0.6) -> MagicMock:
    """Construct a mock LLM that returns a fixed JSON sentiment response."""
    mock_llm = MagicMock()
    mock_message = MagicMock()
    mock_message.content = _make_llm_response(
        overall_sentiment=sentiment,
        veto_score=veto_score,
    )
    mock_llm.invoke.return_value = mock_message
    return mock_llm


def _make_httpx_response(ticker: str = "AAPL") -> MagicMock:
    """Construct a mock httpx response with a fake FMP transcript."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            "symbol": ticker,
            "quarter": 1,
            "year": 2024,
            "content": (
                "Thank you for joining us today. We delivered strong results this quarter. "
                "Revenue grew 12% year-over-year driven by services expansion. "
                "We remain confident in our guidance for the full year. "
                "Free cash flow was $28 billion, up 18% from last year."
            ),
        }
    ]
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _make_analyst_summary(
    strong_buy: int = 6,
    buy: int = 25,
    hold: int = 15,
    sell: int = 1,
    strong_sell: int = 1,
) -> pd.DataFrame:
    """Return a yfinance recommendations_summary-compatible DataFrame."""
    return pd.DataFrame([
        {
            "period": "0m",
            "strongBuy": strong_buy,
            "buy": buy,
            "hold": hold,
            "sell": sell,
            "strongSell": strong_sell,
        }
    ])


def _run_strategist(
    veto_score: float = 0.7,
    sentiment: float = 0.6,
    strong_buy: int = 6,
    buy: int = 25,
    hold: int = 15,
    sell: int = 1,
    strong_sell: int = 1,
    fmp_api_key: str = "test_fmp_key_123",
    earningscall_api_key: str = "",
    earningscall_result: tuple[str, bool] | None = None,
    ticker: str = "AAPL",
) -> dict:
    """Run strategist() with all external deps mocked, return result dict.

    By default earningscall returns ("", False) so tests fall through to FMP.
    Pass earningscall_result=(text, True) to simulate earningscall success.
    """
    state = {"asset_ticker": ticker, "bull_iteration": 0}
    config = {"configurable": {"thread_id": "test-strategist"}}

    mock_llm = _make_mock_llm(veto_score=veto_score, sentiment=sentiment)
    mock_httpx_resp = _make_httpx_response(ticker)
    analyst_df = _make_analyst_summary(strong_buy, buy, hold, sell, strong_sell)

    if earningscall_result is None:
        earningscall_result = ("", False)

    # Patch the module-level transcript cache to avoid cross-test contamination
    with (
        patch("lockin.agents.strategist._TRANSCRIPT_CACHE", {}),
        patch(
            "lockin.agents.strategist._fetch_earningscall_transcript",
            return_value=earningscall_result,
        ),
        patch("lockin.agents.strategist.httpx.get", return_value=mock_httpx_resp),
        patch("lockin.agents.strategist.yf.Ticker") as mock_ticker_class,
        patch("lockin.agents.strategist.get_llm", return_value=mock_llm),
        patch(
            "lockin.agents.strategist.get_settings",
            return_value=MagicMock(
                fmp_api_key=fmp_api_key,
                earningscall_api_key=earningscall_api_key,
                google_api_key="test_google_key",
                strategist_model="gemini-2.5-flash",
            ),
        ),
    ):
        mock_ticker_instance = MagicMock()
        mock_ticker_instance.recommendations_summary = analyst_df
        mock_ticker_class.return_value = mock_ticker_instance

        return strategist(state, config)


# ---------------------------------------------------------------------------
# LangGraph config fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def thread_config() -> dict:
    return {"configurable": {"thread_id": "test-strategist"}}


@pytest.fixture
def initial_state() -> dict:
    return {"asset_ticker": "AAPL", "bull_iteration": 0}


# ---------------------------------------------------------------------------
# Test 1: Returns ConfidenceModifier, circuit_breaker=False
# ---------------------------------------------------------------------------


def test_strategist_returns_confidence_modifier():
    """Strategist returns dict with strategist_modifier as ConfidenceModifier, circuit_breaker=False."""
    result = _run_strategist()

    assert "strategist_modifier" in result, "strategist_modifier key missing from result"
    modifier = result["strategist_modifier"]

    assert isinstance(modifier, ConfidenceModifier), (
        f"Expected ConfidenceModifier, got {type(modifier)}"
    )
    assert modifier.circuit_breaker is False, (
        "circuit_breaker must always be False for Strategist"
    )


# ---------------------------------------------------------------------------
# Test 2: VeTO Signal has has_base_rate=False and base_rate=None
# ---------------------------------------------------------------------------


def test_strategist_veto_no_base_rate():
    """VeTO Signal must have has_base_rate=False and base_rate=None (no empirical validation)."""
    result = _run_strategist(veto_score=0.7)
    modifier = result["strategist_modifier"]

    signal_names = [s.name for s in modifier.signals]
    assert "veto_score" in signal_names, (
        f"veto_score signal not found. Signals: {signal_names}"
    )

    veto_signal = next(s for s in modifier.signals if s.name == "veto_score")
    assert veto_signal.has_base_rate is False, (
        "VeTO signal must have has_base_rate=False — it has no empirical base rate"
    )
    assert veto_signal.base_rate is None, (
        f"VeTO base_rate must be None, got {veto_signal.base_rate}"
    )


# ---------------------------------------------------------------------------
# Test 3: VeTO adjusts variance ONLY — both branches
# ---------------------------------------------------------------------------


def test_strategist_veto_adjusts_variance_only():
    """Low VeTO (score < 0.4) -> variance_adjustment >= 0.10; High VeTO (>= 0.4) -> 0.0."""
    # --- Low VeTO branch ---
    result_low = _run_strategist(veto_score=0.2)
    modifier_low = result_low["strategist_modifier"]
    assert modifier_low.variance_adjustment >= 0.10, (
        f"Low VeTO (0.2) must yield variance_adjustment >= 0.10, "
        f"got {modifier_low.variance_adjustment}"
    )

    # --- High VeTO branch ---
    result_high = _run_strategist(veto_score=0.8)
    modifier_high = result_high["strategist_modifier"]
    assert modifier_high.variance_adjustment == 0.0, (
        f"High VeTO (0.8) must yield variance_adjustment == 0.0, "
        f"got {modifier_high.variance_adjustment}"
    )


# ---------------------------------------------------------------------------
# Test 4: VeTO does NOT contribute to margin_adjustment
# ---------------------------------------------------------------------------


def test_strategist_veto_no_margin():
    """VeTO score low (0.2) with no analyst downgrades -> margin_adjustment == 0.0 (VeTO deferred)."""
    # Net upgrades (no downgrades) → analyst does not trigger margin either
    # All buys, no sells → analyst_momentum positive, no margin bump
    result = _run_strategist(
        veto_score=0.2,   # Low VeTO
        strong_buy=20,
        buy=30,
        hold=5,
        sell=0,           # No sells
        strong_sell=0,
    )
    modifier = result["strategist_modifier"]

    assert modifier.margin_adjustment == 0.0, (
        f"VeTO must NOT contribute to margin_adjustment (deferred to Phase 4). "
        f"Got margin_adjustment={modifier.margin_adjustment}. "
        f"VeTO score was 0.2 (low), but no analyst downgrades — "
        f"expected 0.0, not a VeTO-driven value."
    )


# ---------------------------------------------------------------------------
# Test 5: analyst_momentum Signal has has_base_rate=True and Jegadeesh (2004) source
# ---------------------------------------------------------------------------


def test_strategist_analyst_momentum_has_base_rate():
    """analyst_momentum Signal must have has_base_rate=True and base_rate_source='Jegadeesh (2004)'."""
    result = _run_strategist()
    modifier = result["strategist_modifier"]

    signal_names = [s.name for s in modifier.signals]
    assert "analyst_momentum" in signal_names, (
        f"analyst_momentum signal not found. Signals: {signal_names}"
    )

    momentum_signal = next(s for s in modifier.signals if s.name == "analyst_momentum")
    assert momentum_signal.has_base_rate is True, (
        "analyst_momentum must have has_base_rate=True (calibrated from academic literature)"
    )
    assert momentum_signal.base_rate_source == "Jegadeesh (2004)", (
        f"analyst_momentum base_rate_source must be 'Jegadeesh (2004)', "
        f"got '{momentum_signal.base_rate_source}'"
    )


# ---------------------------------------------------------------------------
# Test 6: margin_adjustment == 0.05 for net analyst downgrades only
# ---------------------------------------------------------------------------


def test_strategist_margin_adjustment_analyst_only():
    """Net analyst downgrades (momentum < 0) -> margin_adjustment == 0.05; VeTO does not add to margin."""
    # Construct heavy sell-side consensus: more sells than buys
    result = _run_strategist(
        veto_score=0.8,   # High VeTO (healthy) — ensures no variance adjustment
        strong_buy=0,
        buy=2,
        hold=10,
        sell=15,          # More sells than buys → net downgrade
        strong_sell=3,
    )
    modifier = result["strategist_modifier"]

    # Net: buys=2, sells=18 → momentum = (2 - 18) / 30 = -0.53 → downgrades
    assert modifier.margin_adjustment == 0.05, (
        f"Net analyst downgrades should yield margin_adjustment == 0.05, "
        f"got {modifier.margin_adjustment}"
    )
    # VeTO high (0.8) → no variance adjustment
    assert modifier.variance_adjustment == 0.0, (
        f"High VeTO (0.8) should yield variance_adjustment == 0.0, "
        f"got {modifier.variance_adjustment}"
    )


# ---------------------------------------------------------------------------
# Test 7: Graceful fallback when FMP key is absent
# ---------------------------------------------------------------------------


def test_strategist_no_transcript_keys():
    """No transcript API keys -> skips both fetches, still returns valid ConfidenceModifier."""
    state = {"asset_ticker": "MSFT", "bull_iteration": 0}
    config = {"configurable": {"thread_id": "test-strategist-no-fmp"}}

    analyst_df = _make_analyst_summary()
    mock_llm = _make_mock_llm(veto_score=0.65, sentiment=0.55)

    with (
        patch("lockin.agents.strategist._TRANSCRIPT_CACHE", {}),
        patch(
            "lockin.agents.strategist._fetch_earningscall_transcript",
            return_value=("", False),
        ),
        patch("lockin.agents.strategist.httpx.get") as mock_http,
        patch("lockin.agents.strategist.yf.Ticker") as mock_ticker_class,
        patch("lockin.agents.strategist.get_llm", return_value=mock_llm),
        patch(
            "lockin.agents.strategist.get_settings",
            return_value=MagicMock(
                fmp_api_key="",          # Empty key — no FMP fetch
                earningscall_api_key="",
                google_api_key="test_google_key",
                strategist_model="gemini-2.5-flash",
            ),
        ),
    ):
        mock_ticker_instance = MagicMock()
        mock_ticker_instance.recommendations_summary = analyst_df
        mock_ticker_class.return_value = mock_ticker_instance

        result = strategist(state, config)

    # httpx.get must NOT have been called (no FMP key)
    mock_http.assert_not_called()

    # Still returns a valid ConfidenceModifier
    assert "strategist_modifier" in result
    modifier = result["strategist_modifier"]
    assert isinstance(modifier, ConfidenceModifier), (
        f"Expected ConfidenceModifier even without transcript APIs, got {type(modifier)}"
    )
    assert modifier.circuit_breaker is False

    # transcript should be in missing sources
    assert "transcript" in modifier.data_coverage.missing, (
        f"transcript should be in missing sources when no keys. "
        f"missing={modifier.data_coverage.missing}"
    )


# ---------------------------------------------------------------------------
# Test 8: EarningsCall transcript used as primary source
# ---------------------------------------------------------------------------


def test_strategist_earningscall_primary():
    """When EarningsCall returns a transcript, it is used (FMP not called)."""
    ec_text = "Good morning. We delivered record results this quarter."
    result = _run_strategist(
        earningscall_result=(ec_text, True),
        fmp_api_key="test_fmp_key",
    )
    modifier = result["strategist_modifier"]

    assert "earningscall_transcript" in modifier.data_coverage.available, (
        f"earningscall_transcript should be in available sources. "
        f"available={modifier.data_coverage.available}"
    )
    # FMP should not appear in available (earningscall succeeded, FMP skipped)
    assert "fmp_transcript" not in modifier.data_coverage.available


# ---------------------------------------------------------------------------
# Test 9: FMP used as fallback when EarningsCall fails
# ---------------------------------------------------------------------------


def test_strategist_fmp_fallback():
    """When EarningsCall fails, FMP is used as fallback."""
    result = _run_strategist(
        earningscall_result=("", False),  # EarningsCall fails
        fmp_api_key="test_fmp_key",       # FMP available
    )
    modifier = result["strategist_modifier"]

    assert "fmp_transcript" in modifier.data_coverage.available, (
        f"fmp_transcript should be in available (fallback). "
        f"available={modifier.data_coverage.available}"
    )
    assert "earningscall_transcript" not in modifier.data_coverage.available


# ---------------------------------------------------------------------------
# Test 10: circuit_breaker is always False regardless of inputs
# ---------------------------------------------------------------------------


def test_strategist_circuit_breaker_always_false():
    """circuit_breaker must be False even with worst-case inputs (low VeTO, heavy downgrades)."""
    # Worst-case: low VeTO + heavy sell-side consensus
    result = _run_strategist(
        veto_score=0.05,   # Extremely low VeTO
        strong_buy=0,
        buy=0,
        hold=2,
        sell=20,
        strong_sell=10,
    )
    modifier = result["strategist_modifier"]
    assert modifier.circuit_breaker is False, (
        f"circuit_breaker must ALWAYS be False for Strategist. "
        f"Got circuit_breaker={modifier.circuit_breaker}"
    )
    assert modifier.circuit_breaker_reason is None, (
        f"circuit_breaker_reason must be None for Strategist. "
        f"Got: '{modifier.circuit_breaker_reason}'"
    )
