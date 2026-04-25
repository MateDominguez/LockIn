"""
RAG table setup script.

Creates:
- documents table (source registry: PDFs, 10-Ks, transcripts)
- chunks table (parent/child text chunks)
- rag_documents table (child chunks with pgvector embeddings, 768 dims)
- match_documents RPC function (used by SupabaseVectorStore similarity search)

Run once after setup_data_tables.py:
    uv run python scripts/setup_rag_tables.py
"""

import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
env_file = project_root / ".env"

if not env_file.exists():
    print("ERROR: .env file not found.")
    sys.exit(1)

from dotenv import load_dotenv
load_dotenv(env_file)

database_url = os.environ.get("DATABASE_URL")
if not database_url:
    print("ERROR: DATABASE_URL not set in .env")
    sys.exit(1)

print(f"Connecting to: {database_url[:50]}...")

import psycopg

# Step 1: Enable pgvector extension
print("\n[1/5] Enabling pgvector extension...")
ENABLE_VECTOR = """
CREATE EXTENSION IF NOT EXISTS vector;
"""
with psycopg.connect(database_url) as conn:
    with conn.cursor() as cur:
        cur.execute(ENABLE_VECTOR)
    conn.commit()
print("      OK — vector extension enabled")

# Step 2: Create documents table (source registry)
print("\n[2/5] Creating documents table...")
CREATE_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(source_type, source_id)
);
CREATE INDEX IF NOT EXISTS documents_source_type_idx ON documents(source_type);
CREATE INDEX IF NOT EXISTS documents_source_id_idx ON documents(source_id);
"""
with psycopg.connect(database_url) as conn:
    with conn.cursor() as cur:
        cur.execute(CREATE_DOCUMENTS)
    conn.commit()
print("      OK — documents table created")

# Step 3: Create chunks table (parent/child text chunks)
print("\n[3/5] Creating chunks table...")
CREATE_CHUNKS = """
CREATE TABLE IF NOT EXISTS chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id),
    content TEXT NOT NULL,
    chunk_index INT NOT NULL,
    is_parent BOOLEAN DEFAULT false,
    parent_id UUID REFERENCES chunks(id),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chunks_document_id_idx ON chunks(document_id);
CREATE INDEX IF NOT EXISTS chunks_parent_id_idx ON chunks(parent_id);
"""
with psycopg.connect(database_url) as conn:
    with conn.cursor() as cur:
        cur.execute(CREATE_CHUNKS)
    conn.commit()
print("      OK — chunks table created")

# Step 4: Create rag_documents table (child chunks + embeddings, 3072 dims for gemini-embedding-001)
print("\n[4/5] Creating rag_documents table...")
CREATE_RAG_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS rag_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id UUID REFERENCES chunks(id),
    content TEXT NOT NULL,
    embedding vector(3072),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);
"""
with psycopg.connect(database_url) as conn:
    with conn.cursor() as cur:
        cur.execute(CREATE_RAG_DOCUMENTS)
    conn.commit()
print("      OK — rag_documents table created")

# Step 5: Create match_documents RPC function (required by SupabaseVectorStore)
print("\n[5/5] Creating match_documents RPC function...")
CREATE_MATCH_FUNCTION = """
CREATE OR REPLACE FUNCTION match_documents(
    query_embedding vector(3072),
    match_count INT DEFAULT 5,
    filter JSONB DEFAULT '{}'
)
RETURNS TABLE (id UUID, content TEXT, metadata JSONB, similarity FLOAT)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT rd.id, rd.content, rd.metadata,
           1 - (rd.embedding <=> query_embedding) AS similarity
    FROM rag_documents rd
    WHERE rd.metadata @> filter
    ORDER BY rd.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
"""
with psycopg.connect(database_url) as conn:
    with conn.cursor() as cur:
        cur.execute(CREATE_MATCH_FUNCTION)
    conn.commit()
print("      OK — match_documents RPC function created")

print("\nRAG tables setup complete.")
print("\nNext step: Run ingestion pipeline to index documents:")
print("  from lockin.rag import ingest_pdf, ingest_10k, ingest_transcript")
