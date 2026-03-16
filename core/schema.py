# -*- coding: utf-8 -*-
"""
Единая схема источника данных. Валидация структуры matrix.json.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set

SCHEMA_VERSION = 1

# Допустимые ключи верхнего уровня
ROOT_KEYS = {"domains", "action_examples", "literature", "action_templates", "ui_config"}

# Допустимые ключи в domain
DOMAIN_KEYS = {"name", "skills"}

# Допустимые ключи в skill
SKILL_KEYS = {"name", "description", "actions"}

# Допустимые ключи в action (стандартный формат)
ACTION_KEYS = {"text", "template_id", "subactions"}
# Допустимые ключи в action (формат группы: type="group")
ACTION_GROUP_KEYS = {"type", "name", "items"}

# Допустимые ключи в subaction
SUBACTION_KEYS = {"text", "template_id"}


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

    # domains — обязателен
    domains = data.get("domains")
    if domains is None:
        result.errors.append("Отсутствует ключ 'domains'")
        return result
    if not isinstance(domains, list):
        result.ok = False
        result.errors.append("'domains' должен быть массивом")
        return result

    templates = data.get("action_templates") or {}
    if not isinstance(templates, dict):
        templates = {}

    seen_domains: Set[str] = set()
    for di, domain in enumerate(domains):
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
                            unknown_sub = set(sub.keys()) - SUBACTION_KEYS
                            if unknown_sub:
                                result.warnings.append(
                                    f"{_path_str(subpath)}: неизвестные ключи: {', '.join(sorted(unknown_sub))}"
                                )

    if not domains and result.ok:
        result.warnings.append("Источник пуст: нет доменов")

    return result


def get_schema_info() -> Dict[str, Any]:
    """Возвращает информацию о схеме для API."""
    return {
        "schema_version": SCHEMA_VERSION,
        "root_keys": list(ROOT_KEYS),
        "required_root": ["domains"],
        "structure": {
            "domain": {"required": ["name", "skills"], "optional": []},
            "skill": {"required": ["name", "actions"], "optional": ["description"]},
            "action": {"required": ["text"], "optional": ["template_id", "subactions"]},
            "subaction": {"required": ["text"], "optional": ["template_id"]},
        },
    }
