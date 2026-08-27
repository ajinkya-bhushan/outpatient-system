"""
app/diarization/alignment.py
─────────────────────────────
Join the two independent pipelines — "who spoke when" (SpeechBrain) and "what
was said" (Whisper) — into a speaker-labelled transcript.

Method
------
Whisper words and diarization segments come from separate models with slightly
different notions of where a word starts, so alignment is done by **maximum
temporal overlap**: each word goes to the speaker whose segments cover most of
that word's time span.

Words that overlap no segment at all (typically Whisper hallucinating over
silence the VAD rejected, or timestamp drift at the very edges) are attributed
to the nearest segment within ``max_gap_sec``, and otherwise marked as
``UNKNOWN_SPEAKER`` rather than silently dropped — losing clinical content is
worse than an unlabelled line.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger
from app.diarization.pipeline import DiarizationResult, SpeakerSegment
from app.diarization.transcribe import TranscriptionResult, Word

logger = get_logger(__name__)

UNKNOWN_SPEAKER = "unknown"


@dataclass
class SpeakerTurn:
    """A run of consecutive words attributed to one speaker."""

    speaker: str
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)
    speaker_name: str | None = None

    @property
    def confidence(self) -> float:
        """Mean Whisper word probability – a transcription-confidence proxy."""
        probabilities = [w.probability for w in self.words if w.probability is not None]
        return sum(probabilities) / len(probabilities) if probabilities else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "speaker_id": self.speaker,
            "speaker_name": self.speaker_name or self.speaker,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "text": self.text,
            "confidence": round(self.confidence, 4),
        }


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def assign_speaker_to_word(
    word: Word,
    segments: list[SpeakerSegment],
    max_gap_sec: float = 0.5,
) -> str:
    """Return the speaker label for a single word.

    Prefers the speaker with the largest temporal overlap; falls back to the
    nearest segment within ``max_gap_sec``.
    """
    best_speaker, best_overlap = None, 0.0
    for segment in segments:
        overlap = _overlap(word.start, word.end, segment.start, segment.end)
        if overlap > best_overlap:
            best_speaker, best_overlap = segment.speaker, overlap

    if best_speaker is not None:
        return best_speaker

    # No overlap: attach to the closest segment if it is close enough.
    nearest_speaker, nearest_gap = None, float("inf")
    for segment in segments:
        if word.end < segment.start:
            gap = segment.start - word.end
        elif word.start > segment.end:
            gap = word.start - segment.end
        else:
            gap = 0.0
        if gap < nearest_gap:
            nearest_speaker, nearest_gap = segment.speaker, gap

    if nearest_speaker is not None and nearest_gap <= max_gap_sec:
        return nearest_speaker
    return UNKNOWN_SPEAKER


def build_speaker_turns(
    transcription: TranscriptionResult,
    diarization: DiarizationResult,
    max_gap_sec: float = 0.5,
    speaker_names: dict[str, str] | None = None,
) -> list[SpeakerTurn]:
    """Produce a speaker-labelled transcript.

    Args:
        transcription: Whisper result containing word-level timestamps.
        diarization:   SpeechBrain result containing speaker segments.
        max_gap_sec:   How far a word may sit from a segment and still be
                       attributed to it.
        speaker_names: Optional ``{"speaker_0": "Doctor"}`` display mapping,
                       from manual assignment or voice enrolment.

    Returns:
        Chronologically ordered speaker turns.
    """
    if not transcription.words:
        logger.warning("alignment_no_words")
        return []

    segments = diarization.segments
    if not segments:
        logger.warning("alignment_no_speaker_segments")

    labels = [assign_speaker_to_word(word, segments, max_gap_sec) for word in transcription.words]

    turns: list[SpeakerTurn] = []
    for word, label in zip(transcription.words, labels):
        if turns and turns[-1].speaker == label:
            turn = turns[-1]
            turn.end = max(turn.end, word.end)
            turn.words.append(word)
            turn.text = f"{turn.text} {word.text}"
        else:
            turns.append(
                SpeakerTurn(
                    speaker=label,
                    start=word.start,
                    end=word.end,
                    text=word.text,
                    words=[word],
                )
            )

    if speaker_names:
        for turn in turns:
            turn.speaker_name = speaker_names.get(turn.speaker)

    unknown_words = sum(1 for label in labels if label == UNKNOWN_SPEAKER)
    logger.info(
        "alignment_done",
        n_turns=len(turns),
        n_words=len(labels),
        unknown_words=unknown_words,
    )
    return turns


def format_transcript(turns: list[SpeakerTurn], with_times: bool = True) -> str:
    """Render turns as a human-readable transcript."""
    lines: list[str] = []
    for turn in turns:
        name = turn.speaker_name or turn.speaker
        if with_times:
            lines.append(f"[{turn.start:7.2f} - {turn.end:7.2f}] {name}: {turn.text}")
        else:
            lines.append(f"{name}: {turn.text}")
    return "\n".join(lines)
