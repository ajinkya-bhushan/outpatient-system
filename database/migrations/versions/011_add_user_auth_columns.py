"""add user auth columns

Revision ID: 011_add_user_auth_columns
Revises: 010_seed_frontend_dummy_data
Create Date: 2026-08-21
"""

from __future__ import annotations

import uuid
from typing import Sequence, Union

import bcrypt
from alembic import op
import sqlalchemy as sa

revision: str = "011_add_user_auth_columns"
down_revision: Union[str, None] = "010_seed_frontend_dummy_data"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def uid(name: str) -> uuid.UUID:
    return uuid.uuid5(NS, f"outpatient-frontend-seed|{name}")


USER_SMITH = uid("user:dr-smith")
USER_ADMIN = uid("user:admin")


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def upgrade() -> None:
    op.add_column("users", sa.Column("provider_id", sa.String(), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(), nullable=True))
    op.add_column("users", sa.Column("display_name", sa.String(), nullable=True))
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    conn = op.get_bind()
    smith_hash = _hash("Smith#2026")
    admin_hash = _hash("Admin#2026")
    placeholder_hash = _hash(str(uuid.uuid4()))

    conn.execute(
        sa.text(
            "UPDATE users SET provider_id = :pid, password_hash = :ph, "
            "display_name = :dn, is_active = true WHERE id = :id"
        ),
        {
            "pid": "DR-SMITH",
            "ph": smith_hash,
            "dn": "Dr. Smith",
            "id": USER_SMITH,
        },
    )
    conn.execute(
        sa.text(
            "UPDATE users SET provider_id = :pid, password_hash = :ph, "
            "display_name = :dn, is_active = true WHERE id = :id"
        ),
        {
            "pid": "ADMIN",
            "ph": admin_hash,
            "dn": "Clinic Admin",
            "id": USER_ADMIN,
        },
    )
    conn.execute(
        sa.text(
            "UPDATE users SET provider_id = 'user-' || id::text, "
            "password_hash = :ph WHERE provider_id IS NULL"
        ),
        {"ph": placeholder_hash},
    )

    op.alter_column("users", "provider_id", existing_type=sa.String(), nullable=False)
    op.alter_column("users", "password_hash", existing_type=sa.String(), nullable=False)
    op.create_unique_constraint("uq_users_provider_id", "users", ["provider_id"])


def downgrade() -> None:
    op.drop_constraint("uq_users_provider_id", "users", type_="unique")
    op.drop_column("users", "is_active")
    op.drop_column("users", "display_name")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "provider_id")
