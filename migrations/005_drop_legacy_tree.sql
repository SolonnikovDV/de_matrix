-- Удаление реляционного дерева legacy (domains → skills → actions → subactions) и staging_*.
-- Дерево матрицы хранится только в matrix_nodes; staging_batches.payload — JSON-снимок.

DROP TABLE IF EXISTS staging_subaction_review_questions CASCADE;
DROP TABLE IF EXISTS staging_action_review_questions CASCADE;
DROP TABLE IF EXISTS staging_subactions CASCADE;
DROP TABLE IF EXISTS staging_actions CASCADE;
DROP TABLE IF EXISTS staging_skills CASCADE;
DROP TABLE IF EXISTS staging_domains CASCADE;

DROP TABLE IF EXISTS subaction_review_questions CASCADE;
DROP TABLE IF EXISTS action_review_questions CASCADE;
DROP TABLE IF EXISTS subactions CASCADE;
DROP TABLE IF EXISTS actions CASCADE;
DROP TABLE IF EXISTS skills CASCADE;
DROP TABLE IF EXISTS domains CASCADE;
