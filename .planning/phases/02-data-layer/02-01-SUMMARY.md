---
phase: 02-data-layer
plan: 01
subsystem: database
tags: [typeddict, protocol, cache, ttl, exceptions, typing, data-layer]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: TypedDict total=False convention from InvestmentState, Python 3.12 project structure
provides:
  - FundamentalsResult TypedDict (19 fields: ticker, 7 income, 4 balance sheet, fiscal_year_end, 6 metadata)
  - MacroResult TypedDict (12 fields: 8 FRED indicators, 4 metadata)
  - ValidationResult TypedDict (5 fields: quality_score, missing_fields, outlier_flags, hitl_required, hitl_reason)
  - REQUIRED_FUNDAMENTAL_FIELDS list (7 fields for quality_score computation)
  - DataUnavailableError and LookAheadError custom exceptions
  - DataSourceProtocol and MacroSourceProtocol (runtime_checkable Protocol)
  - TTLCache with get/set/get_stale/clear and TTL_FUNDAMENTALS/TTL_MACRO constants
affects:
  - 02-02 (YFinanceSource implements DataSourceProtocol, returns FundamentalsResult)
  - 02-03 (FREDSource implements MacroSourceProtocol, returns MacroResult)
  - 02-04 (validator uses REQUIRED_FUNDAMENTAL_FIELDS, returns ValidationResult)
  - 02-05 (storage uses FundamentalsResult.fiscal_year_end as table key)
  - 03-agents (Value Hunter, Bear, Macro Oracle consume these types)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TypedDict total=False for all data layer result types (consistent with InvestmentState)"
    - "typing.Protocol + @runtime_checkable for structural subtyping (enables isinstance checks)"
    - "Instance-based TTLCache (not singleton) for test isolation"
    - "Exception attributes stored on instance (e.ticker, e.source, e.as_of_date, e.data_date)"

key-files:
  created:
    - src/lockin/data/types.py
    - src/lockin/data/exceptions.py
    - src/lockin/data/protocols.py
    - src/lockin/data/cache.py
  modified: []

key-decisions:
  - "FundamentalsResult includes fiscal_year_end: date | None — required by storage.py to key fundamentals table; None if not determinable"
  - "TTLCache is instance-based not a singleton — callers inject fresh cache for test isolation"
  - "Protocols are @runtime_checkable — enables isinstance(source, DataSourceProtocol) assertions in tests"
  - "DataUnavailableError carries ticker and source attributes for structured error handling"
  - "TTL_FUNDAMENTALS=86400s (24h), TTL_MACRO=604800s (7 days) match fundamental update frequency"

patterns-established:
  - "Protocol pattern: define interface in protocols.py, implement in source files, test with isinstance()"
  - "TTL cache: get() for TTL-aware access, get_stale() for graceful degradation fallback"
  - "Exception attributes: set in __init__ so callers can inspect e.ticker, e.source programmatically"

# Metrics
duration: 2min
completed: 2026-02-22
---

# Phase 2 Plan 01: Data Layer Foundation Summary

**FundamentalsResult/MacroResult TypedDicts, runtime_checkable DataSourceProtocol/MacroSourceProtocol, DataUnavailableError/LookAheadError exceptions, and TTLCache with stale fallback — zero external dependencies**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-22T18:29:18Z
- **Completed:** 2026-02-22T18:31:17Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Four TypedDicts (FundamentalsResult 19 fields, MacroResult 12 fields, ValidationResult 5 fields) with total=False convention matching InvestmentState
- REQUIRED_FUNDAMENTAL_FIELDS list (7 fields) enabling consistent quality_score computation across validator
- DataSourceProtocol and MacroSourceProtocol using @runtime_checkable Protocol — any class with the right method signature satisfies the protocol without inheritance
- DataUnavailableError and LookAheadError exceptions with structured attributes for programmatic error handling
- TTLCache: instance-based, get/set/get_stale/clear, UTC-aware timestamps, TTL_FUNDAMENTALS=86400s / TTL_MACRO=604800s

## Task Commits

Each task was committed atomically:

1. **Task 1: Create types, exceptions, and protocols** - `611e7c1` (feat)
2. **Task 2: Create TTL cache with stale fallback** - `e32baa5` (feat)

**Plan metadata:** (see final commit)

## Files Created/Modified

- `src/lockin/data/types.py` - FundamentalsResult, MacroResult, ValidationResult TypedDicts and REQUIRED_FUNDAMENTAL_FIELDS
- `src/lockin/data/exceptions.py` - DataUnavailableError (ticker/source attrs), LookAheadError (as_of_date/data_date attrs)
- `src/lockin/data/protocols.py` - DataSourceProtocol, MacroSourceProtocol (@runtime_checkable Protocol)
- `src/lockin/data/cache.py` - TTLCache class with CacheEntry dataclass, TTL_FUNDAMENTALS/TTL_MACRO constants

## Decisions Made

- **fiscal_year_end on FundamentalsResult:** Added `fiscal_year_end: date | None` field as required by storage.py (plan 02-05) to key the fundamentals table correctly and avoid look-ahead bias. None if not determinable by the source.
- **TTLCache is instance-based:** Not a singleton. Callers (YFinanceSource, FREDSource) inject a fresh cache instance, keeping tests isolated.
- **@runtime_checkable protocols:** Enables `isinstance(source, DataSourceProtocol)` checks in tests, making substitutability explicit and verifiable without inheritance.
- **TTL constants at module level:** `TTL_FUNDAMENTALS = 86_400` and `TTL_MACRO = 604_800` defined in cache.py so all callers use consistent values.
- **Exception attributes on instance:** `e.ticker`, `e.source`, `e.as_of_date`, `e.data_date` stored on the exception instance for structured error handling in agents.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. The project uses a `.venv` virtual environment; verification commands required the explicit venv path `/home/mateo/dev/LockIn/.venv/bin/python`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Ready for Phase 2 Plan 02 (YFinanceSource): implement `DataSourceProtocol.get_fundamentals()` using `yfinance`, cache with `TTLCache(TTL_FUNDAMENTALS)`, raise `DataUnavailableError` on failure, set `fiscal_year_end` from DataFrame column.

Ready for Phase 2 Plan 03 (FREDSource): implement `MacroSourceProtocol.get_macro_indicators()` using `fredapi`, cache with `TTLCache(TTL_MACRO)`.

Ready for Phase 2 Plan 04 (Validator): use `REQUIRED_FUNDAMENTAL_FIELDS` to compute `quality_score`, return `ValidationResult`.

---
*Phase: 02-data-layer*
*Completed: 2026-02-22*
