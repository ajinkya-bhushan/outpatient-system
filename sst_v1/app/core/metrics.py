"""
app/core/metrics.py
────────────────────
Lightweight helpers for computing transcription performance metrics.

All functions are pure (no side-effects) so they are trivially testable.

Metrics glossary
----------------
RTF (Real-Time Factor)
    RTF = processing_time / audio_duration
    < 1.0 → faster than real-time  (good)
    = 1.0 → exactly real-time
    > 1.0 → slower than real-time (too slow for live use)

WER (Word Error Rate)
    WER = (S + D + I) / N
    where S=substitutions, D=deletions, I=insertions, N=reference words.
    Lower is better.  0.0 = perfect match.

CER (Character Error Rate)
    Same formula as WER but applied at character level.
"""

from __future__ import annotations

import time


# ── Timing helpers ────────────────────────────────────────────────────────────

class Timer:
    """Simple context-manager wall-clock timer.

    Example::

        with Timer() as t:
            result = model.transcribe(audio)
        print(t.elapsed)   # seconds as float
    """

    def __init__(self) -> None:
        self.start: float = 0.0
        self.end: float = 0.0

    def __enter__(self) -> "Timer":
        self.start = time.perf_counter()
        return self

    def __exit__(self, *_) -> None:
        self.end = time.perf_counter()

    @property
    def elapsed(self) -> float:
        """Wall-clock seconds between __enter__ and __exit__."""
        return self.end - self.start


# ── Core metric calculations ──────────────────────────────────────────────────

def compute_rtf(processing_time: float, audio_duration: float) -> float:
    """Return Real-Time Factor (RTF).

    Args:
        processing_time: Inference wall-clock time in seconds.
        audio_duration:  Length of the audio clip in seconds.

    Returns:
        RTF as a float, or 0.0 if audio_duration is zero/negative.
    """
    if audio_duration <= 0:
        return 0.0
    return round(processing_time / audio_duration, 4)


def compute_wer(reference: str, hypothesis: str) -> float:
    """Compute Word Error Rate between a reference and hypothesis transcript.

    Uses dynamic-programming edit distance at the word level.

    Args:
        reference:  Ground-truth transcript.
        hypothesis: Model-produced transcript.

    Returns:
        WER in [0.0, ∞).  Returns 0.0 if reference is empty.
    """
    ref_words = reference.lower().split()
    hyp_words = hypothesis.lower().split()

    if len(ref_words) == 0:
        return 0.0

    dist = _edit_distance(ref_words, hyp_words)
    return round(dist / len(ref_words), 4)


def compute_cer(reference: str, hypothesis: str) -> float:
    """Compute Character Error Rate between a reference and hypothesis transcript.

    Args:
        reference:  Ground-truth transcript.
        hypothesis: Model-produced transcript.

    Returns:
        CER in [0.0, ∞).  Returns 0.0 if reference is empty.
    """
    ref_chars = list(reference)
    hyp_chars = list(hypothesis)

    if len(ref_chars) == 0:
        return 0.0

    dist = _edit_distance(ref_chars, hyp_chars)
    return round(dist / len(ref_chars), 4)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _edit_distance(seq_a: list, seq_b: list) -> int:
    """Standard Levenshtein edit distance (insertions, deletions, substitutions)."""
    m, n = len(seq_a), len(seq_b)
    # Use two-row DP to save memory
    prev = list(range(n + 1))
    curr = [0] * (n + 1)

    for i in range(1, m + 1):
        curr[0] = i
        for j in range(1, n + 1):
            if seq_a[i - 1] == seq_b[j - 1]:
                curr[j] = prev[j - 1]
            else:
                curr[j] = 1 + min(prev[j], curr[j - 1], prev[j - 1])
        prev, curr = curr, [0] * (n + 1)

    return prev[n]
