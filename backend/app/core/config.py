"""Application settings loaded from environment / .env."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ROOT = _BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            str(_ROOT / ".env"),
            str(_ROOT / "database" / ".env"),
            str(_BACKEND_DIR / ".env"),
        ),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    HOST: str = "0.0.0.0"
    PORT: int = Field(default=8080, ge=1, le=65535)
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    CORS_ORIGINS: str = "*"
    DATABASE_URL: str = ""
    AUTH_JWT_SECRET: str = "dev-only-change-me-use-32-plus-bytes"
    AUTH_JWT_EXPIRE_SECONDS: int = Field(default=28800, ge=60, le=604800)

    STT_BASE_URL: str = "http://127.0.0.1:8000"
    STT_TIMEOUT_SECONDS: int = Field(default=120, ge=5, le=600)
    DEFAULT_STT_ENGINE: str = "whisper"

    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_DEFAULT_REGION: str = "us-east-1"
    AWS_SESSION_TOKEN: str | None = None

    AAVA_JWT_TOKEN: str | None = None
    AAVA_EXECUTE_ENDPOINT: str = "https://int-ai.aava.ai/agents/execute/agent-executions"
    AAVA_HISTORY_ENDPOINT: str = "https://int-ai.aava.ai/agents/execute/history/execution"
    AAVA_AGENT_ID: str = "54818"
    AAVA_POLL_INTERVAL_SECONDS: int = Field(default=10, ge=1, le=60)
    AAVA_POLL_TIMEOUT_SECONDS: int = Field(default=600, ge=10, le=3600)

    MAX_TRANSCRIPT_CHARS: int = Field(default=20_000, ge=100, le=200_000)
    MAX_AUDIO_SIZE_MB: int = Field(default=50, ge=1, le=500)

    @property
    def cors_origin_list(self) -> list[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]

    @property
    def max_audio_size_bytes(self) -> int:
        return self.MAX_AUDIO_SIZE_MB * 1024 * 1024

    @property
    def aws_configured(self) -> bool:
        return bool(self.AWS_ACCESS_KEY_ID and self.AWS_SECRET_ACCESS_KEY)

    @property
    def aava_configured(self) -> bool:
        return bool(self.AAVA_JWT_TOKEN)


settings = Settings()
