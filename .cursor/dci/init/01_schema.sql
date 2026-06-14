CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS dci_embeddings (
    ledger_id       TEXT        NOT NULL,
    dialog_id       TEXT        NOT NULL DEFAULT 'default',
    ledger_type     TEXT        NOT NULL,
    team            TEXT,
    branch_state    TEXT,
    status          TEXT,
    domain          TEXT,
    content         TEXT        NOT NULL,
    embedding       vector(384) NOT NULL,
    metadata        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    source          TEXT        NOT NULL DEFAULT 'db',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (dialog_id, ledger_id)
);

CREATE INDEX IF NOT EXISTS dci_embeddings_hnsw
    ON dci_embeddings USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS dci_embeddings_ledger_type
    ON dci_embeddings (ledger_type);

CREATE INDEX IF NOT EXISTS dci_embeddings_branch_state
    ON dci_embeddings (branch_state);

CREATE INDEX IF NOT EXISTS dci_embeddings_status
    ON dci_embeddings (status);

CREATE TABLE IF NOT EXISTS dci_sync_log (
    id              BIGSERIAL PRIMARY KEY,
    action          TEXT NOT NULL,
    detail          JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
