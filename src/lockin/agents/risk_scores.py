"""
Risk score formula functions for the Guardian agent.

Pure, deterministic functions — no I/O, no LLM, no yfinance calls.
These implement well-known academic quantitative risk metrics:

  - altman_z_score: Altman (1968) Z-Score for public firms
  - beneish_m_score: Beneish (1999) M-Score for earnings manipulation detection
  - vomc_fragility: VoMC (Volatility of Mean Contribution) fragility sigmoid

All functions are deterministic and unit-testable in isolation.
The Guardian agent calls these, then applies the GRADUATED ConfidenceModifier
adjustment logic defined in guardian.py.

References:
  - Altman, E.I. (1968). Financial ratios, discriminant analysis and the
    prediction of corporate bankruptcy. Journal of Finance.
  - Beneish, M.D. (1999). The detection of earnings manipulation.
    Financial Analysts Journal.
"""

from __future__ import annotations

import math
import statistics


# ---------------------------------------------------------------------------
# Altman Z-Score (1968) — public firm bankruptcy prediction
# ---------------------------------------------------------------------------

# Zone thresholds from Altman (1968)
_Z_SAFE_THRESHOLD = 2.99
_Z_DISTRESS_THRESHOLD = 1.81


def altman_z_score(
    working_capital: float,
    retained_earnings: float,
    ebit: float,
    market_cap: float,
    total_liabilities: float,
    revenue: float,
    total_assets: float,
) -> dict:
    """Compute Altman (1968) Z-Score for public firms.

    Formula:
        Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5

    Where:
        X1 = working_capital / total_assets       (liquidity)
        X2 = retained_earnings / total_assets     (accumulated profitability)
        X3 = ebit / total_assets                  (operating efficiency)
        X4 = market_cap / total_liabilities       (market solvency)
        X5 = revenue / total_assets               (asset utilisation)

    Zones:
        Z > 2.99    -> "safe"    (low bankruptcy risk)
        1.81 < Z <= 2.99 -> "grey"    (uncertain / caution)
        Z <= 1.81   -> "distress" (high bankruptcy risk)

    Args:
        working_capital: Current assets minus current liabilities.
        retained_earnings: Accumulated retained earnings from balance sheet.
        ebit: Earnings before interest and taxes (operating income).
        market_cap: Current market capitalisation (shares * price).
        total_liabilities: Total liabilities from balance sheet.
        revenue: Total revenue for the period.
        total_assets: Total assets from balance sheet.

    Returns:
        dict with keys:
            z_score (float): The computed Z-Score.
            zone (str): "safe" | "grey" | "distress".
            x1..x5 (float): Component ratios for transparency.

    Raises:
        ValueError: If total_assets is zero (division by zero).
    """
    if total_assets == 0:
        raise ValueError(
            "total_assets must be non-zero to compute Altman Z-Score. "
            "Cannot compute financial ratios against zero total assets."
        )

    x1 = working_capital / total_assets
    x2 = retained_earnings / total_assets
    x3 = ebit / total_assets
    x4 = market_cap / total_liabilities if total_liabilities != 0 else 0.0
    x5 = revenue / total_assets

    z_score = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5

    if z_score > _Z_SAFE_THRESHOLD:
        zone = "safe"
    elif z_score <= _Z_DISTRESS_THRESHOLD:
        zone = "distress"
    else:
        zone = "grey"

    return {
        "z_score": z_score,
        "zone": zone,
        "x1": x1,
        "x2": x2,
        "x3": x3,
        "x4": x4,
        "x5": x5,
    }


# ---------------------------------------------------------------------------
# Beneish M-Score (1999) — earnings manipulation detection
# ---------------------------------------------------------------------------

# Manipulation threshold from Beneish (1999): M > -1.78 flags likely manipulator
_M_MANIPULATOR_THRESHOLD = -1.78


def beneish_m_score(
    dsri: float,
    gmi: float,
    aqi: float,
    sgi: float,
    depi: float,
    sgai: float,
    tata: float,
    lvgi: float,
) -> dict:
    """Compute Beneish (1999) M-Score for earnings manipulation detection.

    Formula:
        M = -4.84 + 0.92*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI
              + 0.115*DEPI - 0.172*SGAI + 4.679*TATA - 0.327*LVGI

    Index definitions (each is current_year / prior_year ratio):
        DSRI: Days Sales Receivables Index (receivables/sales ratio change)
              High DSRI -> receivables growing faster than sales (revenue inflation)
        GMI: Gross Margin Index (prior gross margin / current gross margin)
             GMI > 1 -> gross margin deteriorating (quality concern)
        AQI: Asset Quality Index (non-current non-PPE assets / total assets ratio)
             AQI > 1 -> increasing proportion of intangibles/off-balance assets
        SGI: Sales Growth Index (current sales / prior sales)
             High growth pressure can incentivise manipulation
        DEPI: Depreciation Index (prior depr rate / current depr rate)
              DEPI > 1 -> assets being depreciated more slowly (earnings boost)
        SGAI: SGA Expenses Index (SGA/sales current / SGA/sales prior)
              SGAI > 1 -> SGA costs growing faster than sales (efficiency decline)
        TATA: Total Accruals to Total Assets
              High TATA -> earnings driven by accruals, not cash (key manipulation signal)
        LVGI: Leverage Growth Index (leverage current / leverage prior)
              LVGI > 1 -> increasing leverage (financial pressure)

    Interpretation:
        M > -1.78   -> likely_manipulator=True  (flag for investigation)
        M <= -1.78  -> likely_manipulator=False

    Args:
        dsri: Days Sales Receivables Index.
        gmi: Gross Margin Index.
        aqi: Asset Quality Index.
        sgi: Sales Growth Index.
        depi: Depreciation Index.
        sgai: SGA Expenses Index.
        tata: Total Accruals to Total Assets.
        lvgi: Leverage Growth Index.

    Returns:
        dict with keys:
            m_score (float): The computed M-Score.
            likely_manipulator (bool): True if M > -1.78.
    """
    m_score = (
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

    likely_manipulator = m_score > _M_MANIPULATOR_THRESHOLD

    return {
        "m_score": m_score,
        "likely_manipulator": likely_manipulator,
    }


# ---------------------------------------------------------------------------
# VoMC Fragility — Volatility of Mean Contribution fragility sigmoid
# ---------------------------------------------------------------------------

_VOMC_MIN_RETURNS = 20       # minimum data points for meaningful computation
_VOMC_VOL_CENTER = 0.3       # sigmoid inflection: 30% annualised vol
_VOMC_STEEPNESS = 10.0       # sigmoid steepness parameter
_VOMC_TRADING_DAYS = 252     # trading days per year for annualisation


def vomc_fragility(daily_returns: list[float]) -> float:
    """Compute VoMC (Volatility of Mean Contribution) fragility score.

    Maps annualised daily-return volatility to a [0, 1] fragility index
    via a sigmoid function centred at 30% annualised volatility.

    Formula:
        annualized_vol = std(daily_returns) * sqrt(252)
        fragility = 1 / (1 + exp(-10 * (annualized_vol - 0.3)))

    Interpretation:
        fragility -> 0.0  : very stable (low volatility, low systemic risk)
        fragility ~= 0.5  : uncertain / unknown (returned for insufficient data)
        fragility -> 1.0  : very fragile (high volatility, high systemic risk)

    Sigmoid characteristics:
        - At 30% vol: fragility = 0.5 (neutral)
        - At 16% vol: fragility ≈ 0.18 (low risk)
        - At 63% vol: fragility ≈ 0.98 (very high risk)

    Args:
        daily_returns: List of daily log or arithmetic returns. Must have at
            least 20 data points for a meaningful estimate. Returns < 20
            points get a neutral 0.5 (maximum uncertainty).

    Returns:
        float in (0, 1): Fragility score.
            Returns 0.5 if len(daily_returns) < 20 (insufficient data).
    """
    if len(daily_returns) < _VOMC_MIN_RETURNS:
        return 0.5  # maximum uncertainty — not enough data

    # Use population std dev (pstdev) to match the formula
    # (same as numpy's std with ddof=0)
    daily_std = statistics.pstdev(daily_returns)
    annualized_vol = daily_std * math.sqrt(_VOMC_TRADING_DAYS)

    fragility = 1.0 / (1.0 + math.exp(-_VOMC_STEEPNESS * (annualized_vol - _VOMC_VOL_CENTER)))

    return fragility
