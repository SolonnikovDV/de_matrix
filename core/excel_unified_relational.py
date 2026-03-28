# -*- coding: utf-8 -*-
"""
Чтение формата Unified_Relational_Span из .xlsx без openpyxl (zip + XML).
Первая строка — заголовки с тегами в скобках: (item), (leaf_view), (skill_sticker).
"""
from __future__ import annotations

import math
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .matrix_schema import (
    TAG_ITEM,
    TAG_LEAF_VIEW,
    TAG_SKILL_STICKER,
    leaf_view_key_from_header_label,
    normalize_responsible_value,
    parse_header_tag_cell,
)

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _scalar_to_str(val: Any) -> str:
    """Значение ячейки → строка (на случай нестроковых типов из XML/данных)."""
    if val is None:
        return ""
    if isinstance(val, float):
        if math.isnan(val):
            return ""
        if val.is_integer():
            return str(int(val))
        return str(val).strip()
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, int):
        return str(val)
    s = str(val).strip()
    if s.lower() in ("nan", "none", "nat"):
        return ""
    return s


def _load_shared_strings(z: zipfile.ZipFile) -> List[str]:
    try:
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    out: List[str] = []
    for si in root.findall("m:si", NS):
        parts: List[str] = []
        for t in si.findall(".//m:t", NS):
            if t.text:
                parts.append(t.text)
        out.append("".join(parts))
    return out


def _cell_value(cell: ET.Element, sst: List[str]) -> str:
    t = cell.attrib.get("t")
    v = cell.find("m:v", NS)
    if t == "s" and v is not None and v.text is not None:
        i = int(v.text)
        return sst[i] if 0 <= i < len(sst) else v.text
    if v is not None and v.text is not None:
        return v.text
    is_ = cell.find("m:is", NS)
    if is_ is not None:
        tt = is_.find(".//m:t", NS)
        return (tt.text or "") if tt is not None else ""
    return ""


def _parse_sheet_rows(z: zipfile.ZipFile, sheet_path: str, sst: List[str]) -> Dict[int, Dict[str, str]]:
    root = ET.fromstring(z.read(sheet_path))
    rows: Dict[int, Dict[str, str]] = {}
    for row in root.findall(".//m:sheetData/m:row", NS):
        r = int(row.attrib["r"])
        rows[r] = {}
        for c in row.findall("m:c", NS):
            ref = c.attrib.get("r", "")
            m = re.match(r"^([A-Z]+)", ref)
            if not m:
                continue
            rows[r][m.group(1)] = _cell_value(c, sst)
    return rows


def _workbook_sheet_path(z: zipfile.ZipFile, sheet_name: str) -> Optional[str]:
    rel_root = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    relmap = {x.attrib["Id"]: x.attrib["Target"] for x in rel_root}
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    nsr = {"r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    for s in wb.find("m:sheets", NS).findall("m:sheet", NS):
        if s.attrib.get("name") == sheet_name:
            rid = s.attrib.get("{" + nsr["r"] + "}id")
            tgt = relmap.get(rid, "")
            return "xl/" + tgt.lstrip("/")
    return None


def _detect_unified_header(first_row: Dict[str, str]) -> bool:
    joined = " ".join(first_row.values())
    return "(item)" in joined.lower() and ("(leaf_view)" in joined.lower() or "(skill_sticker)" in joined.lower())


def _strip_responsible_cell(raw: Any) -> str:
    s = _scalar_to_str(raw)
    s = re.sub(r"^👤\s*", "", s)
    s = re.sub(r"^(автор|author)\s*:\s*", "", s, flags=re.I)
    return normalize_responsible_value(s.strip())


def _carry_forward_item_row(carry: List[str], raw: List[str]) -> None:
    """
    В merged-таблицах Excel пустые ячейки не попадают в строку XML — значения «текут» сверху.
    При новом значении в колонке i сбрасываем carry[i+1:], чтобы не цеплять подузлы к старому родителю.
    """
    n = len(carry)
    if len(raw) != n:
        return
    for i in range(n):
        if raw[i]:
            carry[i] = raw[i]
            for j in range(i + 1, n):
                carry[j] = ""


def _split_action_sub_if_glued(rest0: str, item_col_count: int) -> List[str]:
    """
    Если в файле ровно 3 item-колонки (домен, навык, одна текстовая), иногда в третью попадает
    «Действие — Поддействие». При ≥4 колонках разбиение не делаем — глубина задаётся колонками.
    """
    t = (rest0 or "").strip()
    if item_col_count != 3 or " — " not in t:
        return [t] if t else []
    left, _, right = t.partition(" — ")
    left, right = left.strip(), right.strip()
    if left and right:
        return [left, right]
    return [t] if t else []


def _item_action_sub_indices(item_col_count: int) -> Tuple[int, Optional[int]]:
    """
    Индексы в path (0=домен, 1=навык, далее item-уровни): последний item = лист/шаг,
    предпоследний = практика/действие. При 5 колонках: контекст не склеивается с практикой.
    ni=3 → только лист-действие в path[2]; ni>=4 → sub в path[ni-1], action в path[ni-2].
    """
    ni = item_col_count
    if ni < 3:
        return 2, None
    if ni == 3:
        return 2, None
    return ni - 2, ni - 1


def try_load_unified_relational_xlsx(
    path: str,
    sheet_name: str = "Unified_Relational_Span",
) -> Optional[Dict[str, Any]]:
    """
    Если файл в формате unified relational — возвращает
    { domains, ui_config_patch } иначе None.
    """
    p = Path(path)
    if not p.is_file():
        return None

    with zipfile.ZipFile(p) as z:
        sst = _load_shared_strings(z)
        sp = _workbook_sheet_path(z, sheet_name)
        if not sp:
            return None
        rows = _parse_sheet_rows(z, sp, sst)
        if 1 not in rows:
            return None
        header = rows[1]
        if not _detect_unified_header(header):
            return None

        item_cols: List[str] = []
        leaf_map: Dict[str, str] = {}
        responsible_col: Optional[str] = None
        skill_sticker_header_label = ""
        column_schema: List[Dict[str, Any]] = []

        for col in sorted(header.keys(), key=lambda x: (len(x), x)):
            raw_h = header[col]
            label, tags = parse_header_tag_cell(_scalar_to_str(raw_h))
            entry: Dict[str, Any] = {"col": col, "header": raw_h, "label": label, "tags": tags}
            if TAG_ITEM in tags:
                item_cols.append(col)
                entry["item_depth"] = len(item_cols) - 1
            if TAG_LEAF_VIEW in tags and label:
                key = leaf_view_key_from_header_label(label)
                leaf_map[col] = key
                entry["leaf_view_key"] = key
            if TAG_SKILL_STICKER in tags:
                responsible_col = col
                entry["maps_to"] = "skill.responsible"
                skill_sticker_header_label = label
            column_schema.append(entry)

        if len(item_cols) < 3:
            return None

        matrix_levels: List[Dict[str, Any]] = []
        for i, col in enumerate(item_cols):
            label, tags = parse_header_tag_cell(_scalar_to_str(header[col]))
            row: Dict[str, Any] = {"depth": i, "title": label, "tags": list(tags)}
            if i == 1:
                row["skill_responsible"] = True
                if skill_sticker_header_label:
                    row["responsible_column_label"] = skill_sticker_header_label
            if i >= 2:
                row["grade_stickers"] = True
            matrix_levels.append(row)

        roots: List[Dict[str, Any]] = []

        def _ensure_ordered_child(children: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
            name = (name or "").strip()
            for ch in children:
                if (ch.get("name") or "").strip() == name:
                    return ch
            node: Dict[str, Any] = {"name": name, "children": []}
            children.append(node)
            return node

        def insert_path(segments: List[str], leaf_payload: Dict[str, str], resp: str) -> None:
            """Один путь item-колонок = цепочка узлов; лист получает leaf_view и excel_path_key."""
            segs = [s.strip() for s in segments if s and str(s).strip()]
            if len(segs) < 3:
                return
            cur_list = roots
            cur: Optional[Dict[str, Any]] = None
            for i, seg in enumerate(segs):
                cur = _ensure_ordered_child(cur_list, seg)
                if i == 1 and resp.strip():
                    cur["responsible"] = resp.strip()
                if i < len(segs) - 1:
                    cur.pop("leaf_view", None)
                cur_list = cur.setdefault("children", [])
            if cur is not None:
                cur["excel_path_key"] = "\x1f".join(x.strip() for x in segs if x.strip())
                if leaf_payload:
                    cur.setdefault("leaf_view", {}).update(leaf_payload)

        ni = len(item_cols)
        carry = [""] * ni

        for r in sorted(rows):
            if r <= 1:
                continue
            row = rows[r]
            raw = [_scalar_to_str(row.get(c)) for c in item_cols]
            if not any(raw):
                continue

            _carry_forward_item_row(carry, raw)

            leaf_payload: Dict[str, str] = {}
            for lc, vk in leaf_map.items():
                val = _scalar_to_str(row.get(lc))
                if val:
                    leaf_payload[vk] = val

            resp = ""
            if responsible_col:
                resp = _strip_responsible_cell(row.get(responsible_col, ""))

            path = list(carry)
            while path and not path[-1].strip():
                path.pop()
            if len(path) < 2:
                continue

            domain_n = path[0].strip()
            skill_n = path[1].strip() if len(path) > 1 else ""
            if not domain_n or not skill_n:
                continue

            if len(path) == 2:
                continue

            segs_trim = [p.strip() for p in path if p and str(p).strip()]
            if len(segs_trim) < 3:
                continue

            if ni == 3 and len(segs_trim) == 3 and " — " in segs_trim[2]:
                split = _split_action_sub_if_glued(segs_trim[2], ni)
                if len(split) == 2:
                    ak, sub_part = split[0].strip(), split[1].strip()
                    insert_path([segs_trim[0], segs_trim[1], ak, sub_part], leaf_payload, resp)
                    continue

            insert_path(segs_trim, leaf_payload, resp)

        ui_patch = {
            "matrix_levels": matrix_levels,
            "matrix_column_schema": column_schema,
        }

        return {"nodes": roots, "domains": [], "ui_config": ui_patch}


def is_unified_relational_xlsx(path: str, sheet_name: str = "Unified_Relational_Span") -> bool:
    try:
        return try_load_unified_relational_xlsx(path, sheet_name=sheet_name) is not None
    except Exception:
        return False
