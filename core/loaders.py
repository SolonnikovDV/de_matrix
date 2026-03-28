# -*- coding: utf-8 -*-
"""
Единый источник данных: JSON, YAML, Excel.
Структура матрицы — только дерево ``nodes``; action_templates, literature, examples, ui_config — как раньше.
Стили (name, icon, color) и инструменты (tools) не в источнике: загружаются из config/metadata.yaml,
инструменты привязываются к листьям по совпадению паттернов в тексте.
Валидация структуры — core/schema.py.
"""
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from .tree import strip_transient_node_fields, tabular_hierarchy_to_nodes
from .schema import validate_source, ValidationResult, SCHEMA_VERSION
from .matrix_schema import normalize_level_tags, normalize_responsible_value
from .excel_unified_relational import try_load_unified_relational_xlsx

# Ключи в источнике (без stack_labels и action_tools — они в config/metadata.yaml).


def excel_cell_str(value: Any) -> str:
    """
    Безопасная строка из ячейки Excel.
    pandas/openpyxl отдают int/float; выражение (v or '').strip() падает на truthy float (например 3.0).
    """
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        if value.is_integer():
            return str(int(value))
        return str(value).strip()
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    s = str(value).strip()
    if s.lower() in ("nan", "none", "nat"):
        return ""
    return s
META_KEYS = (
    "action_examples",
    "literature",
    "action_templates",
    "ui_config",
)


def _parse_level_tag(value: Any) -> Optional[str]:
    """Нормализует уровень компетенции."""
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    aliases = {
        "junior": "junior",
        "jr": "junior",
        "middle": "middle",
        "mid": "middle",
        "senior": "senior",
        "sr": "senior",
        "джуниор": "junior",
        "мидл": "middle",
        "сеньор": "senior",
    }
    return aliases.get(text, text)


def _parse_review_questions(value: Any) -> List[str]:
    """Парсит строку/массив проверочных вопросов в список строк."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if not text:
        return []
    text = text.replace("\r\n", "\n")
    if ";" in text:
        parts = [p.strip() for p in text.split(";")]
    else:
        parts = [p.strip() for p in text.split("\n")]
    return [p for p in parts if p]


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
            rows.append({str(k): excel_cell_str(row.get(k)) for k in df.columns})
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
                return {"nodes": []}

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
                    s = excel_cell_str(v)
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

    # Единый формат: Domain/Домен, Skill/Навык, Action/Действие, Subaction/Поддействие, Description/Описание, Template ID, Level Tag, Review Questions
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
    owner_col = _col(columns, "Responsible", "responsible", "Ответственный", "Автор")
    sticker_col = _col(columns, "Skill Sticker", "skill_sticker", "Level Sticker", "level_sticker", "Наклейка уровня")
    tpl_col = _col(columns, "Template ID", "template_id", "Template_ID")
    level_col = _col(columns, "Level Tag", "level_tag", "Level", "Уровень")
    level_tags_col = _col(columns, "Level Tags", "level_tags", "Наклейки уровня")
    action_level_tags_col = _col(columns, "Action Level Tags", "action_level_tags")
    subaction_level_tags_col = _col(columns, "Subaction Level Tags", "subaction_level_tags")
    questions_col = _col(columns, "Review Questions", "review_questions", "Проверочные вопросы", "Вопросы")

    if domain_col and skill_col and action_col:
        domains_map: Dict[str, Dict] = {}
        for row in rows:
            d_name = excel_cell_str(row.get(domain_col))
            s_name = excel_cell_str(row.get(skill_col))
            a_name = excel_cell_str(row.get(action_col))
            sub_name = excel_cell_str(row.get(sub_col)) if sub_col else ""
            desc = excel_cell_str(row.get(desc_col)) if desc_col else ""
            responsible = excel_cell_str(row.get(owner_col)) if owner_col else ""
            level_sticker = excel_cell_str(row.get(sticker_col)).lower() if sticker_col else ""
            tpl = excel_cell_str(row.get(tpl_col)) or None if tpl_col else None
            review_questions = _parse_review_questions(row.get(questions_col)) if questions_col else []

            if not d_name and not s_name and not a_name:
                continue
            d_name = d_name or "Общее"
            s_name = s_name or "Общие навыки"
            if not a_name:
                continue

            def _row_tags_for_action() -> List[str]:
                if action_level_tags_col:
                    return normalize_level_tags(row.get(action_level_tags_col))
                if sub_name:
                    return []
                if level_tags_col:
                    return normalize_level_tags(row.get(level_tags_col))
                return normalize_level_tags(row.get(level_col)) if level_col else []

            def _row_tags_for_sub() -> List[str]:
                if subaction_level_tags_col:
                    return normalize_level_tags(row.get(subaction_level_tags_col))
                if level_tags_col:
                    return normalize_level_tags(row.get(level_tags_col))
                return normalize_level_tags(row.get(level_col)) if level_col else []

            if d_name not in domains_map:
                domains_map[d_name] = {"name": d_name, "skills": {}}
            skills = domains_map[d_name]["skills"]
            if s_name not in skills:
                skills[s_name] = {"name": s_name, "description": "", "responsible": "", "level_sticker": "", "actions": []}
            if desc and not skills[s_name]["description"]:
                skills[s_name]["description"] = desc
            if responsible and not skills[s_name]["responsible"]:
                skills[s_name]["responsible"] = responsible
            if level_sticker and not skills[s_name]["level_sticker"]:
                skills[s_name]["level_sticker"] = level_sticker

            if sub_name:
                actions = skills[s_name]["actions"]
                if not actions or "subactions" not in actions[-1]:
                    action_item = {"text": a_name, "template_id": tpl, "subactions": []}
                    at = _row_tags_for_action()
                    if at:
                        action_item["level_tags"] = at
                    if review_questions:
                        action_item["review_questions"] = review_questions
                    actions.append(action_item)
                sub_item = {"text": sub_name, "template_id": tpl}
                st = _row_tags_for_sub()
                if st:
                    sub_item["level_tags"] = st
                if review_questions:
                    sub_item["review_questions"] = review_questions
                actions[-1]["subactions"].append(sub_item)
            else:
                action_item = {"text": a_name, "template_id": tpl}
                at = _row_tags_for_action()
                if at:
                    action_item["level_tags"] = at
                if review_questions:
                    action_item["review_questions"] = review_questions
                skills[s_name]["actions"].append(action_item)

        domains_list = []
        for d in domains_map.values():
            skills_list = [
                {
                    "name": s["name"],
                    "description": s.get("description", ""),
                    "responsible": s.get("responsible", ""),
                    "level_sticker": s.get("level_sticker", ""),
                    "actions": s["actions"],
                }
                for s in d["skills"].values()
            ]
            domains_list.append({"name": d["name"], "skills": skills_list})

        return {"nodes": _excel_domain_rows_as_nodes(domains_list)}

    # Вариант 2: Level (1-4), Name, Description, Template ID
    if "Level" in columns or "level" in columns:
        level_col = "Level" if "Level" in columns else "level"
        name_col = "Name" if "Name" in columns else "name"
        desc_col = "Description" if "Description" in columns else ("description" if "description" in columns else None)
        tpl_col = "Template ID" if "Template ID" in columns else ("template_id" if "template_id" in columns else None)
        level_col = "Level Tag" if "Level Tag" in columns else ("level_tag" if "level_tag" in columns else None)
        questions_col = "Review Questions" if "Review Questions" in columns else ("review_questions" if "review_questions" in columns else None)

        def parse_level(s):
            try:
                return int(float(s))
            except (ValueError, TypeError):
                return 0

        root = {"nodes": []}
        current = [root]

        for row in rows:
            level = parse_level(row.get(level_col, 0))
            name = excel_cell_str(row.get(name_col))
            desc = excel_cell_str(row.get(desc_col)) if desc_col else ""
            tpl = excel_cell_str(row.get(tpl_col)) or None if tpl_col else None
            level_tag = _parse_level_tag(row.get(level_col)) if level_col else None
            review_questions = _parse_review_questions(row.get(questions_col)) if questions_col else []
            if not name:
                continue

            node = {"name": name, "description": desc, "template_id": tpl, "children": []}
            if level_tag:
                node["level_tag"] = level_tag
            if review_questions:
                node["review_questions"] = review_questions
            while len(current) > level:
                current.pop()
            parent = current[-1]
            if "children" not in parent:
                parent["children"] = []
            parent["children"].append(node)
            current.append(node)

        if root.get("children"):
            domain_rows = _level_outline_to_domain_rows(root["children"])
            return {"nodes": _excel_domain_rows_as_nodes(domain_rows)}
        return {"nodes": []}

    return {"nodes": []}


def _level_outline_to_domain_rows(children: List[Dict]) -> List[Dict]:
    """Иерархия по колонке Level → промежуточные строки домен/навык/действие (только для Excel)."""
    domains = []
    for d in children:
        domain = {"name": d.get("name", ""), "skills": []}
        for s in d.get("children", []):
            skill = {
                "name": s.get("name", ""),
                "description": s.get("description", ""),
                "responsible": s.get("responsible", ""),
                "level_sticker": s.get("level_sticker", ""),
                "actions": [],
            }
            for a in s.get("children", []):
                if a.get("children"):
                    action = {"text": a.get("name", ""), "template_id": a.get("template_id"), "subactions": []}
                    if a.get("level_tag"):
                        action["level_tag"] = a.get("level_tag")
                    if a.get("review_questions"):
                        action["review_questions"] = a.get("review_questions")
                    for sub in a["children"]:
                        sub_item = {
                            "text": sub.get("name", ""),
                            "template_id": sub.get("template_id"),
                        }
                        if sub.get("level_tag"):
                            sub_item["level_tag"] = sub.get("level_tag")
                        if sub.get("review_questions"):
                            sub_item["review_questions"] = sub.get("review_questions")
                        action["subactions"].append(sub_item)
                    skill["actions"].append(action)
                else:
                    action_item = {"text": a.get("name", ""), "template_id": a.get("template_id")}
                    if a.get("level_tag"):
                        action_item["level_tag"] = a.get("level_tag")
                    if a.get("review_questions"):
                        action_item["review_questions"] = a.get("review_questions")
                    skill["actions"].append(action_item)
            domain["skills"].append(skill)
        domains.append(domain)
    return domains


def _normalize_domain_rows_for_sheet(domains_list: List[Dict]) -> List[Dict]:
    """Нормализует промежуточные domain/skill/action-строки из классического Excel."""
    normalized_domains: List[Dict] = []
    for d in domains_list:
        if not isinstance(d, dict):
            continue
        domain = {k: v for k, v in d.items() if k != "skills"}
        domain["skills"] = []
        for s in d.get("skills", []):
            if not isinstance(s, dict):
                continue
            skill = {k: v for k, v in s.items() if k != "actions"}
            skill["actions"] = [_normalize_action(a) for a in s.get("actions", [])]
            domain["skills"].append(skill)
        normalized_domains.append(domain)
    _sanitize_responsible_fields_in_domains(normalized_domains)
    return normalized_domains


def _excel_domain_rows_as_nodes(domains_list: List[Dict]) -> List[Dict]:
    """Классический Excel → generic ``nodes`` (без id/path/is_leaf)."""
    norm = _normalize_domain_rows_for_sheet(domains_list)
    raw = tabular_hierarchy_to_nodes(norm)
    return strip_transient_node_fields(raw)


def _empty_unified() -> Dict:
    """Пустой единый источник (только структура и текстовое содержимое)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "domains": [],
        "nodes": [],
        "action_examples": [],
        "literature": {},
        "action_templates": {},
        "ui_config": {},
    }


def _normalize_generic_node(n: Dict) -> Dict:
    """Узел дерева произвольной глубины для unified (имена из файла / JSON)."""
    if not isinstance(n, dict):
        return {"name": "", "children": []}
    name = (n.get("name") or n.get("text") or "").strip()
    out: Dict = {"name": name, "children": []}
    for key in ("description", "responsible", "level_sticker", "code", "template_id", "excel_path_key"):
        if key in n and n[key]:
            if key == "excel_path_key":
                out[key] = str(n[key]).strip()
            elif key == "level_sticker":
                out[key] = str(n[key]).strip().lower()
            else:
                out[key] = str(n[key]).strip() if isinstance(n[key], str) else n[key]
    ltags = normalize_level_tags(n.get("level_tags") or n.get("level_tag"))
    if ltags:
        out["level_tags"] = ltags
        if len(ltags) == 1:
            out["level_tag"] = ltags[0]
    elif n.get("level_tag"):
        out["level_tag"] = _parse_level_tag(n.get("level_tag"))
    ch = n.get("children") or []
    if ch:
        out["children"] = [_normalize_generic_node(x) for x in ch if isinstance(x, dict)]
    lv = n.get("leaf_view")
    if isinstance(lv, dict) and lv:
        out["leaf_view"] = deepcopy(lv)
    rq = _parse_review_questions(n.get("review_questions"))
    if rq:
        out["review_questions"] = rq
    return out


def _sanitize_responsible_fields_in_domains(domains: List[Dict]) -> None:
    """Убирает заглушки вроде «не указан» из полей responsible (импорт / нормализация)."""
    for d in domains:
        if not isinstance(d, dict):
            continue
        if "responsible" in d:
            d["responsible"] = normalize_responsible_value(d.get("responsible"))
        for s in d.get("skills") or []:
            if not isinstance(s, dict):
                continue
            if "responsible" in s:
                s["responsible"] = normalize_responsible_value(s.get("responsible"))
            for act in s.get("actions") or []:
                if not isinstance(act, dict):
                    continue
                if "responsible" in act:
                    act["responsible"] = normalize_responsible_value(act.get("responsible"))
                for sub in act.get("subactions") or []:
                    if isinstance(sub, dict) and "responsible" in sub:
                        sub["responsible"] = normalize_responsible_value(sub.get("responsible"))


def _normalize_action(a: Dict) -> Dict:
    """Приводит действие к стандартному формату {text, template_id?, subactions?}."""
    if a.get("type") == "group":
        return {
            "text": a.get("name", ""),
            "template_id": None,
            "subactions": [_normalize_subaction(s) for s in (a.get("items") or [])],
        }
    subactions = a.get("subactions")
    ltags = normalize_level_tags(a.get("level_tags") or a.get("level_tag"))
    normalized_questions = _parse_review_questions(a.get("review_questions"))
    if subactions:
        out = {**a, "subactions": [_normalize_subaction(s) for s in subactions]}
    else:
        out = dict(a)
    if ltags:
        out["level_tags"] = ltags
        if len(ltags) == 1:
            out["level_tag"] = ltags[0]
        else:
            out.pop("level_tag", None)
    else:
        out.pop("level_tags", None)
    if normalized_questions:
        out["review_questions"] = normalized_questions
    elif "review_questions" in out and not out["review_questions"]:
        out.pop("review_questions", None)
    lv = a.get("leaf_view")
    if isinstance(lv, dict) and lv:
        out["leaf_view"] = lv
    return out


def _normalize_subaction(s: Dict) -> Dict:
    """Приводит поддействие к формату {text, template_id?, level_tag?, review_questions?}."""
    if isinstance(s, dict):
        out = {"text": s.get("text", s.get("name", "")), "template_id": s.get("template_id")}
        stags = normalize_level_tags(s.get("level_tags") or s.get("level_tag"))
        if stags:
            out["level_tags"] = stags
            if len(stags) == 1:
                out["level_tag"] = stags[0]
        elif s.get("level_tag"):
            out["level_tag"] = _parse_level_tag(s.get("level_tag"))
        questions = _parse_review_questions(s.get("review_questions"))
        if questions:
            out["review_questions"] = questions
        lv = s.get("leaf_view")
        if isinstance(lv, dict) and lv:
            out["leaf_view"] = lv
        return out
    return {"text": str(s), "template_id": None}


def _normalize_unified(data: Dict) -> Dict:
    """Приводит загруженные данные к формату единого источника (без стилей и списков инструментов)."""
    if not isinstance(data, dict):
        return _empty_unified()
    out = _empty_unified()
    out["schema_version"] = data.get("schema_version", SCHEMA_VERSION)
    nodes_in = data.get("nodes")
    if isinstance(nodes_in, list) and nodes_in:
        out["nodes"] = [_normalize_generic_node(x) for x in nodes_in if isinstance(x, dict)]
    else:
        out["nodes"] = []
    out["domains"] = []
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
    Структура — ``nodes``; метаданные — шаблоны, литература, стек, ui_config.
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
    """Читает Excel: формат Unified_Relational_Span или классические колонки Domain/Skill/Action."""
    ur = try_load_unified_relational_xlsx(path)
    if ur:
        return {
            "nodes": ur.get("nodes") or [],
            "ui_config": ur.get("ui_config") or {},
        }
    structure = load_excel(path)
    return {"nodes": structure.get("nodes", [])}


def load_excel_for_matrix_import(path: str) -> Dict:
    """Предпросмотр/импорт Excel: сначала unified relational (enriched), иначе классический лист."""
    return _load_excel_as_unified(path)


def load_matrix(source_path: str, source_type: Optional[str] = None) -> Dict:
    """
    Загружает матрицу из файла (только структура). Для единого источника используйте load_unified_source.
    """
    unified = load_unified_source(source_path, source_type)
    return {"nodes": unified.get("nodes") or []}
