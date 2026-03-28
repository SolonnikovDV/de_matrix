# -*- coding: utf-8 -*-
"""
Реляционное дерево по уровням: отдельная таблица на каждый depth, имя таблицы из matrix_levels
(латинский идентификатор через core.level_sql_identifier). Реестр — matrix_level_registry.
"""
from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from core.level_sql_identifier import is_safe_dynamic_table_name, qualified_sql_table_name
from core.matrix_schema import (
    action_level_tags_for_json,
    merge_matrix_levels,
    normalize_level_tags,
    normalize_responsible_value,
)
from storage.models import MATRIX_STRUCT_SCHEMA, MatrixLevelRegistry

_COL_DDL = """
  id SERIAL PRIMARY KEY,
  parent_id INTEGER,
  sort_order INTEGER NOT NULL DEFAULT 0,
  node_depth INTEGER NOT NULL DEFAULT 0,
  title TEXT NOT NULL DEFAULT '',
  code VARCHAR(255),
  description TEXT NOT NULL DEFAULT '',
  responsible VARCHAR(255) NOT NULL DEFAULT '',
  level_sticker VARCHAR(16),
  template_id VARCHAR(128),
  level_tag VARCHAR(16),
  level_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
  leaf_view JSONB NOT NULL DEFAULT '{}'::jsonb,
  review_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
  excel_path_key TEXT NOT NULL DEFAULT ''
"""


def _review_questions_for_node(raw: Dict[str, Any]) -> List[str]:
    rq = raw.get("review_questions")
    if isinstance(rq, list):
        return [str(q) for q in rq if str(q).strip()]
    return []


def _node_level_tags(raw: Dict[str, Any]) -> List[str]:
    lt = action_level_tags_for_json(raw)
    if lt:
        return lt
    if raw.get("level_tags"):
        return normalize_level_tags(raw.get("level_tags"))
    if raw.get("level_tag"):
        return normalize_level_tags(raw.get("level_tag"))
    return []


def _max_tree_depth(nodes: List[Dict[str, Any]], depth: int = 0) -> int:
    mx = depth
    for n in nodes or []:
        if not isinstance(n, dict):
            continue
        ch = n.get("children") or []
        if ch:
            mx = max(mx, _max_tree_depth(ch, depth + 1))
        else:
            mx = max(mx, depth)
    return mx


def _levels_meta(ui_config: Dict[str, Any], num_tables: int) -> List[Tuple[int, str, str]]:
    merged = merge_matrix_levels(ui_config or {})
    by_d: Dict[int, Dict[str, Any]] = {int(r["depth"]): r for r in merged if isinstance(r, dict) and "depth" in r}
    out: List[Tuple[int, str, str]] = []
    for d in range(num_tables):
        row = by_d.get(d)
        if row:
            title = str(row.get("title") or "").strip() or f"Слой {d + 1}"
            slug = str(row.get("slug") or "").strip()
        else:
            title = f"Слой {d + 1}"
            slug = ""
        out.append((d, title, slug))
    return out


def drop_all_level_tables(session: Session) -> None:
    """DROP всех зарегистрированных таблиц уровней + очистка реестра."""
    sch = MATRIX_STRUCT_SCHEMA
    rows = session.execute(select(MatrixLevelRegistry.sql_table).order_by(MatrixLevelRegistry.depth.desc())).scalars().all()
    for tbl in rows:
        t = str(tbl or "").strip()
        if not is_safe_dynamic_table_name(sch, t):
            continue
        session.execute(text(f"DROP TABLE IF EXISTS {sch}.{t} CASCADE"))
    session.execute(delete(MatrixLevelRegistry))


def _create_level_table(session: Session, depth: int, sql_table: str, parent_table: Optional[str]) -> None:
    sch = MATRIX_STRUCT_SCHEMA
    if not is_safe_dynamic_table_name(sch, sql_table):
        raise ValueError(f"unsafe table name: {sql_table}")
    inner = _COL_DDL.strip()
    if depth == 0 or not parent_table:
        ddl = f"CREATE TABLE {sch}.{sql_table} (\n{inner}\n)"
    else:
        if not is_safe_dynamic_table_name(sch, parent_table):
            raise ValueError(f"unsafe parent table: {parent_table}")
        inner = inner.replace("parent_id INTEGER,", "parent_id INTEGER NOT NULL,", 1)
        cname = ("fk_" + sql_table + "_p")[:63]
        ddl = (
            f"CREATE TABLE {sch}.{sql_table} (\n{inner},\n"
            f"  CONSTRAINT {cname} FOREIGN KEY (parent_id)\n"
            f"    REFERENCES {sch}.{parent_table}(id) ON DELETE CASCADE\n)"
        )
    session.execute(text(ddl))
    safe_ix = re_safe_index_name(sql_table)
    session.execute(text(f"CREATE INDEX IF NOT EXISTS {safe_ix} ON {sch}.{sql_table}(parent_id)"))


def re_safe_index_name(sql_table: str) -> str:
    """Имя индекса ≤63; только [a-z0-9_]."""
    s = re.sub(r"[^a-z0-9]+", "_", f"ix_{sql_table}_par".lower())
    return s[:63].strip("_") or "ix_lvl_par"


def rebuild_level_tables_from_tree(
    session: Session,
    nodes: List[Dict[str, Any]],
    ui_config: Dict[str, Any],
) -> None:
    """
    Пересоздаёт таблицы уровней и заполняет из generic-дерева nodes.
    Реестр и старые lvl_* должны быть уже сброшены вызывающим кодом.
    """
    drop_all_level_tables(session)
    if not nodes:
        return
    max_d = _max_tree_depth(nodes)
    num_tables = max_d + 1
    if num_tables <= 0:
        return
    meta = _levels_meta(ui_config, num_tables)
    table_names: List[str] = []
    parent_name: Optional[str] = None
    seen: set[str] = set()
    for d, title, slug_hint in meta:
        sql_table = qualified_sql_table_name(MATRIX_STRUCT_SCHEMA, d, title, slug_hint)
        base = sql_table
        n = 0
        while sql_table in seen:
            n += 1
            sql_table = f"{base}_{n}"[:63].rstrip("_")
        seen.add(sql_table)
        table_names.append(sql_table)
        session.add(MatrixLevelRegistry(depth=d, display_name=title, sql_table=sql_table))
        _create_level_table(session, d, sql_table, parent_name)
        parent_name = sql_table
    session.flush()
    _insert_level_tree(session, nodes, 0, None, table_names)


def _insert_level_tree(
    session: Session,
    node_list: List[Dict[str, Any]],
    depth: int,
    parent_id: Optional[int],
    table_names: List[str],
) -> None:
    if depth >= len(table_names):
        return
    tbl = table_names[depth]
    sch = MATRIX_STRUCT_SCHEMA
    for i, raw in enumerate(node_list or []):
        if not isinstance(raw, dict):
            continue
        title = (raw.get("name") or raw.get("text") or "").strip()
        subs = raw.get("children") or []
        if not title and not subs:
            continue
        ltags = _node_level_tags(raw)
        lt0 = ltags[0] if ltags else raw.get("level_tag")
        rq = _review_questions_for_node(raw)
        leaf_v = raw.get("leaf_view") if isinstance(raw.get("leaf_view"), dict) else {}
        sql = text(
            f"""
            INSERT INTO {sch}.{tbl}
            (parent_id, sort_order, node_depth, title, code, description, responsible, level_sticker,
             template_id, level_tag, level_tags, leaf_view, review_questions, excel_path_key)
            VALUES
            (:pid, :so, :nd, :title, :code, :descr, :resp, :lst, :tid, :ltag, CAST(:ltags AS jsonb),
             CAST(:lv AS jsonb), CAST(:rq AS jsonb), :epk)
            RETURNING id
            """
        )
        pid = None if depth == 0 else parent_id
        r = session.execute(
            sql,
            {
                "pid": pid,
                "so": i,
                "nd": depth,
                "title": title or "—",
                "code": (str(raw.get("code") or "").strip() or None),
                "descr": str(raw.get("description") or "").strip(),
                "resp": normalize_responsible_value(raw.get("responsible")),
                "lst": (str(raw.get("level_sticker") or "").strip().lower() or None),
                "tid": raw.get("template_id"),
                "ltag": lt0,
                "ltags": json.dumps(ltags if ltags else []),
                "lv": json.dumps(deepcopy(leaf_v)),
                "rq": json.dumps(rq),
                "epk": str(raw.get("excel_path_key") or "").strip(),
            },
        )
        new_id = r.scalar_one()
        if subs and depth + 1 < len(table_names):
            _insert_level_tree(session, subs, depth + 1, int(new_id), table_names)


def level_registry_nonempty(session: Session) -> bool:
    n = session.execute(select(MatrixLevelRegistry.depth).limit(1)).first()
    return n is not None


def load_tree_from_level_tables(session: Session) -> List[Dict[str, Any]]:
    """Собирает generic nodes из таблиц уровней по реестру."""
    rows = session.execute(select(MatrixLevelRegistry).order_by(MatrixLevelRegistry.depth.asc())).scalars().all()
    if not rows:
        return []
    sch = MATRIX_STRUCT_SCHEMA
    table_names = [r.sql_table for r in rows]
    for t in table_names:
        if not is_safe_dynamic_table_name(sch, t):
            return []

    def load_at(depth: int, parent_id: Optional[int]) -> List[Dict[str, Any]]:
        if depth >= len(table_names):
            return []
        tbl = table_names[depth]
        if parent_id is None:
            q = text(
                f"""
                SELECT id, title, code, description, responsible, level_sticker, template_id, level_tag,
                       level_tags, leaf_view, review_questions, excel_path_key, sort_order
                FROM {sch}.{tbl}
                WHERE parent_id IS NULL
                ORDER BY sort_order, id
                """
            )
            rrows = session.execute(q).mappings().all()
        else:
            q = text(
                f"""
                SELECT id, title, code, description, responsible, level_sticker, template_id, level_tag,
                       level_tags, leaf_view, review_questions, excel_path_key, sort_order
                FROM {sch}.{tbl}
                WHERE parent_id = :pid
                ORDER BY sort_order, id
                """
            )
            rrows = session.execute(q, {"pid": parent_id}).mappings().all()
        out: List[Dict[str, Any]] = []
        for rr in rrows:
            d: Dict[str, Any] = {"name": (rr["title"] or "").strip(), "children": []}
            if rr.get("code"):
                d["code"] = str(rr["code"]).strip()
            if rr.get("description"):
                d["description"] = str(rr["description"]).strip()
            if rr.get("responsible"):
                d["responsible"] = str(rr["responsible"]).strip()
            if rr.get("level_sticker"):
                d["level_sticker"] = str(rr["level_sticker"]).strip().lower()
            if rr.get("template_id"):
                d["template_id"] = rr["template_id"]
            ltgs = rr.get("level_tags")
            if isinstance(ltgs, list) and ltgs:
                d["level_tags"] = list(ltgs)
            elif rr.get("level_tag"):
                d["level_tag"] = rr["level_tag"]
            lv = rr.get("leaf_view")
            if isinstance(lv, dict) and lv:
                d["leaf_view"] = deepcopy(lv)
            rq = rr.get("review_questions")
            if isinstance(rq, list) and rq:
                d["review_questions"] = [str(q) for q in rq]
            epk = str(rr.get("excel_path_key") or "").strip()
            if epk:
                d["excel_path_key"] = epk
            rid = int(rr["id"])
            d["children"] = load_at(depth + 1, rid)
            out.append(d)
        return out

    return load_at(0, None)
