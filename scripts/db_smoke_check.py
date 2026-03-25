#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage.db import db_session
from sqlalchemy import select, func

from storage.postgres_repo import load_unified_from_db, load_tree_projection
from storage.mongo_repo import load_literature_map
from storage.models import StagingBatch


def main():
    with db_session() as session:
        unified = load_unified_from_db(session, literature=load_literature_map())
        projection = load_tree_projection(session)
        staging_count = session.execute(select(func.count(StagingBatch.id))).scalar_one()
    domains = unified.get("domains") or []
    projection_domains = projection.get("domains") or []
    templates = unified.get("action_templates") or {}
    literature = unified.get("literature") or {}
    print(
        f"DB smoke ok: domains={len(domains)} "
        f"projection_domains={len(projection_domains)} "
        f"templates={len(templates)} literature={len(literature)} "
        f"staging_batches={staging_count}"
    )


if __name__ == "__main__":
    main()
