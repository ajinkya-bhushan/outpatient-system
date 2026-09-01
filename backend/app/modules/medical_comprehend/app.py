"""Detect clinical entities from an encounter transcript.

Source: soap_create/app.py

Original behaviour
------------------
The prototype called ``comprehendmedical.detect_entities_v2`` on a hardcoded
doctor-patient conversation and wrote ``entities.json``.

This module keeps that AWS API and entity shape, but accepts transcript text
as input so it can sit between STT and SOAP generation.
"""

from __future__ import annotations

from typing import Any

import boto3

from app.core.config import settings
from app.core.errors import ConfigurationError, UpstreamUnavailable, ValidationFailed
from app.core.logging import get_logger

logger = get_logger(__name__)

COMPREHEND_CHAR_LIMIT = 20_000


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


def detect_entities(text: str) -> list[dict[str, Any]]:
    """Run DetectEntitiesV2 on transcript text and return the Entities list."""
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValidationFailed("Transcript text is empty.")
    if len(cleaned) > settings.MAX_TRANSCRIPT_CHARS:
        raise ValidationFailed(
            f"Transcript exceeds {settings.MAX_TRANSCRIPT_CHARS} characters."
        )

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


def summarize_entities(entities: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entity in entities:
        category = str(entity.get("Category") or "UNKNOWN")
        counts[category] = counts.get(category, 0) + 1
    return counts
