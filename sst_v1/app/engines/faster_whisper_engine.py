"""
app/engines/faster_whisper_engine.py
──────────────────────────────────────
Architecture stub for the Faster-Whisper engine (CTranslate2-backed).

Faster-Whisper achieves up to 4× speedup over standard Whisper on CPU and
significant improvement on GPU by using CTranslate2 quantised models.

This file defines the class with:
* Correct inheritance and method signatures matching ``STTEngine``.
* Graceful ``ImportError`` handling when the optional dependency is absent.
* Placeholder implementations that raise ``NotImplementedError`` until
  the engine is fully built out (Phase 2+).

Install the optional dependency::

    uv sync --extra faster

or::

    uv add faster-whisper ctranslate2
"""

from __future__ import annotations

from typing import Any, AsyncGenerator

from app.core.config import settings
from app.core.logging import get_logger
from app.engines.base import STTEngine

logger = get_logger(__name__)

_FASTER_WHISPER_AVAILABLE = False
try:
    from faster_whisper import WhisperModel as _FasterWhisperModel  # noqa: F401
    _FASTER_WHISPER_AVAILABLE = True
except ImportError:
    pass


class FasterWhisperEngine(STTEngine):
    """CTranslate2-backed Whisper engine for high-throughput CPU/GPU inference.

    Status: STUB – not yet implemented.
    The class structure is intentionally complete so that:
    * Engine registry integration works without changes.
    * Developers know exactly what to implement.

    Raises:
        RuntimeError: On instantiation if ``faster-whisper`` is not installed.
        NotImplementedError: On any transcription call (stub).
    """

    ENGINE_NAME = "faster_whisper"
    ENGINE_VERSION = "unknown"

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
        compute_type: str = "int8",
    ) -> None:
        """
        Args:
            model_name:   Whisper model size.
            device:       ``"cpu"`` | ``"cuda"`` | ``"auto"``.
            compute_type: CTranslate2 quantisation mode.
                          ``"int8"`` (CPU) | ``"float16"`` (GPU) | ``"float32"``.
        """
        if not _FASTER_WHISPER_AVAILABLE:
            raise RuntimeError(
                "faster-whisper is not installed. "
                "Run `uv sync --extra faster` to enable this engine."
            )

        super().__init__()
        self.model_name = model_name or settings.WHISPER_MODEL
        self.device = device or settings.WHISPER_DEVICE
        self.compute_type = compute_type
        self._model = None

        logger.info(
            "faster_whisper_engine_created",
            model=self.model_name,
            device=self.device,
            compute_type=self.compute_type,
        )

    def _load_model(self) -> None:
        """Load the CTranslate2 model (stub – to be implemented)."""
        raise NotImplementedError(
            "FasterWhisperEngine._load_model is not yet implemented. "
            "See the Phase 2+ roadmap in README.md."
        )

    async def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
        task: str = "transcribe",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Stub – to be implemented in a future phase."""
        raise NotImplementedError("FasterWhisperEngine.transcribe is not yet implemented.")

    async def stream_transcribe(
        self,
        audio_chunks: AsyncGenerator[bytes, None],
        language: str | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stub – to be implemented in a future phase."""
        raise NotImplementedError("FasterWhisperEngine.stream_transcribe is not yet implemented.")
        yield  # make this an async generator syntactically
