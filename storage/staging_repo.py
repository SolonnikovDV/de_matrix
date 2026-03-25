# -*- coding: utf-8 -*-
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from storage.models import (
    StagingBatch,
    StagingDomain,
    StagingSkill,
    StagingAction,
    StagingSubaction,
    StagingActionReviewQuestion,
    StagingSubactionReviewQuestion,
)


def _slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in (value or "").strip()).strip("_")


def _domain_code(domain: Dict[str, Any], idx: int) -> str:
    return _slug(domain.get("name") or "") or f"domain_{idx}"


def _skill_code(domain_code: str, skill: Dict[str, Any], idx: int) -> str:
    raw = _slug(skill.get("name") or "") or f"skill_{idx}"
    return f"{domain_code}.{raw}"


def _action_code(skill_code: str, action: Dict[str, Any], idx: int) -> str:
    raw = _slug(action.get("text") or "") or f"action_{idx}"
    return f"{skill_code}.{raw}"


def _subaction_code(action_code: str, sub: Dict[str, Any], idx: int) -> str:
    raw = _slug(sub.get("text") or "") or f"subaction_{idx}"
    return f"{action_code}.{raw}"


def create_staging_batch(
    session: Session,
    *,
    source_filename: str,
    merge_mode: str,
    created_by: str,
    payload: Dict[str, Any],
    target_domain: Optional[str] = None,
    target_skill: Optional[str] = None,
) -> StagingBatch:
    batch = StagingBatch(
        source_filename=source_filename or "",
        merge_mode=merge_mode or "append",
        created_by=created_by or "system",
        target_domain=target_domain,
        target_skill=target_skill,
        payload=deepcopy(payload or {}),
        status="parsed",
    )
    session.add(batch)
    session.flush()

    domains = (payload or {}).get("domains") or []
    for di, domain in enumerate(domains):
        d_code = _domain_code(domain, di)
        session.add(
            StagingDomain(
                batch_id=batch.id,
                code=d_code,
                name=domain.get("name") or "",
                sort_order=di,
            )
        )
        for si, skill in enumerate(domain.get("skills") or []):
            s_code = _skill_code(d_code, skill, si)
            session.add(
                StagingSkill(
                    batch_id=batch.id,
                    domain_code=d_code,
                    code=s_code,
                    name=skill.get("name") or "",
                    description=skill.get("description") or "",
                    sort_order=si,
                )
            )
            for ai, action in enumerate(skill.get("actions") or []):
                a_code = _action_code(s_code, action, ai)
                session.add(
                    StagingAction(
                        batch_id=batch.id,
                        skill_code=s_code,
                        code=a_code,
                        text=action.get("text") or "",
                        template_id=action.get("template_id"),
                        level_tag=action.get("level_tag"),
                        sort_order=ai,
                    )
                )
                for qi, question in enumerate(action.get("review_questions") or []):
                    session.add(
                        StagingActionReviewQuestion(
                            batch_id=batch.id,
                            action_code=a_code,
                            sort_order=qi,
                            question=str(question),
                        )
                    )
                for subi, sub in enumerate(action.get("subactions") or []):
                    sub_code = _subaction_code(a_code, sub, subi)
                    session.add(
                        StagingSubaction(
                            batch_id=batch.id,
                            action_code=a_code,
                            code=sub_code,
                            text=sub.get("text") or "",
                            template_id=sub.get("template_id"),
                            level_tag=sub.get("level_tag"),
                            sort_order=subi,
                        )
                    )
                    for qi, question in enumerate(sub.get("review_questions") or []):
                        session.add(
                            StagingSubactionReviewQuestion(
                                batch_id=batch.id,
                                subaction_code=sub_code,
                                sort_order=qi,
                                question=str(question),
                            )
                        )

    return batch


def load_staging_tree_projection(session: Session, batch_id: int) -> Dict[str, Any]:
    domains_rows = session.execute(
        select(StagingDomain).where(StagingDomain.batch_id == batch_id).order_by(StagingDomain.sort_order, StagingDomain.id)
    ).scalars().all()
    skills_rows = session.execute(
        select(StagingSkill).where(StagingSkill.batch_id == batch_id).order_by(StagingSkill.sort_order, StagingSkill.id)
    ).scalars().all()
    actions_rows = session.execute(
        select(StagingAction).where(StagingAction.batch_id == batch_id).order_by(StagingAction.sort_order, StagingAction.id)
    ).scalars().all()
    sub_rows = session.execute(
        select(StagingSubaction).where(StagingSubaction.batch_id == batch_id).order_by(StagingSubaction.sort_order, StagingSubaction.id)
    ).scalars().all()
    action_q_rows = session.execute(
        select(StagingActionReviewQuestion)
        .where(StagingActionReviewQuestion.batch_id == batch_id)
        .order_by(StagingActionReviewQuestion.sort_order, StagingActionReviewQuestion.id)
    ).scalars().all()
    sub_q_rows = session.execute(
        select(StagingSubactionReviewQuestion)
        .where(StagingSubactionReviewQuestion.batch_id == batch_id)
        .order_by(StagingSubactionReviewQuestion.sort_order, StagingSubactionReviewQuestion.id)
    ).scalars().all()

    action_q_map: Dict[str, list[str]] = {}
    for row in action_q_rows:
        action_q_map.setdefault(row.action_code, []).append(row.question)
    sub_q_map: Dict[str, list[str]] = {}
    for row in sub_q_rows:
        sub_q_map.setdefault(row.subaction_code, []).append(row.question)

    action_map: Dict[str, list[dict[str, Any]]] = {}
    for row in actions_rows:
        item: Dict[str, Any] = {
            "code": row.code,
            "text": row.text,
            "template_id": row.template_id,
            "level_tag": row.level_tag,
            "review_questions": action_q_map.get(row.code, []),
            "subactions": [],
        }
        action_map.setdefault(row.skill_code, []).append(item)

    sub_map: Dict[str, list[dict[str, Any]]] = {}
    for row in sub_rows:
        sub_map.setdefault(row.action_code, []).append(
            {
                "code": row.code,
                "text": row.text,
                "template_id": row.template_id,
                "level_tag": row.level_tag,
                "review_questions": sub_q_map.get(row.code, []),
            }
        )

    for skill_actions in action_map.values():
        for action in skill_actions:
            action["subactions"] = sub_map.get(action["code"], [])

    skill_map: Dict[str, list[dict[str, Any]]] = {}
    for row in skills_rows:
        skill_map.setdefault(row.domain_code, []).append(
            {
                "code": row.code,
                "name": row.name,
                "description": row.description or "",
                "actions": action_map.get(row.code, []),
            }
        )

    domains: list[dict[str, Any]] = []
    for row in domains_rows:
        domains.append(
            {
                "code": row.code,
                "name": row.name,
                "skills": skill_map.get(row.code, []),
            }
        )
    return {"domains": domains}


def delete_staging_batch(session: Session, batch_id: int) -> None:
    session.execute(delete(StagingBatch).where(StagingBatch.id == batch_id))
