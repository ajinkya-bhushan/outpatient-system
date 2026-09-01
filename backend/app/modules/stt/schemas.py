"""
app/modules/stt/schemas.py
───────────────────────────
Request and response contracts for speech-to-text and speaker diarization.
These models *are* the API contract — FastAPI generates the OpenAPI schema at
``/docs`` directly from them.

``TranscriptResult`` is consumed by :mod:`app.models` and
:mod:`app.services.pipeline`, so changes to it must stay additive: new fields
carry defaults and no existing field changes name, type, or meaning.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ── Plain transcription (existing contract) ───────────────────────────────────


class TranscriptSegment(BaseModel):
    """A timed chunk of transcript as produced by Whisper, with no speaker."""

    id: int
    start: float = 0.0
    end: float = 0.0
    text: str


class TranscriptResult(BaseModel):
    """Result of transcribing audio to text.

    Returned by ``POST /api/v1/stt/transcribe`` and embedded in the pipeline
    response.
    """

    text: str = Field(description="Full transcript with no speaker labels")
    language: str = Field(default="unknown", description="Detected or forced language code")
    segments: list[TranscriptSegment] = Field(
        default_factory=list, description="Timed transcript segments"
    )
    audio_duration: float = Field(default=0.0, description="Audio length in seconds")
    processing_time: float = Field(default=0.0, description="Wall-clock inference seconds")
    real_time_factor: float = Field(
        default=0.0, description="processing_time / audio_duration; below 1.0 beats real time"
    )
    engine: str = Field(default="whisper", description="Engine that produced the transcript")
    model: str = Field(default="unknown", description="Model identifier")
    source: str = Field(default="upload", description="How the audio arrived: upload | live | text")

    # ── Additive fields, populated by the local engine ────────────────────────
    job_id: str | None = Field(
        default=None, description="Storage job id, when the audio was persisted"
    )
    num_speakers: int | None = Field(
        default=None, description="Speakers detected, when diarization ran"
    )


# ── Diarization ───────────────────────────────────────────────────────────────


class SpeakerSegmentOut(BaseModel):
    """Who spoke when. Carries no text — this is the diarization timeline."""

    start: float = Field(description="Segment start in seconds from the top of the recording")
    end: float = Field(description="Segment end in seconds")
    speaker_id: str = Field(description="Anonymous cluster label, e.g. 'speaker_0'")
    speaker_name: str = Field(
        description="Display name if one was supplied, otherwise the speaker_id"
    )


class SpeakerTurnOut(BaseModel):
    """A run of consecutive words attributed to one speaker."""

    speaker_id: str = Field(description="Anonymous cluster label, e.g. 'speaker_0'")
    speaker_name: str = Field(
        description="Display name if one was supplied, otherwise the speaker_id"
    )
    start: float = Field(description="Turn start in seconds")
    end: float = Field(description="Turn end in seconds")
    text: str = Field(description="What this speaker said during the turn")
    confidence: float = Field(
        default=0.0,
        description="Mean Whisper word probability for this turn. Transcription "
        "confidence, not speaker-attribution confidence.",
    )


class AudioMeta(BaseModel):
    """Facts about the submitted audio and where it was stored."""

    filename: str = Field(description="Original upload filename")
    duration: float = Field(description="Audio length in seconds")
    sample_rate: int = Field(default=16_000, description="Sample rate the models consumed")
    size_bytes: int = Field(description="Size of the uploaded bytes")
    stored: bool = Field(description="Whether the audio was persisted to disk")
    stored_path: str | None = Field(
        default=None, description="Server-side path of the converted WAV, when persisted"
    )


class StageTimings(BaseModel):
    """Per-stage diarization timings, for locating a slowdown."""

    vad: float = 0.0
    embedding: float = 0.0
    clustering: float = 0.0


class ProcessingMetrics(BaseModel):
    """Timing breakdown for the whole request."""

    audio_duration: float = Field(description="Audio length in seconds")
    diarization_seconds: float = Field(default=0.0, description="Diarization wall-clock seconds")
    transcription_seconds: float = Field(default=0.0, description="Whisper wall-clock seconds")
    total_seconds: float = Field(
        default=0.0,
        description="End-to-end request seconds: validation, ffmpeg conversion, "
        "any wait for the device, and inference. Under load this exceeds the sum "
        "of the stage times because requests queue for the single GPU.",
    )
    diarization_rtf: float = Field(default=0.0, description="Diarization real-time factor")
    transcription_rtf: float = Field(default=0.0, description="Transcription real-time factor")
    total_rtf: float = Field(default=0.0, description="End-to-end real-time factor")
    stage_times: StageTimings = Field(default_factory=StageTimings)


class EngineInfo(BaseModel):
    """Which models produced this result — needed to interpret any comparison."""

    mode: str = Field(description="local | remote")
    device: str = Field(description="Torch device used, e.g. 'cuda:0' or 'cpu'")
    whisper_backend: str = Field(description="faster_whisper | openai_whisper")
    whisper_model: str = Field(description="Whisper model identifier")
    vad_model: str | None = Field(default=None, description="SpeechBrain VAD source")
    embedding_model: str | None = Field(default=None, description="SpeechBrain ECAPA source")
    clustering_method: str | None = Field(
        default=None, description="spectral | agglomerative | single_speaker_screen | trivial"
    )


class DiarizationDiagnostics(BaseModel):
    """Internals worth surfacing when a result looks wrong."""

    n_vad_regions: int | None = None
    n_subsegments: int | None = None
    mean_pairwise_cosine: float | None = Field(
        default=None,
        description="Mean cosine similarity between speaker embeddings. High values "
        "on a multi-speaker recording mean the voices were hard to tell apart.",
    )
    clustering_pval: float | None = None
    oracle_num_speakers: int | None = Field(
        default=None, description="Speaker count supplied by the caller, if any"
    )
    unknown_speaker_words: int = Field(
        default=0, description="Words that could not be attributed to any speaker"
    )


class DiarizedTranscriptResponse(BaseModel):
    """Speaker-labelled transcript — the response of ``POST /api/v1/stt/diarize``."""

    job_id: str = Field(description="Storage job id; use it with /api/v1/stt/jobs/{job_id}")
    encounter_id: str | None = Field(default=None, description="Caller-supplied encounter id")
    created_at: str = Field(description="UTC ISO-8601 completion timestamp")

    text: str = Field(description="Full transcript with no speaker labels")
    labelled_text: str = Field(description="Transcript rendered as 'Speaker: text' lines")
    language: str = Field(description="Detected or forced language code")

    num_speakers: int = Field(description="Number of distinct speakers found")
    speakers: list[str] = Field(description="Speaker labels present in the result")
    turns: list[SpeakerTurnOut] = Field(description="Speaker-labelled transcript turns")
    segments: list[SpeakerSegmentOut] = Field(
        description="Diarization timeline without text (who spoke when)"
    )

    audio: AudioMeta
    metrics: ProcessingMetrics
    engine: EngineInfo
    diagnostics: DiarizationDiagnostics = Field(default_factory=DiarizationDiagnostics)


# ── Job listing ───────────────────────────────────────────────────────────────


class JobSummary(BaseModel):
    """One stored job, without the transcript."""

    job_id: str
    created_date: str = Field(description="UTC date directory the job was stored under")
    created_at: str | None = None
    encounter_id: str | None = None
    language: str | None = None
    num_speakers: int | None = None
    audio_duration: float | None = None
    has_result: bool = True
    has_audio: bool = True


class JobListResponse(BaseModel):
    """Paginated list of stored jobs."""

    total: int = Field(description="Total stored jobs")
    limit: int
    offset: int
    jobs: list[JobSummary]


class EngineStatusResponse(BaseModel):
    """Engine and model readiness, served by ``GET /api/v1/stt/engine``."""

    mode: str
    device: str
    whisper_model: str
    whisper_backend: str
    compute_type: str
    diarization_enabled: bool
    default_num_speakers: int | None
    models_loaded: bool
    dependencies_available: bool
    detail: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
