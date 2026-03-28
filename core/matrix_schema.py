# -*- coding: utf-8 -*-
"""
Схема уровней матрицы и теги колонок (item / leaf_view / skill_sticker).

Модель сущностей (unified relational): каждая строка Excel описывает цепочку item-колонок;
узел дерева — item с дочерними item, лист — item без дочерних. Колонки с тегом leaf_view задают
свойства листа (карточка листа); skill_sticker — метка уровня (в т.ч. ответственный по шапке файла).
Теги — только в полях tags[] и в полном header строки Excel; для UI см. schema_entries_for_ui / display_header_for_schema_entry.
Единая точка формирования колонок: effective_matrix_column_schema(ui_config) — из matrix_column_schema
в **порядке списка как после импорта** (1:1 с файлом) или синтетически из matrix_levels.

Опции ui_config (без схемы из файла):
- synthetic_leaf_view_columns: [{ "leaf_view_key"|"key", "label"|"header" }, ...]
- default_leaf_view_keys: ["readiness", ...] — только ключи, подпись = ключ
matrix_levels[].responsible_column_label — подпись колонки (skill_sticker), напр. из шапки Excel при импорте.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional, Tuple

TAG_ITEM = "item"
TAG_LEAF_VIEW = "leaf_view"
TAG_SKILL_STICKER = "skill_sticker"
STICKER_GRADES = ("junior", "middle", "senior")

# Тексты-заглушки для поля ответственного: не сохраняем и не показываем как «заполнено».
_PLACEHOLDER_RESPONSIBLE_NORMALIZED = frozenset(
    {
        "",
        "не указан",
        "не указано",
        "не указаны",
        "n/a",
        "na",
        "-",
        "—",
        "нет",
        "отсутствует",
        "not specified",
        "none",
        "null",
    }
)

_RU_TO_LAT_LOWER = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def normalize_responsible_value(val: Any) -> str:
    """Пустая строка, если значение — заглушка или пусто (импорт / API)."""
    s = str(val or "").strip()
    if not s:
        return ""
    low = s.lower().replace("ё", "е")
    if low in _PLACEHOLDER_RESPONSIBLE_NORMALIZED:
        return ""
    collapsed = low.replace(" ", "")
    if collapsed in _PLACEHOLDER_RESPONSIBLE_NORMALIZED:
        return ""
    return s


def responsible_field_is_meaningful(val: Any) -> bool:
    return bool(normalize_responsible_value(val))


def slugify_matrix_level_title(title: str, depth: int, max_len: int = 96) -> str:
    """
    Латинский идентификатор уровня по смыслу заголовка (кириллица → транслит).
    Для пустого / служебного заголовка — level_{depth}.
    """
    raw = str(title or "").strip()
    low_comp = raw.lower().replace(" ", "")
    if not raw or (low_comp and re.fullmatch(r"item_\d+", low_comp)):
        return f"level_{int(depth)}"
    buf: List[str] = []
    for ch in raw.lower():
        if ch in _RU_TO_LAT_LOWER:
            buf.append(_RU_TO_LAT_LOWER[ch])
        elif "a" <= ch <= "z" or ch.isdigit():
            buf.append(ch)
        elif ch in " _-/\\.":
            buf.append("_")
        else:
            buf.append("")
    s = "".join(buf)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        return f"level_{int(depth)}"
    if not re.match(r"^[a-z]", s):
        s = f"l_{s}"
    return s[:max_len]


# Глубина в дереве API: 0=корень, 1=второй уровень, … Подписи по умолчанию (если в импорте нет matrix_levels).
DEFAULT_MATRIX_LEVELS: List[Dict[str, Any]] = [
    {"depth": 0, "title": "Область компетенций", "tags": [TAG_ITEM]},
    {"depth": 1, "title": "Навык", "tags": [TAG_ITEM, TAG_SKILL_STICKER], "skill_responsible": True},
    {"depth": 2, "title": "Действие", "tags": [TAG_ITEM], "grade_stickers": True},
    {"depth": 3, "title": "Поддействие", "tags": [TAG_ITEM], "grade_stickers": True},
]

def _is_placeholder_matrix_column_label(lab: str) -> bool:
    """
    True если label похож на технический служебный идентификатор колонки (item_0, ITEM_01),
    а не на человекочитаемую подпись из Excel — тогда для UI берём текст из header.
    """
    s = (lab or "").strip()
    if not s:
        return True
    low = s.lower().replace(" ", "")
    return bool(re.fullmatch(r"item_\d+", low))


_LEAF_VIEW_KEY_ALIASES: Tuple[Tuple[str, str], ...] = (
    ("readiness", "readiness"),
    ("criteria", "readiness"),
    ("критерии", "readiness"),
    ("antipatterns", "antipatterns"),
    ("антипаттерн", "antipatterns"),
    ("stack", "stack"),
    ("технологический", "stack"),
    ("sources", "sources"),
    ("источник", "sources"),
    ("questions", "questions"),
    ("вопрос", "questions"),
    ("toolkit", "toolkit"),
    ("review", "questions"),
)


def parse_header_tag_cell(raw: str) -> Tuple[str, List[str]]:
    """
    'Область компетенций (item)' -> ('Область компетенций', ['item'])
    'Ответственный (skill_sticker)' -> ('Ответственный', ['skill_sticker'])
    Несколько тегов: '(item, leaf_view)'.
    """
    text = str(raw or "").strip()
    if not text:
        return "", []
    m = re.search(r"\(([^)]*)\)\s*$", text)
    if not m:
        return text, []
    label = text[: m.start()].strip()
    inner = m.group(1)
    tags = [t.strip().lower() for t in re.split(r"[,;|]", inner) if t.strip()]
    return label, tags


def display_header_for_schema_entry(
    entry: Dict[str, Any], ui_config: Optional[Dict[str, Any]] = None
) -> str:
    """
    Подпись колонки для UI/API без суффикса (тегов) в скобках.
    Теги остаются в entry['tags'] и в полном header при экспорте в Excel.
    Служебные label (item_0, ITEM_01) игнорируются — используется разбор полного header из файла.
    При пустом тексте в header (например только «(item)») — title из matrix_levels для item_depth.
    """
    if not isinstance(entry, dict):
        return ""
    lab = str(entry.get("label") or "").strip()
    raw = str(entry.get("header") or "").strip()
    if lab and not _is_placeholder_matrix_column_label(lab):
        return lab
    if raw:
        text, _tags = parse_header_tag_cell(raw)
        text = text.strip()
        if text and not _is_placeholder_matrix_column_label(text):
            return text
    tags_low = [str(t).lower() for t in (entry.get("tags") or [])]
    if ui_config is not None:
        if TAG_ITEM in tags_low and entry.get("item_depth") is not None:
            dep = int(entry["item_depth"])
            row = level_schema_for_depth(ui_config, dep)
            t = str(row.get("title") or "").strip()
            if t and not _is_placeholder_matrix_column_label(t):
                return t
            return f"Слой {dep + 1}"
        if TAG_SKILL_STICKER in tags_low:
            r = responsible_column_label_from_ui(ui_config)
            if r:
                return r
    if raw:
        rstrip = raw.strip()
        txt, _ = parse_header_tag_cell(rstrip)
        t2 = (txt or "").strip()
        if t2 and not _is_placeholder_matrix_column_label(t2):
            return t2
        if rstrip and not _is_placeholder_matrix_column_label(rstrip):
            return rstrip
    return ""


def coalesce_schema_entry_labels(
    entry: Dict[str, Any], ui_config: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Подставляет человекочитаемый label вместо служебных item_0 / пустых значений
    (как после старых импортов), чтобы UI и экспорт совпадали с валидацией Excel.
    """
    if not isinstance(entry, dict):
        return {}
    e = copy.deepcopy(entry)
    lab = str(e.get("label") or "").strip()
    if lab and not _is_placeholder_matrix_column_label(lab):
        return e
    disp = display_header_for_schema_entry(e, ui_config)
    tags = [str(t).lower() for t in (e.get("tags") or [])]
    if not disp and ui_config:
        if TAG_SKILL_STICKER in tags:
            disp = responsible_column_label_from_ui(ui_config)
        elif TAG_ITEM in tags and e.get("item_depth") is not None:
            row = level_schema_for_depth(ui_config, int(e["item_depth"]))
            t = str(row.get("title") or "").strip()
            if t and not _is_placeholder_matrix_column_label(t):
                disp = t
    if disp and (_is_placeholder_matrix_column_label(lab) or not lab):
        e["label"] = disp
    return e


def file_header_for_schema_entry(
    entry: Dict[str, Any], ui_config: Optional[Dict[str, Any]] = None
) -> str:
    """
    Заголовок колонки для строки 1 Excel при экспорте unified — как при импорте (суффикс с тегами).
    Если в БД сохранён полный человекочитаемый header из файла — возвращаем его; иначе собираем display_header + (tags).
    """
    if not isinstance(entry, dict):
        return ""
    raw = str(entry.get("header") or "").strip()
    tags = [str(t).strip().lower() for t in (entry.get("tags") or []) if str(t).strip()]

    if raw and re.search(r"\([^)]*\)\s*$", raw):
        cap_txt, _ = parse_header_tag_cell(raw)
        t0 = (cap_txt or "").strip()
        if t0 and not _is_placeholder_matrix_column_label(t0):
            return raw

    base = display_header_for_schema_entry(entry, ui_config)
    if not base:
        lab = str(entry.get("label") or "").strip()
        if lab and not _is_placeholder_matrix_column_label(lab):
            base = lab
    if base and tags:
        return f"{base} ({', '.join(tags)})"
    if tags:
        return f"({', '.join(tags)})"
    return base or ""


def matrix_roundtrip_header_cell(
    entry: Dict[str, Any], ui_config: Optional[Dict[str, Any]] = None
) -> str:
    """
    Ячейка строки 1 unified Excel для шаблона и выгрузки: как в импортированном файле (поле header),
    иначе сборка через file_header (синтетическая схема).
    """
    if not isinstance(entry, dict):
        return ""
    raw = str(entry.get("header") or "").strip()
    if raw:
        return raw
    return file_header_for_schema_entry(entry, ui_config)


def matrix_preview_column_caption(
    entry: Dict[str, Any], ui_config: Optional[Dict[str, Any]] = None
) -> str:
    """
    Подпись колонки без тегов для превью/API: текст из шапки файла до «(tags)»,
    иначе display_header (matrix_levels / схема).
    """
    if not isinstance(entry, dict):
        return ""
    raw = str(entry.get("header") or "").strip()
    if raw:
        text, _ = parse_header_tag_cell(raw)
        t = (text or "").strip()
        if t:
            return t
    return display_header_for_schema_entry(entry, ui_config) or ""


def schema_entries_for_ui(
    schema: Optional[List[Any]], ui_config: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Копия схемы колонок: подписи как у импорта (до скобок с тегами), затем фолбэк на схему."""
    if not isinstance(schema, list):
        return []
    out: List[Dict[str, Any]] = []
    for ent in schema:
        if not isinstance(ent, dict):
            continue
        d = copy.deepcopy(ent)
        disp = matrix_preview_column_caption(ent, ui_config)
        d["header"] = disp
        lab0 = str(d.get("label") or "").strip()
        if not lab0 or _is_placeholder_matrix_column_label(lab0):
            d["label"] = disp if disp else lab0
        out.append(d)
    return out


def leaf_view_key_from_header_label(label: str) -> str:
    low = (label or "").lower()
    for needle, key in _LEAF_VIEW_KEY_ALIASES:
        if needle in low:
            return key
    slug = re.sub(r"[^a-z0-9]+", "_", low, flags=re.I).strip("_")
    return slug or "extra"


def build_constructor_levels(
    ui_config: Optional[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Упорядоченное описание уровней для UI конструктора: из merge_matrix_levels + подсказки колонок
    из matrix_column_schema (item + item_depth). Без хардкода имён уровней на клиенте.

    После последней строки matrix_levels по умолчанию добавляется один «синтетический» шаг
    (constructor_extra_leaf_steps, по умолчанию 1), чтобы можно было выбрать или создать дочерний
    узел в subactions — иначе последняя строка схемы воспринимается как конец пути и лист
    в дереве JSON недоступен. Отключение: ui_config.constructor_extra_leaf_steps = 0.

    Возвращает (levels, applied_extra_leaf_steps).
    """
    levels = merge_matrix_levels(ui_config)
    mcs_raw = (ui_config or {}).get("matrix_column_schema")
    mcs: List[Dict[str, Any]] = [e for e in (mcs_raw if isinstance(mcs_raw, list) else []) if isinstance(e, dict)]

    item_entries_by_step: Dict[int, List[Dict[str, Any]]] = {}
    inferred_next = 0
    for ent in mcs:
        if not isinstance(ent, dict):
            continue
        tags = [str(t).lower() for t in (ent.get("tags") or [])]
        if TAG_ITEM not in tags:
            continue
        idep = ent.get("item_depth")
        if idep is None:
            idep = inferred_next
            inferred_next += 1
        else:
            inferred_next = max(inferred_next, int(idep) + 1)
        idep = int(idep)
        disp = display_header_for_schema_entry(ent, ui_config)
        lab_ent = str(ent.get("label") or "").strip()
        col_lab = disp or lab_ent
        item_entries_by_step.setdefault(idep, []).append(
            {
                "label": col_lab,
                "header": disp,
                "tags": list(ent.get("tags") or []),
                "maps_to": str(ent.get("maps_to") or "").strip(),
                "leaf_view_key": str(ent.get("leaf_view_key") or "").strip(),
            }
        )

    out: List[Dict[str, Any]] = []
    for step, row in enumerate(levels):
        depth = int(row.get("depth", step))
        if step == 0:
            role = "domain"
        elif step == 1:
            role = "skill"
        elif step == 2:
            role = "action"
        else:
            role = "subaction"
        cols = item_entries_by_step.get(step, [])
        if not cols:
            cols = item_entries_by_step.get(depth, [])
        title = str(row.get("title") or "").strip()
        if not title and cols and cols[0].get("label"):
            title = str(cols[0]["label"]).strip()
        if not title:
            title = item_column_fallback_label(ui_config, depth)
        out.append(
            {
                "step": step,
                "depth": depth,
                "title": title,
                "slug": str(row.get("slug") or "").strip()
                or slugify_matrix_level_title(title, depth),
                "tags": list(row.get("tags") or [TAG_ITEM]),
                "skill_responsible": bool(row.get("skill_responsible")),
                "grade_stickers": bool(row.get("grade_stickers")),
                "role": role,
                "columns": cols,
            }
        )

    extra_raw = (ui_config or {}).get("constructor_extra_leaf_steps")
    if extra_raw is None:
        extra = 1
    else:
        try:
            extra = int(extra_raw)
        except (TypeError, ValueError):
            extra = 0
    extra = max(0, min(extra, 16))
    leaf_title_base = str((ui_config or {}).get("constructor_leaf_step_title") or "").strip() or "Лист / подуровень"
    for k in range(extra):
        prev = out[-1] if out else None
        step = len(out)
        depth = int(prev["depth"]) + 1 if prev else 0
        title = leaf_title_base if extra == 1 else f"{leaf_title_base} ({k + 1})"
        out.append(
            {
                "step": step,
                "depth": depth,
                "title": title,
                "slug": slugify_matrix_level_title(title, depth),
                "tags": [TAG_ITEM],
                "skill_responsible": False,
                "grade_stickers": bool(prev.get("grade_stickers")) if prev else False,
                "role": "subaction",
                "columns": [],
                "synthetic": True,
            }
        )
    return out, extra


def merge_matrix_levels(ui_config: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Объединяет matrix_levels из ui_config с дефолтами по depth."""
    cfg = ui_config or {}
    custom = cfg.get("matrix_levels")
    if not isinstance(custom, list) or not custom:
        merged_default = copy.deepcopy(DEFAULT_MATRIX_LEVELS)
        for row in merged_default:
            raw_slug = str(row.get("slug") or "").strip()
            if raw_slug and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,95}", raw_slug):
                row["slug"] = raw_slug.lower()
            else:
                title = str(row.get("title") or "").strip()
                row["slug"] = slugify_matrix_level_title(title, int(row.get("depth", 0)))
        return merged_default
    by_depth: Dict[int, Dict[str, Any]] = {}
    for row in DEFAULT_MATRIX_LEVELS:
        by_depth[int(row["depth"])] = copy.deepcopy(row)
    for row in custom:
        if not isinstance(row, dict) or "depth" not in row:
            continue
        d = int(row["depth"])
        base = by_depth.setdefault(d, {"depth": d, "tags": [TAG_ITEM]})
        if row.get("title"):
            base["title"] = str(row["title"])
        if row.get("tags"):
            base["tags"] = list(row["tags"])
        if "grade_stickers" in row:
            base["grade_stickers"] = bool(row["grade_stickers"])
        if "skill_responsible" in row:
            base["skill_responsible"] = bool(row["skill_responsible"])
        if "responsible_column_label" in row:
            base["responsible_column_label"] = str(row.get("responsible_column_label") or "")
        s_in = str(row.get("slug") or "").strip()
        if s_in:
            base["slug"] = s_in
    merged = [by_depth[k] for k in sorted(by_depth)]
    for row in merged:
        raw_slug = str(row.get("slug") or "").strip()
        if raw_slug and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,95}", raw_slug):
            row["slug"] = raw_slug.lower()
            continue
        title = str(row.get("title") or "").strip()
        row["slug"] = slugify_matrix_level_title(title, int(row.get("depth", 0)))
    return merged


def index_to_excel_column(idx: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    n = idx + 1
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def excel_column_sort_key(col: str) -> Tuple[int, int]:
    c = (col or "").upper().strip()
    if not c or not c.isalpha():
        return (9999, 0)
    w = 0
    for ch in c:
        w = w * 26 + (ord(ch) - 64)
    return (len(c), w)


def _label_from_raw_matrix_column_schema_for_depth(
    ui_config: Optional[Dict[str, Any]], depth: int
) -> str:
    """
    Подпись item-уровня из сохранённой matrix_column_schema (без вызова effective_matrix_column_schema,
    чтобы не зациклиться с build_synthetic_matrix_column_schema).
    Учитывает колонки без item_depth: порядок по букве Excel, как в build_constructor_levels.
    """
    mcs_raw = (ui_config or {}).get("matrix_column_schema")
    if not isinstance(mcs_raw, list) or not mcs_raw:
        return ""
    schema = [e for e in mcs_raw if isinstance(e, dict)]
    item_entries = [
        e
        for e in schema
        if isinstance(e, dict) and TAG_ITEM in [str(t).lower() for t in (e.get("tags") or [])]
    ]
    inferred_next = 0
    for ent in item_entries:
        idep = ent.get("item_depth")
        if idep is None:
            idep = inferred_next
            inferred_next += 1
        else:
            idep = int(idep)
            inferred_next = max(inferred_next, idep + 1)
        if idep != int(depth):
            continue
        ent_c = coalesce_schema_entry_labels(ent, ui_config)
        cap = display_header_for_schema_entry(ent_c, ui_config)
        if cap:
            return cap
    row = level_schema_for_depth(ui_config, int(depth))
    t = str(row.get("title") or "").strip()
    if t and not _is_placeholder_matrix_column_label(t):
        return t
    return ""


def item_column_fallback_label(ui_config: Optional[Dict[str, Any]], depth: int) -> str:
    """Подпись item-уровня: matrix_column_schema → matrix_levels → нейтральный слой (без item_n)."""
    from_schema = _label_from_raw_matrix_column_schema_for_depth(ui_config, depth)
    if from_schema:
        return from_schema
    row = level_schema_for_depth(ui_config, depth)
    t = str(row.get("title") or "").strip()
    if t and not _is_placeholder_matrix_column_label(t):
        return t
    return f"Слой {int(depth) + 1}"


def responsible_column_label_from_ui(ui_config: Optional[Dict[str, Any]]) -> str:
    """Текст слева от (skill_sticker) при синтетической схеме."""
    for row in merge_matrix_levels(ui_config or {}):
        if not row.get("skill_responsible"):
            continue
        lab = str(row.get("responsible_column_label") or "").strip()
        if lab:
            return lab
    return TAG_SKILL_STICKER.replace("_", " ")


def leaf_specs_for_synthetic_ui(ui_config: Optional[Dict[str, Any]]) -> List[Tuple[str, str]]:
    """Пары (leaf_view_key, label) для синтетических колонок (leaf_view)."""
    ui = ui_config or {}
    raw = ui.get("synthetic_leaf_view_columns")
    out: List[Tuple[str, str]] = []
    if isinstance(raw, list):
        for ent in raw:
            if not isinstance(ent, dict):
                continue
            key = str(ent.get("leaf_view_key") or ent.get("key") or "").strip()
            if not key:
                continue
            lab = str(ent.get("label") or ent.get("header") or "").strip() or key
            out.append((key, lab))
    if out:
        return out
    keys = ui.get("default_leaf_view_keys")
    if isinstance(keys, list) and keys:
        for k in keys:
            kk = str(k).strip()
            if kk:
                out.append((kk, kk))
        return out
    return [("readiness", "readiness")]


def build_synthetic_matrix_column_schema(ui_config: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Колонки unified без сохранённой matrix_column_schema — только из merge_matrix_levels и опций ui."""
    ui = ui_config or {}
    mcs: List[Dict[str, Any]] = []
    idx = 0
    for row in merge_matrix_levels(ui):
        depth = int(row.get("depth", idx))
        title = item_column_fallback_label(ui, depth)
        col = index_to_excel_column(idx)
        idx += 1
        mcs.append(
            {
                "col": col,
                "header": f"{title} ({TAG_ITEM})",
                "label": title,
                "tags": [TAG_ITEM],
                "item_depth": depth,
            }
        )
    resp_label = responsible_column_label_from_ui(ui)
    mcs.append(
        {
            "col": index_to_excel_column(idx),
            "header": f"{resp_label} ({TAG_SKILL_STICKER})",
            "label": resp_label,
            "tags": [TAG_SKILL_STICKER],
            "maps_to": "skill.responsible",
        }
    )
    idx += 1
    for lv_key, lv_label in leaf_specs_for_synthetic_ui(ui):
        mcs.append(
            {
                "col": index_to_excel_column(idx),
                "header": f"{lv_label} ({TAG_LEAF_VIEW})",
                "label": lv_label,
                "tags": [TAG_LEAF_VIEW],
                "leaf_view_key": lv_key,
            }
        )
        idx += 1
    return mcs


def effective_matrix_column_schema(ui_config: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Итоговая схема колонок unified (импорт, шаблон, экспорт, витрина): сначала matrix_column_schema из ui,
    иначе синтетика из matrix_levels.

    Порядок колонок при наличии matrix_column_schema — **как в сохранённом списке** (как в загруженном
    файле слева направо). Повторная сортировка по букве колонки не выполняется, чтобы шаблон и экспорт
    были 1:1 с метаданными импорта.
    """
    raw = (ui_config or {}).get("matrix_column_schema")
    if isinstance(raw, list) and raw:
        return [
            coalesce_schema_entry_labels(e, ui_config)
            for e in raw
            if isinstance(e, dict)
        ]
    return build_synthetic_matrix_column_schema(ui_config)


def level_schema_for_depth(ui_config: Optional[Dict[str, Any]], depth: int) -> Dict[str, Any]:
    for row in merge_matrix_levels(ui_config):
        if int(row.get("depth", -1)) == depth:
            return row
    return {"depth": depth, "tags": [TAG_ITEM]}


def level_display_name_for_depth(ui_config: Optional[Dict[str, Any]], depth: int) -> str:
    """Подпись уровня для UI (дерево матрицы, графы): схема колонок → matrix_levels → item_{n}."""
    return item_column_fallback_label(ui_config, depth)


def annotate_matrix_tree(nodes: List[Dict[str, Any]], ui_config: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Рекурсивно добавляет level_schema, level_name (заголовок уровня), level_depth для UI.
    Не мутирует исходное дерево.
    """

    def walk(items: List[Dict[str, Any]], depth: int) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        schema = level_schema_for_depth(ui_config, depth)
        title = level_display_name_for_depth(ui_config, depth) or (schema.get("title") or "")
        for n in items:
            if not isinstance(n, dict):
                continue
            node = dict(n)
            node["level_depth"] = depth
            node["level_schema"] = schema
            if title:
                node["level_name"] = title
            ch = node.get("children")
            if isinstance(ch, list) and ch:
                node["children"] = walk(ch, depth + 1)
            out.append(node)
        return out

    return walk(copy.deepcopy(nodes), 0)


def normalize_level_tags(value: Any) -> List[str]:
    """Приводит level_tags / level_tag к отсортированному списку допустимых грейдов."""
    raw: List[str] = []
    if value is None:
        raw = []
    elif isinstance(value, list):
        raw = [str(x).strip().lower() for x in value if str(x).strip()]
    else:
        text = str(value).strip().lower()
        if not text:
            raw = []
        elif any(sep in text for sep in ",;|"):
            raw = [p.strip() for p in re.split(r"[,;|]", text) if p.strip()]
        else:
            raw = [text]
    seen = set()
    out: List[str] = []
    for t in raw:
        if t in STICKER_GRADES and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def action_level_tags_for_json(action: Dict[str, Any]) -> List[str]:
    """Читает level_tags с фолбэком на level_tag."""
    if not isinstance(action, dict):
        return []
    lt = action.get("level_tags")
    if isinstance(lt, list) and lt:
        return normalize_level_tags(lt)
    if action.get("level_tag"):
        return normalize_level_tags(action.get("level_tag"))
    return []


def subaction_level_tags_for_json(sub: Dict[str, Any]) -> List[str]:
    if not isinstance(sub, dict):
        return []
    lt = sub.get("level_tags")
    if isinstance(lt, list) and lt:
        return normalize_level_tags(lt)
    if sub.get("level_tag"):
        return normalize_level_tags(sub.get("level_tag"))
    return []
