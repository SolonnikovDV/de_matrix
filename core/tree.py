# -*- coding: utf-8 -*-
"""
Универсальная древовидная модель матрицы компетенций.
Уровни вложенности определяются автоматически по структуре данных.
Лист (leaf) — узел без дочерних элементов; только листья имеют страницу с описанием.
"""
from typing import Dict, List, Any, Optional, Tuple
import re


def _normalize_children(
    items: List[Dict],
    path_prefix: List[int],
    id_prefix: str,
    level: int,
) -> List[Dict]:
    """
    Рекурсивно строит узлы из списка элементов с опциональными subactions/children.
    Автоскейл: любая глубина вложенности; лист — элемент без дочерних.
    """
    out = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if item.get("type") == "group":
            text = item.get("name", "")
            subactions = item.get("items", [])
        else:
            text = item.get("text", item.get("name", ""))
            subactions = item.get("subactions", item.get("children", []))
        template_id = item.get("template_id")
        path = path_prefix + [i]
        node_id = f"{id_prefix}{i}" if id_prefix else "n_" + "_".join(str(p) for p in path)
        if subactions:
            child_nodes = _normalize_children(subactions, path, node_id + "_", level + 1)
            node = {
                "id": node_id,
                "name": text,
                "path": path,
                "template_id": template_id,
                "children": child_nodes,
                "level": level,
                "is_leaf": False,
            }
            if item.get("level_tag"):
                node["level_tag"] = item.get("level_tag")
            if item.get("review_questions"):
                node["review_questions"] = item.get("review_questions")
            out.append(node)
        else:
            node = {
                "id": node_id,
                "name": text,
                "path": path,
                "template_id": template_id,
                "children": [],
                "level": level,
                "is_leaf": True,
            }
            if item.get("level_tag"):
                node["level_tag"] = item.get("level_tag")
            if item.get("review_questions"):
                node["review_questions"] = item.get("review_questions")
            out.append(node)
    return out


def _normalize_legacy_domains(domains: List[Dict]) -> List[Dict]:
    """Преобразует legacy-формат (domains -> skills -> actions [-> subactions]) в универсальные узлы с children. Автоскейл по дочерним."""
    result = []
    for di, domain in enumerate(domains):
        node = {
            "id": f"d{di}",
            "name": domain.get("name", ""),
            "path": [di],
            "children": [],
            "level": 0,
        }
        for si, skill in enumerate(domain.get("skills", [])):
            skill_node = {
                "id": f"d{di}s{si}",
                "name": skill.get("name", ""),
                "description": skill.get("description", ""),
                "path": [di, si],
                "children": [],
                "level": 1,
            }
            actions = skill.get("actions", [])
            skill_node["children"] = _normalize_children(actions, [di, si], f"d{di}s{si}a", 2)
            node["children"].append(skill_node)
        result.append(node)
    return result


def _ensure_leaves_flag(nodes: List[Dict]) -> None:
    """Проставляет is_leaf для узлов без children."""
    for node in nodes:
        if node.get("children"):
            _ensure_leaves_flag(node["children"])
        else:
            node["is_leaf"] = True


def build_tree_from_matrix_data(data: Dict) -> List[Dict]:
    """
    Строит дерево из данных матрицы.
    Поддерживает:
    - legacy: { "domains": [ { "name", "skills": [ { "name", "actions": [...] } ] } ] }
    - generic: { "nodes": [ { "name", "children": [...] } ] } — произвольная глубина
    """
    if "nodes" in data:
        # Уже generic-дерево
        nodes = data["nodes"]
        _ensure_leaves_flag(nodes)
        return nodes

    if "domains" in data:
        nodes = _normalize_legacy_domains(data["domains"])
        _ensure_leaves_flag(nodes)
        return nodes

    return []


def collect_leaves(nodes: List[Dict], base_path: Optional[List[int]] = None) -> List[Dict]:
    """Собирает все листья с полными path (path уже задан в узлах при legacy-нормализации)."""
    base_path = base_path or []
    leaves = []
    for i, node in enumerate(nodes):
        path = node.get("path") or (base_path + [i])
        if node.get("children"):
            leaves.extend(collect_leaves(node["children"], path))
        else:
            node["is_leaf"] = True
            node["path"] = path
            leaves.append(node)
    return leaves


def get_node_by_path(nodes: List[Dict], path: List[int]) -> Optional[Dict]:
    """Возвращает узел по пути (список индексов). nodes — верхний уровень (домены)."""
    if not path:
        return None
    idx = int(path[0])
    if idx < 0 or idx >= len(nodes):
        return None
    node = nodes[idx]
    if len(path) == 1:
        return node
    return get_node_by_path(node.get("children", []), path[1:])


def path_to_url(path: List[int]) -> str:
    """Преобразует path в URL для страницы листа: /leaf/0/1/2 или /leaf/0/1/2/0."""
    return "/leaf/" + "/".join(str(p) for p in path)


def get_ancestors(nodes: List[Dict], path: List[int]) -> List[Dict]:
    """Возвращает список предков от корня до узла по path (не включая сам узел)."""
    if not path:
        return []
    idx = int(path[0])
    if idx < 0 or idx >= len(nodes):
        return []
    node = nodes[idx]
    ancestors = [node]
    if len(path) == 1:
        return ancestors
    ancestors.extend(get_ancestors(node.get("children", []), path[1:]))
    return ancestors
