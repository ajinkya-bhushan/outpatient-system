"""create soap_notes table

Revision ID: 006_create_soap_notes
Revises: 005_create_transcripts
Create Date: 2026-08-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "006_create_soap_notes"
down_revision: Union[str, None] = "005_create_transcripts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "soap_notes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["encounter_id"],
            ["encounters.id"],
            name="fk_soap_notes_encounter_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("encounter_id", name="uq_soap_notes_encounter_id"),
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE soap_notes "
        "TO anon, authenticated, service_role"
    )


def downgrade() -> None:
    op.drop_table("soap_notes")
