"""Apply Alembic migrations (create / alter tables)."""

from __future__ import annotations

from alembic import command
from alembic.config import Config

from scripts.connect import ROOT, get_database_url


def upgrade(revision: str = "head") -> str:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", get_database_url())
    command.upgrade(cfg, revision)
    return revision
