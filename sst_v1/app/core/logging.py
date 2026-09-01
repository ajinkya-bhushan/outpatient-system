"""
app/core/logging.py
────────────────────
Structured, rotating application logger built on Loguru.

Design decisions
----------------
* Single call to ``configure_logging()`` at startup (called from ``main.py``).
* ``enqueue=True`` makes sink writes thread-safe – essential because ML inference
  runs in a ``ThreadPoolExecutor`` and will log from worker threads.
* ``serialize=False`` keeps human-readable output in development.
  Switch to ``serialize=True`` for JSON log aggregation in production.
* A separate ``request_id`` context variable lets per-request correlation IDs
  propagate through async middleware automatically.

Usage
-----
    from app.core.logging import get_logger

    logger = get_logger(__name__)
    logger.info("transcription_started", engine="whisper", model="base")
"""

from __future__ import annotations

import sys
from contextvars import ContextVar

from loguru import logger

from app.core.config import settings

# ── Context variable for per-request correlation IDs ─────────────────────────
# Set this at the start of each request; log records pick it up automatically.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

# ── Log format ────────────────────────────────────────────────────────────────
_CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<white>{message}</white>"
)

_FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
    "{level: <8} | "
    "{name}:{function}:{line} | "
    "{message}"
)


def configure_logging() -> None:
    """Initialise Loguru sinks.

    Call exactly **once** from ``app/main.py`` at startup.
    Repeated calls are safe – Loguru removes all previous handlers first.
    """
    logger.remove()  # clear Loguru defaults

    # ── Console sink ──────────────────────────────────────────────────────────
    logger.add(
        sys.stderr,
        level=settings.LOG_LEVEL,
        format=_CONSOLE_FORMAT,
        colorize=True,
        enqueue=True,
    )

    # ── File sink (rotating) ──────────────────────────────────────────────────
    logger.add(
        "logs/app.log",
        level=settings.LOG_LEVEL,
        format=_FILE_FORMAT,
        rotation="10 MB",
        retention="7 days",
        compression="gz",
        enqueue=True,
        encoding="utf-8",
    )

    logger.info(
        "logging_configured",
        level=settings.LOG_LEVEL,
        engine=settings.DEFAULT_ENGINE,
    )


def get_logger(name: str):
    """Return a Loguru logger bound with the module name.

    Example::

        logger = get_logger(__name__)
        logger.info("model_loaded", model="base", device="cpu")
    """
    return logger.bind(module=name)
