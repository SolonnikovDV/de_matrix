# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from typing import Dict, Any, List, Optional

from pymongo import MongoClient


def get_mongo_uri() -> str:
    return os.environ.get("DE_MATRIX_MONGO_URI", "mongodb://localhost:27017")


def get_mongo_db_name() -> str:
    return os.environ.get("DE_MATRIX_MONGO_DB", "de_matrix")


def mongo_db():
    client = MongoClient(get_mongo_uri())
    return client[get_mongo_db_name()]


def load_literature_map() -> Dict[str, Dict[str, Any]]:
    db = mongo_db()
    out: Dict[str, Dict[str, Any]] = {}
    for doc in db.literature_items.find({}, {"_id": 0}):
        lit_id = str(doc.get("id") or "")
        if lit_id:
            out[lit_id] = {k: v for k, v in doc.items() if k != "id"}
    return out


def list_literature_items() -> List[Dict[str, Any]]:
    db = mongo_db()
    return list(db.literature_items.find({}, {"_id": 0}))


def upsert_literature_item(lit_id: str, payload: Dict[str, Any]) -> None:
    db = mongo_db()
    data = {"id": lit_id, **(payload or {})}
    db.literature_items.update_one({"id": lit_id}, {"$set": data}, upsert=True)


def delete_literature_item(lit_id: str) -> None:
    db = mongo_db()
    db.literature_items.delete_one({"id": lit_id})
    db.literature_files.delete_many({"lit_id": lit_id})


def add_literature_file(lit_id: str, filename: str, local_path: str, content_type: Optional[str] = None) -> None:
    db = mongo_db()
    db.literature_files.insert_one(
        {
            "lit_id": lit_id,
            "filename": filename,
            "local_path": local_path,
            "content_type": content_type or "",
        }
    )

