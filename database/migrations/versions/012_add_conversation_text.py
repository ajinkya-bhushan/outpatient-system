"""add conversation_text and full_markdown columns to soap_notes

Revision ID: 012_add_conversation_text
Revises: 011_add_user_auth_columns
Create Date: 2026-08-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "012_add_conversation_text"
down_revision: Union[str, None] = "011_add_user_auth_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "soap_notes",
        sa.Column("conversation_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "soap_notes",
        sa.Column("full_markdown", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("soap_notes", "full_markdown")
    op.drop_column("soap_notes", "conversation_text")
