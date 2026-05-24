# -*- coding: utf-8 -*-
"""
Инкрементальное обогащение матрицы: загрузка должна соответствовать текущей
column schema (маркеры node_i / leaf / label) и глубине дерева; совпадающие
навыки обогащаются, новые — добавляются в существующую иерархию.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from .column_markers import marker_table_header, parse_column_marker
from .matrix_schema import effective_matrix_column_schema, merge_matrix_levels
from .schema import ValidationResult
from .skill_node_payload import merge_skill_fields


def _schema_marker_headers(ui_config: Optional[Dict[str, Any]]) -> List[str]:
    schema = effective_matrix_column_schema(ui_config or {})
    out: List[str] = []
    for ent in schema:
        if not isinstance(ent, dict):
            continue
        h = marker_table_header(ent) or str(ent.get("header") or "").strip()
        if h:
            out.append(h.lower())
    return out


def _tree_depth_from_nodes(nodes: List[Dict[str, Any]]) -> int:
    """Число уровней иерархии по фактическому дереву nodes (0-based max depth + 1)."""
    if not isinstance(nodes, list) or not nodes:
        return 0

    def walk(ns: List[Dict[str, Any]], depth: int = 0) -> int:
        mx = depth
        for n in ns:
            if not isinstance(n, dict):
                continue
            ch = n.get("children") or []
            if ch:
                mx = max(mx, walk(ch, depth + 1))
            else:
                mx = max(mx, depth)
        return mx

    return walk(nodes) + 1


def _tree_depth_from_markers(ui_config: Optional[Dict[str, Any]]) -> int:
    """Глубина по node_i маркерам в matrix_column_schema."""
    schema = effective_matrix_column_schema(ui_config or {})
    node_indices: List[int] = []
    for ent in schema:
        if not isinstance(ent, dict):
            continue
        h = marker_table_header(ent) or str(ent.get("header") or "").strip()
        mk = parse_column_marker(h)
        if mk and mk.kind == "node":
            node_indices.append(int(mk.node_index))
    return max(node_indices) if node_indices else 0


def _tree_depth(ui_config: Optional[Dict[str, Any]], nodes: Optional[List[Dict[str, Any]]] = None) -> int:
    """Эффективная глубина: ui_config (matrix_levels / schema) + фактическое дерево + маркеры."""
    depths: List[int] = []
    levels = merge_matrix_levels(ui_config or {})
    if levels:
        depths.append(len(levels))
    raw_levels = (ui_config or {}).get("matrix_levels")
    if isinstance(raw_levels, list) and raw_levels:
        depths.append(len(raw_levels))
    schema = effective_matrix_column_schema(ui_config or {})
    item_depths = [
        int(e.get("item_depth")) + 1
        for e in schema
        if isinstance(e, dict) and e.get("item_depth") is not None
    ]
    if item_depths:
        depths.append(max(item_depths))
    marker_depth = _tree_depth_from_markers(ui_config)
    if marker_depth:
        depths.append(marker_depth)
    node_depth = _tree_depth_from_nodes(nodes or [])
    if node_depth:
        depths.append(node_depth)
    return max(depths) if depths else 0


def validate_incremental_structure(
    current: Dict[str, Any],
    upload: Dict[str, Any],
) -> ValidationResult:
    """Проверяет, что инкремент совместим с уже загруженной матрицей."""
    result = ValidationResult(ok=True)
    cur = current or {}
    up = upload or {}
    cur_nodes = cur.get("nodes") or []
    up_nodes = up.get("nodes") or []

    if not isinstance(cur_nodes, list) or not cur_nodes:
        result.ok = False
        result.errors.append(
            "Инкремент недоступен: в БД нет матрицы. Используйте «Полная замена» для первичной загрузки."
        )
        return result
    if not isinstance(up_nodes, list) or not up_nodes:
        result.ok = False
        result.errors.append("Файл не содержит строк матрицы для инкремента.")
        return result

    cur_ui = cur.get("ui_config") if isinstance(cur.get("ui_config"), dict) else {}
    up_ui = up.get("ui_config") if isinstance(up.get("ui_config"), dict) else {}

    cur_markers = _schema_marker_headers(cur_ui)
    up_markers = _schema_marker_headers(up_ui)
    if cur_markers and up_markers and cur_markers != up_markers:
        result.ok = False
        result.errors.append(
            "Схема колонок инкремента не совпадает с матрицей в БД "
            f"(ожидалось {len(cur_markers)} колонок, в файле {len(up_markers)})."
        )
    elif cur_markers and not up_markers:
        result.warnings.append(
            "В загрузке нет ui_config/matrix_column_schema; сравнение колонок по умолчанию."
        )

    cur_depth = _tree_depth(cur_ui, cur_nodes)
    up_depth = _tree_depth(up_ui, up_nodes)
    if cur_depth and up_depth and cur_depth != up_depth:
        result.ok = False
        result.errors.append(
            f"Глубина дерева не совпадает: в БД {cur_depth} уровней, в файле {up_depth}."
        )

    result.recommendations.append(
        "Инкремент: существующие навыки обогащаются по пути Домен→Раздел→Навык; новые навыки добавляются."
    )
    return result


def _find_child(children: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    nm = (name or "").strip()
    for ch in children or []:
        if isinstance(ch, dict) and (ch.get("name") or "").strip() == nm:
            return ch
    return None


def _ensure_child(children: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
    nm = (name or "").strip()
    found = _find_child(children, nm)
    if found is not None:
        return found
    node: Dict[str, Any] = {"name": nm, "children": []}
    children.append(node)
    return node


def _collect_leaf_chains(
    nodes: List[Dict[str, Any]],
    prefix: Optional[List[Dict[str, Any]]] = None,
) -> List[List[Dict[str, Any]]]:
    prefix = prefix or []
    out: List[List[Dict[str, Any]]] = []
    for n in nodes or []:
        if not isinstance(n, dict):
            continue
        chain = prefix + [n]
        ch = n.get("children") or []
        if ch:
            out.extend(_collect_leaf_chains(ch, chain))
        else:
            out.append(chain)
    return out


def merge_incremental_nodes(
    existing_nodes: List[Dict[str, Any]],
    incoming_nodes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Обогащает existing_nodes содержимым incoming по пути иерархии."""
    out = deepcopy(existing_nodes if isinstance(existing_nodes, list) else [])

    for chain in _collect_leaf_chains(incoming_nodes or []):
        if not chain:
            continue
        names = [(n.get("name") or "").strip() for n in chain]
        names = [n for n in names if n]
        if not names:
            continue
        leaf_src = chain[-1]
        cur_list = out
        target: Optional[Dict[str, Any]] = None
        for i, nm in enumerate(names):
            if i < len(names) - 1:
                target = _ensure_child(cur_list, nm)
                cur_list = target.setdefault("children", [])
            else:
                target = _find_child(cur_list, nm)
                if target is None:
                    target = deepcopy(leaf_src)
                    if "children" not in target:
                        target["children"] = []
                    cur_list.append(target)
                else:
                    merge_skill_fields(target, leaf_src)
    return out


def merge_incremental_into_source(
    current: Dict[str, Any],
    upload: Dict[str, Any],
) -> Tuple[Dict[str, Any], ValidationResult]:
    from .loaders import META_KEYS, _empty_unified, _normalize_unified
    from .schema import SCHEMA_VERSION

    current = _normalize_unified(current) if current else _empty_unified()
    upload = _normalize_unified(upload) if upload else _empty_unified()
    vr = validate_incremental_structure(current, upload)
    if not vr.ok:
        return current, vr

    out = deepcopy(current)
    out["schema_version"] = SCHEMA_VERSION
    out["nodes"] = merge_incremental_nodes(out.get("nodes") or [], upload.get("nodes") or [])

    up_ui = upload.get("ui_config")
    if isinstance(up_ui, dict) and up_ui.get("matrix_column_schema"):
        cur_ui = out.get("ui_config") if isinstance(out.get("ui_config"), dict) else {}
        merged_ui = {**cur_ui}
        for key in ("matrix_column_schema", "matrix_levels", "column_marker_format"):
            if key in up_ui and up_ui[key] is not None:
                merged_ui[key] = deepcopy(up_ui[key])
        out["ui_config"] = merged_ui

    for key in META_KEYS:
        if key in ("ui_config",):
            continue
        uv = upload.get(key)
        if uv is None:
            continue
        default: Any = [] if key == "action_examples" else {}
        if isinstance(uv, dict):
            out[key] = {**(out.get(key) or default), **uv}
        elif isinstance(uv, list):
            out[key] = list(out.get(key) or []) + list(uv)

    return out, vr
