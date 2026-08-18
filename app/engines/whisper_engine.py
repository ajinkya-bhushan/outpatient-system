"""
app/engines/whisper_engine.py
──────────────────────────────
Concrete Whisper engine (local inference via openai-whisper).

Key design decisions
--------------------
1. **Lazy loading** – the model is downloaded/loaded on the *first* inference
   call, not at import time.  This keeps API startup fast.
2. **Load-once** – the model object is stored as an instance attribute and
   reused for all subsequent requests.  No per-request reload.
3. **Thread-pool offload** – ``whisper.model.transcribe()`` is synchronous and
   CPU/GPU-bound.  We run it in ``asyncio``'s default ``ThreadPoolExecutor``
   via ``asyncio.get_event_loop().run_in_executor(None, …)`` so the FastAPI
   event loop is never blocked.
4. **Thread safety** – a ``threading.Lock`` around ``_load_model`` prevents
   duplicate concurrent loads when multiple requests arrive before the first
   load completes.
5. **Configurable** – model size, device, language, and task are all driven by
   ``settings`` (environment variables), with per-call overrides supported.
"""

from __future__ import annotations

import asyncio
import subprocess
import threading
from functools import partial
from typing import Any, AsyncGenerator

import whisper

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import Timer, compute_rtf
from app.engines.base import STTEngine

logger = get_logger(__name__)

# Supported audio extensions by openai-whisper (ffmpeg handles conversion)
SUPPORTED_EXTENSIONS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg", ".flac"}


class WhisperEngine(STTEngine):
    """Local Whisper inference engine.

    Instantiate once and reuse across requests.

    Example::

        engine = WhisperEngine()
        result = await engine.transcribe("/tmp/audio.wav")
        print(result["text"])
    """

    ENGINE_NAME = "whisper"
    ENGINE_VERSION = whisper.__version__ if hasattr(whisper, "__version__") else "unknown"

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
    ) -> None:
        """
        Args:
            model_name: Whisper model size.  Defaults to ``settings.WHISPER_MODEL``.
            device:     Torch device string.  Defaults to ``settings.WHISPER_DEVICE``.
        """
        super().__init__()
        self.model_name: str = model_name or settings.WHISPER_MODEL
        self.device: str = device or settings.WHISPER_DEVICE
        self._model: whisper.Whisper | None = None
        self._lock = threading.Lock()

        logger.info(
            "whisper_engine_created",
            model=self.model_name,
            device=self.device,
        )

    # ── Model loading ─────────────────────────────────────────────────────────

    def _load_model(self) -> None:
        """Load Whisper model weights (thread-safe, idempotent)."""
        with self._lock:
            if self._model_loaded:
                return  # another thread beat us here

            logger.info("model_loading", engine=self.ENGINE_NAME, model=self.model_name, device=self.device)
            self._model = whisper.load_model(self.model_name, device=self.device)
            self._model_loaded = True
            logger.info("model_loaded", engine=self.ENGINE_NAME, model=self.model_name, device=self.device)

    def _ensure_model(self) -> None:
        """Ensure the model is loaded before use."""
        if not self._model_loaded:
            self._load_model()

    # ── Transcription (file-based) ────────────────────────────────────────────

    async def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
        task: str = "transcribe",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Transcribe an audio file asynchronously.

        The blocking Whisper call is offloaded to a thread-pool executor so
        the FastAPI event loop is never blocked.

        Args:
            audio_path: Path to the audio file.
            language:   BCP-47 language code or None for auto-detection.
            task:       ``"transcribe"`` | ``"translate"``.

        Returns:
            TranscriptionResponse-compatible dict.
        """
        self._ensure_model()

        # Resolve language / task with fallback to settings
        lang = language or settings.WHISPER_LANGUAGE
        task = task or settings.WHISPER_TASK

        logger.info(
            "transcription_started",
            engine=self.ENGINE_NAME,
            model=self.model_name,
            audio_path=audio_path,
            language=lang,
            task=task,
        )

        loop = asyncio.get_running_loop()

        with Timer() as timer:
            # Run the blocking call in a thread-pool – keeps event loop free
            raw_result: dict = await loop.run_in_executor(
                None,
                partial(
                    self._model.transcribe,  # type: ignore[union-attr]
                    audio_path,
                    language=lang,
                    task=task,
                    verbose=False,
                    **kwargs,
                ),
            )

        audio_duration = self._extract_audio_duration(raw_result, audio_path)
        processing_time = timer.elapsed
        rtf = compute_rtf(processing_time, audio_duration)

        result = {
            "text": raw_result.get("text", "").strip(),
            "language": raw_result.get("language", lang or "unknown"),
            "segments": self._format_segments(raw_result.get("segments", [])),
            "audio_duration": audio_duration,
            "processing_time": round(processing_time, 4),
            "real_time_factor": rtf,
            "engine": self.ENGINE_NAME,
            "model": self.model_name,
        }

        logger.info(
            "transcription_completed",
            engine=self.ENGINE_NAME,
            model=self.model_name,
            audio_duration=audio_duration,
            processing_time=processing_time,
            rtf=rtf,
            language=result["language"],
        )

        return result

    # ── Streaming (live) – basic implementation ───────────────────────────────

    async def stream_transcribe(
        self,
        audio_chunks: AsyncGenerator[bytes, None],
        language: str | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Buffer incoming audio chunks and yield partial results.

        Note: Whisper is a batch model; for true streaming use WhisperFlow.
        This implementation accumulates chunks and transcribes on demand.

        Yields:
            Partial result dict per chunk batch.
        """
        import io
        import tempfile
        import os

        self._ensure_model()

        lang = language or settings.WHISPER_LANGUAGE
        buffer = io.BytesIO()
        chunk_count = 0
        loop = asyncio.get_running_loop()
        start_time = loop.time()

        async for chunk in audio_chunks:
            buffer.write(chunk)
            chunk_count += 1

            # Every 10 chunks (~1-2s of audio), attempt a partial transcription
            if chunk_count % 10 == 0:
                buffer.seek(0)
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp.write(buffer.read())
                    tmp_path = tmp.name

                try:
                    raw = await loop.run_in_executor(
                        None,
                        partial(self._model.transcribe, tmp_path, language=lang, verbose=False),  # type: ignore
                    )
                    elapsed_ms = (loop.time() - start_time) * 1000
                    yield {
                        "text": raw.get("text", "").strip(),
                        "is_final": False,
                        "latency_ms": round(elapsed_ms, 1),
                    }
                finally:
                    os.unlink(tmp_path)
                    buffer.seek(0, 2)  # seek to end so writes continue appending

        # Final pass over all buffered audio
        buffer.seek(0)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(buffer.read())
            tmp_path = tmp.name

        try:
            raw = await loop.run_in_executor(
                None,
                partial(self._model.transcribe, tmp_path, language=lang, verbose=False),  # type: ignore
            )
            elapsed_ms = (loop.time() - start_time) * 1000
            yield {
                "text": raw.get("text", "").strip(),
                "is_final": True,
                "latency_ms": round(elapsed_ms, 1),
            }
        finally:
            os.unlink(tmp_path)

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _extract_audio_duration(raw_result: dict, audio_path: str = "") -> float:
        """Extract audio duration in seconds.

        Priority:
        1. Last segment ``end`` time from Whisper output (most accurate).
        2. ffprobe metadata (fallback for silent/empty audio).
        3. 0.0 when both sources fail.
        """
        segments = raw_result.get("segments", [])
        if segments:
            last = segments[-1]
            dur = float(last.get("end", 0.0))
            if dur > 0:
                return round(dur, 3)

        # Fallback: ask ffprobe
        if audio_path:
            try:
                import json as _json
                result = subprocess.run(
                    [
                        "ffprobe", "-v", "quiet",
                        "-print_format", "json",
                        "-show_format",
                        audio_path,
                    ],
                    capture_output=True, text=True, timeout=15,
                )
                if result.returncode == 0:
                    info = _json.loads(result.stdout)
                    dur = float(info.get("format", {}).get("duration", 0.0))
                    return round(dur, 3)
            except Exception:  # ffprobe absent or failed – non-fatal
                pass

        return 0.0

    @staticmethod
    def _format_segments(segments: list[dict]) -> list[dict]:
        """Return only the fields we expose in our API schema."""
        return [
            {
                "id": seg.get("id", i),
                "start": round(float(seg.get("start", 0.0)), 3),
                "end": round(float(seg.get("end", 0.0)), 3),
                "text": seg.get("text", "").strip(),
            }
            for i, seg in enumerate(segments)
        ]
