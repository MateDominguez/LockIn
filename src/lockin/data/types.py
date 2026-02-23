"""
Data layer TypedDicts — Type contracts for all data layer modules.

Uses total=False (same convention as InvestmentState) so partial updates
from sources and validators can be merged without requiring every field.

All downstream modules (protocols.py, cache.py, storage.py, validators.py,
and the agents in Phase 3) import from this module.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TypedDict


# ---------------------------------------------------------------------------
# Fundamental financial data from a single company annual report
# ---------------------------------------------------------------------------

class FundamentalsResult(TypedDict, total=False):
    # Identity
    ticker: str

    # Income statement fields
    total_revenue: float | None
    net_income: float | None
    gross_profit: float | None
    operating_income: float | None
    ebitda: float | None
    diluted_eps: float | None
    free_cash_flow: float | None

    # Balance sheet fields
    total_assets: float | None
    total_debt: float | None
    cash_and_equivalents: float | None
    total_equity: float | None

    # Point-in-time anchor — fiscal year end of the most recent annual report
    # used. Populated by YFinanceSource from the DataFrame column date.
    # None if not determinable. Required by storage.py to key the
    # fundamentals table correctly and avoid look-ahead bias.
    fiscal_year_end: date | None

    # Metadata
    source: str
    fetched_at: datetime
    as_of_date: str          # ISO date string (e.g. "2024-01-15") or "live"
    data_freshness: str      # "FRESH" | "STALE"

    # Validation metadata (merged in by get_fundamentals() public API)
    quality_score: float     # 0.0 – 1.0 fraction of required fields present
    missing_fields: list[str]
    outlier_flags: dict[str, bool]
    hitl_required: bool
    hitl_reason: str


# ---------------------------------------------------------------------------
# Macroeconomic indicator snapshot
# ---------------------------------------------------------------------------

class MacroResult(TypedDict, total=False):
    # FRED indicators
    gdp: float | None
    cpi: float | None
    core_pce: float | None
    fed_funds: float | None
    yield_10y_2y: float | None    # 10Y minus 2Y spread (basis points)
    yield_10y_3m: float | None    # 10Y minus 3M spread (basis points)
    unemployment: float | None

    # Metadata
    source: str
    fetched_at: datetime
    as_of_date: str          # ISO date string or "live"
    data_freshness: str      # "FRESH" | "STALE"


# ---------------------------------------------------------------------------
# Data quality validation result (produced by validator.py)
# ---------------------------------------------------------------------------

class ValidationResult(TypedDict, total=False):
    quality_score: float          # 0.0 – 1.0 (fraction of required fields present)
    missing_fields: list[str]
    outlier_flags: dict[str, bool]
    hitl_required: bool
    hitl_reason: str


# ---------------------------------------------------------------------------
# Required fields list — used by validator to compute quality_score
# ---------------------------------------------------------------------------

REQUIRED_FUNDAMENTAL_FIELDS: list[str] = [
    "total_revenue",
    "net_income",
    "total_assets",
    "total_debt",
    "total_equity",
    "cash_and_equivalents",
    "diluted_eps",
]
