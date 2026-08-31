"""SQLAlchemy models for the outpatient clinical data model.

Tables (FK order):
    users → patients → encounters → recordings → transcripts
                              ↘ soap_notes → soap_note_sections
                                           ↘ coding_suggestions
                              ↘ ehr_sync_log
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


TABLE_NAMES = (
    "users",
    "patients",
    "encounters",
    "recordings",
    "transcripts",
    "soap_notes",
    "soap_note_sections",
    "coding_suggestions",
    "ehr_sync_log",
)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    provider_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    encounters: Mapped[list[Encounter]] = relationship(back_populates="physician")


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    mrn: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    fhir_patient_id: Mapped[str | None] = mapped_column(String, unique=True)

    encounters: Mapped[list[Encounter]] = relationship(back_populates="patient")


class Encounter(Base):
    __tablename__ = "encounters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    physician_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    patient: Mapped[Patient] = relationship(back_populates="encounters")
    physician: Mapped[User] = relationship(back_populates="encounters")
    recordings: Mapped[list[Recording]] = relationship(back_populates="encounter")
    soap_note: Mapped[SoapNote | None] = relationship(back_populates="encounter")
    ehr_sync_logs: Mapped[list[EhrSyncLog]] = relationship(back_populates="encounter")


class Recording(Base):
    __tablename__ = "recordings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("encounters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    s3_key: Mapped[str] = mapped_column(String, nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)

    encounter: Mapped[Encounter] = relationship(back_populates="recordings")
    transcript: Mapped[Transcript | None] = relationship(back_populates="recording")


class Transcript(Base):
    __tablename__ = "transcripts"
    __table_args__ = (UniqueConstraint("recording_id", name="uq_transcripts_recording_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    recording_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recordings.id", ondelete="CASCADE"),
        nullable=False,
    )
    s3_key: Mapped[str] = mapped_column(String, nullable=False)
    engine_version: Mapped[str | None] = mapped_column(String)

    recording: Mapped[Recording] = relationship(back_populates="transcript")


class SoapNote(Base):
    __tablename__ = "soap_notes"
    __table_args__ = (UniqueConstraint("encounter_id", name="uq_soap_notes_encounter_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("encounters.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    conversation_text: Mapped[str | None] = mapped_column(Text)
    full_markdown: Mapped[str | None] = mapped_column(Text)

    encounter: Mapped[Encounter] = relationship(back_populates="soap_note")
    sections: Mapped[list[SoapNoteSection]] = relationship(back_populates="soap_note")
    coding_suggestions: Mapped[list[CodingSuggestion]] = relationship(back_populates="soap_note")


class SoapNoteSection(Base):
    __tablename__ = "soap_note_sections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    soap_note_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("soap_notes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section_type: Mapped[str] = mapped_column(String, nullable=False)
    ai_generated_text: Mapped[str | None] = mapped_column(Text)
    physician_edited_text: Mapped[str | None] = mapped_column(Text)
    confidence_score: Mapped[float | None] = mapped_column(Float)

    soap_note: Mapped[SoapNote] = relationship(back_populates="sections")


class CodingSuggestion(Base):
    __tablename__ = "coding_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    soap_note_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("soap_notes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code_type: Mapped[str] = mapped_column(String, nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    soap_note: Mapped[SoapNote] = relationship(back_populates="coding_suggestions")


class EhrSyncLog(Base):
    __tablename__ = "ehr_sync_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("encounters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    encounter: Mapped[Encounter] = relationship(back_populates="ehr_sync_logs")
