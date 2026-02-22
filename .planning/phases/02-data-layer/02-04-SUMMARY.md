---
phase: 02-data-layer
plan: 04
subsystem: data
tags: [python, point-in-time, public-api, validation, storage, integration-tests, pytest]

# Dependency graph
requires:
  - phase: 02-01
    provides: types.py, protocols.py, exceptions.py, cache.py
  - phase: 02-02
    provides: YFinanceSource, FREDSource concrete data fetchers
  - phase: 02-03
    provides: DataValidator, store_fundamentals, store_macro_data, store_asset

provides:
  - PointInTimeData wrapper with future date guard + live bypass
  - Public API: from lockin.data import get_fundamentals, get_macro_indicators
  - 12-symbol __all__ exposing all data layer types and protocols
  - Lazy-initialized singleton PIT + validator (no import-time network calls)
  - 15 mock-based integration tests covering the full pipeline

affects: [Phase 3 agents (MacroOracle, ValueHunter, Bear use get_fundamentals/get_macro_indicators)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "PointInTimeData thin wrapper: enforce date contract without duplicating PIT logic"
    - "Lazy module singletons: _default_pit + _default_validator initialized on first call"
    - "_NoMacroSource fallback: defers DataUnavailableError to call-time when FRED key absent"
    - "Storage non-fatal: try/except around all storage calls, log to stderr and continue"
    - "Validation metadata merged into FundamentalsResult (missing_fields, outlier_flags)"

key-files:
  created:
    - src/lockin/data/point_in_time.py
    - tests/integration/test_data_pipeline.py
  modified:
    - src/lockin/data/__init__.py

key-decisions:
  - "LOOKAHEAD_DAYS defined as module constant dict (prices=0, fundamentals=7, macro=14) for orchestration agents to reference"
  - "_NoMacroSource defers DataUnavailableError to call-time — importing lockin.data never crashes even without FRED_API_KEY"
  - "Live bypass calls source with as_of_date=None (not date.today()) — sources interpret None as 'latest available'"
  - "fiscal_year_end fallback: if not in result, use as_of_date or date.today() for storage key"
  - "store_asset called before store_fundamentals to satisfy foreign key dependency in assets table"

patterns-established:
  - "Public API pattern: agents import from lockin.data only, never from submodules"
  - "Lazy singleton: global None sentinels + _get_X() constructors called on first use"
  - "Non-fatal storage: wrap DB writes in try/except, print to stderr, always return data"
  - "Mock injection via constructor: PointInTimeData(source, macro) enables test isolation without patching"

# Metrics
duration: 2min
completed: 2026-02-22
---

# Phase 2 Plan 04: PointInTimeData Wrapper and Public API Summary

**PointInTimeData thin wrapper + lockin.data public API composing PIT enforcement, validation, and non-fatal lazy storage into two clean agent-facing functions**

## Performance

- **Duration:** ~2 minutes
- **Started:** 2026-02-22T18:43:39Z
- **Completed:** 2026-02-22T18:45:42Z
- **Tasks:** 3 completed
- **Files modified:** 3

## Accomplishments

- PointInTimeData class enforces future date guard (ValueError), live bypass (None/today calls source with None), and historical delegation to source's own PIT filter
- Public API `from lockin.data import get_fundamentals, get_macro_indicators` composes all data layer components transparently — agents never touch yfinance or FRED internals
- 15 mock-based integration tests passing, covering all pipeline stages without network access or API keys

## Task Commits

1. **Task 1: Implement PointInTimeData wrapper** - `0849558` (feat)
2. **Task 2: Wire public API in __init__.py** - `7767411` (feat)
3. **Task 3: Create integration tests for full data pipeline** - `acc0b1a` (test)

## Files Created/Modified

- `src/lockin/data/point_in_time.py` — PointInTimeData class with LOOKAHEAD_DAYS dict and _guard_future_date helper
- `src/lockin/data/__init__.py` — Public API with lazy singletons, _NoMacroSource fallback, get_fundamentals and get_macro_indicators functions
- `tests/integration/test_data_pipeline.py` — 15 tests across 5 classes testing the full pipeline with mock sources

## Decisions Made

- **Live bypass passes None to source:** When as_of_date is today or None, the source is called with `as_of_date=None` (not `date.today()`). Sources treat None as "latest available" — this is the documented contract. Passing today could confuse sources that don't apply PIT filters for None.
- **_NoMacroSource defers error to call-time:** Instead of raising DataUnavailableError at module import when FRED_API_KEY is absent, _NoMacroSource is substituted and raises only when get_macro_indicators() is actually called. This keeps module import cheap and non-crashing in any environment.
- **fiscal_year_end fallback chain:** If result["fiscal_year_end"] is None (yfinance couldn't determine it), we use `as_of_date or date.today()` as the storage key. This is a pragmatic fallback — better to store with an approximate date than to silently skip storage.
- **store_asset before store_fundamentals:** The assets table is a foreign key dependency for fundamentals. Calling store_asset first ensures the upsert chain always succeeds even for new tickers.
- **15 tests instead of 5:** The plan specified 5 tests but each mapped to a class with 2-4 sub-tests for better granularity and coverage.

## Deviations from Plan

**1. [Rule 2 - Missing Critical] Expanded test suite from 5 to 15 tests**

- **Found during:** Task 3 (integration test implementation)
- **Issue:** Plan specified 5 named tests, but each test scenario naturally decomposed into 2-4 assertions that are more useful as separate parameterized tests (e.g., "future date raises ValueError" and "future date message includes the date" are better as separate tests)
- **Fix:** Organized tests into 5 classes (matching the 5 plan scenarios) with 2-4 sub-tests each. All 15 tests pass.
- **Files modified:** tests/integration/test_data_pipeline.py
- **Verification:** `python -m pytest tests/integration/test_data_pipeline.py -v` → 15 passed
- **Committed in:** acc0b1a (Task 3 commit)

---

**Total deviations:** 1 auto-expanded (test granularity improvement)
**Impact on plan:** No scope change. Expanded test coverage maps 1:1 to the 5 plan scenarios. All 5 core behaviors verified as planned.

## Issues Encountered

None — plan executed cleanly. All imports, verification snippets, and test runs passed on first attempt.

## User Setup Required

None — no external service configuration required. Tests run without FRED API key or database.

## Next Phase Readiness

- Phase 2 complete. All 4 plans executed and committed.
- Phase 3 (Agents + RAG) can begin immediately.
- Agents import: `from lockin.data import get_fundamentals, get_macro_indicators`
- Type safety: All TypedDicts, protocols, and exceptions re-exported from `lockin.data`
- Backtest safety: PointInTimeData ensures no future dates leak into any analysis path

---
*Phase: 02-data-layer*
*Completed: 2026-02-22*
