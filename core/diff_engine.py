from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from core.tree import assign_paths_to_generic_nodes, collect_leaves, get_ancestors, _ensure_leaves_flag


def _escape_pointer_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _join_pointer(path: str, token: str) -> str:
    escaped = _escape_pointer_token(token)
    if not path:
        return f"/{escaped}"
    return f"{path}/{escaped}"


def build_json_patch(before: Any, after: Any, path: str = "") -> List[Dict[str, Any]]:
    """
    Build RFC6902-like JSON Patch operations between two JSON-compatible values.
    Lists are replaced as a whole when changed to keep patch generation deterministic.
    """
    if before == after:
        return []

    if isinstance(before, dict) and isinstance(after, dict):
        ops: List[Dict[str, Any]] = []
        before_keys = set(before.keys())
        after_keys = set(after.keys())

        for key in sorted(before_keys - after_keys):
            ops.append({"op": "remove", "path": _join_pointer(path, str(key))})
        for key in sorted(after_keys - before_keys):
            ops.append({"op": "add", "path": _join_pointer(path, str(key)), "value": deepcopy(after[key])})
        for key in sorted(before_keys & after_keys):
            ops.extend(build_json_patch(before[key], after[key], _join_pointer(path, str(key))))
        return ops

    if isinstance(before, list) and isinstance(after, list):
        return [{"op": "replace", "path": path or "", "value": deepcopy(after)}]

    return [{"op": "replace", "path": path or "", "value": deepcopy(after)}]


def _flatten_leaves(unified: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """leaf_path → метаданные для диффа (имена уровней — хлебные крошки по глубине)."""
    nodes = (unified or {}).get("nodes") or []
    if not nodes:
        return {}
    tree = deepcopy(nodes)
    assign_paths_to_generic_nodes(tree)
    _ensure_leaves_flag(tree)
    leaves = collect_leaves(tree)
    out: Dict[str, Dict[str, Any]] = {}
    for leaf in leaves:
        parts = leaf.get("path") or []
        if not parts:
            continue
        path_str = "/".join(str(p) for p in parts)
        anc = get_ancestors(tree, parts)
        chain = list(anc) + [leaf]
        names = [(n.get("name") or "").strip() for n in chain]
        nlen = len(names)
        if not nlen:
            continue
        dom = names[0]
        sk = names[1] if nlen > 1 else ""
        if nlen == 1:
            act, sub = names[0], ""
        elif nlen == 2:
            act, sub = names[1], ""
        elif nlen == 3:
            act, sub = names[2], ""
        else:
            act, sub = names[-2], names[-1]
        out[path_str] = {
            "path": path_str,
            "domain": dom,
            "skill": sk,
            "action": act,
            "subaction": sub,
            "template_id": leaf.get("template_id"),
            "level_tag": leaf.get("level_tag"),
            "review_questions": deepcopy(leaf.get("review_questions") or []),
        }
    return out


def build_structural_diff(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    before_map = _flatten_leaves(before or {})
    after_map = _flatten_leaves(after or {})
    before_paths = set(before_map.keys())
    after_paths = set(after_map.keys())

    added = [{"path": p, "after": after_map[p]} for p in sorted(after_paths - before_paths)]
    removed = [{"path": p, "before": before_map[p]} for p in sorted(before_paths - after_paths)]

    updated: List[Dict[str, Any]] = []
    for path in sorted(before_paths & after_paths):
        if before_map[path] != after_map[path]:
            updated.append({"path": path, "before": before_map[path], "after": after_map[path]})

    return {
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "updated": len(updated),
        },
        "added": added,
        "removed": removed,
        "updated": updated,
    }


def _count_tree_nodes(nodelist: Any) -> int:
    if not isinstance(nodelist, list):
        return 0
    n = 0
    for node in nodelist:
        if not isinstance(node, dict):
            continue
        n += 1
        n += _count_tree_nodes(node.get("children") or [])
    return n


def build_upsert_plan(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    before_nodes = (before or {}).get("nodes") or []
    after_nodes = (after or {}).get("nodes") or []
    before_leaves = _flatten_leaves(before or {})
    after_leaves = _flatten_leaves(after or {})
    return {
        "nodes": {
            "before_count": _count_tree_nodes(before_nodes),
            "after_count": _count_tree_nodes(after_nodes),
        },
        "leaves": {
            "before_count": len(before_leaves),
            "after_count": len(after_leaves),
        },
    }


def build_revision_payload(
    *,
    base_snapshot: Dict[str, Any],
    upload_payload: Dict[str, Any],
    proposed_snapshot: Dict[str, Any],
    merge_mode: str,
    target_domain: str | None = None,
    target_skill: str | None = None,
) -> Dict[str, Any]:
    base = deepcopy(base_snapshot or {"nodes": []})
    upload = deepcopy(upload_payload or {})
    proposed = deepcopy(proposed_snapshot or {"nodes": []})
    return {
        "merge_mode": merge_mode,
        "target_domain": target_domain,
        "target_skill": target_skill,
        "upload_payload": upload,
        "base_snapshot": base,
        "proposed_snapshot": proposed,
        "json_patch": build_json_patch(base, proposed),
        "structural_diff": build_structural_diff(base, proposed),
        "upsert_plan": build_upsert_plan(base, proposed),
    }
