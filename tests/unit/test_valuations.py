"""
Unit tests for valuation formula functions in lockin.agents.valuations.

TDD RED phase — all tests written before implementation.
Tests cover: EPV, EVA, RIM, Piotroski F-Score, Magic Formula.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers — import module under test (will fail until GREEN phase)
# ---------------------------------------------------------------------------

from lockin.agents.valuations import (
    calculate_epv,
    calculate_eva,
    calculate_rim,
    magic_formula_metrics,
    piotroski_f_score,
)


# ===========================================================================
# calculate_epv — Earnings Power Value
# ===========================================================================


class TestCalculateEpv:
    """calculate_epv(ebit_5y_avg, tax_rate, wacc, shares_outstanding) -> float"""

    def test_epv_basic(self):
        """ebit=1B, tax=0.21, wacc=0.10, shares=1B => per_share = (1B * 0.79 / 0.10) / 1B = 7.9"""
        result = calculate_epv(
            ebit_5y_avg=1_000_000_000,
            tax_rate=0.21,
            wacc=0.10,
            shares_outstanding=1_000_000_000,
        )
        assert abs(result - 7.9) < 1e-9, f"Expected 7.9, got {result}"

    def test_epv_zero_wacc(self):
        """WACC=0 should raise ValueError (division by zero)."""
        with pytest.raises(ValueError, match="WACC"):
            calculate_epv(
                ebit_5y_avg=1_000_000_000,
                tax_rate=0.21,
                wacc=0.0,
                shares_outstanding=1_000_000_000,
            )

    def test_epv_negative_wacc(self):
        """Negative WACC should also raise ValueError."""
        with pytest.raises(ValueError, match="WACC"):
            calculate_epv(
                ebit_5y_avg=1_000_000_000,
                tax_rate=0.21,
                wacc=-0.05,
                shares_outstanding=1_000_000_000,
            )

    def test_epv_negative_ebit(self):
        """Negative EBIT is valid — should return a negative EPV per share."""
        result = calculate_epv(
            ebit_5y_avg=-500_000_000,
            tax_rate=0.21,
            wacc=0.10,
            shares_outstanding=1_000_000_000,
        )
        assert result < 0, "Negative EBIT must produce negative EPV per share"

    def test_epv_scales_with_shares(self):
        """Doubling shares_outstanding halves per-share value."""
        v1 = calculate_epv(1_000_000_000, 0.21, 0.10, 1_000_000_000)
        v2 = calculate_epv(1_000_000_000, 0.21, 0.10, 2_000_000_000)
        assert abs(v1 - 2 * v2) < 1e-9


# ===========================================================================
# calculate_eva — Economic Value Added
# ===========================================================================


class TestCalculateEva:
    """calculate_eva(nopat, wacc, invested_capital) -> float"""

    def test_eva_positive(self):
        """nopat=500M, wacc=0.10, ic=2B => EVA = 500M - 200M = 300M"""
        result = calculate_eva(
            nopat=500_000_000,
            wacc=0.10,
            invested_capital=2_000_000_000,
        )
        assert abs(result - 300_000_000) < 1e-3

    def test_eva_negative(self):
        """nopat=100M, wacc=0.10, ic=2B => EVA = 100M - 200M = -100M"""
        result = calculate_eva(
            nopat=100_000_000,
            wacc=0.10,
            invested_capital=2_000_000_000,
        )
        assert abs(result - (-100_000_000)) < 1e-3

    def test_eva_zero(self):
        """nopat = wacc * IC => EVA = 0 (firm earning exactly its cost of capital)."""
        result = calculate_eva(
            nopat=200_000_000,
            wacc=0.10,
            invested_capital=2_000_000_000,
        )
        assert abs(result) < 1e-3


# ===========================================================================
# calculate_rim — Residual Income Model
# ===========================================================================


class TestCalculateRim:
    """calculate_rim(book_value, roe, cost_of_equity, growth_rate, shares_outstanding) -> float"""

    def test_rim_basic(self):
        """bv=10B, roe=0.15, coe=0.10, g=0.03, shares=1B => per_share ~17.14

        Derivation:
          residual_spread = (0.15 - 0.10) / (0.10 - 0.03) = 0.05 / 0.07 ≈ 0.7143
          total_value = 10B * (1 + 0.7143) ≈ 17.143B
          per_share = 17.143B / 1B ≈ 17.143
        """
        result = calculate_rim(
            book_value=10_000_000_000,
            roe=0.15,
            cost_of_equity=0.10,
            growth_rate=0.03,
            shares_outstanding=1_000_000_000,
        )
        expected = 10_000_000_000 * (1 + (0.15 - 0.10) / (0.10 - 0.03)) / 1_000_000_000
        assert abs(result - expected) < 1e-6

    def test_rim_roe_below_coe(self):
        """When ROE < COE, intrinsic value < book value per share."""
        book_value = 10_000_000_000
        shares = 1_000_000_000
        book_per_share = book_value / shares
        result = calculate_rim(
            book_value=book_value,
            roe=0.08,
            cost_of_equity=0.10,
            growth_rate=0.03,
            shares_outstanding=shares,
        )
        assert result < book_per_share, (
            f"ROE < COE should give per-share value below book; "
            f"got {result:.4f} vs book {book_per_share:.4f}"
        )

    def test_rim_coe_must_exceed_growth_rate(self):
        """cost_of_equity <= growth_rate should raise ValueError."""
        with pytest.raises(ValueError, match="cost_of_equity"):
            calculate_rim(
                book_value=10_000_000_000,
                roe=0.15,
                cost_of_equity=0.03,
                growth_rate=0.05,
                shares_outstanding=1_000_000_000,
            )

    def test_rim_coe_equal_growth_rate(self):
        """cost_of_equity == growth_rate should raise ValueError (division by zero)."""
        with pytest.raises(ValueError):
            calculate_rim(
                book_value=10_000_000_000,
                roe=0.15,
                cost_of_equity=0.05,
                growth_rate=0.05,
                shares_outstanding=1_000_000_000,
            )


# ===========================================================================
# piotroski_f_score — Quality scoring (0-9)
# ===========================================================================

# Signal keys required in current / prior dicts:
_CURRENT_PERFECT = {
    "net_income": 100.0,
    "operating_cf": 150.0,
    "roa": 0.10,          # return on assets (net_income / total_assets)
    "total_assets": 1_000.0,
    "long_term_debt": 200.0,
    "current_ratio": 2.0,
    "shares_outstanding": 100.0,
    "gross_profit": 400.0,
    "total_revenue": 1_000.0,
    "asset_turnover": 1.0,  # revenue / total_assets
}

_PRIOR_PERFECT = {
    "net_income": 80.0,
    "operating_cf": 120.0,
    "roa": 0.08,          # lower roa than current → roa_increasing ✓
    "total_assets": 1_000.0,
    "long_term_debt": 250.0,  # higher than current → decreasing ✓
    "current_ratio": 1.8,     # lower than current → increasing ✓
    "shares_outstanding": 100.0,  # same as current → no dilution ✓
    "gross_profit": 350.0,
    "total_revenue": 950.0,
    "asset_turnover": 0.95,   # lower than current → increasing ✓
}

_CURRENT_ZERO = {
    "net_income": -50.0,       # (1) negative
    "operating_cf": -20.0,     # (2) negative
    "roa": 0.05,               # (3) decreasing vs prior 0.10
    "total_assets": 1_000.0,
    "long_term_debt": 400.0,   # (5) increasing vs prior 300
    "current_ratio": 1.0,      # (6) decreasing vs prior 1.5
    "shares_outstanding": 120.0, # (7) diluted vs prior 100
    "gross_profit": 300.0,
    "total_revenue": 1_000.0,
    "asset_turnover": 0.8,     # (9) decreasing vs prior 1.0
}

_PRIOR_ZERO = {
    "net_income": 100.0,
    "operating_cf": 80.0,
    "roa": 0.10,
    "total_assets": 1_000.0,
    "long_term_debt": 300.0,
    "current_ratio": 1.5,
    "shares_outstanding": 100.0,
    "gross_profit": 380.0,
    "total_revenue": 1_000.0,
    "asset_turnover": 1.0,
}


class TestPiotroskiFScore:
    """piotroski_f_score(current: dict, prior: dict) -> int (0-9)"""

    def test_f_score_perfect(self):
        """All 9 signals positive → returns 9."""
        score = piotroski_f_score(_CURRENT_PERFECT, _PRIOR_PERFECT)
        assert score == 9, f"Expected 9, got {score}"

    def test_f_score_zero(self):
        """All signals negative/missing → returns 0 (or very low).

        For _CURRENT_ZERO vs _PRIOR_ZERO:
        (1) net_income < 0         → 0
        (2) operating_cf < 0       → 0
        (3) roa 0.05 < prior 0.10  → 0
        (4) ocf -20 < net_income -50 → 0 (ocf not > net_income) -- actually -20 > -50, so 1
        (5) LTD 400 > prior 300    → 0
        (6) CR 1.0 < prior 1.5     → 0
        (7) shares 120 > prior 100 → 0
        (8) gross margin 300/1000=0.30 vs 380/1000=0.38 → decreasing → 0
        (9) asset_turn 0.8 < 1.0   → 0

        Note: signal (4) ocf > net_income: -20 > -50 is True → +1
        So minimum achievable score for _CURRENT_ZERO vs _PRIOR_ZERO is 1, not 0.
        We test score <= 2 to allow for edge-case (4) interpretation.
        """
        score = piotroski_f_score(_CURRENT_ZERO, _PRIOR_ZERO)
        assert score <= 2, f"Expected low score (<=2) for mostly-failing signals, got {score}"

    def test_f_score_range(self):
        """Score must always be between 0 and 9 inclusive."""
        s1 = piotroski_f_score(_CURRENT_PERFECT, _PRIOR_PERFECT)
        s2 = piotroski_f_score(_CURRENT_ZERO, _PRIOR_ZERO)
        for s in [s1, s2]:
            assert 0 <= s <= 9, f"Score {s} out of range [0, 9]"

    def test_f_score_partial(self):
        """Mixed signals → correct count in middle range."""
        # 5 positive signals: net_income>0, ocf>0, roa_increasing, ocf>net_income, no_dilution
        current = {
            "net_income": 50.0,       # (1) ✓
            "operating_cf": 80.0,     # (2) ✓
            "roa": 0.12,              # (3) ✓ — roa improved vs prior 0.10
            "total_assets": 1_000.0,
            "long_term_debt": 350.0,  # (5) ✗ — increased vs prior 300
            "current_ratio": 1.2,     # (6) ✗ — decreased vs prior 1.5
            "shares_outstanding": 100.0, # (7) ✓ — same as prior
            "gross_profit": 300.0,
            "total_revenue": 1_000.0, # gross_margin 0.30 < prior 0.38 → (8) ✗
            "asset_turnover": 0.9,    # (9) ✗ — decreased vs prior 1.0
        }
        prior = {
            "net_income": 30.0,
            "operating_cf": 60.0,
            "roa": 0.10,
            "total_assets": 1_000.0,
            "long_term_debt": 300.0,
            "current_ratio": 1.5,
            "shares_outstanding": 100.0,
            "gross_profit": 380.0,
            "total_revenue": 1_000.0,
            "asset_turnover": 1.0,
        }
        # Expected: signals 1,2,3,4,7 = 5 (ocf 80 > net_income 50 ✓)
        score = piotroski_f_score(current, prior)
        assert score == 5, f"Expected 5 for mixed signals, got {score}"

    def test_f_score_returns_int(self):
        """Return type must be int."""
        score = piotroski_f_score(_CURRENT_PERFECT, _PRIOR_PERFECT)
        assert isinstance(score, int), f"Expected int, got {type(score)}"


# ===========================================================================
# magic_formula_metrics — Greenblatt Magic Formula
# ===========================================================================


class TestMagicFormulaMetrics:
    """magic_formula_metrics(ebit, enterprise_value, net_fixed_assets, working_capital) -> dict"""

    def test_magic_formula_basic(self):
        """ebit=1B, ev=10B, nfa=3B, wc=1B → earnings_yield=0.1, roic=0.25"""
        result = magic_formula_metrics(
            ebit=1_000_000_000,
            enterprise_value=10_000_000_000,
            net_fixed_assets=3_000_000_000,
            working_capital=1_000_000_000,
        )
        assert "earnings_yield" in result
        assert "roic" in result
        assert abs(result["earnings_yield"] - 0.10) < 1e-9
        assert abs(result["roic"] - 0.25) < 1e-9

    def test_magic_formula_zero_ev(self):
        """Zero enterprise_value → earnings_yield=0 (no division by zero crash)."""
        result = magic_formula_metrics(
            ebit=1_000_000_000,
            enterprise_value=0,
            net_fixed_assets=3_000_000_000,
            working_capital=1_000_000_000,
        )
        assert result["earnings_yield"] == 0

    def test_magic_formula_zero_capital_base(self):
        """Zero nfa + wc → roic=0 (no division by zero crash)."""
        result = magic_formula_metrics(
            ebit=1_000_000_000,
            enterprise_value=10_000_000_000,
            net_fixed_assets=0,
            working_capital=0,
        )
        assert result["roic"] == 0

    def test_magic_formula_returns_dict(self):
        """Return type must be a dict with at least earnings_yield and roic keys."""
        result = magic_formula_metrics(1e9, 10e9, 3e9, 1e9)
        assert isinstance(result, dict)
        assert "earnings_yield" in result
        assert "roic" in result
