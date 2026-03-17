"""
Unit tests for the Bear adversarial agent (03-05).

All 9 tests mock get_fundamentals and get_llm so no live network calls are made.

Test matrix:
  1. test_bear_independent_of_bull        — Bear never reads Bull output
  2. test_bear_increments_iteration       — bull_iteration += 1
  3. test_bear_red_flags_detected         — FCF < 0 triggers FCF flag
  4. test_bear_returns_value_distribution — returned type is ValueDistribution
  5. test_bear_distribution_pessimistic   — expected_value < known bull estimate
  6. test_bear_distribution_wider_sigma   — std_dev / expected_value > 0.20
  7. test_bear_distribution_log_normal    — p10 < p50 < p90
  8. test_bear_data_coverage              — available + missing both non-empty
  9. test_bear_state_compatible           — returned keys are InvestmentState fields
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lockin.agents.types import ValueDistribution
from lockin.graph.state import InvestmentState

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

# Fundamentals with deliberate red flags: negative FCF, high debt/equity
_BEARISH_FUNDAMENTALS: dict = {
    "ticker": "TESTCO",
    "total_revenue": 1_000_000_000.0,          # $1 B
    "net_income": 50_000_000.0,                 # $50 M
    "gross_profit": 300_000_000.0,              # $300 M
    "operating_income": 30_000_000.0,           # thin margin ~3 %
    "ebitda": 60_000_000.0,
    "diluted_eps": 0.50,
    "free_cash_flow": -20_000_000.0,            # NEGATIVE — cash burn flag
    "total_assets": 800_000_000.0,
    "total_debt": 700_000_000.0,                # debt/equity > 2 — leverage flag
    "cash_and_equivalents": 30_000_000.0,
    "total_equity": 200_000_000.0,
    "fiscal_year_end": None,
    "source": "yfinance",
    "fetched_at": None,
    "as_of_date": "live",
    "data_freshness": "FRESH",
    "quality_score": 0.85,
    "missing_fields": [],
    "outlier_flags": {},
    "hitl_required": False,
    "hitl_reason": "",
}

# LLM response that parse_llm_response can decode
_LLM_JSON_RESPONSE = (
    '{"challenges": ["Revenue growth decelerated sharply", '
    '"Debt levels unsustainable"], '
    '"thesis": "Company is over-leveraged with deteriorating margins.", '
    '"red_flags": ["high_debt_equity", "free_cash_flow_negative"], '
    '"conviction": 0.72}'
)

# Typical bull estimate used in pessimism test (plan: bear < bull)
_TYPICAL_BULL_ESTIMATE = 200_000_000.0  # e.g. $200 M bull EPV


# ---------------------------------------------------------------------------
# Helper: build a minimal InvestmentState for a ticker
# ---------------------------------------------------------------------------


def _make_state(**overrides) -> InvestmentState:
    state = InvestmentState(
        request_id="test-bear-001",
        asset_ticker="TESTCO",
        bull_iteration=0,
    )
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# Mock factories
# ---------------------------------------------------------------------------


def _mock_get_fundamentals(_ticker: str, store: bool = False):
    return _BEARISH_FUNDAMENTALS.copy()


def _make_mock_llm(response_text: str = _LLM_JSON_RESPONSE):
    """Return a mock LLM that returns response_text from .invoke()."""
    mock_llm = MagicMock()
    mock_message = MagicMock()
    mock_message.content = response_text
    mock_llm.invoke.return_value = mock_message
    return mock_llm


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBearAgent:
    """All 9 required unit tests for the Bear agent."""

    @patch("lockin.agents.bear.get_llm", return_value=_make_mock_llm())
    @patch("lockin.agents.bear.get_fundamentals", side_effect=_mock_get_fundamentals)
    def test_bear_independent_of_bull(self, mock_gf, mock_llm):
        """Bear must NOT access bull_thesis or bull_valuation_distribution.

        We inject bull data into state and verify that:
          - get_fundamentals was called (Bear fetches own data)
          - the call args never include bull state keys
        The structural guarantee is enforced by inspecting bear.py source in CI;
        here we verify the runtime path never crashes when bull data is absent.
        """
        from lockin.agents.bear import bear

        # Inject realistic bull data into state
        state = _make_state(
            bull_thesis="Bull is very optimistic about growth prospects",
            bull_valuation_distribution=ValueDistribution(
                expected_value=_TYPICAL_BULL_ESTIMATE,
                std_dev=40_000_000.0,
                p10=120_000_000.0,
                p50=200_000_000.0,
                p90=300_000_000.0,
                confidence=0.80,
            ),
            bull_confidence=0.80,
        )
        config = MagicMock()

        result = bear(state, config)

        # Bear must have fetched its own data (not relied on bull's output)
        mock_gf.assert_called_once_with("TESTCO", store=False)

        # Bear result must be a valid dict with bear-owned keys
        assert "bear_valuation_distribution" in result
        assert "bear_thesis" in result
        assert isinstance(result["bear_valuation_distribution"], ValueDistribution)

    @patch("lockin.agents.bear.get_llm", return_value=_make_mock_llm())
    @patch("lockin.agents.bear.get_fundamentals", side_effect=_mock_get_fundamentals)
    def test_bear_increments_iteration(self, mock_gf, mock_llm):
        """bull_iteration=0 in state -> returned bull_iteration=1."""
        from lockin.agents.bear import bear

        state = _make_state(bull_iteration=0)
        config = MagicMock()

        result = bear(state, config)

        assert result["bull_iteration"] == 1, (
            f"Expected bull_iteration=1, got {result['bull_iteration']}"
        )

    @patch("lockin.agents.bear.get_llm", return_value=_make_mock_llm())
    @patch("lockin.agents.bear.get_fundamentals", side_effect=_mock_get_fundamentals)
    def test_bear_increments_iteration_from_nonzero(self, mock_gf, mock_llm):
        """bull_iteration=1 in state -> returned bull_iteration=2."""
        from lockin.agents.bear import bear

        state = _make_state(bull_iteration=1)
        config = MagicMock()

        result = bear(state, config)

        assert result["bull_iteration"] == 2

    @patch("lockin.agents.bear.get_llm", return_value=_make_mock_llm())
    @patch("lockin.agents.bear.get_fundamentals", side_effect=_mock_get_fundamentals)
    def test_bear_red_flags_detected(self, mock_gf, mock_llm):
        """Negative FCF in data -> 'free_cash_flow' appears in bear_red_flags."""
        from lockin.agents.bear import bear

        state = _make_state()
        config = MagicMock()

        result = bear(state, config)

        red_flags: list[str] = result["bear_red_flags"]
        assert isinstance(red_flags, list), "bear_red_flags must be a list"
        # At least one flag must relate to free_cash_flow (our injected red flag)
        fcf_flags = [f for f in red_flags if "free_cash_flow" in f.lower()]
        assert fcf_flags, (
            f"Expected 'free_cash_flow' flag in bear_red_flags, got: {red_flags}"
        )

    @patch("lockin.agents.bear.get_llm", return_value=_make_mock_llm())
    @patch("lockin.agents.bear.get_fundamentals", side_effect=_mock_get_fundamentals)
    def test_bear_returns_value_distribution(self, mock_gf, mock_llm):
        """bear_valuation_distribution must be a ValueDistribution with all fields."""
        from lockin.agents.bear import bear

        state = _make_state()
        config = MagicMock()

        result = bear(state, config)

        dist = result["bear_valuation_distribution"]
        assert isinstance(dist, ValueDistribution), (
            f"Expected ValueDistribution, got {type(dist)}"
        )

        # All required fields must be present and typed correctly
        assert isinstance(dist.expected_value, (int, float))
        assert isinstance(dist.std_dev, (int, float))
        assert isinstance(dist.p10, (int, float))
        assert isinstance(dist.p50, (int, float))
        assert isinstance(dist.p90, (int, float))
        assert isinstance(dist.confidence, float)
        assert isinstance(dist.methods_used, list)
        assert len(dist.methods_used) > 0, "methods_used must be non-empty"
        assert isinstance(dist.data_coverage.available, list)

    @patch("lockin.agents.bear.get_llm", return_value=_make_mock_llm())
    @patch("lockin.agents.bear.get_fundamentals", side_effect=_mock_get_fundamentals)
    def test_bear_distribution_pessimistic(self, mock_gf, mock_llm):
        """Bear expected_value must be below a typical bull estimate.

        We use _TYPICAL_BULL_ESTIMATE=$200M as the bull comparison point.
        Bear should produce a pessimistic EPV significantly below that.
        """
        from lockin.agents.bear import bear

        state = _make_state()
        config = MagicMock()

        result = bear(state, config)

        dist: ValueDistribution = result["bear_valuation_distribution"]
        assert dist.expected_value < _TYPICAL_BULL_ESTIMATE, (
            f"Bear EPV {dist.expected_value:,.0f} should be < bull estimate "
            f"{_TYPICAL_BULL_ESTIMATE:,.0f}"
        )

    @patch("lockin.agents.bear.get_llm", return_value=_make_mock_llm())
    @patch("lockin.agents.bear.get_fundamentals", side_effect=_mock_get_fundamentals)
    def test_bear_distribution_wider_sigma(self, mock_gf, mock_llm):
        """Bear std_dev / expected_value must be > 0.20 (wider than Bull's ~0.20)."""
        from lockin.agents.bear import bear

        state = _make_state()
        config = MagicMock()

        result = bear(state, config)

        dist: ValueDistribution = result["bear_valuation_distribution"]
        assert dist.expected_value > 0, "expected_value must be positive"

        relative_sigma = dist.std_dev / dist.expected_value
        assert relative_sigma > 0.20, (
            f"Bear relative sigma {relative_sigma:.3f} must be > 0.20 (Bear sigma=0.25)"
        )

    @patch("lockin.agents.bear.get_llm", return_value=_make_mock_llm())
    @patch("lockin.agents.bear.get_fundamentals", side_effect=_mock_get_fundamentals)
    def test_bear_distribution_log_normal(self, mock_gf, mock_llm):
        """Log-normal distribution must satisfy p10 < p50 < p90."""
        from lockin.agents.bear import bear

        state = _make_state()
        config = MagicMock()

        result = bear(state, config)

        dist: ValueDistribution = result["bear_valuation_distribution"]
        assert dist.p10 < dist.p50 < dist.p90, (
            f"Log-normal order violated: p10={dist.p10:.2f}, "
            f"p50={dist.p50:.2f}, p90={dist.p90:.2f}"
        )

    @patch("lockin.agents.bear.get_llm", return_value=_make_mock_llm())
    @patch("lockin.agents.bear.get_fundamentals", side_effect=_mock_get_fundamentals)
    def test_bear_data_coverage(self, mock_gf, mock_llm):
        """data_coverage.available and data_coverage.missing must both be non-empty."""
        from lockin.agents.bear import bear

        state = _make_state()
        config = MagicMock()

        result = bear(state, config)

        dist: ValueDistribution = result["bear_valuation_distribution"]
        coverage = dist.data_coverage

        assert len(coverage.available) > 0, (
            "data_coverage.available must be non-empty"
        )
        assert len(coverage.missing) > 0, (
            "data_coverage.missing must be non-empty (Bear always has info gaps)"
        )

    @patch("lockin.agents.bear.get_llm", return_value=_make_mock_llm())
    @patch("lockin.agents.bear.get_fundamentals", side_effect=_mock_get_fundamentals)
    def test_bear_state_compatible(self, mock_gf, mock_llm):
        """Returned dict keys must all be valid InvestmentState fields."""
        from lockin.agents.bear import bear

        state = _make_state()
        config = MagicMock()

        result = bear(state, config)

        valid_keys = set(InvestmentState.__annotations__.keys())
        invalid_keys = set(result.keys()) - valid_keys

        assert not invalid_keys, (
            f"Bear returned keys not in InvestmentState: {invalid_keys}"
        )

        # Spot-check the 6 expected keys
        expected_keys = {
            "bear_challenges",
            "bear_valuation_distribution",
            "bear_thesis",
            "bear_red_flags",
            "bear_conviction",
            "bull_iteration",
        }
        for key in expected_keys:
            assert key in result, f"Expected key '{key}' missing from Bear output"
