-- Описание и ответственный на домене, действии и поддействии (единый JSON ↔ дерево матрицы).

ALTER TABLE domains ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT '';
ALTER TABLE domains ADD COLUMN IF NOT EXISTS responsible VARCHAR(255) NOT NULL DEFAULT '';

ALTER TABLE actions ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT '';
ALTER TABLE actions ADD COLUMN IF NOT EXISTS responsible VARCHAR(255) NOT NULL DEFAULT '';

ALTER TABLE subactions ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT '';
ALTER TABLE subactions ADD COLUMN IF NOT EXISTS responsible VARCHAR(255) NOT NULL DEFAULT '';
