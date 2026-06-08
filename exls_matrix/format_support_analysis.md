# Анализ форматов данных матрицы (`exls_matrix`)

Дата актуализации: 2026-05-24

## 1) Что есть сейчас

- В каталоге `exls_matrix` используются представления:
  - **JSON list-of-records**: массив объектов-строк с колонками-маркерами (пример: `etl_elt_modeling/`, `arch/`).
  - **JSON workbook**: объект `{ "source_file": "...xlsx", "sheets": { ... } }` (пример: `dataops/`).
  - **XLSX**: синхронизируется из JSON; в `.gitignore`, генерируется локально.
- Домены с маркерными заголовками (мигрированы):
  - `etl_elt_modeling/matrinx_de_etl_elt_modeling`
  - `dataops/matrix_de_dataops`
  - `arch/matrix_de_arch`
- Утилиты:
  - `exls_matrix/xlsx_to_json.py` — XLSX → JSON workbook
  - `exls_matrix/json_to_xlsx.py` — JSON workbook → XLSX
  - `scripts/rename_matrix_markers.py` — legacy русские заголовки → маркеры + XLSX

## 2) Табличный контракт (exchange format)

Канонический порядок колонок:

`node_1`, `node_2`, `node_3`, `label_3_node_3`, `leaf_1_node_3`, `leaf_2_node_3`, `leaf_3_node_3`, `label_4_node_3`, `leaf_5_node_3`, `label_1_node_3`, `label_2_node_3`

Семантика:
- `node_i` — уровень иерархии (Домен → Раздел → Навык);
- `leaf_j_node_3` — содержимое карточки навыка;
- `label_k_node_3` — наклейки навыка (статус, автор, …).

Legacy-заголовки (`Домен`, `Раздел`, …) принимаются при импорте через `core/column_markers.py`.

## 3) Что поддерживает runtime приложения

- API импорт (`/api/source/upload/preview`, `/api/source/upload`): `.json`, `.csv`, `.xlsx`, `.xls`.
- Режимы merge для Excel/CSV на `/admin/import`:
  - **`increment`** — обогащение существующей матрицы (валидация схемы + глубины дерева);
  - **`replace_all`** — полная замена.
- JSON в runtime:
  - unified (`nodes`) + `ui_config`
  - legacy (`domains`)
  - tabular list-of-records → `nodes` + `ui_config` (marker format)
  - JSON workbook (`source_file/sheets`, первый лист)
- Хранение в PostgreSQL:
  - реляционное дерево: `matrix_level_registry` + dynamic level tables;
  - свойства навыка: `skill_payload` JSONB;
  - схема колонок: `ui_config.matrix_column_schema`, `matrix_levels`.

## 4) Статус совместимости

| Аспект | Статус |
|---|---|
| XLS / CSV / JSON import | реализовано |
| Маркерные колонки | канон для etl/dataops/arch |
| Legacy русские заголовки | поддерживаются при импорте |
| Increment merge | реализовано (`core/incremental_merge.py`) |
| Export/preview 1:1 с импортом | реализовано (`build_unified_export_table`) |
| Storage domain (legacy headers) | не мигрирован, импорт через legacy mapping |

## 5) Рекомендуемый workflow

1. Редактировать контент в `*.json`.
2. Сгенерировать XLSX: `python3 scripts/rename_matrix_markers.py <file>.json --xlsx <file>.xlsx` (или `json_to_xlsx.py` для workbook JSON).
3. Первичная загрузка в app: `replace_all` → CR → Apply.
4. Догрузка домена: `increment` → CR → Apply.

## 6) Оставшиеся задачи

1. Мигрировать `storage/*` на маркеры (по мере готовности контента).
2. E2E-проверка эквивалентности: один dataset в XLS/CSV/JSON → одинаковый `nodes` snapshot.
3. E2E-сценарий `increment` в `scripts/e2e_merge_modes_check.py`.

---

Итог: единый tabular contract на маркерах зафиксирован; runtime поддерживает import/export/increment для мигрированных доменов.
