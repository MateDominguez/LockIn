"""
Data layer table setup script.

Creates:
- fundamentals table (financial data per ticker/fiscal_year_end/period/field)
- macro_data table (FRED macro indicators, one row per indicator)
- assets table (ticker registry)

Run once after setup_db.py:
    uv run python scripts/setup_data_tables.py
"""

import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
env_file = project_root / ".env"

if not env_file.exists():
    print("ERROR: .env file not found.")
    sys.exit(1)

from dotenv import load_dotenv
load_dotenv(env_file)

database_url = os.environ.get("DATABASE_URL")
if not database_url:
    print("ERROR: DATABASE_URL not set in .env")
    sys.exit(1)

print(f"Connecting to: {database_url[:50]}...")

import psycopg

# Create tables
print("\n[1/3] Creating fundamentals table...")
CREATE_FUNDAMENTALS = """
CREATE TABLE IF NOT EXISTS fundamentals (
    id              BIGSERIAL PRIMARY KEY,
    ticker          TEXT NOT NULL,
    fiscal_year_end DATE NOT NULL,
    period          TEXT NOT NULL,
    field_name      TEXT NOT NULL,
    value           DOUBLE PRECISION,
    source          TEXT NOT NULL DEFAULT 'yfinance',
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    as_of_date      DATE,
    UNIQUE(ticker, fiscal_year_end, period, field_name)
);
CREATE INDEX IF NOT EXISTS fundamentals_ticker_idx ON fundamentals(ticker);
CREATE INDEX IF NOT EXISTS fundamentals_fetched_at_idx ON fundamentals(fetched_at DESC);
"""
with psycopg.connect(database_url) as conn:
    with conn.cursor() as cur:
        cur.execute(CREATE_FUNDAMENTALS)
    conn.commit()
print("      OK — fundamentals table created")

print("\n[2/3] Creating macro_data table...")
CREATE_MACRO = """
CREATE TABLE IF NOT EXISTS macro_data (
    id              BIGSERIAL PRIMARY KEY,
    indicator       TEXT NOT NULL UNIQUE,
    series_id       TEXT NOT NULL,
    value           DOUBLE PRECISION,
    observation_date DATE,
    source          TEXT NOT NULL DEFAULT 'fred',
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    as_of_date      DATE
);
CREATE INDEX IF NOT EXISTS macro_data_fetched_at_idx ON macro_data(fetched_at DESC);
"""
with psycopg.connect(database_url) as conn:
    with conn.cursor() as cur:
        cur.execute(CREATE_MACRO)
    conn.commit()
print("      OK — macro_data table created")

print("\n[3/3] Creating assets table...")
CREATE_ASSETS = """
CREATE TABLE IF NOT EXISTS assets (
    id          BIGSERIAL PRIMARY KEY,
    ticker      TEXT NOT NULL UNIQUE,
    name        TEXT,
    sector      TEXT,
    exchange    TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS assets_ticker_idx ON assets(ticker);
"""
with psycopg.connect(database_url) as conn:
    with conn.cursor() as cur:
        cur.execute(CREATE_ASSETS)
    conn.commit()
print("      OK — assets table created")

print("\nData tables setup complete.")
