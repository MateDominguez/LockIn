"""
TiingoSource — Historical price data including delisted companies.

Used as fallback when yfinance returns empty data for a ticker.
Free tier covers all listed and delisted US stocks from 1994.
Required for survivorship-bias-free backtesting.

Environment variable required:
    TIINGO_API_KEY — get a free key at https://api.tiingo.com/

## Usage

    from datetime import date
    from lockin.data.tiingo_source import TiingoSource, get_price_history_with_fallback

    source = TiingoSource()  # reads TIINGO_API_KEY from env; raises ValueError if missing

    # Delisted ticker: Lehman Brothers (removed Sep 2008, yfinance has no data)
    prices = source.get_closing_prices("LEH", date(2007, 1, 1), date(2008, 9, 1))
    # → {date(2007, 1, 3): 75.12, date(2007, 1, 4): 74.98, ...}  ~420 trading days

    # Safe fallback: yfinance first, Tiingo only if yfinance returns empty
    start, end = date(2007, 1, 1), date(2008, 9, 1)
    prices = get_price_history_with_fallback("LEH", start, end, tiingo=source)
    # → same dict — caller never needs to know which source served the data
"""

from __future__ import annotations

import os
import sys
from datetime import date

import requests

from lockin.data.cache import TTL_FUNDAMENTALS, TTLCache
from lockin.data.exceptions import DataUnavailableError

TIINGO_BASE = "https://api.tiingo.com/tiingo/daily"


class TiingoSource:
    """Historical price data source backed by Tiingo API.

    Handles both active and delisted tickers — critical for survivorship-bias-free
    backtesting where yfinance returns empty data for companies removed from indices.

    Parameters
    ----------
    api_key : str | None
        Tiingo API key. If None, reads TIINGO_API_KEY from environment.
        Raises ValueError immediately if key is missing (fail loud, fail early).
    cache : TTLCache | None
        Optional injected cache for testing/sharing. If None, a new instance
        is created (default for production use).
    """

    def __init__(self, api_key: str | None = None, cache: TTLCache | None = None) -> None:
        key = api_key or os.environ.get("TIINGO_API_KEY", "")
        if not key:
            raise ValueError(
                "TIINGO_API_KEY not set.\n"
                "Add it to .env: TIINGO_API_KEY=your_tiingo_key_here\n"
                "Get a free key at: https://api.tiingo.com/"
            )
        self._api_key = key
        self._cache: TTLCache = cache if cache is not None else TTLCache()
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Token {self._api_key}"})

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_price_history(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        frequency: str = "daily",
    ) -> list[dict]:
        """Fetch OHLCV price history for a ticker (active or delisted).

        Parameters
        ----------
        ticker : str
            Stock ticker symbol (e.g. "AAPL", "LEH" for delisted Lehman Brothers).
        start_date : date
            First date to include (inclusive).
        end_date : date
            Last date to include (inclusive).
        frequency : str
            "daily" or "monthly". Defaults to "daily".

        Returns
        -------
        list[dict]
            List of {date, open, high, low, close, volume, adjClose, ...} dicts.
            Empty list if ticker not found (404) — expected for some delisted tickers.

        Raises
        ------
        DataUnavailableError
            On non-404 HTTP errors or network failures when no stale cache exists.
        """
        cache_key = f"tiingo:{ticker}:{start_date}:{end_date}:{frequency}"
        cached = self._cache.get(cache_key, TTL_FUNDAMENTALS)
        if cached is not None:
            return cached

        url = f"{TIINGO_BASE}/{ticker}/prices"
        params: dict[str, str] = {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "resampleFreq": "monthly" if frequency == "monthly" else "daily",
            "token": self._api_key,
        }
        try:
            resp = self._session.get(url, params=params, timeout=15)
            if resp.status_code == 404:
                return []  # ticker not found — expected for some delisted companies
            resp.raise_for_status()
            data: list[dict] = resp.json()
            self._cache.set(cache_key, data)
            return data
        except requests.RequestException as exc:
            stale = self._cache.get_stale(cache_key)
            if stale is not None:
                print(
                    f"[TiingoSource] WARNING: fetch failed for {ticker}, "
                    f"using stale cache. Error: {exc}",
                    file=sys.stderr,
                )
                return stale
            raise DataUnavailableError(ticker=ticker, source="tiingo") from exc

    def get_closing_prices(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> dict[date, float]:
        """Return adjusted closing prices as {date: adjClose}.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol.
        start_date : date
            First date to include (inclusive).
        end_date : date
            Last date to include (inclusive).

        Returns
        -------
        dict[date, float]
            Mapping of trading date → split/dividend-adjusted closing price.
            Empty dict if ticker not found or no data in the requested range.
        """
        raw = self.get_price_history(ticker, start_date, end_date, "daily")
        return {
            date.fromisoformat(row["date"][:10]): float(row["adjClose"])
            for row in raw
            if row.get("adjClose") is not None
        }


# ---------------------------------------------------------------------------
# Module-level fallback function — yfinance first, Tiingo second
# ---------------------------------------------------------------------------

def get_price_history_with_fallback(
    ticker: str,
    start_date: date,
    end_date: date,
    tiingo: TiingoSource | None = None,
) -> dict[date, float]:
    """Get adjusted closing prices — yfinance first, Tiingo fallback.

    Tiingo fallback is critical for delisted companies that yfinance no longer
    carries. Both sources returning empty is not raised as an error — the caller
    should log and continue (some tickers are truly unavailable).

    Parameters
    ----------
    ticker : str
        Stock ticker symbol.
    start_date : date
        First date to include (inclusive).
    end_date : date
        Last date to include (inclusive).
    tiingo : TiingoSource | None
        Tiingo source for fallback. If None, Tiingo fallback is skipped.

    Returns
    -------
    dict[date, float]
        Mapping of trading date → adjusted closing price.
        Empty dict if both sources fail or return no data.
    """
    import yfinance as yf

    try:
        hist = yf.Ticker(ticker).history(
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            auto_adjust=True,
        )
        if not hist.empty:
            return {ts.date(): float(row["Close"]) for ts, row in hist.iterrows()}
    except Exception:
        pass

    if tiingo is not None:
        try:
            return tiingo.get_closing_prices(ticker, start_date, end_date)
        except DataUnavailableError:
            pass

    return {}


# ---------------------------------------------------------------------------
# Quick smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from datetime import date as _date

    print("TiingoSource smoke test")
    source = TiingoSource()  # raises if TIINGO_API_KEY not set

    # Active ticker
    start, end = _date(2020, 1, 1), _date(2020, 12, 31)
    prices = source.get_closing_prices("AAPL", start, end)
    assert prices, "Expected AAPL prices"
    print(f"AAPL: {len(prices)} days  first={min(prices)}  last={max(prices)}")

    # Delisted ticker — RSH (RadioShack, delisted 2015)
    prices_rsh = source.get_closing_prices("RSH", _date(2014, 1, 1), _date(2015, 3, 1))
    print(f"RSH (delisted 2015): {len(prices_rsh)} days")

    # Fallback function
    prices_fb = get_price_history_with_fallback("AAPL", start, end, tiingo=source)
    assert prices_fb, "Expected fallback prices for AAPL"
    print(f"AAPL (fallback fn): {len(prices_fb)} days")

    print("OK")
