"""
tests/test_audio.py
────────────────────
Unit tests for audio validation and processing utilities.

All tests are pure Python – no model weights, no ffmpeg required for most
cases.  Tests that need ffprobe are skipped when it is not on PATH.
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest

from app.audio.validator import (
    ALLOWED_EXTENSIONS,
    AudioValidationError,
    validate_extension,
    validate_file_size,
    validate_mime_type,
)
from app.core.metrics import Timer, compute_cer, compute_rtf, compute_wer


# ═══════════════════════════════════════════════════════════════════════════
# Extension validation
# ═══════════════════════════════════════════════════════════════════════════

class TestExtensionValidation:
    def test_valid_extensions(self):
        for ext in [".mp3", ".wav", ".flac", ".ogg", ".m4a", ".webm"]:
            result = validate_extension(f"audio{ext}")
            assert result == ext

    def test_invalid_extension_raises(self):
        with pytest.raises(AudioValidationError, match="Unsupported file extension"):
            validate_extension("document.pdf")

    def test_case_insensitive(self):
        result = validate_extension("AUDIO.MP3")
        assert result == ".mp3"

    def test_no_extension_raises(self):
        with pytest.raises(AudioValidationError):
            validate_extension("audiofile")

    def test_allowed_set_is_not_empty(self):
        assert len(ALLOWED_EXTENSIONS) > 0


# ═══════════════════════════════════════════════════════════════════════════
# MIME type validation
# ═══════════════════════════════════════════════════════════════════════════

class TestMimeValidation:
    def test_valid_audio_mime(self):
        mime = validate_mime_type("audio.mp3", "audio/mpeg")
        assert mime.startswith("audio/")

    def test_valid_webm_mime(self):
        mime = validate_mime_type("audio.webm", "video/webm")
        assert "webm" in mime

    def test_invalid_mime_raises(self):
        with pytest.raises(AudioValidationError, match="Unsupported MIME type"):
            validate_mime_type("file.wav", "application/pdf")

    def test_fallback_guesses_from_filename(self):
        # No content_type provided – should guess from filename
        mime = validate_mime_type("recording.wav")
        assert mime.startswith("audio/")

    def test_mime_with_parameters_stripped(self):
        # Content-Type can include charset/codecs parameters
        mime = validate_mime_type("a.wav", "audio/wav; codecs=pcm")
        assert mime == "audio/wav"


# ═══════════════════════════════════════════════════════════════════════════
# File size validation
# ═══════════════════════════════════════════════════════════════════════════

class TestFileSizeValidation:
    def test_small_file_passes(self):
        validate_file_size(1024)  # 1 KB – should not raise

    def test_oversized_file_raises(self):
        max_bytes = 50 * 1024 * 1024  # 50 MB
        with pytest.raises(AudioValidationError, match="exceeds"):
            validate_file_size(max_bytes + 1, filename="big.wav")

    def test_exact_limit_passes(self):
        max_bytes = 50 * 1024 * 1024
        validate_file_size(max_bytes)  # exactly at limit – should pass

    def test_zero_byte_file_passes(self):
        # Size=0 is valid at this layer; duration check will catch empty audio
        validate_file_size(0)


# ═══════════════════════════════════════════════════════════════════════════
# Metrics: RTF
# ═══════════════════════════════════════════════════════════════════════════

class TestComputeRtf:
    def test_faster_than_realtime(self):
        rtf = compute_rtf(processing_time=6.0, audio_duration=60.0)
        assert rtf == pytest.approx(0.1, rel=1e-3)

    def test_realtime(self):
        rtf = compute_rtf(processing_time=10.0, audio_duration=10.0)
        assert rtf == pytest.approx(1.0)

    def test_zero_duration_returns_zero(self):
        assert compute_rtf(5.0, 0.0) == 0.0

    def test_negative_duration_returns_zero(self):
        assert compute_rtf(5.0, -1.0) == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Metrics: WER
# ═══════════════════════════════════════════════════════════════════════════

class TestComputeWer:
    def test_perfect_match(self):
        assert compute_wer("hello world", "hello world") == 0.0

    def test_one_substitution(self):
        # "world" → "word" = 1 sub out of 2 words = 0.5
        wer = compute_wer("hello world", "hello word")
        assert wer == pytest.approx(0.5)

    def test_empty_hypothesis(self):
        # All words deleted
        wer = compute_wer("hello world", "")
        assert wer == pytest.approx(1.0)

    def test_empty_reference_returns_zero(self):
        assert compute_wer("", "hello") == 0.0

    def test_case_insensitive(self):
        wer = compute_wer("Hello World", "hello world")
        assert wer == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Metrics: CER
# ═══════════════════════════════════════════════════════════════════════════

class TestComputeCer:
    def test_perfect_match(self):
        assert compute_cer("hello", "hello") == 0.0

    def test_one_char_deletion(self):
        cer = compute_cer("hello", "helo")
        assert cer == pytest.approx(1 / 5)

    def test_empty_reference(self):
        assert compute_cer("", "anything") == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Timer context manager
# ═══════════════════════════════════════════════════════════════════════════

class TestTimer:
    def test_elapsed_positive(self):
        import time
        with Timer() as t:
            time.sleep(0.05)
        assert t.elapsed >= 0.04

    def test_elapsed_type_is_float(self):
        with Timer() as t:
            pass
        assert isinstance(t.elapsed, float)
