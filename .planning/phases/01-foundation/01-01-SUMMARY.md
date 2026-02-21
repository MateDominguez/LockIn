---
phase: 01-foundation
plan: "01"
subsystem: core-types
tags: [langgraph, typeddict, python-dotenv, dataclass, lru_cache, investment-state]

# Dependency graph
requires: []
provides:
  - InvestmentState TypedDict (40+ fields) — central state schema for LangGraph StateGraph
  - create_initial_state(ticker) helper — produces valid seed state dict
  - Settings dataclass + get_settings() — cached .env config loader
  - 7 mock agent functions with (state, config) -> dict signature
  - MOCK_AGENTS registry dict mapping agent names to callables
affects:
  - 01-02  (graph builder uses InvestmentState + mock agents as node functions)
  - 01-03  (audit system uses InvestmentState fields for transition logging)
  - 02-*   (data layer agents build on InvestmentState schema)
  - 03-*   (real agents replace mock stubs, same signature)

# Tech tracking
tech-stack:
  added:
    - typing.TypedDict (total=False) for partial-update-compatible state
    - langchain_core.runnables.RunnableConfig for agent signatures
    - python-dotenv (load_dotenv) for .env loading
    - functools.lru_cache for singleton Settings
  patterns:
    - "Agent signature: (state: InvestmentState, config: RunnableConfig) -> dict (partial update)"
    - "State schema uses total=False so LangGraph can merge partial agent outputs"
    - "Bull iteration counter in state drives conditional edge routing (bear increments it)"
    - "Settings is frozen dataclass + lru_cache — single read of .env per process"

key-files:
  created:
    - src/lockin/graph/state.py
    - src/lockin/utils/config.py
    - src/lockin/agents/mock.py
  modified:
    - src/lockin/graph/__init__.py
    - src/lockin/utils/__init__.py
    - src/lockin/agents/__init__.py

key-decisions:
  - "TypedDict total=False chosen over Pydantic/dataclass — LangGraph StateGraph requires TypedDict for partial merge"
  - "bull_iteration lives in InvestmentState and is incremented by mock_bear — conditional edge reads this field"
  - "mock_value_hunter includes bull_refined_thesis + bull_defense only when bull_iteration > 0 (post-debate logic)"
  - "Settings defaults all missing env vars to empty string — agents validate at call-time, not import-time"

patterns-established:
  - "Agent pattern: each agent owns specific fields and returns ONLY those fields (partial state update)"
  - "Bull-Bear iteration: bear increments bull_iteration; graph edge checks this counter to stop after N rounds"
  - "Config pattern: frozen dataclass + lru_cache — single .env read, immutable, testable"

# Metrics
duration: 2min
completed: 2026-02-21
---

# Phase 1 Plan 1: InvestmentState Schema + Mock Agents Summary

**InvestmentState TypedDict (40+ fields, total=False) + 7 mock agent functions with (state, config) -> dict signature covering full macro-to-portfolio analysis pipeline**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-21T04:23:31Z
- **Completed:** 2026-02-21T04:25:22Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- InvestmentState TypedDict with 40+ fields across 7 domains (request metadata, macro, bull-bear dialectic, strategist, guardian, judge, optimizer, audit trail) — the single source of truth for all graph state
- create_initial_state(ticker) produces valid seed state with uuid4 request_id, UTC timestamp, and bull_iteration=0
- 7 mock agents (macro_oracle, value_hunter, bear, strategist, guardian, judge, optimizer) each returning realistic partial state updates with correct (state, config) signature
- mock_bear correctly increments bull_iteration — this is the mechanism the conditional edge will use to count debate rounds
- Settings dataclass + lru_cache get_settings() loading DATABASE_URL, SUPABASE_URL/KEY, GOOGLE_API_KEY, FRED_API_KEY from .env

## Task Commits

Each task was committed atomically:

1. **Task 1: InvestmentState TypedDict + config loader** - `e64940e` (feat)
2. **Task 2: All 7 mock agent functions** - `66c4642` (feat)

**Plan metadata:** (see final docs commit)

## Files Created/Modified

- `src/lockin/graph/state.py` - InvestmentState TypedDict (40+ fields, total=False) + create_initial_state helper
- `src/lockin/utils/config.py` - Settings dataclass + lru_cache get_settings() reading from .env
- `src/lockin/agents/mock.py` - 7 mock agent functions + MOCK_AGENTS registry dict
- `src/lockin/graph/__init__.py` - Exports InvestmentState, create_initial_state
- `src/lockin/utils/__init__.py` - Exports Settings, get_settings
- `src/lockin/agents/__init__.py` - Exports all 7 mock functions + MOCK_AGENTS

## Decisions Made

- Used TypedDict with total=False instead of Pydantic model or dataclass. LangGraph's StateGraph.add_node expects nodes returning dicts that merge into state; TypedDict is the correct type hint for this pattern. Pydantic would require extra conversion.
- bull_iteration is stored in state and incremented by mock_bear (not the graph orchestrator). This keeps the routing logic simple: the conditional edge just reads state["bull_iteration"] and decides whether to loop back to value_hunter or continue.
- mock_value_hunter conditionally includes bull_refined_thesis and bull_defense fields only when bull_iteration > 0. This mirrors the real agent's expected behavior — first pass produces initial thesis, subsequent passes produce refined output.
- Settings defaults all missing .env vars to empty string rather than raising errors at import. Real agents will validate their required keys at the time they need them (plan 01-02+), keeping this module safe to import in any context.

## Deviations from Plan

None — plan executed exactly as written. The only additions beyond the plan spec were:
- Extra percentile keys (P25, P50, P75) added to valuation distributions for completeness (not in plan spec but architecturally required by Judge's Bayesian synthesis)
- fred_api_key, env, and log_level added to Settings (plan only listed 4 env vars; these are in .env.example and needed by agents)

These are minor scope additions within the same task, not architectural changes.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required for this plan. (DATABASE_URL and other keys are loaded lazily; agents validate at call-time.)

## Next Phase Readiness

- InvestmentState schema is stable and ready for graph builder (plan 01-02)
- Mock agents have the correct (state, config) -> dict signature for LangGraph node registration
- bull_iteration increment in mock_bear is ready for conditional edge logic
- Config loader is ready for PostgreSQL checkpointer connection in plan 01-02

---
*Phase: 01-foundation*
*Completed: 2026-02-21*
