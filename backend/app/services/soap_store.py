"""Persist parsed SOAP drafts to Postgres soap_notes / soap_note_sections."""

from __future__ import annotations

from uuid import UUID, uuid5

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.errors import ConfigurationError, NotFound, ValidationFailed
from app.db import Encounter, SoapNote, SoapNoteSection, get_session
from app.modules.generate_soap.parse import SECTION_ORDER, sections_to_markdown
from app.schemas.api import SoapNoteOut, SoapSectionOut

SOAP_NOTE_STATUS = "needs_physician_review"

# Same uuid5 the seed migration uses for Marcus's encounter so the recording
# demo can persist without a schedule round-trip.
_SEED_NS = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
DEFAULT_ENCOUNTER_ID = str(
    uuid5(_SEED_NS, "outpatient-frontend-seed|encounter:marcus-2026-08-19")
)


def _require_database() -> None:
    if not (settings.DATABASE_URL or "").strip():
        raise ConfigurationError("DATABASE_URL is not set.")


def parse_encounter_id(raw: str | None) -> str:
    value = (raw or "").strip() or DEFAULT_ENCOUNTER_ID
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise ValidationFailed("encounter_id must be a UUID.") from exc


def _as_uuid(value: str, field: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValidationFailed(f"{field} must be a UUID.") from exc


def encounter_exists(encounter_id: str) -> bool:
    _require_database()
    session = get_session()
    try:
        return session.get(Encounter, UUID(encounter_id)) is not None
    finally:
        session.close()


def _note_to_out(note: SoapNote, markdown: str | None = None) -> SoapNoteOut:
    by_type = {section.section_type: section.ai_generated_text or "" for section in note.sections}
    sections = [
        SoapSectionOut(section_type=name, ai_generated_text=by_type.get(name) or "")
        for name in SECTION_ORDER
    ]
    body = markdown or sections_to_markdown({item.section_type: item.ai_generated_text for item in sections})
    return SoapNoteOut(
        id=str(note.id),
        status=note.status,
        soap_markdown=body,
        sections=sections,
    )


def persist_soap_note(
    encounter_id: str,
    markdown: str,
    sections: list[dict[str, str]],
) -> SoapNoteOut:
    _require_database()
    enc_uuid = UUID(encounter_id)
    session = get_session()
    try:
        encounter = session.get(Encounter, enc_uuid)
        if encounter is None:
            raise NotFound(f"No encounter {encounter_id}.")

        note = session.scalars(
            select(SoapNote)
            .options(selectinload(SoapNote.sections))
            .where(SoapNote.encounter_id == enc_uuid)
        ).first()
        if note is None:
            note = SoapNote(encounter_id=enc_uuid, status=SOAP_NOTE_STATUS)
            session.add(note)
            session.flush()
        else:
            note.status = SOAP_NOTE_STATUS
            note.approved_at = None
            session.execute(delete(SoapNoteSection).where(SoapNoteSection.soap_note_id == note.id))
            session.flush()

        for section in sections:
            session.add(
                SoapNoteSection(
                    soap_note_id=note.id,
                    section_type=section["section_type"],
                    ai_generated_text=section.get("ai_generated_text") or "",
                )
            )
        session.commit()
        note = session.scalars(
            select(SoapNote)
            .options(selectinload(SoapNote.sections))
            .where(SoapNote.id == note.id)
        ).one()
        return _note_to_out(note, markdown)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_soap_note(note_id: str) -> SoapNoteOut | None:
    _require_database()
    session = get_session()
    try:
        note = session.scalars(
            select(SoapNote)
            .options(selectinload(SoapNote.sections))
            .where(SoapNote.id == _as_uuid(note_id, "soap_note_id"))
        ).first()
        return _note_to_out(note) if note else None
    finally:
        session.close()


def get_soap_note_by_encounter(encounter_id: str) -> SoapNoteOut | None:
    _require_database()
    enc_uuid = _as_uuid(encounter_id, "encounter_id")
    session = get_session()
    try:
        note = session.scalars(
            select(SoapNote)
            .options(selectinload(SoapNote.sections))
            .where(SoapNote.encounter_id == enc_uuid)
        ).first()
        return _note_to_out(note) if note else None
    finally:
        session.close()
