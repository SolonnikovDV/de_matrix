#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage.db import db_session
from sqlalchemy import select, func

from core.diff_engine import _count_tree_nodes
from storage.postgres_repo import load_unified_from_db
from storage.mongo_repo import load_literature_map
from storage.models import StagingBatch


def main():
    with db_session() as session:
        unified = load_unified_from_db(session, literature=load_literature_map())
        staging_count = session.execute(select(func.count(StagingBatch.id))).scalar_one()
    nodes = unified.get("nodes") or []
    templates = unified.get("action_templates") or {}
    literature = unified.get("literature") or {}
    print(
        f"DB smoke ok: tree_nodes={_count_tree_nodes(nodes)} "
        f"roots={len(nodes)} "
        f"templates={len(templates)} literature={len(literature)} "
        f"staging_batches={staging_count}"
    )


if __name__ == "__main__":
    main()
