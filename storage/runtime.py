# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from typing import Dict, Any, List

from storage.db import db_session
from storage.postgres_repo import load_unified_from_db, replace_unified_in_db, list_domains as list_domains_db
from storage.mongo_repo import load_literature_map


def get_storage_mode() -> str:
    env_mode = (os.environ.get("DE_MATRIX_STORAGE_MODE") or "").strip().lower()
    if env_mode and env_mode != "db":
        raise RuntimeError("Only 'db' storage mode is supported")
    return "db"


def approval_required() -> bool:
    env_val = (os.environ.get("DE_MATRIX_APPROVAL_REQUIRED") or "").strip().lower()
    if env_val:
        return env_val in ("1", "true", "yes")
    return True


def load_unified() -> Dict[str, Any]:
    with db_session() as session:
        literature = load_literature_map()
        return load_unified_from_db(session, literature=literature)


def save_unified(unified: Dict[str, Any]) -> None:
    with db_session() as session:
        replace_unified_in_db(session, unified or {})


def load_literature() -> Dict[str, Any]:
    return load_literature_map()


def list_domains() -> List[Dict[str, Any]]:
    with db_session() as session:
        return list_domains_db(session)

