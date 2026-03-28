# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Dict, Any, Optional, List

from sqlalchemy import select, delete, func, text
from sqlalchemy.orm import Session

from storage.matrix_level_tables import (
    drop_all_level_tables,
    level_registry_nonempty,
    load_tree_from_level_tables,
    rebuild_level_tables_from_tree,
)
from storage.models import (
    MATRIX_STRUCT_SCHEMA,
    MatrixNode,
    ActionTemplate,
    ActionTemplateMinimalRequirement,
    ActionTemplateAntipattern,
    ActionTemplateStackRef,
    ActionTemplateExampleRef,
    ActionTemplateLiteratureRef,
    ActionExample,
    UiConfig,
    UiSectionTitle,
    UiSetting,
)
from core.schema import SCHEMA_VERSION
from core.matrix_schema import normalize_level_tags


def _matrix_struct_tables_exist(session: Session) -> bool:
    row = session.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = :sch AND table_name = 'matrix_nodes'"
        ),
        {"sch": MATRIX_STRUCT_SCHEMA},
    ).first()
    return row is not None


def _truncate_matrix_struct(session: Session) -> None:
    """Полная очистка объектов матрицы в схеме matrix_struct перед replace из импорта/CR."""
    if not _matrix_struct_tables_exist(session):
        return
    drop_all_level_tables(session)
    ms = MATRIX_STRUCT_SCHEMA
    session.execute(
        text(
            f"TRUNCATE TABLE "
            f"{ms}.action_template_min_requirements, "
            f"{ms}.action_template_antipatterns, "
            f"{ms}.action_template_stack_refs, "
            f"{ms}.action_template_example_refs, "
            f"{ms}.action_template_literature_refs, "
            f"{ms}.action_templates, "
            f"{ms}.matrix_nodes, "
            f"{ms}.action_examples, "
            f"{ms}.ui_section_titles, "
            f"{ms}.ui_settings, "
            f"{ms}.ui_config "
            f"RESTART IDENTITY CASCADE"
        )
    )


def _empty_unified() -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "domains": [],
        "nodes": [],
        "action_examples": [],
        "literature": {},
        "action_templates": {},
        "ui_config": {},
    }


def load_templates_projection(session: Session) -> Dict[str, Any]:
    templates = session.execute(select(ActionTemplate)).scalars().all()
    out: Dict[str, Any] = {}
    for t in templates:
        item = deepcopy(t.payload or {})
        item.setdefault("name", t.name or "")
        item.setdefault("is_parent", bool(t.is_parent))
        if t.description:
            item.setdefault("description", t.description)
        min_rows = sorted(t.minimal_requirements, key=lambda x: (x.sort_order, x.id))
        anti_rows = sorted(t.antipatterns, key=lambda x: (x.sort_order, x.id))
        stack_rows = sorted(t.stack_refs, key=lambda x: (x.sort_order, x.id))
        ex_rows = sorted(t.example_refs, key=lambda x: (x.sort_order, x.id))
        lit_rows = sorted(t.literature_refs, key=lambda x: (x.sort_order, x.id))
        if min_rows:
            item["minimal_requirements"] = [r.text for r in min_rows]
        if anti_rows:
            item["antipatterns"] = [r.text for r in anti_rows]
        if stack_rows:
            item["stack_refs"] = [r.stack_key for r in stack_rows]
        if ex_rows:
            item["examples_refs"] = [r.example_ref for r in ex_rows]
        if lit_rows:
            item["resource_ids"] = [r.literature_id for r in lit_rows]
        out[t.id] = item
    return out


def load_examples_projection(session: Session) -> List[Dict[str, Any]]:
    examples = session.execute(select(ActionExample).order_by(ActionExample.id)).scalars().all()
    out: List[Dict[str, Any]] = []
    for e in examples:
        item = deepcopy(e.payload or {})
        if e.example_id:
            item.setdefault("id", e.example_id)
        if e.title:
            item.setdefault("title", e.title)
        if e.language:
            item.setdefault("language", e.language)
        if e.code:
            item.setdefault("code", e.code)
        if e.description:
            item.setdefault("description", e.description)
        out.append(item)
    return out


def load_ui_projection(session: Session) -> Dict[str, Any]:
    ui = session.execute(select(UiConfig).where(UiConfig.id == 1)).scalar_one_or_none()
    out: Dict[str, Any] = (deepcopy(ui.payload) if ui and ui.payload else {})
    section_rows = session.execute(select(UiSectionTitle).order_by(UiSectionTitle.id.asc())).scalars().all()
    if section_rows:
        out["section_titles"] = {row.key: row.title for row in section_rows}
    settings_rows = session.execute(select(UiSetting).order_by(UiSetting.id.asc())).scalars().all()
    for row in settings_rows:
        out[row.key] = deepcopy(row.value)
    return out


def load_unified_from_db(session: Session, literature: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    out = _empty_unified()
    out["nodes"] = load_matrix_nodes_nested(session)
    out["domains"] = []
    out["action_templates"] = load_templates_projection(session)
    out["action_examples"] = load_examples_projection(session)
    out["ui_config"] = load_ui_projection(session)
    out["literature"] = literature or {}
    return out


def load_matrix_nodes_nested(session: Session) -> List[Dict[str, Any]]:
    if level_registry_nonempty(session):
        return load_tree_from_level_tables(session)
    cnt = session.execute(select(func.count(MatrixNode.id))).scalar_one()
    if not int(cnt or 0):
        return []
    rows = session.execute(
        select(MatrixNode).order_by(MatrixNode.depth, MatrixNode.sort_order, MatrixNode.id)
    ).scalars().all()
    by_parent: Dict[Optional[int], List[MatrixNode]] = defaultdict(list)
    for r in rows:
        by_parent[r.parent_id].append(r)

    def to_dict(r: MatrixNode) -> Dict[str, Any]:
        kids = by_parent.get(r.id, [])
        ch = [to_dict(c) for c in sorted(kids, key=lambda x: (x.sort_order, x.id))]
        d: Dict[str, Any] = {"name": r.title or "", "children": ch}
        if r.description:
            d["description"] = r.description
        if r.responsible:
            d["responsible"] = r.responsible
        if r.level_sticker:
            d["level_sticker"] = r.level_sticker or ""
        if r.code:
            d["code"] = r.code
        if r.template_id:
            d["template_id"] = r.template_id
        lt = list(r.level_tags or []) if getattr(r, "level_tags", None) else []
        if not lt and r.level_tag:
            lt = normalize_level_tags(r.level_tag)
        if lt:
            d["level_tags"] = lt
        elif r.level_tag:
            d["level_tag"] = r.level_tag
        lv = getattr(r, "leaf_view", None) or {}
        if isinstance(lv, dict) and lv:
            d["leaf_view"] = deepcopy(lv)
        rq = r.review_questions or []
        if isinstance(rq, list) and rq:
            d["review_questions"] = [str(q) for q in rq]
        epk = str(getattr(r, "excel_path_key", None) or "").strip()
        if epk:
            d["excel_path_key"] = epk
        return d

    roots = by_parent.get(None, [])
    return [to_dict(r) for r in sorted(roots, key=lambda x: (x.sort_order, x.id))]


def replace_matrix_nodes(
    session: Session,
    nodes: List[Dict[str, Any]],
    ui_config: Optional[Dict[str, Any]] = None,
) -> None:
    """Полная замена дерева: динамические таблицы уровней + пустой legacy matrix_nodes."""
    session.execute(delete(MatrixNode))
    rebuild_level_tables_from_tree(session, nodes or [], ui_config if isinstance(ui_config, dict) else {})


def replace_templates_in_db(session: Session, templates: Dict[str, Any]) -> None:
    session.execute(delete(ActionTemplateMinimalRequirement))
    session.execute(delete(ActionTemplateAntipattern))
    session.execute(delete(ActionTemplateStackRef))
    session.execute(delete(ActionTemplateExampleRef))
    session.execute(delete(ActionTemplateLiteratureRef))
    session.execute(delete(ActionTemplate))
    for tid, t_payload in (templates or {}).items():
        payload = deepcopy(t_payload or {})
        rec = ActionTemplate(
            id=str(tid),
            name=payload.get("name") or "",
            is_parent=bool(payload.get("is_parent", False)),
            description=payload.get("description") or "",
            payload=payload,
        )
        session.add(rec)
        session.flush()
        for i, value in enumerate(payload.get("minimal_requirements") or []):
            session.add(ActionTemplateMinimalRequirement(template_id=rec.id, sort_order=i, text=str(value)))
        for i, value in enumerate(payload.get("antipatterns") or []):
            session.add(ActionTemplateAntipattern(template_id=rec.id, sort_order=i, text=str(value)))
        for i, value in enumerate(payload.get("stack_refs") or []):
            session.add(ActionTemplateStackRef(template_id=rec.id, sort_order=i, stack_key=str(value)))
        for i, value in enumerate(payload.get("examples_refs") or []):
            session.add(ActionTemplateExampleRef(template_id=rec.id, sort_order=i, example_ref=str(value)))
        for i, value in enumerate(payload.get("resource_ids") or []):
            session.add(ActionTemplateLiteratureRef(template_id=rec.id, sort_order=i, literature_id=str(value)))


def replace_examples_in_db(session: Session, examples: List[Dict[str, Any]]) -> None:
    session.execute(delete(ActionExample))
    for ex in examples or []:
        payload = deepcopy(ex or {})
        session.add(
            ActionExample(
                example_id=(payload.get("id") or None),
                title=payload.get("title") or "",
                language=payload.get("language") or "",
                code=payload.get("code") or "",
                description=payload.get("description") or "",
                payload=payload,
            )
        )


def replace_ui_in_db(session: Session, ui_config: Dict[str, Any]) -> None:
    ui_rec = session.execute(select(UiConfig).where(UiConfig.id == 1)).scalar_one_or_none()
    payload = deepcopy(ui_config or {})
    if not ui_rec:
        ui_rec = UiConfig(id=1, payload=payload)
        session.add(ui_rec)
    else:
        ui_rec.payload = payload
    session.execute(delete(UiSectionTitle))
    for idx, (key, title) in enumerate((payload.get("section_titles") or {}).items()):
        session.add(UiSectionTitle(id=idx + 1, key=str(key), title=str(title)))
    session.execute(delete(UiSetting))
    filtered = {k: v for k, v in payload.items() if k != "section_titles"}
    for idx, (key, value) in enumerate(filtered.items()):
        session.add(UiSetting(id=idx + 1, key=str(key), value=value if isinstance(value, dict) else {"value": value}))


def replace_unified_in_db(session: Session, unified: Dict[str, Any]) -> None:
    _truncate_matrix_struct(session)
    payload = unified or {}
    nodes = payload.get("nodes") if isinstance(payload.get("nodes"), list) else []
    ui_cfg = payload.get("ui_config") if isinstance(payload.get("ui_config"), dict) else {}
    replace_matrix_nodes(session, nodes, ui_cfg)
    replace_templates_in_db(session, payload.get("action_templates") or {})
    replace_examples_in_db(session, payload.get("action_examples") or [])
    replace_ui_in_db(session, payload.get("ui_config") or {})


def list_domains(session: Session) -> List[Dict[str, Any]]:
    """Имена корней и детей первого уровня (для API /api/domains)."""
    nested = load_matrix_nodes_nested(session)
    out = []
    for root in nested:
        if not isinstance(root, dict):
            continue
        ch = root.get("children") or []
        out.append(
            {
                "name": root.get("name", ""),
                "skills": [c.get("name", "") for c in ch if isinstance(c, dict)],
            }
        )
    return out

