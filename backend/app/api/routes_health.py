"""Liveness and readiness probes."""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.core.config import settings
from app.modules.stt.service import get_stt_service

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": __version__}


@router.get("/ready")
async def ready() -> dict:
    stt_status = "unknown"
    try:
        await get_stt_service().health()
        stt_status = "ok"
    except Exception as exc:
        stt_status = f"unavailable: {exc}"
    return {
        "status": "ready",
        "stt": stt_status,
        "stt_base_url": settings.STT_BASE_URL,
        "aws_configured": settings.aws_configured,
        "aava_configured": settings.aava_configured,
        "modules": ["stt", "medical_comprehend", "generate_soap"],
    }
