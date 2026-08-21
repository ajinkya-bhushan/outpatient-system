"""Structured logging with optional request correlation IDs."""

from __future__ import annotations

import sys
from contextvars import ContextVar

from loguru import logger

from app.core.config import settings

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

_CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{extra[request_id]}</cyan> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
    "<level>{message}</level>"
)


def _patch_request_id(record) -> None:
    record["extra"].setdefault("request_id", request_id_ctx.get())


def configure_logging() -> None:
    logger.remove()
    logger.configure(extra={"request_id": "-"})
    logger.patch(_patch_request_id)
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
