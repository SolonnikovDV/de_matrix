# -*- coding: utf-8 -*-
"""
Экспорт матрицы в строки unified relational.
Порядок колонок = effective_matrix_column_schema (как в matrix_column_schema после импорта, слева направо).
Шапка с тегами = matrix_roundtrip_header_cell (исходная ячейка header из файла).
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional, Tuple

from .column_markers import marker_table_header
from .excel_unified_relational import _item_action_sub_indices
from .matrix_schema import (
    TAG_ITEM,
    TAG_LEAF_VIEW,
    TAG_SKILL_STICKER,
    effective_matrix_column_schema,
    matrix_preview_column_caption,
    matrix_roundtrip_header_cell,
)

def _schema_uses_exls_maps(schema: List[Dict[str, Any]]) -> bool:
    for ent in schema:
        mt = str(ent.get("maps_to") or "").strip()
        if mt.startswith("skill.") or mt.startswith("skill_sections."):
            return True
    return False


def _resolve_maps_to_value(maps_to: str, domain: Dict[str, Any], skill: Dict[str, Any]) -> Any:
    mt = str(maps_to or "").strip()
    if not mt:
        return None
    if mt == "skill.section":
        return skill.get("section")
    if mt == "skill.status":
        return skill.get("status")
    if mt == "skill.author":
        return skill.get("author") or skill.get("responsible")
    if mt == "skill.reviewer":
        return skill.get("reviewer")
    if mt == "skill_sections.optional_for_level":
        sections = skill.get("skill_sections") if isinstance(skill.get("skill_sections"), dict) else {}
        q = sections.get("questions") if isinstance(sections.get("questions"), dict) else {}
        t = sections.get("tasks") if isinstance(sections.get("tasks"), dict) else {}
        return q.get("optional_for_level") or t.get("optional_for_level")
    if mt.startswith("skill_sections."):
        cur: Any = skill
        for part in mt.split("."):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(part)
        return cur
    return None


def _serialize_cell(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return ""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        if isinstance(val, float) and val.is_integer():
            return str(int(val))
        return str(val)
    if isinstance(val, list):
        if not val:
            return ""
        if all(isinstance(x, str) for x in val):
            return "\n".join(str(x).strip() for x in val if str(x).strip())
        parts = []
        for x in val:
            if isinstance(x, str):
                parts.append(x.strip())
            else:
                parts.append(json.dumps(x, ensure_ascii=False))
        return "\n".join(p for p in parts if p)
    if isinstance(val, dict):
        return json.dumps(val, ensure_ascii=False)
    return str(val)


def _fill_item_path(
    ni: int,
    idx_action: int,
    idx_sub: Optional[int],
    domain_name: str,
    skill_name: str,
    action: Dict[str, Any],
    sub: Optional[Dict[str, Any]],
) -> List[str]:
    path = [""] * ni
    path[0] = (domain_name or "").strip()
    path[1] = (skill_name or "").strip()
    pk = str(action.get("excel_path_key") or "").strip()
    segs = [s.strip() for s in pk.split("\x1f") if s.strip()] if pk else []
    middle_slots = max(0, idx_action - 1)
    if middle_slots:
        if len(segs) >= middle_slots:
            for i in range(middle_slots):
                path[2 + i] = segs[i]
        else:
            for i in range(len(segs)):
                path[2 + i] = segs[i]
            path[idx_action] = (action.get("text") or "").strip()
    else:
        path[idx_action] = (action.get("text") or "").strip()
    if idx_sub is not None:
        path[idx_sub] = ((sub or {}).get("text") or "").strip()
    return path


def _collect_leaf_chains_from_nodes(nodes: List[Any], prefix: Optional[List[Dict[str, Any]]] = None) -> List[List[Dict[str, Any]]]:
    """Все цепочки от корня до листа в generic-дереве { name, children }."""
    prefix = prefix or []
    out: List[List[Dict[str, Any]]] = []
    for n in nodes or []:
        if not isinstance(n, dict):
            continue
        cur = prefix + [n]
        ch = n.get("children") or []
        if not ch:
            out.append(cur)
        else:
            out.extend(_collect_leaf_chains_from_nodes(ch, cur))
    return out


def _one_row_from_exls_chain(
    chain: List[Dict[str, Any]],
    schema: List[Dict[str, Any]],
    item_entries: List[Dict[str, Any]],
    col_index_for_entry,
    *,
    emit_domain: bool,
    emit_section: bool,
) -> List[str]:
    domain = chain[0] if chain else {}
    skill = chain[-1] if chain else {}
    row = [""] * len(schema)
    names = [(x.get("name") or x.get("text") or "").strip() for x in chain]
    ni = len(item_entries)
    section_on_skill = ni <= 2 and bool(str(skill.get("section") or "").strip())
    for j, ent in enumerate(item_entries):
        ci = col_index_for_entry(ent)
        if ci < 0:
            continue
        depth = int(ent.get("item_depth", j))
        if depth == 0:
            row[ci] = names[0] if emit_domain and names else ""
        elif depth == 1:
            if ni >= 3 and len(names) > 1:
                row[ci] = names[1] if emit_section else ""
            elif section_on_skill:
                row[ci] = str(skill.get("section") or "").strip() if emit_section else ""
            else:
                row[ci] = names[-1] if names else ""
        elif depth >= 2:
            row[ci] = names[-1] if names else ""
    for ent in schema:
        ci = col_index_for_entry(ent)
        if ci < 0:
            continue
        mt = str(ent.get("maps_to") or "").strip()
        if mt == "skill.section":
            row[ci] = str(skill.get("section") or "").strip() if emit_section else ""
            continue
        val = _resolve_maps_to_value(mt, domain, skill)
        if val is not None and str(val).strip():
            row[ci] = _serialize_cell(val)
        tags = [str(t).lower() for t in (ent.get("tags") or [])]
        if TAG_LEAF_VIEW in tags and not mt:
            key = str(ent.get("leaf_view_key") or "").strip()
            lv = skill.get("leaf_view") if isinstance(skill.get("leaf_view"), dict) else {}
            if key and key in lv:
                row[ci] = _serialize_cell(lv.get(key))
    return row


def _one_row_from_node_chain(
    chain: List[Dict[str, Any]],
    schema: List[Dict[str, Any]],
    item_entries: List[Dict[str, Any]],
    ni: int,
    col_index_for_entry,
) -> List[str]:
    """Строка unified: сегменты пути по item-колонкам 0..ni-1, leaf_view с листа, responsible с узла глубины 1."""
    names = [(x.get("name") or x.get("text") or "").strip() for x in chain]
    resp = ""
    if len(chain) > 1:
        resp = str(chain[1].get("responsible") or "").strip()
    leaf = chain[-1]
    lv = leaf.get("leaf_view") if isinstance(leaf.get("leaf_view"), dict) else {}
    path_slots = [""] * ni
    for j in range(min(ni, len(names))):
        path_slots[j] = names[j]
    row = [""] * len(schema)
    for j, ent in enumerate(item_entries):
        ci = col_index_for_entry(ent)
        if ci >= 0 and j < len(path_slots):
            row[ci] = path_slots[j]
    for ent in schema:
        tags = [str(t).lower() for t in (ent.get("tags") or [])]
        ci = col_index_for_entry(ent)
        if ci < 0:
            continue
        if TAG_SKILL_STICKER in tags:
            row[ci] = resp
        elif TAG_LEAF_VIEW in tags:
            key = str(ent.get("leaf_view_key") or "").strip()
            if key and isinstance(lv, dict) and key in lv:
                row[ci] = _serialize_cell(lv.get(key))
    return row


def build_unified_export_table(
    domains: List[Dict[str, Any]],
    ui_config: Optional[Dict[str, Any]],
    *,
    nodes: Optional[List[Dict[str, Any]]] = None,
    include_header_tags: bool = True,
) -> Tuple[List[str], List[List[str]]]:
    """
    Строки — по одной на каждый лист (поддействие или действие без поддействий).
    Заголовки: include_header_tags=True — ячейки строки 1 как в импорте (matrix_roundtrip_header_cell).
    False — подпись до скобок с тегами из той же шапки (matrix_preview_column_caption).

    Если передан непустой ``nodes`` (generic-дерево), обход листьев идёт по нему; иначе — по ``domains`` (legacy).
    """
    schema = effective_matrix_column_schema(ui_config)
    use_markers = bool((ui_config or {}).get("column_marker_format"))
    if include_header_tags:
        headers = [matrix_roundtrip_header_cell(e, ui_config) for e in schema]
    elif use_markers:
        headers = [marker_table_header(e) for e in schema]
    else:
        headers = [matrix_preview_column_caption(e, ui_config) for e in schema]
    item_entries = [e for e in schema if TAG_ITEM in [str(t).lower() for t in (e.get("tags") or [])]]
    ni = len(item_entries)
    if ni < 2:
        return headers, []

    col_to_schema_index = {str(e.get("col") or "").upper(): i for i, e in enumerate(schema)}

    def col_index_for_entry(ent: Dict[str, Any]) -> int:
        c = str(ent.get("col") or "").upper()
        return col_to_schema_index.get(c, -1)

    rows_out: List[List[str]] = []

    if nodes:
        use_exls = _schema_uses_exls_maps(schema)
        prev_domain = ""
        prev_section = ""
        item_count = len(item_entries)
        for chain in _collect_leaf_chains_from_nodes(nodes, []):
            if use_exls:
                domain_name = (chain[0].get("name") or "").strip() if chain else ""
                skill = chain[-1] if chain else {}
                if item_count >= 3 and len(chain) >= 3:
                    sec_name = (chain[1].get("name") or "").strip()
                else:
                    sec_name = str(skill.get("section") or "").strip()
                emit_domain = domain_name != prev_domain
                emit_section = sec_name != prev_section or emit_domain
                rows_out.append(
                    _one_row_from_exls_chain(
                        chain,
                        schema,
                        item_entries,
                        col_index_for_entry,
                        emit_domain=emit_domain,
                        emit_section=emit_section,
                    )
                )
                prev_domain = domain_name
                prev_section = sec_name
            else:
                rows_out.append(
                    _one_row_from_node_chain(chain, schema, item_entries, ni, col_index_for_entry)
                )
        return headers, rows_out

    if ni < 3:
        return headers, []

    idx_action, idx_sub = _item_action_sub_indices(ni)
    for d in domains or []:
        if not isinstance(d, dict):
            continue
        d_name = str(d.get("name") or "").strip()
        for s in d.get("skills") or []:
            if not isinstance(s, dict):
                continue
            s_name = str(s.get("name") or "").strip()
            resp = str(s.get("responsible") or "").strip()
            for a in s.get("actions") or []:
                if not isinstance(a, dict):
                    continue
                subs = a.get("subactions") or []
                if isinstance(subs, list) and subs:
                    for sub in subs:
                        if not isinstance(sub, dict):
                            continue
                        row_cells = _one_row(
                            schema,
                            item_entries,
                            ni,
                            idx_action,
                            idx_sub,
                            d_name,
                            s_name,
                            resp,
                            a,
                            sub,
                            col_index_for_entry,
                        )
                        rows_out.append(row_cells)
                else:
                    row_cells = _one_row(
                        schema,
                        item_entries,
                        ni,
                        idx_action,
                        idx_sub,
                        d_name,
                        s_name,
                        resp,
                        a,
                        None,
                        col_index_for_entry,
                    )
                    rows_out.append(row_cells)

    return headers, rows_out


def _one_row(
    schema: List[Dict[str, Any]],
    item_entries: List[Dict[str, Any]],
    ni: int,
    idx_action: int,
    idx_sub: Optional[int],
    d_name: str,
    s_name: str,
    resp: str,
    action: Dict[str, Any],
    sub: Optional[Dict[str, Any]],
    col_index_for_entry,
) -> List[str]:
    path = _fill_item_path(ni, idx_action, idx_sub, d_name, s_name, action, sub)
    target = sub if sub is not None else action
    lv = target.get("leaf_view") if isinstance(target.get("leaf_view"), dict) else {}

    row = [""] * len(schema)
    for j, ent in enumerate(item_entries):
        ci = col_index_for_entry(ent)
        if ci >= 0 and j < len(path):
            row[ci] = path[j]
    for ent in schema:
        tags = [str(t).lower() for t in (ent.get("tags") or [])]
        ci = col_index_for_entry(ent)
        if ci < 0:
            continue
        if TAG_SKILL_STICKER in tags:
            row[ci] = resp
        elif TAG_LEAF_VIEW in tags:
            key = str(ent.get("leaf_view_key") or "").strip()
            if key and isinstance(lv, dict) and key in lv:
                row[ci] = _serialize_cell(lv.get(key))
    return row
