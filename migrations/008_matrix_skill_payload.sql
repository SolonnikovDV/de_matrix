-- skill_payload: exls skill fields (section, status, author, reviewer, skill_sections)

ALTER TABLE matrix_struct.matrix_nodes
    ADD COLUMN IF NOT EXISTS skill_payload JSONB NOT NULL DEFAULT '{}'::jsonb;
