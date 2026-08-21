"""create coding_suggestions table

Revision ID: 008_create_coding_suggestions
Revises: 007_create_soap_note_sections
Create Date: 2026-08-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "008_create_coding_suggestions"
down_revision: Union[str, None] = "007_create_soap_note_sections"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "coding_suggestions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("soap_note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code_type", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column(
            "accepted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.ForeignKeyConstraint(
            ["soap_note_id"],
            ["soap_notes.id"],
            name="fk_coding_suggestions_soap_note_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_coding_suggestions_soap_note_id",
        "coding_suggestions",
        ["soap_note_id"],
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE coding_suggestions "
        "TO anon, authenticated, service_role"
    )


def downgrade() -> None:
    op.drop_index("ix_coding_suggestions_soap_note_id", table_name="coding_suggestions")
    op.drop_table("coding_suggestions")
