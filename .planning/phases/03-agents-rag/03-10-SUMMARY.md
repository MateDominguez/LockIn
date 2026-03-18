---
phase: 03-agents-rag
plan: 10
subsystem: orchestration
tags: [langgraph, stategraph, agent-wiring, e2e-tests, jaccard, hitl, circuit-breaker, pytest]

# Dependency graph
requires:
  - phase: 03-02
    provides: macro_oracle agent (ConfidenceModifier, FRED regime detection)
  - phase: 03-03
    provides: value_hunter agent (ValueDistribution, EPV/EVA/RIM)
  - phase: 03-04
    provides: strategist agent (ConfidenceModifier, VeTO + analyst momentum)
  - phase: 03-05
    provides: bear agent (ValueDistribution, pessimistic EPV, red flags)
  - phase: 03-06
    provides: guardian agent (ConfidenceModifier with circuit_breaker)
  - phase: 03-08
    provides: judge agent (judge_math.py 7-step Bayesian algorithm, HITL at p<0.40)
  - phase: 03-09
    provides: optimizer agent (Kelly/3 position sizing, hard caps)
provides:
  - builder.py wired to real agents as defaults (no more mock_* in graph)
  - is_argument_exhausted() Jaccard similarity detection for dialectic termination
  - should_guardian_veto() reads guardian_modifier.circuit_breaker (typed, not legacy bool)
  - judge_with_hitl() delegates to real judge agent (p_final < 0.40 threshold)
  - REAL_AGENTS registry dict in lockin.agents.__init__
  - tests/e2e/test_full_pipeline.py: 5 E2E tests covering full pipeline flows
affects:
  - 03-11 (RAG retrieval integration — graph is now fully wired)
  - 04-01 onwards (Integration phase — full pipeline ready)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Jaccard similarity (top-20 most frequent words) for dialectic argument exhaustion detection"
    - "agent_overrides injecting typed-dataclass stubs for E2E tests (no LLM/network)"
    - "autouse pytest fixture patching lockin.utils.audit.get_settings to empty DATABASE_URL"
    - "Real judge algorithm (run_judge_algorithm) called inside stub agents for realistic math"

key-files:
  created:
    - tests/e2e/__init__.py
    - tests/e2e/test_full_pipeline.py
  modified:
    - src/lockin/graph/builder.py
    - src/lockin/agents/__init__.py

key-decisions:
  - "Argument exhaustion: Jaccard similarity on top-20 words with 0.85 threshold — simple, no NLP deps, reproducible"
  - "should_continue_dialectic returns 'value_hunter' (not 'bear') — conditional edge mapping has only 'value_hunter'/'strategist'"
  - "guardian veto routing reads guardian_modifier.circuit_breaker first, falls back to guardian_veto bool for mock compatibility"
  - "E2E tests use agent_overrides with typed stubs (not mock.patch of LLM) — stubs return real ConfidenceModifier/ValueDistribution/JudgeOutput"
  - "run_judge_algorithm called in stub_judge_normal/hitl — real math without LLM/yfinance network calls"
  - "autouse patch_audit_settings fixture in e2e/ — prevents all E2E tests from hitting Supabase"
  - "Phase 1 tests/test_graph_e2e.py failures are pre-existing (invalid Supabase creds, no Google API key) — not regressions"

patterns-established:
  - "E2E test pattern: autouse fixture patches audit settings, agent_overrides provides typed stubs"
  - "Stub agents in E2E tests return same typed dataclasses as real agents (not raw dicts)"
  - "Builder.py conditional edge routing: return 'value_hunter' not 'bear' for loop continuation"

# Metrics
duration: 11min
completed: 2026-03-18
---

# Phase 3 Plan 10: Graph Wiring + E2E Tests Summary

**LangGraph graph wired to all 7 real agents with Jaccard argument exhaustion detection and 5 E2E pipeline tests using typed stubs (no LLM API keys required)**

## Performance

- **Duration:** 11 min
- **Started:** 2026-03-18T03:57:38Z
- **Completed:** 2026-03-18T04:08:58Z
- **Tasks:** 2/2 complete
- **Files modified:** 4

## Accomplishments

- Replaced 7 mock_* agent defaults in builder.py with real agents (macro_oracle, value_hunter, bear, strategist, guardian, judge, optimizer)
- Implemented `is_argument_exhausted()` using Jaccard similarity (top-20 words, 0.85 threshold) and wired into dialectic routing
- Updated `should_guardian_veto()` to read `guardian_modifier.circuit_breaker` (typed ConfidenceModifier) with `guardian_veto` boolean as legacy fallback
- Updated `judge_with_hitl()` to delegate to real judge (p_final < 0.40 threshold per Notion spec)
- Added REAL_AGENTS registry and lazy exports for all 7 real agents in `__init__.py`
- Created 5 E2E tests using typed dataclass stubs: normal flow, guardian veto, judge HITL resume, state continuity, argument exhaustion unit tests

## Task Commits

Each task committed atomically:

1. **Task 1: Update graph builder with real agents + argument exhaustion** - `8c783d8` (feat)
2. **Task 1 fix: Correct dialectic routing return value** - `51d01ae` (fix)
3. **Task 2: E2E pipeline tests with typed stubs** - `fee6866` (test)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `src/lockin/graph/builder.py` — Real agent imports, `is_argument_exhausted()`, updated routing functions, `judge_with_hitl()` delegates to real judge
- `src/lockin/agents/__init__.py` — REAL_AGENTS registry, lazy exports for all 7 real agents
- `tests/e2e/__init__.py` — New E2E test package
- `tests/e2e/test_full_pipeline.py` — 5 E2E tests with typed stubs and audit patching

## Decisions Made

- **Jaccard on top-20 words:** Simple, reproducible, no NLP dependencies. 0.85 threshold gives meaningful similarity without being too aggressive — minor word additions (normal in one rebuttal round) won't trigger early termination.
- **`return "value_hunter"` not `"bear"` in routing:** The conditional edge `add_conditional_edges("bear", should_continue_dialectic, {"value_hunter": ..., "strategist": ...})` has "value_hunter" and "strategist" as the only valid keys. Returning "bear" caused KeyError.
- **guardian_modifier.circuit_breaker primary, guardian_veto fallback:** Real guardian sets both; mock guardian only sets guardian_veto. The dual-path handles both without breaking Phase 1 tests.
- **E2E stubs use real typed dataclasses:** Stubs that return real ConfidenceModifier/ValueDistribution/JudgeOutput test the actual type contracts, not just raw dict structure.
- **run_judge_algorithm in stubs:** Calling the real pure-math function in judge stubs makes the test mathematically realistic without needing LLM/yfinance.
- **autouse patch_audit_settings:** All E2E tests need this — an autouse fixture avoids repetition and ensures no test inadvertently hits Supabase.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed dialectic routing returning wrong destination key**

- **Found during:** Task 2 (E2E test execution)
- **Issue:** `should_continue_dialectic()` returned `"bear"` for the continue case, but the conditional edge mapping only has `"value_hunter"` and `"strategist"` as valid keys — caused `KeyError: 'bear'` on first bear→continue routing.
- **Fix:** Changed return value from `"bear"` to `"value_hunter"` with explanatory comment.
- **Files modified:** `src/lockin/graph/builder.py`
- **Verification:** All 5 E2E tests pass; was causing all non-exhaustion tests to fail with KeyError
- **Committed in:** `51d01ae` (separate atomic fix commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Critical routing bug that would have caused all dialectic loops to crash. Caught immediately by E2E test execution.

## Issues Encountered

- Phase 1 `tests/test_graph_e2e.py` tests are failing with `psycopg.OperationalError` (Supabase creds invalid/expired) and `langchain_google_genai` errors — verified these failures are pre-existing before this plan's changes. Not regressions.

## Next Phase Readiness

- Graph is fully wired with all 7 real agents — ready for Plan 03-11 (RAG retrieval integration)
- E2E test infrastructure established: stub pattern + audit patching reusable for future plans
- agent_overrides mechanism preserved for continued test injection
- Mock agents remain available in `lockin.agents.MOCK_AGENTS` for backward compatibility

---
*Phase: 03-agents-rag*
*Completed: 2026-03-18*
