"""Orchestrate transcript → Comprehend Medical → SOAP generation."""

from __future__ import annotations

from typing import Any

from app.core.errors import ValidationFailed
from app.core.logging import get_logger
from app.models import store
from app.modules.generate_soap.agent_call import generate_soap_note
from app.modules.medical_comprehend.app import (
    build_aava_payload,
    detect_entities,
    summarize_entities,
)
from app.modules.stt.schemas import TranscriptResult
from app.schemas.api import (
    EntityExtractionResponse,
    PipelineResponse,
    SoapGenerateResponse,
)

logger = get_logger(__name__)


def save_transcript(
    text: str,
    *,
    encounter_id: str | None = None,
    language: str | None = None,
    source: str = "text",
    extra: dict[str, Any] | None = None,
) -> TranscriptResult:
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValidationFailed("Transcript text is empty.")
    record = store.get_or_create(encounter_id, source=source)
    payload = extra or {}
    transcript = TranscriptResult(
        text=cleaned,
        language=language or payload.get("language") or "unknown",
        segments=payload.get("segments") or [],
        audio_duration=payload.get("audio_duration") or 0.0,
        processing_time=payload.get("processing_time") or 0.0,
        real_time_factor=payload.get("real_time_factor") or 0.0,
        engine=payload.get("engine") or source,
        model=payload.get("model") or "n/a",
        source=source,
    )
    record.transcript = transcript
    record.source = source
    return transcript


def extract_entities(text: str, encounter_id: str | None = None) -> EntityExtractionResponse:
    record = store.get_or_create(encounter_id, source="text")
    if record.transcript is None:
        save_transcript(text, encounter_id=record.id, source="text")
    entities = detect_entities(text)
    record.entities = entities
    return EntityExtractionResponse(
        encounter_id=record.id,
        entity_count=len(entities),
        category_counts=summarize_entities(entities),
        entities=entities,
    )


def _entity_list(payload: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        return list(payload.get("entities") or [])
    return payload


def create_soap(
    entities: list[dict[str, Any]] | dict[str, Any],
    encounter_id: str | None = None,
    user_inputs: dict[str, str] | None = None,
) -> SoapGenerateResponse:
    entity_list = _entity_list(entities)
    if not entity_list:
        raise ValidationFailed("No entities were provided for SOAP generation.")
    record = store.get_or_create(encounter_id, source="text")
    record.entities = entity_list
    result = generate_soap_note(entities, user_inputs=user_inputs)
    record.soap_markdown = result["soap_markdown"]
    record.soap_execution_id = result["execution_id"]
    record.soap_status = result["status"]
    return SoapGenerateResponse(
        encounter_id=record.id,
        execution_id=result["execution_id"],
        status=result["status"],
        agent_name=result.get("agent_name"),
        soap_markdown=result["soap_markdown"],
        created_at=result.get("created_at"),
    )


def run_from_transcript(
    text: str,
    *,
    encounter_id: str | None = None,
    language: str | None = None,
    source: str = "text",
    user_inputs: dict[str, str] | None = None,
) -> PipelineResponse:
    transcript = save_transcript(text, encounter_id=encounter_id, language=language, source=source)
    record = store.get_or_create(encounter_id, source=source)
    payload = build_aava_payload(transcript.text)
    record.entities = payload.get("entities") or []
    soap = create_soap(payload, encounter_id=record.id, user_inputs=user_inputs)
    logger.info("pipeline_completed", encounter_id=record.id, entity_count=len(record.entities))
    return PipelineResponse(
        encounter_id=record.id,
        transcript=transcript,
        entity_count=len(record.entities),
        category_counts=summarize_entities(record.entities),
        entities=record.entities,
        soap=soap,
    )
