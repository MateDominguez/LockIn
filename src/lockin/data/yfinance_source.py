"""
YFinanceSource — Concrete implementation of DataSourceProtocol using yfinance.

Fetches fundamental financial data (income statement, balance sheet, cash flow)
from Yahoo Finance with:
  - Tenacity retry logic (3 attempts, exponential backoff) for rate limit resilience.
  - TTL caching (24-hour default) to reduce redundant API calls.
  - Stale cache fallback when re-fetch fails (graceful degradation).
  - Point-in-time column filtering when as_of_date is provided (avoid look-ahead bias).
  - Partial result support — missing fields logged in missing_fields, never silently dropped.

Usage
-----
from lockin.data.yfinance_source import YFinanceSource

source = YFinanceSource()
result = source.get_fundamentals("AAPL")
result_pit = source.get_fundamentals("AAPL", as_of_date=date(2023, 1, 1))
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd
import yfinance as yf
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from lockin.data.cache import TTL_FUNDAMENTALS, TTLCache
from lockin.data.exceptions import DataUnavailableError
from lockin.data.types import FundamentalsResult

# ---------------------------------------------------------------------------
# Field mappings — yfinance DataFrame index label → FundamentalsResult key
# yfinance uses human-readable multi-word labels (e.g. "Total Revenue").
# ---------------------------------------------------------------------------

# Income statement fields
_INCOME_FIELDS: dict[str, str] = {
    "Total Revenue": "total_revenue",
    "Net Income": "net_income",
    "Gross Profit": "gross_profit",
    "Operating Income": "operating_income",
    "EBITDA": "ebitda",
    "Diluted EPS": "diluted_eps",
}

# Balance sheet fields
_BALANCE_FIELDS: dict[str, str] = {
    "Total Assets": "total_assets",
    "Total Debt": "total_debt",
    "Cash And Cash Equivalents": "cash_and_equivalents",
    "Stockholders Equity": "total_equity",
}

# Cash flow fields
_CASHFLOW_FIELDS: dict[str, str] = {
    "Free Cash Flow": "free_cash_flow",
}


def _safe_float(val: Any) -> float | None:
    """Convert a pandas/numpy scalar to Python float, or None if NaN/missing."""
    try:
        f = float(val)
        import math
        if math.isnan(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


class YFinanceSource:
    """Fundamental financial data source backed by Yahoo Finance (yfinance).

    Implements DataSourceProtocol structurally — no inheritance required.

    Parameters
    ----------
    cache : TTLCache | None
        Optional injected cache for testing/sharing. If None, a new instance
        is created (default for production use).
    """

    def __init__(self, cache: TTLCache | None = None) -> None:
        self._cache: TTLCache = cache if cache is not None else TTLCache()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _fetch_ticker(self, ticker_sym: str) -> yf.Ticker:
        """Fetch a yfinance Ticker object with retry on any exception.

        This is the retry boundary. Rate limit responses (HTTP 429) will
        trigger exponential backoff before the next attempt.

        Parameters
        ----------
        ticker_sym : str
            Stock ticker symbol (e.g. "AAPL").

        Returns
        -------
        yf.Ticker
            Ticker object ready for .income_stmt, .balance_sheet, .cashflow.
        """
        return yf.Ticker(ticker_sym)

    def _filter_columns_by_date(
        self, df: pd.DataFrame, cutoff: date
    ) -> pd.DataFrame:
        """Keep only DataFrame columns whose date is <= cutoff.

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame with Timestamp columns (yfinance annual report dates).
        cutoff : date
            Maximum allowed column date (inclusive).

        Returns
        -------
        pd.DataFrame
            Filtered DataFrame (may be empty if all columns are after cutoff).
        """
        if df.empty:
            return df
        valid_cols = [
            col for col in df.columns
            if pd.Timestamp(col).date() <= cutoff
        ]
        return df[valid_cols]

    def _extract_field(
        self,
        df: pd.DataFrame,
        yf_label: str,
        result_key: str,
        extracted: dict[str, float | None],
        missing_fields: list[str],
    ) -> None:
        """Extract a single field from the most recent column of a DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame (income_stmt, balance_sheet, or cashflow).
        yf_label : str
            Row index label in the yfinance DataFrame.
        result_key : str
            Key to write into extracted dict.
        extracted : dict
            Accumulator for extracted values.
        missing_fields : list
            Accumulator for field names not found in DataFrame.
        """
        if df.empty or df.shape[1] == 0:
            missing_fields.append(result_key)
            return
        try:
            row = df.loc[yf_label]
            # Most recent column is index 0 (yfinance sorts newest first)
            val = row.iloc[0]
            extracted[result_key] = _safe_float(val)
        except KeyError:
            missing_fields.append(result_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_fundamentals(
        self,
        ticker: str,
        as_of_date: date | None = None,
    ) -> FundamentalsResult:
        """Fetch fundamental financial data for a given ticker.

        Parameters
        ----------
        ticker : str
            The stock ticker symbol (e.g. "AAPL").
        as_of_date : date | None
            Point-in-time date for look-ahead-safe fetching.
            None means "live" (latest available data).

        Returns
        -------
        FundamentalsResult
            TypedDict with financial fields, fiscal_year_end, and metadata.

        Raises
        ------
        DataUnavailableError
            When all fetch attempts fail and no cached data exists.
        """
        cache_key = f"fundamentals:{ticker}"
        data_freshness = "FRESH"

        # ---- 1. Cache check ----
        cached_raw = self._cache.get(cache_key, TTL_FUNDAMENTALS)

        # ---- 2. Fetch on cache miss ----
        if cached_raw is None:
            try:
                ticker_obj = self._fetch_ticker(ticker)
                income_stmt = ticker_obj.income_stmt
                balance_sheet = ticker_obj.balance_sheet
                cashflow = ticker_obj.cashflow

                all_empty = (
                    (income_stmt is None or income_stmt.empty)
                    and (balance_sheet is None or balance_sheet.empty)
                    and (cashflow is None or cashflow.empty)
                )

                if all_empty:
                    # Try stale fallback before raising
                    stale = self._cache.get_stale(cache_key)
                    if stale is not None:
                        cached_raw = stale
                        data_freshness = "STALE"
                    else:
                        raise DataUnavailableError(ticker=ticker, source="yfinance")
                else:
                    raw_data: dict[str, pd.DataFrame] = {
                        "income_stmt": income_stmt if income_stmt is not None else pd.DataFrame(),
                        "balance_sheet": balance_sheet if balance_sheet is not None else pd.DataFrame(),
                        "cashflow": cashflow if cashflow is not None else pd.DataFrame(),
                    }
                    # Store raw DataFrames in cache
                    self._cache.set(cache_key, raw_data)
                    cached_raw = raw_data

            except DataUnavailableError:
                raise
            except Exception as exc:
                # Retry exhausted — try stale fallback
                stale = self._cache.get_stale(cache_key)
                if stale is not None:
                    cached_raw = stale
                    data_freshness = "STALE"
                    print(
                        f"[YFinanceSource] WARNING: re-fetch failed for {ticker}, "
                        f"using stale cache. Error: {exc}",
                        file=sys.stderr,
                    )
                else:
                    raise DataUnavailableError(ticker=ticker, source="yfinance") from exc

        # ---- 3. Extract DataFrames from cached raw data ----
        income_stmt: pd.DataFrame = cached_raw.get("income_stmt", pd.DataFrame())
        balance_sheet: pd.DataFrame = cached_raw.get("balance_sheet", pd.DataFrame())
        cashflow: pd.DataFrame = cached_raw.get("cashflow", pd.DataFrame())

        # ---- 4. Point-in-time filtering ----
        if as_of_date is not None and as_of_date != date.today():
            cutoff = as_of_date + timedelta(days=7)
            income_stmt = self._filter_columns_by_date(income_stmt, cutoff)
            balance_sheet = self._filter_columns_by_date(balance_sheet, cutoff)
            cashflow = self._filter_columns_by_date(cashflow, cutoff)

        # ---- 5. Extract fiscal_year_end from most recent valid income_stmt column ----
        fiscal_year_end: date | None = None
        if not income_stmt.empty and income_stmt.shape[1] > 0:
            first_col = income_stmt.columns[0]
            try:
                fiscal_year_end = pd.Timestamp(first_col).date()
            except Exception:
                fiscal_year_end = None
        elif not balance_sheet.empty and balance_sheet.shape[1] > 0:
            # Fallback to balance sheet date if income_stmt has no columns
            first_col = balance_sheet.columns[0]
            try:
                fiscal_year_end = pd.Timestamp(first_col).date()
            except Exception:
                fiscal_year_end = None

        # ---- 6. Extract financial fields ----
        extracted: dict[str, float | None] = {}
        missing_fields: list[str] = []

        for yf_label, result_key in _INCOME_FIELDS.items():
            self._extract_field(income_stmt, yf_label, result_key, extracted, missing_fields)

        for yf_label, result_key in _BALANCE_FIELDS.items():
            self._extract_field(balance_sheet, yf_label, result_key, extracted, missing_fields)

        for yf_label, result_key in _CASHFLOW_FIELDS.items():
            self._extract_field(cashflow, yf_label, result_key, extracted, missing_fields)

        # ---- 7. Build and return FundamentalsResult ----
        result: FundamentalsResult = {
            "ticker": ticker,
            # Income statement
            "total_revenue": extracted.get("total_revenue"),
            "net_income": extracted.get("net_income"),
            "gross_profit": extracted.get("gross_profit"),
            "operating_income": extracted.get("operating_income"),
            "ebitda": extracted.get("ebitda"),
            "diluted_eps": extracted.get("diluted_eps"),
            "free_cash_flow": extracted.get("free_cash_flow"),
            # Balance sheet
            "total_assets": extracted.get("total_assets"),
            "total_debt": extracted.get("total_debt"),
            "cash_and_equivalents": extracted.get("cash_and_equivalents"),
            "total_equity": extracted.get("total_equity"),
            # Point-in-time anchor
            "fiscal_year_end": fiscal_year_end,
            # Metadata
            "source": "yfinance",
            "fetched_at": datetime.now(timezone.utc),
            "as_of_date": as_of_date.isoformat() if as_of_date else "live",
            "missing_fields": missing_fields,
            "outlier_flags": {},  # Populated by validator in Plan 02-04
            "data_freshness": data_freshness,
        }

        return result
