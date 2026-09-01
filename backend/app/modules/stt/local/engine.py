"""
app/modules/stt/local/engine.py
────────────────────────────────
The process-wide local inference engine: one set of models, shared by every
request.

Three concerns are handled here and nowhere else.

**Load once, lazily.** Whisper plus the SpeechBrain VAD and ECAPA models take
seconds to load and hold GPU memory. They load on first use (or at startup when
``STT_MODEL_PRELOAD`` is set) and are then reused, so a busy API never reloads.

**Never block the event loop.** Inference is synchronous, CPU/GPU-bound work.
It runs in a worker thread via ``run_in_executor``, so FastAPI keeps serving
other requests — health checks, SOAP generation — while a transcription runs.

**One job on the GPU at a time.** There is a single device and the models are
not safe to call concurrently. An ``asyncio.Semaphore(1)`` queues requests
rather than letting them collide or exhaust VRAM. Concurrent callers wait; they
do not fail.

Failure policy: a CUDA problem degrades to CPU rather than taking the API down,
because the orchestrator also serves auth, entity extraction and SOAP routes
that have nothing to do with speech.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.errors import ConfigurationError
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class EngineStatus:
    """What the engine is, and whether it is ready — for readiness probes."""

    mode: str
    device: str
    whisper_model: str
    whisper_backend: str
    compute_type: str
    diarization_enabled: bool
    default_num_speakers: int | None
    models_loaded: bool
    dependencies_available: bool
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "device": self.device,
            "whisper_model": self.whisper_model,
            "whisper_backend": self.whisper_backend,
            "compute_type": self.compute_type,
            "diarization_enabled": self.diarization_enabled,
            "default_num_speakers": self.default_num_speakers,
            "models_loaded": self.models_loaded,
            "dependencies_available": self.dependencies_available,
            "detail": self.detail,
        }


class LocalSTTEngine:
    """Owns the diarizer and the transcriber for the lifetime of the process."""

    def __init__(self) -> None:
        self._diarizer: Any = None
        self._transcriber: Any = None
        self._load_lock = threading.Lock()
        self._gpu_semaphore: asyncio.Semaphore | None = None
        self._device: str = settings.resolved_stt_device

    # ── Availability ──────────────────────────────────────────────────────────

    @staticmethod
    def dependencies_available() -> tuple[bool, str | None]:
        """Check the optional ``stt`` extra is installed, without importing it fully."""
        import importlib.util

        missing = [
            name
            for name in ("torch", "speechbrain", "soundfile", "numpy", "sklearn")
            if importlib.util.find_spec(name) is None
        ]
        has_whisper = any(
            importlib.util.find_spec(name) is not None
            for name in ("faster_whisper", "whisper")
        )
        if not has_whisper:
            missing.append("faster_whisper or openai-whisper")

        if missing:
            return False, (
                f"Local STT dependencies are not installed: {', '.join(missing)}. "
                f"Install them with `uv sync --extra stt`, or set "
                f"STT_ENGINE_MODE=remote to use an external STT service."
            )
        return True, None

    def status(self) -> EngineStatus:
        available, detail = self.dependencies_available()
        return EngineStatus(
            mode="local",
            device=self._device,
            whisper_model=settings.WHISPER_MODEL,
            whisper_backend=(
                self._transcriber.backend if self._transcriber else settings.WHISPER_BACKEND
            ),
            compute_type=settings.WHISPER_COMPUTE_TYPE,
            diarization_enabled=settings.DIARIZATION_ENABLED,
            default_num_speakers=settings.DIARIZATION_NUM_SPEAKERS,
            models_loaded=self._diarizer is not None or self._transcriber is not None,
            dependencies_available=available,
            detail=detail,
        )

    # ── Model loading ─────────────────────────────────────────────────────────

    def load(self) -> None:
        """Load models. Idempotent, thread-safe, and falls back to CPU on failure."""
        if self._transcriber is not None:
            return

        available, detail = self.dependencies_available()
        if not available:
            raise ConfigurationError(detail or "Local STT dependencies are unavailable.")

        with self._load_lock:
            if self._transcriber is not None:
                return

            Path(settings.MODEL_CACHE_DIR).mkdir(parents=True, exist_ok=True)

            from app.modules.stt.local.config import config_from_settings
            from app.modules.stt.local.diarizer import SpeechBrainDiarizer
            from app.modules.stt.local.transcribe import WordLevelTranscriber

            try:
                self._load_models(config_from_settings(), SpeechBrainDiarizer, WordLevelTranscriber)
            except Exception as exc:
                if self._device == "cpu":
                    raise ConfigurationError(
                        f"Could not load local STT models: {exc}"
                    ) from exc

                logger.warning(
                    "stt_gpu_load_failed_falling_back_to_cpu",
                    device=self._device,
                    error=str(exc)[:300],
                )
                self._device = "cpu"
                self._diarizer = None
                self._transcriber = None
                config = config_from_settings()
                config.device = "cpu"
                try:
                    self._load_models(config, SpeechBrainDiarizer, WordLevelTranscriber)
                except Exception as cpu_exc:
                    raise ConfigurationError(
                        f"Could not load local STT models on CPU either: {cpu_exc}"
                    ) from cpu_exc

    def _load_models(self, config: Any, diarizer_cls: Any, transcriber_cls: Any) -> None:
        """Instantiate and warm both models on ``config.device``."""
        device = config.device
        # float16 is a GPU-only compute type; CTranslate2 rejects it on CPU.
        compute_type = settings.WHISPER_COMPUTE_TYPE
        if device == "cpu" and compute_type.startswith("float16"):
            compute_type = "int8"

        logger.info(
            "stt_engine_loading",
            device=device,
            whisper_model=settings.WHISPER_MODEL,
            backend=settings.WHISPER_BACKEND,
            compute_type=compute_type,
            diarization=settings.DIARIZATION_ENABLED,
        )

        transcriber = transcriber_cls(
            model_name=settings.WHISPER_MODEL,
            device=device,
            backend=settings.WHISPER_BACKEND,
            compute_type=compute_type,
            language=settings.WHISPER_LANGUAGE or None,
        )
        transcriber.load()

        diarizer = None
        if settings.DIARIZATION_ENABLED:
            diarizer = diarizer_cls(config)
            diarizer.load()

        self._transcriber = transcriber
        self._diarizer = diarizer
        self._device = device
        logger.info("stt_engine_ready", device=device, backend=transcriber.backend)

    # ── Accessors ─────────────────────────────────────────────────────────────

    @property
    def device(self) -> str:
        return self._device

    def transcriber(self) -> Any:
        self.load()
        return self._transcriber

    def diarizer(self) -> Any:
        self.load()
        if self._diarizer is None:
            raise ConfigurationError(
                "Diarization is disabled. Set DIARIZATION_ENABLED=true to use this endpoint."
            )
        return self._diarizer

    # ── Async execution ───────────────────────────────────────────────────────

    def _semaphore(self) -> asyncio.Semaphore:
        """Lazily create the semaphore, bound to the running event loop."""
        if self._gpu_semaphore is None:
            self._gpu_semaphore = asyncio.Semaphore(1)
        return self._gpu_semaphore

    async def run_exclusive(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Run blocking inference in a worker thread, one job at a time."""
        async with self._semaphore():
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


_engine: LocalSTTEngine | None = None
_engine_lock = threading.Lock()


def get_engine() -> LocalSTTEngine:
    """Return the process-wide engine singleton."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = LocalSTTEngine()
    return _engine
