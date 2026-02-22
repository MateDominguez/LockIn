---
phase: 02-data-layer
plan: 02
subsystem: data
tags: [yfinance, fredapi, tenacity, pandas, ttl-cache, point-in-time, ALFRED]

# Dependency graph
requires:
  - phase: 02-01
    provides: types.py (FundamentalsResult, MacroResult), protocols.py (DataSourceProtocol, MacroSourceProtocol), exceptions.py (DataUnavailableError), cache.py (TTLCache, TTL_FUNDAMENTALS, TTL_MACRO)

provides:
  - YFinanceSource class implementing DataSourceProtocol
  - FREDSource class implementing MacroSourceProtocol
  - Point-in-time fundamentals fetching with 7-day tolerance
  - ALFRED vintage date macro fetching (no revision look-ahead)
  - Tenacity retry (3 attempts, exponential backoff) for yfinance rate limits
  - Stale cache fallback for both sources

affects:
  - 02-03 (DataValidator — validates FundamentalsResult from YFinanceSource)
  - 02-05 (Storage — persists FundamentalsResult keyed by fiscal_year_end)
  - Phase 3 agents (MacroOracle, ValueHunter, BearAgent consume these sources)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Structural Protocol implementation — no inheritance needed, isinstance check works at runtime"
    - "Raw-data cache pattern — cache DataFrames not final results, apply PIT filter post-cache"
    - "fetched_at stored in raw cache dict — cached results preserve original fetch timestamp"
    - "Per-series try/except in FREDSource — individual series failure yields None, not total abort"
    - "ALFRED vintage dates — get_series_as_of_date() for historical, get_series() for live"

key-files:
  created:
    - src/lockin/data/yfinance_source.py
    - src/lockin/data/fred_source.py
  modified: []

key-decisions:
  - "Cache raw DataFrames (not FundamentalsResult) so point-in-time filtering applies post-cache for any requested date"
  - "Store fetched_at in raw cache dict so cached results preserve original timestamp (enables cache hit detection in tests)"
  - "yfinance field names are multi-word human-readable labels (e.g. 'Total Revenue', 'Free Cash Flow') not camelCase — verified against live API"
  - "NAPM series unavailable on FRED — manufacturing_pmi returns None gracefully (NAPM was moved/deleted from public FRED)"
  - "get_series_as_of_date() returns DataFrame with [realtime_start, date, value] columns — not a Series; must use df['value'].iloc[-1]"
  - "fiscal_year_end taken from income_stmt.columns[0] (most recent column after PIT filter) — balances sheet used as fallback"

patterns-established:
  - "Raw-data cache: cache upstream DataFrames, not processed results — enables same cache to serve multiple as_of_date queries"
  - "Graceful partial data: individual field failures append to missing_fields, never raise — partial data is better than no data"
  - "Stale cache fallback: on total failure, try get_stale() before raising DataUnavailableError"
  - "Verified field names against live API before coding — prevented silent empty fetch from wrong field names"

# Metrics
duration: 3min
completed: 2026-02-22
---

# Phase 2 Plan 02: YFinanceSource and FREDSource Summary

**YFinanceSource and FREDSource concrete data fetchers implementing the Protocol interfaces, with tenacity retry, TTL caching, ALFRED vintage dates, and point-in-time column filtering**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-02-22T18:35:51Z
- **Completed:** 2026-02-22T18:39:17Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- YFinanceSource fetches AAPL in one call: all 11 financial fields present, zero missing_fields
- FREDSource fetches 7/8 FRED series (NAPM unavailable but gracefully handled)
- Both sources implement stale cache fallback and raise DataUnavailableError only on total failure
- Point-in-time accuracy: historical queries filtered by column date + 7-day tolerance

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement YFinanceSource** - `1a56e84` (feat)
2. **Task 1 fix: fetched_at in cache dict** - `8095347` (fix — Rule 1 bug during verification)
3. **Task 2: Implement FREDSource** - `4d68f1a` (feat)

**Plan metadata:** (to be committed after SUMMARY.md creation)

## Files Created/Modified
- `src/lockin/data/yfinance_source.py` - YFinanceSource implementing DataSourceProtocol; fetches income_stmt, balance_sheet, cashflow with tenacity retry and TTL cache
- `src/lockin/data/fred_source.py` - FREDSource implementing MacroSourceProtocol; fetches 8 FRED macro series with ALFRED vintage dates for historical path

## Decisions Made

1. **Raw DataFrame cache**: Caching raw DataFrames (not FundamentalsResult) allows the same cache entry to answer queries for any `as_of_date` without re-fetching. Point-in-time filtering is applied post-cache on each call.

2. **fetched_at stored in raw cache dict**: After verification revealed that cached calls returned different `fetched_at` values (auto-fix Rule 1), we store `fetched_at` in the cached dict so all calls to the same ticker within TTL report the same original fetch timestamp.

3. **yfinance field names are multi-word labels**: Verified live against AAPL data before coding. Fields are "Total Revenue", "Free Cash Flow", "Stockholders Equity" etc. (not camelCase). The plan mentioned both formats — actual API uses multi-word.

4. **NAPM series not available**: FRED's NAPM (ISM Manufacturing PMI) series returns HTTP 400 "series does not exist". manufacturing_pmi returns None gracefully per the plan's design. This is not a bug — the series was moved or deleted from public FRED.

5. **get_series_as_of_date() returns DataFrame**: The fredapi method returns a DataFrame with `[realtime_start, date, value]` columns. The plan suggested `df["value"].iloc[-1]` which is correct after sorting by `date`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] fetched_at not preserved across cached calls**

- **Found during:** Task 1 (YFinanceSource) during full verification
- **Issue:** `fetched_at` was set to `datetime.now(timezone.utc)` at result-build time, so two calls within TTL returned different timestamps. The raw DataFrames were cached but the timestamp was recalculated each call.
- **Fix:** Added `"fetched_at": datetime.now(timezone.utc)` to the raw_data dict at cache-write time. Result-build uses `cached_raw.get("fetched_at", datetime.now(timezone.utc))` so cached results preserve the original timestamp. Falls back to now() for stale cache entries without the key.
- **Files modified:** `src/lockin/data/yfinance_source.py`
- **Verification:** `result1['fetched_at'] == result2['fetched_at']` assertion passes in verification suite
- **Committed in:** `8095347`

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Bug fix required for correctness. No scope creep.

## Issues Encountered

- **NAPM series unavailable on FRED**: The plan mentioned NAPM as the manufacturing_pmi series. It returns HTTP 400 "The series does not exist." on the current FRED API. The per-series try/except handles this correctly — manufacturing_pmi is None in all results. Not a code bug.

## User Setup Required

None - no external service configuration required beyond FRED_API_KEY already in .env.

## Next Phase Readiness

- YFinanceSource ready: agents can call `source.get_fundamentals(ticker)` or `source.get_fundamentals(ticker, as_of_date=date(2023, 1, 1))` for point-in-time queries
- FREDSource ready: MacroOracle agent can call `source.get_macro_indicators()` for live or historical macro snapshots
- Both sources handle partial data gracefully — validators (plan 02-03) can inspect missing_fields to compute quality_score
- fiscal_year_end populated from DataFrame column date — storage (plan 02-05) can key the fundamentals table correctly

---
*Phase: 02-data-layer*
*Completed: 2026-02-22*
