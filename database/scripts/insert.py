"""Insert rows through SQLAlchemy."""

from __future__ import annotations

from typing import Any

from sqlalchemy import insert as sa_insert

from scripts.connect import get_session, require_table, row_to_dict


def insert(name: str, row: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    table = require_table(name)
    rows = row if isinstance(row, list) else [row]
    stmt = sa_insert(table).values(rows).returning(*table.c)
    with get_session() as session:
        result = session.execute(stmt)
        session.commit()
        return [row_to_dict(mapping) for mapping in result.mappings()]
