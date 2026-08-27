"""Application settings loaded from environment / .env."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
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

    # ── Speech-to-text engine selection ──────────────────────────────────────
    # "local"  – load SpeechBrain + Whisper in this process (needs the `stt` extra)
    # "remote" – proxy to the sst_v1 service at STT_BASE_URL (legacy behaviour)
    STT_ENGINE_MODE: Literal["local", "remote"] = "local"

    # Used only when STT_ENGINE_MODE=remote.
    STT_BASE_URL: str = "http://127.0.0.1:8000"
    STT_TIMEOUT_SECONDS: int = Field(default=120, ge=5, le=600)
    DEFAULT_STT_ENGINE: str = "whisper"

    # ── Local inference: device and models ───────────────────────────────────
    STT_DEVICE: Literal["auto", "cuda", "cpu"] = "auto"
    STT_MODEL_PRELOAD: bool = False

    WHISPER_MODEL: str = "small.en"
    WHISPER_BACKEND: Literal["faster_whisper", "openai_whisper"] = "faster_whisper"
    WHISPER_COMPUTE_TYPE: str = "float16"
    WHISPER_LANGUAGE: str = "en"

    # ── Local inference: diarization ─────────────────────────────────────────
    DIARIZATION_ENABLED: bool = True
    # Outpatient encounters are usually two-party (clinician + patient) and
    # supplying the count is markedly more reliable than estimating it: on the
    # most confusable evaluation pair, DER fell from 14.59% to 0.40% once the
    # count was given. Set to None/empty to fall back to eigen-gap estimation.
    DIARIZATION_NUM_SPEAKERS: int | None = Field(default=2, ge=1, le=20)
    DIARIZATION_MIN_SPEAKERS: int = Field(default=1, ge=1, le=20)
    DIARIZATION_MAX_SPEAKERS: int = Field(default=6, ge=2, le=20)
    DIARIZATION_WINDOW_SEC: float = Field(default=1.5, gt=0.0, le=10.0)
    DIARIZATION_SHIFT_SEC: float = Field(default=0.75, gt=0.0, le=10.0)
    DIARIZATION_VAD_SOURCE: str = "speechbrain/vad-crdnn-libriparty"
    DIARIZATION_EMBEDDING_SOURCE: str = "speechbrain/spkrec-ecapa-voxceleb"

    # ── Local storage ────────────────────────────────────────────────────────
    # Uploaded encounter audio is PHI. Local disk is a prototype measure only;
    # retention and encryption at rest are still open (see FEATURE_SPEC §26).
    AUDIO_STORAGE_DIR: str = str(_BACKEND_DIR / "data" / "audio")
    MODEL_CACHE_DIR: str = str(_BACKEND_DIR / "data" / "models")

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
    MAX_AUDIO_DURATION_SECONDS: int = Field(default=3600, ge=1, le=14_400)

    @field_validator("DIARIZATION_NUM_SPEAKERS", mode="before")
    @classmethod
    def _blank_speaker_count_means_auto(cls, value: object) -> object:
        """Treat an empty env value as "estimate the speaker count"."""
        if isinstance(value, str) and value.strip().lower() in {"", "none", "null", "auto"}:
            return None
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]

    @property
    def max_audio_size_bytes(self) -> int:
        return self.MAX_AUDIO_SIZE_MB * 1024 * 1024

    @property
    def stt_is_local(self) -> bool:
        return self.STT_ENGINE_MODE == "local"

    @property
    def resolved_stt_device(self) -> str:
        """Torch device string, resolving ``auto`` against the running host.

        Falls back to CPU whenever CUDA is unavailable so the API still starts
        on a machine without a GPU.
        """
        if self.STT_DEVICE != "auto":
            return "cuda:0" if self.STT_DEVICE == "cuda" else self.STT_DEVICE
        try:
            import torch

            return "cuda:0" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"

    @property
    def aws_configured(self) -> bool:
        return bool(self.AWS_ACCESS_KEY_ID and self.AWS_SECRET_ACCESS_KEY)

    @property
    def aava_configured(self) -> bool:
        return bool(self.AAVA_JWT_TOKEN)


settings = Settings()
