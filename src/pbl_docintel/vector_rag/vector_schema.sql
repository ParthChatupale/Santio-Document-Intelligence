-- Application tables in the dedicated sandbox. No approximate index is needed
-- for this small collection; queries use exact cosine-distance search.
CREATE TABLE IF NOT EXISTS rag.vector_indexes (
    index_id text PRIMARY KEY,
    model_name text NOT NULL,
    model_revision text NOT NULL,
    dimensions integer NOT NULL CHECK (dimensions = 384),
    chunk_count integer NOT NULL CHECK (chunk_count > 0),
    manifest jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rag.chunks (
    index_id text NOT NULL REFERENCES rag.vector_indexes(index_id),
    chunk_id text NOT NULL,
    ordinal integer NOT NULL,
    text text NOT NULL,
    contextualized_text text NOT NULL,
    token_count integer NOT NULL,
    metadata jsonb NOT NULL,
    embedding public.vector(384) NOT NULL,
    PRIMARY KEY (index_id, chunk_id),
    UNIQUE (index_id, ordinal)
);

-- Native full-text search complements vector retrieval; existing vectors stay intact.
CREATE INDEX IF NOT EXISTS chunks_context_english_gin
    ON rag.chunks USING gin (to_tsvector('english', contextualized_text));
