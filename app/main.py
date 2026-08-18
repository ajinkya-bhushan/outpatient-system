"""
app/main.py
────────────
FastAPI application entry point.

Responsibilities
----------------
* Initialise structured logging (before any other import that might log).
* Create and configure the FastAPI app instance.
* Register all API routers under the /api/v1 prefix.
* Add CORS middleware (permissive for local dev; tighten for production).
* Provide lifespan context for startup / shutdown hooks.

Do NOT put business logic here.  This file wires existing components together.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.ffmpeg_bootstrap import ensure_ffmpeg

# ── Configure logging first ───────────────────────────────────────────────────
configure_logging()
logger = get_logger(__name__)
ensure_ffmpeg()  # patches PATH with imageio-ffmpeg if system ffmpeg absent

# ── Lazy engine warm-up on startup ───────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: run startup hooks, yield, run shutdown hooks."""
    logger.info(
        "application_starting",
        engine=settings.DEFAULT_ENGINE,
        model=settings.WHISPER_MODEL,
        device=settings.WHISPER_DEVICE,
    )

    # Pre-warm the default engine so the first request isn't slow.
    # Comment this out if you prefer true lazy loading at first request.
    try:
        from app.engines import get_engine
        engine = get_engine(settings.DEFAULT_ENGINE)
        logger.info("default_engine_ready", engine=settings.DEFAULT_ENGINE)
    except Exception as exc:
        # Non-fatal: engine will be loaded on first request instead
        logger.warning("engine_prewarm_skipped", reason=str(exc))

    yield  # ← application runs here

    logger.info("application_shutdown")


# ── Create app ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="SST Model Evaluation API",
    description=(
        "Production-quality Speech-to-Text evaluation framework.\n\n"
        "Supports Whisper (local), WhisperFlow (live), OpenAI Whisper (cloud), "
        "and more via a pluggable engine architecture."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Allow all origins in development.  In production, replace "*" with your
# actual frontend domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
from app.api.routes_health import router as health_router  # noqa: E402
from app.api.routes_upload import router as upload_router  # noqa: E402
from app.api.routes_live import router as live_router      # noqa: E402

app.include_router(health_router, prefix="/api/v1")
app.include_router(upload_router, prefix="/api/v1")
app.include_router(live_router,   prefix="/api/v1")

logger.info("routers_registered", prefix="/api/v1")
