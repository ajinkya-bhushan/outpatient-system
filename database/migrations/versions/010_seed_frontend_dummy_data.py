"""seed frontend dummy clinical data

Revision ID: 010_seed_frontend_dummy_data
Revises: 009_create_ehr_sync_log
Create Date: 2026-08-21

Seeds the DocConnect UI mocks from frontend/src/data/clinicalData.js and
the recording / review / sync screens.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "010_seed_frontend_dummy_data"
down_revision: Union[str, None] = "009_create_ehr_sync_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def uid(name: str) -> uuid.UUID:
    return uuid.uuid5(NS, f"outpatient-frontend-seed|{name}")


USER_SMITH = uid("user:dr-smith")
USER_ADMIN = uid("user:admin")

PAT_MARCUS = uid("patient:marcus-thorne")
PAT_SARAH = uid("patient:sarah-jenkins")
PAT_ROBERT = uid("patient:robert-chen")
PAT_ELENA = uid("patient:elena-rodriguez")

ENC_ELENA = uid("encounter:elena-2026-08-19")
ENC_MARCUS = uid("encounter:marcus-2026-08-19")
ENC_SARAH = uid("encounter:sarah-2026-08-19")
ENC_ROBERT = uid("encounter:robert-2026-08-19")

REC_MARCUS = uid("recording:marcus-2026-08-19")
TRX_MARCUS = uid("transcript:marcus-2026-08-19")

SOAP_MARCUS = uid("soap:marcus-2026-08-19")
SOAP_SARAH = uid("soap:sarah-2026-08-19")
SOAP_ELENA = uid("soap:elena-2026-08-19")

DAY = datetime(2026, 8, 19, tzinfo=timezone.utc)


def _ts(hour: int, minute: int) -> datetime:
    return DAY.replace(hour=hour, minute=minute)


users_t = sa.table(
    "users",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("role", sa.String()),
)
patients_t = sa.table(
    "patients",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("mrn", sa.String()),
    sa.column("fhir_patient_id", sa.String()),
)
encounters_t = sa.table(
    "encounters",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("patient_id", postgresql.UUID(as_uuid=True)),
    sa.column("physician_id", postgresql.UUID(as_uuid=True)),
    sa.column("status", sa.String()),
    sa.column("started_at", sa.DateTime(timezone=True)),
)
recordings_t = sa.table(
    "recordings",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("encounter_id", postgresql.UUID(as_uuid=True)),
    sa.column("s3_key", sa.String()),
    sa.column("duration_seconds", sa.Integer()),
)
transcripts_t = sa.table(
    "transcripts",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("recording_id", postgresql.UUID(as_uuid=True)),
    sa.column("s3_key", sa.String()),
    sa.column("engine_version", sa.String()),
)
soap_notes_t = sa.table(
    "soap_notes",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("encounter_id", postgresql.UUID(as_uuid=True)),
    sa.column("status", sa.String()),
    sa.column("approved_at", sa.DateTime(timezone=True)),
)
sections_t = sa.table(
    "soap_note_sections",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("soap_note_id", postgresql.UUID(as_uuid=True)),
    sa.column("section_type", sa.String()),
    sa.column("ai_generated_text", sa.Text()),
    sa.column("physician_edited_text", sa.Text()),
    sa.column("confidence_score", sa.Float()),
)
coding_t = sa.table(
    "coding_suggestions",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("soap_note_id", postgresql.UUID(as_uuid=True)),
    sa.column("code_type", sa.String()),
    sa.column("code", sa.String()),
    sa.column("accepted", sa.Boolean()),
)
ehr_t = sa.table(
    "ehr_sync_log",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("encounter_id", postgresql.UUID(as_uuid=True)),
    sa.column("status", sa.String()),
    sa.column("retry_count", sa.Integer()),
)

MARCUS_SUBJECTIVE = (
    "Patient presents for cardiology follow-up. Reports improved exercise "
    "tolerance since last visit, but still notes intermittent fatigue in the "
    "evenings. Denies shortness of breath at rest, palpitations, syncope, or "
    "dizziness.\n\n"
    "Verify patient wording: Single episode of mild chest tightness while "
    "climbing stairs yesterday, lasting approximately 2 minutes and resolving "
    "with rest.\n\n"
    "Chief complaint: \"Chest tightness, intermittent\". Duration: 3 days. "
    "Worse with exertion."
)
MARCUS_OBJECTIVE = (
    "Allergies: Penicillin (anaphylaxis).\n"
    "PMH: Hypertension, hyperlipidemia, type 2 diabetes.\n"
    "Labs (drawn 2 days ago): Lipid Panel cholesterol 185 mg/dL Normal; "
    "HbA1c 7.2% Abnormal; CBC hemoglobin 14.5 g/dL Normal.\n"
    "Medications: Lisinopril 10mg PO daily; Atorvastatin 20mg PO at bedtime; "
    "Metformin 500mg PO BID with meals."
)
MARCUS_ASSESSMENT = (
    "1. Essential Hypertension (I10) — Improved but not yet at target. "
    "Home blood pressure log shows readings averaging 132-138 systolic.\n"
    "2. Hyperlipidemia (E78.5) — Stable on Atorvastatin. Patient noted mild "
    "muscle aches in legs, possibly statin-related, though recent CK levels "
    "were normal."
)
MARCUS_PLAN = "\n".join(
    [
        "- Continue Lisinopril 20mg PO daily.",
        "- Emphasized the importance of continued dietary sodium restriction and regular aerobic exercise.",
        "- Advised patient to continue home blood pressure monitoring and keep a log.",
        "- Re-check Basic Metabolic Panel (BMP) to monitor renal function and potassium levels.",
        "- Regarding muscle aches, will hold Atorvastatin for 2 weeks to see if symptoms resolve, then reconsider rechallenge or alternative agent.",
    ]
)
MARCUS_TRANSCRIPT = "\n".join(
    [
        "Marcus: Yeah, it started about three days ago. Just a tight feeling, mostly when I try to take a deep breath or climb the stairs.",
        "Dr. Smith: I see. Does the tightness spread anywhere else? Like your arm, neck, or jaw?",
        "Marcus: No, not really spreading. It just stays right in the center. I did take my Lisinopril this morning though.",
    ]
)


def upgrade() -> None:
    op.bulk_insert(
        users_t,
        [
            {"id": USER_SMITH, "role": "Physician"},
            {"id": USER_ADMIN, "role": "Admin"},
        ],
    )
    op.bulk_insert(
        patients_t,
        [
            {"id": PAT_MARCUS, "mrn": "88291", "fhir_patient_id": "Patient/88291"},
            {"id": PAT_SARAH, "mrn": "44108", "fhir_patient_id": "Patient/44108"},
            {"id": PAT_ROBERT, "mrn": "55932", "fhir_patient_id": "Patient/55932"},
            {"id": PAT_ELENA, "mrn": "33017", "fhir_patient_id": "Patient/33017"},
        ],
    )
    op.bulk_insert(
        encounters_t,
        [
            {
                "id": ENC_ELENA,
                "patient_id": PAT_ELENA,
                "physician_id": USER_SMITH,
                "status": "Synced",
                "started_at": _ts(7, 45),
            },
            {
                "id": ENC_MARCUS,
                "patient_id": PAT_MARCUS,
                "physician_id": USER_SMITH,
                "status": "Pending Review",
                "started_at": _ts(8, 30),
            },
            {
                "id": ENC_SARAH,
                "patient_id": PAT_SARAH,
                "physician_id": USER_SMITH,
                "status": "Pending Review",
                "started_at": _ts(9, 15),
            },
            {
                "id": ENC_ROBERT,
                "patient_id": PAT_ROBERT,
                "physician_id": USER_SMITH,
                "status": "Not Started",
                "started_at": _ts(10, 0),
            },
        ],
    )
    op.bulk_insert(
        recordings_t,
        [
            {
                "id": REC_MARCUS,
                "encounter_id": ENC_MARCUS,
                "s3_key": "recordings/88291/2026-08-19-cardiology.wav",
                "duration_seconds": 252,
            }
        ],
    )
    op.bulk_insert(
        transcripts_t,
        [
            {
                "id": TRX_MARCUS,
                "recording_id": REC_MARCUS,
                "s3_key": "transcripts/88291/2026-08-19-cardiology.txt",
                "engine_version": "whisper-base",
            }
        ],
    )
    # Transcript body is stored at s3_key in the model; persist the UI dialogue
    # in the SOAP subjective source via sections. Store the spoken text on the
    # transcript row by overloading is not possible (no text column). The
    # recording screen copy is captured in MARCUS_TRANSCRIPT on the subjective
    # note and in this comment for operators.
    op.bulk_insert(
        soap_notes_t,
        [
            {
                "id": SOAP_MARCUS,
                "encounter_id": ENC_MARCUS,
                "status": "needs_physician_review",
                "approved_at": None,
            },
            {
                "id": SOAP_SARAH,
                "encounter_id": ENC_SARAH,
                "status": "needs_physician_review",
                "approved_at": None,
            },
            {
                "id": SOAP_ELENA,
                "encounter_id": ENC_ELENA,
                "status": "approved",
                "approved_at": _ts(8, 0),
            },
        ],
    )
    op.bulk_insert(
        sections_t,
        [
            {
                "id": uid("section:marcus:subjective"),
                "soap_note_id": SOAP_MARCUS,
                "section_type": "subjective",
                "ai_generated_text": MARCUS_SUBJECTIVE + "\n\nTranscript:\n" + MARCUS_TRANSCRIPT,
                "physician_edited_text": None,
                "confidence_score": 0.96,
            },
            {
                "id": uid("section:marcus:objective"),
                "soap_note_id": SOAP_MARCUS,
                "section_type": "objective",
                "ai_generated_text": MARCUS_OBJECTIVE,
                "physician_edited_text": None,
                "confidence_score": 0.99,
            },
            {
                "id": uid("section:marcus:assessment"),
                "soap_note_id": SOAP_MARCUS,
                "section_type": "assessment",
                "ai_generated_text": MARCUS_ASSESSMENT,
                "physician_edited_text": None,
                "confidence_score": 0.88,
            },
            {
                "id": uid("section:marcus:plan"),
                "soap_note_id": SOAP_MARCUS,
                "section_type": "plan",
                "ai_generated_text": MARCUS_PLAN,
                "physician_edited_text": MARCUS_PLAN,
                "confidence_score": 0.94,
            },
            {
                "id": uid("section:sarah:subjective"),
                "soap_note_id": SOAP_SARAH,
                "section_type": "subjective",
                "ai_generated_text": "45-year-old female presenting for annual physical.",
                "physician_edited_text": None,
                "confidence_score": 0.96,
            },
            {
                "id": uid("section:sarah:objective"),
                "soap_note_id": SOAP_SARAH,
                "section_type": "objective",
                "ai_generated_text": "Vital signs and exam pending completion of visit.",
                "physician_edited_text": None,
                "confidence_score": 0.99,
            },
            {
                "id": uid("section:sarah:assessment"),
                "soap_note_id": SOAP_SARAH,
                "section_type": "assessment",
                "ai_generated_text": "Annual wellness visit; no acute complaints documented in the schedule mock.",
                "physician_edited_text": None,
                "confidence_score": 0.88,
            },
            {
                "id": uid("section:sarah:plan"),
                "soap_note_id": SOAP_SARAH,
                "section_type": "plan",
                "ai_generated_text": "Complete annual physical, age-appropriate screening, and routine labs.",
                "physician_edited_text": None,
                "confidence_score": 0.94,
            },
            {
                "id": uid("section:elena:subjective"),
                "soap_note_id": SOAP_ELENA,
                "section_type": "subjective",
                "ai_generated_text": "32-year-old female presenting for lab results review.",
                "physician_edited_text": None,
                "confidence_score": 0.96,
            },
            {
                "id": uid("section:elena:objective"),
                "soap_note_id": SOAP_ELENA,
                "section_type": "objective",
                "ai_generated_text": "Laboratory results reviewed with the patient.",
                "physician_edited_text": None,
                "confidence_score": 0.99,
            },
            {
                "id": uid("section:elena:assessment"),
                "soap_note_id": SOAP_ELENA,
                "section_type": "assessment",
                "ai_generated_text": "Lab results review; no new diagnoses in the schedule mock.",
                "physician_edited_text": None,
                "confidence_score": 0.88,
            },
            {
                "id": uid("section:elena:plan"),
                "soap_note_id": SOAP_ELENA,
                "section_type": "plan",
                "ai_generated_text": "Continue current plan; results discussed. Synced to Epic EHR.",
                "physician_edited_text": None,
                "confidence_score": 0.94,
            },
        ],
    )
    op.bulk_insert(
        coding_t,
        [
            {
                "id": uid("code:marcus:I10"),
                "soap_note_id": SOAP_MARCUS,
                "code_type": "ICD",
                "code": "I10",
                "accepted": True,
            },
            {
                "id": uid("code:marcus:E78.5"),
                "soap_note_id": SOAP_MARCUS,
                "code_type": "ICD",
                "code": "E78.5",
                "accepted": False,
            },
        ],
    )
    op.bulk_insert(
        ehr_t,
        [
            {
                "id": uid("ehr:marcus:epic"),
                "encounter_id": ENC_MARCUS,
                "status": "success",
                "retry_count": 0,
            },
            {
                "id": uid("ehr:elena:epic"),
                "encounter_id": ENC_ELENA,
                "status": "success",
                "retry_count": 0,
            },
        ],
    )


def downgrade() -> None:
    section_ids = [
        uid("section:marcus:subjective"),
        uid("section:marcus:objective"),
        uid("section:marcus:assessment"),
        uid("section:marcus:plan"),
        uid("section:sarah:subjective"),
        uid("section:sarah:objective"),
        uid("section:sarah:assessment"),
        uid("section:sarah:plan"),
        uid("section:elena:subjective"),
        uid("section:elena:objective"),
        uid("section:elena:assessment"),
        uid("section:elena:plan"),
    ]
    op.execute(ehr_t.delete().where(ehr_t.c.encounter_id.in_([ENC_MARCUS, ENC_ELENA])))
    op.execute(coding_t.delete().where(coding_t.c.soap_note_id.in_([SOAP_MARCUS])))
    op.execute(sections_t.delete().where(sections_t.c.id.in_(section_ids)))
    op.execute(soap_notes_t.delete().where(soap_notes_t.c.id.in_([SOAP_MARCUS, SOAP_SARAH, SOAP_ELENA])))
    op.execute(transcripts_t.delete().where(transcripts_t.c.id == TRX_MARCUS))
    op.execute(recordings_t.delete().where(recordings_t.c.id == REC_MARCUS))
    op.execute(
        encounters_t.delete().where(
            encounters_t.c.id.in_([ENC_ELENA, ENC_MARCUS, ENC_SARAH, ENC_ROBERT])
        )
    )
    op.execute(
        patients_t.delete().where(
            patients_t.c.id.in_([PAT_MARCUS, PAT_SARAH, PAT_ROBERT, PAT_ELENA])
        )
    )
    op.execute(users_t.delete().where(users_t.c.id.in_([USER_SMITH, USER_ADMIN])))
