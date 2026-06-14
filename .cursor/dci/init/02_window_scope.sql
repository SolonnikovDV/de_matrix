-- Optional index for dialog_id prefix scans (project/window namespaces)
CREATE INDEX IF NOT EXISTS dci_embeddings_dialog_id_prefix
    ON dci_embeddings (dialog_id text_pattern_ops);
