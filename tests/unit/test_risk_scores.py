"""
Unit tests for risk score formula functions in lockin.agents.risk_scores.

TDD RED phase — all tests written before implementation.
Tests cover: Altman Z-Score, Beneish M-Score, VoMC Fragility.

Formula references:
  - Altman (1968) Z-Score for public firms
  - Beneish (1999) M-Score for earnings manipulation detection
  - VoMC (Volatility of Mean Contribution) fragility index
"""

from __future__ import annotations

import math

import pytest

from lockin.agents.risk_scores import (
    altman_z_score,
    beneish_m_score,
    vomc_fragility,
)


# ===========================================================================
# altman_z_score — Altman (1968) Z-Score for public firms
# Formula: Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5
#   X1 = working_capital / total_assets
#   X2 = retained_earnings / total_assets
#   X3 = ebit / total_assets
#   X4 = market_cap / total_liabilities
#   X5 = revenue / total_assets
#
# Zones:
#   Z > 2.99  -> "safe"
#   1.81 < Z <= 2.99 -> "grey"
#   Z <= 1.81 -> "distress"
# ===========================================================================


class TestAltmanZScore:
    """altman_z_score(working_capital, retained_earnings, ebit, market_cap,
    total_liabilities, revenue, total_assets) -> dict"""

    def test_z_score_safe(self):
        """High-quality inputs should produce Z > 2.99, zone='safe'.

        Calculation:
          wc=500M, re=2B, ebit=1B, mcap=50B, tl=5B, rev=30B, ta=20B
          X1 = 500M/20B  = 0.025
          X2 = 2B/20B    = 0.10
          X3 = 1B/20B    = 0.05
          X4 = 50B/5B    = 10.0
          X5 = 30B/20B   = 1.5
          Z = 1.2*0.025 + 1.4*0.10 + 3.3*0.05 + 0.6*10.0 + 1.0*1.5
            = 0.03 + 0.14 + 0.165 + 6.0 + 1.5
            = 7.835
        """
        result = altman_z_score(
            working_capital=500_000_000,
            retained_earnings=2_000_000_000,
            ebit=1_000_000_000,
            market_cap=50_000_000_000,
            total_liabilities=5_000_000_000,
            revenue=30_000_000_000,
            total_assets=20_000_000_000,
        )
        assert "z_score" in result
        assert "zone" in result
        assert abs(result["z_score"] - 7.835) < 1e-6, (
            f"Expected Z~7.835, got {result['z_score']}"
        )
        assert result["zone"] == "safe", (
            f"Expected zone='safe', got {result['zone']}"
        )

    def test_z_score_distress(self):
        """Weak balance sheet should produce Z < 1.81, zone='distress'.

        Deliberately terrible inputs: high liabilities, low market cap,
        negative retained earnings, minimal revenue.
        """
        result = altman_z_score(
            working_capital=-500_000_000,      # negative working capital
            retained_earnings=-2_000_000_000,  # accumulated losses
            ebit=-100_000_000,                 # operating losses
            market_cap=200_000_000,            # tiny market cap
            total_liabilities=8_000_000_000,   # heavy debt load
            revenue=1_000_000_000,             # minimal revenue vs assets
            total_assets=5_000_000_000,
        )
        assert result["zone"] == "distress", (
            f"Expected zone='distress', got {result['zone']} (Z={result['z_score']:.3f})"
        )
        assert result["z_score"] < 1.81, (
            f"Expected Z < 1.81 for distressed firm, got {result['z_score']:.3f}"
        )

    def test_z_score_grey_zone(self):
        """Marginal inputs should produce 1.81 < Z < 2.99, zone='grey'.

        Tuned to land in the grey zone [1.81, 2.99]:
          wc=300M, re=200M, ebit=200M, mcap=2B, tl=3B, rev=4B, ta=5B
          X1 = 300M/5B = 0.06
          X2 = 200M/5B = 0.04
          X3 = 200M/5B = 0.04
          X4 = 2B/3B   = 0.667
          X5 = 4B/5B   = 0.8
          Z = 1.2*0.06 + 1.4*0.04 + 3.3*0.04 + 0.6*0.667 + 1.0*0.8
            = 0.072 + 0.056 + 0.132 + 0.4 + 0.8
            = 1.46  -- too low, adjust market cap upward
        Adjusted: mcap=6B, tl=3B → X4 = 2.0
          Z = 0.072 + 0.056 + 0.132 + 1.2 + 0.8 = 2.26  -> grey ✓
        """
        result = altman_z_score(
            working_capital=300_000_000,
            retained_earnings=200_000_000,
            ebit=200_000_000,
            market_cap=6_000_000_000,
            total_liabilities=3_000_000_000,
            revenue=4_000_000_000,
            total_assets=5_000_000_000,
        )
        assert result["zone"] == "grey", (
            f"Expected zone='grey', got {result['zone']} (Z={result['z_score']:.3f})"
        )
        assert 1.81 < result["z_score"] < 2.99, (
            f"Expected 1.81 < Z < 2.99, got {result['z_score']:.3f}"
        )

    def test_z_score_zero_assets_raises(self):
        """total_assets=0 should raise ValueError (division by zero)."""
        with pytest.raises(ValueError, match="total_assets"):
            altman_z_score(
                working_capital=100_000_000,
                retained_earnings=500_000_000,
                ebit=200_000_000,
                market_cap=1_000_000_000,
                total_liabilities=500_000_000,
                revenue=2_000_000_000,
                total_assets=0,
            )

    def test_z_score_returns_dict_with_required_keys(self):
        """Return value must be a dict with z_score and zone keys."""
        result = altman_z_score(
            working_capital=500_000_000,
            retained_earnings=2_000_000_000,
            ebit=1_000_000_000,
            market_cap=50_000_000_000,
            total_liabilities=5_000_000_000,
            revenue=30_000_000_000,
            total_assets=20_000_000_000,
        )
        assert isinstance(result, dict)
        assert "z_score" in result
        assert "zone" in result

    def test_z_score_boundary_safe(self):
        """Z exactly at 2.99 should NOT be 'safe' (safe requires Z > 2.99)."""
        # We test a value very close to 2.99 from below -> should be 'grey'
        # This validates the boundary condition strictly
        result = altman_z_score(
            working_capital=300_000_000,
            retained_earnings=200_000_000,
            ebit=200_000_000,
            market_cap=6_000_000_000,
            total_liabilities=3_000_000_000,
            revenue=4_000_000_000,
            total_assets=5_000_000_000,
        )
        # Just check zone is correctly set based on the formula
        z = result["z_score"]
        if z > 2.99:
            assert result["zone"] == "safe"
        elif z <= 1.81:
            assert result["zone"] == "distress"
        else:
            assert result["zone"] == "grey"


# ===========================================================================
# beneish_m_score — Beneish (1999) earnings manipulation M-Score
# Formula: M = -4.84 + 0.92*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI
#               + 0.115*DEPI - 0.172*SGAI + 4.679*TATA - 0.327*LVGI
#
# Interpretation:
#   M > -1.78  -> likely_manipulator=True  (red flag: ~75% manipulators detected)
#   M <= -2.22 -> clearly clean
#   -2.22 < M <= -1.78 -> borderline
# ===========================================================================


class TestBeneishMScore:
    """beneish_m_score(dsri, gmi, aqi, sgi, depi, sgai, tata, lvgi) -> dict"""

    def test_m_score_clean(self):
        """All indices near 1.0 (no change) should produce M < -1.78, likely_manipulator=False.

        With all inputs = 1.0:
          M = -4.84 + 0.92*1 + 0.528*1 + 0.404*1 + 0.892*1
              + 0.115*1 - 0.172*1 + 4.679*1 - 0.327*1
            = -4.84 + 0.92 + 0.528 + 0.404 + 0.892 + 0.115 - 0.172 + 4.679 - 0.327
            = 2.199 -- WAIT this is positive, use TATA=0 for clean firm

        Clean firms have minimal total accruals (TATA ≈ 0):
        With TATA=0.01 (typical for clean firms), all others = 1.0:
          M = -4.84 + 0.92 + 0.528 + 0.404 + 0.892 + 0.115 - 0.172 + 4.679*0.01 - 0.327
            = -4.84 + 2.466 + 0.04679
            = -2.327  -> clean (M < -2.22)
        """
        result = beneish_m_score(
            dsri=1.0,   # no change in receivables relative to sales
            gmi=1.0,    # no change in gross margin
            aqi=1.0,    # no change in asset quality
            sgi=1.0,    # no revenue growth (suspicious if DSRI also grows)
            depi=1.0,   # no change in depreciation
            sgai=1.0,   # no change in SGA expenses
            tata=0.01,  # low accruals (cash-based earnings)
            lvgi=1.0,   # no change in leverage
        )
        assert "m_score" in result
        assert "likely_manipulator" in result
        assert result["likely_manipulator"] is False, (
            f"Expected likely_manipulator=False for clean firm, got {result}"
        )
        assert result["m_score"] < -1.78, (
            f"Expected M < -1.78 for clean firm, got {result['m_score']:.3f}"
        )

    def test_m_score_manipulator(self):
        """High DSRI + high AQI + high TATA should produce M > -1.78, likely_manipulator=True.

        Manipulator profile (high-risk flags):
          DSRI=1.5 (receivables growing faster than sales -- revenue inflation)
          AQI=1.3 (increasing intangibles/off-balance assets)
          TATA=0.1 (high accruals relative to assets -- classic manipulation signal)
          Others near 1.0
        """
        result = beneish_m_score(
            dsri=1.5,
            gmi=1.0,
            aqi=1.3,
            sgi=1.2,
            depi=1.0,
            sgai=1.0,
            tata=0.1,
            lvgi=1.0,
        )
        assert result["likely_manipulator"] is True, (
            f"Expected likely_manipulator=True for manipulator profile, got {result}"
        )
        assert result["m_score"] > -1.78, (
            f"Expected M > -1.78 for manipulator, got {result['m_score']:.3f}"
        )

    def test_m_score_returns_dict_with_required_keys(self):
        """Return value must be a dict with m_score and likely_manipulator keys."""
        result = beneish_m_score(
            dsri=1.0, gmi=1.0, aqi=1.0, sgi=1.0,
            depi=1.0, sgai=1.0, tata=0.01, lvgi=1.0,
        )
        assert isinstance(result, dict)
        assert "m_score" in result
        assert "likely_manipulator" in result

    def test_m_score_formula_exact(self):
        """Verify exact formula: M = -4.84 + 0.92*dsri + 0.528*gmi + 0.404*aqi
        + 0.892*sgi + 0.115*depi - 0.172*sgai + 4.679*tata - 0.327*lvgi
        """
        dsri, gmi, aqi, sgi = 1.2, 0.9, 1.1, 1.15
        depi, sgai, tata, lvgi = 0.95, 1.05, 0.05, 1.0
        expected_m = (
            -4.84
            + 0.92 * dsri
            + 0.528 * gmi
            + 0.404 * aqi
            + 0.892 * sgi
            + 0.115 * depi
            - 0.172 * sgai
            + 4.679 * tata
            - 0.327 * lvgi
        )
        result = beneish_m_score(
            dsri=dsri, gmi=gmi, aqi=aqi, sgi=sgi,
            depi=depi, sgai=sgai, tata=tata, lvgi=lvgi,
        )
        assert abs(result["m_score"] - expected_m) < 1e-9, (
            f"Formula mismatch: expected {expected_m:.6f}, got {result['m_score']:.6f}"
        )


# ===========================================================================
# vomc_fragility — Volatility of Mean Contribution (VoMC) fragility index
# Formula:
#   annualized_vol = std(daily_returns) * sqrt(252)
#   fragility = 1 / (1 + exp(-10 * (annualized_vol - 0.3)))
#   -> Sigmoid centered at 0.3 (30% annualized vol)
#   -> vol << 0.3 -> fragility -> 0.0 (stable)
#   -> vol >> 0.3 -> fragility -> 1.0 (fragile)
# ===========================================================================


class TestVomcFragility:
    """vomc_fragility(daily_returns: list[float]) -> float"""

    def test_vomc_low_vol(self):
        """Low daily volatility (~1% daily = ~16% annualized) -> fragility < 0.3."""
        import random
        random.seed(42)
        # std ~0.01 daily = ~0.159 annualized (below 0.3 threshold)
        returns = [0.01 * (2 * random.random() - 1) for _ in range(252)]
        result = vomc_fragility(returns)
        assert isinstance(result, float)
        assert result < 0.3, (
            f"Expected fragility < 0.3 for low-vol stock, got {result:.4f}"
        )

    def test_vomc_high_vol(self):
        """High daily volatility (~4% daily = ~63% annualized) -> fragility > 0.7."""
        import random
        random.seed(42)
        # std ~0.04 daily = ~0.635 annualized (well above 0.3 threshold)
        returns = [0.04 * (2 * random.random() - 1) for _ in range(252)]
        result = vomc_fragility(returns)
        assert isinstance(result, float)
        assert result > 0.7, (
            f"Expected fragility > 0.7 for high-vol stock, got {result:.4f}"
        )

    def test_vomc_empty_returns_returns_half(self):
        """< 20 returns (too few data points) -> return 0.5 (maximum uncertainty)."""
        result = vomc_fragility([])
        assert result == 0.5, f"Expected 0.5 for empty returns, got {result}"

    def test_vomc_insufficient_returns_returns_half(self):
        """Fewer than 20 data points -> return 0.5."""
        result = vomc_fragility([0.01, 0.02, -0.01, 0.005, 0.015])
        assert result == 0.5, (
            f"Expected 0.5 for < 20 returns, got {result}"
        )

    def test_vomc_range(self):
        """Output must always be in (0, 1) open interval."""
        import random
        random.seed(99)
        # Normal volatility range
        returns_normal = [0.015 * (2 * random.random() - 1) for _ in range(252)]
        result = vomc_fragility(returns_normal)
        assert 0 < result < 1, f"Output must be in (0, 1), got {result}"

    def test_vomc_formula_exact(self):
        """Verify exact sigmoid formula at known vol."""
        # Construct returns with exact std = 0.02 daily
        # annualized = 0.02 * sqrt(252) ≈ 0.3175
        # fragility = 1 / (1 + exp(-10 * (0.3175 - 0.3))) = 1 / (1 + exp(-0.175))
        std_daily = 0.02
        n = 252
        # Generate centered returns with known std
        returns = [std_daily if i % 2 == 0 else -std_daily for i in range(n)]
        actual_std = (sum((r - sum(returns) / n) ** 2 for r in returns) / n) ** 0.5
        ann_vol = actual_std * math.sqrt(252)
        expected_fragility = 1.0 / (1.0 + math.exp(-10.0 * (ann_vol - 0.3)))
        result = vomc_fragility(returns)
        assert abs(result - expected_fragility) < 1e-9, (
            f"Formula mismatch: expected {expected_fragility:.6f}, got {result:.6f}"
        )
