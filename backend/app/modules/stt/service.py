"""HTTP client for the sst_v1 transcription service.

sst_v1 remains the Whisper engine host. This module does not load models;
it records/uploads audio and returns a transcript through that service.

Endpoints used
--------------
POST {STT_BASE_URL}/api/v1/transcribe   file upload
WS   {STT_BASE_URL}/api/v1/live         live recording
GET  {STT_BASE_URL}/api/v1/health       liveness
GET  {STT_BASE_URL}/api/v1/ready        engine readiness
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.core.errors import UpstreamTimeout, UpstreamUnavailable, ValidationFailed
from app.core.logging import get_logger
from app.modules.stt.schemas import TranscriptResult, TranscriptSegment

logger = get_logger(__name__)


class STTService:
    def __init__(self, base_url: str | None = None, timeout: float | None = None) -> None:
        self.base_url = (base_url or settings.STT_BASE_URL).rstrip("/")
        self.timeout = timeout or settings.STT_TIMEOUT_SECONDS

    def live_url(self) -> str:
        http_url = self.base_url
        if http_url.startswith("https://"):
            return http_url.replace("https://", "wss://", 1) + "/api/v1/live"
        return http_url.replace("http://", "ws://", 1) + "/api/v1/live"

    async def health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/v1/health")
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise UpstreamUnavailable(f"STT service is not reachable at {self.base_url}: {exc}") from exc

    async def transcribe_upload(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str | None = None,
        engine: str | None = None,
        language: str | None = None,
        task: str = "transcribe",
    ) -> TranscriptResult:
        if not file_bytes:
            raise ValidationFailed("Audio file is empty.")
        if len(file_bytes) > settings.max_audio_size_bytes:
            raise ValidationFailed(
                f"Audio exceeds {settings.MAX_AUDIO_SIZE_MB} MB limit."
            )

        data = {
            "engine": engine or settings.DEFAULT_STT_ENGINE,
            "language": language or "",
            "task": task,
        }
        files = {
            "file": (filename, file_bytes, content_type or "application/octet-stream"),
        }

        logger.info("stt_upload_started", filename=filename, engine=data["engine"])
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/transcribe",
                    data=data,
                    files=files,
                )
        except httpx.TimeoutException as exc:
            raise UpstreamTimeout("STT transcription timed out.") from exc
        except httpx.HTTPError as exc:
            raise UpstreamUnavailable(f"STT service request failed: {exc}") from exc

        if response.status_code == 400:
            raise ValidationFailed(response.text)
        if response.status_code >= 400:
            raise UpstreamUnavailable(
                f"STT transcription failed: HTTP {response.status_code} {response.text}"
            )

        payload = response.json()
        segments = [
            TranscriptSegment(
                id=item.get("id", index),
                start=item.get("start", 0.0),
                end=item.get("end", 0.0),
                text=item.get("text", ""),
            )
            for index, item in enumerate(payload.get("segments") or [])
        ]
        result = TranscriptResult(
            text=payload.get("text") or "",
            language=payload.get("language") or "unknown",
            segments=segments,
            audio_duration=payload.get("audio_duration") or 0.0,
            processing_time=payload.get("processing_time") or 0.0,
            real_time_factor=payload.get("real_time_factor") or 0.0,
            engine=payload.get("engine") or data["engine"],
            model=payload.get("model") or "unknown",
            source="upload",
        )
        logger.info(
            "stt_upload_completed",
            engine=result.engine,
            chars=len(result.text),
            rtf=result.real_time_factor,
        )
        return result


def get_stt_service() -> STTService:
    return STTService()
