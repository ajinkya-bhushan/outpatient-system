"""create patients table

Revision ID: 002_create_patients
Revises: 001_create_users
Create Date: 2026-08-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002_create_patients"
down_revision: Union[str, None] = "001_create_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "patients",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("mrn", sa.String(), nullable=False),
        sa.Column("fhir_patient_id", sa.String(), nullable=True),
        sa.UniqueConstraint("mrn", name="uq_patients_mrn"),
        sa.UniqueConstraint("fhir_patient_id", name="uq_patients_fhir_patient_id"),
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE patients "
        "TO anon, authenticated, service_role"
    )


def downgrade() -> None:
    op.drop_table("patients")
