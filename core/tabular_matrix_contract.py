# -*- coding: utf-8 -*-
"""
Контракт табличной матрицы exls_matrix (CSV / XLSX / JSON list-of-records).

Дерево: Домен (L0) → Навык (L1, лист).
Раздел — свойство навыка (section), не отдельный уровень дерева.

Содержимое навыка:
- status, author, reviewer — свойства навыка
- skill_sections.questions — раздел «Вопросы» (+ materials, optional_for_level)
- skill_sections.tasks — раздел «Задачи» (+ optional_for_level)
- skill_sections.reviewer_questions — раздел «Вопросы ревьюера»
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

from .matrix_schema import (
    TAG_ITEM,
    TAG_LEAF_VIEW,
    TAG_SKILL_STICKER,
    index_to_excel_column,
    normalize_responsible_value,
)
from .column_markers import (
    DEFAULT_LABEL_SEMANTICS,
    DEFAULT_LEAF_SEMANTICS,
    build_marker_ui_config,
    detect_marker_tabular_columns,
    matches_marker_tabular_columns,
    parse_column_marker,
)

# --- Имена колонок (рус / en) ---

COL_DOMAIN = ("Домен", "Domain", "domain")
COL_SECTION = ("Раздел", "Section", "section")
COL_SKILL = ("Навык", "Skill", "skill", "Competency", "competency")
COL_STATUS = ("Статус", "Status", "status")
COL_QUESTIONS = ("Вопросы", "Questions", "questions")
COL_MATERIALS = ("Материалы", "Materials", "materials")
COL_TASKS = ("Задачи", "Tasks", "tasks")
COL_OPTIONAL = ("Опционально для уровня", "Опционально", "Optional", "optional")
COL_REVIEWER_Q = ("Вопросы ревьюера", "Reviewer Questions", "reviewer_questions")
COL_AUTHOR = ("Автор", "Author", "author")
COL_REVIEWER = ("Ревьюер", "Reviewer", "reviewer")

EXLS_MATRIX_LEVELS: List[Dict[str, Any]] = [
    {"depth": 0, "title": "Домен", "tags": [TAG_ITEM]},
    {"depth": 1, "title": "Навык", "tags": [TAG_ITEM, TAG_SKILL_STICKER], "skill_responsible": True},
]


def _norm(name: str) -> str:
    return str(name or "").strip().casefold()


def _pick(columns: List[str], candidates: Tuple[str, ...]) -> Optional[str]:
    cand = {_norm(c) for c in candidates}
    for col in columns:
        if _norm(col) in cand:
            return col
    return None


def detect_exls_tabular_columns(columns: List[str]) -> Optional[Dict[str, Optional[str]]]:
    """True если таблица соответствует контракту exls (есть Домен и Навык)."""
    domain = _pick(columns, COL_DOMAIN)
    skill = _pick(columns, COL_SKILL)
    if not domain or not skill:
        return None
    return {
        "domain": domain,
        "section": _pick(columns, COL_SECTION),
        "skill": skill,
        "status": _pick(columns, COL_STATUS),
        "questions": _pick(columns, COL_QUESTIONS),
        "materials": _pick(columns, COL_MATERIALS),
        "tasks": _pick(columns, COL_TASKS),
        "optional": _pick(columns, COL_OPTIONAL),
        "reviewer_questions": _pick(columns, COL_REVIEWER_Q),
        "author": _pick(columns, COL_AUTHOR),
        "reviewer": _pick(columns, COL_REVIEWER),
    }


def matches_exls_tabular_columns(columns: List[str]) -> bool:
    if matches_marker_tabular_columns(columns):
        return True
    return detect_exls_tabular_columns(columns) is not None


def build_exls_matrix_column_schema(columns: List[str]) -> List[Dict[str, Any]]:
    """matrix_column_schema для ui_config после импорта exls-таблицы."""
    cols = detect_exls_tabular_columns(columns)
    if not cols:
        return []
    ordered: List[Tuple[str, str, List[str], Optional[int], Optional[str]]] = [
        ("domain", "Домен", [TAG_ITEM], 0, None),
        ("section", "Раздел", [TAG_SKILL_STICKER], None, "skill.section"),
        ("skill", "Навык", [TAG_ITEM], 1, None),
        ("status", "Статус", [TAG_LEAF_VIEW], None, "skill.status"),
        ("questions", "Вопросы", [TAG_LEAF_VIEW], None, "skill_sections.questions.body"),
        ("materials", "Материалы", [TAG_LEAF_VIEW], None, "skill_sections.questions.materials"),
        ("tasks", "Задачи", [TAG_LEAF_VIEW], None, "skill_sections.tasks.body"),
        ("optional", "Опционально для уровня", [TAG_LEAF_VIEW], None, "skill_sections.optional_for_level"),
        ("reviewer_questions", "Вопросы ревьюера", [TAG_LEAF_VIEW], None, "skill_sections.reviewer_questions.body"),
        ("author", "Автор", [TAG_SKILL_STICKER], None, "skill.author"),
        ("reviewer", "Ревьюер", [TAG_LEAF_VIEW], None, "skill.reviewer"),
    ]
    mcs: List[Dict[str, Any]] = []
    idx = 0
    for key, default_label, tags, item_depth, maps_to in ordered:
        col_name = cols.get(key)
        if not col_name:
            continue
        ent: Dict[str, Any] = {
            "col": index_to_excel_column(idx),
            "header": col_name,
            "label": str(col_name).strip() or default_label,
            "tags": list(tags),
        }
        if item_depth is not None:
            ent["item_depth"] = item_depth
        if maps_to:
            ent["maps_to"] = maps_to
        if TAG_LEAF_VIEW in tags and maps_to:
            ent["leaf_view_key"] = maps_to.split(".")[-1]
        mcs.append(ent)
        idx += 1
    return mcs


def build_exls_ui_config(columns: List[str]) -> Dict[str, Any]:
    mcs = build_exls_matrix_column_schema(columns)
    if not mcs:
        return {}
    return {
        "matrix_levels": copy.deepcopy(EXLS_MATRIX_LEVELS),
        "matrix_column_schema": mcs,
        "constructor_extra_leaf_steps": 0,
    }


def _merge_text(existing: str, incoming: str) -> str:
    left = str(existing or "").strip()
    right = str(incoming or "").strip()
    if not right:
        return left
    if not left:
        return right
    if right in left:
        return left
    return f"{left}\n{right}"


def _set_skill_section_field(
    node: Dict[str, Any],
    section_key: str,
    field: str,
    value: str,
) -> None:
    if not value:
        return
    sections = node.setdefault("skill_sections", {})
    if not isinstance(sections, dict):
        sections = {}
        node["skill_sections"] = sections
    sec = sections.setdefault(section_key, {})
    if not isinstance(sec, dict):
        sec = {}
        sections[section_key] = sec
    prev = sec.get(field)
    if isinstance(prev, str):
        sec[field] = _merge_text(prev, value)
    elif not prev:
        sec[field] = value


def attach_exls_row_to_skill_node(
    node: Dict[str, Any],
    row: Dict[str, Any],
    cols: Dict[str, Optional[str]],
    *,
    cell_str,
) -> None:
    """Заполняет свойства навыка и разделы из строки таблицы."""
    status_col = cols.get("status")
    if status_col:
        v = cell_str(row.get(status_col))
        if v and not node.get("status"):
            node["status"] = v

    author_col = cols.get("author")
    if author_col:
        v = normalize_responsible_value(cell_str(row.get(author_col)))
        if v:
            if not node.get("author"):
                node["author"] = v
            if not node.get("responsible"):
                node["responsible"] = v

    reviewer_col = cols.get("reviewer")
    if reviewer_col:
        v = normalize_responsible_value(cell_str(row.get(reviewer_col)))
        if v and not node.get("reviewer"):
            node["reviewer"] = v

    q_col = cols.get("questions")
    if q_col:
        _set_skill_section_field(node, "questions", "body", cell_str(row.get(q_col)))

    m_col = cols.get("materials")
    if m_col:
        _set_skill_section_field(node, "questions", "materials", cell_str(row.get(m_col)))

    t_col = cols.get("tasks")
    if t_col:
        _set_skill_section_field(node, "tasks", "body", cell_str(row.get(t_col)))

    o_col = cols.get("optional")
    if o_col:
        opt = cell_str(row.get(o_col))
        if opt:
            _set_skill_section_field(node, "questions", "optional_for_level", opt)
            _set_skill_section_field(node, "tasks", "optional_for_level", opt)

    rq_col = cols.get("reviewer_questions")
    if rq_col:
        _set_skill_section_field(node, "reviewer_questions", "body", cell_str(row.get(rq_col)))


def _apply_label_maps_to(node: Dict[str, Any], maps_to: str, value: str) -> None:
    if not value:
        return
    if maps_to == "skill.author":
        if not node.get("author"):
            node["author"] = value
        if not node.get("responsible"):
            node["responsible"] = value
    elif maps_to == "skill.reviewer":
        if not node.get("reviewer"):
            node["reviewer"] = value
    elif maps_to == "skill.status":
        if not node.get("status"):
            node["status"] = value
    elif maps_to == "skill_sections.optional_for_level":
        _set_skill_section_field(node, "questions", "optional_for_level", value)
        _set_skill_section_field(node, "tasks", "optional_for_level", value)


def _apply_leaf_maps_to(node: Dict[str, Any], maps_to: str, value: str) -> None:
    if not value or not maps_to.startswith("skill_sections."):
        return
    parts = maps_to.split(".")
    if len(parts) == 3:
        _, sec_key, field = parts
        _set_skill_section_field(node, sec_key, field, value)


def attach_marker_row_to_leaf_node(
    node: Dict[str, Any],
    row: Dict[str, Any],
    columns: List[str],
    *,
    cell_str,
) -> None:
    """Заполняет leaf/label-свойства целевого узла из строки по маркерам колонок."""
    for col in columns:
        mk = parse_column_marker(col)
        if not mk or mk.kind == "node":
            continue
        val = cell_str(row.get(col))
        if not val:
            continue
        if mk.kind == "label":
            sem = DEFAULT_LABEL_SEMANTICS.get(mk.slot_index)
            if sem:
                v = normalize_responsible_value(val) if mk.slot_index in (1, 2) else val
                _apply_label_maps_to(node, sem[0], v)
        elif mk.kind == "leaf":
            sem = DEFAULT_LEAF_SEMANTICS.get(mk.slot_index)
            if sem:
                _apply_leaf_maps_to(node, sem[0], val)


def marker_tabular_rows_to_nodes(
    rows: List[Dict[str, Any]],
    columns: List[str],
    *,
    cell_str,
    strip_transient,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    CSV/XLSX/JSON table → nodes по маркерам node_i / leaf_j_node_i / label_k_node_i.
    Иерархия: node_1 → node_2 → … → node_N (лист дерева).
    """
    layout = detect_marker_tabular_columns(columns)
    if not layout:
        return [], {}

    max_node = int(layout["max_node"])
    node_cols: List[Tuple[int, str]] = []
    for col in columns:
        mk = parse_column_marker(col)
        if mk and mk.kind == "node":
            node_cols.append((mk.node_index, col))
    node_cols.sort(key=lambda x: x[0])
    depth_by_node_index = {idx: pos for pos, (idx, _col) in enumerate(node_cols)}
    tree_depth = len(node_cols)

    carry = [""] * tree_depth
    root: Dict[str, Dict[str, Any]] = {}
    order = 0

    for row in rows:
        for node_idx, col in node_cols:
            pos = depth_by_node_index[node_idx]
            raw = cell_str(row.get(col))
            if raw:
                carry[pos] = raw
                for j in range(pos + 1, tree_depth):
                    carry[j] = ""

        path = [carry[i].strip() for i in range(tree_depth)]
        if not path[-1]:
            continue
        if not path[0]:
            path[0] = "Общее"

        slot: Dict[str, Dict[str, Any]] = root
        for depth, name in enumerate(path):
            if not name:
                break
            if name not in slot:
                slot[name] = {"__order__": order, "__children__": {}}
                order += 1
            leaf_slot = slot[name]
            if depth < tree_depth - 1:
                ch = leaf_slot.setdefault("__children__", {})
                if not isinstance(ch, dict):
                    ch = {}
                    leaf_slot["__children__"] = ch
                slot = ch
            else:
                attach_marker_row_to_leaf_node(leaf_slot, row, columns, cell_str=cell_str)

    def to_nodes(tree: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for name in sorted(tree.keys(), key=lambda k: tree[k].get("__order__", 0)):
            slot = tree[name]
            ch_tree = slot.get("__children__") or {}
            children = to_nodes(ch_tree) if isinstance(ch_tree, dict) else []
            node: Dict[str, Any] = {"name": name, "children": children}
            for key in (
                "status",
                "author",
                "reviewer",
                "responsible",
                "skill_sections",
            ):
                if slot.get(key) is not None:
                    node[key] = copy.deepcopy(slot[key])
            out.append(node)
        return out

    nodes = strip_transient(to_nodes(root))
    ui_config = build_marker_ui_config(columns)
    return nodes, ui_config


def exls_tabular_rows_to_nodes(
    rows: List[Dict[str, Any]],
    columns: List[str],
    *,
    cell_str,
    strip_transient,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    CSV/XLSX/JSON table → nodes + ui_config.
    Маркеры node_i имеют приоритет; иначе legacy exls (Домен → Навык, Раздел как свойство).
    """
    if matches_marker_tabular_columns(columns):
        return marker_tabular_rows_to_nodes(
            rows, columns, cell_str=cell_str, strip_transient=strip_transient
        )

    cols = detect_exls_tabular_columns(columns)
    if not cols:
        return [], {}

    domain_col = cols["domain"]
    section_col = cols.get("section")
    skill_col = cols["skill"]

    last_domain = ""
    last_section = ""
    last_skill = ""

    root: Dict[str, Dict[str, Any]] = {}
    order = 0

    for row in rows:
        raw_domain = cell_str(row.get(domain_col)) if domain_col else ""
        raw_section = cell_str(row.get(section_col)) if section_col else ""
        raw_skill = cell_str(row.get(skill_col)) if skill_col else ""

        if raw_domain:
            last_domain = raw_domain
        if section_col and raw_section:
            last_section = raw_section
        if raw_skill:
            last_skill = raw_skill

        domain_name = last_domain
        skill_name = last_skill
        if not skill_name:
            continue
        if not domain_name:
            domain_name = "Общее"

        if domain_name not in root:
            root[domain_name] = {"__order__": order, "__children__": {}}
            order += 1
        domain_slot = root[domain_name]
        children = domain_slot.setdefault("__children__", {})
        if not isinstance(children, dict):
            children = {}
            domain_slot["__children__"] = children

        if skill_name not in children:
            children[skill_name] = {"__order__": order, "__children__": {}}
            order += 1
        skill_slot = children[skill_name]

        if last_section and not skill_slot.get("section"):
            skill_slot["section"] = last_section
        elif section_col and raw_section:
            skill_slot["section"] = raw_section

        attach_exls_row_to_skill_node(skill_slot, row, cols, cell_str=cell_str)

    def to_nodes(tree: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for name in sorted(tree.keys(), key=lambda k: tree[k].get("__order__", 0)):
            slot = tree[name]
            ch_tree = slot.get("__children__") or {}
            children = to_nodes(ch_tree) if isinstance(ch_tree, dict) else []
            node: Dict[str, Any] = {"name": name, "children": children}
            for key in (
                "section",
                "status",
                "author",
                "reviewer",
                "responsible",
                "skill_sections",
            ):
                if slot.get(key) is not None:
                    node[key] = copy.deepcopy(slot[key])
            out.append(node)
        return out

    nodes = strip_transient(to_nodes(root))
    ui_config = build_exls_ui_config(columns)
    return nodes, ui_config


def serialize_exls_row_from_skill(
    domain_name: str,
    skill: Dict[str, Any],
    cols: Dict[str, Optional[str]],
    *,
    emit_domain: bool,
    emit_section: bool,
) -> Dict[str, Optional[str]]:
    """Одна строка экспорта для навыка (sparse null для carry-forward)."""
    row: Dict[str, Optional[str]] = {}
    if cols.get("domain"):
        row[cols["domain"]] = domain_name if emit_domain else None
    if cols.get("section"):
        sec = str(skill.get("section") or "").strip()
        row[cols["section"]] = sec if emit_section else None
    if cols.get("skill"):
        row[cols["skill"]] = str(skill.get("name") or "").strip()

    sections = skill.get("skill_sections") if isinstance(skill.get("skill_sections"), dict) else {}
    q = sections.get("questions") if isinstance(sections.get("questions"), dict) else {}
    t = sections.get("tasks") if isinstance(sections.get("tasks"), dict) else {}
    rq = sections.get("reviewer_questions") if isinstance(sections.get("reviewer_questions"), dict) else {}

    if cols.get("status"):
        row[cols["status"]] = str(skill.get("status") or "").strip() or None
    if cols.get("questions"):
        row[cols["questions"]] = str(q.get("body") or "").strip() or None
    if cols.get("materials"):
        row[cols["materials"]] = str(q.get("materials") or "").strip() or None
    if cols.get("tasks"):
        row[cols["tasks"]] = str(t.get("body") or "").strip() or None
    if cols.get("optional"):
        opt = str(q.get("optional_for_level") or t.get("optional_for_level") or "").strip()
        row[cols["optional"]] = opt or None
    if cols.get("reviewer_questions"):
        row[cols["reviewer_questions"]] = str(rq.get("body") or "").strip() or None
    if cols.get("author"):
        row[cols["author"]] = str(skill.get("author") or skill.get("responsible") or "").strip() or None
    if cols.get("reviewer"):
        row[cols["reviewer"]] = str(skill.get("reviewer") or "").strip() or None
    return row


def exls_nodes_to_tabular_rows(nodes: List[Dict[str, Any]], columns: List[str]) -> List[Dict[str, Optional[str]]]:
    """Экспорт nodes → строки таблицы exls с carry-forward null."""
    cols = detect_exls_tabular_columns(columns)
    if not cols:
        return []

    rows_out: List[Dict[str, Optional[str]]] = []
    prev_domain = ""
    prev_section = ""

    for domain in nodes or []:
        if not isinstance(domain, dict):
            continue
        d_name = str(domain.get("name") or "").strip()
        for skill in domain.get("children") or []:
            if not isinstance(skill, dict):
                continue
            sec = str(skill.get("section") or "").strip()
            emit_domain = d_name != prev_domain
            emit_section = sec != prev_section or emit_domain
            rows_out.append(
                serialize_exls_row_from_skill(
                    d_name,
                    skill,
                    cols,
                    emit_domain=emit_domain,
                    emit_section=emit_section,
                )
            )
            prev_domain = d_name
            prev_section = sec
    return rows_out
