"""
app/core/config.py
──────────────────
Centralised, validated configuration using Pydantic Settings v2.

All values can be set via:
  1. A real `.env` file in the project root.
  2. OS-level environment variables (override .env).
  3. Constructor kwargs (useful in tests).

Usage
-----
    from app.core.config import settings

    print(settings.WHISPER_MODEL)   # "base" (default)
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # silently ignore unknown env vars
    )

    # ── Whisper (local) ──────────────────────────────────────────────────────
    WHISPER_MODEL: str = Field(
        default="base",
        description="Whisper model size: tiny|base|small|medium|large|large-v2|large-v3",
    )
    WHISPER_DEVICE: str = Field(
        default="cpu",
        description="Torch device: cpu | cuda | mps",
    )
    WHISPER_LANGUAGE: str | None = Field(
        default=None,
        description="Force language code (e.g. 'en') or None for auto-detection",
    )
    WHISPER_TASK: Literal["transcribe", "translate"] = Field(
        default="transcribe",
        description="'transcribe' keeps original language; 'translate' forces English output",
    )

    # ── Optional / external engines ──────────────────────────────────────────
    OPENAI_API_KEY: str | None = Field(
        default=None,
        description="OpenAI API key – only required for the OpenAI engine",
    )

    # ── Default engine selection ──────────────────────────────────────────────
    DEFAULT_ENGINE: Literal["whisper", "whisperflow", "openai", "faster_whisper"] = Field(
        default="whisper",
        description="Engine used when the caller does not specify one explicitly",
    )

    # ── Upload limits ─────────────────────────────────────────────────────────
    MAX_AUDIO_SIZE_MB: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum accepted audio file size in megabytes",
    )
    MAX_AUDIO_DURATION_SECONDS: int = Field(
        default=300,
        ge=1,
        le=3600,
        description="Maximum accepted audio duration in seconds",
    )

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Loguru / stdlib logging level",
    )

    # ── Server ────────────────────────────────────────────────────────────────
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000, ge=1, le=65535)

    # ── Streamlit ─────────────────────────────────────────────────────────────
    API_BASE_URL: str = Field(
        default="http://localhost:8000",
        description="Backend API URL used by the Streamlit frontend",
    )

    # ── Derived helpers ───────────────────────────────────────────────────────
    @property
    def max_audio_size_bytes(self) -> int:
        """MAX_AUDIO_SIZE_MB expressed in bytes for easy comparison."""
        return self.MAX_AUDIO_SIZE_MB * 1024 * 1024

    @field_validator("WHISPER_LANGUAGE", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v: str | None) -> str | None:
        """Treat empty string from .env as None (auto-detect)."""
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


# Module-level singleton – import this everywhere, do NOT re-instantiate.
settings = Settings()
