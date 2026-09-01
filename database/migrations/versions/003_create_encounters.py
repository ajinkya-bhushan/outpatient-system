"""create encounters table

Revision ID: 003_create_encounters
Revises: 002_create_patients
Create Date: 2026-08-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003_create_encounters"
down_revision: Union[str, None] = "002_create_patients"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "encounters",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("physician_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name="fk_encounters_patient_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["physician_id"],
            ["users.id"],
            name="fk_encounters_physician_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_encounters_patient_id", "encounters", ["patient_id"])
    op.create_index("ix_encounters_physician_id", "encounters", ["physician_id"])
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE encounters "
        "TO anon, authenticated, service_role"
    )


def downgrade() -> None:
    op.drop_index("ix_encounters_physician_id", table_name="encounters")
    op.drop_index("ix_encounters_patient_id", table_name="encounters")
    op.drop_table("encounters")
