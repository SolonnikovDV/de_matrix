# -*- coding: utf-8 -*-
"""
Слияние загруженных данных с текущим источником.
Режимы: append (добавить в существующие ветки и создать новые), replace_domain, replace_skill.
"""
from typing import Dict, Any, List, Optional
from copy import deepcopy

from .loaders import META_KEYS, _normalize_unified, _empty_unified
from .schema import SCHEMA_VERSION


def _find_domain(domains: List[Dict], name: str) -> Optional[int]:
    """Индекс домена по имени."""
    name = (name or "").strip()
    for i, d in enumerate(domains):
        if (d.get("name") or "").strip() == name:
            return i
    return None


def _find_skill(skills: List[Dict], name: str) -> Optional[int]:
    """Индекс навыка по имени."""
    name = (name or "").strip()
    for i, s in enumerate(skills):
        if (s.get("name") or "").strip() == name:
            return i
    return None


def _action_key(a: Dict) -> str:
    """Ключ для сравнения действий (избежание дубликатов)."""
    return (a.get("text") or "").strip()


def _merge_actions(existing: List[Dict], new_actions: List[Dict], skip_duplicates: bool = True) -> List[Dict]:
    """Объединяет списки действий. При skip_duplicates не добавляет дубликаты по text."""
    result = list(existing)
    seen = {_action_key(a) for a in existing} if skip_duplicates else set()
    for a in new_actions:
        key = _action_key(a)
        if skip_duplicates and key in seen:
            continue
        seen.add(key)
        result.append(deepcopy(a))
    return result


def merge_upload_into_source(
    current: Dict[str, Any],
    upload: Dict[str, Any],
    merge_mode: str = "append",
    target_domain: Optional[str] = None,
    target_skill: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Сливает загруженные данные с текущим источником. Автоскейл: в существующую ветку или новую.

    merge_mode:
      - append: автоскейл по имени — в существующие домены/навыки или создание новых
      - append_to_domain: все данные в указанный домен (target_domain)
      - append_to_skill: все действия в указанный навык (target_domain + target_skill)
      - replace_domain: заменить домен целиком
      - replace_skill: заменить навык целиком
    """
    current = _normalize_unified(current) if current else _empty_unified()
    upload = _normalize_unified(upload) if upload else {"domains": []}
    upload_domains = upload.get("domains") or []

    if not upload_domains:
        return current

    out = deepcopy(current)
    out["schema_version"] = SCHEMA_VERSION
    out_domains = out["domains"]

    if merge_mode == "replace_domain":
        d_name = (upload_domains[0].get("name") or "").strip()
        idx = _find_domain(out_domains, d_name)
        new_d = deepcopy(upload_domains[0])
        if idx is not None:
            out_domains[idx] = new_d
        else:
            out_domains.append(new_d)
        return out

    if merge_mode == "replace_skill":
        if not upload_domains or not (upload_domains[0].get("skills")):
            return out
        d_name = (upload_domains[0].get("name") or "").strip()
        s_name = (upload_domains[0]["skills"][0].get("name") or "").strip()
        di = _find_domain(out_domains, d_name)
        if di is None:
            out_domains.append(deepcopy(upload_domains[0]))
            return out
        new_skill = deepcopy(upload_domains[0]["skills"][0])
        si = _find_skill(out_domains[di]["skills"], s_name)
        if si is not None:
            out_domains[di]["skills"][si] = new_skill
        else:
            out_domains[di]["skills"].append(new_skill)
        return out

    if merge_mode == "append_to_domain" and target_domain:
        # Все данные из upload — в указанный домен. Автоскейл навыков.
        td_name = (target_domain or "").strip()
        di = _find_domain(out_domains, td_name)
        if di is None:
            out_domains.append({"name": td_name, "skills": []})
            di = len(out_domains) - 1
        for ud in upload_domains:
            for us in ud.get("skills") or []:
                s_name = (us.get("name") or "").strip()
                if not s_name:
                    continue
                si = _find_skill(out_domains[di]["skills"], s_name)
                if si is None:
                    out_domains[di]["skills"].append(deepcopy(us))
                else:
                    existing = out_domains[di]["skills"][si].get("actions") or []
                    new_actions = us.get("actions") or []
                    out_domains[di]["skills"][si]["actions"] = _merge_actions(
                        existing, new_actions, skip_duplicates=True
                    )
        return out

    if merge_mode == "append_to_skill" and target_domain and target_skill:
        # Все действия из upload — в указанный навык.
        td_name = (target_domain or "").strip()
        ts_name = (target_skill or "").strip()
        di = _find_domain(out_domains, td_name)
        if di is None:
            out_domains.append({"name": td_name, "skills": [{"name": ts_name, "description": "", "actions": []}]})
            di = len(out_domains) - 1
        si = _find_skill(out_domains[di]["skills"], ts_name)
        if si is None:
            out_domains[di]["skills"].append({"name": ts_name, "description": "", "actions": []})
            si = len(out_domains[di]["skills"]) - 1
        all_actions = []
        for ud in upload_domains:
            for us in ud.get("skills") or []:
                for a in us.get("actions") or []:
                    all_actions.append(deepcopy(a))
        existing = out_domains[di]["skills"][si].get("actions") or []
        out_domains[di]["skills"][si]["actions"] = _merge_actions(existing, all_actions, skip_duplicates=True)
        return out

    # append (default) — автоскейл по имени
    for ud in upload_domains:
        d_name = (ud.get("name") or "").strip()
        if not d_name:
            continue
        di = _find_domain(out_domains, d_name)
        if di is None:
            out_domains.append(deepcopy(ud))
            continue

        for us in ud.get("skills") or []:
            s_name = (us.get("name") or "").strip()
            if not s_name:
                continue
            si = _find_skill(out_domains[di]["skills"], s_name)
            if si is None:
                out_domains[di]["skills"].append(deepcopy(us))
                continue

            existing_actions = out_domains[di]["skills"][si].get("actions") or []
            new_actions = us.get("actions") or []
            out_domains[di]["skills"][si]["actions"] = _merge_actions(
                existing_actions, new_actions, skip_duplicates=True
            )
            # subactions внутри действий — при дубликате action перезаписываем subactions
            for na in new_actions:
                if not na.get("subactions"):
                    continue
                for ea in out_domains[di]["skills"][si]["actions"]:
                    if _action_key(ea) == _action_key(na):
                        ea["subactions"] = deepcopy(na["subactions"])
                        break

    # Мета: объединяем (upload перезаписывает/дополняет)
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
