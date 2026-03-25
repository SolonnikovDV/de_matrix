from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List


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
    leaves: Dict[str, Dict[str, Any]] = {}
    domains = (unified or {}).get("domains") or []
    for di, domain in enumerate(domains):
        domain_name = domain.get("name") or ""
        for si, skill in enumerate(domain.get("skills") or []):
            skill_name = skill.get("name") or ""
            for ai, action in enumerate(skill.get("actions") or []):
                action_name = action.get("text") or ""
                subactions = action.get("subactions") or []
                if subactions:
                    for subi, sub in enumerate(subactions):
                        path = f"{di}/{si}/{ai}/{subi}"
                        leaves[path] = {
                            "path": path,
                            "domain": domain_name,
                            "skill": skill_name,
                            "action": action_name,
                            "subaction": sub.get("text") or "",
                            "template_id": sub.get("template_id"),
                            "level_tag": sub.get("level_tag"),
                            "review_questions": deepcopy(sub.get("review_questions") or []),
                        }
                else:
                    path = f"{di}/{si}/{ai}"
                    leaves[path] = {
                        "path": path,
                        "domain": domain_name,
                        "skill": skill_name,
                        "action": action_name,
                        "subaction": "",
                        "template_id": action.get("template_id"),
                        "level_tag": action.get("level_tag"),
                        "review_questions": deepcopy(action.get("review_questions") or []),
                    }
    return leaves


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


def build_upsert_plan(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    before_domains = (before or {}).get("domains") or []
    after_domains = (after or {}).get("domains") or []
    before_d_codes = {d.get("code") or d.get("name") or "" for d in before_domains}
    after_d_codes = {d.get("code") or d.get("name") or "" for d in after_domains}

    def _collect(items: List[Dict[str, Any]], child_key: str) -> set[str]:
        out: set[str] = set()
        for item in items:
            code = item.get("code") or item.get("name") or item.get("text") or ""
            if code:
                out.add(str(code))
            for child in item.get(child_key) or []:
                child_code = child.get("code") or child.get("name") or child.get("text") or ""
                if child_code:
                    out.add(str(child_code))
        return out

    before_skills = _collect([s for d in before_domains for s in (d.get("skills") or [])], "actions")
    after_skills = _collect([s for d in after_domains for s in (d.get("skills") or [])], "actions")
    before_actions = _collect(
        [a for d in before_domains for s in (d.get("skills") or []) for a in (s.get("actions") or [])],
        "subactions",
    )
    after_actions = _collect(
        [a for d in after_domains for s in (d.get("skills") or []) for a in (s.get("actions") or [])],
        "subactions",
    )
    before_subs = {
        (sub.get("code") or sub.get("text") or "")
        for d in before_domains
        for s in (d.get("skills") or [])
        for a in (s.get("actions") or [])
        for sub in (a.get("subactions") or [])
    }
    after_subs = {
        (sub.get("code") or sub.get("text") or "")
        for d in after_domains
        for s in (d.get("skills") or [])
        for a in (s.get("actions") or [])
        for sub in (a.get("subactions") or [])
    }

    return {
        "domains": {
            "insert": len(after_d_codes - before_d_codes),
            "delete": len(before_d_codes - after_d_codes),
            "update": len(before_d_codes & after_d_codes),
        },
        "skills": {
            "insert": len(after_skills - before_skills),
            "delete": len(before_skills - after_skills),
            "update": len(before_skills & after_skills),
        },
        "actions": {
            "insert": len(after_actions - before_actions),
            "delete": len(before_actions - after_actions),
            "update": len(before_actions & after_actions),
        },
        "subactions": {
            "insert": len(after_subs - before_subs),
            "delete": len(before_subs - after_subs),
            "update": len(before_subs & after_subs),
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
    base = deepcopy(base_snapshot or {"domains": []})
    upload = deepcopy(upload_payload or {})
    proposed = deepcopy(proposed_snapshot or {"domains": []})
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
