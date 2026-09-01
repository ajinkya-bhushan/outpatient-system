"""Structured logging with optional request correlation IDs.

Call sites pass an event name plus keyword metadata::

    logger.info("stt_local_diarize_completed", job_id=..., num_speakers=2)

The patcher below flattens those keywords onto the console line, so the fields
are actually visible rather than silently discarded.

**Never pass transcript text, patient identifiers, or audio content as a log
field.** Encounter audio is PHI; log ids, counts, durations and timings only.
"""

from __future__ import annotations

import sys
from contextvars import ContextVar

from loguru import logger

from app.core.config import settings

NO_REQUEST_ID = "-"

request_id_ctx: ContextVar[str] = ContextVar("request_id", default=NO_REQUEST_ID)

_CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{extra[request_id]}</cyan> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
    "<level>{message}</level>"
    "{extra[context]}"
)

# Consumed by the format string itself, so not repeated as metadata.
_RESERVED_EXTRA = frozenset({"request_id", "logger_name", "context"})


def _patch_record(record) -> None:
    extra = record["extra"]
    # The configured default is itself the placeholder, so it must not be
    # allowed to mask a request id set by the route.
    if extra.get("request_id", NO_REQUEST_ID) == NO_REQUEST_ID:
        extra["request_id"] = request_id_ctx.get()

    fields = " ".join(
        f"{key}={value}" for key, value in extra.items() if key not in _RESERVED_EXTRA
    )
    extra["context"] = f" | {fields}" if fields else ""


def configure_logging() -> None:
    # patcher= is passed to configure() because logger.patch() returns a new
    # logger rather than mutating the global one.
    logger.configure(
        extra={"request_id": NO_REQUEST_ID, "context": ""}, patcher=_patch_record
    )
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.LOG_LEVEL,
        format=_CONSOLE_FORMAT,
        enqueue=True,
        backtrace=False,
        diagnose=False,
    )


def get_logger(name: str):
    return logger.bind(logger_name=name)
