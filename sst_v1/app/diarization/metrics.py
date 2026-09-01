"""
app/diarization/metrics.py
───────────────────────────
Evaluation metrics for the diarization + transcription pipeline.

Diarization Error Rate follows the NIST ``md-eval`` formulation:

    DER = (missed + false-alarm + confusion) / total reference speech

computed on a fixed frame grid, with a forgiveness *collar* around reference
boundaries (human-annotated turn boundaries are only accurate to ~250 ms, so
scoring them exactly would punish correct systems).

Because diarization labels are arbitrary (``speaker_0`` is not inherently the
doctor), hypothesis labels are first mapped onto reference labels by the
assignment that maximises agreement — solved exactly with the Hungarian
algorithm, as md-eval does.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np
from scipy.optimize import linear_sum_assignment

Segment = tuple[float, float, str]  # (start, end, speaker)


@dataclass
class DERResult:
    """Diarization Error Rate broken down into its three components."""

    der: float
    missed_speech: float
    false_alarm: float
    speaker_confusion: float
    total_reference_speech: float
    reference_speakers: int
    hypothesis_speakers: int
    mapping: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "der_percent": round(self.der * 100, 2),
            "missed_speech_percent": round(self.missed_speech * 100, 2),
            "false_alarm_percent": round(self.false_alarm * 100, 2),
            "speaker_confusion_percent": round(self.speaker_confusion * 100, 2),
            "total_reference_speech_sec": round(self.total_reference_speech, 2),
            "reference_speakers": self.reference_speakers,
            "hypothesis_speakers": self.hypothesis_speakers,
            "mapping": self.mapping,
        }


def _frame_labels(
    segments: Iterable[Segment],
    n_frames: int,
    frame_sec: float,
    speaker_index: dict[str, int],
) -> np.ndarray:
    """Rasterise segments onto a boolean ``(n_speakers, n_frames)`` grid."""
    grid = np.zeros((len(speaker_index), n_frames), dtype=bool)
    for start, end, speaker in segments:
        lo = max(0, int(np.floor(start / frame_sec)))
        hi = min(n_frames, int(np.ceil(end / frame_sec)))
        if hi > lo:
            grid[speaker_index[speaker], lo:hi] = True
    return grid


def compute_der(
    reference: list[Segment],
    hypothesis: list[Segment],
    collar: float = 0.25,
    frame_sec: float = 0.01,
    audio_duration: float | None = None,
) -> DERResult:
    """Compute Diarization Error Rate.

    Args:
        reference:      Ground-truth ``(start, end, speaker)`` segments.
        hypothesis:     System output in the same form.
        collar:         Seconds ignored on *each side* of every reference
                        boundary. 0.25 s is the NIST/DIHARD convention.
        frame_sec:      Scoring grid resolution.
        audio_duration: Recording length; inferred from the segments if omitted.

    Returns:
        A :class:`DERResult`. ``der`` is a fraction, not a percentage.
    """
    if not reference:
        raise ValueError("reference must contain at least one segment")

    if audio_duration is None:
        audio_duration = max(end for _, end, _ in reference + hypothesis)
    n_frames = int(np.ceil(audio_duration / frame_sec)) + 1

    ref_speakers = sorted({spk for _, _, spk in reference})
    hyp_speakers = sorted({spk for _, _, spk in hypothesis})
    ref_index = {spk: i for i, spk in enumerate(ref_speakers)}
    hyp_index = {spk: i for i, spk in enumerate(hyp_speakers)}

    ref_grid = _frame_labels(reference, n_frames, frame_sec, ref_index)
    hyp_grid = _frame_labels(hypothesis, n_frames, frame_sec, hyp_index)

    # ── Collar: drop frames near reference boundaries from scoring ────────────
    scored = np.ones(n_frames, dtype=bool)
    if collar > 0:
        half = int(round(collar / frame_sec))
        for start, end, _ in reference:
            for boundary in (start, end):
                center = int(round(boundary / frame_sec))
                scored[max(0, center - half) : min(n_frames, center + half + 1)] = False

    ref_grid = ref_grid[:, scored]
    hyp_grid = hyp_grid[:, scored]

    ref_counts = ref_grid.sum(axis=0)
    hyp_counts = hyp_grid.sum(axis=0)

    total_reference = float(ref_counts.sum()) * frame_sec
    if total_reference == 0:
        raise ValueError("no reference speech survives the collar; lower the collar")

    # ── Optimal reference↔hypothesis label mapping ────────────────────────────
    mapping: dict[str, str] = {}
    correct_frames = np.zeros(ref_grid.shape[1], dtype=int)

    if hyp_speakers:
        # cost[i, j] = frames where ref speaker i and hyp speaker j coincide
        agreement = (ref_grid.astype(np.int32) @ hyp_grid.astype(np.int32).T)
        row_ind, col_ind = linear_sum_assignment(-agreement)
        for i, j in zip(row_ind, col_ind):
            if agreement[i, j] > 0:
                mapping[hyp_speakers[j]] = ref_speakers[i]
                correct_frames += (ref_grid[i] & hyp_grid[j]).astype(int)

    missed = np.maximum(0, ref_counts - hyp_counts).sum() * frame_sec
    false_alarm = np.maximum(0, hyp_counts - ref_counts).sum() * frame_sec
    confusion = (np.minimum(ref_counts, hyp_counts) - correct_frames).sum() * frame_sec

    return DERResult(
        der=float((missed + false_alarm + confusion) / total_reference),
        missed_speech=float(missed / total_reference),
        false_alarm=float(false_alarm / total_reference),
        speaker_confusion=float(confusion / total_reference),
        total_reference_speech=total_reference,
        reference_speakers=len(ref_speakers),
        hypothesis_speakers=len(hyp_speakers),
        mapping=mapping,
    )


# ── Transcription metrics ─────────────────────────────────────────────────────

_PUNCTUATION = re.compile(r"[^\w\s']")


def normalise_text(text: str) -> str:
    """Upper-case, strip punctuation, collapse whitespace.

    LibriSpeech references are upper-case and unpunctuated while Whisper emits
    cased, punctuated text; without this, WER measures formatting rather than
    recognition.
    """
    text = _PUNCTUATION.sub(" ", text.upper())
    return " ".join(text.split())


def compute_wer(reference_text: str, hypothesis_text: str) -> dict[str, float]:
    """Word and character error rates over normalised text."""
    import jiwer

    reference = normalise_text(reference_text)
    hypothesis = normalise_text(hypothesis_text)

    measures = jiwer.process_words(reference, hypothesis)
    return {
        "wer_percent": round(measures.wer * 100, 2),
        "cer_percent": round(jiwer.cer(reference, hypothesis) * 100, 2),
        "substitutions": measures.substitutions,
        "deletions": measures.deletions,
        "insertions": measures.insertions,
        "hits": measures.hits,
        "reference_words": len(reference.split()),
        "hypothesis_words": len(hypothesis.split()),
    }


def word_speaker_accuracy(
    words: list[tuple[float, float, str]],
    reference: list[Segment],
    mapping: dict[str, str],
) -> dict[str, Any]:
    """Fraction of transcribed words given the correct speaker.

    This is the metric that matters for a clinical transcript: DER measures
    time, but a mislabelled sentence is what a clinician actually notices.

    Args:
        words:     ``(start, end, assigned_speaker)`` per transcribed word.
        reference: Ground-truth speaker segments.
        mapping:   Hypothesis→reference label mapping from :func:`compute_der`.

    Returns:
        Counts and accuracy, ignoring words whose midpoint falls outside all
        reference speech (nothing to compare against there).
    """
    correct = scored = unscored = 0

    for start, end, assigned in words:
        midpoint = (start + end) / 2
        truth = next(
            (spk for seg_start, seg_end, spk in reference if seg_start <= midpoint <= seg_end),
            None,
        )
        if truth is None:
            unscored += 1
            continue
        scored += 1
        if mapping.get(assigned) == truth:
            correct += 1

    return {
        "word_speaker_accuracy_percent": round(100 * correct / scored, 2) if scored else 0.0,
        "correct_words": correct,
        "scored_words": scored,
        "unscored_words": unscored,
    }
