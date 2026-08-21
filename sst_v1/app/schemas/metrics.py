"""
app/schemas/metrics.py
───────────────────────
Pydantic v2 models for benchmark / metrics records.

These are used by:
* The benchmarking utilities (benchmarks/benchmark_upload.py)
* The /api/v1/transcribe response (embedded via TranscriptionResponse)
* CSV/JSON result storage
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class BenchmarkRecord(BaseModel):
    """A single benchmark run entry written to JSON / CSV."""

    model_config = ConfigDict(from_attributes=True)

    # ── Identity ──────────────────────────────────────────────────────────────
    run_id: str = Field(..., description="Unique run identifier (UUID)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # ── Engine / model info ───────────────────────────────────────────────────
    engine: str = Field(..., description="Engine name: whisper | whisperflow | openai | …")
    model: str = Field(..., description="Model size / identifier")
    device: str = Field(..., description="Compute device: cpu | cuda | mps")

    # ── Audio info ────────────────────────────────────────────────────────────
    audio_filename: str = Field(..., description="Original filename of the audio sample")
    audio_duration: float = Field(..., ge=0.0, description="Audio length in seconds")

    # ── Performance ───────────────────────────────────────────────────────────
    processing_time: float = Field(..., ge=0.0, description="Inference wall-clock time (seconds)")
    real_time_factor: float = Field(..., ge=0.0, description="RTF = processing_time / audio_duration")
    time_to_first_token_ms: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Milliseconds from audio start to first partial transcript (live only)",
    )
    total_latency_ms: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="End-to-end latency in milliseconds",
    )

    # ── Transcript quality (when reference is available) ─────────────────────
    detected_language: Optional[str] = Field(default=None)
    reference_transcript: Optional[str] = Field(
        default=None,
        description="Ground-truth transcript (if available); never fabricated",
    )
    hypothesis_transcript: Optional[str] = Field(
        default=None,
        description="Model-produced transcript",
    )
    wer: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Word Error Rate (0.0 = perfect). Only populated when reference_transcript is set",
    )
    cer: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Character Error Rate. Only populated when reference_transcript is set",
    )

    # ── Error tracking ────────────────────────────────────────────────────────
    error: Optional[str] = Field(default=None, description="Error message if transcription failed")
    success: bool = Field(default=True, description="False if this run ended in an error")
