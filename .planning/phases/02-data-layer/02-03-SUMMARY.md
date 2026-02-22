---
phase: 02-data-layer
plan: "03"
subsystem: database
tags: [psycopg, postgres, validation, outlier-detection, hitl, data-lineage, upsert]

# Dependency graph
requires:
  - phase: 02-01
    provides: FundamentalsResult, MacroResult, ValidationResult, REQUIRED_FUNDAMENTAL_FIELDS types
  - phase: 01-02
    provides: log_audit_event, short-lived psycopg connection pattern
provides:
  - DataValidator class with quality scoring and outlier detection
  - store_fundamentals: per-field UPSERT with fiscal_year_end keying
  - store_macro_data: per-indicator UPSERT for FRED snapshots
  - store_asset: ticker registry UPSERT with COALESCE semantics
  - setup_data_tables.py: idempotent CREATE TABLE for fundamentals, macro_data, assets
affects:
  - 02-02 (YFinanceSource can call store_fundamentals after fetching)
  - 02-04 (FREDSource can call store_macro_data after fetching)
  - Phase 3 agents (DataValidator used before passing data to agents)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Short-lived psycopg.connect() per write call — never shared with LangGraph checkpointer"
    - "Storage errors caught and logged to stderr, never re-raised — resilient pipeline"
    - "Data lineage columns (source, fetched_at, as_of_date) on every persisted row"
    - "UNIQUE constraint + ON CONFLICT DO UPDATE for idempotent upserts"
    - "Sentinel thread_id 'data_validation' for audit events outside LangGraph context"

key-files:
  created:
    - src/lockin/data/validator.py
    - src/lockin/data/storage.py
    - scripts/setup_data_tables.py
  modified: []

key-decisions:
  - "HITL threshold >200% change: consistent with plan spec; 50-200% is warning-only (outlier_flags set but no HITL)"
  - "FRED_SERIES_IDS duplicated in storage.py (not imported from fred_source.py) to avoid circular imports"
  - "Sentinel thread_id 'data_validation' used in audit logs: validator has no LangGraph thread context"
  - "observation_date stored as NULL in macro_data for now: FRED response parsing is fred_source.py responsibility"
  - "storage errors logged to stderr but not re-raised: storage outage must not break data fetch pipeline"

patterns-established:
  - "DataValidator.validate_period_change is a static method available to external callers"
  - "quality_score = 1.0 - (missing_count / total_required), clamped to [0.0, 1.0]"
  - "FINANCIAL_FIELDS (11 fields) and FRED_SERIES_IDS (8 indicators) defined at module level for external inspection"

# Metrics
duration: 2min
completed: 2026-02-22
---

# Phase 2 Plan 03: DataValidator, Storage Functions, and DB Setup Summary

**Quality-scored fundamentals validation with HITL triggers (>200% outlier) plus PostgreSQL UPSERT storage for fundamentals, macro snapshots, and asset registry — with full data lineage on every row.**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-02-22T18:36:23Z
- **Completed:** 2026-02-22T18:38:18Z
- **Tasks:** 2/2 completed
- **Files modified:** 3 created

## Accomplishments

- DataValidator computes quality_score from 7 required fields (0.0–1.0), detects outliers at 50% and 200% thresholds, and logs HITL triggers to audit_logs
- storage.py provides three resilient UPSERT functions using short-lived psycopg connections with full data lineage columns
- setup_data_tables.py creates fundamentals, macro_data, and assets tables idempotently with correct indexes

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement DataValidator** - `2359fce` (feat)
2. **Task 2: Implement storage functions and DB setup script** - `0e48e53` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `src/lockin/data/validator.py` - DataValidator with quality_score computation, outlier detection (50%/200% thresholds), HITL audit logging
- `src/lockin/data/storage.py` - store_fundamentals, store_macro_data, store_asset with UPSERT SQL and data lineage
- `scripts/setup_data_tables.py` - Idempotent CREATE TABLE for fundamentals, macro_data, assets with indexes

## Decisions Made

- **Sentinel thread_id:** Used `"data_validation"` as static string for audit logs — the validator has no LangGraph thread context and this clearly identifies the source
- **Circular import avoidance:** Duplicated FRED_SERIES_IDS in storage.py rather than importing from a future fred_source.py module that doesn't exist yet
- **observation_date as NULL:** The macro_data table has an `observation_date` column but it's set to NULL by store_macro_data — the FRED observation date is parsed inside fred_source.py (plan 02-04), not here
- **Storage resilience:** All three storage functions catch exceptions and log to stderr rather than raising — a database outage at storage time must not propagate back to fail the data fetch

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all verification tests passed on first run.

## User Setup Required

None - no external service configuration required. The setup_data_tables.py script requires DATABASE_URL to be set in .env, which is a prerequisite already documented in the Phase 1 setup.

## Next Phase Readiness

- DataValidator is ready for Phase 3 agents to call before processing fundamentals
- store_fundamentals and store_macro_data await implementation of YFinanceSource (02-02) and FREDSource (02-04) to call them
- setup_data_tables.py must be run against Supabase once before Phase 2 sources can persist data

---
*Phase: 02-data-layer*
*Completed: 2026-02-22*
