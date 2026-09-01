"""create recordings table

Revision ID: 004_create_recordings
Revises: 003_create_encounters
Create Date: 2026-08-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004_create_recordings"
down_revision: Union[str, None] = "003_create_encounters"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recordings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("s3_key", sa.String(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["encounter_id"],
            ["encounters.id"],
            name="fk_recordings_encounter_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_recordings_encounter_id", "recordings", ["encounter_id"])
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE recordings "
        "TO anon, authenticated, service_role"
    )


def downgrade() -> None:
    op.drop_index("ix_recordings_encounter_id", table_name="recordings")
    op.drop_table("recordings")
