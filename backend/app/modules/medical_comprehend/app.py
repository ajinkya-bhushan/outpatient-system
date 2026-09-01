"""Detect clinical entities from an encounter transcript.

Source: soap_create/app.py

Original behaviour
------------------
The prototype called ``comprehendmedical.detect_entities_v2`` on a hardcoded
doctor-patient conversation and wrote ``entities.json``.

This module keeps that AWS API and entity shape, but accepts transcript text
as input so it can sit between STT and SOAP generation. ``infer_icd10`` wraps
``comprehendmedical.infer_icd10_cm``; ``infer_rx_norm`` wraps
``comprehendmedical.infer_rx_norm``. ``build_aava_payload`` combines those
results into the JSON uploaded to the SOAP agent.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import boto3

from app.core.config import settings
from app.core.errors import ConfigurationError, UpstreamUnavailable, ValidationFailed
from app.core.logging import get_logger

logger = get_logger(__name__)

COMPREHEND_CHAR_LIMIT = 20_000
INFER_CHAR_LIMIT = 10_000


def _client():
    if not settings.aws_configured:
        raise ConfigurationError(
            "AWS credentials are not set. Add AWS_ACCESS_KEY_ID and "
            "AWS_SECRET_ACCESS_KEY to the backend .env file."
        )
    # Pass keys explicitly. Pydantic loads them from env files into Settings;
    # that does not export them into os.environ, so boto3's default chain
    # (env vars, shared credentials file, instance role) cannot see them.
    kwargs: dict[str, Any] = {
        "region_name": settings.AWS_DEFAULT_REGION,
        "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
        "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
    }
    if settings.AWS_SESSION_TOKEN:
        kwargs["aws_session_token"] = settings.AWS_SESSION_TOKEN
    return boto3.client("comprehendmedical", **kwargs)


def _chunks(text: str, limit: int = COMPREHEND_CHAR_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            parts.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = remaining.rfind(" ", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        parts.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip()
    return parts


def _validated_text(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValidationFailed("Transcript text is empty.")
    if len(cleaned) > settings.MAX_TRANSCRIPT_CHARS:
        raise ValidationFailed(
            f"Transcript exceeds {settings.MAX_TRANSCRIPT_CHARS} characters."
        )
    return cleaned


def _shift_offsets(entity: dict[str, Any], offset: int) -> dict[str, Any]:
    shifted = dict(entity)
    shifted["BeginOffset"] = int(shifted.get("BeginOffset") or 0) + offset
    shifted["EndOffset"] = int(shifted.get("EndOffset") or 0) + offset
    attributes = []
    for attr in shifted.get("Attributes") or []:
        attr = dict(attr)
        attr["BeginOffset"] = int(attr.get("BeginOffset") or 0) + offset
        attr["EndOffset"] = int(attr.get("EndOffset") or 0) + offset
        attributes.append(attr)
    if attributes:
        shifted["Attributes"] = attributes
    return shifted


def detect_entities(text: str) -> list[dict[str, Any]]:
    """Run DetectEntitiesV2 on transcript text and return the Entities list."""
    cleaned = _validated_text(text)
    client = _client()
    entities: list[dict[str, Any]] = []
    offset = 0
    try:
        for chunk in _chunks(cleaned, COMPREHEND_CHAR_LIMIT):
            logger.info("comprehend_detect_started", chars=len(chunk), offset=offset)
            result = client.detect_entities_v2(Text=chunk)
            for entity in result.get("Entities") or []:
                entity = dict(entity)
                entity["BeginOffset"] = int(entity.get("BeginOffset") or 0) + offset
                entity["EndOffset"] = int(entity.get("EndOffset") or 0) + offset
                entities.append(entity)
            offset += len(chunk)
    except ValidationFailed:
        raise
    except Exception as exc:
        raise UpstreamUnavailable(f"Comprehend Medical request failed: {exc}") from exc

    logger.info("comprehend_detect_completed", entity_count=len(entities))
    return entities


def _paginated_infer(text: str, method: str, *, log_event: str, error_label: str) -> dict[str, Any]:
    cleaned = _validated_text(text)
    client = _client()
    call = getattr(client, method)
    entities: list[dict[str, Any]] = []
    model_version: str | None = None
    offset = 0
    try:
        for chunk in _chunks(cleaned, INFER_CHAR_LIMIT):
            logger.info(f"{log_event}_started", chars=len(chunk), offset=offset)
            pagination_token: str | None = None
            while True:
                kwargs: dict[str, Any] = {"Text": chunk}
                if pagination_token:
                    kwargs["PaginationToken"] = pagination_token
                result = call(**kwargs)
                model_version = result.get("ModelVersion") or model_version
                for entity in result.get("Entities") or []:
                    entities.append(_shift_offsets(entity, offset))
                pagination_token = result.get("PaginationToken") or None
                if not pagination_token:
                    break
            offset += len(chunk)
    except ValidationFailed:
        raise
    except Exception as exc:
        raise UpstreamUnavailable(
            f"Comprehend Medical {error_label} request failed: {exc}"
        ) from exc

    logger.info(f"{log_event}_completed", entity_count=len(entities))
    return {
        "Entities": entities,
        "PaginationToken": None,
        "ModelVersion": model_version,
    }


def infer_icd10(text: str) -> dict[str, Any]:
    """Run InferICD10CM and return Entities, PaginationToken, and ModelVersion."""
    return _paginated_infer(
        text,
        "infer_icd10_cm",
        log_event="comprehend_infer_icd10",
        error_label="InferICD10CM",
    )


def infer_rx_norm(text: str) -> dict[str, Any]:
    """Run InferRxNorm and return Entities, PaginationToken, and ModelVersion."""
    return _paginated_infer(
        text,
        "infer_rx_norm",
        log_event="comprehend_infer_rx_norm",
        error_label="InferRxNorm",
    )


def _codes_with_confidence(
    entities: list[dict[str, Any]], concept_key: str
) -> list[dict[str, Any]]:
    """Keep the top linked code plus its confidence for each inferred entity."""
    rows: list[dict[str, Any]] = []
    for entity in entities:
        concepts = [
            concept
            for concept in (entity.get(concept_key) or [])
            if concept.get("Code")
        ]
        if not concepts:
            continue
        top = max(concepts, key=lambda concept: float(concept.get("Score") or 0))
        traits = [
            str(trait.get("Name"))
            for trait in (entity.get("Traits") or [])
            if trait.get("Name")
        ]
        attributes = [
            {"type": attr.get("Type"), "text": attr.get("Text")}
            for attr in (entity.get("Attributes") or [])
            if attr.get("Type") and attr.get("Text")
        ]
        row: dict[str, Any] = {
            "text": entity.get("Text"),
            "type": entity.get("Type"),
            "code": top.get("Code"),
            "description": top.get("Description"),
            "confidence": top.get("Score"),
            "entity_confidence": entity.get("Score"),
            "traits": traits,
            "negated": "NEGATION" in traits,
        }
        if attributes:
            row["attributes"] = attributes
        rows.append(row)
    return rows


def build_aava_payload(text: str) -> dict[str, Any]:
    """DetectEntitiesV2 plus InferICD10CM / InferRxNorm codes for the SOAP agent."""
    cleaned = _validated_text(text)
    with ThreadPoolExecutor(max_workers=3) as pool:
        entities_future = pool.submit(detect_entities, cleaned)
        icd10_future = pool.submit(infer_icd10, cleaned)
        rxnorm_future = pool.submit(infer_rx_norm, cleaned)
        entities = entities_future.result()
        icd10 = icd10_future.result()
        rxnorm = rxnorm_future.result()
    payload = {
        "entities": entities,
        "icd10": _codes_with_confidence(icd10.get("Entities") or [], "ICD10CMConcepts"),
        "rxnorm": _codes_with_confidence(rxnorm.get("Entities") or [], "RxNormConcepts"),
    }
    logger.info(
        "comprehend_aava_payload_built",
        entity_count=len(entities),
        icd10_count=len(payload["icd10"]),
        rxnorm_count=len(payload["rxnorm"]),
    )
    return payload


def summarize_entities(entities: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entity in entities:
        category = str(entity.get("Category") or "UNKNOWN")
        counts[category] = counts.get(category, 0) + 1
    return counts
