#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.loaders import load_unified_source
from storage.db import db_session
from storage.postgres_repo import replace_unified_in_db, load_unified_from_db, load_tree_projection
from storage.mongo_repo import upsert_literature_item, load_literature_map


def _build_report(label: str, unified: dict) -> dict:
    domains = unified.get("domains") or []
    skills = sum(len(d.get("skills") or []) for d in domains)
    actions = sum(
        len(s.get("actions") or [])
        for d in domains
        for s in (d.get("skills") or [])
    )
    subactions = sum(
        len(a.get("subactions") or [])
        for d in domains
        for s in (d.get("skills") or [])
        for a in (s.get("actions") or [])
    )
    return {
        "label": label,
        "domains": len(domains),
        "skills": skills,
        "actions": actions,
        "subactions": subactions,
        "templates": len(unified.get("action_templates") or {}),
        "examples": len(unified.get("action_examples") or []),
        "literature": len(unified.get("literature") or {}),
    }


def _build_tree_projection_report(projection: dict) -> dict:
    domains = projection.get("domains") or []
    skills = sum(len(d.get("skills") or []) for d in domains)
    actions = sum(
        len(s.get("actions") or [])
        for d in domains
        for s in (d.get("skills") or [])
    )
    subactions = sum(
        len(a.get("subactions") or [])
        for d in domains
        for s in (d.get("skills") or [])
        for a in (s.get("actions") or [])
    )
    return {
        "domains": len(domains),
        "skills": skills,
        "actions": actions,
        "subactions": subactions,
    }


def main():
    parser = argparse.ArgumentParser(description="Migrate unified source file to PostgreSQL + MongoDB")
    parser.add_argument("--source", required=True, help="Path to source json/yaml")
    parser.add_argument("--dry-run", action="store_true", help="Only print migration report without writes")
    parser.add_argument("--report-json", help="Optional path to save report as JSON")
    args = parser.parse_args()

    source_path = Path(args.source)
    unified = load_unified_source(str(source_path))
    report = {"before": _build_report("source", unified)}

    if not args.dry_run:
        with db_session() as session:
            replace_unified_in_db(session, unified)

        for lit_id, item in (unified.get("literature") or {}).items():
            upsert_literature_item(str(lit_id), item or {})

        with db_session() as session:
            actual = load_unified_from_db(session, literature=load_literature_map())
            projection = load_tree_projection(session)
        report["after"] = _build_report("db", actual)
        report["projection_after"] = _build_tree_projection_report(projection)
        report["idempotent_hint"] = "Script is idempotent because replace_unified_in_db performs full replacement."
        report["counts_match"] = report["before"] == report["after"]
    else:
        report["after"] = None
        report["projection_after"] = None
        report["idempotent_hint"] = "Dry-run mode: no writes performed."
        report["counts_match"] = None

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report_json:
        Path(args.report_json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

