# Data Engineer Matrix (`de_matrix`)

Веб-приложение на Flask для ведения и визуализации матрицы компетенций Data Engineer:
- структура доменов/навыков/действий;
- графы и дерево компетенций;
- каталог литературы и привязки к листам;
- импорт/экспорт данных;
- бэкапы и восстановление источника.

## Что актуально сейчас

- Источник данных **единый**: `data/sources/matrix.json` (или другой файл из `source_dir`).
- `matrix_data.json` в runtime не используется.
- Импорт и экспорт выровнены по единому Excel-формату.
- Для литературы есть CRUD, привязка к листам, предпросмотр и загрузка в `data/library`.
- Есть страница `О приложении`, MIT License и конфигурируемые данные автора/репозитория.

## Основной функционал

### UI-страницы

| Страница | Маршрут | Назначение |
|---|---|---|
| Главная | `/` | Краткая статистика и навигация |
| Матрица | `/matrix` | Карточки доменов и навыков |
| Домен | `/domain/<domain_idx>` | Дерево: домен → навыки → действия → поддействия |
| Навык домена | `/domain/<domain_idx>/skill/<skill_idx>` | Дерево с фокусом на один навык |
| Глобальный граф | `/graph` | Иерархический граф всей матрицы |
| Граф домена | `/domain-graph/<domain_idx>` | Граф конкретного домена |
| Экспорт | `/export` | Табличный просмотр + XLSX/CSV |
| Импорт | `/import` | Валидация и загрузка JSON/XLSX |
| Литература | `/literature` | Каталог источников и привязки |
| Настройки | `/settings` | Работа с бэкапами и источниками |
| О приложении | `/about` | Инфо о проекте/авторе/лицензии |

### Импорт/экспорт

- Поддержка JSON/YAML/XLSX/XLS.
- Preview + validation перед применением.
- Merge-режимы загрузки:
  - `append`
  - `append_to_domain`
  - `append_to_skill`
  - `replace_all`
- Автобэкап перед изменениями источника.
- Шаблон импорта: `GET /api/import/template`.
- Единый Excel-формат:
  - `Domain`, `Skill`, `Action`, `Subaction`, `Description`, `Template ID`
  - также принимаются русские заголовки.

### Литература

- Добавление, редактирование и удаление источников.
- Привязка литературы к листам (`leaf`) матрицы.
- Загрузка файла в `data/library`.
- Загрузка по URL с определением контента.
- Предпросмотр:
  - для доступных ресурсов — в модальном iframe;
  - fallback-кнопка открытия источника в новой вкладке.

## Архитектура данных

### Единый источник

Основной файл (`matrix.json`) содержит:
- `domains` (структура матрицы),
- `action_templates`,
- `literature`,
- `action_examples`,
- `ui_config`.

### Конфигурация и кэш

- `config/settings.yaml` — пути и runtime-настройки.
- `config/metadata.yaml` / `config/metadata.json` — метаданные для UI/инструментов.
- `data/checkpoint.yaml` — чекпоинт со сверкой по хэшу источника.
- `data/backups/` — бэкапы источника.

## Структура проекта

```text
de_matrix/
├── app.py
├── core/
│   ├── backup.py
│   ├── checkpoint.py
│   ├── config_loader.py
│   ├── loaders.py
│   ├── schema.py
│   ├── tools_matcher.py
│   ├── tree.py
│   └── upload_merge.py
├── config/
│   ├── settings.yaml
│   ├── metadata.yaml
│   └── metadata.json
├── data/
│   ├── sources/
│   │   └── matrix.json
│   ├── checkpoint.yaml
│   ├── backups/
│   └── library/
├── static/
│   ├── css/style.css
│   └── js/matrix.js
├── templates/
│   ├── base.html
│   ├── home.html
│   ├── matrix.html
│   ├── domain_view.html
│   ├── graph.html
│   ├── domain_graph.html
│   ├── export.html
│   ├── import.html
│   ├── literature.html
│   ├── settings.html
│   ├── about.html
│   ├── action_detail.html
│   ├── 404.html
│   └── 500.html
├── scripts/
├── requirements.txt
├── LICENSE
└── README.md
```

## Требования

- Python 3.8+
- pip

`requirements.txt`:
- Flask, Jinja2, Werkzeug
- PyYAML
- pandas
- openpyxl
- certifi

## Быстрый старт

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

По умолчанию запуск на порту `5001`.

Параметры запуска:

```bash
python app.py --port 5001
python app.py --auto-port
python app.py --debug
```

## Конфигурация

`config/settings.yaml`:

```yaml
source_dir: data/sources
checkpoint_file: data/checkpoint.yaml
default_source: matrix.json
literature_dir: data/library
ssl_verify: false
flexible: true
```

Переменные окружения:

- `DE_MATRIX_AUTHOR_NAME`
- `DE_MATRIX_AUTHOR_TELEGRAM`
- `DE_MATRIX_REPO_URL`
- `DE_MATRIX_SSL_VERIFY` (`0/1`)

## API (актуальный набор)

### Данные и дерево

- `GET /api/matrix`
- `GET /api/tree`
- `GET /api/tree-for-link`
- `GET /api/leaves`
- `GET /api/leaf-literature`
- `GET /api/meta`

### Листья/действия/графы

- `GET /api/leaf/<path>`
- `GET /api/action/<di>/<si>/<ai>`
- `GET /api/subaction/<di>/<si>/<ai>/<sub_idx>`
- `GET /api/graph-data`
- `GET /api/domain-graph/<domain_idx>`

### Источники и импорт

- `GET /api/sources`
- `POST /api/source/load`
- `POST /api/source/upload/preview`
- `POST /api/source/upload`
- `GET /api/import/template`
- `GET /api/schema`
- `POST /api/validate`

### Литература

- `GET /api/literature`
- `POST /api/literature`
- `POST /api/literature/upload`
- `PATCH /api/literature/<lit_id>`
- `DELETE /api/literature/<lit_id>`
- `POST /api/literature/<lit_id>/link`
- `POST /api/literature/<lit_id>/download`

### Домены/бэкапы/служебные

- `GET /api/domains`
- `GET /api/domain/<domain_idx>`
- `GET /api/backups`
- `GET /api/backups/<backup_id>/compatibility`
- `POST /api/restore`
- `GET /api/reload`
- `GET /debug`

## Заметки по предпросмотру литературы

- Если ресурс в iframe не отображается, чаще всего причина на стороне внешнего сайта (`X-Frame-Options`/`CSP`).
- В модале всегда доступна кнопка открытия источника в новой вкладке.
- Для локальных файлов предпросмотр идет через `/library/<filename>`.

## Лицензия

MIT, см. файл `LICENSE`.
