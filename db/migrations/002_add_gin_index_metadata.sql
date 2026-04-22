-- Migration 002: GIN index on metadata JSONB for dependency queries
-- Enables efficient filtering on class_name, injects, calls, component_name, tables, etc.

CREATE INDEX IF NOT EXISTS idx_code_embeddings_metadata_gin
    ON code_embeddings
    USING gin (metadata jsonb_path_ops);
