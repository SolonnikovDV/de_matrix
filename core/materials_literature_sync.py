# -*- coding: utf-8 -*-
"""Sync materials URLs from skill_sections into Mongo literature catalog."""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from copy import deepcopy

_LEAF_VIEW_SOURCE_URL_RE = re.compile(r"https?://[^\s\]\)<>\"']+")


def _coerce_source_dict(d: Any) -> Dict[str, str]:
    if not isinstance(d, dict):
        return {}
    rid = str(d.get("id") or d.get("literature_id") or "").strip()
    url = str(d.get("url") or d.get("link") or "").strip()
    title = str(d.get("title") or d.get("name") or d.get("text") or "").strip()
    raw = str(d.get("raw") or d.get("value") or "").strip()
    return {
        "literature_id": rid,
        "url": url,
        "title": title or raw,
        "raw": raw or title or url,
    }


def _parse_line_to_entry(line: str) -> Optional[Dict[str, str]]:
    line = (line or "").strip()
    if not line:
        return None
    m = _LEAF_VIEW_SOURCE_URL_RE.search(line)
    url = m.group(0) if m else ""
    rest = line.replace(url, "").strip(" —–-|").strip() if url else line
    title = rest or (url if url else line)
    return _coerce_source_dict({"url": url, "title": title, "raw": line})


def parse_materials_text(text: str) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    for ln in re.split(r"[\n\r]+", text or ""):
        e = _parse_line_to_entry(ln)
        if e and (e.get("url") or e.get("title") or e.get("raw")):
            entries.append(e)
    return entries


def extract_materials_text(node: Dict[str, Any]) -> str:
    if not isinstance(node, dict):
        return ""
    ss = node.get("skill_sections")
    if isinstance(ss, dict):
        q = ss.get("questions")
        if isinstance(q, dict):
            m = q.get("materials")
            if isinstance(m, str) and m.strip():
                return m.strip()
    lv = node.get("leaf_view")
    if isinstance(lv, dict):
        for key in ("materials", "Материалы", "sources"):
            v = lv.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return ""


def _literature_id_for_entry(entry: Dict[str, str], existing: Dict[str, Any]) -> str:
    rid = (entry.get("literature_id") or "").strip()
    if rid and rid in existing:
        return rid
    url = (entry.get("url") or "").strip()
    if url:
        for lit_id, item in existing.items():
            if (str(item.get("url") or "").strip()) == url:
                return str(lit_id)
    title = (entry.get("title") or "").strip()
    if title:
        tl = title.lower()
        for lit_id, item in existing.items():
            if (str(item.get("title") or "").strip().lower()) == tl:
                return str(lit_id)
    gk = url or title or (entry.get("raw") or "").strip()
    h = hashlib.md5(gk.encode("utf-8")).hexdigest()[:12]
    return f"mat_{h}"


def collect_materials_from_nodes(nodes: List[Dict[str, Any]]) -> List[Tuple[Dict[str, str], str]]:
    """Return (entry, breadcrumb) for each materials line in leaf nodes."""
    out: List[Tuple[Dict[str, str], str]] = []

    def walk(items: List[Dict[str, Any]], trail: List[str]) -> None:
        for n in items or []:
            if not isinstance(n, dict):
                continue
            name = (n.get("name") or "").strip()
            path = trail + ([name] if name else [])
            ch = n.get("children") or []
            if ch:
                walk(ch, path)
            else:
                text = extract_materials_text(n)
                crumb = " → ".join(p for p in path if p)
                for e in parse_materials_text(text):
                    out.append((e, crumb))

    walk(nodes or [], [])
    return out


def sync_materials_to_literature(
    nodes: List[Dict[str, Any]],
    existing: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Build literature map entries from materials in skill nodes.
    Merges with existing catalog; does not remove stale entries.
    """
    catalog = deepcopy(existing or {})
    seen_keys: Set[Tuple[str, str]] = set()
    for entry, _crumb in collect_materials_from_nodes(nodes):
        url = (entry.get("url") or "").strip()
        title = (entry.get("title") or entry.get("raw") or url or "Материал").strip()
        if not url and not title:
            continue
        dedupe_key = (url, title.lower())
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        lit_id = _literature_id_for_entry(entry, catalog)
        prev = catalog.get(lit_id) or {}
        catalog[lit_id] = {
            "title": title if (title and title != url) else (prev.get("title") or url or title),
            "chapter": prev.get("chapter") or "",
            "pages": prev.get("pages") or "",
            "url": url or prev.get("url") or "",
            "description": prev.get("description") or "Из колонки «Материалы» матрицы.",
            "local_path": prev.get("local_path") or "",
            "from_matrix_materials": True,
        }
    return catalog
