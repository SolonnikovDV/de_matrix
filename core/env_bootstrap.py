# -*- coding: utf-8 -*-
"""Load .env and normalize connection settings for host vs Docker runtime."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


def _parse_env_lines(lines: Iterable[str]) -> None:
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_dotenv_file(path: Path) -> None:
    if not path.is_file():
        return
    _parse_env_lines(path.read_text(encoding="utf-8").splitlines())


def _running_in_docker() -> bool:
    return Path("/.dockerenv").exists()


def _rewrite_service_urls_for_host() -> None:
    """When app.py runs on host, map docker-compose service names to localhost ports."""
    if _running_in_docker():
        return

    pg_port = (os.environ.get("DE_MATRIX_POSTGRES_PORT") or "15432").strip()
    mongo_port = (os.environ.get("DE_MATRIX_MONGO_PORT") or "27018").strip()
    smtp_port = (os.environ.get("DE_MATRIX_SMTP_PORT") or "11025").strip()

    db_url = (os.environ.get("DE_MATRIX_DB_URL") or "").strip()
    if not db_url:
        os.environ["DE_MATRIX_DB_URL"] = (
            f"postgresql+psycopg://dematrix:dematrix@127.0.0.1:{pg_port}/dematrix"
        )
    elif "@postgres:" in db_url or "@postgres/" in db_url:
        os.environ["DE_MATRIX_DB_URL"] = (
            f"postgresql+psycopg://dematrix:dematrix@127.0.0.1:{pg_port}/dematrix"
        )

    mongo_uri = (os.environ.get("DE_MATRIX_MONGO_URI") or "").strip()
    if not mongo_uri:
        os.environ["DE_MATRIX_MONGO_URI"] = f"mongodb://127.0.0.1:{mongo_port}"
    elif "://mongo:" in mongo_uri or "://mongo/" in mongo_uri:
        os.environ["DE_MATRIX_MONGO_URI"] = f"mongodb://127.0.0.1:{mongo_port}"

    smtp_host = (os.environ.get("DE_MATRIX_SMTP_HOST") or "").strip()
    if not smtp_host or smtp_host == "smtp":
        os.environ["DE_MATRIX_SMTP_HOST"] = "127.0.0.1"
        if not (os.environ.get("DE_MATRIX_SMTP_PORT") or "").strip():
            os.environ["DE_MATRIX_SMTP_PORT"] = smtp_port


def bootstrap_project_env(project_root: Path) -> None:
    root = project_root.resolve()
    load_dotenv_file(root / ".env")
    load_dotenv_file(root / ".env.local")
    _rewrite_service_urls_for_host()
