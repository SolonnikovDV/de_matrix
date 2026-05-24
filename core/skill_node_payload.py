# -*- coding: utf-8 -*-
"""Pack/unpack exls skill fields (section, status, author, reviewer, skill_sections) for DB storage."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional

SKILL_TOP_LEVEL_KEYS = ("section", "status", "author", "reviewer")


def pack_skill_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Extract skill-specific fields from a tree node for JSONB persistence."""
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Any] = {}
    for key in SKILL_TOP_LEVEL_KEYS:
        val = raw.get(key)
        if isinstance(val, str):
            s = val.strip()
            if s:
                out[key] = s
        elif val not in (None, "", []):
            out[key] = val
    ss = raw.get("skill_sections")
    if isinstance(ss, dict) and ss:
        out["skill_sections"] = deepcopy(ss)
    return out


def apply_skill_payload(node: Dict[str, Any], payload: Optional[Dict[str, Any]]) -> None:
    """Merge persisted skill_payload back into a loaded tree node."""
    if not isinstance(node, dict) or not isinstance(payload, dict) or not payload:
        return
    merge_skill_fields(node, payload, overwrite_empty_only=False)


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


def merge_skill_fields(
    dst: Dict[str, Any],
    src: Dict[str, Any],
    *,
    overwrite_empty_only: bool = True,
) -> None:
    """Обогащает навык: label/leaf поля и skill_sections (merge текста)."""
    if not isinstance(dst, dict) or not isinstance(src, dict):
        return

    def _set_top(key: str, val: Any) -> None:
        if not isinstance(val, str) or not val.strip():
            return
        if overwrite_empty_only and str(dst.get(key) or "").strip():
            return
        dst[key] = val.strip()

    for key in SKILL_TOP_LEVEL_KEYS:
        _set_top(key, src.get(key))
    if src.get("author") and not str(dst.get("responsible") or "").strip():
        dst["responsible"] = str(src.get("author")).strip()

    src_ss = src.get("skill_sections")
    if not isinstance(src_ss, dict):
        return
    sections = dst.setdefault("skill_sections", {})
    if not isinstance(sections, dict):
        sections = {}
        dst["skill_sections"] = sections
    for sec_key, sec_val in src_ss.items():
        if not isinstance(sec_val, dict):
            continue
        sec = sections.setdefault(str(sec_key), {})
        if not isinstance(sec, dict):
            sec = {}
            sections[str(sec_key)] = sec
        for field, raw in sec_val.items():
            if not isinstance(raw, str) or not raw.strip():
                continue
            prev = sec.get(field)
            if isinstance(prev, str) and prev.strip():
                sec[field] = _merge_text(prev, raw)
            else:
                sec[field] = raw.strip()
