"""
app/modules/stt/local/diarizer.py
──────────────────────────────────
Offline SpeechBrain diarization: audio in, speaker-labelled timeline out.

    waveform → VAD → sub-segments → ECAPA embeddings → spectral clustering
             → merge same-speaker runs → resolve overlaps → speaker segments

This is the "who spoke when" half of the system; it knows nothing about words.
:mod:`app.modules.stt.local.alignment` joins the result to a Whisper transcript.

The same building blocks are reusable for the streaming path: run this over a
rolling window for provisional labels, then re-run it over the complete
recording once the consultation ends to produce the corrected transcript.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import soundfile as sf

from app.core.logging import get_logger
from app.modules.stt.local.clustering import cluster_embeddings
from app.modules.stt.local.config import DiarizationConfig
from app.modules.stt.local.embeddings import ECAPAEmbedder, build_subsegments
from app.modules.stt.local.vad import SpeechBrainVAD

logger = get_logger(__name__)


@dataclass
class SpeakerSegment:
    """A contiguous stretch of audio attributed to one speaker."""

    start: float
    end: float
    speaker: str

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "speaker": self.speaker,
        }


@dataclass
class DiarizationResult:
    """Full diarization output plus timing and diagnostic information."""

    segments: list[SpeakerSegment]
    num_speakers: int
    audio_duration: float
    speech_duration: float
    processing_time: float
    stage_times: dict[str, float] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def real_time_factor(self) -> float:
        return self.processing_time / self.audio_duration if self.audio_duration else 0.0

    @property
    def speakers(self) -> list[str]:
        return sorted({segment.speaker for segment in self.segments})

    def speaker_at(self, start: float, end: float) -> str | None:
        """Return the speaker with the largest overlap of ``[start, end)``.

        Used by word-to-speaker alignment; returns ``None`` when no segment
        overlaps the interval at all.
        """
        best_speaker, best_overlap = None, 0.0
        for segment in self.segments:
            overlap = min(end, segment.end) - max(start, segment.start)
            if overlap > best_overlap:
                best_speaker, best_overlap = segment.speaker, overlap
        return best_speaker

    def to_dict(self) -> dict[str, Any]:
        return {
            "num_speakers": self.num_speakers,
            "speakers": self.speakers,
            "audio_duration": round(self.audio_duration, 3),
            "speech_duration": round(self.speech_duration, 3),
            "processing_time": round(self.processing_time, 3),
            "real_time_factor": round(self.real_time_factor, 4),
            "stage_times": {k: round(v, 3) for k, v in self.stage_times.items()},
            "diagnostics": self.diagnostics,
            "segments": [segment.to_dict() for segment in self.segments],
        }


class SpeechBrainDiarizer:
    """End-to-end offline speaker diarization.

    Models load lazily on the first :meth:`diarize` call and are then reused,
    so instantiate this once per process.

    Example::

        diarizer = SpeechBrainDiarizer()
        result = diarizer.diarize("consult.wav", num_speakers=2)
        for segment in result.segments:
            print(f"{segment.start:6.2f}-{segment.end:6.2f}  {segment.speaker}")
    """

    def __init__(self, config: DiarizationConfig | None = None) -> None:
        self.config = config or DiarizationConfig()
        self.vad = SpeechBrainVAD(self.config)
        self.embedder = ECAPAEmbedder(self.config)

    def load(self) -> None:
        """Eagerly load both models (useful at service startup)."""
        self.vad.load()
        self.embedder.load()

    # ── Main entry point ──────────────────────────────────────────────────────

    def diarize(
        self,
        audio_path: str,
        num_speakers: int | None = None,
        recording_id: str = "rec",
    ) -> DiarizationResult:
        """Diarize an audio file.

        Args:
            audio_path:   Path to a mono WAV file at ``config.sample_rate``.
            num_speakers: Known speaker count, or ``None`` to estimate it.
            recording_id: Identifier used in RTTM output.

        Returns:
            A :class:`DiarizationResult` with non-overlapping, chronologically
            ordered speaker segments.
        """
        started = time.perf_counter()
        stage_times: dict[str, float] = {}

        waveform, sample_rate = self._read_audio(audio_path)
        audio_duration = len(waveform) / sample_rate

        # ── Stage 1: voice activity detection ─────────────────────────────────
        stage_start = time.perf_counter()
        regions = self.vad.get_speech_regions(audio_path)
        if not regions:
            logger.warning("vad_no_speech_using_full_audio", audio_path=audio_path)
            regions = [(0.0, audio_duration)]
        stage_times["vad"] = time.perf_counter() - stage_start
        speech_duration = sum(end - start for start, end in regions)

        # ── Stage 2: sub-segment + embed ──────────────────────────────────────
        stage_start = time.perf_counter()
        embedding_cfg = self.config.embedding
        subsegs = build_subsegments(
            regions,
            window_sec=embedding_cfg.window_sec,
            shift_sec=embedding_cfg.shift_sec,
            min_subseg_sec=embedding_cfg.min_subseg_sec,
        )
        embeddings = self.embedder.embed(waveform, subsegs)
        stage_times["embedding"] = time.perf_counter() - stage_start

        if not subsegs:
            logger.warning("diarization_no_subsegments", audio_path=audio_path)
            return DiarizationResult(
                segments=[],
                num_speakers=0,
                audio_duration=audio_duration,
                speech_duration=speech_duration,
                processing_time=time.perf_counter() - started,
                stage_times=stage_times,
                diagnostics={"reason": "no_subsegments"},
            )

        # ── Stage 3: cluster ──────────────────────────────────────────────────
        stage_start = time.perf_counter()
        clustering = cluster_embeddings(
            embeddings,
            config=self.config.clustering,
            num_speakers=num_speakers,
        )
        stage_times["clustering"] = time.perf_counter() - stage_start

        # ── Stage 4: build the speaker timeline ───────────────────────────────
        segments = self._build_segments(subsegs, clustering.labels, recording_id)

        result = DiarizationResult(
            segments=segments,
            num_speakers=clustering.num_speakers,
            audio_duration=audio_duration,
            speech_duration=speech_duration,
            processing_time=time.perf_counter() - started,
            stage_times=stage_times,
            diagnostics={
                "n_vad_regions": len(regions),
                "n_subsegments": len(subsegs),
                "clustering_method": clustering.method,
                "clustering_pval": clustering.pval,
                "mean_pairwise_cosine": round(clustering.mean_pairwise_cosine, 4),
                "oracle_num_speakers": num_speakers,
            },
        )
        logger.info(
            "diarization_done",
            num_speakers=result.num_speakers,
            n_segments=len(segments),
            rtf=round(result.real_time_factor, 3),
        )
        return result

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _read_audio(self, audio_path: str) -> tuple[np.ndarray, int]:
        """Load mono float32 audio, rejecting an unexpected sample rate."""
        waveform, sample_rate = sf.read(audio_path, dtype="float32", always_2d=False)
        if waveform.ndim > 1:
            waveform = waveform.mean(axis=1)

        if sample_rate != self.config.sample_rate:
            raise ValueError(
                f"{audio_path} is {sample_rate} Hz but the pipeline expects "
                f"{self.config.sample_rate} Hz — resample it first "
                f"(app/audio/processor.py handles this for uploads)."
            )
        return waveform, sample_rate

    @staticmethod
    def _build_segments(
        subsegs: list,
        labels: np.ndarray,
        recording_id: str,
    ) -> list[SpeakerSegment]:
        """Turn per-sub-segment labels into a clean speaker timeline.

        Sub-segments overlap by design, so this merges same-speaker runs and
        then splits the remaining overlaps down the middle using SpeechBrain's
        own post-processing, giving non-overlapping segments.
        """
        from speechbrain.integrations.alignment.diarization import (
            distribute_overlap,
            merge_ssegs_same_speaker,
        )

        # SpeechBrain's helpers work on [rec_id, start, end, speaker] lists.
        rows = [
            [recording_id, float(sub.start), float(sub.end), f"speaker_{int(label)}"]
            for sub, label in zip(subsegs, labels)
        ]
        rows.sort(key=lambda row: (row[1], row[2]))

        merged = merge_ssegs_same_speaker(rows)
        resolved = distribute_overlap(merged)

        return [
            SpeakerSegment(start=row[1], end=row[2], speaker=row[3])
            for row in resolved
            if row[2] > row[1]
        ]
