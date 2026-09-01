"""
app/modules/stt/local/runner.py
────────────────────────────────
Request-level orchestration for local inference: bytes in, contract objects out.

Where :mod:`app.modules.stt.local.engine` owns the *models* (load once, one job
on the GPU at a time), this module owns a single *job*:

    validate → persist → convert to 16 kHz mono → diarize + transcribe
             → align words to speakers → build response → persist result

Both models read the same converted WAV. That matters: word-to-speaker
alignment compares Whisper word timestamps against SpeechBrain segment
boundaries, so the two must share one time base.

Diarization and transcription both run inside a single worker-thread call so the
pair is serialised together on the device rather than interleaving.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.errors import ValidationFailed
from app.core.logging import get_logger
from app.modules.stt.local import storage
from app.modules.stt.local.audio import (
    TARGET_SAMPLE_RATE,
    convert_to_wav16k_mono,
    probe_duration,
    validate_duration,
    validate_upload,
)
from app.modules.stt.local.engine import get_engine
from app.modules.stt.schemas import (
    AudioMeta,
    DiarizationDiagnostics,
    DiarizedTranscriptResponse,
    EngineInfo,
    ProcessingMetrics,
    SpeakerSegmentOut,
    SpeakerTurnOut,
    StageTimings,
    TranscriptResult,
    TranscriptSegment,
)

logger = get_logger(__name__)


@dataclass
class _PreparedAudio:
    """A validated, converted job ready for inference."""

    job_id: str
    wav_path: Path
    duration: float
    extension: str
    stored: storage.StoredAudio | None
    cleanup: Any = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_num_speakers(requested: int | None) -> int | None:
    """Decide the speaker count to hand the clusterer.

    An explicit request wins; otherwise the configured default applies. ``None``
    means "estimate it", which is measurably less reliable than supplying a
    count, so the default is deliberately not ``None``.
    """
    if requested is not None and requested > 0:
        return requested
    if requested is not None and requested <= 0:
        return None  # explicit request to auto-estimate
    return settings.DIARIZATION_NUM_SPEAKERS


def _prepare(file_bytes: bytes, filename: str, save_audio: bool) -> _PreparedAudio:
    """Validate the upload, put it on disk, and normalise it to 16 kHz mono WAV.

    The audio must exist as a file regardless of ``save_audio``: ffmpeg and
    SpeechBrain's VAD are both file-based. When persistence is declined the
    file lands in a temporary directory that is removed afterwards.
    """
    extension = validate_upload(filename, len(file_bytes))

    if save_audio:
        stored = storage.save_upload(file_bytes, extension)
        original_path = stored.original_path
        wav_path = stored.wav_path
        cleanup = None
        job_id = stored.job_id
    else:
        stored = None
        cleanup = storage.temporary_workspace()
        workspace = Path(cleanup.name)
        job_id = storage.new_job_id()
        original_path = workspace / f"original{extension}"
        original_path.write_bytes(file_bytes)
        wav_path = workspace / "audio.wav"

    try:
        duration = probe_duration(original_path)
        validate_duration(duration)
        convert_to_wav16k_mono(original_path, wav_path)
    except Exception:
        # A rejected upload must not leave an orphan job directory: it would
        # show up in /jobs with no result and accumulate PHI indefinitely.
        if cleanup is not None:
            cleanup.cleanup()
        elif stored is not None:
            storage.delete_job(stored.job_id)
        raise

    return _PreparedAudio(
        job_id=job_id,
        wav_path=wav_path,
        duration=duration,
        extension=extension,
        stored=stored,
        cleanup=cleanup,
    )


# ── Plain transcription ───────────────────────────────────────────────────────


async def transcribe(
    file_bytes: bytes,
    filename: str,
    language: str | None = None,
    task: str = "transcribe",
    save_audio: bool = True,
) -> TranscriptResult:
    """Transcribe audio to text, without speaker labels."""
    if task and task != "transcribe":
        raise ValidationFailed(
            f"Local STT supports task='transcribe' only, not {task!r}. "
            f"Use STT_ENGINE_MODE=remote for translation."
        )

    engine = get_engine()
    # Clock the whole request, not just inference: validation, conversion and
    # any wait for the device are latency the caller actually experiences.
    started = time.perf_counter()
    prepared = _prepare(file_bytes, filename, save_audio)

    try:
        transcription = await engine.run_exclusive(
            engine.transcriber().transcribe,
            str(prepared.wav_path),
            language=language or settings.WHISPER_LANGUAGE or None,
        )
        total_seconds = time.perf_counter() - started

        result = TranscriptResult(
            text=transcription.text,
            language=transcription.language,
            segments=[
                TranscriptSegment(
                    id=index,
                    start=segment["start"],
                    end=segment["end"],
                    text=segment["text"],
                )
                for index, segment in enumerate(transcription.segments)
            ],
            audio_duration=prepared.duration,
            processing_time=round(total_seconds, 3),
            real_time_factor=round(total_seconds / prepared.duration, 4)
            if prepared.duration
            else 0.0,
            engine=f"local:{transcription.backend}",
            model=transcription.model,
            source="upload",
            job_id=prepared.job_id if prepared.stored else None,
        )

        if prepared.stored is not None:
            storage.save_result(prepared.stored, result.model_dump())

        logger.info(
            "stt_local_transcribe_completed",
            job_id=prepared.job_id,
            duration=round(prepared.duration, 2),
            rtf=result.real_time_factor,
            chars=len(result.text),
        )
        return result
    finally:
        if prepared.cleanup is not None:
            prepared.cleanup.cleanup()
        elif prepared.stored is not None and prepared.stored.cleanup is not None:
            prepared.stored.cleanup.cleanup()


# ── Transcription + diarization ───────────────────────────────────────────────


def _run_diarized_job(
    wav_path: str,
    num_speakers: int | None,
    language: str | None,
    min_speakers: int | None,
    max_speakers: int | None,
) -> tuple[Any, Any]:
    """Blocking half of the diarized job: both models, one device, one thread.

    Per-request speaker bounds are applied here rather than by the caller
    because the diarizer is a process-wide singleton: this function body runs
    under the engine's semaphore, so one request's bounds cannot leak into
    another's.
    """
    engine = get_engine()
    diarizer = engine.diarizer()
    clustering = diarizer.config.clustering
    original_bounds = (clustering.min_speakers, clustering.max_speakers)

    try:
        if min_speakers is not None:
            clustering.min_speakers = min_speakers
        if max_speakers is not None:
            clustering.max_speakers = max_speakers

        diarization = diarizer.diarize(wav_path, num_speakers=num_speakers)
        transcription = engine.transcriber().transcribe(wav_path, language=language)
        return diarization, transcription
    finally:
        clustering.min_speakers, clustering.max_speakers = original_bounds


async def diarize(
    file_bytes: bytes,
    filename: str,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    language: str | None = None,
    speaker_names: dict[str, str] | None = None,
    encounter_id: str | None = None,
    save_audio: bool = True,
) -> DiarizedTranscriptResponse:
    """Produce a speaker-labelled transcript."""
    # Acquire the engine before importing the alignment helpers: both pull in the
    # optional ``stt`` extra, and going through the engine turns a missing
    # install into a 503 with install instructions rather than a bare
    # ModuleNotFoundError surfacing as a 500.
    engine = get_engine()
    diarizer = engine.diarizer()

    from app.modules.stt.local.alignment import (
        UNKNOWN_SPEAKER,
        build_speaker_turns,
        format_transcript,
    )

    # Clock the whole request, not just inference: validation, conversion and
    # any wait for the device are latency the caller actually experiences.
    started = time.perf_counter()
    prepared = _prepare(file_bytes, filename, save_audio)
    resolved_speakers = resolve_num_speakers(num_speakers)

    try:
        diarization, transcription = await engine.run_exclusive(
            _run_diarized_job,
            str(prepared.wav_path),
            resolved_speakers,
            language or settings.WHISPER_LANGUAGE or None,
            min_speakers,
            max_speakers,
        )
        total_seconds = time.perf_counter() - started

        turns = build_speaker_turns(
            transcription,
            diarization,
            speaker_names=speaker_names,
        )
        unknown_words = sum(
            len(turn.words) for turn in turns if turn.speaker == UNKNOWN_SPEAKER
        )

        def display_name(speaker_id: str) -> str:
            return (speaker_names or {}).get(speaker_id, speaker_id)

        duration = prepared.duration or diarization.audio_duration
        response = DiarizedTranscriptResponse(
            job_id=prepared.job_id,
            encounter_id=encounter_id or None,
            created_at=_utc_now(),
            text=transcription.text,
            labelled_text=format_transcript(turns, with_times=False),
            language=transcription.language,
            num_speakers=diarization.num_speakers,
            speakers=diarization.speakers,
            turns=[
                SpeakerTurnOut(
                    speaker_id=turn.speaker,
                    speaker_name=turn.speaker_name or display_name(turn.speaker),
                    start=round(turn.start, 3),
                    end=round(turn.end, 3),
                    text=turn.text,
                    confidence=round(turn.confidence, 4),
                )
                for turn in turns
            ],
            segments=[
                SpeakerSegmentOut(
                    start=round(segment.start, 3),
                    end=round(segment.end, 3),
                    speaker_id=segment.speaker,
                    speaker_name=display_name(segment.speaker),
                )
                for segment in diarization.segments
            ],
            audio=AudioMeta(
                filename=filename,
                duration=round(duration, 3),
                sample_rate=TARGET_SAMPLE_RATE,
                size_bytes=len(file_bytes),
                stored=prepared.stored is not None,
                stored_path=storage.audio_reference(prepared.stored),
            ),
            metrics=ProcessingMetrics(
                audio_duration=round(duration, 3),
                diarization_seconds=round(diarization.processing_time, 3),
                transcription_seconds=round(transcription.processing_time, 3),
                total_seconds=round(total_seconds, 3),
                diarization_rtf=round(diarization.real_time_factor, 4),
                transcription_rtf=round(transcription.real_time_factor, 4),
                total_rtf=round(total_seconds / duration, 4) if duration else 0.0,
                stage_times=StageTimings(
                    vad=round(diarization.stage_times.get("vad", 0.0), 3),
                    embedding=round(diarization.stage_times.get("embedding", 0.0), 3),
                    clustering=round(diarization.stage_times.get("clustering", 0.0), 3),
                ),
            ),
            engine=EngineInfo(
                mode="local",
                device=engine.device,
                whisper_backend=transcription.backend,
                whisper_model=transcription.model,
                vad_model=diarizer.config.vad.source,
                embedding_model=diarizer.config.embedding.source,
                clustering_method=diarization.diagnostics.get("clustering_method"),
            ),
            diagnostics=DiarizationDiagnostics(
                n_vad_regions=diarization.diagnostics.get("n_vad_regions"),
                n_subsegments=diarization.diagnostics.get("n_subsegments"),
                mean_pairwise_cosine=diarization.diagnostics.get("mean_pairwise_cosine"),
                clustering_pval=diarization.diagnostics.get("clustering_pval"),
                oracle_num_speakers=resolved_speakers,
                unknown_speaker_words=unknown_words,
            ),
        )

        if prepared.stored is not None:
            storage.save_result(prepared.stored, response.model_dump())

        logger.info(
            "stt_local_diarize_completed",
            job_id=prepared.job_id,
            duration=round(duration, 2),
            num_speakers=response.num_speakers,
            n_turns=len(response.turns),
            total_rtf=response.metrics.total_rtf,
            unknown_words=unknown_words,
        )
        return response
    finally:
        if prepared.cleanup is not None:
            prepared.cleanup.cleanup()
        elif prepared.stored is not None and prepared.stored.cleanup is not None:
            prepared.stored.cleanup.cleanup()
