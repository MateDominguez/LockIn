"""
RAG retriever with citation tracking.

Uses SupabaseVectorStore with the rag_documents table and Parent Document
Retriever pattern. Each retrieved chunk carries citation metadata:
source_type, source_id, section, page, chunk_index, relevance_score.

Graceful degradation: returns None / [] when Supabase is not configured.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def _get_supabase_client():
    """Return a Supabase client or None if not configured."""
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY") or os.environ.get(
        "SUPABASE_SERVICE_KEY"
    )
    if not supabase_url or not supabase_key:
        return None
    try:
        from supabase import create_client

        return create_client(supabase_url, supabase_key)
    except Exception as exc:
        logger.warning("Supabase client init failed: %s", exc)
        return None


def _get_embeddings():
    """Return GoogleGenerativeAIEmbeddings for text-embedding-004."""
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    return GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")


def get_retriever(k: int = 5):
    """
    Initialize and return a SupabaseVectorStore retriever.

    Returns:
        A LangChain retriever configured for rag_documents, or None if
        Supabase is not configured or initialisation fails.

    Args:
        k: Number of documents to retrieve per query.
    """
    client = _get_supabase_client()
    if client is None:
        logger.warning(
            "SUPABASE_URL / SUPABASE_KEY not set — RAG retriever unavailable"
        )
        return None

    try:
        from langchain_community.vectorstores import SupabaseVectorStore

        embeddings = _get_embeddings()
        vector_store = SupabaseVectorStore(
            client=client,
            embedding=embeddings,
            table_name="rag_documents",
            query_name="match_documents",
        )
        return vector_store.as_retriever(search_kwargs={"k": k})
    except Exception as exc:
        logger.warning("SupabaseVectorStore init failed: %s", exc)
        return None


def retrieve_with_citations(query: str, k: int = 5) -> list[dict]:
    """
    Retrieve relevant document chunks with full citation metadata.

    Args:
        query: Natural-language query string.
        k: Number of results to return.

    Returns:
        List of dicts, each containing:
            - content (str): The retrieved text chunk.
            - source_type (str): "pdf" | "10k" | "transcript".
            - source_id (str): Unique document identifier.
            - section (str | None): Document section if available in metadata.
            - page (int | None): Page number if available.
            - chunk_index (int | None): Index of this chunk within the document.
            - relevance_score (float | None): Cosine similarity score (0-1).

        Returns [] if retriever is not configured or query fails.
    """
    retriever = get_retriever(k=k)
    if retriever is None:
        return []

    try:
        docs = retriever.invoke(query)
    except Exception as exc:
        logger.error("RAG retrieval failed for query %r: %s", query, exc)
        return []

    results: list[dict] = []
    for doc in docs:
        metadata = doc.metadata if hasattr(doc, "metadata") else {}

        citation: dict = {
            "content": doc.page_content if hasattr(doc, "page_content") else str(doc),
            "source_type": metadata.get("source_type"),
            "source_id": metadata.get("source_id"),
            "section": metadata.get("section"),
            "page": metadata.get("page"),
            "chunk_index": metadata.get("chunk_index"),
            "relevance_score": metadata.get("similarity") or metadata.get("score"),
        }
        results.append(citation)

    return results
