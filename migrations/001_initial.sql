-- Run using a database owner account. Application tables are not exposed by PostgREST.
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;
-- If vector was installed in public, relocate before running this migration:
-- ALTER EXTENSION vector SET SCHEMA extensions;
CREATE SCHEMA IF NOT EXISTS rag;
REVOKE ALL ON SCHEMA rag FROM PUBLIC;

CREATE TABLE IF NOT EXISTS rag.documents (
    id uuid PRIMARY KEY,
    title text NOT NULL,
    edition text NOT NULL,
    source_uri text NOT NULL DEFAULT '',
    embedding_signature text NOT NULL
);
CREATE TABLE IF NOT EXISTS rag.sections (
    document_id uuid NOT NULL REFERENCES rag.documents ON DELETE CASCADE,
    id text NOT NULL,
    number text NOT NULL,
    title text NOT NULL,
    kind text NOT NULL,
    parent_id text,
    PRIMARY KEY (document_id, id),
    FOREIGN KEY (document_id, parent_id) REFERENCES rag.sections(document_id, id)
        DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX IF NOT EXISTS sections_number ON rag.sections(document_id, number);
CREATE INDEX IF NOT EXISTS sections_parent ON rag.sections(document_id, parent_id);
CREATE TABLE IF NOT EXISTS rag.section_references (
    document_id uuid NOT NULL,
    source_id text NOT NULL,
    target_id text NOT NULL,
    PRIMARY KEY (document_id, source_id, target_id),
    FOREIGN KEY (document_id, source_id) REFERENCES rag.sections(document_id, id)
        ON DELETE CASCADE,
    FOREIGN KEY (document_id, target_id) REFERENCES rag.sections(document_id, id)
        ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS rag.chunks (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id uuid NOT NULL,
    section_id text NOT NULL,
    chunk_index integer NOT NULL,
    page integer,
    text text NOT NULL,
    embedding extensions.vector(768) NOT NULL,
    search_text tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    UNIQUE (document_id, section_id, chunk_index),
    FOREIGN KEY (document_id, section_id) REFERENCES rag.sections(document_id, id)
        ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS chunks_text ON rag.chunks USING gin(search_text);
-- Exact vector search is intentional for the small free-tier corpus: filtered
-- searches retain full recall and avoid a large HNSW index. Benchmark before adding ANN.
CREATE TABLE IF NOT EXISTS rag.conversations (
    id uuid PRIMARY KEY,
    document_ids uuid[] NOT NULL,
    version integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS rag.messages (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES rag.conversations ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('user', 'assistant')),
    content text NOT NULL,
    citations jsonb NOT NULL DEFAULT '[]',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_history ON rag.messages(conversation_id, id DESC);

-- Active external vector generation; old or partial writes never become searchable.
ALTER TABLE rag.documents ADD COLUMN IF NOT EXISTS vector_generation uuid;
