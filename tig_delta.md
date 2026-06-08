---
{
  "tig_cli_version": "1.5",
  "generated_at": "2026-06-08T10:20:33Z",
  "base_ref": "origin/main",
  "base_ref_note": "origin/main",
  "snapshot": "/Users/dmitrysolonnikov/PycharmProjects/de_matrix/tig_snapshot.md",
  "snapshot_reused": true,
  "fingerprint": "sha256:23dea55d6f48ad2d",
  "git_head": "b10233aed4581eb0061082415d839559f1b75f9e",
  "git_dirty": true
}
---

# TIG Delta Report

- **Snapshot:** `tig_snapshot.md` (reused)
- **Fingerprint:** `sha256:23dea55d6f48ad2d`
- **Base ref:** `origin/main` (origin/main)

## Working tree

```text
M .env
 M .env.example
 M .gitignore
 M README.md
 M docker-compose.yml
 M exls_matrix/format_support_analysis.md
 M exls_matrix/matrix_methodology.md
?? README_CUSTOM_RULES.md
?? scripts/dci-propagate.sh
?? scripts/dci-setup-projects.sh
?? scripts/dci-test.sh
?? scripts/dci-validate-all-projects.sh
?? scripts/dci-vector.sh
?? scripts/dci_embed_server.py
?? scripts/dci_vector_sync.py
?? scripts/export_presentation_pdf.sh
?? scripts/rules-validate-all-projects.sh
?? scripts/start.sh
?? scripts/tig-context.sh
?? scripts/tig-test.sh
?? tig_delta.md
?? tig_snapshot.md
```

## Commits since base ref

```text
(no commits)
```

## Changed files vs base ref

```text
(no diff vs base ref)
```

## Unified diff vs base ref

```diff
# base: origin/main (origin/main)
(no committed diff vs base ref)
```

## Working tree diff

```diff
## Unstaged
diff --git a/.env b/.env
index bf9fe0b..9d7d0f7 100644
--- a/.env
+++ b/.env
@@ -46,6 +46,6 @@ DE_MATRIX_FAIL2BAN_MAXRETRY=30
 DE_MATRIX_LOGROTATE_INTERVAL=daily
 DE_MATRIX_LOGROTATE_COPIES=14
 
-DE_MATRIX_AUTHOR_NAME=Dmitry Solonnikov
+DE_MATRIX_AUTHOR_NAME="Dmitry Solonnikov"
 DE_MATRIX_AUTHOR_TELEGRAM=https://t.me/Dmitry_as_SoloD
 DE_MATRIX_REPO_URL=https://github.com/SolonnikovDV/de_matrix.git
diff --git a/.env.example b/.env.example
index e195c24..20c288c 100644
--- a/.env.example
+++ b/.env.example
@@ -58,6 +58,6 @@ DE_MATRIX_FAIL2BAN_MAXRETRY=30
 DE_MATRIX_LOGROTATE_INTERVAL=daily
 DE_MATRIX_LOGROTATE_COPIES=14
 
-DE_MATRIX_AUTHOR_NAME=Dmitry Solonnikov
+DE_MATRIX_AUTHOR_NAME="Dmitry Solonnikov"
 DE_MATRIX_AUTHOR_TELEGRAM=https://t.me/Dmitry_as_SoloD
 DE_MATRIX_REPO_URL=https://github.com/SolonnikovDV/de_matrix.git
diff --git a/.gitignore b/.gitignore
index 44fa027..8ea5be8 100644
--- a/.gitignore
+++ b/.gitignore
@@ -29,11 +29,8 @@ tig_snapshot_de_matrix.md
 *.xlsx
 
 # exls_matrix local/generated artifacts (keep locally, do not publish)
-exls_matrix/**/*_preview.html
-exls_matrix/**/*_preview_clean.html
-exls_matrix/**/*_answers.md
-exls_matrix/**/martrix_*
-exls_matrix/**/matrinx_*
+exls_matrix/
+presentations/
 
 # ----------------------------
 # Runtime files and backups
@@ -60,3 +57,15 @@ proxy/certs/provided/*
 
 # macOS
 .DS_Store
+
+# --- DCI local/runtime (do not publish) ---
+.cursor/dci/dci.env
+.cursor/context/.project_lock
+.cursor/context/.dialog_window_lock
+.cursor/context/vector_fallback.jsonl
+.cursor/context/.compress_snapshot.project.json
+.cursor/context/dialogs/**/.compress_snapshot.json
+.cursor/context/dialogs/**/dialog_bundle.md
+.cursor/context/dialog_bundle.md
+.cursor/context/vector_index.meta.md
+.cursor/context/dialogs/**/vector_index.meta.md
diff --git a/README.md b/README.md
index af3c412..d7f7265 100644
--- a/README.md
+++ b/README.md
@@ -48,25 +48,37 @@
 
 ### Импорт/экспорт и merge-режимы
 
-- админ-импорт Excel (`/admin/import`) с превью и валидацией;
-- Excel-импорт выполняется как `replace_all` (снос текущей структуры и инициализация новой);
+- админ-импорт Excel/JSON/CSV (`/admin/import`) с превью и валидацией;
+- **Excel/CSV на `/admin/import`**: два режима:
+  - **`increment`** (по умолчанию) — обогащение существующей матрицы: проверка схемы колонок и глубины дерева, слияние по пути Домен → Раздел → Навык;
+  - **`replace_all`** — полная замена матрицы (с подтверждением риска);
+- первичная загрузка новой матрицы — `replace_all`; догрузка доменов/навыков — `increment`;
 - пользовательский конструктор `/constructor` как альтернатива file upload;
 - git-style подтверждение из конструктора: `commit title/body`, confirm modal и отправка в CR workflow;
-- merge-режимы:
+- merge-режимы API (`/api/source/upload*`):
+  - `increment` — инкрементальное обогащение при совместимой схеме;
   - `append`
   - `append_to_domain`
   - `append_to_skill`
   - `replace_domain`
   - `replace_skill`
   - `replace_all`
+- **табличный контракт `exls_matrix`**: колонки-маркеры (канон для новых файлов):
+  - `node_1`, `node_2`, `node_3` — иерархия (Домен → Раздел → Навык);
+  - `leaf_1_node_3` … `leaf_5_node_3` — содержимое карточки навыка (вопросы, материалы, задачи, …);
+  - `label_1_node_3` … `label_4_node_3` — наклейки навыка (автор, ревьюер, статус, опционально);
+  - legacy-заголовки на русском (`Домен`, `Раздел`, …) по-прежнему принимаются при импорте;
 - импорт JSON: поддерживаются и единое дерево `nodes`, и legacy-обёртка `domains` (нормализуется в `nodes`);
 - загрузка через API (`/api/source/upload*`) принимает `.json`, `.csv`, `.xlsx`, `.xls`;
 - JSON-upload поддерживает:
   - unified (`nodes`) и legacy (`domains`) структуру;
   - табличный JSON list-of-records;
   - JSON-книгу формата `{source_file, sheets}` (парсится первый лист);
-- для файлового контура `exls_matrix` доступны конвертеры `xlsx_to_json.py` и `json_to_xlsx.py`;
-- экспорт и шаблон импорта;
+- для файлового контура `exls_matrix`:
+  - `exls_matrix/xlsx_to_json.py`, `exls_matrix/json_to_xlsx.py` — roundtrip JSON workbook ↔ XLSX;
+  - `scripts/rename_matrix_markers.py` — переименование русских заголовков в маркеры + генерация XLSX;
+- экспорт и шаблон импорта восстанавливают таблицу из БД по `matrix_column_schema` (маркеры как в импортируемом файле);
+- дерево в БД хранится реляционно: отдельная таблица на каждый уровень (`matrix_level_registry` + dynamic level tables), свойства навыка — в `skill_payload` JSONB;
 - staging batch + diff (`json_patch`, structural diff, upsert-plan).
 
 ### Governance и безопасность изменений
@@ -178,14 +190,16 @@ graph TD
 
 | Скрипт | Назначение |
 |---|---|
-| `scripts/deploy.sh` | **Деплой инфраструктуры** (postgres, mongo, smtp) |
-| `scripts/run_app.sh` | **Запуск приложения** (`python app.py` на хосте) |
+| `scripts/start.sh` | **Умный one-click запуск** — самолечение инфры, зависимостей и портов, затем `app.py` |
+| `scripts/deploy.sh` | Деплой инфраструктуры (postgres, mongo, smtp) без запуска app |
+| `scripts/run_app.sh` | Запуск `python app.py` на хосте (требует готовой инфры) |
 | `scripts/deploy_prod.sh` | **Полный деплой** (app + proxy + hardening в Docker) |
 | `scripts/up.sh` | Alias на `deploy_prod.sh` (обратная совместимость) |
 | `scripts/prod_status.sh` | Статус сервисов и ключевые URL |
 | `scripts/prod_down.sh` | Остановка стека |
 | `scripts/prod_rebuild.sh` | Переиспользуемый update-сценарий: остановка -> pull/build -> запуск |
 | `scripts/prod_cleanup.sh` | Полная очистка `de_matrix` контейнерной группы (контейнеры/сети/тома, опц. образы) |
+| `scripts/rename_matrix_markers.py` | Legacy-заголовки exls_matrix → маркеры `node_i`/`leaf`/`label` + генерация XLSX |
 | `scripts/smoke_all.sh` | Комплексный smoke/e2e прогон |
 | `scripts/db_backup.sh` | Backup PostgreSQL/Mongo |
 | `scripts/db_restore.sh` | Restore PostgreSQL/Mongo |
@@ -245,19 +259,20 @@ de_matrix/
 
 ### 5.1 Два режима запуска
 
-| Режим | Деплой | Запуск приложения | URL |
-|---|---|---|---|
-| **Разработка (host app)** | `bash scripts/deploy.sh` | `bash scripts/run_app.sh` или `python app.py` | `http://localhost:5001` |
-| **Production (all-in-docker)** | `bash scripts/deploy_prod.sh` | app уже в контейнере `de-matrix-app` | `https://localhost` |
+| Режим | Команда | URL |
+|---|---|---|
+| **Разработка (host app)** | `bash scripts/start.sh` | `http://localhost:5001` |
+| **Production (all-in-docker)** | `bash scripts/deploy_prod.sh` | `https://localhost` |
 
-**Разработка** — инфраструктура в Docker, процесс приложения на хосте через `app.py`:
+**Разработка** — один скрипт делает всё: проверяет Docker, поднимает инфру, чинит порты, обновляет зависимости, запускает app:
 
 ```bash
 chmod +x ./scripts/*.sh
-bash ./scripts/deploy.sh      # postgres + mongo + smtp
-bash ./scripts/run_app.sh     # python app.py с автозагрузкой .env
+bash ./scripts/start.sh
 ```
 
+> `start.sh` — самодостаточный: при первом запуске копирует `.env.example` → `.env`, создаёт `.venv`, устанавливает зависимости. При повторных — умный `no-op` для всего, что уже готово.
+
 **Production / полный стек** — app + proxy + hardening в контейнерах:
 
 ```bash
@@ -275,16 +290,14 @@ bash ./scripts/prod_rebuild.sh
 
 ```bash
 bash ./scripts/prod_rebuild.sh --host-dev
-bash ./scripts/run_app.sh
+bash ./scripts/start.sh
 ```
 
 ### 5.2 Первый запуск (кратко)
 
 ```bash
 chmod +x ./scripts/*.sh
-cp .env.example .env   # если .env ещё нет
-bash ./scripts/deploy.sh
-bash ./scripts/run_app.sh
+bash ./scripts/start.sh   # всё остальное — автоматически
 ```
 
 Проверка:
@@ -327,6 +340,9 @@ bash ./scripts/prod_status.sh
 
 ### 7.1 Подготовка локальной среды
 
+`start.sh` создаёт `.venv` и устанавливает зависимости автоматически.  
+Для ручной настройки:
+
 ```bash
 python3 -m venv .venv
 source .venv/bin/activate
@@ -337,9 +353,14 @@ pip install -r requirements.txt
 
 Host app (рекомендуется для разработки):
 
+```bash
+bash ./scripts/start.sh   # one-click: инфра + порты + deps + app
+```
+
+Только инфраструктура (без запуска app):
+
 ```bash
 bash ./scripts/deploy.sh
-bash ./scripts/run_app.sh
 ```
 
 Full docker stack:
@@ -522,6 +543,7 @@ docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=200
 | `Password change required` | Временный пароль | Завершить смену пароля на `/account/password` |
 | `app restarting` | рассинхрон схемы БД/моделей | применить миграции и перезапустить app |
 | e2e/smoke fail после rollback | Изменилось состояние БД | повторить `db_init`, проверить пользователей и CR |
+| Инкремент: «глубина дерева не совпадает» | Устаревший `ui_config` в БД после Apply | обновить app, при необходимости повторный Apply CR с актуальным `ui_config` |
 | Нет писем на реальную почту | Mailpit только перехватывает SMTP | открыть UI Mailpit по `DE_MATRIX_MAIL_UI_PORT` или настроить внешний SMTP + TLS/логин |
 | Уведомления `skipped` / пустые получатели | В профиле нет email | заполнить email у админов/авторов; смотреть `/admin/notifications` |
 | `Connection refused` к SMTP | Неверный host/port для среды | в контейнере app — `smtp:1025`; с хоста — `127.0.0.1` и порт проброса Mailpit |
diff --git a/docker-compose.yml b/docker-compose.yml
index 7d9f55c..750f61d 100644
--- a/docker-compose.yml
+++ b/docker-compose.yml
@@ -62,7 +62,7 @@ services:
       POSTGRES_USER: dematrix
       POSTGRES_PASSWORD: dematrix
     ports:
-      - "127.0.0.1:${DE_MATRIX_POSTGRES_PORT:-15432}:5432"
+      - "0:5432"   # dynamic host port — actual value discovered by start.sh via `docker compose port`
     volumes:
       - postgres_data:/var/lib/postgresql/data
     healthcheck:
@@ -73,12 +73,13 @@ services:
     restart: unless-stopped
     networks:
       - backend
+      - edge   # required for Docker Desktop host port binding (internal-only networks block proxy)
 
   mongo:
     image: mongo:7
     container_name: de-matrix-mongo
     ports:
-      - "127.0.0.1:${DE_MATRIX_MONGO_PORT:-27018}:27017"
+      - "0:27017"   # dynamic host port
     volumes:
       - mongo_data:/data/db
     healthcheck:
@@ -89,13 +90,14 @@ services:
     restart: unless-stopped
     networks:
       - backend
+      - edge   # required for Docker Desktop host port binding
 
   smtp:
     image: axllent/mailpit:latest
     container_name: de-matrix-smtp
     ports:
-      - "127.0.0.1:${DE_MATRIX_MAIL_UI_PORT:-18025}:8025"
-      - "127.0.0.1:${DE_MATRIX_MAIL_SMTP_PORT:-11025}:1025"
+      - "0:8025"   # dynamic — mailpit UI
+      - "0:1025"   # dynamic — mailpit SMTP
     restart: unless-stopped
     networks:
       - edge
diff --git a/exls_matrix/format_support_analysis.md b/exls_matrix/format_support_analysis.md
index ca2cedd..69b1233 100644
--- a/exls_matrix/format_support_analysis.md
+++ b/exls_matrix/format_support_analysis.md
@@ -1,71 +1,75 @@
 # Анализ форматов данных матрицы (`exls_matrix`)
 
-Дата: 2026-05-23
+Дата актуализации: 2026-05-24
 
 ## 1) Что есть сейчас
 
-- В каталоге `exls_matrix` используются три фактических представления:
-  - **CSV (semicolon-delimited)**: плоская таблица с русскими колонками (`Домен`, `Раздел`, `Навык`, ...).
-  - **JSON list-of-records**: массив объектов-строк (пример: `arch/matrix_de_arch.json`, `etl_elt_modeling/matrinx_de_etl_elt_modeling.json`).
-  - **JSON workbook**: объект вида `{ "source_file": "...xlsx", "sheets": { ... } }` (пример: `dataops/*.json`, `storage/*.json`).
-- Для конвертации присутствуют утилиты:
-  - `exls_matrix/xlsx_to_json.py` (XLSX -> JSON workbook),
-  - `exls_matrix/json_to_xlsx.py` (JSON workbook -> XLSX).
-
-## 2) Что поддерживает runtime приложения
-
-- API импорт матрицы (`/api/source/upload/preview`, `/api/source/upload`) принимает:
-  - `.json`
-  - `.csv`
-  - `.xlsx`
-  - `.xls`
-- JSON в runtime поддерживает:
-  - unified (`nodes`)
-  - legacy (`domains`)
-  - tabular list-of-records
-  - workbook dump (`source_file/sheets`, парсится первый лист)
+- В каталоге `exls_matrix` используются представления:
+  - **JSON list-of-records**: массив объектов-строк с колонками-маркерами (пример: `etl_elt_modeling/`, `arch/`).
+  - **JSON workbook**: объект `{ "source_file": "...xlsx", "sheets": { ... } }` (пример: `dataops/`).
+  - **XLSX**: синхронизируется из JSON; в `.gitignore`, генерируется локально.
+- Домены с маркерными заголовками (мигрированы):
+  - `etl_elt_modeling/matrinx_de_etl_elt_modeling`
+  - `dataops/matrix_de_dataops`
+  - `arch/matrix_de_arch`
+- Утилиты:
+  - `exls_matrix/xlsx_to_json.py` — XLSX → JSON workbook
+  - `exls_matrix/json_to_xlsx.py` — JSON workbook → XLSX
+  - `scripts/rename_matrix_markers.py` — legacy русские заголовки → маркеры + XLSX
+
+## 2) Табличный контракт (exchange format)
 
-## 3) Выявленные несовместимости
+Канонический порядок колонок:
 
-1. **Два разных JSON-стандарта в `exls_matrix`**:
-   - list-of-records и workbook JSON.
-   - Оба не являются runtime-unified JSON для прямой загрузки в matrix API.
-2. **Семантика колонок неоднородна**:
-   - встречаются варианты `Опционально` и `Опционально для уровня`,
-   - есть `null` в иерархических колонках (наследование домена/раздела по строкам).
+`node_1`, `node_2`, `node_3`, `label_3_node_3`, `leaf_1_node_3`, `leaf_2_node_3`, `leaf_3_node_3`, `label_4_node_3`, `leaf_5_node_3`, `label_1_node_3`, `label_2_node_3`
 
-## 4) Требование из TODO и статус
+Семантика:
+- `node_i` — уровень иерархии (Домен → Раздел → Навык);
+- `leaf_j_node_3` — содержимое карточки навыка;
+- `label_k_node_3` — наклейки навыка (статус, автор, …).
 
-Требование: единая структура должна поддерживаться через XLS/CSV/JSON.
+Legacy-заголовки (`Домен`, `Раздел`, …) принимаются при импорте через `core/column_markers.py`.
 
-Текущий статус:
-- XLS: поддержан.
-- CSV: поддержан.
-- JSON: поддержан в структурированных и табличных вариантах.
-- Остаточный риск: неоднородная семантика колонок и разные названия полей в наборах `exls_matrix`.
+## 3) Что поддерживает runtime приложения
+
+- API импорт (`/api/source/upload/preview`, `/api/source/upload`): `.json`, `.csv`, `.xlsx`, `.xls`.
+- Режимы merge для Excel/CSV на `/admin/import`:
+  - **`increment`** — обогащение существующей матрицы (валидация схемы + глубины дерева);
+  - **`replace_all`** — полная замена.
+- JSON в runtime:
+  - unified (`nodes`) + `ui_config`
+  - legacy (`domains`)
+  - tabular list-of-records → `nodes` + `ui_config` (marker format)
+  - JSON workbook (`source_file/sheets`, первый лист)
+- Хранение в PostgreSQL:
+  - реляционное дерево: `matrix_level_registry` + dynamic level tables;
+  - свойства навыка: `skill_payload` JSONB;
+  - схема колонок: `ui_config.matrix_column_schema`, `matrix_levels`.
 
-## 5) Рекомендуемый целевой контракт
+## 4) Статус совместимости
 
-Рекомендуется зафиксировать 2 уровня формата:
+| Аспект | Статус |
+|---|---|
+| XLS / CSV / JSON import | реализовано |
+| Маркерные колонки | канон для etl/dataops/arch |
+| Legacy русские заголовки | поддерживаются при импорте |
+| Increment merge | реализовано (`core/incremental_merge.py`) |
+| Export/preview 1:1 с импортом | реализовано (`build_unified_export_table`) |
+| Storage domain (legacy headers) | не мигрирован, импорт через legacy mapping |
 
-1. **Canonical runtime contract** (для API и БД):
-   - unified JSON с `nodes` (+ `ui_config`, `action_templates`, и т.д.).
-2. **Exchange tabular contract** (для редакторов/контента):
-   - табличная схема колонок (XLS/CSV/JSON workbook),
-   - детерминированный маппинг в canonical runtime contract.
+## 5) Рекомендуемый workflow
 
-## 6) Дальнейший план стабилизации
+1. Редактировать контент в `*.json`.
+2. Сгенерировать XLSX: `python3 scripts/rename_matrix_markers.py <file>.json --xlsx <file>.xlsx` (или `json_to_xlsx.py` для workbook JSON).
+3. Первичная загрузка в app: `replace_all` → CR → Apply.
+4. Догрузка домена: `increment` → CR → Apply.
 
-Уже реализовано:
-1. `load_csv_for_matrix_import()` (delimiter auto-detect + utf-8/utf-8-sig/cp1251).
-2. `.csv` добавлен в whitelist API upload/preview.
-3. Единый конвертер `tabular -> unified nodes` используется для XLS и CSV.
-4. `_normalize_unified` расширен для tabular JSON list-of-records и JSON workbook dump.
+## 6) Оставшиеся задачи
 
-Осталось:
-1. Зафиксировать единый tabular schema contract (названия/порядок колонок, nullable-поля).
-2. Добавить e2e-проверку эквивалентности: один dataset в XLS/CSV/JSON -> одинаковый `nodes` snapshot.
+1. Мигрировать `storage/*` на маркеры (по мере готовности контента).
+2. E2E-проверка эквивалентности: один dataset в XLS/CSV/JSON → одинаковый `nodes` snapshot.
+3. E2E-сценарий `increment` в `scripts/e2e_merge_modes_check.py`.
 
 ---
 
-Итог: базовая поддержка "XLS + CSV + JSON" реализована; следующий этап — жесткая стандартизация схемы колонок и e2e-эквивалентность форматов.
+Итог: единый tabular contract на маркерах зафиксирован; runtime поддерживает import/export/increment для мигрированных доменов.
diff --git a/exls_matrix/matrix_methodology.md b/exls_matrix/matrix_methodology.md
index 51d0a7a..4fbcf77 100644
--- a/exls_matrix/matrix_methodology.md
+++ b/exls_matrix/matrix_methodology.md
@@ -72,34 +72,68 @@
 
 ## 5) Каноническая схема данных
 
-Обязательные поля строки навыка:
-- `Домен`
-- `Раздел`
-- `Навык`
-- `Статус`
-- `Вопросы`
-- `Материалы`
-- `Задачи`
-- `Опционально` или `Опционально для уровня` (см. правило совместимости ниже)
... [working tree diff: truncated, 163 lines omitted]
```
