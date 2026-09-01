"""create soap_note_sections table

Revision ID: 007_create_soap_note_sections
Revises: 006_create_soap_notes
Create Date: 2026-08-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "007_create_soap_note_sections"
down_revision: Union[str, None] = "006_create_soap_notes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "soap_note_sections",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("soap_note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_type", sa.String(), nullable=False),
        sa.Column("ai_generated_text", sa.Text(), nullable=True),
        sa.Column("physician_edited_text", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["soap_note_id"],
            ["soap_notes.id"],
            name="fk_soap_note_sections_soap_note_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_soap_note_sections_soap_note_id",
        "soap_note_sections",
        ["soap_note_id"],
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE soap_note_sections "
        "TO anon, authenticated, service_role"
    )


def downgrade() -> None:
    op.drop_index("ix_soap_note_sections_soap_note_id", table_name="soap_note_sections")
    op.drop_table("soap_note_sections")
