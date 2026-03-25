# -*- coding: utf-8 -*-
from __future__ import annotations

from copy import deepcopy
from typing import Dict, Any, Optional, List

from sqlalchemy import select, delete, func
from sqlalchemy.orm import Session

from storage.models import (
    Domain,
    Skill,
    Action,
    Subaction,
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
    ActionReviewQuestion,
    SubactionReviewQuestion,
)
from core.schema import SCHEMA_VERSION


def _empty_unified() -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "domains": [],
        "action_examples": [],
        "literature": {},
        "action_templates": {},
        "ui_config": {},
    }


def _slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in (value or "").strip()).strip("_")


def _domain_code(name: str, idx: int) -> str:
    return _slug(name) or f"domain_{idx}"


def _skill_code(domain_code: str, name: str, idx: int) -> str:
    return f"{domain_code}.{_slug(name) or f'skill_{idx}'}"


def _action_code(skill_code: str, text: str, idx: int) -> str:
    return f"{skill_code}.{_slug(text) or f'action_{idx}'}"


def _subaction_code(action_code: str, text: str, idx: int) -> str:
    return f"{action_code}.{_slug(text) or f'subaction_{idx}'}"


def load_tree_projection(session: Session) -> Dict[str, Any]:
    out = {"domains": []}
    domains = session.execute(select(Domain).order_by(Domain.sort_order, Domain.id)).scalars().all()
    for d in domains:
        d_item = {"code": d.code or "", "name": d.name, "skills": []}
        skills = sorted(d.skills, key=lambda s: (s.sort_order, s.id))
        for s in skills:
            s_item = {"code": s.code or "", "name": s.name, "description": s.description or "", "actions": []}
            actions = sorted(s.actions, key=lambda a: (a.sort_order, a.id))
            for a in actions:
                action_questions = [q.question for q in sorted(a.review_question_rows, key=lambda x: (x.sort_order, x.id))]
                if not action_questions:
                    action_questions = deepcopy(a.review_questions or [])
                a_item = {
                    "code": a.code or "",
                    "text": a.text,
                    "template_id": a.template_id,
                    "review_questions": action_questions,
                }
                if a.level_tag:
                    a_item["level_tag"] = a.level_tag
                subs = sorted(a.subactions, key=lambda x: (x.sort_order, x.id))
                if subs:
                    a_item["subactions"] = []
                    for sub in subs:
                        sub_questions = [q.question for q in sorted(sub.review_question_rows, key=lambda x: (x.sort_order, x.id))]
                        if not sub_questions:
                            sub_questions = deepcopy(sub.review_questions or [])
                        sub_item = {
                            "code": sub.code or "",
                            "text": sub.text,
                            "template_id": sub.template_id,
                            "review_questions": sub_questions,
                        }
                        if sub.level_tag:
                            sub_item["level_tag"] = sub.level_tag
                        a_item["subactions"].append(sub_item)
                s_item["actions"].append(a_item)
            d_item["skills"].append(s_item)
        out["domains"].append(d_item)
    return out


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
    tree = load_tree_projection(session)
    out["domains"] = tree.get("domains") or []
    out["action_templates"] = load_templates_projection(session)
    out["action_examples"] = load_examples_projection(session)
    out["ui_config"] = load_ui_projection(session)
    out["literature"] = literature or {}
    return out


def replace_tree_projection_in_db(session: Session, projection: Dict[str, Any]) -> None:
    domains = (projection or {}).get("domains") or []
    session.execute(delete(Subaction))
    session.execute(delete(SubactionReviewQuestion))
    session.execute(delete(ActionReviewQuestion))
    session.execute(delete(Action))
    session.execute(delete(Skill))
    session.execute(delete(Domain))

    for di, d in enumerate(domains):
        d_rec = Domain(
            name=d.get("name", ""),
            code=d.get("code") or _domain_code(d.get("name") or "", di),
            sort_order=di,
        )
        session.add(d_rec)
        session.flush()
        for si, s in enumerate(d.get("skills") or []):
            s_rec = Skill(
                domain_id=d_rec.id,
                name=s.get("name", ""),
                code=s.get("code") or _skill_code(d_rec.code or "", s.get("name") or "", si),
                description=s.get("description", "") or "",
                sort_order=si,
            )
            session.add(s_rec)
            session.flush()
            for ai, a in enumerate(s.get("actions") or []):
                a_rec = Action(
                    skill_id=s_rec.id,
                    text=a.get("text", ""),
                    code=a.get("code") or _action_code(s_rec.code or "", a.get("text") or "", ai),
                    template_id=a.get("template_id"),
                    level_tag=a.get("level_tag"),
                    review_questions=a.get("review_questions") or [],
                    sort_order=ai,
                )
                session.add(a_rec)
                session.flush()
                for qi, question in enumerate(a.get("review_questions") or []):
                    session.add(
                        ActionReviewQuestion(
                            action_id=a_rec.id,
                            sort_order=qi,
                            question=str(question),
                        )
                    )
                for subi, sub in enumerate(a.get("subactions") or []):
                    sub_rec = Subaction(
                        action_id=a_rec.id,
                        text=sub.get("text", ""),
                        code=sub.get("code") or _subaction_code(a_rec.code or "", sub.get("text") or "", subi),
                        template_id=sub.get("template_id"),
                        level_tag=sub.get("level_tag"),
                        review_questions=sub.get("review_questions") or [],
                        sort_order=subi,
                    )
                    session.add(sub_rec)
                    session.flush()
                    for qi, question in enumerate(sub.get("review_questions") or []):
                        session.add(
                            SubactionReviewQuestion(
                                subaction_id=sub_rec.id,
                                sort_order=qi,
                                question=str(question),
                            )
                        )


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
    payload = unified or {}
    replace_tree_projection_in_db(session, {"domains": payload.get("domains") or []})
    replace_templates_in_db(session, payload.get("action_templates") or {})
    replace_examples_in_db(session, payload.get("action_examples") or [])
    replace_ui_in_db(session, payload.get("ui_config") or {})


def upsert_from_staging_projection(session: Session, staging_projection: Dict[str, Any]) -> None:
    """
    Transitional upsert implementation: currently full replacement of normalized tree.
    """
    replace_tree_projection_in_db(session, staging_projection or {"domains": []})


def list_domains(session: Session) -> List[Dict[str, Any]]:
    domains = session.execute(select(Domain).order_by(Domain.sort_order, Domain.id)).scalars().all()
    out = []
    for d in domains:
        skills = sorted(d.skills, key=lambda s: (s.sort_order, s.id))
        out.append({"name": d.name, "skills": [s.name for s in skills]})
    return out


def count_domains(session: Session) -> int:
    return session.execute(select(func.count(Domain.id))).scalar_one()

