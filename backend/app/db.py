"""SQLAlchemy engine and session against DATABASE_URL."""

from __future__ import annotations

import importlib.util
import os
import sys
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import settings

_WORKSPACE = Path(__file__).resolve().parents[2]
_MODELS_PATH = _WORKSPACE / "database" / "models.py"
_spec = importlib.util.spec_from_file_location("outpatient_db_models", _MODELS_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Cannot load database models from {_MODELS_PATH}")
_models = importlib.util.module_from_spec(_spec)
sys.modules["outpatient_db_models"] = _models
_spec.loader.exec_module(_models)
User = _models.User
Encounter = _models.Encounter
SoapNote = _models.SoapNote
SoapNoteSection = _models.SoapNoteSection


def get_database_url() -> str:
    url = (settings.DATABASE_URL or os.environ.get("DATABASE_URL", "")).strip()
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
    return create_engine(get_database_url(), pool_pre_ping=True, poolclass=NullPool)


def get_session() -> Session:
    return Session(get_engine())
