"""
Valuation formula functions for the Value Hunter (Bull) agent.

Implements three core intrinsic-value models:
  - EPV (Earnings Power Value) — Greenwald's no-growth franchise value
  - EVA (Economic Value Added) — Residual-income firm value
  - RIM (Residual Income Model) — Book-value anchored perpetuity

Plus two quality / screening metrics:
  - Piotroski F-Score (9-signal accounting quality index)
  - Magic Formula metrics (Greenblatt earnings yield + ROIC)

All functions are pure (no I/O, no side effects) so they are trivially
testable and reusable across agents.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# EPV — Earnings Power Value (Greenwald)
# ---------------------------------------------------------------------------


def calculate_epv(
    ebit_5y_avg: float,
    tax_rate: float,
    wacc: float,
    shares_outstanding: float,
) -> float:
    """Calculate intrinsic value per share using the Earnings Power Value model.

    EPV assumes zero growth — the firm perpetually earns its average EBIT at
    current efficiency.  This is the conservative Graham-style floor value.

    Formula:
        after_tax_earnings = ebit_5y_avg * (1 - tax_rate)
        EPV_total          = after_tax_earnings / wacc
        EPV_per_share      = EPV_total / shares_outstanding

    Parameters
    ----------
    ebit_5y_avg : float
        5-year average EBIT (earnings before interest and taxes) in currency units.
        May be negative for loss-making companies; result will be negative.
    tax_rate : float
        Effective tax rate as a decimal (e.g. 0.21 for 21%).
    wacc : float
        Weighted average cost of capital as a decimal (must be > 0).
    shares_outstanding : float
        Number of diluted shares outstanding.

    Returns
    -------
    float
        EPV per share in currency units.

    Raises
    ------
    ValueError
        If wacc <= 0 (perpetuity calculation requires positive discount rate).
    """
    if wacc <= 0:
        raise ValueError(
            f"WACC must be positive for EPV calculation, got {wacc}. "
            "A zero or negative WACC implies infinite or negative firm value."
        )
    after_tax = ebit_5y_avg * (1 - tax_rate)
    return after_tax / wacc / shares_outstanding


# ---------------------------------------------------------------------------
# EVA — Economic Value Added
# ---------------------------------------------------------------------------


def calculate_eva(
    nopat: float,
    wacc: float,
    invested_capital: float,
) -> float:
    """Calculate Economic Value Added — the residual profit above cost of capital.

    EVA > 0 means the firm is creating shareholder value.
    EVA < 0 means the firm is destroying value even if accounting profit is positive.

    Formula:
        EVA = NOPAT - (WACC × Invested Capital)

    Parameters
    ----------
    nopat : float
        Net Operating Profit After Tax.
    wacc : float
        Weighted average cost of capital as a decimal.
    invested_capital : float
        Total invested capital (equity + interest-bearing debt).

    Returns
    -------
    float
        EVA in currency units (positive = value creation, negative = destruction).
    """
    return nopat - (wacc * invested_capital)


# ---------------------------------------------------------------------------
# RIM — Residual Income Model
# ---------------------------------------------------------------------------


def calculate_rim(
    book_value: float,
    roe: float,
    cost_of_equity: float,
    growth_rate: float,
    shares_outstanding: float,
) -> float:
    """Calculate intrinsic value per share using the Residual Income Model.

    RIM anchors value to book equity then adds/subtracts the present value of
    residual earnings (ROE - COE) in perpetuity with Gordon Growth Model.

    Formula:
        residual_spread = (ROE - COE) / (COE - g)
        total_value     = book_value * (1 + residual_spread)
        per_share       = total_value / shares_outstanding

    When ROE < COE, residual_spread is negative → total_value < book_value,
    correctly capturing value destruction.

    Parameters
    ----------
    book_value : float
        Total shareholders' equity (book value) in currency units.
    roe : float
        Return on equity as a decimal (e.g. 0.15 for 15%).
    cost_of_equity : float
        Required return on equity (discount rate) as a decimal.
    growth_rate : float
        Long-run sustainable growth rate as a decimal.
    shares_outstanding : float
        Number of diluted shares outstanding.

    Returns
    -------
    float
        RIM intrinsic value per share in currency units.

    Raises
    ------
    ValueError
        If cost_of_equity <= growth_rate (Gordon Growth Model denominator must
        be positive to keep the perpetuity finite).
    """
    if cost_of_equity <= growth_rate:
        raise ValueError(
            f"cost_of_equity ({cost_of_equity}) must exceed growth_rate ({growth_rate}). "
            "The Gordon Growth Model requires (COE - g) > 0 for a finite perpetuity value."
        )
    residual_spread = (roe - cost_of_equity) / (cost_of_equity - growth_rate)
    total_value = book_value * (1 + residual_spread)
    return total_value / shares_outstanding


# ---------------------------------------------------------------------------
# Piotroski F-Score (9 accounting-quality signals)
# ---------------------------------------------------------------------------


def piotroski_f_score(current: dict, prior: dict) -> int:
    """Calculate the Piotroski F-Score — a 0-9 composite accounting quality index.

    Each of the 9 binary signals contributes 1 point.  Higher scores (>=7)
    indicate strong accounting quality; lower scores (<=3) flag potential
    distress or earnings manipulation.

    Signals
    -------
    Profitability (4 signals):
        1. net_income > 0              (positive ROA)
        2. operating_cf > 0            (positive operating cash flow)
        3. roa increasing              (current roa > prior roa)
        4. operating_cf > net_income   (cash flow quality / accruals)

    Leverage / Liquidity (3 signals):
        5. long_term_debt decreasing   (current < prior)
        6. current_ratio increasing    (current > prior)
        7. no share dilution           (shares_outstanding not increased)

    Operating Efficiency (2 signals):
        8. gross_margin increasing     (gross_profit/total_revenue vs prior)
        9. asset_turnover increasing   (asset_turnover vs prior)

    Parameters
    ----------
    current : dict
        Current period data with keys: net_income, operating_cf, roa,
        total_assets, long_term_debt, current_ratio, shares_outstanding,
        gross_profit, total_revenue, asset_turnover.
    prior : dict
        Prior period data with the same keys.

    Returns
    -------
    int
        Integer score in [0, 9].
    """
    score = 0

    # --- Profitability ---

    # (1) ROA positive: net_income > 0
    if current.get("net_income", 0) > 0:
        score += 1

    # (2) Operating cash flow positive
    if current.get("operating_cf", 0) > 0:
        score += 1

    # (3) ROA increasing
    if current.get("roa", 0) > prior.get("roa", 0):
        score += 1

    # (4) Cash flow quality: OCF > net_income (low accruals)
    if current.get("operating_cf", 0) > current.get("net_income", 0):
        score += 1

    # --- Leverage / Liquidity ---

    # (5) Long-term debt decreasing
    if current.get("long_term_debt", 0) < prior.get("long_term_debt", 0):
        score += 1

    # (6) Current ratio increasing
    if current.get("current_ratio", 0) > prior.get("current_ratio", 0):
        score += 1

    # (7) No share dilution (shares_outstanding not increased)
    if current.get("shares_outstanding", 0) <= prior.get("shares_outstanding", 0):
        score += 1

    # --- Operating Efficiency ---

    # (8) Gross margin increasing
    current_revenue = current.get("total_revenue", 0)
    prior_revenue = prior.get("total_revenue", 0)
    current_gm = (
        current.get("gross_profit", 0) / current_revenue if current_revenue else 0
    )
    prior_gm = (
        prior.get("gross_profit", 0) / prior_revenue if prior_revenue else 0
    )
    if current_gm > prior_gm:
        score += 1

    # (9) Asset turnover increasing
    if current.get("asset_turnover", 0) > prior.get("asset_turnover", 0):
        score += 1

    return score


# ---------------------------------------------------------------------------
# Magic Formula metrics (Greenblatt)
# ---------------------------------------------------------------------------


def magic_formula_metrics(
    ebit: float,
    enterprise_value: float,
    net_fixed_assets: float,
    working_capital: float,
) -> dict:
    """Calculate Greenblatt Magic Formula screening metrics.

    The Magic Formula ranks stocks on two axes:
      1. Earnings Yield (EBIT / Enterprise Value) — measures cheapness
      2. ROIC (EBIT / (Net Fixed Assets + Working Capital)) — measures quality

    High-ranking stocks on both axes historically outperform.

    Parameters
    ----------
    ebit : float
        Earnings before interest and taxes.
    enterprise_value : float
        Market cap + total debt - cash (total firm value to all claimants).
    net_fixed_assets : float
        PP&E net of depreciation.
    working_capital : float
        Current assets minus current liabilities (operating working capital,
        excluding excess cash).

    Returns
    -------
    dict
        {"earnings_yield": float, "roic": float}
        Both metrics are 0 if the denominator is zero (guard against crashes).
    """
    earnings_yield = ebit / enterprise_value if enterprise_value else 0.0
    capital_base = net_fixed_assets + working_capital
    roic = ebit / capital_base if capital_base else 0.0
    return {"earnings_yield": earnings_yield, "roic": roic}
