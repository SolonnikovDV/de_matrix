# Анализ форматов данных матрицы (`exls_matrix`)

Дата: 2026-05-23

## 1) Что есть сейчас

- В каталоге `exls_matrix` используются три фактических представления:
  - **CSV (semicolon-delimited)**: плоская таблица с русскими колонками (`Домен`, `Раздел`, `Навык`, ...).
  - **JSON list-of-records**: массив объектов-строк (пример: `arch/matrix_de_arch.json`, `etl_elt_modeling/matrinx_de_etl_elt_modeling.json`).
  - **JSON workbook**: объект вида `{ "source_file": "...xlsx", "sheets": { ... } }` (пример: `dataops/*.json`, `storage/*.json`).
- Для конвертации присутствуют утилиты:
  - `exls_matrix/xlsx_to_json.py` (XLSX -> JSON workbook),
  - `exls_matrix/json_to_xlsx.py` (JSON workbook -> XLSX).

## 2) Что поддерживает runtime приложения

- API импорт матрицы (`/api/source/upload/preview`, `/api/source/upload`) принимает:
  - `.json`
  - `.csv`
  - `.xlsx`
  - `.xls`
- JSON в runtime поддерживает:
  - unified (`nodes`)
  - legacy (`domains`)
  - tabular list-of-records
  - workbook dump (`source_file/sheets`, парсится первый лист)

## 3) Выявленные несовместимости

1. **Два разных JSON-стандарта в `exls_matrix`**:
   - list-of-records и workbook JSON.
   - Оба не являются runtime-unified JSON для прямой загрузки в matrix API.
2. **Семантика колонок неоднородна**:
   - встречаются варианты `Опционально` и `Опционально для уровня`,
   - есть `null` в иерархических колонках (наследование домена/раздела по строкам).

## 4) Требование из TODO и статус

Требование: единая структура должна поддерживаться через XLS/CSV/JSON.

Текущий статус:
- XLS: поддержан.
- CSV: поддержан.
- JSON: поддержан в структурированных и табличных вариантах.
- Остаточный риск: неоднородная семантика колонок и разные названия полей в наборах `exls_matrix`.

## 5) Рекомендуемый целевой контракт

Рекомендуется зафиксировать 2 уровня формата:

1. **Canonical runtime contract** (для API и БД):
   - unified JSON с `nodes` (+ `ui_config`, `action_templates`, и т.д.).
2. **Exchange tabular contract** (для редакторов/контента):
   - табличная схема колонок (XLS/CSV/JSON workbook),
   - детерминированный маппинг в canonical runtime contract.

## 6) Дальнейший план стабилизации

Уже реализовано:
1. `load_csv_for_matrix_import()` (delimiter auto-detect + utf-8/utf-8-sig/cp1251).
2. `.csv` добавлен в whitelist API upload/preview.
3. Единый конвертер `tabular -> unified nodes` используется для XLS и CSV.
4. `_normalize_unified` расширен для tabular JSON list-of-records и JSON workbook dump.

Осталось:
1. Зафиксировать единый tabular schema contract (названия/порядок колонок, nullable-поля).
2. Добавить e2e-проверку эквивалентности: один dataset в XLS/CSV/JSON -> одинаковый `nodes` snapshot.

---

Итог: базовая поддержка "XLS + CSV + JSON" реализована; следующий этап — жесткая стандартизация схемы колонок и e2e-эквивалентность форматов.
