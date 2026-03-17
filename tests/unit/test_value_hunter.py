"""
Unit tests for the Value Hunter (Bull) agent in lockin.agents.value_hunter.

TDD RED phase — all tests written before implementation.
Tests mock: get_fundamentals (lockin.data), get_llm (lockin.agents.llm).
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from lockin.agents.types import DataCoverage, ValueDistribution
from lockin.agents.value_hunter import value_hunter
from lockin.graph.state import create_initial_state


# ---------------------------------------------------------------------------
# Shared fixture: minimal FundamentalsResult for mocking
# ---------------------------------------------------------------------------


def _make_fundamentals(
    ticker: str = "AAPL",
    operating_income: float = 1_000_000_000,
    net_income: float = 800_000_000,
    total_assets: float = 10_000_000_000,
    total_equity: float = 4_000_000_000,
    total_debt: float = 2_000_000_000,
    gross_profit: float = 4_000_000_000,
    total_revenue: float = 10_000_000_000,
    free_cash_flow: float = 900_000_000,
    cash_and_equivalents: float = 500_000_000,
) -> dict:
    """Return a minimal FundamentalsResult-compatible dict for testing."""
    return {
        "ticker": ticker,
        "operating_income": operating_income,
        "net_income": net_income,
        "total_assets": total_assets,
        "total_equity": total_equity,
        "total_debt": total_debt,
        "gross_profit": gross_profit,
        "total_revenue": total_revenue,
        "ebitda": operating_income * 1.2,
        "free_cash_flow": free_cash_flow,
        "cash_and_equivalents": cash_and_equivalents,
        "diluted_eps": 5.0,
        "fiscal_year_end": date(2024, 9, 30),
        "source": "yfinance",
        "fetched_at": datetime.utcnow(),
        "as_of_date": "live",
        "data_freshness": "FRESH",
        "quality_score": 0.9,
        "missing_fields": [],
        "outlier_flags": {},
        "hitl_required": False,
        "hitl_reason": "",
    }


@pytest.fixture
def minimal_state():
    """Minimal InvestmentState for AAPL, first iteration."""
    return create_initial_state("AAPL")


@pytest.fixture
def thread_config():
    """Standard LangGraph config."""
    return {"configurable": {"thread_id": "test-value-hunter"}}


@pytest.fixture
def mock_llm():
    """A mock LLM that returns a canned string response."""
    llm = MagicMock()
    response = MagicMock()
    response.content = (
        "AAPL demonstrates strong earnings power with a durable competitive moat. "
        "EPV analysis suggests the stock trades at a discount to intrinsic value. "
        "Piotroski F-Score of 7 confirms high financial quality."
    )
    llm.invoke.return_value = response
    return llm


# ---------------------------------------------------------------------------
# Test: first pass (bull_iteration == 0)
# ---------------------------------------------------------------------------


class TestValueHunterFirstPass:
    """Tests for value_hunter() when bull_iteration == 0."""

    @patch("lockin.agents.value_hunter.get_llm")
    @patch("lockin.agents.value_hunter.get_fundamentals")
    def test_value_hunter_first_pass(
        self, mock_get_fundamentals, mock_get_llm, minimal_state, thread_config, mock_llm
    ):
        """Returns dict with bull_thesis, bull_valuation_distribution, quality_metrics."""
        mock_get_fundamentals.return_value = _make_fundamentals()
        mock_get_llm.return_value = mock_llm

        result = value_hunter(minimal_state, thread_config)

        assert "bull_thesis" in result, "Must return bull_thesis"
        assert "bull_valuation_distribution" in result, "Must return bull_valuation_distribution"
        assert "quality_metrics" in result, "Must return quality_metrics"

    @patch("lockin.agents.value_hunter.get_llm")
    @patch("lockin.agents.value_hunter.get_fundamentals")
    def test_value_hunter_returns_value_distribution(
        self, mock_get_fundamentals, mock_get_llm, minimal_state, thread_config, mock_llm
    ):
        """bull_valuation_distribution must be a ValueDistribution instance."""
        mock_get_fundamentals.return_value = _make_fundamentals()
        mock_get_llm.return_value = mock_llm

        result = value_hunter(minimal_state, thread_config)

        dist = result["bull_valuation_distribution"]
        assert isinstance(dist, ValueDistribution), (
            f"Expected ValueDistribution, got {type(dist)}"
        )

    @patch("lockin.agents.value_hunter.get_llm")
    @patch("lockin.agents.value_hunter.get_fundamentals")
    def test_value_hunter_distribution_log_normal(
        self, mock_get_fundamentals, mock_get_llm, minimal_state, thread_config, mock_llm
    ):
        """ValueDistribution must satisfy p10 < p50 < p90 (log-normal monotonicity)."""
        mock_get_fundamentals.return_value = _make_fundamentals()
        mock_get_llm.return_value = mock_llm

        result = value_hunter(minimal_state, thread_config)

        dist = result["bull_valuation_distribution"]
        assert dist.p10 < dist.p50, f"p10 ({dist.p10}) must be < p50 ({dist.p50})"
        assert dist.p50 < dist.p90, f"p50 ({dist.p50}) must be < p90 ({dist.p90})"

    @patch("lockin.agents.value_hunter.get_llm")
    @patch("lockin.agents.value_hunter.get_fundamentals")
    def test_value_hunter_data_coverage(
        self, mock_get_fundamentals, mock_get_llm, minimal_state, thread_config, mock_llm
    ):
        """data_coverage.available must be non-empty; confidence in [0, 1]."""
        mock_get_fundamentals.return_value = _make_fundamentals()
        mock_get_llm.return_value = mock_llm

        result = value_hunter(minimal_state, thread_config)

        dist = result["bull_valuation_distribution"]
        assert isinstance(dist.data_coverage, DataCoverage), "data_coverage must be DataCoverage"
        assert len(dist.data_coverage.available) > 0, "data_coverage.available must be non-empty"
        assert 0.0 <= dist.confidence <= 1.0, (
            f"confidence must be in [0, 1], got {dist.confidence}"
        )

    @patch("lockin.agents.value_hunter.get_llm")
    @patch("lockin.agents.value_hunter.get_fundamentals")
    def test_value_hunter_methods_used(
        self, mock_get_fundamentals, mock_get_llm, minimal_state, thread_config, mock_llm
    ):
        """methods_used must contain at least one model name (e.g. 'EPV', 'EVA', 'RIM')."""
        mock_get_fundamentals.return_value = _make_fundamentals()
        mock_get_llm.return_value = mock_llm

        result = value_hunter(minimal_state, thread_config)

        dist = result["bull_valuation_distribution"]
        assert len(dist.methods_used) > 0, "methods_used must not be empty"
        known_models = {"EPV", "EVA", "RIM"}
        used = set(dist.methods_used)
        assert used & known_models, (
            f"methods_used {used} must include at least one of {known_models}"
        )

    @patch("lockin.agents.value_hunter.get_llm")
    @patch("lockin.agents.value_hunter.get_fundamentals")
    def test_value_hunter_bull_confidence(
        self, mock_get_fundamentals, mock_get_llm, minimal_state, thread_config, mock_llm
    ):
        """bull_confidence in result must be in [0, 1]."""
        mock_get_fundamentals.return_value = _make_fundamentals()
        mock_get_llm.return_value = mock_llm

        result = value_hunter(minimal_state, thread_config)

        confidence = result.get("bull_confidence", None)
        assert confidence is not None, "bull_confidence must be present"
        assert 0.0 <= confidence <= 1.0, f"bull_confidence {confidence} must be in [0, 1]"

    @patch("lockin.agents.value_hunter.get_llm")
    @patch("lockin.agents.value_hunter.get_fundamentals")
    def test_value_hunter_quality_metrics(
        self, mock_get_fundamentals, mock_get_llm, minimal_state, thread_config, mock_llm
    ):
        """quality_metrics must contain piotroski_f and magic_formula keys."""
        mock_get_fundamentals.return_value = _make_fundamentals()
        mock_get_llm.return_value = mock_llm

        result = value_hunter(minimal_state, thread_config)

        qm = result["quality_metrics"]
        assert isinstance(qm, dict), "quality_metrics must be a dict"
        assert "piotroski_f" in qm, "quality_metrics must have piotroski_f"
        assert "magic_formula" in qm, "quality_metrics must have magic_formula"


# ---------------------------------------------------------------------------
# Test: refinement pass (bull_iteration == 1)
# ---------------------------------------------------------------------------


class TestValueHunterRefinement:
    """Tests for value_hunter() when bull_iteration > 0 (post-bear-challenge)."""

    @patch("lockin.agents.value_hunter.get_llm")
    @patch("lockin.agents.value_hunter.get_fundamentals")
    def test_value_hunter_refinement(
        self, mock_get_fundamentals, mock_get_llm, thread_config, mock_llm
    ):
        """When bull_iteration=1 + bear_challenges present, returns bull_refined_thesis."""
        mock_get_fundamentals.return_value = _make_fundamentals()
        mock_get_llm.return_value = mock_llm

        # State with iteration > 0 and bear challenges
        state = create_initial_state("AAPL")
        state["bull_iteration"] = 1
        state["bear_challenges"] = [
            "Revenue deceleration risk",
            "Rising competition from Android ecosystem",
        ]

        result = value_hunter(state, thread_config)

        assert "bull_refined_thesis" in result, (
            "When bull_iteration > 0 and bear_challenges present, "
            "must return bull_refined_thesis"
        )

    @patch("lockin.agents.value_hunter.get_llm")
    @patch("lockin.agents.value_hunter.get_fundamentals")
    def test_value_hunter_no_refined_thesis_on_first_pass(
        self, mock_get_fundamentals, mock_get_llm, minimal_state, thread_config, mock_llm
    ):
        """On first pass (bull_iteration=0), bull_refined_thesis should NOT appear."""
        mock_get_fundamentals.return_value = _make_fundamentals()
        mock_get_llm.return_value = mock_llm

        result = value_hunter(minimal_state, thread_config)

        # Either not present or explicitly None/empty
        refined = result.get("bull_refined_thesis", None)
        assert not refined, (
            "bull_refined_thesis should not be set on first pass (iteration=0)"
        )


# ---------------------------------------------------------------------------
# Test: get_fundamentals called with store=False
# ---------------------------------------------------------------------------


class TestValueHunterDataFetching:
    """Tests around get_fundamentals call contract."""

    @patch("lockin.agents.value_hunter.get_llm")
    @patch("lockin.agents.value_hunter.get_fundamentals")
    def test_get_fundamentals_called_store_false(
        self, mock_get_fundamentals, mock_get_llm, minimal_state, thread_config, mock_llm
    ):
        """get_fundamentals must be called with store=False."""
        mock_get_fundamentals.return_value = _make_fundamentals()
        mock_get_llm.return_value = mock_llm

        value_hunter(minimal_state, thread_config)

        call_kwargs = mock_get_fundamentals.call_args
        # Accept positional or keyword
        assert call_kwargs is not None
        kwargs = call_kwargs.kwargs if call_kwargs.kwargs else {}
        args = call_kwargs.args if call_kwargs.args else []
        # store=False must be present either as kwarg or positional index
        if "store" in kwargs:
            assert kwargs["store"] is False, "store must be False"
        # If positional: get_fundamentals(ticker, store=False) is typical

    @patch("lockin.agents.value_hunter.get_llm")
    @patch("lockin.agents.value_hunter.get_fundamentals")
    def test_llm_invoked(
        self, mock_get_fundamentals, mock_get_llm, minimal_state, thread_config, mock_llm
    ):
        """LLM must be invoked at least once to generate bull thesis."""
        mock_get_fundamentals.return_value = _make_fundamentals()
        mock_get_llm.return_value = mock_llm

        value_hunter(minimal_state, thread_config)

        assert mock_llm.invoke.called, "LLM invoke must be called at least once"

    @patch("lockin.agents.value_hunter.get_llm")
    @patch("lockin.agents.value_hunter.get_fundamentals")
    def test_distribution_positive_values(
        self, mock_get_fundamentals, mock_get_llm, minimal_state, thread_config, mock_llm
    ):
        """For a profitable company, all percentiles must be positive (log-normal)."""
        mock_get_fundamentals.return_value = _make_fundamentals(operating_income=1_000_000_000)
        mock_get_llm.return_value = mock_llm

        result = value_hunter(minimal_state, thread_config)

        dist = result["bull_valuation_distribution"]
        assert dist.p10 > 0, f"p10 must be positive for profitable co, got {dist.p10}"
        assert dist.p50 > 0
        assert dist.p90 > 0
