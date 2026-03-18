"""
RAGAs evaluation suite for the LockIn RAG pipeline.

Measures faithfulness and answer relevancy of retrieved answers against ground
truths.  Target: faithfulness > 90% on a representative financial-bibliography
dataset.

Graceful degradation: when Supabase / Google credentials are absent the
functions return an error dict rather than raising exceptions.

Public API::

    from lockin.rag.evaluation import create_eval_dataset, evaluate_rag

    # Build dataset from scratch (calls retrieve_with_citations + LLM):
    dataset = create_eval_dataset(questions=[...], ground_truths=[...])

    # Run evaluation (supply dataset, or questions+truths, or use defaults):
    results = evaluate_rag()
    print(results["faithfulness"])    # float 0-1 or None
    print(results["answer_relevancy"])

Implementation notes:
- retrieve_with_citations imported at module level (required for unittest.mock.patch
  to work; lazy import inside function body is not patchable via module attribute).
- ragas_evaluate imported at module level for the same reason.
- datasets.Dataset imported at module level so tests can patch create_eval_dataset
  without hitting HuggingFace network at import time.
"""

from __future__ import annotations

import logging
import os
import sys
import warnings
from typing import Optional

# ---------------------------------------------------------------------------
# Module-level imports — required for unittest.mock.patch to work.
# (patch() replaces the attribute on the module object at patch time;
#  a lazy import inside the function body is not patchable as a module attr.)
# ---------------------------------------------------------------------------
from datasets import Dataset
from ragas import evaluate as ragas_evaluate
import warnings as _warnings

with _warnings.catch_warnings():
    _warnings.simplefilter("ignore", DeprecationWarning)
    from ragas.metrics import answer_relevancy, faithfulness

from lockin.rag.retriever import retrieve_with_citations

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in smoke-test questions (require financial bibliography to be ingested)
# ---------------------------------------------------------------------------
_DEFAULT_QUESTIONS: list[str] = [
    "What is the Altman Z-Score formula?",
    "What are the components of Piotroski F-Score?",
    "How does the Kelly Criterion determine position sizing?",
]

_DEFAULT_GROUND_TRUTHS: list[str] = [
    (
        "The Altman Z-Score formula is Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5, "
        "where X1=working capital/total assets, X2=retained earnings/total assets, "
        "X3=EBIT/total assets, X4=market cap/total liabilities, X5=sales/total assets."
    ),
    (
        "The Piotroski F-Score has nine components grouped into three categories: "
        "profitability (ROA, operating cash flow, change in ROA, accruals), "
        "leverage/liquidity/source of funds (change in leverage, change in current ratio, "
        "absence of dilution), and operating efficiency (change in gross margin, "
        "change in asset turnover)."
    ),
    (
        "The Kelly Criterion determines position sizing as f* = (bp - q) / b, "
        "where b is the net odds received, p is the probability of winning, "
        "and q is the probability of losing (1 - p). "
        "A fractional Kelly (e.g. 1/3 Kelly) is commonly used to reduce volatility."
    ),
]


def _check_rag_configured() -> bool:
    """Return True if Supabase environment variables are set."""
    return bool(
        os.environ.get("SUPABASE_URL")
        and (os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY"))
    )


def _check_llm_configured() -> bool:
    """Return True if Google API key is available."""
    if os.environ.get("GOOGLE_API_KEY"):
        return True
    try:
        from lockin.utils.config import get_settings

        return bool(get_settings().google_api_key)
    except Exception:
        return False


def _generate_answer(question: str, contexts: list[dict]) -> str:
    """
    Generate an answer for *question* using the supplied retrieved *contexts*.

    Calls the LLM with a simple prompt that grounds the answer in the provided
    context chunks.  Falls back to an empty string when the LLM is not
    configured or fails.
    """
    if not contexts:
        return ""

    context_text = "\n\n".join(c.get("content", "") for c in contexts if c.get("content"))
    if not context_text.strip():
        return ""

    try:
        from langchain_core.messages import HumanMessage

        from lockin.agents.llm import MODEL_FLASH, get_llm

        llm = get_llm(model=MODEL_FLASH, temperature=0.0)
        prompt = (
            "You are a financial research assistant. "
            "Answer the question below using ONLY the provided context. "
            "Be concise and factual.\n\n"
            f"Context:\n{context_text}\n\n"
            f"Question: {question}\n\n"
            "Answer:"
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        return response.content if hasattr(response, "content") else str(response)
    except Exception as exc:
        logger.warning("LLM answer generation failed for %r: %s", question, exc)
        return ""


def create_eval_dataset(
    questions: list[str],
    ground_truths: list[str],
) -> Dataset:
    """
    Build a HuggingFace Dataset ready for RAGAs evaluation.

    For each question:
    1. Retrieves context via ``retrieve_with_citations()`` from the configured
       Supabase vector store.
    2. Generates an answer with the LLM using the retrieved context.
    3. Assembles rows with columns: ``question``, ``answer``, ``contexts``,
       ``ground_truth``.

    Args:
        questions:    Natural-language evaluation questions.
        ground_truths: Ground-truth reference answers (one per question).

    Returns:
        ``datasets.Dataset`` with 4 columns expected by ragas ``evaluate()``.
    """
    rows: dict[str, list] = {
        "question": [],
        "answer": [],
        "contexts": [],
        "ground_truth": [],
    }

    for question, ground_truth in zip(questions, ground_truths):
        citations = retrieve_with_citations(question)
        context_strings: list[str] = [
            c["content"] for c in citations if c.get("content")
        ]
        answer = _generate_answer(question, citations)

        rows["question"].append(question)
        rows["answer"].append(answer)
        rows["contexts"].append(context_strings)
        rows["ground_truth"].append(ground_truth)

    return Dataset.from_dict(rows)


def evaluate_rag(
    dataset: Optional[Dataset] = None,
    questions: Optional[list[str]] = None,
    ground_truths: Optional[list[str]] = None,
) -> dict:
    """
    Run RAGAs faithfulness + answer_relevancy evaluation on the RAG pipeline.

    Call priority:
    1. If *dataset* is provided, use it directly.
    2. If *questions* and *ground_truths* are provided, build the dataset first
       via :func:`create_eval_dataset`.
    3. Otherwise use the three built-in smoke-test questions (requires
       financial bibliography to be ingested in Supabase).

    Args:
        dataset:       Pre-built ``datasets.Dataset`` (optional).
        questions:     List of evaluation questions (optional).
        ground_truths: Matching reference answers (optional).

    Returns:
        dict with keys:
        - ``"faithfulness"``     (float 0-1, or None on error)
        - ``"answer_relevancy"`` (float 0-1, or None on error)
        - ``"details"``          (list of per-row scores, empty on error)
        - ``"error"``            (str, only present when evaluation failed)
    """
    # ------------------------------------------------------------------
    # Graceful degradation when infrastructure not available
    # ------------------------------------------------------------------
    if not _check_rag_configured():
        logger.warning("RAG not configured: SUPABASE_URL / SUPABASE_KEY missing")
        return {
            "faithfulness": None,
            "answer_relevancy": None,
            "details": [],
            "error": "RAG not configured",
        }

    # ------------------------------------------------------------------
    # Build dataset if not supplied
    # ------------------------------------------------------------------
    if dataset is None:
        if questions is None or ground_truths is None:
            questions = _DEFAULT_QUESTIONS
            ground_truths = _DEFAULT_GROUND_TRUTHS
        try:
            dataset = create_eval_dataset(questions, ground_truths)
        except Exception as exc:
            logger.error("Dataset creation failed: %s", exc)
            return {
                "faithfulness": None,
                "answer_relevancy": None,
                "details": [],
                "error": f"Dataset creation failed: {exc}",
            }

    # ------------------------------------------------------------------
    # Run ragas evaluation
    # ------------------------------------------------------------------
    try:
        # Suppress deprecation warnings from ragas internals during evaluation
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = ragas_evaluate(
                dataset=dataset,
                metrics=[faithfulness, answer_relevancy],
                raise_exceptions=False,
                show_progress=False,
            )

        # Extract mean scores from EvaluationResult._repr_dict
        score_dict = getattr(result, "_repr_dict", {})
        faithfulness_score = score_dict.get("faithfulness")
        relevancy_score = score_dict.get("answer_relevancy")

        # Build per-row details from result.scores
        details: list[dict] = []
        if hasattr(result, "scores") and result.scores:
            for i, row_scores in enumerate(result.scores):
                details.append(
                    {
                        "row": i,
                        "faithfulness": row_scores.get("faithfulness"),
                        "answer_relevancy": row_scores.get("answer_relevancy"),
                    }
                )

        output = {
            "faithfulness": (
                float(faithfulness_score) if faithfulness_score is not None else None
            ),
            "answer_relevancy": (
                float(relevancy_score) if relevancy_score is not None else None
            ),
            "details": details,
        }

        # Print summary to stdout for human review
        print(
            f"\nRAGAs Evaluation Results\n"
            f"  Faithfulness:     {output['faithfulness']}\n"
            f"  Answer Relevancy: {output['answer_relevancy']}\n"
            f"  Rows evaluated:   {len(details)}\n",
            file=sys.stdout,
            flush=True,
        )

        return output

    except Exception as exc:
        logger.error("RAGAs evaluation failed: %s", exc)
        return {
            "faithfulness": None,
            "answer_relevancy": None,
            "details": [],
            "error": f"Evaluation failed: {exc}",
        }
