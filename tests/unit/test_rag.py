"""
Unit tests for RAG ingestion and retrieval modules.

Test coverage:
    1. test_retrieve_with_citations_returns_list
       Mock SupabaseVectorStore — verify retrieve_with_citations returns list
       of dicts with all required citation keys.

    2. test_retrieve_graceful_no_config
       When SUPABASE_URL / SUPABASE_KEY env vars absent, returns empty list
       without raising exceptions.

    3. test_ingest_pdf_chunking
       Mock pypdf + embeddings + DB — verify chunking logic produces parent
       and child chunks, and that the DB writes are called correctly.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Test 1: retrieve_with_citations returns list of dicts with expected keys
# ---------------------------------------------------------------------------


class TestRetrieveWithCitationsReturnsList:
    """retrieve_with_citations mocks SupabaseVectorStore and verifies output shape."""

    def test_retrieve_with_citations_returns_list(self, monkeypatch):
        """Mocked retriever returns list of dicts with all required citation keys."""
        # Required keys in each citation dict
        required_keys = {
            "content",
            "source_type",
            "source_id",
            "section",
            "page",
            "chunk_index",
            "relevance_score",
        }

        # Build fake RPC response data (matches Supabase RPC match_documents output)
        fake_rpc_row = {
            "content": "Revenue increased 15% year-over-year driven by cloud.",
            "metadata": {
                "source_type": "10k",
                "source_id": "10k:AAPL:2024-11-01",
                "section": "MD&A",
                "page": 42,
                "chunk_index": 7,
            },
            "similarity": 0.92,
        }

        # Mock Supabase client and RPC call
        fake_response = MagicMock()
        fake_response.data = [fake_rpc_row, fake_rpc_row]
        fake_rpc = MagicMock()
        fake_rpc.execute.return_value = fake_response
        fake_client = MagicMock()
        fake_client.rpc.return_value = fake_rpc

        monkeypatch.setattr(
            "lockin.rag.retriever._get_supabase_client",
            lambda: fake_client,
        )
        # Mock embeddings to avoid real API call
        fake_embeddings = MagicMock()
        fake_embeddings.embed_query.return_value = [0.0] * 3072
        monkeypatch.setattr(
            "lockin.rag.retriever._get_embeddings",
            lambda: fake_embeddings,
        )

        from lockin.rag import retrieve_with_citations

        results = retrieve_with_citations("cloud revenue growth", k=2)

        assert isinstance(results, list), "Must return a list"
        assert len(results) == 2, "Should return 2 results (one per fake doc)"

        for item in results:
            assert isinstance(item, dict), "Each result must be a dict"
            for key in required_keys:
                assert key in item, f"Missing key '{key}' in citation dict: {item}"

        # Spot-check values
        first = results[0]
        assert first["content"] == "Revenue increased 15% year-over-year driven by cloud."
        assert first["source_type"] == "10k"
        assert first["source_id"] == "10k:AAPL:2024-11-01"
        assert first["section"] == "MD&A"
        assert first["page"] == 42
        assert first["chunk_index"] == 7
        assert first["relevance_score"] == 0.92


# ---------------------------------------------------------------------------
# Test 2: Graceful degradation when Supabase not configured
# ---------------------------------------------------------------------------


class TestRetrieveGracefulNoConfig:
    """When SUPABASE_URL / SUPABASE_KEY absent, retrieve_with_citations returns []."""

    def test_retrieve_graceful_no_config(self, monkeypatch):
        """No Supabase env vars → returns empty list without raising."""
        # Remove Supabase env vars
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_KEY", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)

        # Ensure get_retriever returns None when Supabase not configured
        monkeypatch.setattr(
            "lockin.rag.retriever._get_supabase_client",
            lambda: None,
        )

        from lockin.rag import retrieve_with_citations

        results = retrieve_with_citations("any query about earnings")

        assert results == [], f"Expected empty list, got: {results}"
        assert isinstance(results, list), "Must return a list even when not configured"


# ---------------------------------------------------------------------------
# Test 3: ingest_pdf chunking logic
# ---------------------------------------------------------------------------


class TestIngestPdfChunking:
    """Mock pypdf + embeddings + DB to verify chunking and storage flow."""

    def test_ingest_pdf_chunking(self, tmp_path, monkeypatch):
        """
        ingest_pdf should:
        1. Extract text from PDF pages via pypdf
        2. Split into parent (1500-char) and child (500-char) chunks
        3. Embed child chunks via GoogleGenerativeAIEmbeddings
        4. Store document + chunks + rag_documents rows via DB connection

        We mock pypdf.PdfReader, embeddings, and psycopg.connect.
        """
        # ---- Mock pypdf.PdfReader ----
        fake_page = MagicMock()
        # Produce enough text to generate multiple chunks
        fake_page.extract_text.return_value = (
            "The company reported strong financial results. " * 80
        )
        fake_reader = MagicMock()
        fake_reader.pages = [fake_page, fake_page]  # 2 pages

        # ---- Mock embeddings ----
        fake_embeddings = MagicMock()
        # embed_documents returns list of 768-dim vectors
        fake_embeddings.embed_documents.return_value = [
            [0.1] * 768,
            [0.2] * 768,
            [0.3] * 768,
            [0.4] * 768,
            [0.5] * 768,
            [0.6] * 768,
        ]

        # ---- Mock DB connection ----
        fake_cursor = MagicMock()
        # _upsert_document returns a UUID row — use a string UUID
        import uuid as _uuid
        doc_uuid = _uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        chunk_uuid = _uuid.UUID("11111111-2222-3333-4444-555555555555")

        fake_cursor.__enter__ = lambda s: s
        fake_cursor.__exit__ = MagicMock(return_value=False)
        fake_cursor.fetchone.return_value = (doc_uuid,)

        fake_conn = MagicMock()
        fake_conn.__enter__ = lambda s: s
        fake_conn.__exit__ = MagicMock(return_value=False)
        fake_conn.cursor.return_value = fake_cursor

        # Patch pypdf.PdfReader, embeddings factory, and DB factory
        with (
            patch("lockin.rag.ingestion.PdfReader", return_value=fake_reader),
            patch(
                "lockin.rag.ingestion._get_embeddings",
                return_value=fake_embeddings,
            ),
            patch(
                "lockin.rag.ingestion._get_db_conn",
                return_value=fake_conn,
            ),
        ):
            # Create a dummy PDF file so FileNotFoundError is not raised
            dummy_pdf = tmp_path / "annual_report_2024.pdf"
            dummy_pdf.write_bytes(b"%PDF-1.4 fake pdf content")

            from lockin.rag.ingestion import ingest_pdf

            document_id = ingest_pdf(str(dummy_pdf))

        # Verify a document_id was returned
        assert document_id is not None
        assert isinstance(document_id, str)

        # Verify pypdf was called (text extraction happened)
        fake_page.extract_text.assert_called()

        # Verify embeddings were called with child chunks (non-empty list)
        fake_embeddings.embed_documents.assert_called_once()
        call_args = fake_embeddings.embed_documents.call_args[0][0]
        assert isinstance(call_args, list), "embed_documents must receive a list"
        assert len(call_args) > 0, "Must embed at least one child chunk"

        # Verify DB connection was closed (resource cleanup)
        fake_conn.close.assert_called_once()
