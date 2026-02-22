# Phase 2: Data Layer - Research

**Researched:** 2026-02-22
**Domain:** Financial data pipelines — yfinance, fredapi, point-in-time access, PostgreSQL storage
**Confidence:** HIGH (core APIs verified via official docs and GitHub source; patterns verified)

---

## Summary

Phase 2 builds the data foundation that agents call at analysis time. Three technical areas require
research: (1) the yfinance and fredapi library APIs, (2) point-in-time access pattern to prevent
look-ahead bias, and (3) the PostgreSQL schema for lazy-stored fundamentals and macro snapshots.

All three primary libraries (`yfinance>=0.2.50`, `fredapi>=0.5.2`, `psycopg[binary]>=3.1.0`) are
already declared in `pyproject.toml` from Phase 1. No new dependencies are needed. The
`get_settings()` function already exposes `fred_api_key` and `database_url`. The `audit_logs`
infrastructure is in place; data validation warnings that cross HITL thresholds write there.

The most important finding is that **fredapi has native `get_series_as_of_date()`** which provides
real point-in-time macro data retrieval via ALFRED vintage dates — use it directly rather than
building a custom filter. For yfinance, point-in-time for fundamentals must be implemented
manually (filter DataFrame columns to `<= as_of_date + 7d tolerance`). yfinance has **active rate
limiting issues in 2025/2026** (YFRateLimitError); the 24-hour TTL caching layer is essential, not
optional.

**Primary recommendation:** Use `typing.Protocol` for the source-agnostic wrapper interface
(structural subtyping, no inheritance required for yfinance/fredapi backends). Implement TTL cache
as a simple dict with `(ticker, date)` keys and `(data, fetched_at)` values — no external cache
library needed for a 2-week phase.

---

## Standard Stack

### Core (already in pyproject.toml — no new installs)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| yfinance | >=0.2.50 | Stock prices, income_stmt, balance_sheet, cashflow | De-facto standard for Yahoo Finance data in Python |
| fredapi | >=0.5.2 | FRED macro series; ALFRED vintage/point-in-time | Official Python client for Federal Reserve FRED API |
| psycopg[binary] | >=3.1.0 | PostgreSQL writes for fundamentals + macro tables | Already used for audit_logs in Phase 1 |
| pandas | >=2.2.0 | yfinance returns DataFrames; fredapi returns Series | Already in stack |
| tenacity | >=9.0.0 | Retry with exponential backoff on YFRateLimitError | Already in stack |

### No new dependencies needed

All required libraries are already declared. Phase 2 adds **modules**, not packages.

**Verification:** `pyproject.toml` lines confirmed: yfinance, fredapi, pandas, psycopg[binary], tenacity all present.

---

## Architecture Patterns

### Recommended Module Structure

```
src/lockin/data/
├── __init__.py              # Public API: get_fundamentals, get_macro_indicators
├── protocols.py             # DataSourceProtocol, MacroSourceProtocol (typing.Protocol)
├── yfinance_source.py       # YFinanceSource: implements DataSourceProtocol
├── fred_source.py           # FREDSource: implements MacroSourceProtocol
├── point_in_time.py         # PointInTimeData class
├── validator.py             # DataValidator class
├── cache.py                 # TTLCache: simple dict-based, no external dependency
├── storage.py               # PostgreSQL writes: fundamentals table, macro_data table
├── types.py                 # TypedDicts: FundamentalsResult, MacroResult, ValidationResult
└── exceptions.py            # DataUnavailableError, LookAheadError

scripts/
└── setup_data_tables.py     # New: CREATE TABLE IF NOT EXISTS for fundamentals, macro_data
```

### Pattern 1: Protocol-Based Source Abstraction

**What:** `typing.Protocol` (structural subtyping) lets yfinance and future Alpha Vantage
implement the same interface without inheriting from a base class.

**When to use:** This is the locked decision — agents call `DataSourceProtocol`, never `yf.Ticker`
directly.

```python
# Source: typing.python.org/en/latest/spec/protocol.html
from typing import Protocol, runtime_checkable
from datetime import date
from lockin.data.types import FundamentalsResult, MacroResult

@runtime_checkable
class DataSourceProtocol(Protocol):
    def get_fundamentals(self, ticker: str, as_of_date: date | None = None) -> FundamentalsResult:
        ...

@runtime_checkable
class MacroSourceProtocol(Protocol):
    def get_macro_indicators(self, as_of_date: date | None = None) -> MacroResult:
        ...
```

### Pattern 2: yfinance Fundamentals Access

**What:** `yf.Ticker` attributes return annual DataFrames with dates as column headers.
Point-in-time is enforced by filtering columns `<= as_of_date + 7d tolerance`.

**Key attributes (verified against yfinance GitHub source):**
- `ticker.income_stmt` — annual income statement (TotalRevenue, NetIncome, GrossProfit,
  OperatingIncome, EBITDA, DilutedEPS, FreeCashFlow)
- `ticker.balance_sheet` — annual balance sheet (TotalAssets, TotalLiabilities, TotalEquity,
  TotalDebt, CashAndCashEquivalents, AccountsReceivable, Inventory)
- `ticker.cashflow` — annual cash flow (OperatingCashFlow, CapitalExpenditure, FreeCashFlow)
- `ticker.quarterly_income_stmt` — quarterly variant (same fields, 4 columns instead of 4 years)
- `ticker.info` — dict with market cap, P/E, sector, etc. (live, no date filtering)

```python
# Source: ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.html
import yfinance as yf

ticker = yf.Ticker("AAPL")

# Annual income statement — DataFrame with dates as columns
income = ticker.income_stmt          # index=field_name, columns=fiscal_year_dates
balance = ticker.balance_sheet
cashflow = ticker.cashflow

# Access a specific field across all available years:
net_income_series = income.loc["NetIncome"]   # pandas Series, indexed by date

# For point-in-time: filter columns to dates <= as_of_date + tolerance
def _filter_as_of(df: pd.DataFrame, cutoff: date) -> pd.DataFrame:
    valid_cols = [c for c in df.columns if pd.Timestamp(c).date() <= cutoff]
    return df[valid_cols] if valid_cols else df.iloc[:, :0]  # empty if no valid
```

### Pattern 3: fredapi Point-in-Time Access

**What:** fredapi has native `get_series_as_of_date()` via ALFRED vintage dates. Use this
directly for macro data — no manual filtering needed.

```python
# Source: github.com/mortada/fredapi/blob/master/README.md
from fredapi import Fred
from datetime import date

fred = Fred(api_key="...")

# Latest data (for live analysis):
gdp = fred.get_series("GDP")

# Point-in-time (for backtesting as_of_date):
gdp_as_of = fred.get_series_as_of_date("GDP", "2023-06-01")
# Returns DataFrame with realtime_start/realtime_end cols

# First release only (avoids revision look-ahead):
gdp_first = fred.get_series_first_release("GDP")
```

**FRED series IDs for required macro indicators (verified via fred.stlouisfed.org):**

| Indicator | Series ID | Frequency | Notes |
|-----------|-----------|-----------|-------|
| GDP | `GDP` | Quarterly | Nominal GDP |
| CPI Inflation | `CPIAUCSL` | Monthly | All Urban Consumers |
| Core PCE | `PCEPILFE` | Monthly | Fed's preferred inflation measure |
| Federal Funds Rate | `FEDFUNDS` | Monthly | Effective rate |
| 10Y-2Y Yield Spread | `T10Y2Y` | Daily | Yield curve inversion signal |
| 10Y-3M Yield Spread | `T10Y3M` | Daily | Alternative inversion indicator |
| Unemployment Rate | `UNRATE` | Monthly | Standard macro indicator |
| ISM Manufacturing PMI | `MANEMP` + search | Monthly | FRED hosts NAPM-derived series; verify exact ID at runtime via `fred.search("ISM Manufacturing")` |

**Note on PMI:** ISM Manufacturing PMI composite series exists in FRED but the exact series ID
could not be confirmed as a single authoritative string from public docs. Recommend using
`fred.search("manufacturing pmi")` at initialization to identify the correct current ID, or use
`MANEMP` (manufacturing employment) as a proxy if PMI series is unavailable.

### Pattern 4: TTL Cache (no external dependency)

**What:** Simple dict with `(ticker, date_bucket)` key; stores `(result, fetched_at)` tuple.
TTL checked at read time.

```python
# Simple in-process TTL cache
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Any

@dataclass
class CacheEntry:
    data: Any
    fetched_at: datetime

class TTLCache:
    def __init__(self):
        self._store: dict[str, CacheEntry] = {}

    def get(self, key: str, ttl_seconds: int) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        age = (datetime.now(timezone.utc) - entry.fetched_at).total_seconds()
        if age > ttl_seconds:
            return None  # Expired; caller decides stale vs. re-fetch
        return entry.data

    def set(self, key: str, data: Any) -> None:
        self._store[key] = CacheEntry(data=data, fetched_at=datetime.now(timezone.utc))
```

### Pattern 5: PointInTimeData Class

**What:** Enforces as_of_date contract. Live analysis (as_of_date=today) bypasses enforcement.
Future dates raise ValueError immediately.

```python
from datetime import date, timedelta
from lockin.data.exceptions import LookAheadError

LOOKAHEAD_DAYS = {
    "prices": 0,
    "fundamentals": 7,
    "macro": 14,
}

class PointInTimeData:
    def __init__(self, source: DataSourceProtocol, macro: MacroSourceProtocol):
        self._source = source
        self._macro = macro

    def get_data_as_of(self, ticker: str, as_of_date: date, data_type: str = "fundamentals"):
        today = date.today()
        if as_of_date > today:
            raise ValueError(f"as_of_date {as_of_date} is in the future (today={today})")
        # Live analysis: bypass point-in-time enforcement
        if as_of_date == today:
            return self._source.get_fundamentals(ticker, as_of_date=None)
        # Historical: apply lookahead tolerance
        cutoff = as_of_date + timedelta(days=LOOKAHEAD_DAYS[data_type])
        return self._source.get_fundamentals(ticker, as_of_date=cutoff)
```

### Pattern 6: Tenacity Retry for Rate Limits

**What:** yfinance raises `YFRateLimitError` (HTTP 429). Wrap all yfinance calls with tenacity.

```python
# Source: tenacity.readthedocs.io
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import yfinance as yf

@retry(
    retry=retry_if_exception_type(Exception),  # YFRateLimitError is a subclass of Exception
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
)
def _fetch_ticker_data(ticker_sym: str) -> yf.Ticker:
    return yf.Ticker(ticker_sym)
```

### Pattern 7: PostgreSQL UPSERT for Storage

**What:** Use `INSERT ... ON CONFLICT DO UPDATE` for idempotent upserts. Separate connection
from LangGraph checkpointer (same pattern as audit_logs in Phase 1).

```python
# Source: psycopg3 docs + audit.py Phase 1 pattern
import psycopg
from datetime import datetime, timezone

UPSERT_FUNDAMENTALS = """
INSERT INTO fundamentals
    (ticker, fiscal_year_end, period, field_name, value,
     source, fetched_at, as_of_date)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (ticker, fiscal_year_end, period, field_name)
DO UPDATE SET
    value = EXCLUDED.value,
    fetched_at = EXCLUDED.fetched_at,
    as_of_date = EXCLUDED.as_of_date;
"""

def store_fundamentals(database_url: str, ticker: str, data: dict, as_of_date) -> None:
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            for row in data["rows"]:
                cur.execute(UPSERT_FUNDAMENTALS, row)
        conn.commit()
```

### Anti-Patterns to Avoid

- **Importing `yf.Ticker` directly in agent files:** Agents must call `DataSourceProtocol`,
  never yfinance. Violates the abstraction decision.
- **Storing prices in PostgreSQL:** Phase 2 decision is live-only for prices. No `prices` table.
- **Using `ticker.financials` (old API):** This attribute is deprecated and returns empty
  DataFrames. Use `ticker.income_stmt`, `ticker.balance_sheet`, `ticker.cashflow`.
- **Global `TTLCache` singleton:** Use instance injection so tests can inject a fresh cache.
- **`as_of_date` enforcement in live-analysis path:** When `as_of_date == date.today()`, bypass
  all date filtering entirely — fetch latest.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| FRED point-in-time access | Custom vintage date filtering | `fred.get_series_as_of_date()` | ALFRED API native; handles realtime_start/end correctly |
| HTTP retry logic | Custom `while True` retry | `tenacity` (`@retry` decorator) | Already in pyproject.toml; handles jitter, backoff, max attempts |
| FRED series fetching | Direct HTTP to api.stlouisfed.org | `fredapi.Fred.get_series()` | Handles auth, pagination, pandas conversion |
| yfinance session management | Custom requests.Session | Default (or `curl_cffi` if 429s become frequent) | curl_cffi impersonates browser TLS fingerprint — resolves persistent 429 blocks |
| DataFrame field extraction | Writing field parsers | `df.loc["FieldName"]` with `.get()` fallback | yfinance row indices match `fundamentals_keys` constants from const.py |

**Key insight:** FRED's ALFRED archive is the correct solution for macro point-in-time. It stores
every revision with `realtime_start` / `realtime_end` dates. `get_series_as_of_date()` wraps this
cleanly. Don't replicate it.

---

## Common Pitfalls

### Pitfall 1: YFRateLimitError on Repeated Fetches

**What goes wrong:** yfinance throws `YFRateLimitError: Too Many Requests` after ~50-100 requests
in rapid succession, or even on first request during certain IP/time conditions.

**Why it happens:** Yahoo Finance implemented TLS fingerprinting detection in 2024. Standard Python
`requests.Session` is blocked; browser impersonation or delays are needed. Rate limits are
per-IP, not per-API-key (no auth key for yfinance).

**How to avoid:**
1. The 24-hour TTL cache is the primary mitigation — most repeat requests are cache hits.
2. Wrap all `yf.Ticker()` and `.history()` calls with tenacity `@retry(wait=wait_exponential(...))`.
3. If persistent 429s occur: `from curl_cffi import requests as cffi_requests; session = cffi_requests.Session(impersonate="chrome"); yf.Ticker(sym, session=session)`.

**Warning signs:** CI tests suddenly failing with HTTP 429; local dev working but deployment failing.

### Pitfall 2: Deprecated yfinance Attributes

**What goes wrong:** `ticker.financials`, `ticker.quarterly_earnings` return empty DataFrames
without error in recent yfinance versions.

**Why it happens:** Yahoo Finance changed their API; yfinance deprecated old attributes silently.

**How to avoid:** Use ONLY the non-deprecated attributes:
- `ticker.income_stmt` (NOT `ticker.financials`)
- `ticker.balance_sheet` (OK, not deprecated)
- `ticker.cashflow` (OK, not deprecated)
- DO NOT use `ticker.earnings` or `ticker.quarterly_earnings`

**Warning signs:** Empty DataFrame returned; no exception raised.

### Pitfall 3: Look-Ahead Bias from Wrong Column Filtering

**What goes wrong:** Annual financial statements have 4 columns (4 fiscal years). If you take
`df.iloc[:, 0]` (most recent), you include data published AFTER `as_of_date`.

**Why it happens:** yfinance always returns the latest 4 annual reports. The most recent
column may be a 10-K filed AFTER your `as_of_date`.

**How to avoid:** Filter DataFrame columns by date, not by position index:
```python
valid_cols = [c for c in df.columns if pd.Timestamp(c).date() <= cutoff_date]
```
Always apply the 7-day lookahead tolerance for fundamentals to account for filing delays.

**Warning signs:** Backtests show suspiciously good performance on fundamental factors;
PointInTimeData returning more data than expected for old as_of_dates.

### Pitfall 4: FRED Data Revisions Without Vintage Access

**What goes wrong:** `fred.get_series("GDP")` always returns the LATEST revised values, not the
values known on a past date. GDP is revised 3 times (advance, second, final estimate) over 3+ months.

**Why it happens:** FRED's default API returns current best estimates. ALFRED (Archival FRED)
stores the revision history.

**How to avoid:** Use `fred.get_series_as_of_date("GDP", as_of_date_str)` for backtesting paths.
Only use `fred.get_series("GDP")` for live analysis (as_of_date == today).

**Warning signs:** Backtesting macro signals are too good; GDP values in historical runs match
current revised figures, not original announcements.

### Pitfall 5: Psycopg3 Connection Sharing with LangGraph Checkpointer

**What goes wrong:** Using the same PostgreSQL connection as LangGraph's PostgresSaver for data
writes causes deadlocks or transaction conflicts.

**Why it happens:** LangGraph's PostgresSaver holds an open transaction. Inserting data inside
that same connection corrupts checkpoint state.

**How to avoid:** Open a NEW short-lived `psycopg.connect()` for every fundamentals/macro write.
This is the identical pattern already established in `lockin/utils/audit.py`.

**Warning signs:** `psycopg.errors.InFailedSqlTransaction` during data writes; checkpoint reads
returning stale data after agent runs.

### Pitfall 6: Cold-Start Cache Miss + Source Down

**What goes wrong:** On first run with no cached data and yfinance returning 429 or FRED down,
the pipeline tries to invoke agents with `None` data.

**Why it happens:** No fallback to stale cache exists when there's no cache at all.

**How to avoid:** On cold-start failure, raise `DataUnavailableError`. This is the locked decision
— skip the ticker, log the failure, let the pipeline continue for other tickers. Do NOT return
`None` silently.

---

## Code Examples

Verified patterns from official sources:

### yfinance: Full Fundamentals Fetch with Point-in-Time Filter

```python
# Source: ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.html
# Source: github.com/ranaroussi/yfinance/blob/main/yfinance/scrapers/fundamentals.py
import yfinance as yf
import pandas as pd
from datetime import date, timedelta

FUNDAMENTALS_TOLERANCE_DAYS = 7

def get_fundamentals_raw(ticker_sym: str, as_of_date: date | None) -> dict:
    """Fetch and filter fundamentals to point-in-time cutoff."""
    ticker = yf.Ticker(ticker_sym)

    # Fetch the three financial statements (annual)
    income = ticker.income_stmt       # NOT ticker.financials (deprecated)
    balance = ticker.balance_sheet
    cashflow = ticker.cashflow

    if as_of_date is not None and as_of_date != date.today():
        cutoff = as_of_date + timedelta(days=FUNDAMENTALS_TOLERANCE_DAYS)
        income  = _filter_columns_as_of(income,  cutoff)
        balance = _filter_columns_as_of(balance, cutoff)
        cashflow = _filter_columns_as_of(cashflow, cutoff)

    return {
        "income":   income,
        "balance":  balance,
        "cashflow": cashflow,
        "info":     ticker.info,   # live metadata: market cap, sector
    }

def _filter_columns_as_of(df: pd.DataFrame, cutoff: date) -> pd.DataFrame:
    """Return only columns with fiscal year end <= cutoff date."""
    valid = [c for c in df.columns if pd.Timestamp(c).date() <= cutoff]
    return df[valid]
```

### fredapi: Macro Indicators Fetch

```python
# Source: github.com/mortada/fredapi/blob/master/README.md
from fredapi import Fred
from datetime import date

FRED_SERIES = {
    "gdp":           "GDP",
    "cpi":           "CPIAUCSL",
    "core_pce":      "PCEPILFE",
    "fed_funds":     "FEDFUNDS",
    "yield_10y_2y":  "T10Y2Y",
    "yield_10y_3m":  "T10Y3M",
    "unemployment":  "UNRATE",
}

def get_macro_indicators_raw(fred: Fred, as_of_date: date | None) -> dict:
    result = {}
    for name, series_id in FRED_SERIES.items():
        if as_of_date is None or as_of_date == date.today():
            s = fred.get_series(series_id)
            result[name] = float(s.dropna().iloc[-1]) if not s.empty else None
        else:
            # ALFRED point-in-time: what was known on as_of_date
            df = fred.get_series_as_of_date(series_id, str(as_of_date))
            if df is not None and not df.empty:
                result[name] = float(df["value"].iloc[-1])
            else:
                result[name] = None
    return result
```

### TypedDict Return Types

```python
# Source: project convention from Phase 1 (InvestmentState pattern)
from typing import TypedDict
from datetime import datetime

class FundamentalsResult(TypedDict, total=False):
    ticker: str
    # Income statement
    total_revenue: float | None
    net_income: float | None
    gross_profit: float | None
    operating_income: float | None
    ebitda: float | None
    diluted_eps: float | None
    free_cash_flow: float | None
    # Balance sheet
    total_assets: float | None
    total_debt: float | None
    cash_and_equivalents: float | None
    total_equity: float | None
    # Metadata (data lineage)
    source: str              # "yfinance"
    fetched_at: datetime
    as_of_date: str          # ISO date string or "live"
    missing_fields: list[str]
    outlier_flags: dict[str, bool]
    data_freshness: str      # "FRESH" | "STALE"

class MacroResult(TypedDict, total=False):
    gdp: float | None
    cpi: float | None
    core_pce: float | None
    fed_funds: float | None
    yield_10y_2y: float | None
    yield_10y_3m: float | None
    unemployment: float | None
    # Metadata
    source: str              # "fred"
    fetched_at: datetime
    as_of_date: str
    data_freshness: str      # "FRESH" | "STALE"
```

### PostgreSQL Schema (new tables for Phase 2)

```sql
-- Run via scripts/setup_data_tables.py (new script, Phase 2)

-- Fundamentals: lazy storage for analyzed tickers
-- One row per (ticker, fiscal_year_end, period, field_name)
CREATE TABLE IF NOT EXISTS fundamentals (
    id              BIGSERIAL PRIMARY KEY,
    ticker          TEXT NOT NULL,
    fiscal_year_end DATE NOT NULL,
    period          TEXT NOT NULL,          -- 'annual' | 'quarterly'
    field_name      TEXT NOT NULL,          -- 'net_income', 'total_assets', etc.
    value           DOUBLE PRECISION,
    -- Data lineage (one column per row, no separate table)
    source          TEXT NOT NULL DEFAULT 'yfinance',
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    as_of_date      DATE,                   -- NULL means live fetch
    UNIQUE(ticker, fiscal_year_end, period, field_name)
);

CREATE INDEX IF NOT EXISTS fundamentals_ticker_idx ON fundamentals(ticker);
CREATE INDEX IF NOT EXISTS fundamentals_fetched_at_idx ON fundamentals(fetched_at DESC);

-- Macro data: current snapshot per indicator (not full time series in Phase 2)
-- One row per indicator, upserted on each refresh
CREATE TABLE IF NOT EXISTS macro_data (
    id              BIGSERIAL PRIMARY KEY,
    indicator       TEXT NOT NULL UNIQUE,   -- 'gdp', 'cpi', 'fed_funds', etc.
    series_id       TEXT NOT NULL,          -- 'GDP', 'CPIAUCSL', etc.
    value           DOUBLE PRECISION,
    observation_date DATE,                  -- date the value applies to
    -- Data lineage
    source          TEXT NOT NULL DEFAULT 'fred',
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    as_of_date      DATE,
    UNIQUE(indicator)                       -- one row per indicator, upserted
);

CREATE INDEX IF NOT EXISTS macro_data_fetched_at_idx ON macro_data(fetched_at DESC);
```

### DataValidator Pattern

```python
# Outlier detection per locked decision: 50-200% -> warning; >200% -> HITL
def validate_period_change(
    field: str,
    current: float | None,
    previous: float | None,
) -> tuple[bool, str]:
    """Returns (is_outlier, severity). severity: 'warning' | 'hitl'"""
    if current is None or previous is None or previous == 0:
        return False, ""
    change_pct = abs((current - previous) / previous) * 100
    if change_pct > 200:
        return True, "hitl"
    elif change_pct > 50:
        return True, "warning"
    return False, ""
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `ticker.financials` | `ticker.income_stmt` | yfinance ~0.2.x | Old attribute returns empty DataFrame silently |
| `ticker.quarterly_earnings` | `ticker.quarterly_income_stmt` | yfinance ~0.2.x | earnings deprecated |
| Raw `requests` session with yfinance | `curl_cffi` session if 429s persist | 2024 | Yahoo Finance added TLS fingerprinting |
| FRED latest-only data | ALFRED vintage via `get_series_as_of_date()` | fredapi 0.5+ | Native point-in-time for macro |

**Deprecated/outdated:**
- `ticker.financials`: returns empty DataFrame. Use `ticker.income_stmt`.
- `ticker.earnings`: returns None. Read Net Income from `ticker.income_stmt`.
- FRED API v1: v2 is now standard; fredapi handles this transparently.

---

## Open Questions

1. **ISM Manufacturing PMI series ID on FRED**
   - What we know: FRED hosts PMI-related series; series IDs BSCICP02USM460S (OECD confidence)
     exist but may not be canonical ISM PMI.
   - What's unclear: Whether ISM publishes PMI to FRED under a fixed series ID, or if the
     historical NAPM series (`NAPM`) is still active.
   - Recommendation: At implementation time, run `fred.search("ISM manufacturing PMI")` to
     find current series ID. Fallback: use `BSCICP02USM460S` (OECD manufacturing confidence)
     as a reasonable proxy. Document the chosen ID in `fred_source.py`.

2. **yfinance 429 severity in production**
   - What we know: YFRateLimitError is a real issue in 2025/2026; TTL cache + tenacity retry
     is the primary mitigation.
   - What's unclear: Whether Supabase-hosted deployment IP range triggers faster throttling than
     local dev.
   - Recommendation: Implement cache first; add `curl_cffi` as an optional session parameter
     in `YFinanceSource.__init__()` for easy activation if needed.

3. **fredapi `get_series_as_of_date()` return format**
   - What we know: Returns a DataFrame with value, realtime_start, realtime_end columns.
   - What's unclear: Whether it raises an exception or returns an empty DataFrame when no
     vintage data exists for the given as_of_date.
   - Recommendation: Wrap with try/except and check for empty DataFrame; return `None` for
     the value if no data available for that date.

---

## Sources

### Primary (HIGH confidence)

- yfinance GitHub: `github.com/ranaroussi/yfinance/blob/main/yfinance/scrapers/fundamentals.py`
  — confirmed `income_stmt`, `balance_sheet`, `cashflow` attributes; confirmed field names
  from `const.fundamentals_keys`
- yfinance API docs: `ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.html`
  — confirmed method signatures: `get_income_stmt(freq=)`, `get_balance_sheet(freq=)`, etc.
- fredapi README: `github.com/mortada/fredapi/blob/master/README.md`
  — confirmed `get_series()`, `get_series_as_of_date()`, `get_series_first_release()` methods
- FRED series IDs: `fred.stlouisfed.org/series/CPIAUCSL`, `/series/GDP`, `/series/PCEPILFE`
  — confirmed series IDs for CPI, GDP, Core PCE
- FRED yield curve: `fred.stlouisfed.org/tags/series?t=treasury%3Byield+curve`
  — confirmed `T10Y2Y` and `T10Y3M` series IDs

### Secondary (MEDIUM confidence)

- yfinance rate limit issues: GitHub issue #2422 (`github.com/ranaroussi/yfinance/issues/2422`)
  — `curl_cffi` workaround confirmed by community; TLS fingerprinting diagnosis plausible
- FRED rate limit ~120 req/min: multiple community sources agree; not found in official docs
- tenacity patterns: `tenacity.readthedocs.io` — `@retry`, `wait_exponential` confirmed

### Tertiary (LOW confidence)

- ISM PMI FRED series ID: search results inconclusive; needs runtime verification
- FRED `get_series_as_of_date()` return format on empty result: not confirmed from official docs

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in pyproject.toml; API methods verified via GitHub source
- Architecture: HIGH — Protocol pattern verified via python.org; yfinance/fredapi access patterns
  confirmed from official docs; Phase 1 psycopg connection pattern directly applicable
- Pitfalls: HIGH (yfinance 429, deprecated attributes, look-ahead bias) — verified via GitHub issues
  and source code; MEDIUM (FRED empty result handling) — not confirmed from official source
- FRED series IDs: HIGH for GDP/CPI/PCE/FEDFUNDS/T10Y2Y/T10Y3M/UNRATE; LOW for ISM PMI

**Research date:** 2026-02-22
**Valid until:** 2026-03-22 (stable libraries; yfinance rate limit landscape could shift sooner)
