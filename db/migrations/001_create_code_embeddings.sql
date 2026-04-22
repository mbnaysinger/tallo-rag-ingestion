-- Migration 001: Create code_embeddings table with pgvector support
-- Requirements: 5.1, 5.2

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE code_embeddings (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    content     TEXT        NOT NULL,
    file_path   TEXT        NOT NULL,
    metadata    JSONB,
    embedding   vector(3072)
);

-- Btree index for efficient deduplication by file hash
CREATE INDEX ON code_embeddings
    USING btree ((metadata->>'file_sha256'));

-- HNSW index for cosine similarity search at scale
CREATE INDEX ON code_embeddings
    USING hnsw (embedding vector_cosine_ops);

ALTER TABLE code_embeddings ALTER COLUMN embedding TYPE halfvec(3072);
CREATE INDEX ON code_embeddings USING hnsw (embedding halfvec_l2_ops);
