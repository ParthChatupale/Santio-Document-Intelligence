-- Run as a PostgreSQL administrator in the dedicated santio_vector_sandbox DB.
-- The application login and database are provisioned separately.
-- Adds pgvector to this database; does not alter existing project databases.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS rag AUTHORIZATION santio_vector_app;
ALTER ROLE santio_vector_app IN DATABASE santio_vector_sandbox
    SET search_path = rag, public;
