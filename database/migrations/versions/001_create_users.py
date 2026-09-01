"""create users table

Revision ID: 001_create_users
Revises:
Create Date: 2026-08-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_create_users"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("role", sa.String(), nullable=False),
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE users "
        "TO anon, authenticated, service_role"
    )


def downgrade() -> None:
    op.drop_table("users")
