# -*- coding: utf-8 -*-
"""
Маркеры колонок exls_matrix:
- node_i — i-й уровень иерархии (item)
- leaf_j_node_i — j-е leaf-свойство узла уровня i
- label_k_node_i — k-я наклейка узла уровня i
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .matrix_schema import (
    TAG_ITEM,
    TAG_LEAF_VIEW,
    TAG_SKILL_STICKER,
    index_to_excel_column,
)

NODE_RE = re.compile(r"^node_(\d+)$", re.I)
LEAF_RE = re.compile(r"^leaf_(\d+)_node_(\d+)$", re.I)
LABEL_RE = re.compile(r"^label_(\d+)_node_(\d+)$", re.I)

DEFAULT_NODE_TITLES: Dict[int, str] = {
    1: "Домен",
    2: "Раздел",
    3: "Навык",
}

DEFAULT_LEAF_SEMANTICS: Dict[int, Tuple[str, str]] = {
    1: ("skill_sections.questions.body", "Вопросы"),
    2: ("skill_sections.questions.materials", "Материалы"),
    3: ("skill_sections.tasks.body", "Задачи"),
    5: ("skill_sections.reviewer_questions.body", "Вопросы ревьюера"),
}

CANONICAL_MARKER_COLUMNS: List[str] = [
    "node_1",
    "node_2",
    "node_3",
    "label_3_node_3",
    "leaf_1_node_3",
    "leaf_2_node_3",
    "leaf_3_node_3",
    "label_4_node_3",
    "leaf_5_node_3",
    "label_1_node_3",
    "label_2_node_3",
]

DEFAULT_LABEL_SEMANTICS: Dict[int, Tuple[str, str]] = {
    1: ("skill.author", "Автор"),
    2: ("skill.reviewer", "Ревьюер"),
    3: ("skill.status", "Статус"),
    4: ("skill_sections.optional_for_level", "Опционально для уровня"),
}

# Legacy русские заголовки → маркер (обратная совместимость)
LEGACY_HEADER_TO_MARKER: Dict[str, str] = {
    "домен": "node_1",
    "domain": "node_1",
    "раздел": "node_2",
    "section": "node_2",
    "навык": "node_3",
    "skill": "node_3",
    "competency": "node_3",
    "статус": "label_3_node_3",
    "status": "label_3_node_3",
    "вопросы": "leaf_1_node_3",
    "questions": "leaf_1_node_3",
    "материалы": "leaf_2_node_3",
    "materials": "leaf_2_node_3",
    "задачи": "leaf_3_node_3",
    "tasks": "leaf_3_node_3",
    "опционально для уровня": "label_4_node_3",
    "опционально": "label_4_node_3",
    "optional": "label_4_node_3",
    "вопросы ревьюера": "leaf_5_node_3",
    "reviewer questions": "leaf_5_node_3",
    "reviewer_questions": "leaf_5_node_3",
    "автор": "label_1_node_3",
    "author": "label_1_node_3",
    "ревьюер": "label_2_node_3",
    "reviewer": "label_2_node_3",
}


@dataclass(frozen=True)
class ColumnMarker:
    raw: str
    kind: str  # node | leaf | label
    node_index: int
    slot_index: int = 0

    @property
    def marker(self) -> str:
        if self.kind == "node":
            return f"node_{self.node_index}"
        if self.kind == "leaf":
            return f"leaf_{self.slot_index}_node_{self.node_index}"
        return f"label_{self.slot_index}_node_{self.node_index}"


def _norm_header(name: str) -> str:
    return str(name or "").strip().casefold()


MARKER_HEADER_RE = re.compile(
    r"^(node_\d+|leaf_\d+_node_\d+|label_\d+_node_\d+)$",
    re.I,
)


def is_marker_column_header(header: str) -> bool:
    return bool(MARKER_HEADER_RE.match(str(header or "").strip()))


def marker_table_header(entry: Dict[str, Any]) -> str:
    """Заголовок колонки для round-trip таблицы: маркер из header, иначе label."""
    if not isinstance(entry, dict):
        return ""
    raw = str(entry.get("header") or entry.get("marker") or "").strip()
    if raw and is_marker_column_header(raw):
        return raw
    lab = str(entry.get("label") or "").strip()
    return lab or raw


def normalize_header_to_marker(header: str) -> str:
    """Приводит заголовок колонки к каноническому маркеру."""
    raw = str(header or "").strip()
    if not raw:
        return raw
    low = _norm_header(raw)
    if NODE_RE.match(raw) or LEAF_RE.match(raw) or LABEL_RE.match(raw):
        return raw.lower() if raw.isupper() else raw
    mapped = LEGACY_HEADER_TO_MARKER.get(low)
    if mapped:
        return mapped
    # «Домен (item)» и прочие — label до скобки
    base = re.sub(r"\s*\([^)]*\)\s*$", "", raw).strip()
    return LEGACY_HEADER_TO_MARKER.get(_norm_header(base), raw)


def parse_column_marker(header: str) -> Optional[ColumnMarker]:
    canon = normalize_header_to_marker(header)
    m = NODE_RE.match(canon)
    if m:
        return ColumnMarker(raw=canon, kind="node", node_index=int(m.group(1)))
    m = LEAF_RE.match(canon)
    if m:
        return ColumnMarker(
            raw=canon,
            kind="leaf",
            slot_index=int(m.group(1)),
            node_index=int(m.group(2)),
        )
    m = LABEL_RE.match(canon)
    if m:
        return ColumnMarker(
            raw=canon,
            kind="label",
            slot_index=int(m.group(1)),
            node_index=int(m.group(2)),
        )
    return None


def detect_marker_tabular_columns(columns: List[str]) -> Optional[Dict[str, Any]]:
    """
    Разбор таблицы по маркерам. Требуются node_1 и node_3 (или legacy Домен+Навык).
    """
    specs: List[Tuple[str, ColumnMarker]] = []
    for col in columns:
        mk = parse_column_marker(col)
        if mk:
            specs.append((col, mk))
    if not specs:
        return None
    node_indices = sorted({mk.node_index for _, mk in specs if mk.kind == "node"})
    if not node_indices or 1 not in node_indices:
        return None
    max_node = max(node_indices)
    if max_node < 2:
        return None
    leaf_target = max(
        (mk.node_index for _, mk in specs if mk.kind in ("leaf", "label")),
        default=max_node,
    )
    return {
        "columns": columns,
        "specs": specs,
        "node_indices": node_indices,
        "max_node": max_node,
        "leaf_target_node": leaf_target,
        "by_marker": {mk.marker: col for col, mk in specs},
    }


def matches_marker_tabular_columns(columns: List[str]) -> bool:
    return detect_marker_tabular_columns(columns) is not None


def build_marker_matrix_column_schema(columns: List[str]) -> List[Dict[str, Any]]:
    layout = detect_marker_tabular_columns(columns)
    if not layout:
        return []
    max_node = int(layout["max_node"])
    mcs: List[Dict[str, Any]] = []
    idx = 0
    for col in columns:
        mk = parse_column_marker(col)
        if not mk:
            continue
        ent: Dict[str, Any] = {
            "col": index_to_excel_column(idx),
            "header": col,
            "label": col,
            "marker": mk.marker,
            "marker_kind": mk.kind,
            "target_node_index": mk.node_index,
        }
        if mk.kind == "node":
            ent["tags"] = [TAG_ITEM]
            ent["item_depth"] = mk.node_index - 1
            ent["label"] = DEFAULT_NODE_TITLES.get(mk.node_index, mk.marker)
        elif mk.kind == "leaf":
            sem = DEFAULT_LEAF_SEMANTICS.get(mk.slot_index)
            maps_to = sem[0] if sem else f"leaf.{mk.slot_index}.node_{mk.node_index}"
            title = sem[1] if sem else mk.marker
            ent["tags"] = [TAG_LEAF_VIEW]
            ent["maps_to"] = maps_to
            ent["leaf_view_key"] = maps_to.split(".")[-1]
            ent["label"] = title
            ent["leaf_slot"] = mk.slot_index
        else:
            sem = DEFAULT_LABEL_SEMANTICS.get(mk.slot_index)
            maps_to = sem[0] if sem else f"label.{mk.slot_index}.node_{mk.node_index}"
            title = sem[1] if sem else mk.marker
            ent["tags"] = [TAG_SKILL_STICKER]
            ent["maps_to"] = maps_to
            ent["label"] = title
            ent["label_slot"] = mk.slot_index
        mcs.append(ent)
        idx += 1
    return mcs


def build_marker_matrix_levels(max_node: int, node_indices: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    indices = sorted(node_indices or list(range(1, max_node + 1)))
    levels: List[Dict[str, Any]] = []
    for pos, i in enumerate(indices):
        row: Dict[str, Any] = {
            "depth": pos,
            "title": DEFAULT_NODE_TITLES.get(i, f"node_{i}"),
            "slug": f"node_{i}",
            "tags": [TAG_ITEM],
            "node_index": i,
        }
        if pos == len(indices) - 1:
            row["skill_responsible"] = True
        levels.append(row)
    return levels


def build_marker_ui_config(columns: List[str]) -> Dict[str, Any]:
    layout = detect_marker_tabular_columns(columns)
    if not layout:
        return {}
    max_node = int(layout["max_node"])
    node_indices = list(layout.get("node_indices") or [])
    return {
        "matrix_levels": build_marker_matrix_levels(max_node, node_indices),
        "matrix_column_schema": build_marker_matrix_column_schema(columns),
        "constructor_extra_leaf_steps": 0,
        "column_marker_format": True,
    }
