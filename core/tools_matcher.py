# -*- coding: utf-8 -*-
"""
Привязка инструментов к листьям по совпадению паттернов в тексте матрицы.
Источник данных не содержит списков инструментов — они определяются по ключевым словам
в названии действия и в тексте шаблона (minimal_requirements, antipatterns).
"""
from typing import Dict, List, Any


def _normalize(text: str) -> str:
    """Приведение к нижнему регистру и склейка для поиска."""
    if not text:
        return ""
    return " " + (text or "").lower().replace("\n", " ") + " "


def get_tools_for_text(
    leaf_text: str,
    template_text: str,
    tools_patterns: Dict[str, List[str]],
    tools_groups: Dict[str, Dict[str, Any]],
) -> List[str]:
    """
    По тексту листа (название действия) и тексту шаблона (minimal_requirements, antipatterns)
    возвращает список инструментов: для каждой группы, чьи ключевые слова встретились в тексте,
    добавляются все инструменты из этой группы (без дубликатов, порядок по первому вхождению группы).
    """
    if not tools_patterns or not tools_groups:
        return []
    combined = _normalize(leaf_text) + " " + _normalize(template_text)
    seen_groups: List[str] = []
    result: List[str] = []
    for group_id, keywords in (tools_patterns or {}).items():
        if group_id not in tools_groups:
            continue
        for kw in keywords:
            if kw in combined:
                if group_id not in seen_groups:
                    seen_groups.append(group_id)
                    group = tools_groups.get(group_id, {})
                    for t in group.get("tools") or []:
                        if t not in result:
                            result.append(t)
                break
    return result


def get_tools_groups_for_display(
    tools_patterns: Dict[str, List[str]],
    tools_groups: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Список всех групп инструментов для UI (name, id, tools)."""
    out = []
    for gid, group in (tools_groups or {}).items():
        out.append({
            "id": gid,
            "name": group.get("name", gid),
            "tools": group.get("tools", []),
        })
    return out
