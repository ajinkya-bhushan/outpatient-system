"""Pydantic models for STT results."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    id: int
    start: float = 0.0
    end: float = 0.0
    text: str


class TranscriptResult(BaseModel):
    text: str
    language: str = "unknown"
    segments: list[TranscriptSegment] = Field(default_factory=list)
    audio_duration: float = 0.0
    processing_time: float = 0.0
    real_time_factor: float = 0.0
    engine: str = "whisper"
    model: str = "unknown"
    source: str = "upload"
