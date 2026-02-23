"""
FREDSource — Concrete implementation of MacroSourceProtocol using fredapi.

Fetches macroeconomic indicators from the Federal Reserve Economic Data (FRED)
database with:
  - TTL caching (7-day default) to reduce redundant API calls.
  - Stale cache fallback when re-fetch fails (graceful degradation).
  - Point-in-time accuracy via ALFRED vintage dates for backtesting paths.
  - Partial result support — individual series failures yield None, not total abort.
  - DataUnavailableError only raised when ALL series fail and no cache exists.

Live analysis uses get_series() (latest available values).
Historical/backtesting uses get_series_as_of_date() which returns data as known
on that specific date — no revision look-ahead bias.

Usage
-----
from lockin.data.fred_source import FREDSource

source = FREDSource()
result = source.get_macro_indicators()
result_pit = source.get_macro_indicators(as_of_date=date(2023, 1, 1))
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from typing import Any

from fredapi import Fred

from lockin.data.cache import TTL_MACRO, TTLCache
from lockin.data.exceptions import DataUnavailableError
from lockin.data.types import MacroResult
from lockin.utils.config import get_settings

# ---------------------------------------------------------------------------
# FRED series ID mapping — indicator name → FRED series ID
# ---------------------------------------------------------------------------

FRED_SERIES: dict[str, str] = {
    "gdp": "GDP",
    "cpi": "CPIAUCSL",
    "core_pce": "PCEPILFE",
    "fed_funds": "FEDFUNDS",
    "yield_10y_2y": "T10Y2Y",
    "yield_10y_3m": "T10Y3M",
    "unemployment": "UNRATE",
}


class FREDSource:
    """Macroeconomic indicator source backed by FRED (Federal Reserve).

    Implements MacroSourceProtocol structurally — no inheritance required.

    Parameters
    ----------
    api_key : str | None
        FRED API key. If None, read from get_settings().fred_api_key.
        Raises DataUnavailableError if no key is available.
    cache : TTLCache | None
        Optional injected cache for testing/sharing. If None, a new instance
        is created (default for production use).
    """

    def __init__(
        self,
        api_key: str | None = None,
        cache: TTLCache | None = None,
    ) -> None:
        resolved_key = api_key or get_settings().fred_api_key
        if not resolved_key:
            raise DataUnavailableError(
                ticker="FRED",
                source="fred",
                message=(
                    "FRED API key not configured. "
                    "Set FRED_API_KEY in .env or pass api_key to FREDSource()."
                ),
            )
        self._fred: Fred = Fred(api_key=resolved_key)
        self._cache: TTLCache = cache if cache is not None else TTLCache()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch_series_live(self, series_id: str) -> float | None:
        """Fetch latest value for a FRED series (live analysis path).

        Parameters
        ----------
        series_id : str
            FRED series ID (e.g. "GDP").

        Returns
        -------
        float | None
            Most recent non-NaN value, or None on failure.
        """
        try:
            series = self._fred.get_series(series_id)
            clean = series.dropna()
            if clean.empty:
                return None
            return float(clean.iloc[-1])
        except Exception as exc:
            print(
                f"[FREDSource] WARNING: failed to fetch series '{series_id}': {exc}",
                file=sys.stderr,
            )
            return None

    def _fetch_series_historical(
        self, series_id: str, as_of_date: date
    ) -> float | None:
        """Fetch FRED series value as known on a specific historical date.

        Uses ALFRED vintage dates — returns data as it was known on as_of_date,
        preventing revision look-ahead bias in backtesting.

        Parameters
        ----------
        series_id : str
            FRED series ID (e.g. "GDP").
        as_of_date : date
            The date for which to retrieve vintage data.

        Returns
        -------
        float | None
            Most recent value as known on as_of_date, or None on failure.
        """
        try:
            df = self._fred.get_series_as_of_date(series_id, str(as_of_date))
            if df is None or df.empty:
                return None
            # df has columns: ['realtime_start', 'date', 'value']
            # Sort by date to ensure we get the most recent observation
            df_sorted = df.sort_values("date")
            val = df_sorted["value"].dropna()
            if val.empty:
                return None
            return float(val.iloc[-1])
        except Exception as exc:
            print(
                f"[FREDSource] WARNING: failed to fetch historical series "
                f"'{series_id}' as of {as_of_date}: {exc}",
                file=sys.stderr,
            )
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_macro_indicators(
        self,
        as_of_date: date | None = None,
    ) -> MacroResult:
        """Fetch macroeconomic indicators.

        Parameters
        ----------
        as_of_date : date | None
            Point-in-time date for look-ahead-safe fetching.
            None means "live" (latest available data).

        Returns
        -------
        MacroResult
            TypedDict with 7 FRED indicators and metadata.

        Raises
        ------
        DataUnavailableError
            When ALL series fetch attempts fail and no cached data exists.
        """
        is_live = as_of_date is None or as_of_date == date.today()
        cache_key = f"macro:{as_of_date or 'live'}"
        data_freshness = "FRESH"

        # ---- 1. Cache check ----
        cached_result = self._cache.get(cache_key, TTL_MACRO)
        if cached_result is not None:
            return cached_result

        # ---- 2. Fetch each series ----
        indicators: dict[str, float | None] = {}

        for indicator_name, series_id in FRED_SERIES.items():
            if is_live:
                value = self._fetch_series_live(series_id)
            else:
                value = self._fetch_series_historical(series_id, as_of_date)
            indicators[indicator_name] = value

        # ---- 3. Check for total failure ----
        all_none = all(v is None for v in indicators.values())
        if all_none:
            stale = self._cache.get_stale(cache_key)
            if stale is not None:
                return stale
            raise DataUnavailableError(
                ticker="FRED",
                source="fred",
                message=(
                    "All FRED series fetch attempts failed and no cached data exists. "
                    f"as_of_date={as_of_date or 'live'}"
                ),
            )

        # ---- 4. Build MacroResult ----
        result: MacroResult = {
            "gdp": indicators.get("gdp"),
            "cpi": indicators.get("cpi"),
            "core_pce": indicators.get("core_pce"),
            "fed_funds": indicators.get("fed_funds"),
            "yield_10y_2y": indicators.get("yield_10y_2y"),
            "yield_10y_3m": indicators.get("yield_10y_3m"),
            "unemployment": indicators.get("unemployment"),
            "source": "fred",
            "fetched_at": datetime.now(timezone.utc),
            "as_of_date": as_of_date.isoformat() if as_of_date else "live",
            "data_freshness": data_freshness,
        }

        # ---- 5. Cache the result ----
        self._cache.set(cache_key, result)

        return result
