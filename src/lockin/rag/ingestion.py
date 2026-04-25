"""
RAG ingestion pipeline.

Handles document ingestion from:
- PDF files (financial reports, research papers)
- SEC 10-K filings (via edgar library)
- Earnings call transcripts (plain text)

Uses Parent Document Retriever pattern:
- Parent chunks: 1500 chars / 200 overlap (stored for context retrieval)
- Child chunks: 500 chars / 50 overlap (stored in rag_documents with embeddings)

All functions are IDEMPOTENT via UPSERT on (source_type, source_id).
Graceful degradation when DATABASE_URL not configured.
"""

from __future__ import annotations

import json
import os
import pathlib
import uuid
import logging
from typing import Optional

from pypdf import PdfReader

logger = logging.getLogger(__name__)


def _get_db_conn():
    """Return a psycopg connection or None if DATABASE_URL not set."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.warning("DATABASE_URL not set — RAG ingestion unavailable")
        return None
    try:
        import psycopg
        return psycopg.connect(database_url)
    except Exception as exc:
        logger.warning("RAG DB connection failed: %s", exc)
        return None


def _get_embeddings():
    """Return GoogleGenerativeAIEmbeddings instance for gemini-embedding-001."""
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    return GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")


def _split_text(text: str) -> tuple[list[str], list[str]]:
    """
    Split text into parent and child chunks.

    Returns:
        (parent_chunks, child_chunks) — lists of text strings.
        parent: 1500 chars / 200 overlap
        child:  500 chars / 50 overlap
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    parent_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=200,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    parent_chunks = parent_splitter.split_text(text)
    child_chunks = child_splitter.split_text(text)
    return parent_chunks, child_chunks


def _upsert_document(
    conn,
    source_type: str,
    source_id: str,
    title: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> str:
    """
    UPSERT a document record. Returns the document UUID string.

    Uses ON CONFLICT (source_type, source_id) DO UPDATE to ensure idempotency.
    """
    meta = metadata or {}
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO documents (source_type, source_id, title, metadata)
            VALUES (%s, %s, %s, %s::jsonb)
            ON CONFLICT (source_type, source_id)
            DO UPDATE SET
                title = EXCLUDED.title,
                metadata = EXCLUDED.metadata
            RETURNING id
            """,
            (source_type, source_id, title, json.dumps(meta)),
        )
        row = cur.fetchone()
    conn.commit()
    return str(row[0])


def _store_chunks_and_embeddings(
    conn,
    document_id: str,
    parent_chunks: list[str],
    child_chunks: list[str],
    embeddings_model,
    base_metadata: Optional[dict] = None,
) -> None:
    """
    Store parent chunks (is_parent=True, no embedding) and child chunks
    (is_parent=False, embedding stored in rag_documents).

    Deletes existing chunks for document_id first to ensure idempotency.
    """
    meta = base_metadata or {}

    with conn.cursor() as cur:
        # Delete existing chunks (cascade handles rag_documents via FK)
        cur.execute(
            "DELETE FROM rag_documents WHERE chunk_id IN "
            "(SELECT id FROM chunks WHERE document_id = %s)",
            (document_id,),
        )
        cur.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
    conn.commit()

    # Insert parent chunks
    parent_ids: list[str] = []
    with conn.cursor() as cur:
        for idx, text in enumerate(parent_chunks):
            chunk_meta = {**meta, "chunk_type": "parent", "chunk_index": idx}
            cur.execute(
                """
                INSERT INTO chunks (document_id, content, chunk_index, is_parent, metadata)
                VALUES (%s, %s, %s, TRUE, %s::jsonb)
                RETURNING id
                """,
                (document_id, text, idx, json.dumps(chunk_meta)),
            )
            row = cur.fetchone()
            parent_ids.append(str(row[0]))
    conn.commit()

    # Embed child chunks in batches (respects API rate limits)
    # Each batch is embedded, inserted, and committed independently so partial
    # progress is preserved if a later batch fails.
    if not child_chunks:
        return

    import time

    _EMBED_BATCH_SIZE = 50  # Conservative to stay under 100 req/min free-tier
    _EMBED_RETRY_DELAY = 65  # Seconds to wait on rate-limit (API says ~60s)
    _MAX_RETRIES = 5

    for batch_start in range(0, len(child_chunks), _EMBED_BATCH_SIZE):
        batch_texts = child_chunks[batch_start : batch_start + _EMBED_BATCH_SIZE]
        batch_num = batch_start // _EMBED_BATCH_SIZE

        # Embed with retry
        batch_vectors = None
        for attempt in range(_MAX_RETRIES):
            try:
                batch_vectors = embeddings_model.embed_documents(batch_texts)
                break
            except Exception as exc:
                if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                    logger.info(
                        "Rate limited on batch %d — waiting %ds (attempt %d/%d)",
                        batch_num, _EMBED_RETRY_DELAY, attempt + 1, _MAX_RETRIES,
                    )
                    time.sleep(_EMBED_RETRY_DELAY)
                else:
                    logger.error("Embedding failed: %s", exc)
                    raise

        if batch_vectors is None:
            logger.error("Batch %d failed after %d retries — skipping", batch_num, _MAX_RETRIES)
            continue

        # Insert this batch of child chunks + rag_documents and commit
        with conn.cursor() as cur:
            for i, (text, vector) in enumerate(zip(batch_texts, batch_vectors)):
                idx = batch_start + i
                chunk_meta = {**meta, "chunk_type": "child", "chunk_index": idx}
                cur.execute(
                    """
                    INSERT INTO chunks (document_id, content, chunk_index, is_parent, metadata)
                    VALUES (%s, %s, %s, FALSE, %s::jsonb)
                    RETURNING id
                    """,
                    (document_id, text, idx, json.dumps(chunk_meta)),
                )
                chunk_id = str(cur.fetchone()[0])

                rag_meta = {
                    **meta,
                    "chunk_index": idx,
                    "document_id": document_id,
                    "chunk_id": chunk_id,
                }
                vector_str = "[" + ",".join(str(v) for v in vector) + "]"
                cur.execute(
                    """
                    INSERT INTO rag_documents (chunk_id, content, embedding, metadata)
                    VALUES (%s, %s, %s::vector, %s::jsonb)
                    """,
                    (chunk_id, text, vector_str, json.dumps(rag_meta)),
                )
        conn.commit()
        logger.info("Batch %d committed (%d chunks)", batch_num, len(batch_texts))

        # Pause between batches to stay under rate limit
        if batch_start + _EMBED_BATCH_SIZE < len(child_chunks):
            time.sleep(2)


# ---------------------------------------------------------------------------
# Public ingestion functions
# ---------------------------------------------------------------------------


def ingest_pdf(
    file_path: str,
    source_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> str:
    """
    Ingest a PDF file into the RAG pipeline.

    Args:
        file_path: Absolute path to the PDF file.
        source_id: Unique identifier for this document (defaults to file_path).
        metadata: Extra metadata to attach to all chunks.

    Returns:
        document_id (UUID string) — the documents table row ID.

    Raises:
        RuntimeError: If DATABASE_URL not configured.
        FileNotFoundError: If PDF file does not exist.
    """
    path = pathlib.Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    sid = source_id or str(path.resolve())
    title = path.stem

    # Extract text from PDF
    reader = PdfReader(str(path))
    pages_text: list[str] = []
    for page_num, page in enumerate(reader.pages):
        extracted = page.extract_text() or ""
        pages_text.append(extracted)

    full_text = "\n\n".join(pages_text)
    if not full_text.strip():
        logger.warning("PDF %s yielded no extractable text", file_path)

    meta = {
        "source_type": "pdf",
        "source_id": sid,
        "file_path": str(path.resolve()),
        "page_count": len(reader.pages),
        **(metadata or {}),
    }

    conn = _get_db_conn()
    if conn is None:
        raise RuntimeError("DATABASE_URL not configured — cannot ingest PDF")

    try:
        document_id = _upsert_document(conn, "pdf", sid, title=title, metadata=meta)
        parent_chunks, child_chunks = _split_text(full_text)
        embeddings_model = _get_embeddings()
        _store_chunks_and_embeddings(
            conn, document_id, parent_chunks, child_chunks, embeddings_model, meta
        )
        logger.info(
            "Ingested PDF %s: document_id=%s, %d parent / %d child chunks",
            file_path, document_id, len(parent_chunks), len(child_chunks),
        )
        return document_id
    finally:
        conn.close()


def _resolve_cik(ticker: str) -> tuple[str, str] | None:
    """Resolve a stock ticker to (company_name, cik) via SEC EDGAR.

    Returns None if the ticker cannot be resolved.
    """
    import httpx

    try:
        resp = httpx.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": "LockIn Research research@lockin.dev"},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        for entry in data.values():
            if entry.get("ticker", "").upper() == ticker.upper():
                cik = str(entry["cik_str"]).zfill(10)
                name = entry["title"]
                return name, cik
    except Exception as exc:
        logger.warning("CIK lookup failed for %s: %s", ticker, exc)
    return None


def ingest_10k(ticker: str, years: int = 3) -> list[str]:
    """
    Fetch and ingest SEC 10-K filings for a ticker via the edgar library.

    Args:
        ticker: Stock ticker symbol (e.g. "AAPL").
        years: Number of most recent 10-K filings to ingest.

    Returns:
        List of document_id strings (one per filing ingested).

    Notes:
        - Idempotent: subsequent calls for same ticker/year upsert in place.
        - Gracefully returns [] if DATABASE_URL not configured.
        - edgar 5.x API: Company(name, cik), get_10Ks(), get_10Ks_metadata().
    """
    conn = _get_db_conn()
    if conn is None:
        logger.warning("DATABASE_URL not configured — skipping 10-K ingest for %s", ticker)
        return []

    try:
        from edgar import Company

        resolved = _resolve_cik(ticker)
        if resolved is None:
            logger.error("Could not resolve CIK for ticker %s", ticker)
            return []
        company_name, cik = resolved

        company = Company(company_name, cik)

        # get_10Ks() returns list of lxml HTML elements (one per filing)
        filings = company.get_10Ks()
        if not isinstance(filings, list):
            filings = [filings] if filings is not None else []

        # get_10Ks_metadata() returns list of dicts with filing dates
        metadata_list = company.get_10Ks_metadata()
        if not isinstance(metadata_list, list):
            metadata_list = [metadata_list] if metadata_list is not None else []

        # Limit to requested number of years
        filings = filings[:years]
        metadata_list = metadata_list[:years]

        document_ids: list[str] = []
        embeddings_model = _get_embeddings()

        for i, filing in enumerate(filings):
            try:
                # Extract text from lxml element
                text = filing.text_content() if hasattr(filing, "text_content") else ""

                if not text.strip():
                    logger.warning("10-K for %s yielded no text; skipping", ticker)
                    continue

                # Get filing date from metadata
                filing_date = "unknown"
                if i < len(metadata_list) and isinstance(metadata_list[i], dict):
                    filing_date = metadata_list[i].get(
                        "Filing Date",
                        metadata_list[i].get("Period of Report", "unknown"),
                    )

                source_id = f"10k:{ticker}:{filing_date}"
                title = f"{ticker} 10-K {filing_date}"

                meta = {
                    "source_type": "10k",
                    "source_id": source_id,
                    "ticker": ticker,
                    "filing_date": str(filing_date),
                    "form_type": "10-K",
                }

                document_id = _upsert_document(
                    conn, "10k", source_id, title=title, metadata=meta
                )
                parent_chunks, child_chunks = _split_text(text)
                _store_chunks_and_embeddings(
                    conn,
                    document_id,
                    parent_chunks,
                    child_chunks,
                    embeddings_model,
                    meta,
                )
                document_ids.append(document_id)
                logger.info(
                    "Ingested 10-K %s (%s): document_id=%s, %d parent / %d child chunks",
                    ticker, filing_date, document_id,
                    len(parent_chunks), len(child_chunks),
                )
            except Exception as exc:
                logger.error("Failed to ingest 10-K filing for %s: %s", ticker, exc)
                continue

        return document_ids
    except Exception as exc:
        logger.error("10-K ingestion failed for %s: %s", ticker, exc)
        return []
    finally:
        conn.close()


def ingest_transcript(
    ticker: str,
    quarter: int,
    year: int,
    transcript_text: str,
) -> str:
    """
    Ingest an earnings call transcript into the RAG pipeline.

    Args:
        ticker: Stock ticker symbol (e.g. "AAPL").
        quarter: Fiscal quarter (1-4).
        year: Calendar year of the earnings call.
        transcript_text: Full plaintext transcript content.

    Returns:
        document_id (UUID string).

    Raises:
        RuntimeError: If DATABASE_URL not configured.
        ValueError: If quarter not in 1-4.
    """
    if quarter not in (1, 2, 3, 4):
        raise ValueError(f"quarter must be 1-4, got {quarter}")

    source_id = f"transcript:{ticker}:Q{quarter}{year}"
    title = f"{ticker} Q{quarter} {year} Earnings Call Transcript"

    meta = {
        "source_type": "transcript",
        "source_id": source_id,
        "ticker": ticker,
        "quarter": quarter,
        "year": year,
        "form_type": "transcript",
    }

    conn = _get_db_conn()
    if conn is None:
        raise RuntimeError(
            "DATABASE_URL not configured — cannot ingest transcript"
        )

    try:
        document_id = _upsert_document(
            conn, "transcript", source_id, title=title, metadata=meta
        )
        parent_chunks, child_chunks = _split_text(transcript_text)
        embeddings_model = _get_embeddings()
        _store_chunks_and_embeddings(
            conn, document_id, parent_chunks, child_chunks, embeddings_model, meta
        )
        logger.info(
            "Ingested transcript %s Q%d%d: document_id=%s, %d parent / %d child chunks",
            ticker, quarter, year, document_id,
            len(parent_chunks), len(child_chunks),
        )
        return document_id
    finally:
        conn.close()
