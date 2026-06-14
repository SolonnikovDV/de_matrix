---
{
  "tig_cli_version": "1.5",
  "generated_at": "2026-06-14T14:17:59Z",
  "target": "/Users/dmitrysolonnikov/PycharmProjects/de_matrix",
  "mode": "compact",
  "fingerprint": "sha256:9b2512005568ebce",
  "git_head": "52e09d36f569f5d9bac946b073fc6e91edd54cf9",
  "git_dirty": true,
  "base_ref": "origin/main",
  "base_ref_note": "origin/main",
  "file_count": 206,
  "total_files": 206
}
---

# TIG Snapshot

**Project:** `de_matrix`
**Mode:** `compact` | **Fingerprint:** `sha256:9b2512005568ebce`
**Base ref:** `origin/main` (origin/main)

## Module map

| Module | Files | Size |
|--------|------:|-----:|
| `.cursor` | 36 | 257355 bytes |
| `.DS_Store` | 1 | 6148 bytes |
| `.github` | 5 | 19658 bytes |
| `.gitignore` | 1 | 1596 bytes |
| `app.py` | 1 | 207107 bytes |
| `config` | 3 | 10761 bytes |
| `core` | 21 | 222341 bytes |
| `docker-compose.prod.yml` | 1 | 2726 bytes |
| `docker-compose.yml` | 1 | 2928 bytes |
| `Dockerfile` | 1 | 261 bytes |
| `exls_matrix` | 44 | 1423769 bytes |
| `LICENSE` | 1 | 1075 bytes |
| `migrations` | 8 | 20201 bytes |
| `presentations` | 4 | 3556449 bytes |
| `proxy` | 7 | 10565 bytes |
| `README.md` | 1 | 27466 bytes |
| `requirements.txt` | 1 | 775 bytes |
| `scripts` | 28 | 78398 bytes |
| `security` | 3 | 884 bytes |
| `static` | 3 | 78185 bytes |
| `storage` | 9 | 60443 bytes |
| `templates` | 24 | 483609 bytes |
| `tig_app_ru.py` | 1 | 40718 bytes |
| `TODO.md` | 1 | 34065 bytes |

**Total:** 206 files

## Directory tree

*depth ≤ 2*

```text
de_matrix/
├── .cursor/
│   ├── context/
│   │   ├── dialogs/ …
│   ├── dci/
│   │   ├── init/ …
│   ├── rules/
│   ├── skills/
│   │   ├── b2c-team/ …
│   │   ├── de-matrix-team/ …
│   │   ├── dialog-context-index/ …
│   │   ├── presentation-team/ …
│   │   ├── sql-team/ …
│   │   ├── web-app-team/ …
│   ├── tools/
│   │   ├── dci/ …
├── .github/
│   ├── workflows/
├── .pycache_compile/
│   ├── Applications/
│   │   ├── Xcode.app/ …
│   ├── Library/
│   │   ├── Frameworks/ …
│   ├── Users/
│   │   ├── dmitrysolonnikov/ …
├── config/
│   ├── metadata.json
│   ├── metadata.yaml
│   ├── settings.yaml
├── core/
│   ├── __init__.py
│   ├── backup.py
│   ├── checkpoint.py
│   ├── column_markers.py
│   ├── config_loader.py
│   ├── diff_engine.py
│   ├── env_bootstrap.py
│   ├── excel_unified_export.py
│   ├── excel_unified_relational.py
│   ├── incremental_merge.py
│   ├── level_sql_identifier.py
│   ├── loaders.py
│   ├── materials_literature_sync.py
│   ├── matrix_schema.py
│   ├── schema.py
│   ├── skill_node_payload.py
│   ├── smtp_delivery.py
│   ├── tabular_matrix_contract.py
│   ├── tools_matcher.py
│   ├── tree.py
│   ├── upload_merge.py
├── exls_matrix/
│   ├── ai/
│   ├── arch/
│   ├── dba/
│   ├── etl_elt_modeling/
│   ├── review/
│   ├── storage/
│   ├── .DS_Store
│   ├── de_matrix_plan.md
│   ├── format_support_analysis.md
│   ├── json_to_xlsx.py
│   ├── matrix_methodology.md
│   ├── middle_de_research_notes.md
│   ├── xlsx_to_json.py
├── migrations/
│   ├── 001_initial.sql
│   ├── 002_excel_path_key.sql
│   ├── 003_domain_action_descriptions.sql
│   ├── 004_matrix_nodes.sql
│   ├── 005_drop_legacy_tree.sql
│   ├── 006_matrix_struct_schema.sql
│   ├── 007_matrix_level_registry.sql
│   ├── 008_matrix_skill_payload.sql
├── presentations/
│   ├── scr/
│   ├── middle_de_competency_matrix.html
│   ├── middle_de_competency_matrix.pdf
│   ├── middle_de_competency_matrix_v2.html
│   ├── middle_de_competency_matrix_v2.pdf
├── proxy/
│   ├── certs/
│   │   ├── live/ …
│   │   ├── provided/ …
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── nginx.conf.template
├── scripts/
│   ├── autoscale_regression_check.py
│   ├── db_backup.sh
│   ├── db_init.py
│   ├── db_restore.sh
│   ├── db_smoke_check.py
│   ├── deploy.sh
│   ├── deploy_prod.sh
│   ├── dump_unified_vitrine.py
│   ├── e2e_merge_modes_check.py
│   ├── export_presentation_pdf.sh
│   ├── fail2ban_prepare.sh
│   ├── merge_to_unified_source.py
│   ├── migrate_file_to_db.py
│   ├── notification_smoke_check.py
│   ├── notify_release.py
│   ├── prod_cleanup.sh
│   ├── prod_down.sh
│   ├── prod_rebuild.sh
│   ├── prod_status.sh
│   ├── prod_up.sh
│   ├── proxy_prepare_tls.sh
│   ├── rename_matrix_markers.py
│   ├── resolve_deploy_targets.py
│   ├── run_app.sh
│   ├── smoke_all.sh
│   ├── start.sh
│   ├── turn_to_base_config.py
│   ├── up.sh
├── security/
│   ├── fail2ban/
│   │   ├── filter.d/ …
├── static/
│   ├── css/
│   ├── js/
├── storage/
│   ├── __init__.py
│   ├── approval_repo.py
│   ├── db.py
│   ├── matrix_level_tables.py
│   ├── models.py
│   ├── mongo_repo.py
│   ├── postgres_repo.py
│   ├── runtime.py
│   ├── staging_repo.py
├── templates/
│   ├── 404.html
│   ├── 500.html
│   ├── about.html
│   ├── account.html
│   ├── account_password.html
│   ├── action_detail.html
│   ├── admin_notifications.html
│   ├── admin_presence.html
│   ├── admin_sql_console.html
│   ├── admin_tree_editor.html
│   ├── admin_users.html
│   ├── base.html
│   ├── changes.html
│   ├── constructor.html
│   ├── domain_graph.html
│   ├── domain_view.html
│   ├── export.html
│   ├── graph.html
│   ├── home.html
│   ├── import.html
│   ├── literature.html
│   ├── login.html
│   ├── matrix.html
│   ├── settings.html
├── utils/
├── .DS_Store
├── .gitignore
├── app.py
├── docker-compose.prod.yml
├── docker-compose.yml
├── Dockerfile
├── LICENSE
├── README.md
├── requirements.txt
├── tig_app_ru.py
├── TODO.md
```

## Git evolution (compact)

```text
Корень: /Users/dmitrysolonnikov/PycharmProjects/de_matrix

=== STATUS ===
M .gitignore
 D README_CUSTOM_RULES.md
 D scripts/dci-propagate.sh
 D scripts/dci-setup-projects.sh
 D scripts/dci-test.sh
 D scripts/dci-validate-all-projects.sh
 D scripts/dci-vector.sh
 D scripts/dci_embed_server.py
 D scripts/dci_vector_sync.py
 D scripts/rules-validate-all-projects.sh
 D scripts/tig-context.sh
 D scripts/tig-test.sh
 D tig_delta.md
 D tig_snapshot.md
?? .cursor/

=== LOG (12 oneline) ===
52e09d3 (HEAD -> main, origin/main) major update
b10233a alpha update
fc30d21 update readme
b42b8c7 add mail server option
32832b7 update ci stage
0886377 update release version
e2d91ef fix smoke test
349b0dc fix smoke test
5418bd0 fix smoke test
0cb4d0e fix smoke test
26140f7 fix smoke test
7d26ef9 fix smoke test
```

## File index (compressed)

### Notable files (largest / capped index)
- `presentations/middle_de_competency_matrix_v2.pdf` (2567185 bytes)
- `presentations/middle_de_competency_matrix.pdf` (884922 bytes)
- `exls_matrix/review/Мидл ДЕ -Разработка ETL_ELT.html` (402883 bytes)
- `exls_matrix/review/Мидл ДЕ -Хранение данных.html` (304517 bytes)
- `app.py` (207107 bytes)
- `templates/constructor.html` (103321 bytes)
- `.cursor/tools/dci/lib/dci_vector_sync.py` (90668 bytes)
- `exls_matrix/storage/martrix_de_storage_preview.html` (90644 bytes)
- `presentations/middle_de_competency_matrix_v2.html` (73088 bytes)
- `static/css/style.css` (63281 bytes)
- `exls_matrix/ai/matrix_de_ai.json` (61027 bytes)
- `exls_matrix/storage/matrix_de_example2.json` (56163 bytes)
- `templates/admin_tree_editor.html` (44113 bytes)
- `exls_matrix/review/Разработка ETL.review.json` (42561 bytes)
- `tig_app_ru.py` (40718 bytes)
- `core/loaders.py` (35294 bytes)
- `TODO.md` (34065 bytes)
- `exls_matrix/review/de_matrix_review_methodology.md` (32946 bytes)
- `templates/base.html` (31864 bytes)
- `templates/import.html` (31476 bytes)
- `presentations/middle_de_competency_matrix.html` (31254 bytes)
- `templates/export.html` (30669 bytes)
- `core/matrix_schema.py` (30156 bytes)
- `exls_matrix/storage/martrix_de_storage.json` (29303 bytes)
- `templates/domain_graph.html` (29167 bytes)
- `exls_matrix/ai/matrix_de_ai_answers.md` (28286 bytes)
- `exls_matrix/dba/matrix_de_dba.json` (27631 bytes)
- `templates/graph.html` (27524 bytes)
- `README.md` (27466 bytes)
- `exls_matrix/review/Хранение данных.review.json` (27059 bytes)
- `.cursor/context/vector_fallback.jsonl` (26737 bytes)
- `scripts/e2e_merge_modes_check.py` (26441 bytes)
- `exls_matrix/etl_elt_modeling/matrinx_de_etl_elt_modeling.json` (26016 bytes)
- `templates/matrix.html` (25048 bytes)
- `templates/literature.html` (24759 bytes)
- `.cursor/skills/presentation-team/SKILL.md` (24128 bytes)
- `exls_matrix/etl_elt_modeling/matrinx_de_etl_elt_modeling.csv` (23883 bytes)
- `core/schema.py` (23402 bytes)
- `templates/action_detail.html` (22673 bytes)
- `exls_matrix/arch/matrix_de_arch.json` (22319 bytes)
- `exls_matrix/matrix_methodology.md` (20273 bytes)
- `exls_matrix/ai/matrix_de_ai.xlsx` (20102 bytes)
- `core/tabular_matrix_contract.py` (19785 bytes)
- `exls_matrix/storage/martrix_de_storage_answers.md` (19742 bytes)
- `storage/models.py` (19362 bytes)
- `exls_matrix/storage/matrix_de_example2.xlsx` (19294 bytes)
- `templates/changes.html` (18704 bytes)
- `.cursor/context/dci_test_cases.md` (18204 bytes)
- `exls_matrix/storage/martrix_de_storage_preview_clean.html` (17360 bytes)
- `templates/admin_presence.html` (17169 bytes)

*+156 more files — see `tig_delta.md` git diff*