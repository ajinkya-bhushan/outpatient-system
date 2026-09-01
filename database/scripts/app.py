"""FastAPI endpoints for migrate / insert / update / delete against Postgres."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import inspect

from scripts.connect import get_engine, ping
from scripts.delete import delete
from scripts.insert import insert
from scripts.migrate import upgrade
from scripts.update import update

from models import Base  # noqa: E402

app = FastAPI(
    title="Outpatient Database API",
    description=(
        "Schema via Alembic (`POST /migrate` or `uv run alembic upgrade head`). "
        "Rows via SQLAlchemy against DATABASE_URL."
    ),
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class InsertBody(BaseModel):
    row: dict[str, Any] | None = None
    rows: list[dict[str, Any]] | None = None


class MutationBody(BaseModel):
    values: dict[str, Any] | None = None
    filters: dict[str, Any] = Field(default_factory=dict)


def _run(fn, *args, **kwargs):
    try:
        return {"data": fn(*args, **kwargs)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict[str, object]:
    ping()
    inspector = inspect(get_engine())
    return {"status": "ok", "tables": inspector.get_table_names()}


@app.post("/migrate")
def migrate_endpoint() -> dict[str, object]:
    """Create tables by applying Alembic migrations to head."""
    try:
        target = upgrade("head")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "ok", "target": target, "tables": list(Base.metadata.tables)}


@app.post("/insert/{table_name}")
def insert_endpoint(table_name: str, body: InsertBody) -> dict[str, Any]:
    payload = body.row if body.row is not None else body.rows
    if payload is None:
        raise HTTPException(status_code=400, detail="Provide `row` or `rows`")
    return _run(insert, table_name, payload)


@app.patch("/update/{table_name}")
@app.patch("/update/{table_name}/{row_id}")
def update_endpoint(
    table_name: str, body: MutationBody, row_id: str | None = None
) -> dict[str, Any]:
    if not body.values:
        raise HTTPException(status_code=400, detail="Provide `values`")
    return _run(update, table_name, body.values, row_id, body.filters)


@app.delete("/delete/{table_name}")
@app.delete("/delete/{table_name}/{row_id}")
def delete_endpoint(
    table_name: str, row_id: str | None = None, body: MutationBody | None = None
) -> dict[str, Any]:
    filters = body.filters if body else {}
    return _run(delete, table_name, row_id, filters)
