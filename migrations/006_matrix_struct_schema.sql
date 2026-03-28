-- Вынос объектов матрицы (дерево, шаблоны, примеры, ui) в схему matrix_struct.
-- Публичные users, change_*, staging_batches, stable_state и т.д. остаются в public.
-- Выполнять после 005_drop_legacy_tree.sql.

CREATE SCHEMA IF NOT EXISTS matrix_struct;

-- Дочерние таблицы шаблонов → родитель; затем прочие объекты матрицы.
DO $m$ BEGIN
  IF to_regclass('public.action_template_min_requirements') IS NOT NULL THEN
    ALTER TABLE public.action_template_min_requirements SET SCHEMA matrix_struct;
  END IF;
END $m$;
DO $m$ BEGIN
  IF to_regclass('public.action_template_antipatterns') IS NOT NULL THEN
    ALTER TABLE public.action_template_antipatterns SET SCHEMA matrix_struct;
  END IF;
END $m$;
DO $m$ BEGIN
  IF to_regclass('public.action_template_stack_refs') IS NOT NULL THEN
    ALTER TABLE public.action_template_stack_refs SET SCHEMA matrix_struct;
  END IF;
END $m$;
DO $m$ BEGIN
  IF to_regclass('public.action_template_example_refs') IS NOT NULL THEN
    ALTER TABLE public.action_template_example_refs SET SCHEMA matrix_struct;
  END IF;
END $m$;
DO $m$ BEGIN
  IF to_regclass('public.action_template_literature_refs') IS NOT NULL THEN
    ALTER TABLE public.action_template_literature_refs SET SCHEMA matrix_struct;
  END IF;
END $m$;
DO $m$ BEGIN
  IF to_regclass('public.action_templates') IS NOT NULL THEN
    ALTER TABLE public.action_templates SET SCHEMA matrix_struct;
  END IF;
END $m$;
DO $m$ BEGIN
  IF to_regclass('public.action_examples') IS NOT NULL THEN
    ALTER TABLE public.action_examples SET SCHEMA matrix_struct;
  END IF;
END $m$;
DO $m$ BEGIN
  IF to_regclass('public.ui_section_titles') IS NOT NULL THEN
    ALTER TABLE public.ui_section_titles SET SCHEMA matrix_struct;
  END IF;
END $m$;
DO $m$ BEGIN
  IF to_regclass('public.ui_settings') IS NOT NULL THEN
    ALTER TABLE public.ui_settings SET SCHEMA matrix_struct;
  END IF;
END $m$;
DO $m$ BEGIN
  IF to_regclass('public.ui_config') IS NOT NULL THEN
    ALTER TABLE public.ui_config SET SCHEMA matrix_struct;
  END IF;
END $m$;
DO $m$ BEGIN
  IF to_regclass('public.matrix_nodes') IS NOT NULL THEN
    ALTER TABLE public.matrix_nodes SET SCHEMA matrix_struct;
  END IF;
END $m$;
