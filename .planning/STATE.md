# Project State: AI-Investment Swarm

**Last Updated:** 2026-03-18
**Current Phase:** Phase 3 - Agents + RAG (In Progress — 03-11 auto tasks done, awaiting human checkpoint)
**Status:** Phase 2 complete — Phase 3 in progress (03-01 through 03-11 auto tasks done; 03-11 checkpoint pending human verify)

---

## Project Reference

**Building:** AI-Investment Swarm — Sistema multi-agente con síntesis Bayesiana para análisis de inversiones Value Investing híbrido (Graham × VeTO × VoMC)

**Core Value:** Transparencia total mediante arquitectura "caja de cristal" — cada decisión trazable, explicable, auditable.

**Current Focus:** Phase 3 Agents + RAG — executing plans 03-01 through 03-11.

---

## Current Position

**Phase:** 3 of 6 (Phase 3 — Agents + RAG, Awaiting human checkpoint)
**Progress:** ██████████████████ 64% (Phase 1 + Phase 2 complete + 03-01 through 03-11 auto tasks done)
Last activity: 2026-03-18 - Executed 03-11-PLAN.md (auto tasks); checkpoint pending human verify

```
✓ Phase 0 - Planning      [██████████] 100%
✓ Phase 1 - Foundation    [██████████] 100%  (3/3 plans, verified 13/13)
✓ Phase 2 - Data Layer    [██████████] 100%  (4/4 plans: 02-01, 02-02, 02-03, 02-04 complete)
  Phase 3 - Agents + RAG  [██████████]  ~99%  (11/11 plans: 03-01..03-11 auto tasks done; 03-11 checkpoint pending)
  Phase 4 - Integration   [░░░░░░░░░░]   0%
  Phase 5 - Validation    [░░░░░░░░░░]   0%
  Phase 6 - Interface     [░░░░░░░░░░]   0%
```

---

## Recent Decisions

**Plan 03-11 Implementation (2026-03-18):**
- Module-level imports for retrieve_with_citations, ragas_evaluate, faithfulness, answer_relevancy in evaluation.py — unittest.mock.patch requires attribute to exist at module level; lazy import inside function body is not patchable (same fix as 03-07 PdfReader)
- ragas 0.4.x singleton metric instances (from ragas.metrics import faithfulness) — simpler than ragas.metrics.collections which requires LLM arg in constructor; works correctly in 0.4.x
- Graceful degradation returns error dict (not exception) when SUPABASE_URL/KEY absent — consistent with retrieve_with_citations returning [] on no config
- EvaluationResult._repr_dict used for mean score extraction — only place ragas 0.4 exposes per-metric means as dict

**Plan 03-10 Implementation (2026-03-18):**
- Jaccard similarity on top-20 most frequent words with 0.85 threshold for argument exhaustion detection — simple, no NLP deps, reproducible; minor word additions (normal in one rebuttal) don't trigger early termination
- should_continue_dialectic() returns "value_hunter" (not "bear") for continue case — conditional edge mapping has only "value_hunter" and "strategist" as valid destination keys; "bear" caused KeyError
- guardian veto routing reads guardian_modifier.circuit_breaker first (typed ConfidenceModifier from real guardian), falls back to guardian_veto boolean (mock guardian backward compat) — both agents work correctly
- E2E stubs return real typed dataclasses (ConfidenceModifier, ValueDistribution, JudgeOutput) not raw dicts — tests the actual type contracts enforced by judge_math.run_judge_algorithm
- run_judge_algorithm() called inside stub_judge_normal/hitl — real Bayesian math without LLM/yfinance network calls; judge_output is a valid JudgeOutput in all E2E tests
- autouse pytest fixture patches lockin.utils.audit.get_settings to empty DATABASE_URL — all E2E tests use stderr audit logging, no Supabase connection needed
- Phase 1 tests/test_graph_e2e.py failures are pre-existing (Supabase creds invalid, Google API key missing) — confirmed by running stash before changes; not regressions from this plan

**Plan 03-08 Implementation (2026-03-18):**
- judge_math.py is pure (no yfinance/LLM/RAG imports) — entire 7-step algorithm testable without mocks; 35 tests run in 0.05s
- HITL threshold 0.40 (NOT 0.50): p_final < 0.40 = HOLD per Notion spec v1.0; regression guard test `test_judge_no_hitl_p_045` prevents reversion to old Foundation scaffold threshold
- compute_recommendation decision order: `current_price > precio_target` (PASS for overvaluation) checked BEFORE `p_final < 0.40` (HOLD for low probability) — strict ordering matters for correct behavior
- KELLY_FRACTION = 0.33 (Kelly/3): more conservative than Kelly/4 since system lacks Phase 5 empirical base rates yet
- data_quality_factor returns 0.5 when data_coverage.available is empty (neutral weight, prevents zero-weight collapse)
- current_price fallback = geometric mean of bull/bear expected values when yfinance unavailable (not hardcoded 100.0)
- Sentinel pattern for mutable default args in test fixtures: use `missing is None` check (not `missing or [default]`) — empty list `[]` is falsy in Python

**Plan 03-09 Implementation (2026-03-18):**
- KELLY_FRACTION = 0.33 (Kelly/3, NOT Kelly/4) — Notion spec explicitly specifies this; judge_math pre-applies the 1/3 fractional before writing kelly_fraction to JudgeOutput
- MAX_POSITION_SIZE = 0.10 (10% hard cap), MAX_SECTOR_ALLOCATION = 0.325 (midpoint 30-35%), CIRCUIT_BREAKER_OVERRIDE_CAP = 0.02 — all constants from Notion spec
- HOLD -> 0 new capital — HOLD means maintain existing position, not add new; only BUY triggers Kelly allocation
- circuit_breaker_override caps at <=2% (applied after BUY sizing); circuit_breaker with no override -> hard 0
- yfinance sector fetch is best-effort (try/except, defaults to "Unknown") — network failure must not crash deterministic position sizing
- MODEL_FLASH for LLM narrative — prose summary does not need MODEL_PRO reasoning quality
- position_cap_applied flag uses `kelly_fraction > MAX_POSITION_SIZE and position_size <= MAX_POSITION_SIZE` (precise check) vs plan's round() comparison (imprecise for floats)
- 16 tests (vs 9 required minimum): added output structure, metrics sub-keys, and LLM fallback tests for full coverage

**Plan 03-07 Implementation (2026-03-17):**
- PdfReader imported at module level in ingestion.py — unittest.mock.patch requires attribute to exist on module object; lazy import inside function body is not patchable
- ivfflat index with lists=100 on rag_documents embedding — standard Supabase pgvector pattern for cosine similarity; appropriate for expected document volume (<1M rows)
- Idempotency via DELETE+INSERT for chunks (not per-chunk UPSERT) — chunk count/content can change on re-ingest; UPSERT on documents preserves UUID
- Table name "rag_documents" throughout (not "embeddings") per plan IMPORTANT CONTEXT
- match_documents RPC uses filter JSONB parameter for metadata filtering via SupabaseVectorStore

**Plan 03-04 Implementation (2026-03-17):**
- VeTO signal: `has_base_rate=False` — informational only in Phase 3, no empirical validation; does NOT adjust probability. Only adjusts `variance_adjustment += 0.10` when `veto_score < 0.4`.
- VeTO does NOT adjust `margin_adjustment` — deferred to Phase 4 per CONTEXT.md. Strategist code documents this explicitly with inline comment.
- `analyst_momentum` signal: `has_base_rate=True`, `base_rate_source="Jegadeesh (2004)"` — academic support for revision momentum; adjusts `margin_adjustment += 0.05` ONLY for net analyst downgrades.
- `circuit_breaker` always False — Guardian is the circuit-breaker agent; Strategist is a Modifier, never vetoes investment.
- Module-level `_TRANSCRIPT_CACHE: dict[str, str]` for FMP API — free tier 250 req/day; cache per ticker avoids redundant calls.
- LLM JSON parsing strips markdown code blocks + fills defaults on failure — ensures agent never crashes even with malformed LLM response.

**Plan 03-03 Implementation (2026-03-17):**
- Valuation model selection heuristic: financial/tech -> RIM; mature -> EVA; default -> EPV — routes to best model for company type
- Log-normal sigma adjusted by Piotroski F-Score: F>=7 -> sigma*0.85 (narrow); F<=3 -> sigma*1.20 (wide); else DEFAULT_SIGMA=0.20
- Piotroski prior-year approximation: scale current-year metrics by 0.90 as synthetic prior; flagged in quality_metrics.synthetic_prior=True
- Shares outstanding derived from net_income / diluted_eps — FundamentalsResult lacks direct shares_outstanding field
- TDD cycle: 4 atomic commits (RED test, GREEN impl, RED test, GREEN impl); 33 total tests (21 formula + 12 agent), all passing

**Plan 03-02 Implementation (2026-03-17):**
- MODEL_FLASH for Macro Oracle — structured quantitative task; PRO quota reserved for Value Hunter, Bear, Judge (per 03-CONTEXT.md)
- Deterministic overrides LLM for yield_curve and fed_stance — inverted if yield_10y_2y<0 OR yield_10y_3m<0; hawkish if fed_funds>4.0; no judgment needed
- margin_adjustment=+0.175 — midpoint of [+0.15, +0.20] spec range for extreme greed (expansion+risk_on+normal curve)
- macro_confidence clamped to [0.3, 0.95] — 0.3 floor for minimal weight without FRED data; 0.95 cap prevents overconfidence
- circuit_breaker always False for Oracle — Oracle adjusts trust, never blocks

**Plan 03-05 Implementation (2026-03-17):**
- Bear sigma=0.25 (fixed constant) — wider than Bull's ~0.20 to reflect greater uncertainty in bearish case; simple constant avoids instability on sparse fundamentals
- EPV uses operating_income as EBIT proxy; fallback to net_income gross-up by (1-tax_rate) — always computable even with sparse data
- DataCoverage.missing hardcoded to 3 structural unknowns (competitive_threat_detail, regulatory_risk, insider_sentiment) — cannot be derived from fundamentals alone
- store=False in Bear's get_fundamentals call — Bear is read-only; Bull (Value Hunter) already stored the same fundamentals
- LLM fallback: silent stderr + safe defaults — LLM failure must not crash the dialectic loop
- Net-cash adjustment applied to NOPAT-based EPV: epv_equity = epv + cash - debt (standard EPV formula for equity value)

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
- [x] 03-02: Macro Oracle agent — deterministic+LLM regime detection, ConfidenceModifier output, FRED fallback (DONE)
- [x] 03-03: Value Hunter agent — EPV/EVA/RIM + log-normal ValueDistribution + LLM thesis (DONE)
- [x] 03-04: Strategist agent — ConfidenceModifier with VeTO (variance only, has_base_rate=False) + analyst momentum (Jegadeesh 2004), 8 unit tests (DONE)
- [x] 03-05: Bear adversarial agent — independent pessimistic EPV + ValueDistribution (DONE)
- [x] 03-06: Guardian agent (DONE)
- [x] 03-07: Judge agent (DONE)
- [x] 03-08: Judge agent — judge_math.py (7-step pure algorithm) + judge.py (LangGraph agent), 43 tests (DONE)
- [x] 03-09: Optimizer agent (DONE)
- [x] 03-10: Graph wiring + E2E tests — real agents in builder.py, argument exhaustion, 5 E2E tests (DONE)
- [~] 03-11: RAG retrieval integration (auto tasks done; checkpoint:human-verify pending)
- [ ] 03-12: Phase 3 integration tests

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

**Last session:** 2026-03-18
**Activity:** Executed Phase 3 plan 03-11 auto tasks — RAGAs evaluation module (evaluation.py) + 3 integration tests (test_ragas.py). Stopped at checkpoint:human-verify.
**Stopped at:** 03-11-PLAN.md auto tasks done (2/2, 2 commits). Checkpoint pending human verification.
**Resume file:** None

**When resuming (after checkpoint approval):**
1. Review STATE.md (this file)
2. Phase 3 is complete after checkpoint is approved — proceed to Phase 4 Integration
3. RAGAs evaluation: `from lockin.rag.evaluation import evaluate_rag` — runs faithfulness + answer_relevancy
4. Full pipeline: `from lockin.graph.builder import create_graph` uses all 7 real agents by default
5. RAG modules: `ls src/lockin/rag/` — ingestion.py, retriever.py, evaluation.py, __init__.py

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
**Status:** In Progress (3/11 plans complete)
**Dependencies:** Phase 1, 2 complete
**Plan 03-01:** Complete ✓ — shared infra: LLM factory, typed dataclasses, Settings, InvestmentState typed fields
**Plan 03-02:** Complete ✓ — Macro Oracle agent: FRED regime detection, ConfidenceModifier (circuit_breaker=False), macro_base_rate signal, 6 unit tests
**Plan 03-05:** Complete ✓ — Bear adversarial agent: pessimistic EPV, log-normal ValueDistribution (sigma=0.25), 5 red-flag signals, 10 unit tests
**Plan 03-08:** Complete ✓ — Judge agent: judge_math.py (7-step pure Bayesian algorithm, 35 tests) + judge.py (LangGraph agent, LLM narrative, HITL at p<0.40 or circuit_breaker, 8 tests)
**Plan 03-10:** Complete ✓ — Graph wiring: real agents as defaults, is_argument_exhausted() Jaccard detection, guardian_modifier.circuit_breaker routing, 5 E2E tests
**Plan 03-11:** Auto tasks complete ✓ (checkpoint pending) — RAGAs evaluation module: create_eval_dataset + evaluate_rag, graceful no-config degradation, 3 integration tests

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
**Last commit:** 6d7186b — feat(03-11): add RAGAs integration tests + fix module-level imports

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
*Last updated: 2026-03-18 after Phase 3 plan 03-08 completion*
