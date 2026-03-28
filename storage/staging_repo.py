# -*- coding: utf-8 -*-
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional

from sqlalchemy import delete
from sqlalchemy.orm import Session

from core.loaders import META_KEYS, _normalize_unified
from storage.models import StagingBatch


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
    """Сохраняет нормализованный unified-снимок в payload (дерево только в nodes)."""
    norm = _normalize_unified(deepcopy(payload or {}))
    slim: Dict[str, Any] = {
        "schema_version": norm.get("schema_version"),
        "nodes": norm.get("nodes") or [],
        "domains": [],
    }
    for k in META_KEYS:
        if k in norm:
            slim[k] = deepcopy(norm[k])
    batch = StagingBatch(
        source_filename=source_filename or "",
        merge_mode=merge_mode or "append",
        created_by=created_by or "system",
        target_domain=target_domain,
        target_skill=target_skill,
        payload=slim,
        status="parsed",
    )
    session.add(batch)
    session.flush()
    return batch


def load_staging_tree_projection(session: Session, batch_id: int) -> Dict[str, Any]:
    """Снимок дерева из JSON payload батча (без реляционного staging)."""
    batch = session.get(StagingBatch, batch_id)
    if not batch or not isinstance(batch.payload, dict):
        return {"nodes": []}
    nodes = batch.payload.get("nodes")
    return {"nodes": deepcopy(nodes) if isinstance(nodes, list) else []}


def delete_staging_batch(session: Session, batch_id: int) -> None:
    session.execute(delete(StagingBatch).where(StagingBatch.id == batch_id))
