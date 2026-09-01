"""
app/engines/base.py
────────────────────
Abstract interface for every Speech-to-Text engine.

Design rationale
----------------
* Every concrete engine (Whisper, WhisperFlow, OpenAI, FasterWhisper, …)
  must subclass ``STTEngine`` and implement the two abstract methods.
* The API routes import ``STTEngine`` and call ``transcribe`` / ``stream_transcribe``
  without knowing *which* engine is in use → clean dependency inversion.
* ``get_info()`` is a concrete helper that all engines inherit; each engine
  overrides only the class-level attributes to fill in the info dict.
* Lazy loading is enforced by design: ``_load_model()`` is called on first use,
  not at import time.  This keeps startup time fast and avoids loading GPU
  memory for engines that are never used.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator


class STTEngine(ABC):
    """Abstract base class for Speech-to-Text engines.

    Subclasses must implement:
        ``transcribe``        – batch / file-based transcription
        ``stream_transcribe`` – streaming / live transcription (async generator)

    Subclasses should set:
        ``ENGINE_NAME``  – human-readable engine identifier (e.g. "whisper")
        ``ENGINE_VERSION`` – version string surfaced in API responses
    """

    ENGINE_NAME: str = "base"
    ENGINE_VERSION: str = "0.0.0"

    def __init__(self) -> None:
        self._model_loaded: bool = False

    # ── Abstract methods ──────────────────────────────────────────────────────

    @abstractmethod
    async def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
        task: str = "transcribe",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Transcribe an audio file.

        Args:
            audio_path: Absolute path to a supported audio file.
            language:   BCP-47 language code (e.g. "en") or ``None`` for
                        automatic detection.
            task:       ``"transcribe"`` or ``"translate"`` (to English).
            **kwargs:   Engine-specific options forwarded verbatim.

        Returns:
            A dict with keys:
                text            (str)   – full transcript
                language        (str)   – detected/forced language code
                segments        (list)  – list of timed segment dicts
                audio_duration  (float) – seconds
                processing_time (float) – wall-clock seconds
                real_time_factor(float) – processing_time / audio_duration
                engine          (str)   – ENGINE_NAME
                model           (str)   – model identifier used
        """
        ...

    @abstractmethod
    async def stream_transcribe(
        self,
        audio_chunks: AsyncGenerator[bytes, None],
        language: str | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield partial transcription results from an audio stream.

        Args:
            audio_chunks: Async generator producing raw PCM/audio bytes.
            language:     Force language or ``None`` for auto-detection.
            **kwargs:     Engine-specific options.

        Yields:
            Partial result dicts with keys:
                text        (str)  – accumulated transcript so far
                is_final    (bool) – True on the last chunk
                latency_ms  (float)– milliseconds since first chunk
        """
        ...

    # ── Concrete helpers ──────────────────────────────────────────────────────

    def get_info(self) -> dict[str, str]:
        """Return basic metadata about this engine instance.

        Surfaced by the ``/api/v1/health`` endpoint.
        """
        return {
            "engine": self.ENGINE_NAME,
            "version": self.ENGINE_VERSION,
            "model_loaded": str(self._model_loaded),
        }

    @abstractmethod
    def _load_model(self) -> None:
        """Load the underlying model into memory.

        Called lazily on the first ``transcribe`` or ``stream_transcribe`` call.
        Implementations must set ``self._model_loaded = True`` when done.
        """
        ...
