"""
app/audio/validator.py
───────────────────────
Audio file validation utilities.

Validation is performed in multiple layers:
1. **Extension** – filename suffix against an allow-list.
2. **MIME type** – python-magic or mimetypes fallback (no magic lib required).
3. **File size** – compared to ``settings.MAX_AUDIO_SIZE_MB``.
4. **Audio duration** – extracted via ffprobe, compared to
   ``settings.MAX_AUDIO_DURATION_SECONDS``.

All functions raise ``AudioValidationError`` (a subclass of ``ValueError``)
on failure so API route handlers can catch a single exception type.
"""

from __future__ import annotations

import mimetypes
import os
import subprocess
import json
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg", ".flac"}
)

ALLOWED_MIME_PREFIXES: tuple[str, ...] = (
    "audio/",
    "video/mp4",   # m4a/mp4 containers often carry audio
    "video/webm",  # webm can be audio-only
)


# ── Custom exception ──────────────────────────────────────────────────────────

class AudioValidationError(ValueError):
    """Raised when an audio file fails any validation check."""


# ── Validators ────────────────────────────────────────────────────────────────

def validate_extension(filename: str) -> str:
    """Return the (lowered) extension or raise AudioValidationError.

    Args:
        filename: Original filename from the uploaded file.

    Returns:
        Lowercased extension including the leading dot, e.g. ``".wav"``.

    Raises:
        AudioValidationError: Extension not in the allow-list.
    """
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise AudioValidationError(
            f"Unsupported file extension '{ext}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    logger.debug("extension_valid", ext=ext, filename=filename)
    return ext


def validate_mime_type(filename: str, content_type: str | None = None) -> str:
    """Validate MIME type from the uploaded content-type header or filename.

    Args:
        filename:     Original filename (used as fallback for MIME guess).
        content_type: Content-Type header value from the HTTP request.

    Returns:
        The resolved MIME type string.

    Raises:
        AudioValidationError: MIME type is not audio-compatible.
    """
    mime = content_type or ""
    if not mime:
        guessed, _ = mimetypes.guess_type(filename)
        mime = guessed or "application/octet-stream"

    # Strip parameters e.g. "audio/wav; codecs=pcm"
    mime_base = mime.split(";")[0].strip().lower()

    if not any(mime_base.startswith(prefix) for prefix in ALLOWED_MIME_PREFIXES):
        raise AudioValidationError(
            f"Unsupported MIME type '{mime_base}'. Expected an audio/* type."
        )

    logger.debug("mime_valid", mime=mime_base, filename=filename)
    return mime_base


def validate_file_size(size_bytes: int, filename: str = "") -> None:
    """Raise AudioValidationError if the file exceeds MAX_AUDIO_SIZE_MB.

    Args:
        size_bytes: File size in bytes.
        filename:   Used only in log/error messages.

    Raises:
        AudioValidationError: File too large.
    """
    max_bytes = settings.max_audio_size_bytes
    if size_bytes > max_bytes:
        size_mb = size_bytes / (1024 * 1024)
        raise AudioValidationError(
            f"File '{filename}' is {size_mb:.1f} MB, exceeds the "
            f"{settings.MAX_AUDIO_SIZE_MB} MB limit."
        )
    logger.debug("file_size_valid", size_bytes=size_bytes, filename=filename)


def get_audio_duration(file_path: str) -> float:
    """Use ffprobe to extract the audio duration in seconds.

    Requires ``ffprobe`` to be on the system PATH (ships with ffmpeg).

    Args:
        file_path: Absolute path to the audio file.

    Returns:
        Duration in seconds as a float.  Returns 0.0 on failure (non-fatal).

    Raises:
        AudioValidationError: ffprobe not found on PATH.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("ffprobe_failed", stderr=result.stderr[:200])
            return 0.0

        info = json.loads(result.stdout)
        duration = float(info.get("format", {}).get("duration", 0.0))
        logger.debug("audio_duration_extracted", duration=duration, path=file_path)
        return round(duration, 3)

    except FileNotFoundError:
        raise AudioValidationError(
            "ffprobe is not installed or not on PATH. "
            "Install ffmpeg: https://ffmpeg.org/download.html"
        )
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError) as exc:
        logger.warning("ffprobe_parse_error", error=str(exc))
        return 0.0


def validate_audio_duration(file_path: str) -> float:
    """Validate and return audio duration.

    Args:
        file_path: Path to the audio file.

    Returns:
        Duration in seconds.

    Raises:
        AudioValidationError: Duration exceeds MAX_AUDIO_DURATION_SECONDS.
    """
    duration = get_audio_duration(file_path)
    max_dur = settings.MAX_AUDIO_DURATION_SECONDS

    if duration > 0 and duration > max_dur:
        raise AudioValidationError(
            f"Audio duration {duration:.1f}s exceeds the {max_dur}s limit."
        )

    return duration


def validate_audio_file(
    filename: str,
    size_bytes: int,
    file_path: str | None = None,
    content_type: str | None = None,
) -> dict:
    """Run all validation steps and return a summary dict.

    Args:
        filename:     Original upload filename.
        size_bytes:   File size in bytes.
        file_path:    Saved path (used for ffprobe duration check).
        content_type: HTTP Content-Type header.

    Returns:
        ``{"extension": str, "mime_type": str, "duration": float}``

    Raises:
        AudioValidationError: On any failed validation.
    """
    ext = validate_extension(filename)
    mime = validate_mime_type(filename, content_type)
    validate_file_size(size_bytes, filename)

    duration = 0.0
    if file_path and os.path.exists(file_path):
        duration = validate_audio_duration(file_path)

    return {"extension": ext, "mime_type": mime, "duration": duration}
