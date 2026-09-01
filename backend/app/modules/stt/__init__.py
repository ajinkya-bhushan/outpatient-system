"""Speech-to-text adapter around the sst_v1 FastAPI service."""

from app.modules.stt.service import STTService, get_stt_service

__all__ = ["STTService", "get_stt_service"]
