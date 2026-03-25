# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

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
        note="initial revision",
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

