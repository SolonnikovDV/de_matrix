# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from storage.models import ChangeRequest, ChangeRevision, ApprovalDecision


def utcnow():
    return datetime.now(timezone.utc)


VALID_STATUSES = {"draft", "submitted", "in_review", "approved", "rejected", "applied"}


def create_change_request(
    session: Session,
    title: str,
    merge_mode: str,
    payload: Dict[str, Any],
    staging_batch_id: Optional[int] = None,
    created_by: str = "system",
    target_domain: Optional[str] = None,
    target_skill: Optional[str] = None,
    initial_note: str = "initial revision",
) -> ChangeRequest:
    cr = ChangeRequest(
        title=title or "Change request",
        status="draft",
        merge_mode=merge_mode or "append",
        target_domain=target_domain,
        target_skill=target_skill,
        created_by=created_by or "system",
        created_at=utcnow(),
        updated_at=utcnow(),
        applied=False,
    )
    session.add(cr)
    session.flush()
    rev = ChangeRevision(
        change_request_id=cr.id,
        staging_batch_id=staging_batch_id,
        revision_no=1,
        payload=payload or {},
        created_by=created_by or "system",
        created_at=utcnow(),
        note=(initial_note or "initial revision"),
    )
    session.add(rev)
    return cr


def add_revision(
    session: Session,
    change_id: int,
    payload: Dict[str, Any],
    actor: str,
    note: str = "",
    staging_batch_id: Optional[int] = None,
) -> ChangeRevision:
    max_rev = (
        session.execute(
            select(ChangeRevision.revision_no).where(ChangeRevision.change_request_id == change_id).order_by(ChangeRevision.revision_no.desc())
        ).scalars().first()
        or 0
    )
    rev = ChangeRevision(
        change_request_id=change_id,
        staging_batch_id=staging_batch_id,
        revision_no=max_rev + 1,
        payload=payload or {},
        created_by=actor or "system",
        created_at=utcnow(),
        note=note or "",
    )
    session.add(rev)
    return rev


def set_status(session: Session, change_id: int, status: str, actor: str, comment: str = "") -> Optional[ChangeRequest]:
    if status not in VALID_STATUSES:
        return None
    cr = session.get(ChangeRequest, change_id)
    if not cr:
        return None
    cr.status = status
    cr.updated_at = utcnow()
    session.add(
        ApprovalDecision(
            change_request_id=change_id,
            decision=status,
            comment=comment or "",
            actor=actor or "system",
            created_at=utcnow(),
        )
    )
    return cr


def _hint_set(
    hints: Dict[str, Dict[str, Any]],
    path: str,
    actor: str,
    change_id: int,
    created_at: str,
) -> None:
    if path in hints:
        return
    hints[path] = {
        "actor": actor,
        "change_id": change_id,
        "at": created_at or "",
    }


def _merge_leaf_hints_from_nodes_tree(
    hints: Dict[str, Dict[str, Any]],
    nodes: Any,
    actor: str,
    change_id: int,
    created_at: str,
) -> None:
    if not isinstance(nodes, list):
        return

    def walk(nlist: List[Dict[str, Any]], prefix: List[int]) -> None:
        for i, n in enumerate(nlist):
            if not isinstance(n, dict):
                continue
            p = prefix + [i]
            ps = "/".join(str(x) for x in p)
            _hint_set(hints, ps, actor, change_id, created_at)
            ch = n.get("children") or []
            if ch:
                walk(ch, p)

    walk(nodes, [])


def _merge_leaf_hints_from_domains_payload(
    hints: Dict[str, Dict[str, Any]],
    domains: Any,
    actor: str,
    change_id: int,
    created_at: str,
) -> None:
    if not isinstance(domains, list):
        return
    for di, d in enumerate(domains):
        if not isinstance(d, dict):
            continue
        _hint_set(hints, str(di), actor, change_id, created_at)
        skills = d.get("skills") or []
        if not isinstance(skills, list):
            continue
        for si, s in enumerate(skills):
            if not isinstance(s, dict):
                continue
            _hint_set(hints, f"{di}/{si}", actor, change_id, created_at)
            actions = s.get("actions") or []
            if not isinstance(actions, list):
                continue
            for ai, a in enumerate(actions):
                if not isinstance(a, dict):
                    continue
                subs = a.get("subactions") or []
                if isinstance(subs, list) and subs:
                    for subi, sub in enumerate(subs):
                        if isinstance(sub, dict):
                            _hint_set(hints, f"{di}/{si}/{ai}/{subi}", actor, change_id, created_at)
                else:
                    _hint_set(hints, f"{di}/{si}/{ai}", actor, change_id, created_at)


def leaf_path_hints_from_applied_changes(
    session: Session,
    live_nodes: Optional[List[Dict[str, Any]]] = None,
    *,
    limit_crs: int = 80,
) -> Dict[str, Dict[str, Any]]:
    """
    Для каждого path (индексы как в /leaf/...) — автор последней применённой ревизии CR.
    Берётся proposed_snapshot.nodes из payload ревизии; для старых CR — domains в snapshot.
    """
    hints: Dict[str, Dict[str, Any]] = {}
    rows = (
        session.execute(
            select(ChangeRequest)
            .where(ChangeRequest.applied.is_(True))
            .order_by(ChangeRequest.updated_at.desc())
            .limit(int(limit_crs))
        )
        .scalars()
        .all()
    )
    for cr in rows:
        rev = (
            session.execute(
                select(ChangeRevision)
                .where(ChangeRevision.change_request_id == cr.id)
                .order_by(ChangeRevision.revision_no.desc())
            )
            .scalars()
            .first()
        )
        if not rev or not isinstance(rev.payload, dict):
            continue
        actor = (rev.created_by or cr.created_by or "system").strip() or "system"
        at = rev.created_at.isoformat() if rev.created_at else ""
        proposed = rev.payload.get("proposed_snapshot")
        if not isinstance(proposed, dict):
            proposed = rev.payload
        nodes_payload = proposed.get("nodes") if isinstance(proposed, dict) else None
        if isinstance(nodes_payload, list) and nodes_payload:
            _merge_leaf_hints_from_nodes_tree(hints, nodes_payload, actor, int(cr.id), at)
        else:
            domains = proposed.get("domains") if isinstance(proposed, dict) else None
            _merge_leaf_hints_from_domains_payload(hints, domains, actor, int(cr.id), at)
    return hints


def get_latest_payload(session: Session, change_id: int) -> Optional[Dict[str, Any]]:
    rev = (
        session.execute(
            select(ChangeRevision).where(ChangeRevision.change_request_id == change_id).order_by(ChangeRevision.revision_no.desc())
        ).scalars().first()
    )
    return (rev.payload if rev else None) or None


def list_change_requests(session: Session) -> List[Dict[str, Any]]:
    rows = session.execute(select(ChangeRequest).order_by(ChangeRequest.updated_at.desc(), ChangeRequest.id.desc())).scalars().all()
    out = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "title": r.title,
                "status": r.status,
                "merge_mode": r.merge_mode,
                "target_domain": r.target_domain,
                "target_skill": r.target_skill,
                "created_by": r.created_by,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                "applied": bool(r.applied),
            }
        )
    return out


def get_change_request_details(session: Session, change_id: int) -> Optional[Dict[str, Any]]:
    cr = session.get(ChangeRequest, change_id)
    if not cr:
        return None
    revisions = (
        session.execute(
            select(ChangeRevision).where(ChangeRevision.change_request_id == change_id).order_by(ChangeRevision.revision_no.asc())
        ).scalars().all()
    )
    decisions = (
        session.execute(
            select(ApprovalDecision).where(ApprovalDecision.change_request_id == change_id).order_by(ApprovalDecision.id.asc())
        ).scalars().all()
    )
    return {
        "id": cr.id,
        "title": cr.title,
        "status": cr.status,
        "merge_mode": cr.merge_mode,
        "target_domain": cr.target_domain,
        "target_skill": cr.target_skill,
        "created_by": cr.created_by,
        "created_at": cr.created_at.isoformat() if cr.created_at else None,
        "updated_at": cr.updated_at.isoformat() if cr.updated_at else None,
        "applied": bool(cr.applied),
        "revisions": [
            {
                "id": rev.id,
                "revision_no": rev.revision_no,
                "staging_batch_id": rev.staging_batch_id,
                "payload": rev.payload,
                "note": rev.note,
                "created_by": rev.created_by,
                "created_at": rev.created_at.isoformat() if rev.created_at else None,
            }
            for rev in revisions
        ],
        "decisions": [
            {
                "id": d.id,
                "decision": d.decision,
                "comment": d.comment,
                "actor": d.actor,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in decisions
        ],
    }

