"""In-memory SOAP create jobs: transcript → Comprehend → Aava → Postgres."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from uuid import uuid4

from app.core.config import settings
from app.core.errors import ConfigurationError, NotFound, ValidationFailed
from app.core.logging import get_logger
from app.modules.generate_soap.agent_call import generate_soap_note
from app.modules.generate_soap.parse import parse_soap_markdown, sections_as_list
from app.modules.medical_comprehend.app import detect_entities, summarize_entities
from app.schemas.api import (
    SoapJobError,
    SoapJobResponse,
    SoapNoteOut,
    SoapStep,
)
from app.services import soap_store

logger = get_logger(__name__)

_ERROR_CODES = {
    "ValidationFailed": "validation_failed",
    "NotFound": "not_found",
    "ConfigurationError": "configuration_error",
    "UpstreamUnavailable": "upstream_unavailable",
    "UpstreamTimeout": "upstream_timeout",
}

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="soap-job")
_jobs: dict[str, SoapJob] = {}
_lock = threading.Lock()


@dataclass
class SoapJob:
    id: str
    encounter_id: str
    transcript: str
    language: str | None = None
    stt_job_id: str | None = None
    user_inputs: dict[str, str] = field(default_factory=dict)
    status: str = "queued"
    failed_step: str | None = None
    soap_note_id: str | None = None
    entity_count: int | None = None
    category_counts: dict[str, int] = field(default_factory=dict)
    execution_id: str | None = None
    soap_markdown: str | None = None
    soap_note: SoapNoteOut | None = None
    error_code: str | None = None
    error_detail: str | None = None


def require_soap_dependencies() -> None:
    if not settings.aws_configured:
        raise ConfigurationError(
            "AWS credentials are not set. Add AWS_ACCESS_KEY_ID and "
            "AWS_SECRET_ACCESS_KEY to the backend .env file."
        )
    if not settings.aava_configured:
        raise ConfigurationError(
            "AAVA_JWT_TOKEN is not set. Add it to the backend .env file."
        )


def _steps_for(job: SoapJob) -> list[SoapStep]:
    extracting = "queued"
    generating = "queued"
    if job.status == "extracting":
        extracting = "active"
    elif job.status in {"generating", "done"}:
        extracting = "done"
        generating = "active" if job.status == "generating" else "done"
    elif job.status == "failed":
        if job.failed_step == "extracting":
            extracting = "failed"
        else:
            extracting = "done"
            generating = "failed"
    return [
        SoapStep(id="transcribing", status="done"),
        SoapStep(id="extracting", status=extracting),  # type: ignore[arg-type]
        SoapStep(id="generating", status=generating),  # type: ignore[arg-type]
    ]


def job_to_response(job: SoapJob) -> SoapJobResponse:
    error = None
    if job.error_code and job.error_detail:
        error = SoapJobError(code=job.error_code, detail=job.error_detail)
    return SoapJobResponse(
        soap_job_id=job.id,
        encounter_id=job.encounter_id,
        soap_note_id=job.soap_note_id,
        status=job.status,  # type: ignore[arg-type]
        steps=_steps_for(job),
        entity_count=job.entity_count,
        category_counts=job.category_counts,
        execution_id=job.execution_id,
        soap_note=job.soap_note,
        error=error,
    )


def _set_status(job: SoapJob, status: str, *, failed_step: str | None = None) -> None:
    with _lock:
        job.status = status
        if failed_step:
            job.failed_step = failed_step


def _fail(job: SoapJob, exc: BaseException, step: str) -> None:
    code = _ERROR_CODES.get(type(exc).__name__, "internal_error")
    detail = getattr(exc, "message", None) or str(exc)
    logger.error("soap_job_failed", soap_job_id=job.id, step=step, error=detail)
    with _lock:
        job.status = "failed"
        job.failed_step = step
        job.error_code = code
        job.error_detail = detail


def run_job(job_id: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
    if job is None:
        return

    _set_status(job, "extracting")
    try:
        entities = detect_entities(job.transcript)
        with _lock:
            job.entity_count = len(entities)
            job.category_counts = summarize_entities(entities)
    except Exception as exc:  # noqa: BLE001 — any extract failure becomes job.failed
        _fail(job, exc, "extracting")
        return

    _set_status(job, "generating")
    try:
        result = generate_soap_note(entities, user_inputs=job.user_inputs)
        markdown = result["soap_markdown"]
        parsed = parse_soap_markdown(markdown)
        section_rows = sections_as_list(parsed)
        note = soap_store.persist_soap_note(job.encounter_id, markdown, section_rows, conversation_text=job.transcript)
        with _lock:
            job.execution_id = result.get("execution_id")
            job.soap_markdown = markdown
            job.soap_note = note
            job.soap_note_id = note.id
            job.status = "done"
        logger.info("soap_job_completed", soap_job_id=job.id, soap_note_id=note.id)
    except Exception as exc:  # noqa: BLE001 — Aava/parse/DB failure becomes job.failed
        _fail(job, exc, "generating")


def enqueue(job_id: str) -> None:
    _executor.submit(run_job, job_id)


def submit_create(
    transcript: str,
    *,
    encounter_id: str | None = None,
    job_id: str | None = None,
    language: str | None = None,
    user_inputs: dict[str, str] | None = None,
) -> SoapJob:
    cleaned = (transcript or "").strip()
    if not cleaned:
        raise ValidationFailed("Transcript text is empty.")
    if len(cleaned) > settings.MAX_TRANSCRIPT_CHARS:
        raise ValidationFailed(
            f"Transcript exceeds {settings.MAX_TRANSCRIPT_CHARS} characters."
        )

    require_soap_dependencies()
    resolved_encounter = soap_store.parse_encounter_id(encounter_id)
    if not soap_store.encounter_exists(resolved_encounter):
        raise NotFound(f"No encounter {resolved_encounter}.")

    job = SoapJob(
        id=str(uuid4()),
        encounter_id=resolved_encounter,
        transcript=cleaned,
        language=language,
        stt_job_id=job_id,
        user_inputs=dict(user_inputs or {}),
    )
    with _lock:
        _jobs[job.id] = job
    logger.info("soap_job_queued", soap_job_id=job.id, encounter_id=resolved_encounter)
    enqueue(job.id)
    return job


def get_job(job_id: str) -> SoapJob:
    with _lock:
        job = _jobs.get(job_id)
    if job is None:
        raise NotFound(f"No SOAP job {job_id}.")
    return job


def reset_jobs() -> None:
    """Drop in-memory jobs. Used by tests."""
    with _lock:
        _jobs.clear()
