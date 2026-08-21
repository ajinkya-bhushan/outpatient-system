"""create ehr_sync_log table

Revision ID: 009_create_ehr_sync_log
Revises: 008_create_coding_suggestions
Create Date: 2026-08-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "009_create_ehr_sync_log"
down_revision: Union[str, None] = "008_create_coding_suggestions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ehr_sync_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.ForeignKeyConstraint(
            ["encounter_id"],
            ["encounters.id"],
            name="fk_ehr_sync_log_encounter_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_ehr_sync_log_encounter_id", "ehr_sync_log", ["encounter_id"])
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE ehr_sync_log "
        "TO anon, authenticated, service_role"
    )


def downgrade() -> None:
    op.drop_index("ix_ehr_sync_log_encounter_id", table_name="ehr_sync_log")
    op.drop_table("ehr_sync_log")
