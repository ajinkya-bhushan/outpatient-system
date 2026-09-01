"""Comprehend Medical entity extraction routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.errors import raise_app_error
from app.core.errors import AppError
from app.core.logging import request_id_ctx
from app.modules.medical_comprehend.app import infer_icd10, infer_rx_norm
from app.schemas.api import (
    EntityExtractionResponse,
    InferIcd10Response,
    InferRxNormResponse,
    TranscriptTextRequest,
)
from app.services import pipeline as pipeline_service

router = APIRouter(prefix="/comprehend", tags=["Medical Comprehend"])


@router.post("/entities", response_model=EntityExtractionResponse)
def extract_entities(body: TranscriptTextRequest) -> EntityExtractionResponse:
    request_id_ctx.set(str(uuid.uuid4())[:8])
    try:
        return pipeline_service.extract_entities(body.text, encounter_id=body.encounter_id)
    except AppError as exc:
        raise_app_error(exc)


@router.post("/icd10", response_model=InferIcd10Response)
def infer_icd10_cm(body: TranscriptTextRequest) -> InferIcd10Response:
    request_id_ctx.set(str(uuid.uuid4())[:8])
    try:
        return InferIcd10Response.model_validate(infer_icd10(body.text))
    except AppError as exc:
        raise_app_error(exc)


@router.post("/rxnorm", response_model=InferRxNormResponse)
def infer_rxnorm(body: TranscriptTextRequest) -> InferRxNormResponse:
    request_id_ctx.set(str(uuid.uuid4())[:8])
    try:
        return InferRxNormResponse.model_validate(infer_rx_norm(body.text))
    except AppError as exc:
        raise_app_error(exc)
