"""create transcripts table

Revision ID: 005_create_transcripts
Revises: 004_create_recordings
Create Date: 2026-08-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005_create_transcripts"
down_revision: Union[str, None] = "004_create_recordings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transcripts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("recording_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("s3_key", sa.String(), nullable=False),
        sa.Column("engine_version", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["recordings.id"],
            name="fk_transcripts_recording_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("recording_id", name="uq_transcripts_recording_id"),
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE transcripts "
        "TO anon, authenticated, service_role"
    )


def downgrade() -> None:
    op.drop_table("transcripts")
