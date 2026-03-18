# -*- coding: utf-8 -*-
"""
Единый источник данных: JSON, YAML, Excel.
Источник — только текстовая структура: domains + action_templates (текст), literature, examples, ui_config.
Стили (name, icon, color) и инструменты (tools) не в источнике: загружаются из config/metadata.yaml,
инструменты привязываются к листьям по совпадению паттернов в тексте.
Валидация структуры — core/schema.py.
"""
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from .tree import build_tree_from_matrix_data
from .schema import validate_source, ValidationResult, SCHEMA_VERSION

# Ключи в источнике (без stack_labels и action_tools — они в config/metadata.yaml).
META_KEYS = (
    "action_examples",
    "literature",
    "action_templates",
    "ui_config",
)


def load_json(path: str) -> Dict:
    """Загружает JSON-файл."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_yaml(path: str) -> Dict:
    """Загружает YAML-файл."""
    try:
        import yaml
    except ImportError:
        raise RuntimeError("Для загрузки YAML установите: pip install pyyaml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_excel(path: str, sheet_name: Optional[str] = None) -> Dict:
    """
    Загружает Excel-файл. Ожидаемые колонки: Domain, Skill, Action, [Subaction], [Description], [Template ID], ...
    Или первый столбец — уровень вложенности (1=домен, 2=навык, 3=действие, 4=поддействие), далее Name, Description, Template ID.
    """
    rows: List[Dict[str, str]] = []
    columns: List[str] = []

    # 1) Быстрый путь через pandas (если установлен)
    try:
        import pandas as pd
        df = pd.read_excel(path, sheet_name=sheet_name or 0)
        df = df.astype(str).replace("nan", "")
        columns = [str(c) for c in df.columns]
        rows = []
        for _, row in df.iterrows():
            rows.append({str(k): (row.get(k) or "").strip() for k in df.columns})
    except ImportError:
        # 2) Фолбэк без pandas — только openpyxl
        try:
            from openpyxl import load_workbook
        except ImportError:
            raise RuntimeError("Для загрузки Excel установите: pip install openpyxl")

        wb = load_workbook(path, data_only=True, read_only=True)
        try:
            try:
                if isinstance(sheet_name, str):
                    ws = wb[sheet_name]
                elif isinstance(sheet_name, int):
                    ws = wb.worksheets[sheet_name]
                else:
                    ws = wb.worksheets[0]
            except Exception:
                ws = wb.worksheets[0]

            header_iter = ws.iter_rows(min_row=1, max_row=1, values_only=True)
            header_row = next(header_iter, None)
            if not header_row:
                return {"domains": []}

            columns = [str(c).strip() if c is not None else "" for c in header_row]
            rows = []
            max_data_rows = 200000
            empty_streak = 0
            max_empty_streak = 2000
            for raw in ws.iter_rows(min_row=2, values_only=True):
                rec: Dict[str, str] = {}
                has_values = False
                for i, col_name in enumerate(columns):
                    if not col_name:
                        continue
                    v = raw[i] if i < len(raw) else None
                    s = "" if v is None else str(v).strip()
                    if s:
                        has_values = True
                    rec[col_name] = s

                if has_values:
                    rows.append(rec)
                    empty_streak = 0
                else:
                    empty_streak += 1
                    # У части файлов XLSX "хвост" состоит из тысяч пустых строк из-за форматирования листа.
                    # Прерываем чтение, чтобы preview/validation не зависали.
                    if empty_streak >= max_empty_streak:
                        break

                if len(rows) >= max_data_rows:
                    break
        finally:
            wb.close()

    # Единый формат: Domain/Домен, Skill/Навык, Action/Действие, Subaction/Поддействие, Description/Описание, Template ID
    def _col(cols, *candidates):
        for c in candidates:
            if c in cols:
                return c
        return None

    domain_col = _col(columns, "Domain", "domain", "Домен")
    skill_col = _col(columns, "Skill", "skill", "Навык")
    action_col = _col(columns, "Action", "action", "Действие")
    sub_col = _col(columns, "Subaction", "subaction", "Поддействие")
    desc_col = _col(columns, "Description", "description", "Описание навыка", "Описание")
    tpl_col = _col(columns, "Template ID", "template_id", "Template_ID")

    if domain_col and skill_col and action_col:
        domains_map: Dict[str, Dict] = {}
        for row in rows:
            d_name = (row.get(domain_col) or "").strip()
            s_name = (row.get(skill_col) or "").strip()
            a_name = (row.get(action_col) or "").strip()
            sub_name = (row.get(sub_col) or "").strip() if sub_col else ""
            desc = (row.get(desc_col) or "").strip() if desc_col else ""
            tpl = (row.get(tpl_col) or "").strip() or None if tpl_col else None

            if not d_name and not s_name and not a_name:
                continue
            d_name = d_name or "Общее"
            s_name = s_name or "Общие навыки"
            if not a_name:
                continue

            if d_name not in domains_map:
                domains_map[d_name] = {"name": d_name, "skills": {}}
            skills = domains_map[d_name]["skills"]
            if s_name not in skills:
                skills[s_name] = {"name": s_name, "description": "", "actions": []}
            if desc and not skills[s_name]["description"]:
                skills[s_name]["description"] = desc

            if sub_name:
                actions = skills[s_name]["actions"]
                if not actions or "subactions" not in actions[-1]:
                    actions.append({"text": a_name, "template_id": tpl, "subactions": []})
                actions[-1]["subactions"].append({"text": sub_name, "template_id": tpl})
            else:
                skills[s_name]["actions"].append({"text": a_name, "template_id": tpl})

        domains_list = []
        for d in domains_map.values():
            skills_list = [{"name": s["name"], "description": s.get("description", ""), "actions": s["actions"]} for s in d["skills"].values()]
            domains_list.append({"name": d["name"], "skills": skills_list})

        return {"domains": domains_list}

    # Вариант 2: Level (1-4), Name, Description, Template ID
    if "Level" in columns or "level" in columns:
        level_col = "Level" if "Level" in columns else "level"
        name_col = "Name" if "Name" in columns else "name"
        desc_col = "Description" if "Description" in columns else ("description" if "description" in columns else None)
        tpl_col = "Template ID" if "Template ID" in columns else ("template_id" if "template_id" in columns else None)

        def parse_level(s):
            try:
                return int(float(s))
            except (ValueError, TypeError):
                return 0

        root = {"nodes": []}
        current = [root]

        for row in rows:
            level = parse_level(row.get(level_col, 0))
            name = (row.get(name_col) or "").strip()
            desc = (row.get(desc_col) or "").strip() if desc_col else ""
            tpl = (row.get(tpl_col) or "").strip() or None if tpl_col else None
            if not name:
                continue

            node = {"name": name, "description": desc, "template_id": tpl, "children": []}
            while len(current) > level:
                current.pop()
            parent = current[-1]
            if "children" not in parent:
                parent["children"] = []
            parent["children"].append(node)
            current.append(node)

        # Преобразуем root в формат domains, если верхний уровень — домены
        if root.get("children"):
            return _children_to_domains(root["children"])
        return {"domains": []}

    return {"domains": []}


def _children_to_domains(children: List[Dict]) -> Dict:
    """Рекурсивно превращает узлы с children в legacy domains/skills/actions."""
    domains = []
    for d in children:
        domain = {"name": d.get("name", ""), "skills": []}
        for s in d.get("children", []):
            skill = {"name": s.get("name", ""), "description": s.get("description", ""), "actions": []}
            for a in s.get("children", []):
                if a.get("children"):
                    action = {"text": a.get("name", ""), "template_id": a.get("template_id"), "subactions": []}
                    for sub in a["children"]:
                        action["subactions"].append({
                            "text": sub.get("name", ""),
                            "template_id": sub.get("template_id"),
                        })
                    skill["actions"].append(action)
                else:
                    skill["actions"].append({"text": a.get("name", ""), "template_id": a.get("template_id")})
            domain["skills"].append(skill)
        domains.append(domain)
    return {"domains": domains}


def _empty_unified() -> Dict:
    """Пустой единый источник (только структура и текстовое содержимое)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "domains": [],
        "action_examples": [],
        "literature": {},
        "action_templates": {},
        "ui_config": {},
    }


def _normalize_action(a: Dict) -> Dict:
    """Приводит действие к стандартному формату {text, template_id?, subactions?}."""
    if a.get("type") == "group":
        return {
            "text": a.get("name", ""),
            "template_id": None,
            "subactions": [_normalize_subaction(s) for s in (a.get("items") or [])],
        }
    subactions = a.get("subactions")
    if subactions:
        return {**a, "subactions": [_normalize_subaction(s) for s in subactions]}
    return dict(a)


def _normalize_subaction(s: Dict) -> Dict:
    """Приводит поддействие к формату {text, template_id?}."""
    if isinstance(s, dict):
        return {"text": s.get("text", s.get("name", "")), "template_id": s.get("template_id")}
    return {"text": str(s), "template_id": None}


def _normalize_unified(data: Dict) -> Dict:
    """Приводит загруженные данные к формату единого источника (без стилей и списков инструментов)."""
    if not isinstance(data, dict):
        return _empty_unified()
    out = _empty_unified()
    out["schema_version"] = data.get("schema_version", SCHEMA_VERSION)
    domains = data.get("domains") or []
    out["domains"] = []
    for d in domains:
        domain = {k: v for k, v in d.items() if k != "skills"}
        domain["skills"] = []
        for s in d.get("skills", []):
            skill = {k: v for k, v in s.items() if k != "actions"}
            skill["actions"] = [_normalize_action(a) for a in s.get("actions", [])]
            domain["skills"].append(skill)
        out["domains"].append(domain)
    for key in META_KEYS:
        if key in data and data[key] is not None:
            default = [] if key == "action_examples" else {}
            out[key] = data[key] if isinstance(data[key], (dict, list)) else default
    return out


def load_unified_source(
    source_path: str,
    source_type: Optional[str] = None,
    validate: bool = False,
) -> Dict:
    """
    Загружает единый источник данных (JSON, YAML или Excel).
    Один файл содержит структуру (domains) и метаданные (шаблоны, литература, стек, ui_config).
    Уровни вложенности (domain → skill → action → subactions) сохраняются.
    Для Excel загружается только структура; мета при необходимости — из того же файла (листы) или пустая.
    Если validate=True, при ошибках валидации выбрасывается ValueError с текстом ошибок.
    """
    path = Path(source_path)
    if not path.exists():
        return _empty_unified()

    ext = (source_type or path.suffix or "").lower()
    if ext == ".json":
        data = load_json(str(path))
    elif ext in (".yaml", ".yml"):
        data = load_yaml(str(path))
    elif ext in (".xlsx", ".xls"):
        data = _load_excel_as_unified(str(path))
    else:
        data = load_json(str(path))

    out = _normalize_unified(data)
    if validate:
        vr = validate_source(out)
        if not vr.ok:
            raise ValueError("Ошибки валидации: " + "; ".join(vr.errors))
    return out


def load_unified_source_with_validation(
    source_path: str, source_type: Optional[str] = None
) -> Tuple[Dict, ValidationResult]:
    """
    Загружает источник и возвращает (data, validation_result).
    Не выбрасывает исключение при ошибках валидации.
    """
    path = Path(source_path)
    if not path.exists():
        return _empty_unified(), ValidationResult(ok=False, errors=["Файл не найден"])

    try:
        ext = (source_type or path.suffix or "").lower()
        if ext == ".json":
            data = load_json(str(path))
        elif ext in (".yaml", ".yml"):
            data = load_yaml(str(path))
        elif ext in (".xlsx", ".xls"):
            data = _load_excel_as_unified(str(path))
        else:
            data = load_json(str(path))
    except Exception as e:
        return _empty_unified(), ValidationResult(ok=False, errors=[str(e)])

    out = _normalize_unified(data)
    vr = validate_source(out)
    return out, vr


def _load_excel_as_unified(path: str) -> Dict:
    """Читает Excel: первый лист — структура (domains), остальные листы — опционально мета."""
    structure = load_excel(path)
    # При необходимости можно читать листы "action_templates", "literature" и т.д.
    return {"domains": structure.get("domains", [])}


def load_matrix(source_path: str, source_type: Optional[str] = None) -> Dict:
    """
    Загружает матрицу из файла (только структура). Для единого источника используйте load_unified_source.
    Возвращает dict с domains (и при необходимости nodes), готовый для build_tree_from_matrix_data.
    """
    unified = load_unified_source(source_path, source_type)
    return {"domains": unified.get("domains", [])}
