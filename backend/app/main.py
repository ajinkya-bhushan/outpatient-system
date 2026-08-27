"""FastAPI entry point for the outpatient documentation backend."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes_auth import router as auth_router
from app.api.routes_comprehend import router as comprehend_router
from app.api.routes_health import router as health_router
from app.api.routes_pipeline import router as pipeline_router
from app.api.routes_soap import router as soap_router
from app.api.routes_stt import router as stt_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Optionally warm the local STT models so the first request is not slow.

    Controlled by ``STT_MODEL_PRELOAD``; failures are logged, never fatal, since
    the other routes do not depend on speech models.
    """
    from app.modules.stt.service import get_stt_service

    get_stt_service().preload()
    yield


app = FastAPI(
    title="Outpatient Documentation API",
    description=(
        "Record or upload an encounter, transcribe it with speaker diarization "
        "(SpeechBrain + Whisper), extract clinical entities with Amazon "
        "Comprehend Medical, and draft a SOAP note."
    ),
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(stt_router, prefix="/api/v1")
app.include_router(comprehend_router, prefix="/api/v1")
app.include_router(soap_router, prefix="/api/v1")
app.include_router(pipeline_router, prefix="/api/v1")


@app.exception_handler(Exception)
async def unhandled_error(_request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_error", error=str(exc), exc_info=True)
    return JSONResponse(status_code=500, content={"error": "internal_error", "detail": str(exc)})


logger.info("backend_ready", version=__version__)
