"""SOAP generation routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.errors import raise_app_error
from app.core.errors import AppError, ValidationFailed
from app.core.logging import request_id_ctx
from app.models import store
from app.schemas.api import SoapGenerateRequest, SoapGenerateResponse
from app.services import pipeline as pipeline_service

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
