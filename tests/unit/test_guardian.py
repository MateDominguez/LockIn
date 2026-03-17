"""
Unit tests for the Guardian agent in lockin.agents.guardian.

TDD RED phase — tests written before implementation.

The Guardian is a Modifier agent that computes risk scores (Altman Z, Beneish M,
VoMC) and outputs a ConfidenceModifier with GRADUATED adjustments.

circuit_breaker=True ONLY for two specific conditions:
  1. M-Score > -1.78 AND (Z distress OR debt/ebitda > 4x OR VoMC > 0.7)
  2. Z-Score < 1.0 AND debt/ebitda > 4x

All other risk levels use graduated margin/variance adjustments only.

Tests mock: yf.Ticker, get_fundamentals, get_llm to avoid network calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lockin.agents.types import ConfidenceModifier, Signal


# ---------------------------------------------------------------------------
# Shared mock builders
# ---------------------------------------------------------------------------

def _mock_ticker(
    market_cap: float = 50_000_000_000,
    total_assets: float = 20_000_000_000,
    working_capital: float = 2_000_000_000,
    retained_earnings: float = 5_000_000_000,
    ebit: float = 3_000_000_000,
    total_liabilities: float = 5_000_000_000,
    revenue: float = 30_000_000_000,
    daily_returns: list[float] | None = None,
) -> MagicMock:
    """Build a mock yf.Ticker object with controlled financial data."""
    ticker = MagicMock()

    # info dict: market cap
    ticker.info = {"marketCap": market_cap}

    # balance_sheet: DataFrame-like with get() interface
    bs = MagicMock()
    bs.get.side_effect = lambda key, default=None: {
        "Net Receivables": 500_000_000,
        "Net PPE": 3_000_000_000,
        "Selling General Administrative": 1_000_000_000,
        "Retained Earnings": retained_earnings,
        "Current Assets": working_capital + 2_000_000_000,
        "Current Liabilities": 2_000_000_000,
        "Total Liabilities Net Minority Interest": total_liabilities,
    }.get(key, default)
    ticker.balance_sheet = bs

    # financials (income statement)
    fin = MagicMock()
    fin.get.side_effect = lambda key, default=None: {
        "Total Revenue": revenue,
        "EBIT": ebit,
        "Total Assets": total_assets,
    }.get(key, default)
    ticker.financials = fin

    # history: returns DataFrame with 'Close' column for daily returns
    if daily_returns is None:
        # Default: stable stock (low volatility)
        n = 252
        prices = [100.0 + 0.1 * i + (0.5 if i % 2 == 0 else -0.5) for i in range(n + 1)]
        daily_returns = [
            (prices[i + 1] - prices[i]) / prices[i] for i in range(n)
        ]

    history_df = MagicMock()
    history_df.__len__ = lambda self: len(daily_returns) + 1
    # The guardian will compute returns from Close prices
    # Simulate a Close series with the desired returns
    prices_for_history = [100.0]
    for r in daily_returns:
        prices_for_history.append(prices_for_history[-1] * (1 + r))

    close_series = MagicMock()
    close_series.pct_change.return_value = MagicMock()
    close_series.pct_change.return_value.dropna.return_value = MagicMock()
    close_series.pct_change.return_value.dropna.return_value.tolist.return_value = daily_returns
    history_df.__getitem__ = lambda self, key: close_series
    ticker.history.return_value = history_df

    return ticker


def _mock_fundamentals(
    total_assets: float = 20_000_000_000,
    total_debt: float = 4_000_000_000,
    ebitda: float = 4_000_000_000,
    working_capital: float = 2_000_000_000,
    retained_earnings: float = 5_000_000_000,
    ebit: float = 3_000_000_000,
    total_liabilities: float = 5_000_000_000,
    revenue: float = 30_000_000_000,
) -> dict:
    """Build mock fundamentals dict."""
    return {
        "ticker": "AAPL",
        "total_assets": total_assets,
        "total_debt": total_debt,
        "ebitda": ebitda,
        "total_revenue": revenue,
        "operating_income": ebit,
        "total_equity": total_assets - total_liabilities,
        "quality_score": 1.0,
        "missing_fields": [],
        "outlier_flags": {},
        "hitl_required": False,
        "hitl_reason": "",
    }


def _make_state(ticker: str = "AAPL") -> dict:
    """Minimal InvestmentState for guardian testing."""
    return {"asset_ticker": ticker, "bull_iteration": 0}


def _make_config() -> MagicMock:
    """Minimal RunnableConfig mock."""
    cfg = MagicMock()
    cfg.get.return_value = {}
    return cfg


# ---------------------------------------------------------------------------
# Helper to build stable low-vol returns (fragility < 0.3)
# ---------------------------------------------------------------------------

def _low_vol_returns(n: int = 252) -> list[float]:
    """Returns with daily std ≈ 0.005 (annualized ≈ 8%), fragility < 0.3."""
    return [0.005 if i % 2 == 0 else -0.005 for i in range(n)]


def _high_vol_returns(n: int = 252) -> list[float]:
    """Returns with daily std = 0.04 (annualized ≈ 63%), fragility > 0.7."""
    return [0.04 if i % 2 == 0 else -0.04 for i in range(n)]


# ===========================================================================
# Tests
# ===========================================================================


class TestGuardianHealthy:
    """Happy path: healthy company, no red flags, no circuit breaker."""

    def test_guardian_healthy_no_circuit_breaker(self):
        """Healthy company: Z safe, M clean, low VoMC -> circuit_breaker=False."""
        from lockin.agents.guardian import guardian

        mock_tick = _mock_ticker(
            market_cap=50_000_000_000,
            total_assets=20_000_000_000,
            working_capital=2_000_000_000,
            retained_earnings=5_000_000_000,
            ebit=3_000_000_000,
            total_liabilities=5_000_000_000,
            revenue=30_000_000_000,
            daily_returns=_low_vol_returns(),
        )
        mock_fund = _mock_fundamentals(
            total_debt=2_000_000_000,
            ebitda=4_000_000_000,  # debt/ebitda = 0.5x
        )
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value = MagicMock(
            content="This is a healthy company with strong fundamentals."
        )

        with patch("lockin.agents.guardian.yf") as mock_yf, \
             patch("lockin.agents.guardian.get_fundamentals", return_value=mock_fund), \
             patch("lockin.agents.guardian.get_llm", return_value=mock_llm_instance):
            mock_yf.Ticker.return_value = mock_tick
            result = guardian(_make_state(), _make_config())

        assert "guardian_modifier" in result
        modifier = result["guardian_modifier"]
        assert isinstance(modifier, ConfidenceModifier)
        assert modifier.circuit_breaker is False
        assert result["guardian_veto"] is False

    def test_guardian_returns_confidence_modifier(self):
        """guardian_modifier field must be a ConfidenceModifier instance."""
        from lockin.agents.guardian import guardian

        mock_tick = _mock_ticker(daily_returns=_low_vol_returns())
        mock_fund = _mock_fundamentals(total_debt=1_000_000_000, ebitda=5_000_000_000)
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value = MagicMock(content="Risk narrative.")

        with patch("lockin.agents.guardian.yf") as mock_yf, \
             patch("lockin.agents.guardian.get_fundamentals", return_value=mock_fund), \
             patch("lockin.agents.guardian.get_llm", return_value=mock_llm_instance):
            mock_yf.Ticker.return_value = mock_tick
            result = guardian(_make_state(), _make_config())

        assert isinstance(result["guardian_modifier"], ConfidenceModifier)


class TestGuardianGraduatedAdjustments:
    """Graduated margin/variance adjustments based on risk level."""

    def test_guardian_graduated_grey_zone(self):
        """Z in grey zone -> margin includes +0.10, variance +0.05, circuit_breaker=False.

        Grey zone requires 1.81 < Z <= 2.99.
        Using inputs that produce Z in grey zone:
          market_cap small, modest retained earnings, positive ebit.
        """
        from lockin.agents.guardian import guardian

        # Tune to get Z in grey zone (~2.26)
        mock_tick = _mock_ticker(
            market_cap=6_000_000_000,    # smaller market cap
            total_assets=5_000_000_000,
            working_capital=300_000_000,
            retained_earnings=200_000_000,
            ebit=200_000_000,
            total_liabilities=3_000_000_000,
            revenue=4_000_000_000,
            daily_returns=_low_vol_returns(),
        )
        mock_fund = _mock_fundamentals(
            total_assets=5_000_000_000,
            total_debt=1_000_000_000,
            ebitda=1_000_000_000,  # debt/ebitda = 1x (not distressed)
            working_capital=300_000_000,
            retained_earnings=200_000_000,
            ebit=200_000_000,
            total_liabilities=3_000_000_000,
            revenue=4_000_000_000,
        )
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value = MagicMock(content="Grey zone analysis.")

        with patch("lockin.agents.guardian.yf") as mock_yf, \
             patch("lockin.agents.guardian.get_fundamentals", return_value=mock_fund), \
             patch("lockin.agents.guardian.get_llm", return_value=mock_llm_instance):
            mock_yf.Ticker.return_value = mock_tick
            result = guardian(_make_state(), _make_config())

        modifier = result["guardian_modifier"]
        assert modifier.circuit_breaker is False, (
            "Grey zone alone must NOT trigger circuit_breaker"
        )
        # Margin should include grey zone penalty (+0.10 base)
        assert modifier.margin_adjustment >= 0.10, (
            f"Grey zone should add >= 0.10 margin penalty, got {modifier.margin_adjustment}"
        )
        # Variance should include grey zone addition (+0.05)
        assert modifier.variance_adjustment >= 0.05, (
            f"Grey zone should add >= 0.05 variance, got {modifier.variance_adjustment}"
        )

    def test_guardian_graduated_distress(self):
        """Z in distress zone -> margin includes +0.25, variance +0.10, circuit_breaker=False.

        Distress without M-Score issue and without debt/ebitda > 4x:
        Z < 1.81 but M clean, reasonable debt.
        """
        from lockin.agents.guardian import guardian

        # Tune for distress Z < 1.81
        mock_tick = _mock_ticker(
            market_cap=200_000_000,
            total_assets=5_000_000_000,
            working_capital=-500_000_000,
            retained_earnings=-2_000_000_000,
            ebit=-100_000_000,
            total_liabilities=8_000_000_000,
            revenue=1_000_000_000,
            daily_returns=_low_vol_returns(),
        )
        mock_fund = _mock_fundamentals(
            total_assets=5_000_000_000,
            total_debt=3_000_000_000,
            ebitda=2_000_000_000,  # debt/ebitda = 1.5x — NOT > 4x
            working_capital=-500_000_000,
            retained_earnings=-2_000_000_000,
            ebit=-100_000_000,
            total_liabilities=8_000_000_000,
            revenue=1_000_000_000,
        )
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value = MagicMock(content="Distress analysis.")

        with patch("lockin.agents.guardian.yf") as mock_yf, \
             patch("lockin.agents.guardian.get_fundamentals", return_value=mock_fund), \
             patch("lockin.agents.guardian.get_llm", return_value=mock_llm_instance):
            mock_yf.Ticker.return_value = mock_tick
            result = guardian(_make_state(), _make_config())

        modifier = result["guardian_modifier"]
        # Distress alone (no M-Score, no debt/ebitda > 4x): graduated only
        assert modifier.circuit_breaker is False, (
            "Z distress alone (no M issue, no debt/ebitda > 4x) must NOT trigger circuit_breaker"
        )
        assert modifier.margin_adjustment >= 0.25, (
            f"Distress should add >= 0.25 margin penalty, got {modifier.margin_adjustment}"
        )
        assert modifier.variance_adjustment >= 0.10, (
            f"Distress should add >= 0.10 variance, got {modifier.variance_adjustment}"
        )


class TestGuardianCircuitBreaker:
    """circuit_breaker=True triggered ONLY for two specific conditions."""

    def test_guardian_circuit_breaker_mscore_red_flag_z_distress(self):
        """M > -1.78 AND Z distress -> circuit_breaker=True.

        Per plan: circuit_breaker=True if M-Score > -1.78 AND
        (Z distress OR debt_ebitda > 4x OR VoMC > 0.7)
        """
        from lockin.agents.guardian import guardian

        # Distress Z (same params as above)
        mock_tick = _mock_ticker(
            market_cap=200_000_000,
            total_assets=5_000_000_000,
            working_capital=-500_000_000,
            retained_earnings=-2_000_000_000,
            ebit=-100_000_000,
            total_liabilities=8_000_000_000,
            revenue=1_000_000_000,
            daily_returns=_low_vol_returns(),
        )
        mock_fund = _mock_fundamentals(
            total_assets=5_000_000_000,
            total_debt=3_000_000_000,
            ebitda=2_000_000_000,
            working_capital=-500_000_000,
            retained_earnings=-2_000_000_000,
            ebit=-100_000_000,
            total_liabilities=8_000_000_000,
            revenue=1_000_000_000,
        )
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value = MagicMock(content="High risk analysis.")

        # Patch _compute_beneish to return manipulator M-Score
        with patch("lockin.agents.guardian.yf") as mock_yf, \
             patch("lockin.agents.guardian.get_fundamentals", return_value=mock_fund), \
             patch("lockin.agents.guardian.get_llm", return_value=mock_llm_instance), \
             patch("lockin.agents.guardian._compute_beneish",
                   return_value={"m_score": -1.50, "likely_manipulator": True}):
            mock_yf.Ticker.return_value = mock_tick
            result = guardian(_make_state(), _make_config())

        modifier = result["guardian_modifier"]
        assert modifier.circuit_breaker is True, (
            "M > -1.78 AND Z distress must trigger circuit_breaker"
        )
        assert result["guardian_veto"] is True

    def test_guardian_circuit_breaker_zscore_leverage(self):
        """Z < 1.0 AND debt/ebitda > 4x -> circuit_breaker=True."""
        from lockin.agents.guardian import guardian

        mock_tick = _mock_ticker(
            market_cap=200_000_000,
            total_assets=5_000_000_000,
            working_capital=-500_000_000,
            retained_earnings=-2_000_000_000,
            ebit=-100_000_000,
            total_liabilities=8_000_000_000,
            revenue=1_000_000_000,
            daily_returns=_low_vol_returns(),
        )
        mock_fund = _mock_fundamentals(
            total_assets=5_000_000_000,
            total_debt=12_000_000_000,  # debt/ebitda = 12/2 = 6x > 4x
            ebitda=2_000_000_000,
            working_capital=-500_000_000,
            retained_earnings=-2_000_000_000,
            ebit=-100_000_000,
            total_liabilities=8_000_000_000,
            revenue=1_000_000_000,
        )
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value = MagicMock(content="High leverage analysis.")

        with patch("lockin.agents.guardian.yf") as mock_yf, \
             patch("lockin.agents.guardian.get_fundamentals", return_value=mock_fund), \
             patch("lockin.agents.guardian.get_llm", return_value=mock_llm_instance):
            mock_yf.Ticker.return_value = mock_tick
            result = guardian(_make_state(), _make_config())

        modifier = result["guardian_modifier"]
        assert modifier.circuit_breaker is True, (
            "Z < 1.0 AND debt/ebitda > 4x must trigger circuit_breaker"
        )
        assert result["guardian_veto"] is True

    def test_guardian_no_circuit_breaker_mscore_alone(self):
        """M > -1.78 but NO other red flag -> circuit_breaker=False (graduated only).

        If M is flagged but Z is safe and debt/ebitda <= 4x and VoMC <= 0.7,
        circuit_breaker must remain False. Only graduated margin penalty applies.
        """
        from lockin.agents.guardian import guardian

        # Healthy Z (safe zone), low VoMC, M manipulator but no other flags
        mock_tick = _mock_ticker(
            market_cap=50_000_000_000,
            total_assets=20_000_000_000,
            working_capital=2_000_000_000,
            retained_earnings=5_000_000_000,
            ebit=3_000_000_000,
            total_liabilities=5_000_000_000,
            revenue=30_000_000_000,
            daily_returns=_low_vol_returns(),
        )
        mock_fund = _mock_fundamentals(
            total_debt=2_000_000_000,
            ebitda=4_000_000_000,  # debt/ebitda = 0.5x — NOT > 4x
        )
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value = MagicMock(
            content="M-Score concern, but overall financials healthy."
        )

        with patch("lockin.agents.guardian.yf") as mock_yf, \
             patch("lockin.agents.guardian.get_fundamentals", return_value=mock_fund), \
             patch("lockin.agents.guardian.get_llm", return_value=mock_llm_instance), \
             patch("lockin.agents.guardian._compute_beneish",
                   return_value={"m_score": -1.50, "likely_manipulator": True}):
            mock_yf.Ticker.return_value = mock_tick
            result = guardian(_make_state(), _make_config())

        modifier = result["guardian_modifier"]
        assert modifier.circuit_breaker is False, (
            "M > -1.78 alone (Z safe, debt/ebitda <= 4x, VoMC <= 0.7) must NOT trigger "
            "circuit_breaker — only graduated penalty"
        )
        # But margin should include M-Score penalty (+0.20 for manipulator)
        assert modifier.margin_adjustment >= 0.20, (
            f"M > -1.78 should add >= 0.20 margin, got {modifier.margin_adjustment}"
        )


class TestGuardianSignals:
    """All signals must have has_base_rate=True with academic sources."""

    def test_guardian_signals_have_base_rates(self):
        """All guardian signals must have has_base_rate=True and non-empty base_rate_source."""
        from lockin.agents.guardian import guardian

        mock_tick = _mock_ticker(daily_returns=_low_vol_returns())
        mock_fund = _mock_fundamentals(total_debt=1_000_000_000, ebitda=5_000_000_000)
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value = MagicMock(content="Signals analysis.")

        with patch("lockin.agents.guardian.yf") as mock_yf, \
             patch("lockin.agents.guardian.get_fundamentals", return_value=mock_fund), \
             patch("lockin.agents.guardian.get_llm", return_value=mock_llm_instance):
            mock_yf.Ticker.return_value = mock_tick
            result = guardian(_make_state(), _make_config())

        modifier = result["guardian_modifier"]
        assert len(modifier.signals) >= 3, (
            f"Expected at least 3 signals, got {len(modifier.signals)}"
        )
        for sig in modifier.signals:
            assert sig.has_base_rate is True, (
                f"Signal '{sig.name}' must have has_base_rate=True"
            )
            assert sig.base_rate_source and len(sig.base_rate_source) > 0, (
                f"Signal '{sig.name}' must have a non-empty base_rate_source"
            )

    def test_guardian_signal_sources(self):
        """Specific signals must cite their academic sources."""
        from lockin.agents.guardian import guardian

        mock_tick = _mock_ticker(daily_returns=_low_vol_returns())
        mock_fund = _mock_fundamentals(total_debt=1_000_000_000, ebitda=5_000_000_000)
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value = MagicMock(content="Sources check.")

        with patch("lockin.agents.guardian.yf") as mock_yf, \
             patch("lockin.agents.guardian.get_fundamentals", return_value=mock_fund), \
             patch("lockin.agents.guardian.get_llm", return_value=mock_llm_instance):
            mock_yf.Ticker.return_value = mock_tick
            result = guardian(_make_state(), _make_config())

        modifier = result["guardian_modifier"]
        signal_map = {s.name: s for s in modifier.signals}

        # z_score signal: source = "backtest"
        assert "z_score" in signal_map, "Expected z_score signal"
        assert signal_map["z_score"].base_rate_source == "backtest"

        # m_score signal: source = "Beneish (1999)"
        assert "m_score" in signal_map, "Expected m_score signal"
        assert signal_map["m_score"].base_rate_source == "Beneish (1999)"

        # piotroski_score: source = "Piotroski (2000)"
        assert "piotroski_score" in signal_map, "Expected piotroski_score signal"
        assert signal_map["piotroski_score"].base_rate_source == "Piotroski (2000)"

        # vomc_fragility: source = "backtest"
        assert "vomc_fragility" in signal_map, "Expected vomc_fragility signal"
        assert signal_map["vomc_fragility"].base_rate_source == "backtest"


class TestGuardianReturnSchema:
    """Verify the complete return dict schema."""

    def test_guardian_return_keys(self):
        """guardian() must return all required keys."""
        from lockin.agents.guardian import guardian

        mock_tick = _mock_ticker(daily_returns=_low_vol_returns())
        mock_fund = _mock_fundamentals()
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value = MagicMock(content="Return schema check.")

        with patch("lockin.agents.guardian.yf") as mock_yf, \
             patch("lockin.agents.guardian.get_fundamentals", return_value=mock_fund), \
             patch("lockin.agents.guardian.get_llm", return_value=mock_llm_instance):
            mock_yf.Ticker.return_value = mock_tick
            result = guardian(_make_state(), _make_config())

        required_keys = {
            "guardian_modifier",
            "guardian_risk_report",
            "guardian_veto",
            "guardian_veto_reason",
        }
        missing = required_keys - set(result.keys())
        assert not missing, f"Missing required return keys: {missing}"

    def test_guardian_risk_report_is_dict(self):
        """guardian_risk_report must be a dict."""
        from lockin.agents.guardian import guardian

        mock_tick = _mock_ticker(daily_returns=_low_vol_returns())
        mock_fund = _mock_fundamentals()
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value = MagicMock(content="Risk report check.")

        with patch("lockin.agents.guardian.yf") as mock_yf, \
             patch("lockin.agents.guardian.get_fundamentals", return_value=mock_fund), \
             patch("lockin.agents.guardian.get_llm", return_value=mock_llm_instance):
            mock_yf.Ticker.return_value = mock_tick
            result = guardian(_make_state(), _make_config())

        assert isinstance(result["guardian_risk_report"], dict)
        assert "z_score" in result["guardian_risk_report"]
        assert "m_score" in result["guardian_risk_report"]
        assert "vomc_fragility" in result["guardian_risk_report"]

    def test_guardian_veto_is_bool(self):
        """guardian_veto must be a bool."""
        from lockin.agents.guardian import guardian

        mock_tick = _mock_ticker(daily_returns=_low_vol_returns())
        mock_fund = _mock_fundamentals()
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value = MagicMock(content="Veto type check.")

        with patch("lockin.agents.guardian.yf") as mock_yf, \
             patch("lockin.agents.guardian.get_fundamentals", return_value=mock_fund), \
             patch("lockin.agents.guardian.get_llm", return_value=mock_llm_instance):
            mock_yf.Ticker.return_value = mock_tick
            result = guardian(_make_state(), _make_config())

        assert isinstance(result["guardian_veto"], bool)
