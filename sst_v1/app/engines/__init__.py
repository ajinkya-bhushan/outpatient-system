"""
app/engines/__init__.py
────────────────────────
Engine registry – maps string names to concrete engine classes.

Usage
-----
    from app.engines import get_engine

    engine = get_engine("whisper")
    result = await engine.transcribe("/path/to/audio.wav")

Design decisions
----------------
* ``get_engine()`` returns a **shared singleton** per engine type, enforcing
  the "load once, reuse" requirement without the caller managing state.
* The registry is a plain dict; adding a new engine = one new dict entry.
* Unavailable optional engines (WhisperFlow, FasterWhisper) are registered
  lazily – the ``RuntimeError`` from their ``__init__`` is only raised when
  the caller actually requests that engine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.logging import get_logger
from app.engines.whisper_engine import WhisperEngine

if TYPE_CHECKING:
    from app.engines.base import STTEngine

logger = get_logger(__name__)

# ── Singleton registry ─────────────────────────────────────────────────────────
# Engines are instantiated on first request and cached here.
_registry: dict[str, "STTEngine"] = {}


def get_engine(name: str | None = None) -> "STTEngine":
    """Return (or create) the singleton engine for *name*.

    Args:
        name: One of ``"whisper"`` | ``"whisperflow"`` | ``"openai"`` |
              ``"faster_whisper"``.  Defaults to ``settings.DEFAULT_ENGINE``.

    Returns:
        An initialised ``STTEngine`` instance.

    Raises:
        ValueError:  Unknown engine name.
        RuntimeError: Optional dependency not installed.
    """
    engine_name = (name or settings.DEFAULT_ENGINE).lower()

    if engine_name in _registry:
        return _registry[engine_name]

    logger.info("engine_initialising", engine=engine_name)

    if engine_name == "whisper":
        engine: STTEngine = WhisperEngine()

    elif engine_name == "whisperflow":
        from app.engines.whisperflow_engine import WhisperFlowEngine
        engine = WhisperFlowEngine()

    elif engine_name == "openai":
        from app.engines.openai_engine import OpenAIWhisperEngine
        engine = OpenAIWhisperEngine()

    elif engine_name == "faster_whisper":
        from app.engines.faster_whisper_engine import FasterWhisperEngine
        engine = FasterWhisperEngine()

    else:
        raise ValueError(
            f"Unknown engine '{engine_name}'. "
            f"Available: whisper | whisperflow | openai | faster_whisper"
        )

    _registry[engine_name] = engine
    logger.info("engine_registered", engine=engine_name)
    return engine


def list_engines() -> list[str]:
    """Return names of all engine types (not just instantiated ones)."""
    return ["whisper", "whisperflow", "openai", "faster_whisper"]
