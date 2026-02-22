---
phase: 01-foundation
plan: 03
subsystem: orchestration, testing
tags: [langgraph, hitl, interrupt, postgresql, checkpointing, pytest, e2e-tests]

# Dependency graph
requires:
  - phase: 01-02
    provides: create_graph factory with 7 audited nodes, conditional edges, agent_overrides

provides:
  - judge_with_hitl: pauses execution via interrupt() when judge_conviction < 0.5
  - postgres_checkpointer context manager (PostgresSaver + setup())
  - 6 passing E2E tests covering all Phase 1 CORE requirements
  - Human review flow: first invoke pauses at judge, Command(resume=...) resumes to optimizer

affects:
  - 02-xx (Data layer: real agents will use same HITL pattern)
  - 05-xx (Validation: test patterns established here used as template)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "judge_with_hitl pattern: run agent first, then check output, call interrupt() conditionally — node re-executes on resume, interrupt() returns human input"
    - "Command(resume=value): LangGraph resume primitive — pass to graph.invoke() on interrupted thread"
    - "postgres_checkpointer context manager: PostgresSaver.from_conn_string + saver.setup() in __enter__"
    - "agent_overrides for test injection: pass mock functions to create_graph to override specific nodes"

key-files:
  modified:
    - src/lockin/graph/builder.py
    - src/lockin/graph/__init__.py
  created:
    - tests/conftest.py
    - tests/test_graph_e2e.py
    - tests/__init__.py

key-decisions:
  - "judge_with_hitl runs mock_judge first then checks conviction — avoids side effects before interrupt()"
  - "JUDGE_HITL_THRESHOLD = 0.5 defined as module constant in builder.py for visibility"
  - "postgres_checkpointer calls saver.setup() on entry — idempotent, creates tables if needed"
  - "test_hitl_interrupt_low_conviction injects mock_judge_low_conviction (conviction=0.3) via agent_overrides"
  - "test_audit_logging_stderr patches get_settings to return empty DATABASE_URL — uses capsys to capture stderr"

# Metrics
duration: ~7min (including human verification checkpoint)
completed: 2026-02-21
---

# Phase 1 Plan 03: HITL Interrupt + PostgreSQL Checkpointing + E2E Tests

**HITL interrupt at judge node, PostgresSaver context manager, and 6 passing E2E tests validating all Phase 1 CORE requirements.**

## Performance

- **Duration:** ~7 min (including human verification pause)
- **Completed:** 2026-02-21
- **Tasks:** 3/3 (including checkpoint)
- **Files modified:** 5 (2 modified, 3 created)
- **Tests:** 6/6 passed

## Accomplishments

- `judge_with_hitl` in `builder.py`: wraps `mock_judge`, calls `interrupt()` when `judge_conviction < 0.5`; on resume, `interrupt()` returns the `Command(resume=...)` value which is stored in `state.human_review`
- `postgres_checkpointer` context manager: `PostgresSaver.from_conn_string(url)` + `saver.setup()` — ready for production use
- 6 E2E tests covering all Phase 1 CORE requirements — all pass with `MemorySaver`

## Task Commits

1. **Task 1: HITL interrupt in judge node + PostgresSaver** — `6da570e` (feat)
2. **Task 2: End-to-end test suite** — `a1627a4` (feat)
3. **Task 3: Human verification checkpoint** — approved (6/6 tests passed in 135.51s)

## Files Created/Modified

- `src/lockin/graph/builder.py` — Added `judge_with_hitl`, `JUDGE_HITL_THRESHOLD`, `postgres_checkpointer`; `create_graph` now defaults to `judge_with_hitl`
- `src/lockin/graph/__init__.py` — Exported `judge_with_hitl`, `postgres_checkpointer`
- `tests/conftest.py` — Shared fixtures: `memory_saver`, `graph`, `initial_state`, `thread_config`
- `tests/test_graph_e2e.py` — 6 E2E tests (247 lines)
- `tests/__init__.py` — Empty package init

## Test Results

```
tests/test_graph_e2e.py::test_full_pipeline_mock              PASSED
tests/test_graph_e2e.py::test_bull_bear_iteration_count       PASSED
tests/test_graph_e2e.py::test_guardian_veto_stops_pipeline    PASSED
tests/test_graph_e2e.py::test_checkpoint_stores_state         PASSED
tests/test_graph_e2e.py::test_hitl_interrupt_low_conviction   PASSED
tests/test_graph_e2e.py::test_audit_logging_stderr            PASSED
======================== 6 passed in 135.51s ========================
```

## Decisions Made

- **`judge_with_hitl` runs agent first, then checks:** Avoids placing side effects before `interrupt()`. The entire node re-executes on resume — `interrupt()` returns the human input instead of pausing.
- **`JUDGE_HITL_THRESHOLD = 0.5`:** Module constant in `builder.py`. Mock judge returns `conviction=0.70` (above threshold), so normal runs never trigger HITL. Tests inject `conviction=0.30` to force the interrupt path.
- **`postgres_checkpointer` as context manager:** `saver.setup()` is idempotent — safe to call on every startup. Keeps PostgresSaver lifecycle explicit.

## Deviations from Plan

None. All 6 tests written and passing as specified.

## Next Phase Readiness

- All CORE-01 through CORE-04 requirements verified by tests
- Graph ready for Phase 2 (Data Layer): real data fetchers replace mock agents via same `agent_overrides` pattern
- `postgres_checkpointer` ready for production runs
- Test patterns established here serve as template for Phase 5 (Validation)

---
*Phase: 01-foundation*
*Completed: 2026-02-21*
