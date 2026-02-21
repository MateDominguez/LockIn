---
phase: 01-foundation
plan: 02
subsystem: orchestration
tags: [langgraph, stategraph, psycopg, audit-trail, conditional-edges, bull-bear, guardian-veto]

# Dependency graph
requires:
  - phase: 01-01
    provides: InvestmentState TypedDict + 7 mock agent functions (mock_bear increments bull_iteration)

provides:
  - LangGraph StateGraph with 7 audited agent nodes compiled and runnable
  - Bull-Bear dialectic conditional edge (loops value_hunter<->bear x2, then exits to strategist)
  - Guardian veto conditional edge (END on veto, judge on pass)
  - audit_node wrapper that emits agent_start/agent_end events per execution
  - log_audit_event persists to Supabase audit_logs table via separate psycopg connection

affects:
  - 01-03 (HITL: will add interrupt_before="judge" to this graph)
  - 02-xx (Data layer: real agents will replace mocks, same graph structure)
  - 03-xx (Agents + RAG: same audit_node wrapper used around real LLM agents)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "audit_node wrapper pattern: decorate any (state, config)->dict function to add audit logging without modifying the function"
    - "Separate psycopg connection for audit writes: avoids transaction conflicts with LangGraph checkpointer"
    - "agent_overrides dict in create_graph: allows test injection without changing graph topology"
    - "should_continue_dialectic / should_guardian_veto: pure functions over state -> string for conditional routing"

key-files:
  created:
    - src/lockin/utils/audit.py
    - src/lockin/graph/builder.py
  modified:
    - src/lockin/utils/__init__.py
    - src/lockin/graph/__init__.py

key-decisions:
  - "Used separate short-lived psycopg.connect() for audit writes instead of sharing checkpointer connection, preventing transaction conflicts"
  - "audit_logs table schema (Supabase) uses payload JSONB column (not state_snapshot) — adapted INSERT to match actual schema"
  - "agent_start logs only asset_ticker + bull_iteration (minimal payload); agent_end logs full agent output dict"
  - "MAX_BULL_BEAR_ITERATIONS=2 constant in builder.py — bear runs twice, value_hunter rebuts twice, then exits to strategist"
  - "Conditional edge mapping uses string '__end__': END for guardian veto path — confirmed END == '__end__' in LangGraph"

patterns-established:
  - "audit_node(name, fn): standard wrapper for all agent functions in graph — apply at add_node time"
  - "create_graph(checkpointer, agent_overrides): factory pattern — always import this, never build graph inline"

# Metrics
duration: 3min
completed: 2026-02-21
---

# Phase 1 Plan 02: LangGraph StateGraph + Audit Trail Summary

**LangGraph StateGraph with 7 audited nodes, bull-bear loop (x2) and guardian veto conditional edges, audit trail persisting to Supabase audit_logs via separate psycopg connection**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-02-21T04:28:41Z
- **Completed:** 2026-02-21T04:31:35Z
- **Tasks:** 2/2
- **Files modified:** 4 (2 created, 2 updated)

## Accomplishments

- `audit_node` wrapper emits `agent_start` + `agent_end` events around every agent call; persists to Supabase `audit_logs` or falls back to stderr when `DATABASE_URL` is empty
- `create_graph` factory compiles a LangGraph `StateGraph` with all 7 nodes, linear edges, and two conditional edges — full end-to-end mock run completes with `BUY` recommendation and `bull_iteration=2`
- Bull-Bear dialectic executes exactly 2 rounds: `bear` increments `bull_iteration` 0→1→2, conditional edge loops back to `value_hunter` once then exits to `strategist`

## Task Commits

Each task was committed atomically:

1. **Task 1: Audit trail logger with DB persistence** - `f5bf97a` (feat)
2. **Task 2: StateGraph builder with all edges and conditionals** - `efe1e01` (feat)

**Plan metadata:** (docs commit below)

## Files Created/Modified

- `src/lockin/utils/audit.py` - `log_audit_event` (psycopg INSERT to audit_logs) + `audit_node` wrapper
- `src/lockin/graph/builder.py` - `create_graph` factory with all 7 nodes, conditional edge functions
- `src/lockin/utils/__init__.py` - Added `audit_node`, `log_audit_event` to exports
- `src/lockin/graph/__init__.py` - Added `create_graph` to exports

## Decisions Made

- **Separate psycopg connection for audit writes:** LangGraph's PostgreSQL checkpointer holds open transactions; inserting into the same connection can deadlock. Short-lived `psycopg.connect()` per audit event avoids this entirely.
- **Actual audit_logs schema differs from plan spec:** The Supabase table uses `payload` (JSONB) instead of `state_snapshot`, and `created_at` instead of `timestamp`. INSERT adapted accordingly. (Rule 1 - Bug fix)
- **`agent_start` logs minimal state:** Only `asset_ticker` + `bull_iteration` to keep payloads small. `agent_end` logs the full agent output dict for complete traceability.
- **`MAX_BULL_BEAR_ITERATIONS = 2`:** Constant defined in `builder.py` so the loop count is visible and easy to change without touching routing logic.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Actual audit_logs table schema differs from plan spec**

- **Found during:** Task 1 (Audit trail logger) verification
- **Issue:** Plan specified `state_snapshot` JSONB column and `timestamp` column. The actual Supabase `audit_logs` table uses `payload` JSONB, `created_at` TIMESTAMPTZ (auto-filled), and has additional columns `asset_ticker`, `request_id`, `session_id`. INSERT failed with `UndefinedColumn: column "state_snapshot" does not exist`.
- **Fix:** Introspected actual schema via `information_schema.columns`. Updated `log_audit_event` signature to accept optional `asset_ticker` and `request_id` params. Changed INSERT to use `payload`, removed explicit `timestamp` (DB default handles it), added `asset_ticker`, `request_id`, `session_id` columns.
- **Files modified:** `src/lockin/utils/audit.py`
- **Verification:** INSERT succeeds; confirmed rows in DB: `SELECT agent_name, event_type FROM audit_logs ORDER BY id DESC LIMIT 4` returns `macro_oracle / agent_end` and `macro_oracle / agent_start`.
- **Committed in:** f5bf97a (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug — schema mismatch)
**Impact on plan:** Fix required for audit writes to work at all. No scope creep — same audit semantics, just correct column names.

## Issues Encountered

None beyond the schema mismatch documented above.

## User Setup Required

None — audit_logs table already exists in Supabase. No new tables or manual configuration required.

## Next Phase Readiness

- Graph is fully compiled and runnable with mock agents
- Audit trail writing to Supabase in real time (confirmed via DB query)
- Ready for Plan 01-03: HITL interrupt (`interrupt_before="judge"`) — will add `interrupt_before` param to `builder.compile()` call in `create_graph`
- `agent_overrides` param in `create_graph` ready for Phase 3 real agent injection

---
*Phase: 01-foundation*
*Completed: 2026-02-21*
