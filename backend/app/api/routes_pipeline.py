"""End-to-end encounter pipeline: transcript → entities → SOAP."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, UploadFile

from app.api.errors import raise_app_error
from app.core.errors import AppError
from app.core.logging import request_id_ctx
from app.modules.stt.service import get_stt_service
from app.schemas.api import PipelineRequest, PipelineResponse
from app.services import pipeline as pipeline_service

router = APIRouter(prefix="/pipeline", tags=["Pipeline"])


@router.post("", response_model=PipelineResponse)
def run_pipeline_from_text(body: PipelineRequest) -> PipelineResponse:
    request_id_ctx.set(str(uuid.uuid4())[:8])
    try:
        return pipeline_service.run_from_transcript(
            body.transcript,
            encounter_id=body.encounter_id,
            language=body.language,
            source=body.source,
        )
    except AppError as exc:
        raise_app_error(exc)


@router.post("/upload", response_model=PipelineResponse)
async def run_pipeline_from_upload(
    file: UploadFile = File(..., description="Encounter audio"),
    engine: str = Form(default=""),
    language: str = Form(default=""),
    encounter_id: str = Form(default=""),
) -> PipelineResponse:
    request_id_ctx.set(str(uuid.uuid4())[:8])
    file_bytes = await file.read()
    try:
        transcript = await get_stt_service().transcribe_upload(
            file_bytes=file_bytes,
            filename=file.filename or "upload.bin",
            content_type=file.content_type,
            engine=engine or None,
            language=language or None,
        )
        return pipeline_service.run_from_transcript(
            transcript.text,
            encounter_id=encounter_id or None,
            language=transcript.language,
            source="upload",
        )
    except AppError as exc:
        raise_app_error(exc)
