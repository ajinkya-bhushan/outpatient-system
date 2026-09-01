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
    service = get_stt_service()

    stt_status = "unknown"
    try:
        await service.health()
        stt_status = "ok"
    except Exception as exc:
        stt_status = f"unavailable: {exc}"

    engine = service.engine_status()
    return {
        "status": "ready",
        "stt": stt_status,
        "stt_mode": engine.mode,
        "stt_engine": {
            "device": engine.device,
            "whisper_model": engine.whisper_model,
            "whisper_backend": engine.whisper_backend,
            "diarization_enabled": engine.diarization_enabled,
            "models_loaded": engine.models_loaded,
            "dependencies_available": engine.dependencies_available,
        },
        # Only meaningful in remote mode; kept for backwards compatibility.
        "stt_base_url": settings.STT_BASE_URL,
        "aws_configured": settings.aws_configured,
        "aava_configured": settings.aava_configured,
        "modules": ["stt", "diarization", "medical_comprehend", "generate_soap"],
    }
