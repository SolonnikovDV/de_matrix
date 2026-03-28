-- Произвольная глубина дерева матрицы (альтернатива фиксированным domains/skills/actions/subactions).

CREATE TABLE IF NOT EXISTS matrix_nodes (
    id SERIAL PRIMARY KEY,
    parent_id INTEGER REFERENCES matrix_nodes(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    depth INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL DEFAULT '',
    code VARCHAR(255),
    description TEXT NOT NULL DEFAULT '',
    responsible VARCHAR(255) NOT NULL DEFAULT '',
    level_sticker VARCHAR(16),
    template_id VARCHAR(128),
    level_tag VARCHAR(16),
    level_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    leaf_view JSONB NOT NULL DEFAULT '{}'::jsonb,
    review_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
    excel_path_key TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS ix_matrix_nodes_parent_id ON matrix_nodes(parent_id);
CREATE INDEX IF NOT EXISTS ix_matrix_nodes_depth ON matrix_nodes(depth);
