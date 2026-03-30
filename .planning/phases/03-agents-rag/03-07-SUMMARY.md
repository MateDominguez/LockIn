---
phase: "03"
plan: "07"
subsystem: "rag"
tags: ["rag", "pgvector", "supabase", "langchain", "pypdf", "edgar", "embeddings", "text-embedding-004"]

dependency-graph:
  requires:
    - "03-01"  # LLM factory and shared agent infra (GoogleGenerativeAIEmbeddings)
    - "02-03"  # DB setup patterns (psycopg, setup scripts)
  provides:
    - "RAG ingestion pipeline (PDF, 10-K, transcript)"
    - "Parent Document Retriever with citation tracking"
    - "rag_documents, documents, chunks tables + match_documents RPC"
  affects:
    - "03-10"  # RAG retrieval integration into agents
    - "03-11"  # Phase 3 integration tests

tech-stack:
  added:
    - "pypdf>=4.0.0 (PDF text extraction)"
    - "langchain-text-splitters (RecursiveCharacterTextSplitter)"
    - "langchain-community.vectorstores.SupabaseVectorStore"
    - "edgar (SEC 10-K fetching)"
  patterns:
    - "Parent Document Retriever: 1500/200 parent chunks, 500/50 child chunks with embeddings"
    - "Idempotent UPSERT on (source_type, source_id) for all ingestion functions"
    - "Graceful degradation: returns None/[] when DATABASE_URL or Supabase env vars absent"
    - "Module-level imports for testability (PdfReader at top of ingestion.py)"

key-files:
  created:
    - "scripts/setup_rag_tables.py"
    - "src/lockin/rag/ingestion.py"
    - "src/lockin/rag/retriever.py"
    - "src/lockin/rag/__init__.py"
    - "tests/unit/test_rag.py"
  modified: []

decisions:
  - id: "rag-001"
    choice: "PdfReader imported at module level (not lazily inside ingest_pdf)"
    rationale: "unittest.mock.patch requires attribute to exist at module level; lazy import inside function body is not patchable as lockin.rag.ingestion.PdfReader"
    alternatives: ["patch pypdf.PdfReader globally", "keep lazy import and patch pypdf module directly"]

  - id: "rag-002"
    choice: "json imported at module level alongside pathlib"
    rationale: "Eliminates __import__('json') calls and redundant per-function imports; cleaner code"
    alternatives: ["keep __import__('json') pattern from legacy code"]

  - id: "rag-003"
    choice: "ivfflat index with lists=100 on rag_documents embedding column"
    rationale: "Supabase pgvector standard for cosine similarity search; lists=100 appropriate for expected document volume (<1M rows)"
    alternatives: ["hnsw index (no lists parameter, better recall at scale)"]

  - id: "rag-004"
    choice: "Idempotency via DELETE+INSERT (not UPDATE) for chunks"
    rationale: "Chunk count and content can change on re-ingest; simpler to delete all old chunks and reinsert than diff. UPSERT on documents table preserves document UUID."
    alternatives: ["full UPSERT with conflict resolution per chunk"]

metrics:
  duration: "4m 28s"
  completed: "2026-03-17"
  tasks-completed: 2
  tests-added: 3
  tests-passing: 3
---

# Phase 3 Plan 07: RAG Infrastructure Summary

**One-liner:** pgvector RAG pipeline with Parent Document Retriever (1500/500-char parent/child splits), idempotent PDF/10-K/transcript ingestion via text-embedding-004, and citation-aware retrieval from rag_documents table.

---

## What Was Built

### Task 1: RAG Tables and Ingestion Pipeline

**`scripts/setup_rag_tables.py`** — Idempotent schema setup script:
- Enables `vector` extension
- Creates `documents` table (source registry with UPSERT key `source_type + source_id`)
- Creates `chunks` table (parent and child chunks with `is_parent` flag and `parent_id` self-reference)
- Creates `rag_documents` table (child chunks + `vector(768)` embedding column, ivfflat index)
- Creates `match_documents(query_embedding, match_count, filter)` PL/pgSQL RPC function used by `SupabaseVectorStore`

**`src/lockin/rag/ingestion.py`** — Three public ingestion functions:

- `ingest_pdf(file_path, source_id=None, metadata=None) -> str`
  - Extracts text via `pypdf.PdfReader`
  - Splits with `RecursiveCharacterTextSplitter`: 1500/200 parent, 500/50 child
  - Embeds child chunks via `GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")`
  - UPSERT document + stores parent + child chunks in DB
  - Returns `document_id` UUID

- `ingest_10k(ticker, years=3) -> list[str]`
  - Fetches 10-K filings via `edgar.Company(ticker).get_filings(form="10-K").latest(years)`
  - Same chunking/embedding pipeline as PDF
  - Source ID keyed as `10k:{ticker}:{filing_date}` for idempotency
  - Returns `[]` gracefully if DATABASE_URL absent

- `ingest_transcript(ticker, quarter, year, transcript_text) -> str`
  - Validates quarter in 1-4
  - Source ID: `transcript:{ticker}:Q{quarter}{year}`
  - Same pipeline; raises RuntimeError if DATABASE_URL not set

All functions are idempotent via DELETE+INSERT for chunks and UPSERT for documents.

### Task 2: Parent Document Retriever with Citations

**`src/lockin/rag/retriever.py`** — Two public retrieval functions:

- `get_retriever(k=5) -> retriever | None`
  - Initializes `SupabaseVectorStore(table_name="rag_documents", query_name="match_documents")`
  - Returns `None` gracefully if `SUPABASE_URL` or `SUPABASE_KEY` absent

- `retrieve_with_citations(query, k=5) -> list[dict]`
  - Calls `get_retriever` — returns `[]` if None
  - For each result builds citation dict:
    - `content`, `source_type`, `source_id`, `section`, `page`, `chunk_index`, `relevance_score`
  - Returns `[]` on any retrieval error

**`src/lockin/rag/__init__.py`** — Exports all 5 public functions.

**`tests/unit/test_rag.py`** — 3 unit tests, all passing:
1. `test_retrieve_with_citations_returns_list` — mocked SupabaseVectorStore, verifies all 7 citation keys present and values correct
2. `test_retrieve_graceful_no_config` — env vars absent, confirms empty list returned
3. `test_ingest_pdf_chunking` — mocked pypdf + embeddings + DB connection, verifies chunking called embed_documents with non-empty list and conn.close() called

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] PdfReader lazy import prevented mocking**

- **Found during:** Task 2 (test execution — test_ingest_pdf_chunking FAILED)
- **Issue:** `PdfReader` was imported lazily inside `ingest_pdf` body (`from pypdf import PdfReader`). `unittest.mock.patch("lockin.rag.ingestion.PdfReader", ...)` requires the attribute to exist on the module object at patch time.
- **Fix:** Moved `from pypdf import PdfReader` to module top-level in `ingestion.py`. Also moved `import pathlib` and `import json` to module level for consistency.
- **Files modified:** `src/lockin/rag/ingestion.py`
- **Commit:** fbad712

---

## Verification Results

```
python -m pytest tests/unit/test_rag.py -v
  PASSED  tests/unit/test_rag.py::TestRetrieveWithCitationsReturnsList::test_retrieve_with_citations_returns_list
  PASSED  tests/unit/test_rag.py::TestRetrieveGracefulNoConfig::test_retrieve_graceful_no_config
  PASSED  tests/unit/test_rag.py::TestIngestPdfChunking::test_ingest_pdf_chunking
  3 passed in 4.09s

from lockin.rag import retrieve_with_citations, ingest_pdf  # imports cleanly ✓
Table name "rag_documents" throughout (not "embeddings")    # verified ✓
match_documents RPC defined in setup_rag_tables.py          # verified ✓
```

---

## Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| rag-001 | PdfReader at module level | Enables `unittest.mock.patch` to work |
| rag-002 | json/pathlib at module level | Cleaner, eliminates __import__ calls |
| rag-003 | ivfflat index, lists=100 | Supabase standard; appropriate for expected volume |
| rag-004 | DELETE+INSERT for chunks idempotency | Simpler than per-chunk UPSERT when chunk count can change |

---

## Next Phase Readiness

**Plan 03-07 is complete.** RAG infrastructure ready for:
- **03-10** (RAG retrieval integration): `from lockin.rag import retrieve_with_citations` — agents can query RAG with citations
- **03-11** (Phase 3 integration tests): ingestion/retrieval pipeline testable end-to-end

**To use RAG in production:**
1. Run `uv run python scripts/setup_rag_tables.py` once
2. Set `SUPABASE_URL`, `SUPABASE_KEY`, `GOOGLE_API_KEY` in `.env`
3. Call `ingest_pdf()`, `ingest_10k()`, `ingest_transcript()` to index documents
4. Call `retrieve_with_citations(query)` in agent nodes

**No blockers for subsequent plans.**
