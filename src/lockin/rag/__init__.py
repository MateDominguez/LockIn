"""
lockin.rag — RAG ingestion and retrieval pipeline.

Public API:
    Ingestion:
        ingest_pdf(file_path, source_id=None, metadata=None) -> str
        ingest_10k(ticker, years=3) -> list[str]
        ingest_transcript(ticker, quarter, year, transcript_text) -> str

    Retrieval:
        get_retriever(k=5) -> retriever | None
        retrieve_with_citations(query, k=5) -> list[dict]

    Evaluation:
        create_eval_dataset(questions, ground_truths) -> Dataset
        evaluate_rag(dataset=None, questions=None, ground_truths=None) -> dict
"""

from lockin.rag.ingestion import ingest_pdf, ingest_10k, ingest_transcript
from lockin.rag.retriever import get_retriever, retrieve_with_citations
from lockin.rag.evaluation import create_eval_dataset, evaluate_rag

__all__ = [
    "ingest_pdf",
    "ingest_10k",
    "ingest_transcript",
    "get_retriever",
    "retrieve_with_citations",
    "create_eval_dataset",
    "evaluate_rag",
]
