"""Speech-to-text adapter: in-process local engine or remote HTTP proxy."""

from app.modules.stt.service import STTService, get_stt_service

__all__ = ["STTService", "get_stt_service"]
