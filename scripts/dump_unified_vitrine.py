#!/usr/bin/env python3
"""
Печать «полной витрины» unified-матрицы из PostgreSQL — те же заголовки и строки,
что у /api/export/unified-table и unified xlsx (build_unified_export_table).

Запуск из корня репозитория (нужен SQLAlchemy 2.x и драйвер из DE_MATRIX_DB_URL):
  DE_MATRIX_DB_URL=postgresql+psycopg://... python3 scripts/dump_unified_vitrine.py

Без Mongo: литература не влияет на таблицу unified — передаём literature={}.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage.db import db_session
from storage.postgres_repo import load_unified_from_db
from core.matrix_schema import effective_matrix_column_schema
from core.excel_unified_export import build_unified_export_table


def main() -> None:
    p = argparse.ArgumentParser(description="Dump unified matrix vitrine from DB")
    p.add_argument("--json", action="store_true", help="Print headers + row_count + first N rows as JSON")
    p.add_argument("--sample-rows", type=int, default=2, help="With --json, include first N data rows")
    args = p.parse_args()

    with db_session() as session:
        u = load_unified_from_db(session, literature={})
        domains = u.get("domains") or []
        nodes = u.get("nodes") or []
        ui = u.get("ui_config") or {}
        schema = effective_matrix_column_schema(ui)
        headers, rows = build_unified_export_table(
            domains, ui, nodes=(nodes or None), include_header_tags=False
        )

    if args.json:
        out = {
            "header_count": len(headers),
            "row_count": len(rows),
            "headers": headers,
            "schema_cols": [str(e.get("col") or "") for e in schema],
            "sample_rows": rows[: max(0, args.sample_rows)],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    print(f"domains: {len(domains)}  node_roots: {len(nodes)}  headers: {len(headers)}  rows: {len(rows)}")
    print("--- headers ---")
    for i, h in enumerate(headers, 1):
        print(f"{i:3}  {h}")


if __name__ == "__main__":
    main()
