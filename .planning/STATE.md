# Project State: AI-Investment Swarm

**Last Updated:** 2026-02-22
**Current Phase:** Phase 2 - Data Layer (In progress)
**Status:** Phase 2 plan 02-01 complete — foundational types, protocols, exceptions, cache

---

## Project Reference

**Building:** AI-Investment Swarm — Sistema multi-agente con síntesis Bayesiana para análisis de inversiones Value Investing híbrido (Graham × VeTO × VoMC)

**Core Value:** Transparencia total mediante arquitectura "caja de cristal" — cada decisión trazable, explicable, auditable.

**Current Focus:** Phase 2 Data Layer — executing plans 02-01 through 02-05.

---

## Current Position

**Phase:** 2 of 6 (In progress — 1/4 plans complete)
**Progress:** ████████░░ 20% (Phase 1 complete + 1 plan in Phase 2)

```
✓ Phase 0 - Planning      [██████████] 100%
✓ Phase 1 - Foundation    [██████████] 100%  (3/3 plans, verified 13/13)
  Phase 2 - Data Layer    [██░░░░░░░░]  25%  (1/4 plans: 02-01 complete)
  Phase 3 - Agents + RAG  [░░░░░░░░░░]   0%
  Phase 4 - Integration   [░░░░░░░░░░]   0%
  Phase 5 - Validation    [░░░░░░░░░░]   0%
  Phase 6 - Interface     [░░░░░░░░░░]   0%
```

---

## Recent Decisions

**Plan 02-01 Implementation (2026-02-22):**
- FundamentalsResult includes fiscal_year_end: date | None — required by storage.py (plan 02-05) to key fundamentals table correctly; None if YFinanceSource cannot determine it
- TTLCache is instance-based (not singleton) — callers inject fresh cache for test isolation
- DataSourceProtocol and MacroSourceProtocol are @runtime_checkable — enables isinstance(source, DataSourceProtocol) assertions in tests without inheritance
- TTL_FUNDAMENTALS=86400s (24h), TTL_MACRO=604800s (7 days) defined in cache.py so all callers use consistent values
- Exception attributes on instance: e.ticker, e.source for DataUnavailableError; e.as_of_date, e.data_date for LookAheadError

**Plan 01-03 Implementation (2026-02-21):**
- judge_with_hitl runs mock_judge first then calls interrupt() conditionally — avoids side effects before interrupt() since node re-executes on resume
- JUDGE_HITL_THRESHOLD = 0.5 as module constant; mock_judge returns conviction=0.70 (above threshold) so normal runs never trigger HITL
- postgres_checkpointer context manager calls saver.setup() on entry — idempotent, creates tables if needed
- 6/6 E2E tests pass with MemorySaver (135.51s); all CORE-01 through CORE-04 requirements verified

**Plan 01-02 Implementation (2026-02-21):**
- Separate short-lived psycopg.connect() for audit writes — LangGraph checkpointer holds open transactions; sharing connection can deadlock
- audit_logs table schema (Supabase) uses `payload` JSONB (not `state_snapshot`) — adapted INSERT at runtime
- MAX_BULL_BEAR_ITERATIONS=2 constant in builder.py
- Conditional edge mapping uses `'__end__': END` for guardian veto path

**Plan 01-01 Implementation (2026-02-21):**
- TypedDict total=False for InvestmentState — LangGraph requires TypedDict for partial merge
- bull_iteration incremented by mock_bear — conditional edge reads this to count debate rounds
- Settings defaults all missing .env vars to empty string — agents validate at call-time

**Agent Architecture Finalized (2026-02-08):**
- ✓ 7 agents for v1 (Macro Oracle, Value Hunter, Strategist, Bear, Guardian, Judge, Optimizer)
- ✓ Bull-Bear dialectical iteration (minimum 1 back-and-forth)
- ✓ Bayesian synthesis in Judge (not simple voting)
- ✓ Guardian veto power as constitutional rule
- ✓ Simplified VeTO in v1, full NLP model deferred to v2

**Technology Stack:**
- ✓ LangGraph for orchestration
- ✓ Python 3.12 + pandas/numpy/scipy
- ✓ Google AI (Gemini) for LLMs (free tier 1500 req/day)
- ✓ Supabase (PostgreSQL + pgvector) for DB + RAG
- ✓ Streamlit for dashboard

---

## Pending Todos

### Phase 2 - Data Layer (In Progress)
- [x] 02-01: Types, protocols, exceptions, TTL cache (DONE)
- [ ] 02-02: YFinanceSource — implements DataSourceProtocol
- [ ] 02-03: FREDSource — implements MacroSourceProtocol
- [ ] 02-04: Validator — uses REQUIRED_FUNDAMENTAL_FIELDS, returns ValidationResult
- [ ] 02-05: Storage — PostgreSQL schema, uses fiscal_year_end to key fundamentals

---

## Blockers/Concerns

**None currently.**

**Known Limitations (deferred):**
- **audit_node duplicate agent_start on HITL resume** (defer to Phase 3): `audit_node` logs `agent_start` BEFORE calling `fn(state, config)`. When `judge_with_hitl` calls `interrupt()`, the node pauses mid-execution. On resume, LangGraph re-executes the entire node from the top — including the `audit_node` wrapper — so `agent_start` is logged twice (2× `agent_start` + 1× `agent_end` for judge on HITL runs). Violates the research principle "no side effects before interrupt()". Does not affect the 6 other agents (none call `interrupt()`). Does not affect normal runs where conviction ≥ 0.5. Fix in Phase 3 when real judge agent is implemented — proper fix may distinguish "first execution" vs "resumed execution" in audit records.

**Future considerations:**
- Google AI rate limits (1500 req/day) — monitor in Phase 3, have OpenAI backup
- yfinance reliability — implement caching strategy in Phase 2 (TTLCache ready)
- RAG quality — RAGAs evaluation in Phase 3, iterate if faithfulness <90%
- Phase 3 duration (6 weeks) — longest phase, break into sub-phases if needed

---

## Session Continuity

**Last session:** 2026-02-22
**Activity:** Executed Phase 2 plan 02-01 — types, protocols, exceptions, TTL cache
**Stopped at:** Completed 02-01-PLAN.md (2/2 tasks, 2 commits)
**Resume file:** None

**When resuming:**
1. Review STATE.md (this file)
2. Execute 02-02: YFinanceSource (`get_fundamentals`, point-in-time, TTLCache)
3. Reference `src/lockin/data/protocols.py` for interface to implement
4. Reference `src/lockin/data/cache.py` for TTLCache usage

---

## Phase Status

### Phase 0 - Planning ✓
**Status:** Complete
**Completed:** 2026-02-08

### Phase 1 - Foundation ✓
**Status:** Complete
**Completed:** 2026-02-21
**Verification:** 13/13 must-haves passed
**Key Deliverables:**
- ✓ InvestmentState TypedDict (43 fields, total=False)
- ✓ 7 mock agents with (state, config) -> dict signature
- ✓ Settings config loader (lru_cache, .env, no crash)
- ✓ LangGraph StateGraph — 7 nodes, bull-bear loop (x2), guardian veto
- ✓ audit_node wrapper — agent_start + agent_end to Supabase audit_logs
- ✓ judge_with_hitl — interrupt() at conviction < 0.5, Command(resume) continues
- ✓ postgres_checkpointer context manager
- ✓ 6 passing E2E tests (MemorySaver, all CORE-01..04)

### Phase 2 - Data Layer
**Status:** In Progress (1/4 plans complete)
**Dependencies:** Phase 1 complete ✓
**Plan 02-01:** Complete ✓ — types.py, exceptions.py, protocols.py, cache.py

### Phase 3 - Agents & RAG
**Status:** Not Started
**Dependencies:** Phase 1, 2 complete

### Phase 4 - Integration
**Status:** Not Started
**Dependencies:** Phase 1, 2, 3 complete

### Phase 5 - Validation
**Status:** Not Started
**Dependencies:** Phase 1, 2, 3, 4 complete

### Phase 6 - Interface
**Status:** Not Started
**Dependencies:** Phase 3, 4 complete (can partially overlap with Phase 5)

---

## Git Status

**Branch:** main
**Last commit:** e32baa5 — feat(02-01): create TTL cache with stale fallback

---

## Quick Reference

**Commands:**
- Resume work: `/gsd:resume-work`
- Check progress: `/gsd:progress`
- Execute next plan: `/gsd:execute-phase 2` (plan 02-02)

**Key Files:**
- Architecture: `.planning/PROJECT.md`
- Requirements: `.planning/REQUIREMENTS.md`
- Roadmap: `.planning/ROADMAP.md`
- Phase 1 patterns: `.planning/phases/01-foundation/`
- Phase 2 foundation: `src/lockin/data/types.py`, `src/lockin/data/protocols.py`, `src/lockin/data/cache.py`

**Data Layer Contracts (02-01):**
- Types: `from lockin.data.types import FundamentalsResult, MacroResult, ValidationResult, REQUIRED_FUNDAMENTAL_FIELDS`
- Protocols: `from lockin.data.protocols import DataSourceProtocol, MacroSourceProtocol`
- Exceptions: `from lockin.data.exceptions import DataUnavailableError, LookAheadError`
- Cache: `from lockin.data.cache import TTLCache, TTL_FUNDAMENTALS, TTL_MACRO`

**Timeline:**
- Week 0-2: Phase 1 (Foundation) ✓
- Week 2-4: Phase 2 (Data Layer) ← in progress
- Week 4-10: Phase 3 (Agents + RAG)
- Week 10-12: Phase 4 (Integration)
- Week 12-15: Phase 5 (Validation)
- Week 15-18: Phase 6 (Interface)
- **Target:** June 2026

---

*State initialized: 2026-02-08*
*Last updated: 2026-02-22 after Phase 2 plan 02-01 completion*
