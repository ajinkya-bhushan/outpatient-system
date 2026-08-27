"""SOAP generation routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.errors import raise_app_error
from app.core.errors import AppError, NotFound, ValidationFailed
from app.core.logging import request_id_ctx
from app.models import store
from app.schemas.api import (
    SoapCreateRequest,
    SoapGenerateRequest,
    SoapGenerateResponse,
    SoapJobResponse,
    SoapNoteOut,
)
from app.services import pipeline as pipeline_service
from app.services import soap_jobs, soap_store

router = APIRouter(prefix="/soap", tags=["Generate SOAP"])


@router.post("/generate", response_model=SoapGenerateResponse)
def generate_soap(body: SoapGenerateRequest) -> SoapGenerateResponse:
    request_id_ctx.set(str(uuid.uuid4())[:8])
    entities = body.entities
    if not entities and body.encounter_id:
        record = store.get(body.encounter_id)
        entities = record.entities if record else None
    try:
        if not entities:
            raise ValidationFailed("Provide entities or an encounter_id that already has entities.")
        return pipeline_service.create_soap(
            entities,
            encounter_id=body.encounter_id,
            user_inputs=body.user_inputs,
        )
    except AppError as exc:
        raise_app_error(exc)


@router.post("/create", response_model=SoapJobResponse, status_code=202)
def create_soap(body: SoapCreateRequest) -> SoapJobResponse:
    """Start transcript → Comprehend → Aava as a background job."""
    request_id_ctx.set(str(uuid.uuid4())[:8])
    try:
        job = soap_jobs.submit_create(
            body.transcript,
            encounter_id=body.encounter_id,
            job_id=body.job_id,
            language=body.language,
            user_inputs=body.user_inputs,
        )
        return soap_jobs.job_to_response(job)
    except AppError as exc:
        raise_app_error(exc)


@router.get("/jobs/{soap_job_id}", response_model=SoapJobResponse)
def get_soap_job(soap_job_id: str) -> SoapJobResponse:
    request_id_ctx.set(str(uuid.uuid4())[:8])
    try:
        return soap_jobs.job_to_response(soap_jobs.get_job(soap_job_id))
    except AppError as exc:
        raise_app_error(exc)


@router.get("/notes/{soap_note_id}", response_model=SoapNoteOut)
def get_soap_note(soap_note_id: str) -> SoapNoteOut:
    request_id_ctx.set(str(uuid.uuid4())[:8])
    try:
        note = soap_store.get_soap_note(soap_note_id)
        if note is None:
            raise NotFound(f"No SOAP note {soap_note_id}.")
        return note
    except AppError as exc:
        raise_app_error(exc)


@router.get("/encounters/{encounter_id}", response_model=SoapNoteOut)
def get_soap_note_for_encounter(encounter_id: str) -> SoapNoteOut:
    request_id_ctx.set(str(uuid.uuid4())[:8])
    try:
        note = soap_store.get_soap_note_by_encounter(encounter_id)
        if note is None:
            raise NotFound(f"No SOAP note for encounter {encounter_id}.")
        return note
    except AppError as exc:
        raise_app_error(exc)
