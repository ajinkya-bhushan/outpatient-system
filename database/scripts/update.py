"""Update rows through SQLAlchemy."""

from __future__ import annotations

from typing import Any

from sqlalchemy import update as sa_update

from scripts.connect import apply_filters, get_session, require_table, row_to_dict


def update(
    name: str,
    values: dict[str, Any],
    row_id: str | None = None,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not values:
        raise ValueError("Update values cannot be empty")
    table = require_table(name)
    stmt = apply_filters(sa_update(table).values(**values), table, row_id, filters)
    stmt = stmt.returning(*table.c)
    with get_session() as session:
        result = session.execute(stmt)
        session.commit()
        return [row_to_dict(mapping) for mapping in result.mappings()]
