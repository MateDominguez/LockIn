# Project State: AI-Investment Swarm

**Last Updated:** 2026-03-17
**Current Phase:** Phase 3 - Agents + RAG (In Progress — 1/11 plans done)
**Status:** Phase 2 complete — Phase 3 started (03-01 done) (types/protocols + data sources + validator/storage + public API + integration tests)

---

## Project Reference

**Building:** AI-Investment Swarm — Sistema multi-agente con síntesis Bayesiana para análisis de inversiones Value Investing híbrido (Graham × VeTO × VoMC)

**Core Value:** Transparencia total mediante arquitectura "caja de cristal" — cada decisión trazable, explicable, auditable.

**Current Focus:** Phase 3 Agents + RAG — executing plans 03-01 through 03-11.

---

## Current Position

**Phase:** 3 of 6 (Phase 3 — Agents + RAG, In Progress)
**Progress:** █████████████░ 36% (Phase 1 + Phase 2 complete + 03-01 done)

```
✓ Phase 0 - Planning      [██████████] 100%
✓ Phase 1 - Foundation    [██████████] 100%  (3/3 plans, verified 13/13)
✓ Phase 2 - Data Layer    [██████████] 100%  (4/4 plans: 02-01, 02-02, 02-03, 02-04 complete)
  Phase 3 - Agents + RAG  [█░░░░░░░░░]   9%  (1/11 plans: 03-01 done)
  Phase 4 - Integration   [░░░░░░░░░░]   0%
  Phase 5 - Validation    [░░░░░░░░░░]   0%
  Phase 6 - Interface     [░░░░░░░░░░]   0%
```

---

## Recent Decisions

**Plan 03-01 Implementation (2026-03-17):**
- Lazy `__getattr__` in `lockin.graph.__init__` and `lockin.agents.__init__` — breaks circular dependency between mock agents, graph state, and agent types
- Runtime imports (not TYPE_CHECKING) required for agent type annotations in `InvestmentState` — LangGraph calls `get_type_hints()` at StateGraph construction which cannot resolve forward references
- `lockin.agents.types` eagerly imported in `agents/__init__` (no graph deps); mock/llm/base imports deferred — allows `state.py` to safely `from lockin.agents.types import ...`
- BASE_RATE_TABLE values all `success_rate: None` — Phase 5 Validation will backfill empirical rates; academic defaults from published papers used as placeholders

**Plan 02-02 Implementation (2026-02-22):**
- Cache raw DataFrames (not FundamentalsResult) so point-in-time filtering applies post-cache for any requested date
- Store fetched_at in raw cache dict so cached results preserve the original fetch timestamp (enables cache hit detection)
- yfinance field names are multi-word labels ("Total Revenue", not "TotalRevenue") — verified live against AAPL before coding
- NAPM series unavailable on FRED — manufacturing_pmi returns None gracefully (series deleted from public FRED)
- get_series_as_of_date() returns DataFrame with [realtime_start, date, value] columns (not a Series)
- fiscal_year_end taken from income_stmt.columns[0] after PIT filter; balance_sheet used as fallback

**Plan 02-04 Implementation (2026-02-22):**
- LOOKAHEAD_DAYS defined as module constant dict (prices=0, fundamentals=7, macro=14) — informational metadata for orchestration agents
- _NoMacroSource fallback defers DataUnavailableError to call-time when FRED_API_KEY absent — importing lockin.data never crashes
- Live bypass calls source with as_of_date=None (not date.today()) — sources treat None as "latest available"
- fiscal_year_end fallback: if not in result, use as_of_date or date.today() for storage key
- store_asset called before store_fundamentals to satisfy foreign key dependency in assets table
- Public API pattern: agents import from lockin.data only, never from submodules directly
- Lazy singleton: _default_pit + _default_validator initialized on first call (no import-time network calls)
- Storage non-fatal: try/except around all DB writes, print to stderr, always return data

**Plan 02-03 Implementation (2026-02-22):**
- Sentinel thread_id "data_validation" used in audit logs from DataValidator — validator has no LangGraph thread context; static string identifies the source clearly
- FRED_SERIES_IDS duplicated in storage.py (not imported from fred_source.py) to avoid circular imports between data source and storage modules
- observation_date stored as NULL in macro_data by store_macro_data — FRED observation date parsing is fred_source.py's responsibility (plan 02-04)
- Storage errors caught and logged to stderr, never re-raised — a DB outage at storage time must not propagate back to fail the data fetch pipeline
- HITL threshold >200% change: warning-only for 50-200% (outlier_flags set, no HITL), HITL trigger for >200%

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

### Phase 2 - Data Layer (COMPLETE)
- [x] 02-01: Types, protocols, exceptions, TTL cache (DONE)
- [x] 02-02: YFinanceSource + FREDSource — implement DataSourceProtocol + MacroSourceProtocol (DONE)
- [x] 02-03: DataValidator + storage functions + DB setup script (DONE)
- [x] 02-04: PointInTimeData wrapper + public API + integration tests (DONE)

### Phase 3 - Agents + RAG (In Progress)
- [x] 03-01: Shared agent infrastructure — LLM factory, typed dataclasses, Settings update, InvestmentState typed fields (DONE)
- [ ] 03-02: Macro Oracle agent
- [ ] 03-03: Value Hunter agent
- [ ] 03-04: Bear agent
- [ ] 03-05: Strategist agent
- [ ] 03-06: Guardian agent
- [ ] 03-07: Judge agent
- [ ] 03-08: Optimizer agent
- [ ] 03-09: RAG ingestion pipeline
- [ ] 03-10: RAG retrieval integration
- [ ] 03-11: Phase 3 integration tests

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

**Last session:** 2026-03-17
**Activity:** Executed Phase 3 plan 03-01 — shared agent infrastructure (LLM factory, typed dataclasses, Settings, InvestmentState typed fields).
**Stopped at:** Completed 03-01-PLAN.md (3/3 tasks, 3 commits). Phase 3 plan 1 of 11 done.
**Resume file:** None

**When resuming:**
1. Review STATE.md (this file)
2. Begin Phase 3 plan 03-02 (Macro Oracle agent)
3. Agent infrastructure ready: from lockin.agents import get_llm, invoke_agent, BASE_RATE_TABLE, ConfidenceModifier

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
**Status:** Complete ✓
**Completed:** 2026-02-22
**Dependencies:** Phase 1 complete ✓
**Plan 02-01:** Complete ✓ — types.py, exceptions.py, protocols.py, cache.py
**Plan 02-02:** Complete ✓ — yfinance_source.py, fred_source.py
**Plan 02-03:** Complete ✓ — validator.py, storage.py, scripts/setup_data_tables.py
**Plan 02-04:** Complete ✓ — point_in_time.py, __init__.py (public API), tests/integration/test_data_pipeline.py (15 tests)

### Phase 3 - Agents & RAG
**Status:** In Progress (1/11 plans complete)
**Dependencies:** Phase 1, 2 complete
**Plan 03-01:** Complete ✓ — shared infra: LLM factory, typed dataclasses, Settings, InvestmentState typed fields

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
**Last commit:** d31d84e — feat(03-01): update InvestmentState with typed agent output fields

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

**Data Layer Contracts (02-02):**
- YFinance: `from lockin.data.yfinance_source import YFinanceSource`
- FRED: `from lockin.data.fred_source import FREDSource, FRED_SERIES`

**Data Layer Contracts (02-03):**
- Validator: `from lockin.data.validator import DataValidator`
- Storage: `from lockin.data.storage import store_fundamentals, store_macro_data, store_asset, FINANCIAL_FIELDS, FRED_SERIES_IDS`
- DB setup: `uv run python scripts/setup_data_tables.py` (run after setup_db.py)

**Data Layer Public API (02-04) — agents use ONLY this:**
- Fundamentals: `from lockin.data import get_fundamentals`
- Macro: `from lockin.data import get_macro_indicators`
- PIT wrapper: `from lockin.data import PointInTimeData`
- All types/exceptions re-exported: `from lockin.data import FundamentalsResult, MacroResult, DataUnavailableError, ...`
- Integration tests: `python -m pytest tests/integration/test_data_pipeline.py -v` (15 tests, no network required)

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
*Last updated: 2026-02-22 after Phase 2 plan 02-02 completion*
