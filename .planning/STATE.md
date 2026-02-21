# Project State: AI-Investment Swarm

**Last Updated:** 2026-02-21
**Current Phase:** Phase 1 - Foundation (In Progress)
**Status:** Plan 01-02 complete (StateGraph + audit trail)

---

## Project Reference

**Building:** AI-Investment Swarm — Sistema multi-agente con síntesis Bayesiana para análisis de inversiones Value Investing híbrido (Graham × VeTO × VoMC)

**Core Value:** Transparencia total mediante arquitectura "caja de cristal" — cada decisión trazable, explicable, auditable.

**Current Focus:** Phase 1 Foundation — plans 01-01 and 01-02 complete, continue with HITL (01-03)

---

## Current Position

**Phase:** 1 (Foundation) of 6
**Plan:** 2 of 3 in Phase 1
**Progress:** █████░░░░░ 57% (2/3 Phase 1 plans complete)

```
✓ Phase 0 - Planning      [██████████] 100%
  Phase 1 - Foundation    [██████░░░░]  67%  (plans 01-01 + 01-02 done)
  Phase 2 - Data Layer    [░░░░░░░░░░]   0%
  Phase 3 - Agents + RAG  [░░░░░░░░░░]   0%
  Phase 4 - Integration   [░░░░░░░░░░]   0%
  Phase 5 - Validation    [░░░░░░░░░░]   0%
  Phase 6 - Interface     [░░░░░░░░░░]   0%
```

---

## Recent Decisions

**Plan 01-02 Implementation (2026-02-21):**
- Separate short-lived psycopg.connect() for audit writes — LangGraph checkpointer holds open transactions; sharing connection can deadlock or corrupt checkpoint state
- audit_logs table schema (Supabase) uses `payload` JSONB (not `state_snapshot`) — adapted INSERT to match actual schema discovered at runtime
- agent_start logs only asset_ticker + bull_iteration (minimal payload); agent_end logs full agent output dict
- MAX_BULL_BEAR_ITERATIONS=2 constant defined in builder.py — bear runs twice, value_hunter rebuts twice, then exits to strategist
- Conditional edge mapping uses string `'__end__': END` for guardian veto path — confirmed END == '__end__' in LangGraph

**Plan 01-01 Implementation (2026-02-21):**
- TypedDict total=False for InvestmentState — LangGraph StateGraph requires TypedDict for partial merge; Pydantic/dataclass would need extra conversion
- bull_iteration lives in InvestmentState and is incremented by mock_bear — conditional edge reads this to count debate rounds
- mock_value_hunter emits bull_refined_thesis + bull_defense only when bull_iteration > 0 — mirrors real agent's post-debate output path
- Settings defaults all missing .env vars to empty string — agents validate required keys at call-time, not import-time

**Agent Architecture Finalized (2026-02-08):**
- ✓ 7 agents for v1 (Macro Oracle, Value Hunter, Strategist, Bear, Guardian, Judge, Optimizer)
- ✓ Bull-Bear dialectical iteration (minimum 1 back-and-forth)
- ✓ Bayesian synthesis in Judge (not simple voting)
- ✓ Guardian veto power as constitutional rule
- ✓ Simplified VeTO in v1 (keyword + sentiment), full NLP model deferred to v2
- ✓ Chartist, Historian, Trader deferred to v2
- ✓ Watchlist analysis only (no active screening in v1)

**Data Sources (2026-02-08):**
- ✓ yfinance + FRED (single source for v1)
- Multi-source fallback deferred to v2

**Technology Stack (2026-01-31 + 2026-02-08):**
- ✓ LangGraph for orchestration
- ✓ Python + pandas/numpy/scipy
- ✓ Google AI (Gemini) for LLMs (free tier 1500 req/day)
- ✓ Supabase (PostgreSQL + pgvector) for DB + RAG
- ✓ Streamlit for dashboard
- ✓ RAGAs/DeepEval for RAG quality evaluation

**Timeline Confirmed (2026-02-08):**
- 18 weeks total (~4.5 months)
- Target completion: June 2026
- 2-3 week buffer for TFM writeup

---

## Pending Todos

### Immediate (Before Phase 1)
- [x] Review ROADMAP.md with brother for feedback (approved 2026-02-20)
- [x] Set up Supabase account + PostgreSQL instance + DB schema (2026-02-20)
- [x] Install LangGraph + dependencies (uv sync, 2026-02-20)
- [x] Create project repository structure (src/lockin/, tests/, data/, scripts/, 2026-02-20)
- [x] Initialize Python virtual environment (.venv via uv, Python 3.12, 2026-02-20)

### Short-term (Phase 1 - Week 1)
- [x] Define InvestmentState TypedDict schema (2026-02-21)
- [x] Implement mock agents (dummy functions) (2026-02-21)
- [x] Create LangGraph StateGraph structure (plan 01-02, 2026-02-21)
- [x] Implement audit trail logger (plan 01-02, 2026-02-21)
- [ ] Set up PostgreSQL checkpointing (plan 01-03)
- [ ] Implement HITL interrupt at judge node (plan 01-03)

---

## Blockers/Concerns

**None currently.**

**Future considerations:**
- Google AI rate limits (1500 req/day) — monitor in Phase 3, have OpenAI backup
- yfinance reliability — implement caching strategy in Phase 2
- RAG quality — RAGAs evaluation in Phase 3, iterate if faithfulness <90%
- Phase 3 duration (6 weeks) — longest phase, break into sub-phases if needed

---

## Session Continuity

**Last session:** 2026-02-21T04:31:35Z
**Activity:** Executed plan 01-02 — LangGraph StateGraph + audit trail
**Stopped at:** Completed 01-02-PLAN.md
**Resume file:** None

**When resuming:**
1. Review STATE.md (this file)
2. Execute plan 01-03: PostgreSQL checkpointing + HITL interrupt at judge node
3. Reference 01-02-SUMMARY.md for create_graph signature and audit_node pattern
4. Key: add `interrupt_before="judge"` to builder.compile() call in create_graph

---

## Phase Status

### Phase 0 - Planning ✓
**Status:** Complete
**Completed:** 2026-02-08
**Key Deliverables:**
- ✓ PROJECT.md (agent architecture, constitution, constraints, key decisions)
- ✓ REQUIREMENTS.md (38 v1 requirements)
- ✓ ROADMAP.md (6 phases, 18 weeks)
- ✓ Knowledge base (PRD, design principles, methodologies, theoretical foundations)
- ✓ STATE.md (this file)

### Phase 1 - Foundation
**Status:** In Progress (2/3 plans complete)
**Duration:** 2 weeks
**Goal:** LangGraph infrastructure with checkpointing + HITL
**Success Criteria:** StateGraph compiles, checkpointing works, audit trail logs all transitions, HITL interrupt functional
**Completed plans:**
- [x] 01-01 — InvestmentState TypedDict + 7 mock agents (2026-02-21)
- [x] 01-02 — LangGraph StateGraph + audit trail (2026-02-21)

### Phase 2 - Data Layer
**Status:** Not Started
**Dependencies:** Phase 1 complete

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
**Last commit:** efe1e01 - "feat(01-02): build StateGraph with 7 nodes and conditional edges"

---

## Quick Reference

**Commands:**
- Resume work: `/gsd:resume-work`
- Check progress: `/gsd:progress`
- Plan next phase: `/gsd:plan-phase 1`
- Execute phase: `/gsd:execute-phase 1` (after planning)

**Key Files:**
- Architecture: `.planning/PROJECT.md`
- Requirements: `.planning/REQUIREMENTS.md`
- Roadmap: `.planning/ROADMAP.md`
- Knowledge: `.planning/knowledge_base/`
- Research: `.planning/research/`

**Timeline:**
- Week 0-2: Phase 1 (Foundation)
- Week 2-4: Phase 2 (Data Layer)
- Week 4-10: Phase 3 (Agents + RAG)
- Week 10-12: Phase 4 (Integration)
- Week 12-15: Phase 5 (Validation)
- Week 15-18: Phase 6 (Interface)
- **Target:** June 2026

---

*State initialized: 2026-02-08*
*Last updated: 2026-02-21 after plan 01-02*
