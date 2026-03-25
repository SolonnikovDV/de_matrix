# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session


def get_database_url() -> str:
    return os.environ.get("DE_MATRIX_DB_URL", "postgresql+psycopg://dematrix:dematrix@localhost:5432/dematrix")


ENGINE = create_engine(get_database_url(), future=True)
SessionLocal = sessionmaker(
    bind=ENGINE,
    autoflush=False,
    autocommit=False,
    future=True,
    # Keep loaded scalar attributes available after commit/close.
    # This avoids DetachedInstanceError in auth/session flows where
    # user attributes are read right after helper functions return.
    expire_on_commit=False,
)


@contextmanager
def db_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

