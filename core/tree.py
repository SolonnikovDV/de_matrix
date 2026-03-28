# -*- coding: utf-8 -*-
"""
Универсальная древовидная модель матрицы компетенций.
Уровни вложенности определяются автоматически по структуре данных.
Лист (leaf) — узел без дочерних элементов; только листья имеют страницу с описанием.
"""
from typing import Dict, List, Any, Optional, Tuple
import re

from core.matrix_schema import normalize_level_tags


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
            if (item.get("description") or "").strip():
                node["description"] = str(item.get("description") or "").strip()
            if (item.get("responsible") or "").strip():
                node["responsible"] = str(item.get("responsible") or "").strip()
            ltags = normalize_level_tags(item.get("level_tags") or item.get("level_tag"))
            if ltags:
                node["level_tags"] = ltags
            elif item.get("level_tag"):
                node["level_tag"] = item.get("level_tag")
            if item.get("review_questions"):
                node["review_questions"] = item.get("review_questions")
            lv = item.get("leaf_view")
            if isinstance(lv, dict) and lv:
                node["leaf_view"] = lv
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
            if (item.get("description") or "").strip():
                node["description"] = str(item.get("description") or "").strip()
            if (item.get("responsible") or "").strip():
                node["responsible"] = str(item.get("responsible") or "").strip()
            ltags = normalize_level_tags(item.get("level_tags") or item.get("level_tag"))
            if ltags:
                node["level_tags"] = ltags
            elif item.get("level_tag"):
                node["level_tag"] = item.get("level_tag")
            if item.get("review_questions"):
                node["review_questions"] = item.get("review_questions")
            lv = item.get("leaf_view")
            if isinstance(lv, dict) and lv:
                node["leaf_view"] = lv
            out.append(node)
    return out


def strip_transient_node_fields(nodes: List[Dict]) -> List[Dict]:
    """Удаляет id, path, is_leaf из узлов перед сохранением снапшота (CR / merge)."""
    out: List[Dict] = []
    for n in nodes or []:
        if not isinstance(n, dict):
            continue
        c = {k: v for k, v in n.items() if k not in ("id", "path", "is_leaf")}
        ch = n.get("children")
        if isinstance(ch, list) and ch:
            c["children"] = strip_transient_node_fields(ch)
        else:
            c["children"] = []
        out.append(c)
    return out


def assign_paths_to_generic_nodes(nodes: List[Dict], base: Optional[List[int]] = None) -> None:
    """Проставляет path (индексы для /leaf/...) узлам generic-дерева { name, children }."""
    base = base or []
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        path = base + [i]
        node["path"] = path
        ch = node.get("children") or []
        if ch:
            assign_paths_to_generic_nodes(ch, path)


def tabular_hierarchy_to_nodes(domains: List[Dict]) -> List[Dict]:
    """Табличная иерархия домен→навык→действие (внутренний формат парсера Excel) → дерево с id/path для снятия полей."""
    result = []
    for di, domain in enumerate(domains):
        node = {
            "id": f"d{di}",
            "name": domain.get("name", ""),
            "description": domain.get("description", ""),
            "responsible": domain.get("responsible", ""),
            "path": [di],
            "children": [],
            "level": 0,
        }
        dtags = normalize_level_tags(domain.get("level_tags") or domain.get("level_tag"))
        if dtags:
            node["level_tags"] = dtags
        for si, skill in enumerate(domain.get("skills", [])):
            skill_node = {
                "id": f"d{di}s{si}",
                "name": skill.get("name", ""),
                "description": skill.get("description", ""),
                "responsible": skill.get("responsible", ""),
                "level_sticker": skill.get("level_sticker", ""),
                "path": [di, si],
                "children": [],
                "level": 1,
            }
            stags = normalize_level_tags(skill.get("level_tags") or skill.get("level_sticker") or skill.get("level_tag"))
            if stags:
                skill_node["level_tags"] = stags
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
    """Строит дерево из `nodes` (пути и is_leaf). Пустой список, если узлов нет."""
    nodes = (data or {}).get("nodes") or []
    if not isinstance(nodes, list) or not nodes:
        return []
    assign_paths_to_generic_nodes(nodes)
    _ensure_leaves_flag(nodes)
    return nodes


def collect_leaves(nodes: List[Dict], base_path: Optional[List[int]] = None) -> List[Dict]:
    """Собирает все листья с полными path (path задаётся assign_paths_to_generic_nodes / билдером дерева)."""
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
    """Предки узла по path: от корня до родителя; сам узел path в список не входит."""
    if not path:
        return []
    idx = int(path[0])
    if idx < 0 or idx >= len(nodes):
        return []
    node = nodes[idx]
    if len(path) == 1:
        return []
    ancestors = [node]
    ancestors.extend(get_ancestors(node.get("children", []), path[1:]))
    return ancestors
