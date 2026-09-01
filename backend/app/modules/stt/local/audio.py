"""
app/modules/stt/local/audio.py
───────────────────────────────
Upload validation and normalisation to the one audio format the models accept:
16 kHz mono 16-bit PCM WAV.

Conversion goes through ffmpeg as a subprocess rather than a Python decoder, so
browser recordings (WebM/Opus), phone recordings (M4A/AAC) and lossy uploads all
work without adding codec dependencies. Whisper would call ffmpeg internally
anyway, but converting up front means the diarizer and the transcriber read the
exact same samples — otherwise their timestamps could disagree, and word-to-
speaker alignment depends on a shared time base.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from app.core.config import settings
from app.core.errors import ConfigurationError, ValidationFailed
from app.core.logging import get_logger

logger = get_logger(__name__)

TARGET_SAMPLE_RATE = 16_000
TARGET_CHANNELS = 1

SUPPORTED_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".flac",
    ".ogg",
    ".oga",
    ".opus",
    ".m4a",
    ".mp4",
    ".aac",
    ".webm",
    ".mkv",
    ".wma",
    ".aiff",
    ".amr",
}


def require_ffmpeg() -> None:
    """Fail with a 503 if ffmpeg is missing, rather than a cryptic OSError."""
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise ConfigurationError(
            "ffmpeg/ffprobe not found on PATH. Install ffmpeg to accept audio uploads."
        )


def validate_upload(filename: str, size_bytes: int) -> str:
    """Check filename and size before anything touches the disk.

    Returns:
        The lower-cased file extension, including the leading dot.
    """
    if size_bytes == 0:
        raise ValidationFailed("Audio file is empty.")

    if size_bytes > settings.max_audio_size_bytes:
        actual_mb = size_bytes / (1024 * 1024)
        raise ValidationFailed(
            f"Audio is {actual_mb:.1f} MB, which exceeds the "
            f"{settings.MAX_AUDIO_SIZE_MB} MB limit."
        )

    extension = Path(filename).suffix.lower()
    if not extension:
        raise ValidationFailed(
            f"Cannot determine audio format from filename {filename!r}. "
            f"Supported extensions: {', '.join(sorted(SUPPORTED_EXTENSIONS))}."
        )
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValidationFailed(
            f"Unsupported audio format {extension!r}. "
            f"Supported extensions: {', '.join(sorted(SUPPORTED_EXTENSIONS))}."
        )
    return extension


def probe_duration(audio_path: str | Path) -> float:
    """Return the duration of an audio file in seconds via ffprobe."""
    require_ffmpeg()

    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        # ffprobe echoes the full server-side path, so the raw stderr is logged
        # rather than returned to the client.
        logger.warning("audio_probe_failed", stderr=completed.stderr.strip()[:500])
        raise ValidationFailed(
            "Could not read the audio file — it may be corrupt, truncated, or "
            "not audio at all."
        )

    try:
        duration = float(json.loads(completed.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise ValidationFailed(f"Audio file has no readable duration: {exc}") from exc

    if duration <= 0:
        raise ValidationFailed("Audio file contains no audio.")
    return duration


def validate_duration(duration: float) -> None:
    """Reject recordings longer than the configured ceiling."""
    limit = settings.MAX_AUDIO_DURATION_SECONDS
    if duration > limit:
        raise ValidationFailed(
            f"Audio is {duration / 60:.1f} minutes, which exceeds the "
            f"{limit / 60:.0f} minute limit."
        )


def convert_to_wav16k_mono(source_path: str | Path, target_path: str | Path) -> None:
    """Transcode any supported input to 16 kHz mono 16-bit PCM WAV."""
    require_ffmpeg()

    completed = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-i",
            str(source_path),
            "-vn",
            "-ac",
            str(TARGET_CHANNELS),
            "-ar",
            str(TARGET_SAMPLE_RATE),
            "-acodec",
            "pcm_s16le",
            str(target_path),
        ],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if completed.returncode != 0:
        logger.error("audio_conversion_failed", stderr=completed.stderr.strip()[:500])
        raise ValidationFailed(
            "Audio conversion failed — the file may be corrupt or use an "
            "unsupported codec."
        )

    if not Path(target_path).exists() or Path(target_path).stat().st_size == 0:
        raise ValidationFailed("Audio conversion produced an empty file.")
