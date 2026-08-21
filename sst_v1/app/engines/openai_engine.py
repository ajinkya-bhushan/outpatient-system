"""
app/engines/openai_engine.py
─────────────────────────────
Optional engine that calls the OpenAI hosted Whisper API.

This engine is useful when:
* Local GPU is unavailable or too slow.
* You want to benchmark cloud inference vs. local.
* You need the highest accuracy without running large models locally.

Requirements
------------
* ``OPENAI_API_KEY`` must be set in ``.env`` or the OS environment.
* Install the optional dependency: ``uv sync --extra openai``

Cost note
---------
The OpenAI Whisper API is priced per minute of audio.
Do not run large-scale benchmarks without tracking API usage.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, AsyncGenerator

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import Timer, compute_rtf
from app.engines.base import STTEngine

logger = get_logger(__name__)

_OPENAI_AVAILABLE = False
try:
    import openai as _openai_pkg  # noqa: F401
    _OPENAI_AVAILABLE = True
except ImportError:
    pass


class OpenAIWhisperEngine(STTEngine):
    """Cloud Whisper engine backed by OpenAI's transcription API.

    Raises:
        RuntimeError: If ``openai`` package is not installed.
        ValueError:   If ``OPENAI_API_KEY`` is not configured.
    """

    ENGINE_NAME = "openai"
    ENGINE_VERSION = "whisper-1"

    def __init__(self) -> None:
        if not _OPENAI_AVAILABLE:
            raise RuntimeError(
                "openai package is not installed. "
                "Run `uv sync --extra openai` to enable this engine."
            )
        if not settings.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY is not set. "
                "Add it to your .env file or export it as an environment variable."
            )

        super().__init__()
        import openai
        self._client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self._model_loaded = True  # no local weights to load

        logger.info("openai_engine_created")

    def _load_model(self) -> None:
        """No-op – OpenAI engine has no local model to load."""
        self._model_loaded = True

    async def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
        task: str = "transcribe",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Call OpenAI Whisper API and return standardised result dict."""
        lang = language or settings.WHISPER_LANGUAGE

        logger.info("transcription_started", engine=self.ENGINE_NAME, audio_path=audio_path)

        with Timer() as timer:
            audio_file = Path(audio_path).open("rb")
            try:
                response = await self._client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=lang,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )
            finally:
                audio_file.close()

        processing_time = timer.elapsed
        audio_duration = float(getattr(response, "duration", 0.0))
        rtf = compute_rtf(processing_time, audio_duration)

        segments = [
            {
                "id": i,
                "start": round(float(s.start), 3),
                "end": round(float(s.end), 3),
                "text": s.text.strip(),
            }
            for i, s in enumerate(getattr(response, "segments", []) or [])
        ]

        logger.info(
            "transcription_completed",
            engine=self.ENGINE_NAME,
            rtf=rtf,
            processing_time=processing_time,
        )

        return {
            "text": response.text.strip(),
            "language": getattr(response, "language", lang or "unknown"),
            "segments": segments,
            "audio_duration": audio_duration,
            "processing_time": round(processing_time, 4),
            "real_time_factor": rtf,
            "engine": self.ENGINE_NAME,
            "model": "whisper-1",
        }

    async def stream_transcribe(
        self,
        audio_chunks: AsyncGenerator[bytes, None],
        language: str | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """OpenAI API does not support true streaming; accumulate then transcribe."""
        import io
        import tempfile, os

        buf = io.BytesIO()
        async for chunk in audio_chunks:
            buf.write(chunk)

        buf.seek(0)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(buf.read())
            tmp_path = tmp.name

        try:
            result = await self.transcribe(tmp_path, language=language)
            yield {**result, "is_final": True, "latency_ms": result["processing_time"] * 1000}
        finally:
            os.unlink(tmp_path)
