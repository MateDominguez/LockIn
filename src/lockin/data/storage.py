"""
PostgreSQL storage functions for the LockIn data layer.

Provides three write functions:
  - store_fundamentals: upserts per-field rows into the fundamentals table
  - store_macro_data:   upserts per-indicator rows into the macro_data table
  - store_asset:        upserts a ticker record into the assets table

Design notes:
  - Each function opens a NEW short-lived psycopg.connect() — never share with
    the LangGraph checkpointer (which holds open transactions and can deadlock).
  - If database_url is empty, log to stderr and return (same pattern as audit.py).
  - Storage failures are caught and logged to stderr but never re-raised — a
    storage outage must not break the data fetch pipeline.
  - Data lineage columns (source, fetched_at, as_of_date) are stored on every row.
  - FRED_SERIES_IDS is duplicated here (not imported from fred_source.py) to
    avoid circular imports between the data source and storage modules.
"""

from __future__ import annotations

import sys
from datetime import date

import psycopg

from lockin.data.types import FundamentalsResult, MacroResult


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Maps MacroResult field names → FRED series IDs.
# Duplicated from fred_source.py to avoid circular imports.
FRED_SERIES_IDS: dict[str, str] = {
    "gdp": "GDP",
    "cpi": "CPIAUCSL",
    "core_pce": "PCEPILFE",
    "fed_funds": "FEDFUNDS",
    "yield_10y_2y": "T10Y2Y",
    "yield_10y_3m": "T10Y3M",
    "unemployment": "UNRATE",
}

# Financial fields from FundamentalsResult to persist.
FINANCIAL_FIELDS: list[str] = [
    "total_revenue",
    "net_income",
    "gross_profit",
    "operating_income",
    "ebitda",
    "diluted_eps",
    "free_cash_flow",
    "total_assets",
    "total_debt",
    "cash_and_equivalents",
    "total_equity",
]


# ---------------------------------------------------------------------------
# Public storage functions
# ---------------------------------------------------------------------------


def store_fundamentals(
    database_url: str,
    ticker: str,
    data: FundamentalsResult,
    fiscal_year_end: date,
    period: str = "annual",
) -> None:
    """Upsert fundamental financial data rows for a single ticker.

    One row is written per field in FINANCIAL_FIELDS (if the field is not None).
    The UNIQUE constraint on (ticker, fiscal_year_end, period, field_name) ensures
    idempotent writes — re-fetching the same period updates the value and metadata.

    Args:
        database_url: PostgreSQL connection string. If empty, logs and returns.
        ticker:       Stock ticker symbol (e.g. "AAPL").
        data:         FundamentalsResult dict returned by a DataSourceProtocol.
        fiscal_year_end: Date of the fiscal year end for this report period.
        period:       Reporting period label, default "annual".
    """
    if not database_url:
        print(
            "store_fundamentals skipped: no DATABASE_URL",
            file=sys.stderr,
        )
        return

    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                for field in FINANCIAL_FIELDS:
                    value = data.get(field)  # type: ignore[literal-required]
                    if value is None:
                        continue
                    cur.execute(
                        """
                        INSERT INTO fundamentals
                            (ticker, fiscal_year_end, period, field_name,
                             value, source, fetched_at, as_of_date)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (ticker, fiscal_year_end, period, field_name)
                        DO UPDATE SET
                            value      = EXCLUDED.value,
                            fetched_at = EXCLUDED.fetched_at,
                            as_of_date = EXCLUDED.as_of_date;
                        """,
                        (
                            ticker,
                            fiscal_year_end,
                            period,
                            field,
                            float(value),
                            data.get("source", "yfinance"),  # type: ignore[typeddict-item]
                            data.get("fetched_at"),           # type: ignore[typeddict-item]
                            data.get("as_of_date"),           # type: ignore[typeddict-item]
                        ),
                    )
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        print(
            f"store_fundamentals error for {ticker}: {exc}",
            file=sys.stderr,
        )


def store_macro_data(database_url: str, data: MacroResult) -> None:
    """Upsert macro indicator rows from a MacroResult snapshot.

    One row is written per indicator in FRED_SERIES_IDS (if the field is not None).
    The UNIQUE constraint on (indicator) means there is always exactly one row per
    indicator — each call updates the latest value and metadata.

    Args:
        database_url: PostgreSQL connection string. If empty, logs and returns.
        data:         MacroResult dict returned by a MacroSourceProtocol.
    """
    if not database_url:
        print(
            "store_macro_data skipped: no DATABASE_URL",
            file=sys.stderr,
        )
        return

    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                for indicator, series_id in FRED_SERIES_IDS.items():
                    value = data.get(indicator)  # type: ignore[literal-required]
                    if value is None:
                        continue
                    cur.execute(
                        """
                        INSERT INTO macro_data
                            (indicator, series_id, value, observation_date,
                             source, fetched_at, as_of_date)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (indicator) DO UPDATE SET
                            value            = EXCLUDED.value,
                            series_id        = EXCLUDED.series_id,
                            fetched_at       = EXCLUDED.fetched_at,
                            as_of_date       = EXCLUDED.as_of_date;
                        """,
                        (
                            indicator,
                            series_id,
                            float(value),
                            None,  # observation_date not yet captured from FRED response
                            data.get("source", "fred"),    # type: ignore[typeddict-item]
                            data.get("fetched_at"),        # type: ignore[typeddict-item]
                            data.get("as_of_date"),        # type: ignore[typeddict-item]
                        ),
                    )
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        print(
            f"store_macro_data error: {exc}",
            file=sys.stderr,
        )


def store_asset(
    database_url: str,
    ticker: str,
    name: str | None = None,
    sector: str | None = None,
    exchange: str | None = None,
) -> None:
    """Upsert a ticker record in the assets registry table.

    Uses COALESCE on update so existing non-null values are never overwritten
    by a NULL from a partial update.

    Args:
        database_url: PostgreSQL connection string. If empty, logs and returns.
        ticker:       Stock ticker symbol (e.g. "AAPL").
        name:         Company name (optional).
        sector:       GICS sector (optional).
        exchange:     Exchange name, e.g. "NASDAQ" (optional).
    """
    if not database_url:
        print(
            "store_asset skipped: no DATABASE_URL",
            file=sys.stderr,
        )
        return

    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO assets (ticker, name, sector, exchange)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (ticker) DO UPDATE SET
                        name     = COALESCE(EXCLUDED.name,     assets.name),
                        sector   = COALESCE(EXCLUDED.sector,   assets.sector),
                        exchange = COALESCE(EXCLUDED.exchange,  assets.exchange);
                    """,
                    (ticker, name, sector, exchange),
                )
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        print(
            f"store_asset error for {ticker}: {exc}",
            file=sys.stderr,
        )
