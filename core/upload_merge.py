# -*- coding: utf-8 -*-
"""
Слияние загруженных данных с текущим источником (единое дерево `nodes`).
Режимы: append, append_to_domain, append_to_skill, replace_domain, replace_skill,
replace_all, increment (обогащение при совпадении схемы).
"""
from typing import Dict, Any, List, Optional, Tuple
from copy import deepcopy

from .loaders import META_KEYS, _normalize_unified, _empty_unified
from .schema import SCHEMA_VERSION, ValidationResult


def _merge_node_meta(dst: Dict, src: Dict) -> None:
    if not isinstance(dst, dict) or not isinstance(src, dict):
        return
    for key in ("description", "responsible", "code", "excel_path_key"):
        if key in src and str(src.get(key) or "").strip():
            dst[key] = str(src[key]).strip()
    if "level_sticker" in src and str(src.get("level_sticker") or "").strip():
        dst["level_sticker"] = str(src["level_sticker"]).strip().lower()
    if src.get("template_id"):
        dst["template_id"] = src["template_id"]
    if isinstance(src.get("level_tags"), list) and src["level_tags"]:
        dst["level_tags"] = deepcopy(src["level_tags"])
        if len(src["level_tags"]) == 1:
            dst["level_tag"] = src["level_tags"][0]
    elif src.get("level_tag"):
        dst["level_tag"] = src["level_tag"]
    if isinstance(src.get("review_questions"), list) and src["review_questions"]:
        dst["review_questions"] = deepcopy(src["review_questions"])
    if isinstance(src.get("leaf_view"), dict) and src["leaf_view"]:
        dst["leaf_view"] = {**(dst.get("leaf_view") or {}), **deepcopy(src["leaf_view"])}
    for key in ("section", "status", "author", "reviewer"):
        val = src.get(key)
        if isinstance(val, str) and val.strip() and not str(dst.get(key) or "").strip():
            dst[key] = val.strip()
    ss = src.get("skill_sections")
    if isinstance(ss, dict) and ss:
        from .skill_node_payload import merge_skill_fields

        merge_skill_fields(dst, src)


def _merge_children_by_name(existing: List[Dict], incoming: List[Dict]) -> List[Dict]:
    out = deepcopy(existing)
    idx_map = {(n.get("name") or "").strip(): i for i, n in enumerate(out) if isinstance(n, dict)}
    for inc in incoming:
        if not isinstance(inc, dict):
            continue
        nm = (inc.get("name") or "").strip()
        if not nm:
            continue
        if nm not in idx_map:
            out.append(deepcopy(inc))
            idx_map[nm] = len(out) - 1
            continue
        ei = idx_map[nm]
        _merge_node_meta(out[ei], inc)
        inc_ch = inc.get("children") or []
        if inc_ch:
            ex_ch = out[ei].get("children") or []
            out[ei]["children"] = _merge_children_by_name(ex_ch, inc_ch)
    return out


def _find_root_skill(out_nodes: List[Dict], domain_name: str, skill_name: str) -> Tuple[Optional[Dict], Optional[Dict]]:
    dn = (domain_name or "").strip()
    sn = (skill_name or "").strip()
    for root in out_nodes:
        if not isinstance(root, dict):
            continue
        if (root.get("name") or "").strip() != dn:
            continue
        for sk in root.get("children") or []:
            if isinstance(sk, dict) and (sk.get("name") or "").strip() == sn:
                return root, sk
        return root, None
    return None, None


def merge_upload_into_source(
    current: Dict[str, Any],
    upload: Dict[str, Any],
    merge_mode: str = "append",
    target_domain: Optional[str] = None,
    target_skill: Optional[str] = None,
) -> Dict[str, Any]:
    current = _normalize_unified(current) if current else _empty_unified()
    upload = _normalize_unified(upload) if upload else _empty_unified()
    up_nodes = upload.get("nodes") or []

    if merge_mode == "increment":
        from .incremental_merge import merge_incremental_into_source

        merged, vr = merge_incremental_into_source(current, upload)
        if not vr.ok:
            raise ValueError("; ".join(vr.errors))
        return merged

    if merge_mode == "replace_all":
        out = _empty_unified()
        out["schema_version"] = SCHEMA_VERSION
        out["nodes"] = deepcopy(up_nodes) if isinstance(up_nodes, list) else []
        for key in META_KEYS:
            uv = upload.get(key)
            if uv is not None:
                default = [] if key == "action_examples" else {}
                out[key] = deepcopy(uv) if isinstance(uv, (dict, list)) else default
        return out

    out = deepcopy(current)
    out["schema_version"] = SCHEMA_VERSION
    out_nodes = out.get("nodes") or []
    if not isinstance(out_nodes, list):
        out_nodes = []
        out["nodes"] = out_nodes

    if not up_nodes:
        pass
    elif merge_mode == "replace_domain" and up_nodes:
        d_name = (up_nodes[0].get("name") or "").strip()
        replaced = False
        for i, root in enumerate(out_nodes):
            if isinstance(root, dict) and (root.get("name") or "").strip() == d_name:
                out_nodes[i] = deepcopy(up_nodes[0])
                replaced = True
                break
        if not replaced:
            out_nodes.append(deepcopy(up_nodes[0]))
    elif merge_mode == "replace_skill" and up_nodes:
        u0 = up_nodes[0]
        d_name = (u0.get("name") or "").strip()
        u_skills = u0.get("children") or []
        if not u_skills or not isinstance(u_skills[0], dict):
            pass
        else:
            s_new = deepcopy(u_skills[0])
            s_name = (s_new.get("name") or "").strip()
            root, _ = _find_root_skill(out_nodes, d_name, s_name)
            if root is None:
                out_nodes.append(deepcopy(u0))
            else:
                ch = root.get("children") or []
                found = False
                for j, c in enumerate(ch):
                    if isinstance(c, dict) and (c.get("name") or "").strip() == s_name:
                        ch[j] = s_new
                        found = True
                        break
                if not found:
                    ch.append(s_new)
                root["children"] = ch
    elif merge_mode == "append_to_domain" and target_domain:
        td = (target_domain or "").strip()
        ri = None
        for i, root in enumerate(out_nodes):
            if isinstance(root, dict) and (root.get("name") or "").strip() == td:
                ri = i
                break
        if ri is None:
            out_nodes.append({"name": td, "children": []})
            ri = len(out_nodes) - 1
        root = out_nodes[ri]
        for ur in up_nodes:
            if not isinstance(ur, dict):
                continue
            _merge_node_meta(root, ur)
            root["children"] = _merge_children_by_name(root.get("children") or [], ur.get("children") or [])
    elif merge_mode == "append_to_skill" and target_domain and target_skill:
        td = (target_domain or "").strip()
        ts = (target_skill or "").strip()
        root, skill_node = _find_root_skill(out_nodes, td, ts)
        if root is None:
            out_nodes.append({"name": td, "children": [{"name": ts, "children": []}]})
            _, skill_node = _find_root_skill(out_nodes, td, ts)
        elif skill_node is None:
            root.setdefault("children", []).append({"name": ts, "children": []})
            _, skill_node = _find_root_skill(out_nodes, td, ts)
        bucket: List[Dict] = []
        for ur in up_nodes:
            if not isinstance(ur, dict):
                continue
            for snode in ur.get("children") or []:
                if not isinstance(snode, dict):
                    continue
                if (snode.get("name") or "").strip() == ts or len(ur.get("children") or []) == 1:
                    bucket.extend(snode.get("children") or [])
        if not bucket:
            for ur in up_nodes:
                if isinstance(ur, dict):
                    bucket.extend(ur.get("children") or [])
        if skill_node is not None:
            skill_node["children"] = _merge_children_by_name(skill_node.get("children") or [], bucket)
    else:
        out["nodes"] = _merge_children_by_name(out_nodes, up_nodes)

    for key in META_KEYS:
        uv = upload.get(key)
        if uv is None:
            continue
        default = [] if key == "action_examples" else {}
        if isinstance(uv, dict):
            out[key] = {**(out.get(key) or default), **uv}
        elif isinstance(uv, list):
            out[key] = list(out.get(key) or []) + list(uv)
        else:
            out[key] = uv

    return out
