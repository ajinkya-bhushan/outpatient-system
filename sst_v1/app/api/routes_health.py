"""
app/api/routes_health.py
─────────────────────────
Health-check and readiness endpoints.

GET /api/v1/health  – basic liveness probe (always returns 200 if the
                      process is running).
GET /api/v1/ready   – readiness probe that lists registered engines and
                      reports whether the default engine has been initialised.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.engines import list_engines

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Liveness probe")
async def health_check() -> dict:
    """Return 200 OK if the API process is alive."""
    return {"status": "ok", "version": "0.1.0"}


@router.get("/ready", summary="Readiness probe")
async def readiness_check() -> dict:
    """Return engine registry status and configuration summary."""
    return {
        "status": "ready",
        "default_engine": settings.DEFAULT_ENGINE,
        "whisper_model": settings.WHISPER_MODEL,
        "whisper_device": settings.WHISPER_DEVICE,
        "available_engines": list_engines(),
        "max_audio_size_mb": settings.MAX_AUDIO_SIZE_MB,
        "max_audio_duration_s": settings.MAX_AUDIO_DURATION_SECONDS,
    }
