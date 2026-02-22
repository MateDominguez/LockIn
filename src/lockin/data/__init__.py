"""
Public API for the LockIn data layer.

Agents import ONLY from this module — never from submodules directly.
This module composes all data layer components into two simple functions:

    from lockin.data import get_fundamentals, get_macro_indicators

The functions handle:
  - Point-in-time enforcement (PointInTimeData wrapper)
  - Data quality validation (DataValidator)
  - Lazy storage to PostgreSQL (store_fundamentals, store_macro_data)
  - Graceful FRED key absence (falls back to _NoMacroSource)

Module-level globals (_default_pit, _default_validator) are lazily initialized
on first call so that importing this module at startup does NOT require a live
FRED API key or database connection.

Design notes:
  - Storage is opt-in (store=True by default) but non-fatal: a DB outage
    at write-time logs to stderr and returns the data normally.
  - FRED absence: if FRED_API_KEY is not set, get_macro_indicators raises
    DataUnavailableError on call instead of crashing at import time.
  - Validation metadata (missing_fields, outlier_flags) is merged into the
    FundamentalsResult so agents receive an enriched dict.
"""

from __future__ import annotations

import sys
from datetime import date
from typing import TYPE_CHECKING

from lockin.data.cache import TTLCache
from lockin.data.exceptions import DataUnavailableError, LookAheadError
from lockin.data.point_in_time import PointInTimeData
from lockin.data.protocols import DataSourceProtocol, MacroSourceProtocol
from lockin.data.storage import store_asset, store_fundamentals, store_macro_data
from lockin.data.types import FundamentalsResult, MacroResult, ValidationResult
from lockin.data.validator import DataValidator

if TYPE_CHECKING:
    pass  # future type-only imports go here


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "get_fundamentals",
    "get_macro_indicators",
    "PointInTimeData",
    "DataSourceProtocol",
    "MacroSourceProtocol",
    "DataUnavailableError",
    "LookAheadError",
    "FundamentalsResult",
    "MacroResult",
    "ValidationResult",
    "DataValidator",
    "TTLCache",
]


# ---------------------------------------------------------------------------
# Fallback macro source when FRED API key is not configured
# ---------------------------------------------------------------------------


class _NoMacroSource:
    """Stub MacroSource used when FREDSource cannot be initialized.

    Returns a DataUnavailableError on every call so the error surface is
    deferred to call-time rather than import-time.
    """

    def get_macro_indicators(self, as_of_date: date | None = None) -> MacroResult:
        raise DataUnavailableError(
            ticker="FRED",
            source="fred",
            message=(
                "FRED_API_KEY is not configured. "
                "Set FRED_API_KEY in your .env file to enable macro data."
            ),
        )


# ---------------------------------------------------------------------------
# Module-level lazy singletons
# ---------------------------------------------------------------------------

_default_pit: PointInTimeData | None = None
_default_validator: DataValidator | None = None


def _get_pit() -> PointInTimeData:
    """Return (or construct) the default PointInTimeData singleton.

    Construction is deferred to first call so importing this module never
    requires a live FRED API key or network access.

    FREDSource initialization raises DataUnavailableError when FRED_API_KEY
    is absent. In that case we substitute _NoMacroSource, which defers the
    error to the actual get_macro_indicators() call.
    """
    global _default_pit
    if _default_pit is None:
        from lockin.data.yfinance_source import YFinanceSource

        yf_source = YFinanceSource()

        try:
            from lockin.data.fred_source import FREDSource

            macro_source: MacroSourceProtocol = FREDSource()
        except DataUnavailableError:
            macro_source = _NoMacroSource()  # type: ignore[assignment]

        _default_pit = PointInTimeData(yf_source, macro_source)

    return _default_pit


def _get_validator() -> DataValidator:
    """Return (or construct) the default DataValidator singleton.

    Construction is deferred to first call — database_url may be empty in
    environments without a live Supabase connection (e2e tests, CI).
    """
    global _default_validator
    if _default_validator is None:
        from lockin.utils.config import get_settings

        _default_validator = DataValidator(database_url=get_settings().database_url)
    return _default_validator


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def get_fundamentals(
    ticker: str,
    as_of_date: date | None = None,
    store: bool = True,
) -> FundamentalsResult:
    """Fetch fundamental financial data for a ticker with full pipeline.

    Pipeline:
      1. PointInTimeData enforces future-date guard and live/historical bypass.
      2. DataValidator computes quality_score, missing_fields, outlier_flags.
      3. Validation metadata is merged into the FundamentalsResult.
      4. Lazily stores to PostgreSQL (if store=True and DATABASE_URL is set).

    Parameters
    ----------
    ticker : str
        Stock ticker symbol (e.g. "AAPL").
    as_of_date : date | None
        Point-in-time analysis date. None = live (latest available).
    store : bool
        If True (default), attempt to persist data to the fundamentals and
        assets tables. Storage failures are non-fatal (logged to stderr).

    Returns
    -------
    FundamentalsResult
        TypedDict with financial fields plus validation metadata merged in:
        missing_fields (list[str]) and outlier_flags (dict[str, bool]).

    Raises
    ------
    ValueError
        If as_of_date is in the future.
    DataUnavailableError
        If the data source cannot return data for the requested ticker.
    """
    # Step 1: fetch with point-in-time enforcement
    result: FundamentalsResult = _get_pit().get_fundamentals(ticker, as_of_date)

    # Step 2: validate quality
    validation: ValidationResult = _get_validator().validate_fundamentals(result)

    # Step 3: merge validation metadata into result
    result["missing_fields"] = validation["missing_fields"]  # type: ignore[typeddict-unknown-key]
    result["outlier_flags"] = validation["outlier_flags"]    # type: ignore[typeddict-unknown-key]

    # Step 4: lazy storage (non-fatal)
    if store:
        from lockin.utils.config import get_settings

        database_url = get_settings().database_url
        if database_url:
            try:
                # Determine fiscal_year_end anchor for the storage key
                fiscal_year_end: date = result.get("fiscal_year_end") or (  # type: ignore[typeddict-item]
                    as_of_date or date.today()
                )
                # Upsert asset registry first (foreign key dependency)
                store_asset(database_url, ticker)
                # Upsert fundamentals rows
                store_fundamentals(database_url, ticker, result, fiscal_year_end)
            except Exception as exc:  # noqa: BLE001
                print(
                    f"get_fundamentals storage error for {ticker}: {exc}",
                    file=sys.stderr,
                )

    return result


def get_macro_indicators(
    as_of_date: date | None = None,
    store: bool = True,
) -> MacroResult:
    """Fetch macroeconomic indicators with full pipeline.

    Pipeline:
      1. PointInTimeData enforces future-date guard and live/historical bypass.
      2. Lazily stores to PostgreSQL (if store=True and DATABASE_URL is set).

    Parameters
    ----------
    as_of_date : date | None
        Point-in-time analysis date. None = live (latest available).
    store : bool
        If True (default), attempt to persist data to the macro_data table.
        Storage failures are non-fatal (logged to stderr).

    Returns
    -------
    MacroResult
        TypedDict with 8 FRED indicators and metadata.

    Raises
    ------
    ValueError
        If as_of_date is in the future.
    DataUnavailableError
        If FRED_API_KEY is not configured or the source cannot return data.
    """
    # Step 1: fetch with point-in-time enforcement
    result: MacroResult = _get_pit().get_macro_indicators(as_of_date)

    # Step 2: lazy storage (non-fatal)
    if store:
        from lockin.utils.config import get_settings

        database_url = get_settings().database_url
        if database_url:
            try:
                store_macro_data(database_url, result)
            except Exception as exc:  # noqa: BLE001
                print(
                    f"get_macro_indicators storage error: {exc}",
                    file=sys.stderr,
                )

    return result
