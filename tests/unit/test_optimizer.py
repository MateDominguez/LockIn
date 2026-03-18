"""
Unit tests for the Optimizer agent in lockin.agents.optimizer.

Tests cover:
  - kelly_criterion() formula correctness (positive, negative, edge cases)
  - optimizer() decision table (BUY, HOLD, PASS, circuit breaker paths)
  - Position cap enforcement (10% hard cap)
  - Circuit breaker override cap enforcement (<=2%)
  - Constant verification (KELLY_FRACTION == 0.33)

All network calls (yf.Ticker, get_llm) are mocked to avoid I/O in unit tests.
JudgeOutput objects are built directly from lockin.agents.types.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lockin.agents.optimizer import (
    CIRCUIT_BREAKER_OVERRIDE_CAP,
    KELLY_FRACTION,
    MAX_POSITION_SIZE,
    kelly_criterion,
)
from lockin.agents.types import JudgeOutput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_judge_output(
    recommendation: str = "BUY",
    kelly_fraction: float = 0.05,
    p_success: float = 0.60,
    circuit_breaker: bool = False,
    circuit_breaker_override: bool = False,
) -> JudgeOutput:
    """Build a minimal JudgeOutput for testing."""
    return JudgeOutput(
        recommendation=recommendation,
        consensus_distribution=(4.0, 0.20),
        valor_mediano=55.0,
        precio_target=60.0,
        margin_of_safety=0.30,
        p_success=p_success,
        p_base=0.55,
        kelly_fraction=kelly_fraction,
        circuit_breaker=circuit_breaker,
        circuit_breaker_override=circuit_breaker_override,
    )


def make_state(judge_out: JudgeOutput, ticker: str = "AAPL") -> dict:
    """Wrap a JudgeOutput into a minimal InvestmentState dict."""
    return {
        "asset_ticker": ticker,
        "judge_output": judge_out,
        "bull_iteration": 0,
    }


# Shared mock config (LangGraph RunnableConfig not needed for unit tests)
MOCK_CONFIG = MagicMock()


# ---------------------------------------------------------------------------
# Kelly criterion formula tests
# ---------------------------------------------------------------------------


class TestKellyCriterion:
    """Tests for the standalone kelly_criterion() formula."""

    def test_kelly_basic(self):
        """win_prob=0.6, win_loss_ratio=2.0 -> f* = (0.6*2 - 0.4) / 2 = 0.4"""
        result = kelly_criterion(win_prob=0.6, win_loss_ratio=2.0)
        assert abs(result - 0.4) < 1e-9, f"Expected 0.4, got {result}"

    def test_kelly_negative_edge_returns_zero(self):
        """win_prob=0.3, win_loss_ratio=1.0 -> f* = -0.4 -> clamped to 0.0"""
        result = kelly_criterion(win_prob=0.3, win_loss_ratio=1.0)
        assert result == 0.0, f"Expected 0.0 (negative edge), got {result}"

    def test_kelly_edge_50_50(self):
        """win_prob=0.5, win_loss_ratio=1.0 -> f* = (0.5 - 0.5) / 1.0 = 0.0"""
        result = kelly_criterion(win_prob=0.5, win_loss_ratio=1.0)
        assert result == 0.0, f"Expected 0.0 (breakeven), got {result}"

    def test_kelly_zero_ratio_returns_zero(self):
        """win_loss_ratio <= 0 must return 0.0 without dividing by zero."""
        assert kelly_criterion(win_prob=0.9, win_loss_ratio=0.0) == 0.0
        assert kelly_criterion(win_prob=0.9, win_loss_ratio=-1.0) == 0.0


# ---------------------------------------------------------------------------
# Constant verification
# ---------------------------------------------------------------------------


class TestConstants:
    """Verify spec constants are set correctly."""

    def test_kelly_third_not_fourth(self):
        """KELLY_FRACTION must be 0.33 (Kelly/3), NOT 0.25 (Kelly/4)."""
        assert KELLY_FRACTION == 0.33, (
            f"KELLY_FRACTION should be 0.33 (Kelly/3), got {KELLY_FRACTION}"
        )

    def test_max_position_size_10pct(self):
        """MAX_POSITION_SIZE must be 0.10 (10% hard cap)."""
        assert MAX_POSITION_SIZE == 0.10

    def test_circuit_breaker_override_cap_2pct(self):
        """CIRCUIT_BREAKER_OVERRIDE_CAP must be 0.02 (2% hard cap)."""
        assert CIRCUIT_BREAKER_OVERRIDE_CAP == 0.02


# ---------------------------------------------------------------------------
# Optimizer decision table tests
# ---------------------------------------------------------------------------


class TestOptimizerDecisionTable:
    """Tests for optimizer() — decision table (BUY, HOLD, PASS, CB paths)."""

    @patch("lockin.agents.optimizer.get_llm")
    @patch("lockin.agents.optimizer.yf.Ticker")
    def test_optimizer_buy(self, mock_ticker, mock_get_llm):
        """BUY with kelly_fraction=0.05 -> position_size == 0.05 (under cap)."""
        from lockin.agents.optimizer import optimizer

        _setup_yf_mock(mock_ticker)
        _setup_llm_mock(mock_get_llm)

        judge_out = make_judge_output(recommendation="BUY", kelly_fraction=0.05)
        state = make_state(judge_out)

        result = optimizer(state, MOCK_CONFIG)

        assert result["optimizer_portfolio"]["AAPL"] == pytest.approx(0.05)
        assert result["optimizer_metrics"]["position_size"] == pytest.approx(0.05)
        assert result["optimizer_metrics"]["kelly_fraction"] == pytest.approx(0.05)

    @patch("lockin.agents.optimizer.get_llm")
    @patch("lockin.agents.optimizer.yf.Ticker")
    def test_optimizer_pass(self, mock_ticker, mock_get_llm):
        """PASS recommendation -> position_size == 0.0 regardless of kelly_fraction."""
        from lockin.agents.optimizer import optimizer

        _setup_yf_mock(mock_ticker)
        _setup_llm_mock(mock_get_llm)

        judge_out = make_judge_output(recommendation="PASS", kelly_fraction=0.08)
        state = make_state(judge_out)

        result = optimizer(state, MOCK_CONFIG)

        assert result["optimizer_portfolio"]["AAPL"] == 0.0
        assert result["optimizer_metrics"]["position_size"] == 0.0

    @patch("lockin.agents.optimizer.get_llm")
    @patch("lockin.agents.optimizer.yf.Ticker")
    def test_optimizer_hold(self, mock_ticker, mock_get_llm):
        """HOLD recommendation -> 0 new capital allocated."""
        from lockin.agents.optimizer import optimizer

        _setup_yf_mock(mock_ticker)
        _setup_llm_mock(mock_get_llm)

        judge_out = make_judge_output(recommendation="HOLD", kelly_fraction=0.06)
        state = make_state(judge_out)

        result = optimizer(state, MOCK_CONFIG)

        assert result["optimizer_portfolio"]["AAPL"] == 0.0
        assert result["optimizer_metrics"]["position_size"] == 0.0

    @patch("lockin.agents.optimizer.get_llm")
    @patch("lockin.agents.optimizer.yf.Ticker")
    def test_optimizer_position_cap_10pct(self, mock_ticker, mock_get_llm):
        """BUY with kelly_fraction=0.15 -> position capped at 10% (MAX_POSITION_SIZE)."""
        from lockin.agents.optimizer import optimizer

        _setup_yf_mock(mock_ticker)
        _setup_llm_mock(mock_get_llm)

        judge_out = make_judge_output(recommendation="BUY", kelly_fraction=0.15)
        state = make_state(judge_out)

        result = optimizer(state, MOCK_CONFIG)

        assert result["optimizer_portfolio"]["AAPL"] == pytest.approx(0.10)
        assert result["optimizer_metrics"]["position_size"] == pytest.approx(0.10)
        assert result["optimizer_metrics"]["position_cap_applied"] is True

    @patch("lockin.agents.optimizer.get_llm")
    @patch("lockin.agents.optimizer.yf.Ticker")
    def test_optimizer_circuit_breaker_override(self, mock_ticker, mock_get_llm):
        """circuit_breaker_override=True, kelly_fraction=0.08 -> position <= 2%."""
        from lockin.agents.optimizer import optimizer

        _setup_yf_mock(mock_ticker)
        _setup_llm_mock(mock_get_llm)

        judge_out = make_judge_output(
            recommendation="BUY",
            kelly_fraction=0.08,
            circuit_breaker=True,
            circuit_breaker_override=True,
        )
        state = make_state(judge_out)

        result = optimizer(state, MOCK_CONFIG)

        position = result["optimizer_portfolio"]["AAPL"]
        assert position <= CIRCUIT_BREAKER_OVERRIDE_CAP, (
            f"Circuit breaker override should cap position at {CIRCUIT_BREAKER_OVERRIDE_CAP}, "
            f"got {position}"
        )
        assert result["optimizer_metrics"]["circuit_breaker_override_applied"] is True

    @patch("lockin.agents.optimizer.get_llm")
    @patch("lockin.agents.optimizer.yf.Ticker")
    def test_optimizer_circuit_breaker_no_override(self, mock_ticker, mock_get_llm):
        """circuit_breaker=True, circuit_breaker_override=False -> position == 0.0."""
        from lockin.agents.optimizer import optimizer

        _setup_yf_mock(mock_ticker)
        _setup_llm_mock(mock_get_llm)

        judge_out = make_judge_output(
            recommendation="BUY",
            kelly_fraction=0.08,
            circuit_breaker=True,
            circuit_breaker_override=False,
        )
        state = make_state(judge_out)

        result = optimizer(state, MOCK_CONFIG)

        assert result["optimizer_portfolio"]["AAPL"] == 0.0, (
            "Circuit breaker with no override must produce 0 position"
        )


# ---------------------------------------------------------------------------
# Output structure tests
# ---------------------------------------------------------------------------


class TestOptimizerOutputStructure:
    """Tests for optimizer() return value structure."""

    @patch("lockin.agents.optimizer.get_llm")
    @patch("lockin.agents.optimizer.yf.Ticker")
    def test_optimizer_returns_all_keys(self, mock_ticker, mock_get_llm):
        """optimizer() must return all required optimizer_* keys."""
        from lockin.agents.optimizer import optimizer

        _setup_yf_mock(mock_ticker)
        _setup_llm_mock(mock_get_llm)

        judge_out = make_judge_output(recommendation="BUY", kelly_fraction=0.05)
        state = make_state(judge_out)

        result = optimizer(state, MOCK_CONFIG)

        assert "optimizer_portfolio" in result
        assert "optimizer_sectors" in result
        assert "optimizer_rebalancing" in result
        assert "optimizer_metrics" in result
        assert "optimizer_narrative" in result

    @patch("lockin.agents.optimizer.get_llm")
    @patch("lockin.agents.optimizer.yf.Ticker")
    def test_optimizer_metrics_keys(self, mock_ticker, mock_get_llm):
        """optimizer_metrics must contain all expected sub-keys."""
        from lockin.agents.optimizer import optimizer

        _setup_yf_mock(mock_ticker)
        _setup_llm_mock(mock_get_llm)

        judge_out = make_judge_output(recommendation="BUY", kelly_fraction=0.05)
        state = make_state(judge_out)

        result = optimizer(state, MOCK_CONFIG)
        metrics = result["optimizer_metrics"]

        expected_keys = {
            "kelly_fraction",
            "position_size",
            "position_cap_applied",
            "circuit_breaker_override_applied",
            "expected_return",
            "portfolio_risk",
            "sharpe",
            "max_drawdown_estimate",
        }
        assert expected_keys.issubset(metrics.keys()), (
            f"Missing metrics keys: {expected_keys - set(metrics.keys())}"
        )

    @patch("lockin.agents.optimizer.get_llm")
    @patch("lockin.agents.optimizer.yf.Ticker")
    def test_optimizer_llm_failure_uses_fallback_narrative(
        self, mock_ticker, mock_get_llm
    ):
        """If LLM fails, optimizer_narrative falls back to deterministic string."""
        from lockin.agents.optimizer import optimizer

        _setup_yf_mock(mock_ticker)
        # Simulate LLM raising an exception
        mock_get_llm.side_effect = Exception("API unavailable")

        judge_out = make_judge_output(recommendation="BUY", kelly_fraction=0.05)
        state = make_state(judge_out)

        result = optimizer(state, MOCK_CONFIG)

        # Should not raise, should have a non-empty narrative string
        assert isinstance(result["optimizer_narrative"], str)
        assert len(result["optimizer_narrative"]) > 0


# ---------------------------------------------------------------------------
# Private mock helpers
# ---------------------------------------------------------------------------


def _setup_yf_mock(mock_ticker: MagicMock) -> None:
    """Configure yf.Ticker mock to return minimal info dict."""
    mock_info = {
        "sector": "Technology",
        "currentPrice": 150.0,
    }
    mock_ticker.return_value.info = mock_info


def _setup_llm_mock(mock_get_llm: MagicMock) -> None:
    """Configure get_llm mock to return a mock LLM with .invoke()."""
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "Test narrative from LLM."
    mock_llm.invoke.return_value = mock_response
    mock_get_llm.return_value = mock_llm
