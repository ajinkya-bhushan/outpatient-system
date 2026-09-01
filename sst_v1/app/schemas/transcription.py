"""
app/schemas/transcription.py
──────────────────────────────
Pydantic v2 models for the transcription API request/response.

All models use ``model_config = ConfigDict(from_attributes=True)`` so they
can be constructed directly from ORM objects or plain dicts interchangeably.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ── Segment ───────────────────────────────────────────────────────────────────

class Segment(BaseModel):
    """A single timed transcript segment."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Zero-based segment index")
    start: float = Field(..., ge=0.0, description="Segment start time in seconds")
    end: float = Field(..., ge=0.0, description="Segment end time in seconds")
    text: str = Field(..., description="Transcript text for this segment")


# ── Response ──────────────────────────────────────────────────────────────────

class TranscriptionResponse(BaseModel):
    """Full transcription result returned by POST /api/v1/transcribe."""

    model_config = ConfigDict(from_attributes=True)

    text: str = Field(..., description="Full concatenated transcript")
    language: str = Field(..., description="Detected or forced BCP-47 language code")
    segments: list[Segment] = Field(default_factory=list, description="Timed segments")

    audio_duration: float = Field(..., ge=0.0, description="Audio length in seconds")
    processing_time: float = Field(..., ge=0.0, description="Inference wall-clock time in seconds")
    real_time_factor: float = Field(
        ...,
        ge=0.0,
        description="RTF = processing_time / audio_duration.  <1 = faster than real-time",
    )

    engine: str = Field(..., description="Engine used (whisper | whisperflow | openai | …)")
    model: str = Field(..., description="Model identifier (e.g. base, large-v3)")


# ── Live / streaming ──────────────────────────────────────────────────────────

class PartialTranscriptEvent(BaseModel):
    """WebSocket message emitted by the live transcription endpoint."""

    model_config = ConfigDict(from_attributes=True)

    text: str = Field(..., description="Accumulated transcript text so far")
    is_final: bool = Field(False, description="True when this is the final result for the session")
    latency_ms: float = Field(0.0, ge=0.0, description="Milliseconds since the session started")


# ── Request helpers ───────────────────────────────────────────────────────────

class TranscriptionRequest(BaseModel):
    """Query parameters / form fields that accompany a file upload."""

    engine: str = Field(default="whisper", description="Engine to use")
    language: str | None = Field(default=None, description="Force language or None for auto")
    task: str = Field(default="transcribe", description="transcribe | translate")
