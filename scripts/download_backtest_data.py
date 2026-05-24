#!/usr/bin/env python3
"""
scripts/download_backtest_data.py — Bulk data downloader for the backtest.

One-time (or resumable) download of fundamentals and price history for the
full S&P 500 historical universe (2009–2024). Safe to re-run: skips tickers
already present in the database so an interrupted download resumes cleanly.

## Usage

    # Recommended first run: fundamentals only, no Tiingo key needed yet
    uv run python scripts/download_backtest_data.py --mode fundamentals
    # → downloads ~500 tickers × annual fundamentals (~17 min, resumable)
    # → stores to Supabase `fundamentals` table; skips tickers already present

    # Test yfinance prices without Tiingo (fast iteration, survivorship bias)
    uv run python scripts/download_backtest_data.py --mode prices --skip-tiingo
    # → downloads price history in batches of 50; warns about delisted tickers

    # Full production run (requires TIINGO_API_KEY in .env)
    uv run python scripts/download_backtest_data.py --mode all
    # → fundamentals + yfinance prices + Tiingo fallback for delisted companies

    # Re-run is safe at any point — already-stored tickers are skipped:
    #   "Fundamentals: 127 to download, 373 already in DB."

Estimated runtime (first run):
    Fundamentals: ~17 minutes (500 tickers × 2s delay)
    Prices:        ~5 minutes (yfinance batches of 50)
    Tiingo:        variable (only tickers yfinance couldn't serve)
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import date

import psycopg
import yfinance as yf
import pandas as pd

from lockin.data.sp500_universe import get_sp500_tickers_at_date
from lockin.data.yfinance_source import YFinanceSource
from lockin.data.tiingo_source import TiingoSource
from lockin.data.storage import store_fundamentals

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BACKTEST_START = date(2009, 1, 1)
BACKTEST_END = date(2024, 12, 31)
DELAY_BETWEEN_TICKERS = 2.0   # seconds between yfinance fundamentals calls
PRICE_BATCH_SIZE = 50          # tickers per yfinance batch download
UPSERT_CHUNK = 1_000           # rows per Supabase upsert (payload limit)


# ---------------------------------------------------------------------------
# DB helpers — defined here until storage.py is extended with these functions
# ---------------------------------------------------------------------------

def _get_db_url() -> str:
    """Return DATABASE_URL from environment, or '' if not set."""
    return os.environ.get("DATABASE_URL", "")


def get_already_downloaded_tickers() -> set[str]:
    """Return tickers that already have fundamentals in the database.

    Enables resumable downloads: skips tickers already stored so a re-run
    after interruption picks up where it left off rather than re-downloading
    500 companies × 2 seconds from scratch.

    Returns an empty set (with a warning) if DATABASE_URL is not set or the
    DB is unreachable — the download will proceed from scratch in that case.
    """
    db_url = _get_db_url()
    if not db_url:
        log.warning(
            "DATABASE_URL not set — cannot check already-downloaded tickers. "
            "Will re-download all."
        )
        return set()
    try:
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT ticker FROM fundamentals")
                return {row[0] for row in cur.fetchall()}
    except Exception as exc:
        log.warning(
            f"Could not query already-downloaded tickers: {exc}. Will re-download all."
        )
        return set()


def _store_prices_rows(rows: list[dict]) -> None:
    """Upsert a flat list of price rows into the daily_prices table."""
    db_url = _get_db_url()
    if not db_url or not rows:
        return
    try:
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                for i in range(0, len(rows), UPSERT_CHUNK):
                    cur.executemany(
                        """
                        INSERT INTO daily_prices (ticker, date, close, source)
                        VALUES (%(ticker)s, %(date)s, %(close)s, %(source)s)
                        ON CONFLICT (ticker, date) DO UPDATE
                            SET close = EXCLUDED.close,
                                source = EXCLUDED.source
                        """,
                        rows[i : i + UPSERT_CHUNK],
                    )
            conn.commit()
        log.info(f"  Stored {len(rows)} price rows.")
    except Exception as exc:
        log.warning(f"Failed to store price rows: {exc}")


def store_prices_batch(tickers: list[str], data: pd.DataFrame) -> None:
    """Upsert daily closing prices from a yfinance multi-ticker DataFrame.

    Parameters
    ----------
    tickers : list[str]
        Tickers to extract from the DataFrame.
    data : pd.DataFrame
        Multi-level DataFrame from yf.download() — columns are (price_type, ticker).
        Single-ticker DataFrames (flat columns) are also handled.
    """
    rows: list[dict] = []
    for ticker in tickers:
        try:
            # yf.download with multiple tickers → MultiIndex columns (price_type, ticker)
            # yf.download with a single ticker  → flat columns ('Close', 'Volume', ...)
            if isinstance(data.columns, pd.MultiIndex):
                close_col = ("Close", ticker)
                if close_col not in data.columns:
                    continue
                series = data[close_col].dropna()
            else:
                if "Close" not in data.columns:
                    continue
                series = data["Close"].dropna()

            for ts, price in series.items():
                rows.append({
                    "ticker": ticker,
                    "date": ts.date().isoformat(),
                    "close": float(price),
                    "source": "yfinance",
                })
        except Exception as exc:
            log.warning(f"  Failed to extract prices for {ticker}: {exc}")

    _store_prices_rows(rows)


def store_prices_from_tiingo(ticker: str, prices: dict[date, float]) -> None:
    """Upsert Tiingo price data for a single (typically delisted) ticker."""
    rows = [
        {"ticker": ticker, "date": d.isoformat(), "close": p, "source": "tiingo"}
        for d, p in prices.items()
    ]
    _store_prices_rows(rows)
    if rows:
        log.info(f"  Tiingo: stored {len(rows)} rows for {ticker}.")


# ---------------------------------------------------------------------------
# Download routines
# ---------------------------------------------------------------------------

def download_fundamentals(source: YFinanceSource, tickers: list[str]) -> None:
    """Download and store fundamentals for all tickers, skipping already-stored ones.

    Parameters
    ----------
    source : YFinanceSource
        Configured fundamentals source.
    tickers : list[str]
        Full universe of tickers to download.
    """
    already = get_already_downloaded_tickers()
    pending = [t for t in tickers if t not in already]
    log.info(
        f"Fundamentals: {len(pending)} to download, {len(already)} already in DB."
    )

    db_url = _get_db_url()
    for i, ticker in enumerate(pending):
        log.info(f"[{i + 1}/{len(pending)}] {ticker}")
        try:
            result = source.get_fundamentals(ticker)
            fiscal_year_end = result.get("fiscal_year_end")
            if not db_url:
                log.debug(f"  {ticker}: no DATABASE_URL — skipping storage.")
            elif fiscal_year_end is None:
                log.warning(f"  {ticker}: no fiscal_year_end — skipping storage.")
            else:
                store_fundamentals(db_url, ticker, result, fiscal_year_end)
        except Exception as exc:
            log.warning(f"  {ticker}: failed — {exc}")
        time.sleep(DELAY_BETWEEN_TICKERS)


def download_prices(tickers: list[str], tiingo: TiingoSource | None) -> None:
    """Download price history for all tickers.

    Tries yfinance first in batches of PRICE_BATCH_SIZE (fast, no rate limit
    for historical daily). Falls back to Tiingo for tickers where yfinance
    returns empty data — primarily delisted companies needed to avoid
    survivorship bias.

    SPY and TLT are always included as benchmark and bond-proxy series.

    Parameters
    ----------
    tickers : list[str]
        Universe of tickers to download.
    tiingo : TiingoSource | None
        Tiingo source for the delisted fallback. None when --skip-tiingo is set.
    """
    all_tickers = sorted(set(tickers) | {"SPY", "TLT"})
    log.info(
        f"Prices: downloading {len(all_tickers)} tickers "
        f"in batches of {PRICE_BATCH_SIZE}."
    )

    yfinance_empty: list[str] = []
    total_batches = (len(all_tickers) + PRICE_BATCH_SIZE - 1) // PRICE_BATCH_SIZE

    for i in range(0, len(all_tickers), PRICE_BATCH_SIZE):
        batch = all_tickers[i : i + PRICE_BATCH_SIZE]
        batch_num = i // PRICE_BATCH_SIZE + 1
        log.info(
            f"  yfinance batch {batch_num}/{total_batches}: "
            f"{batch[0]}–{batch[-1]}"
        )
        try:
            data = yf.download(
                tickers=batch,
                start=BACKTEST_START.isoformat(),
                end=BACKTEST_END.isoformat(),
                auto_adjust=True,
                progress=False,
            )
            # Detect tickers where yfinance returned all-NaN (delisted)
            for ticker in batch:
                col = ("Close", ticker)
                if (
                    not isinstance(data.columns, pd.MultiIndex)
                    or col not in data.columns
                    or data[col].dropna().empty
                ):
                    yfinance_empty.append(ticker)
            store_prices_batch(batch, data)
        except Exception as exc:
            log.warning(
                f"  Batch {batch_num} failed: {exc} — "
                "adding all to Tiingo fallback list."
            )
            yfinance_empty.extend(batch)

    if not yfinance_empty:
        log.info("All tickers had yfinance data — no Tiingo fallback needed.")
        return

    log.info(
        f"Tiingo fallback needed for {len(yfinance_empty)} tickers "
        "with no yfinance data."
    )

    if tiingo is None:
        log.warning(
            f"  --skip-tiingo set: skipping fallback for {len(yfinance_empty)} tickers. "
            "These will have no price data — survivorship bias risk. "
            "Add TIINGO_API_KEY to .env and re-run without --skip-tiingo."
        )
        return

    for ticker in yfinance_empty:
        log.info(f"  Tiingo: {ticker}")
        try:
            prices = tiingo.get_closing_prices(ticker, BACKTEST_START, BACKTEST_END)
            if prices:
                store_prices_from_tiingo(ticker, prices)
            else:
                log.warning(
                    f"  {ticker}: no data from Tiingo either — "
                    "ticker truly unavailable."
                )
        except Exception as exc:
            log.warning(f"  Tiingo failed for {ticker}: {exc}")


# ---------------------------------------------------------------------------
# Universe construction
# ---------------------------------------------------------------------------

def build_universe() -> list[str]:
    """Return all unique tickers that ever appeared in the S&P 500 (2010–2024).

    Sampled at quarterly frequency (Jan/Apr/Jul/Oct) to capture all additions
    and deletions without processing every single calendar day.
    """
    all_tickers: set[str] = set()
    for year in range(2010, 2025):
        for month in (1, 4, 7, 10):
            try:
                all_tickers.update(get_sp500_tickers_at_date(date(year, month, 1)))
            except ValueError:
                pass  # date before first CSV row — skip
    return sorted(all_tickers)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Bulk download backtest data (fundamentals + prices) "
            "for the full S&P 500 historical universe."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["fundamentals", "prices", "all"],
        default="all",
        help="What to download. Default: all.",
    )
    parser.add_argument(
        "--skip-tiingo",
        action="store_true",
        help=(
            "Skip Tiingo fallback for delisted tickers. "
            "Use this for initial testing when TIINGO_API_KEY is not yet configured. "
            "WARNING: results will have survivorship bias — "
            "re-run without this flag before the final backtest."
        ),
    )
    args = parser.parse_args()

    log.info("Building S&P 500 historical universe (2010–2024)...")
    universe = build_universe()
    log.info(f"Total unique tickers across all quarters: {len(universe)}")

    yf_source = YFinanceSource()

    # Tiingo: loud failure if key is missing (unless --skip-tiingo was passed)
    tiingo: TiingoSource | None = None
    if not args.skip_tiingo:
        # TiingoSource.__init__ raises ValueError with instructions if key missing
        tiingo = TiingoSource()
    else:
        log.warning(
            "--skip-tiingo: Tiingo fallback disabled. Delisted companies will have "
            "no price data (survivorship bias). Add TIINGO_API_KEY to .env and "
            "re-run without --skip-tiingo for the final backtest."
        )

    if args.mode in ("fundamentals", "all"):
        log.info("=== Phase 1: Fundamentals ===")
        download_fundamentals(yf_source, universe)

    if args.mode in ("prices", "all"):
        log.info("=== Phase 2: Prices ===")
        download_prices(universe, tiingo)

    log.info("Download complete.")


if __name__ == "__main__":
    main()
