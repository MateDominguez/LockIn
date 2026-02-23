# Phase 3: Agents & RAG - Context

**Gathered:** 2026-02-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement all 7 real agents (replacing mock agents from Phase 1) with actual LLM calls, dialectical
Bull-Bear reasoning, risk veto logic, and RAG over financial bibliography. Agents use the public
data API from Phase 2 (`from lockin.data import get_fundamentals, get_macro_indicators`).

Backtesting, paper trading, and the Streamlit dashboard are separate phases.

</domain>

<decisions>
## Implementation Decisions

### Bull-Bear Dialectic Design

- Bear builds its thesis **completely blind** to Bull's analysis — independent adversarial
  investigation from scratch, not a rebuttal. Prevents anchoring on Bull's framing.
- After both present their initial theses, **Judge mediates the debate**: if signal divergence is
  significant, Judge sends one or both agents back to refine or reinforce their case.
- Stopping criteria: **"argument exhaustion" OR hard cap of 3 cycles** — whichever comes first.
  Judge evaluates whether each refinement round added substantive new evidence or data points.
  If a refinement is mostly rephrasing the previous version (no new substance), that's exhausted.
  This mirrors UN-style debate: parties stop when they have nothing new to add, not when they agree.
- Bull and Bear are NOT expected to converge — Judge synthesizes a posterior from two strong,
  opposing, well-argued positions.

### Simplified VeTO Scope (Strategist Agent)

- **Simplified VeTO = three signals combined:**
  1. Earnings call NLP via FMP API (Financial Modeling Prep free tier: 250 req/day)
     — keyword frequency + tone/sentiment (Claude's Discretion on exact implementation)
  2. Analyst consensus shifts from yfinance `upgrades_downgrades` (already in Phase 2 data layer)
     — net upgrade/downgrade direction over last 90 days
  3. News sentiment — deferred (not in Phase 3 scope)
  4. Insider trading signals — deferred
- Insider trading and news sentiment are NOT included in Phase 3 simplified VeTO.
- **VeTO score is INFORMATIONAL ONLY in Phase 3** — does not automatically adjust the margin
  of safety calculation yet. Judge sees it as context. Full margin-of-safety wiring deferred.
- NLP analysis of transcripts: Claude's Discretion on whether to use keyword counting or
  LLM-based extraction — choose the approach that balances quality with Phase 3 scope.

### RAG — Vector Store

- **Supabase pgvector** — already in stack (PostgreSQL + pgvector extension). No new service.
  The Notion DB schema already specifies `chunks` and `embeddings` tables. Parent Document
  Retriever supported. Migrate to Pinecone if/when v2 SaaS requires multi-tenant scale.

### RAG — Initial Document Corpus

Three document types to ingest:
1. **SEC 10-K filings** — last 3 years per company (3 × 10-K per ticker in the watchlist).
   Source: SEC EDGAR. Free, no API key.
2. **Earnings call transcripts** — via FMP API (same source as Strategist/VeTO). Double-use:
   index in RAG for citations in agent reasoning.
3. **Academic/investment books (PDFs)** — manual ingestion. Minimum: Graham's *Security Analysis*
   and *The Intelligent Investor*. Additional papers as available.

### LLM Strategy

- **Provider:** Google Gemini only (for now). Architecture must allow per-agent model swapping
  via config without code changes.
- **Per-agent model config in Settings** — each agent has a `model` key in config/settings.
  Override any agent's model by changing one value in `.env` or config file.
- **Model split (default config):**
  - `gemini-2.5-pro`: Value Hunter (Bull), Bear, Judge — deepest analytical reasoning required
  - `gemini-2.0-flash`: Macro Oracle, Strategist, Guardian, Optimizer — structured/quantitative tasks
- Rationale: Pro quota (1500 req/day) reserved for the three agents where reasoning quality
  is most critical (valuation, adversarial thesis, Bayesian synthesis).

### Claude's Discretion

- VeTO NLP implementation detail: keyword extraction vs LLM-based scoring
- Earnings transcript chunking strategy for RAG (semantic vs. fixed-size)
- Exact embedding model for pgvector (e.g., `text-embedding-004`)
- Guardian's quantitative calculations (Z-Score, M-Score, VoMC math) are deterministic —
  no discretion needed, implement per Notion spec exactly

</decisions>

<specifics>
## Specific Ideas

- **Bear "from scratch" philosophy**: The Notion page explicitly states Bear is NOT reactive —
  it builds "the best bearish thesis possible" independently. This is architecturally important:
  Bear receives ticker + raw data, NOT the Bull's output.
- **Debate exhaustion = no new substance**: If an agent's refinement round is semantically
  very similar to its previous version, Judge recognizes the argument is exhausted and stops
  the loop. This mirrors how debates work: you stop when parties have nothing new to add.
- **FMP for transcripts**: Free tier is 250 req/day. This covers VeTO AND RAG ingestion for
  the transcript corpus. Manage quota carefully — cache aggressively.
- **pgvector justification**: Already Supabase users. The Notion schema already defines
  `chunks` and `embeddings` tables. Zero new infrastructure.
- **3 years of 10-Ks**: Chosen to cover trend analysis without excessive storage. Each 10-K
  is large (hundreds of pages) so 3 years balances context vs. ingestion cost.

</specifics>

<deferred>
## Deferred Ideas

- Insider trading signals (Strategist) — future phase or v2
- News sentiment aggregation — future phase or v2
- VeTO margin-of-safety wiring (VeTO score adjusting margin by ±5-10%) — Phase 4 Integration
- Migration from pgvector to Pinecone — v2 SaaS when multi-tenant scale is needed
- OpenAI / Claude API as agent LLM providers — possible in v2 or if Gemini quota is insufficient
- Full VeTO NLP model (clustering, absorption capacity scoring per Notion full spec) — v2

</deferred>

---

*Phase: 03-agents-rag*
*Context gathered: 2026-02-23*
