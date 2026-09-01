"""Delete rows through SQLAlchemy."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete as sa_delete

from scripts.connect import apply_filters, get_session, require_table, row_to_dict


def delete(
    name: str,
    row_id: str | None = None,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    table = require_table(name)
    stmt = apply_filters(sa_delete(table), table, row_id, filters)
    stmt = stmt.returning(*table.c)
    with get_session() as session:
        result = session.execute(stmt)
        session.commit()
        return [row_to_dict(mapping) for mapping in result.mappings()]
