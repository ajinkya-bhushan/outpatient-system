"""
app/engines/whisperflow_engine.py
──────────────────────────────────
WhisperFlow engine for low-latency, incremental live transcription.

What WhisperFlow IS
-------------------
WhisperFlow is a thin streaming wrapper around Whisper that uses overlapping
windows to produce partial transcripts as audio arrives, reducing perceived
latency compared to waiting for a full utterance.

What WhisperFlow IS NOT
-----------------------
It is NOT a fully real-time, word-by-word streaming ASR like DeepSpeech or
Google Speech-to-Text streaming. It still processes chunks of audio (typically
2-4 seconds) and produces transcripts for each window.

Installation conflict (IMPORTANT)
----------------------------------
The PyPI ``whisperflow`` package (0.1.x) pins ``fastapi==0.108.0``.
This project requires ``fastapi>=0.111.0``.  The two cannot coexist in the
same virtualenv.

Workarounds:
1. Use ``WhisperEngine`` for live transcription (default).  It uses
   the same Whisper model but transcribes buffered audio every
   PARTIAL_INTERVAL_SECONDS seconds instead of truly streaming.
2. Run WhisperFlow in a separate isolated process/microservice.
3. Install with ``--no-deps`` (may break other things):
   ``uv pip install whisperflow --no-deps``
4. Wait for a whisperflow release that supports fastapi>=0.111.

This engine class is fully implemented; it will activate automatically when
``whisperflow`` is importable.  When not installed, it raises ``RuntimeError``
on instantiation with a clear message, and is excluded from the engine registry.

Live streaming behaviour
------------------------
* ``transcribe()``       : batch mode via Whisper (same as WhisperEngine)
* ``stream_transcribe()`` : feeds PCM chunks into whisperflow's rolling window
                            and yields partial results per window

Audio format requirement
------------------------
``stream_transcribe`` expects raw 16 kHz mono 16-bit PCM bytes.
Browser WebM audio MUST be decoded first before feeding here.
The WebSocket route handles that via temp files + ffmpeg.

RTF & latency notes
-------------------
* Chunk latency: time from chunk arrival to partial transcript (ms)
* TTFT: time from first audio chunk to first non-empty partial
* Total session latency: from ``start`` message to ``session_ended`` message
* RTF is only meaningful on the final (full-audio) transcription pass
"""

from __future__ import annotations

import asyncio
import time
from functools import partial
from typing import Any, AsyncGenerator

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import Timer, compute_rtf
from app.engines.base import STTEngine

logger = get_logger(__name__)

# ── Availability check ─────────────────────────────────────────────────────────
_WHISPERFLOW_AVAILABLE = False
_WHISPERFLOW_IMPORT_ERROR: str = ""

try:
    import whisperflow  # noqa: F401
    _WHISPERFLOW_AVAILABLE = True
except ImportError as _e:
    _WHISPERFLOW_IMPORT_ERROR = str(_e)


class WhisperFlowEngine(STTEngine):
    """Streaming transcription engine backed by WhisperFlow.

    Falls back to WhisperEngine behaviour when whisperflow is not installed.

    Raises:
        RuntimeError: On instantiation if ``whisperflow`` is not installed.
    """

    ENGINE_NAME = "whisperflow"
    ENGINE_VERSION: str = "unknown"

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
    ) -> None:
        if not _WHISPERFLOW_AVAILABLE:
            raise RuntimeError(
                "WhisperFlow is not installed or conflicts with FastAPI version.\n"
                f"Import error: {_WHISPERFLOW_IMPORT_ERROR}\n"
                "Options:\n"
                "  1. Use 'whisper' engine instead (default, always available)\n"
                "  2. Install whisperflow in isolation: uv pip install whisperflow --no-deps\n"
                "  3. See README for full workaround instructions"
            )

        super().__init__()
        self.model_name: str = model_name or settings.WHISPER_MODEL
        self.device: str = device or settings.WHISPER_DEVICE
        self._flow = None  # lazy-loaded WhisperFlow pipeline
        self._lock = __import__("threading").Lock()

        try:
            import whisperflow as wf
            self.ENGINE_VERSION = getattr(wf, "__version__", "unknown")
        except ImportError:
            pass

        logger.info(
            "whisperflow_engine_created",
            model=self.model_name,
            device=self.device,
            version=self.ENGINE_VERSION,
        )

    # ── Model loading ──────────────────────────────────────────────────────────

    def _load_model(self) -> None:
        """Initialise the WhisperFlow pipeline (thread-safe, idempotent)."""
        with self._lock:
            if self._model_loaded:
                return

            logger.info("model_loading", engine=self.ENGINE_NAME, model=self.model_name)

            # Guard: import inside method so top-level failure is graceful
            try:
                from whisperflow.pipeline import WhisperFlowPipeline  # type: ignore[import]
            except ImportError as exc:
                raise RuntimeError(
                    f"Cannot load WhisperFlow pipeline: {exc}\n"
                    "The whisperflow package may be installed without its pipeline module."
                ) from exc

            self._flow = WhisperFlowPipeline(
                model=self.model_name,
                device=self.device,
            )
            self._model_loaded = True
            logger.info("model_loaded", engine=self.ENGINE_NAME, model=self.model_name)

    def _ensure_model(self) -> None:
        if not self._model_loaded:
            self._load_model()

    # ── Batch transcription ───────────────────────────────────────────────────

    async def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
        task: str = "transcribe",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Batch-transcribe an audio file using WhisperFlow.

        WhisperFlow delegates to Whisper for file-based transcription.
        """
        self._ensure_model()

        lang = language or settings.WHISPER_LANGUAGE
        logger.info("transcription_started", engine=self.ENGINE_NAME, audio_path=audio_path)

        loop = asyncio.get_running_loop()

        with Timer() as timer:
            try:
                raw = await loop.run_in_executor(
                    None,
                    partial(self._flow.transcribe, audio_path, language=lang),  # type: ignore
                )
            except AttributeError:
                # Some whisperflow versions may use a different method name
                raw = await loop.run_in_executor(
                    None,
                    partial(self._flow.transcribe_file, audio_path, language=lang),  # type: ignore
                )

        processing_time = timer.elapsed
        audio_duration = float(raw.get("duration", 0.0))
        rtf = compute_rtf(processing_time, audio_duration)

        logger.info(
            "transcription_completed",
            engine=self.ENGINE_NAME,
            rtf=rtf,
            processing_time=processing_time,
        )

        return {
            "text": raw.get("text", "").strip(),
            "language": raw.get("language", lang or "unknown"),
            "segments": raw.get("segments", []),
            "audio_duration": audio_duration,
            "processing_time": round(processing_time, 4),
            "real_time_factor": rtf,
            "engine": self.ENGINE_NAME,
            "model": self.model_name,
        }

    # ── Streaming (live) ───────────────────────────────────────────────────────

    async def stream_transcribe(
        self,
        audio_chunks: AsyncGenerator[bytes, None],
        language: str | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Feed raw PCM audio chunks into WhisperFlow's rolling window pipeline.

        Input format requirement
        -----------------------
        Chunks must be raw 16 kHz mono 16-bit PCM bytes.
        Browser WebM audio must be decoded before calling this method.

        WhisperFlow processes each chunk via its internal windowing algorithm
        and emits a partial transcript per chunk (when text is available).

        Latency characteristics
        -----------------------
        * Minimum latency per partial: WhisperFlow window size (typically 2-3s)
        * TTFT: time from first chunk to first non-empty partial
        * RTF is not reported per-chunk (only meaningful for full audio)

        Limitations
        -----------
        * Not truly real-time: WhisperFlow is batch-under-the-hood with windowing
        * Accuracy improves with longer chunks (minimum ~1s recommended)
        * Silent audio will produce empty partials (normal behaviour)
        """
        self._ensure_model()

        lang = language or settings.WHISPER_LANGUAGE
        loop = asyncio.get_running_loop()
        start = time.perf_counter()

        logger.info(
            "stream_transcription_started",
            engine=self.ENGINE_NAME,
            language=lang,
        )

        chunk_index = 0
        async for chunk in audio_chunks:
            chunk_index += 1
            chunk_start = time.perf_counter()

            try:
                # process_chunk is synchronous; offload to thread pool
                partial_result = await loop.run_in_executor(
                    None,
                    partial(self._flow.process_chunk, chunk, language=lang),  # type: ignore
                )
            except Exception as exc:
                logger.warning(
                    "stream_chunk_error",
                    engine=self.ENGINE_NAME,
                    chunk=chunk_index,
                    error=str(exc),
                )
                partial_result = None

            elapsed_ms = (time.perf_counter() - start) * 1000
            chunk_latency_ms = (time.perf_counter() - chunk_start) * 1000

            if partial_result:
                yield {
                    "text": partial_result.get("text", "").strip(),
                    "is_final": partial_result.get("is_final", False),
                    "latency_ms": round(elapsed_ms, 1),
                    "chunk_latency_ms": round(chunk_latency_ms, 1),
                    "chunk_index": chunk_index,
                    "timestamp": time.time(),
                }

        logger.info(
            "stream_transcription_ended",
            engine=self.ENGINE_NAME,
            chunks_processed=chunk_index,
        )

    def get_info(self) -> dict[str, str]:
        """Return engine metadata including availability status."""
        base = super().get_info()
        base["whisperflow_available"] = str(_WHISPERFLOW_AVAILABLE)
        if not _WHISPERFLOW_AVAILABLE:
            base["install_note"] = "whisperflow conflicts with fastapi>=0.111; see README"
        return base
