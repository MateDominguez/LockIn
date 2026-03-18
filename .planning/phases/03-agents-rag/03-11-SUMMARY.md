---
phase: "03"
plan: "11"
subsystem: "rag"
tags: ["ragas", "evaluation", "faithfulness", "answer-relevancy", "huggingface-datasets", "pgvector", "integration-tests"]

dependency-graph:
  requires:
    - "03-07"  # RAG ingestion/retrieval pipeline (retrieve_with_citations)
    - "03-10"  # Graph wiring (full agent pipeline)
  provides:
    - "RAGAs evaluation module: create_eval_dataset() + evaluate_rag()"
    - "Faithfulness + answer_relevancy measurement against ground truths"
    - "Graceful degradation when Supabase/LLM not configured"
    - "3 integration tests covering: no-config, dataset structure, mock evaluation"
  affects:
    - "Phase 4 Integration"  # RAGAs as quality gate for RAG changes
    - "Phase 5 Validation"   # Faithfulness >90% target measured via evaluate_rag()

tech-stack:
  added:
    - "ragas>=0.2.0 (already in pyproject, now wired)"
    - "datasets (HuggingFace, transitive dependency of ragas)"
  patterns:
    - "Module-level imports for mock.patch compatibility (retrieve_with_citations, ragas_evaluate, faithfulness, answer_relevancy)"
    - "Graceful degradation: check SUPABASE_URL/KEY before evaluation, return error dict not exception"
    - "ragas 0.4.x API: singleton metric instances (from ragas.metrics import faithfulness), EvaluationResult._repr_dict for mean scores"
    - "DeprecationWarning suppression with warnings.catch_warnings at import time for ragas.metrics singleton imports"

key-files:
  created:
    - "src/lockin/rag/evaluation.py"
    - "tests/integration/test_ragas.py"
  modified:
    - "src/lockin/rag/__init__.py"  # exports create_eval_dataset, evaluate_rag

decisions:
  - id: "eval-001"
    choice: "Module-level imports for retrieve_with_citations, ragas_evaluate, faithfulness, answer_relevancy"
    rationale: "unittest.mock.patch requires attribute to exist on module object at patch time; lazy imports inside function body are not patchable as module attrs. Same fix as 03-07 PdfReader."
    alternatives: ["Keep lazy imports and patch at the ragas/langchain module level directly"]

  - id: "eval-002"
    choice: "ragas 0.4.x singleton metric instances (from ragas.metrics import faithfulness)"
    rationale: "ragas.metrics exposes pre-constructed singleton instances; the new ragas.metrics.collections API requires LLM arg in constructor. Singleton path is simpler and works correctly in 0.4.x."
    alternatives: ["ragas.metrics.collections Faithfulness(llm=...) — requires constructing LLM before metrics"]

  - id: "eval-003"
    choice: "Graceful degradation returns error dict (not exception) when SUPABASE_URL missing"
    rationale: "Matches pattern of retrieve_with_citations returning [] on no config; agents/tests should never crash on missing infra."
    alternatives: ["Raise ConfigurationError — would require callers to always handle exception"]

  - id: "eval-004"
    choice: "EvaluationResult._repr_dict for mean scores extraction"
    rationale: "ragas 0.4 EvaluationResult does not expose metric means as direct attributes; _repr_dict is populated in __post_init__ with safe_nanmean values per metric name."
    alternatives: ["result.to_pandas() then .mean() — heavier, adds pandas dependency within evaluate_rag"]

metrics:
  duration: "5min"
  completed: "2026-03-18"
  tasks-completed: 2
  tests-added: 3
  tests-passing: 3
---

# Phase 3 Plan 11: RAGAs Evaluation Suite Summary

**RAGAs faithfulness + answer_relevancy evaluation module with HuggingFace Dataset construction via retrieve_with_citations + LLM, graceful no-config degradation, and 3 mock-based integration tests.**

---

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-18T04:17:17Z
- **Completed:** 2026-03-18T04:22:18Z
- **Tasks:** 2 (auto tasks complete; Task 3 is checkpoint requiring human verification)
- **Files modified:** 3

---

## Accomplishments

- `create_eval_dataset()`: calls `retrieve_with_citations()` per question, generates answers via LLM grounded on retrieved context, builds HuggingFace Dataset with `question/answer/contexts/ground_truth` columns
- `evaluate_rag()`: runs `ragas.evaluate` with faithfulness + answer_relevancy metrics; accepts pre-built dataset, questions+truths, or 3 built-in financial smoke-test questions (Altman Z-Score, Piotroski F-Score, Kelly Criterion)
- Graceful degradation path: when `SUPABASE_URL`/`SUPABASE_KEY` absent, returns `{"faithfulness": None, "answer_relevancy": None, "error": "RAG not configured"}` without raising
- 3 integration tests all passing: no-config, dataset column structure, mock evaluation

---

## Task Commits

1. **Task 1: RAGAs evaluation module** — `0ec361d` (feat)
2. **Task 2: Integration tests + module-level import fix** — `6d7186b` (feat + Rule 1 bug fix)

---

## Files Created/Modified

- `src/lockin/rag/evaluation.py` — RAGAs evaluation module: `create_eval_dataset`, `evaluate_rag`, `_generate_answer`, `_check_rag_configured`
- `tests/integration/test_ragas.py` — 3 integration tests (mock-based, no network required)
- `src/lockin/rag/__init__.py` — added `create_eval_dataset`, `evaluate_rag` to public exports

---

## Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| eval-001 | Module-level imports for retrieve_with_citations, ragas_evaluate, metrics | unittest.mock.patch requires attribute at module level; same pattern as 03-07 PdfReader fix |
| eval-002 | ragas 0.4.x singleton instances (from ragas.metrics import faithfulness) | Simpler than ragas.metrics.collections which requires LLM arg in constructor |
| eval-003 | Graceful degradation returns error dict, not exception | Consistent with retrieve_with_citations returning [] on no config |
| eval-004 | EvaluationResult._repr_dict for mean score extraction | Only place ragas 0.4 exposes per-metric mean scores as dict |

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Lazy imports of retrieve_with_citations and ragas_evaluate prevented mocking**

- **Found during:** Task 2 (test_create_eval_dataset_structure FAILED, test_evaluate_rag_with_mock_data FAILED)
- **Issue:** Initial implementation used lazy imports inside function bodies (`from lockin.rag.retriever import retrieve_with_citations` inside `create_eval_dataset`, `from ragas import evaluate as ragas_evaluate` inside `evaluate_rag`). `unittest.mock.patch("lockin.rag.evaluation.retrieve_with_citations", ...)` raised `AttributeError: module does not have attribute 'retrieve_with_citations'` because the attribute only exists after the lazy import runs.
- **Fix:** Moved all four imports to module level: `retrieve_with_citations`, `ragas_evaluate`, `faithfulness`, `answer_relevancy`. Added `warnings.catch_warnings` block to suppress ragas DeprecationWarning at import time.
- **Files modified:** `src/lockin/rag/evaluation.py`
- **Verification:** `python -m pytest tests/integration/test_ragas.py -v` → 3 passed, 0 warnings
- **Committed in:** `6d7186b` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Fix was essential for test correctness. Same pattern established in 03-07 (PdfReader). No scope creep.

---

## Issues Encountered

None beyond the lazy-import mock-patch issue documented above.

---

## Next Phase Readiness

**Task 3 (checkpoint:human-verify) is pending.** Human must verify:
1. All tests pass: `python -m pytest tests/ -v --tb=short`
2. All agent modules exist: `ls src/lockin/agents/*.py`
3. All RAG modules exist: `ls src/lockin/rag/*.py`
4. Optionally, live run with real `GOOGLE_API_KEY` and/or real Supabase + documents

**After checkpoint approval:** Phase 3 is complete. Ready for Phase 4 Integration.

**To use RAGAs evaluation in production (after Supabase setup):**
```python
from lockin.rag import ingest_pdf
from lockin.rag.evaluation import evaluate_rag

ingest_pdf("path/to/financial_textbook.pdf")
results = evaluate_rag()  # uses built-in smoke-test questions
print(f"Faithfulness: {results['faithfulness']:.1%}")  # target >90%
```

---

*Phase: 03-agents-rag*
*Completed: 2026-03-18*
