"""SQLAlchemy engine and session against DATABASE_URL."""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT.parent / ".env")
load_dotenv(ROOT / ".env", override=True)

from models import Base  # noqa: E402


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("Set DATABASE_URL")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    if "sslmode=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    # Transaction pooler (6543) cannot hold pooled sessions.
    return create_engine(get_database_url(), pool_pre_ping=True, poolclass=NullPool)


def get_session() -> Session:
    return Session(get_engine())


def require_table(name: str):
    tables = Base.metadata.tables
    if name not in tables:
        raise ValueError(f"Unknown table '{name}'. Allowed: {', '.join(tables)}")
    return tables[name]


def ping() -> None:
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))


def row_to_dict(mapping: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in dict(mapping).items():
        if isinstance(value, uuid.UUID):
            out[key] = str(value)
        elif isinstance(value, datetime):
            out[key] = value.isoformat()
        else:
            out[key] = value
    return out


def apply_filters(stmt: Any, table: Any, row_id: str | None, filters: dict[str, Any] | None):
    if row_id is not None:
        stmt = stmt.where(table.c.id == row_id)
    for column, value in (filters or {}).items():
        if column not in table.c:
            raise ValueError(f"Unknown column '{column}' on {table.name}")
        stmt = stmt.where(table.c[column] == value)
    if row_id is None and not filters:
        raise ValueError("Provide an id or at least one filter")
    return stmt
