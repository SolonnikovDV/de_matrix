# -*- coding: utf-8 -*-
"""
Единая схема источника данных. Валидация структуры matrix.json.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set

SCHEMA_VERSION = 1

# Допустимые ключи верхнего уровня
ROOT_KEYS = {
    "schema_version",
    "domains",
    "nodes",
    "action_examples",
    "literature",
    "action_templates",
    "ui_config",
}

# Допустимые ключи в domain
DOMAIN_KEYS = {"name", "skills", "description", "responsible", "level_tag", "level_tags"}

# Допустимые ключи в skill
SKILL_KEYS = {"name", "description", "responsible", "level_sticker", "level_tag", "level_tags", "actions"}

# Допустимые ключи в action (стандартный формат)
ACTION_KEYS = {
    "text",
    "template_id",
    "subactions",
    "level_tag",
    "level_tags",
    "leaf_view",
    "review_questions",
    "code",
    "description",
    "responsible",
    "excel_path_key",
}
# Допустимые ключи в action (формат группы: type="group")
ACTION_GROUP_KEYS = {"type", "name", "items"}

# Допустимые ключи в subaction
SUBACTION_KEYS = {
    "text",
    "template_id",
    "level_tag",
    "level_tags",
    "leaf_view",
    "review_questions",
    "code",
    "description",
    "responsible",
    "excel_path_key",
}

ALLOWED_LEVEL_TAGS = {"junior", "middle", "senior"}
ALLOWED_SKILL_STICKERS = {"junior", "middle", "senior"}

# Узлы generic-дерева (nodes)
NODE_KEYS = {
    "name",
    "text",
    "children",
    "description",
    "responsible",
    "template_id",
    "level_tag",
    "level_tags",
    "level_sticker",
    "leaf_view",
    "review_questions",
    "code",
    "excel_path_key",
    "type",
    "items",
    "id",
    "path",
    "is_leaf",
    "section",
    "status",
    "author",
    "reviewer",
    "skill_sections",
}


@dataclass
class ValidationResult:
    """Результат валидации источника."""
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "recommendations": self.recommendations,
            "schema_version": self.schema_version,
        }


def _path_str(path: List[str]) -> str:
    return " → ".join(path) if path else "корень"


def _node_children(node: Dict[str, Any]) -> List[Any]:
    if node.get("type") == "group" and isinstance(node.get("items"), list):
        return node["items"]
    ch = node.get("children")
    return ch if isinstance(ch, list) else []


def _validate_generic_nodes(
    nodes: List[Any],
    path: List[str],
    result: ValidationResult,
    templates: Dict[str, Any],
) -> None:
    """Рекурсивная проверка дерева nodes (name/children)."""
    if not isinstance(nodes, list):
        result.errors.append(f"{_path_str(path)}: nodes должен быть массивом")
        result.ok = False
        return
    for i, raw in enumerate(nodes):
        np = path + [f"[{i}]"]
        if not isinstance(raw, dict):
            result.errors.append(f"{_path_str(np)}: узел должен быть объектом")
            result.ok = False
            continue
        unknown_n = set(raw.keys()) - NODE_KEYS
        if unknown_n:
            result.warnings.append(f"{_path_str(np)}: неизвестные ключи: {', '.join(sorted(unknown_n))}")
        ch = _node_children(raw)
        is_leaf = len(ch) == 0
        label = (raw.get("name") or raw.get("text") or "").strip() if not is_leaf else (raw.get("name") or raw.get("text") or "")
        if not str(label or "").strip() and not is_leaf:
            result.warnings.append(f"{_path_str(np)}: пустое имя внутреннего узла")
        if raw.get("type") == "group":
            items = raw.get("items")
            if items is not None and not isinstance(items, list):
                result.errors.append(f"{_path_str(np)}: items должен быть массивом")
                result.ok = False
        else:
            cc = raw.get("children")
            if cc is not None and not isinstance(cc, list):
                result.errors.append(f"{_path_str(np)}: children должен быть массивом")
                result.ok = False
        sticker = raw.get("level_sticker")
        if sticker not in (None, ""):
            sv = str(sticker).strip().lower()
            if sv not in ALLOWED_SKILL_STICKERS:
                result.errors.append(
                    f"{_path_str(np)}: level_sticker должен быть одним из {', '.join(sorted(ALLOWED_SKILL_STICKERS))}"
                )
                result.ok = False
        slt = raw.get("level_tags")
        if slt not in (None, "", []):
            if not isinstance(slt, list):
                result.errors.append(f"{_path_str(np)}: level_tags должен быть массивом строк")
                result.ok = False
            else:
                for j, x in enumerate(slt):
                    v = str(x).strip().lower()
                    if v not in ALLOWED_LEVEL_TAGS:
                        result.errors.append(
                            f"{_path_str(np + [f'level_tags[{j}]'])}: допустимы только {', '.join(sorted(ALLOWED_LEVEL_TAGS))}"
                        )
                        result.ok = False
        if is_leaf:
            nm = str(raw.get("name") or raw.get("text") or "").strip()
            if not nm:
                result.errors.append(f"{_path_str(np)}: у листа должно быть непустое name или text")
                result.ok = False
            tpl_id = raw.get("template_id")
            if tpl_id and templates and str(tpl_id) not in templates:
                result.recommendations.append(
                    f"{_path_str(np)}: template_id '{tpl_id}' не найден в action_templates."
                )
            _validate_leaf_meta(np, raw, result)
        else:
            _validate_generic_nodes(ch, np, result, templates)


def _validate_leaf_meta(path: List[str], node: Dict[str, Any], result: ValidationResult) -> None:
    """Проверяет level_tag и review_questions для листового элемента."""
    level_tag = node.get("level_tag")
    if level_tag not in (None, ""):
        level_value = str(level_tag).strip().lower()
        if level_value not in ALLOWED_LEVEL_TAGS:
            result.errors.append(
                f"{_path_str(path)}: level_tag должен быть одним из {', '.join(sorted(ALLOWED_LEVEL_TAGS))}"
            )
            result.ok = False

    lt = node.get("level_tags")
    if lt not in (None, "", []):
        if not isinstance(lt, list):
            result.errors.append(f"{_path_str(path)}: level_tags должен быть массивом строк")
            result.ok = False
        else:
            for i, x in enumerate(lt):
                v = str(x).strip().lower()
                if v not in ALLOWED_LEVEL_TAGS:
                    result.errors.append(
                        f"{_path_str(path + [f'level_tags[{i}]'])}: допустимы только {', '.join(sorted(ALLOWED_LEVEL_TAGS))}"
                    )
                    result.ok = False

    lv = node.get("leaf_view")
    if lv not in (None, "", {}):
        if not isinstance(lv, dict):
            result.errors.append(f"{_path_str(path)}: leaf_view должен быть объектом")
            result.ok = False

    review_questions = node.get("review_questions")
    if review_questions not in (None, ""):
        if not isinstance(review_questions, list):
            result.errors.append(f"{_path_str(path)}: review_questions должен быть массивом строк")
            result.ok = False
        else:
            for qi, question in enumerate(review_questions):
                if not isinstance(question, str) or not question.strip():
                    result.errors.append(f"{_path_str(path)}: review_questions[{qi}] должен быть непустой строкой")
                    result.ok = False

    ss = node.get("skill_sections")
    if ss not in (None, "", {}):
        if not isinstance(ss, dict):
            result.errors.append(f"{_path_str(path)}: skill_sections должен быть объектом")
            result.ok = False
        else:
            for sec_key, sec_val in ss.items():
                if sec_val in (None, ""):
                    continue
                if not isinstance(sec_val, dict):
                    result.errors.append(
                        f"{_path_str(path + [f'skill_sections.{sec_key}'])}: раздел навыка должен быть объектом"
                    )
                    result.ok = False

    for prop in ("status", "author", "reviewer", "section"):
        val = node.get(prop)
        if val is not None and val != "" and not isinstance(val, str):
            result.errors.append(f"{_path_str(path)}: {prop} должен быть строкой")
            result.ok = False


def validate_source(data: Any) -> ValidationResult:
    """
    Валидирует структуру единого источника.
    Возвращает ValidationResult с ошибками, предупреждениями и рекомендациями.
    """
    result = ValidationResult(ok=True)
    if not isinstance(data, dict):
        result.ok = False
        result.errors.append("Источник должен быть объектом (dict)")
        return result

    # Неизвестные ключи верхнего уровня
    unknown = set(data.keys()) - ROOT_KEYS
    if unknown:
        result.warnings.append(f"Неизвестные ключи верхнего уровня: {', '.join(sorted(unknown))}. Будут проигнорированы.")

    # domains — устаревший контейнер (после нормализации всегда []); nodes — основное дерево
    domains = data.get("domains")
    if domains is None:
        domains = []
    if not isinstance(domains, list):
        result.ok = False
        result.errors.append("'domains' должен быть массивом")
        return result

    nodes = data.get("nodes")
    if nodes is None:
        nodes = []
    if not isinstance(nodes, list):
        result.ok = False
        result.errors.append("'nodes' должен быть массивом")
        return result

    has_nodes = len(nodes) > 0

    templates = data.get("action_templates") or {}
    if not isinstance(templates, dict):
        templates = {}

    if has_nodes:
        _validate_generic_nodes(nodes, ["nodes"], result, templates)

    seen_domains: Set[str] = set()
    for di, domain in (enumerate(domains) if domains else enumerate([])):
        path = [f"domains[{di}]"]
        if not isinstance(domain, dict):
            result.errors.append(f"{_path_str(path)}: домен должен быть объектом")
            result.ok = False
            continue

        name = domain.get("name")
        if not name or not str(name).strip():
            result.errors.append(f"{_path_str(path)}: поле 'name' обязательно и не должно быть пустым")
            result.ok = False
        else:
            name = str(name).strip()
            if name in seen_domains:
                result.warnings.append(f"{_path_str(path)}: дубликат домена '{name}'")
            seen_domains.add(name)

        unknown_d = set(domain.keys()) - DOMAIN_KEYS
        if unknown_d:
            result.warnings.append(f"{_path_str(path)}: неизвестные ключи: {', '.join(sorted(unknown_d))}")
        dlt = domain.get("level_tags")
        if dlt not in (None, "", []):
            if not isinstance(dlt, list):
                result.errors.append(f"{_path_str(path)}: level_tags должен быть массивом строк")
                result.ok = False
            else:
                for i, x in enumerate(dlt):
                    v = str(x).strip().lower()
                    if v not in ALLOWED_LEVEL_TAGS:
                        result.errors.append(
                            f"{_path_str(path + [f'level_tags[{i}]'])}: допустимы только {', '.join(sorted(ALLOWED_LEVEL_TAGS))}"
                        )
                        result.ok = False

        skills = domain.get("skills")
        if skills is None:
            result.errors.append(f"{_path_str(path)}: отсутствует ключ 'skills'")
            result.ok = False
            continue
        if not isinstance(skills, list):
            result.errors.append(f"{_path_str(path)}: 'skills' должен быть массивом")
            result.ok = False
            continue

        seen_skills: Set[str] = set()
        for si, skill in enumerate(skills):
            spath = path + [f"skills[{si}]"]
            if not isinstance(skill, dict):
                result.errors.append(f"{_path_str(spath)}: навык должен быть объектом")
                result.ok = False
                continue

            sname = skill.get("name")
            if not sname or not str(sname).strip():
                result.errors.append(f"{_path_str(spath)}: поле 'name' обязательно")
                result.ok = False
            else:
                sname = str(sname).strip()
                key = f"{name}::{sname}"
                if key in seen_skills:
                    result.warnings.append(f"{_path_str(spath)}: дубликат навыка '{sname}' в домене '{name}'")
                seen_skills.add(key)

            unknown_s = set(skill.keys()) - SKILL_KEYS
            if unknown_s:
                result.warnings.append(f"{_path_str(spath)}: неизвестные ключи: {', '.join(sorted(unknown_s))}")
            sticker = skill.get("level_sticker")
            if sticker not in (None, ""):
                sticker_value = str(sticker).strip().lower()
                if sticker_value not in ALLOWED_SKILL_STICKERS:
                    result.errors.append(
                        f"{_path_str(spath)}: level_sticker должен быть одним из {', '.join(sorted(ALLOWED_SKILL_STICKERS))}"
                    )
                    result.ok = False
            slt = skill.get("level_tags")
            if slt not in (None, "", []):
                if not isinstance(slt, list):
                    result.errors.append(f"{_path_str(spath)}: level_tags должен быть массивом строк")
                    result.ok = False
                else:
                    for i, x in enumerate(slt):
                        v = str(x).strip().lower()
                        if v not in ALLOWED_LEVEL_TAGS:
                            result.errors.append(
                                f"{_path_str(spath + [f'level_tags[{i}]'])}: допустимы только {', '.join(sorted(ALLOWED_LEVEL_TAGS))}"
                            )
                            result.ok = False

            actions = skill.get("actions")
            if actions is None:
                result.errors.append(f"{_path_str(spath)}: отсутствует ключ 'actions'")
                result.ok = False
                continue
            if not isinstance(actions, list):
                result.errors.append(f"{_path_str(spath)}: 'actions' должен быть массивом")
                result.ok = False
                continue

            for ai, action in enumerate(actions):
                apath = spath + [f"actions[{ai}]"]
                if not isinstance(action, dict):
                    result.errors.append(f"{_path_str(apath)}: действие должно быть объектом")
                    result.ok = False
                    continue

                is_group = action.get("type") == "group"
                if is_group:
                    text = action.get("name")
                    subactions = action.get("items")
                    unknown_a = set(action.keys()) - ACTION_GROUP_KEYS
                else:
                    text = action.get("text")
                    subactions = action.get("subactions")
                    unknown_a = set(action.keys()) - ACTION_KEYS

                if not text or not str(text).strip():
                    result.errors.append(
                        f"{_path_str(apath)}: поле 'text' (или 'name' для type='group') обязательно"
                    )
                    result.ok = False
                else:
                    if len(str(text).strip()) < 3:
                        result.warnings.append(f"{_path_str(apath)}: текст действия слишком короткий")

                if not is_group:
                    tpl_id = action.get("template_id")
                    if tpl_id and templates and str(tpl_id) not in templates:
                        result.recommendations.append(
                            f"{_path_str(apath)}: template_id '{tpl_id}' не найден в action_templates. "
                            "Добавьте шаблон или оставьте template_id пустым."
                        )
                    _validate_leaf_meta(apath, action, result)

                if unknown_a:
                    result.warnings.append(f"{_path_str(apath)}: неизвестные ключи: {', '.join(sorted(unknown_a))}")

                if is_group and subactions is None:
                    subactions = []
                if subactions is not None:
                    if not isinstance(subactions, list):
                        attr = "items" if is_group else "subactions"
                        result.errors.append(f"{_path_str(apath)}: '{attr}' должен быть массивом")
                        result.ok = False
                    else:
                        sub_key = "items" if is_group else "subactions"
                        for subi, sub in enumerate(subactions):
                            subpath = apath + [f"{sub_key}[{subi}]"]
                            if not isinstance(sub, dict):
                                result.errors.append(f"{_path_str(subpath)}: поддействие должно быть объектом")
                                result.ok = False
                                continue
                            sub_text = sub.get("text", sub.get("name", ""))
                            if not sub_text or not str(sub_text).strip():
                                result.errors.append(f"{_path_str(subpath)}: поле 'text' обязательно")
                                result.ok = False
                            sub_tpl = sub.get("template_id")
                            if sub_tpl and templates and str(sub_tpl) not in templates:
                                result.recommendations.append(
                                    f"{_path_str(subpath)}: template_id '{sub_tpl}' не найден в action_templates."
                                )
                            _validate_leaf_meta(subpath, sub, result)
                            unknown_sub = set(sub.keys()) - SUBACTION_KEYS
                            if unknown_sub:
                                result.warnings.append(
                                    f"{_path_str(subpath)}: неизвестные ключи: {', '.join(sorted(unknown_sub))}"
                                )

    if not domains and not has_nodes and result.ok:
        result.recommendations.append(
            "Источник пуст: нет узлов в nodes. Добавьте данные матрицы."
        )

    return result


def get_schema_info() -> Dict[str, Any]:
    """Возвращает информацию о схеме для API."""
    return {
        "schema_version": SCHEMA_VERSION,
        "root_keys": list(ROOT_KEYS),
        "required_root": ["nodes"],
        "structure": {
            "domain": {
                "required": ["name", "skills"],
                "optional": ["description", "responsible", "level_tag", "level_tags"],
            },
            "skill": {
                "required": ["name", "actions"],
                "optional": ["description", "responsible", "level_sticker", "level_tag", "level_tags"],
            },
            "action": {
                "required": ["text"],
                "optional": [
                    "template_id",
                    "subactions",
                    "level_tag",
                    "level_tags",
                    "leaf_view",
                    "review_questions",
                    "code",
                    "description",
                    "responsible",
                    "excel_path_key",
                ],
                "notes": {
                    "level_tags": "Список грейдов (junior, middle, senior); приоритет над устаревшим level_tag.",
                    "leaf_view": "Объект блоков листа: ключи из заголовков (leaf_view) в Excel, значения — строки или списки строк.",
                    "excel_path_key": "Внутренний ключ пути item-колонок (разделитель U+001F); для симметричного экспорта в unified relational.",
                },
            },
            "subaction": {
                "required": ["text"],
                "optional": [
                    "template_id",
                    "level_tag",
                    "level_tags",
                    "leaf_view",
                    "review_questions",
                    "code",
                    "description",
                    "responsible",
                    "excel_path_key",
                ],
                "notes": {
                    "level_tags": "Как у action.",
                    "leaf_view": "Как у action; для листа-поддействия.",
                    "excel_path_key": "Как у action.",
                },
            },
        },
        "ui_config": {
            "matrix_levels": "Иерархия уровней и теги (item / leaf_view / skill_sticker).",
            "matrix_column_schema": "Описание колонок импорта, в т.ч. leaf_view_key для подписей блоков.",
            "constructor_extra_leaf_steps": "Число доп. шагов башни после последней строки matrix_levels (по умолчанию 1) — выбор/создание дочернего узла в subactions; 0 = башня строго по matrix_levels.",
            "constructor_leaf_step_title": "Заголовок первого доп. шага башни (лист/подуровень).",
        },
    }
