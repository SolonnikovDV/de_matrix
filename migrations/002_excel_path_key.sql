-- Persist Excel unified path segments for round-trip export (optional manual run).
ALTER TABLE actions ADD COLUMN IF NOT EXISTS excel_path_key TEXT NOT NULL DEFAULT '';
ALTER TABLE subactions ADD COLUMN IF NOT EXISTS excel_path_key TEXT NOT NULL DEFAULT '';
ALTER TABLE staging_actions ADD COLUMN IF NOT EXISTS excel_path_key TEXT NOT NULL DEFAULT '';
ALTER TABLE staging_subactions ADD COLUMN IF NOT EXISTS excel_path_key TEXT NOT NULL DEFAULT '';
