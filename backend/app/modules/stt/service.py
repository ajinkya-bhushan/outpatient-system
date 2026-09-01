"""
app/modules/stt/service.py
───────────────────────────
The single seam every caller uses to reach speech-to-text.

``STT_ENGINE_MODE`` decides what sits behind it:

* ``local``  – SpeechBrain + Whisper in this process (:mod:`app.modules.stt.local`)
* ``remote`` – an external STT HTTP service (:mod:`app.modules.stt.remote_client`)

Routes depend only on this facade, so swapping engines needs no route changes —
which is how local inference replaced the remote proxy without touching
``/api/v1/pipeline/upload``. ``transcribe_upload`` keeps its original signature
for that reason.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.errors import ConfigurationError
from app.core.logging import get_logger
from app.modules.stt.remote_client import RemoteSTTClient
from app.modules.stt.schemas import (
    DiarizedTranscriptResponse,
    EngineStatusResponse,
    TranscriptResult,
)

logger = get_logger(__name__)


class STTService:
    """Engine-agnostic speech-to-text entry point."""

    def __init__(self, mode: str | None = None) -> None:
        self.mode = mode or settings.STT_ENGINE_MODE

    @property
    def is_local(self) -> bool:
        return self.mode == "local"

    # ── Status ────────────────────────────────────────────────────────────────

    def engine_status(self) -> EngineStatusResponse:
        """Describe the active engine without triggering a model load."""
        if self.is_local:
            from app.modules.stt.local.engine import get_engine

            return EngineStatusResponse(**get_engine().status().to_dict())

        return EngineStatusResponse(
            mode="remote",
            device="n/a",
            whisper_model="delegated to remote STT",
            whisper_backend=settings.DEFAULT_STT_ENGINE,
            compute_type="n/a",
            diarization_enabled=False,
            default_num_speakers=None,
            models_loaded=False,
            dependencies_available=True,
            detail=f"Proxying to remote STT at {settings.STT_BASE_URL}",
            extra={"stt_base_url": settings.STT_BASE_URL},
        )

    async def health(self) -> dict[str, Any]:
        """Readiness detail for ``/api/v1/ready``."""
        if self.is_local:
            status = self.engine_status()
            if not status.dependencies_available:
                raise ConfigurationError(status.detail or "Local STT is unavailable.")
            return {
                "status": "ok",
                "mode": "local",
                "device": status.device,
                "models_loaded": status.models_loaded,
            }

        payload = await RemoteSTTClient().health()
        return {"status": "ok", "mode": "remote", **payload}

    def preload(self) -> None:
        """Load models eagerly. Never fatal — the API serves other routes too."""
        if not (self.is_local and settings.STT_MODEL_PRELOAD):
            return

        from app.modules.stt.local.engine import get_engine

        try:
            get_engine().load()
        except Exception as exc:
            logger.warning("stt_preload_failed", error=str(exc)[:300])

    # ── Live streaming ────────────────────────────────────────────────────────

    def live_url(self) -> str:
        """Upstream WebSocket URL for the live-recording proxy.

        Live streaming is only available in remote mode. The local engine is
        file-based for now; incremental diarization is a separate piece of work
        (see backend/docs/STT_DIARIZATION_API.md).
        """
        if self.is_local:
            raise ConfigurationError(
                "Live streaming is not implemented for the local STT engine. "
                "Use POST /api/v1/stt/diarize with a recorded file, or set "
                "STT_ENGINE_MODE=remote to proxy live audio to an external STT service."
            )
        return RemoteSTTClient().live_url()

    # ── Transcription ─────────────────────────────────────────────────────────

    async def transcribe_upload(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str | None = None,
        engine: str | None = None,
        language: str | None = None,
        task: str = "transcribe",
    ) -> TranscriptResult:
        """Transcribe an uploaded audio file to plain text."""
        if not self.is_local:
            return await RemoteSTTClient().transcribe_upload(
                file_bytes=file_bytes,
                filename=filename,
                content_type=content_type,
                engine=engine,
                language=language,
                task=task,
            )

        from app.modules.stt.local import runner

        return await runner.transcribe(
            file_bytes=file_bytes,
            filename=filename,
            language=language,
            task=task,
        )

    async def diarize_upload(
        self,
        file_bytes: bytes,
        filename: str,
        num_speakers: int | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
        language: str | None = None,
        speaker_names: dict[str, str] | None = None,
        encounter_id: str | None = None,
        save_audio: bool = True,
    ) -> DiarizedTranscriptResponse:
        """Transcribe an uploaded audio file and label each turn with a speaker."""
        if not self.is_local:
            raise ConfigurationError(
                "Speaker diarization requires STT_ENGINE_MODE=local; remote STT "
                "does not expose a diarization endpoint."
            )

        from app.modules.stt.local import runner

        return await runner.diarize(
            file_bytes=file_bytes,
            filename=filename,
            num_speakers=num_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
            language=language,
            speaker_names=speaker_names,
            encounter_id=encounter_id,
            save_audio=save_audio,
        )


def get_stt_service() -> STTService:
    return STTService()
