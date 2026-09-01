"""
app/audio/processor.py
───────────────────────
Audio file processing utilities – conversion, normalisation, and temp-file
lifecycle management.

All conversion is done through ffmpeg (via subprocess) so there is no
dependency on a Python audio library for format conversion.  soundfile and
librosa are used only for metadata extraction and waveform analysis.

Design decisions
----------------
* We always write to a temp .wav (16 kHz, mono, 16-bit PCM) before passing
  to Whisper.  Whisper's own ffmpeg call can handle most formats, but
  pre-converting avoids surprises with exotic codecs.
* Temp files are managed by the caller using a context manager
  (``managed_audio_file``) to guarantee cleanup even on exceptions.
* All processing is synchronous (not async) because it's fast (~sub-second)
  and is always called inside a ThreadPoolExecutor anyway.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from app.core.logging import get_logger

logger = get_logger(__name__)

# Target format for Whisper
_TARGET_SAMPLE_RATE = 16000
_TARGET_CHANNELS = 1
_TARGET_FORMAT = "wav"


# ── Context manager for temp files ─────────────────────────────────────────────

@contextmanager
def managed_audio_file(suffix: str = ".wav") -> Generator[str, None, None]:
    """Create a named temp file and delete it on exit.

    Yields:
        Absolute path to the temp file (not yet written).

    Example::

        with managed_audio_file(".wav") as path:
            convert_to_wav(source, path)
            result = model.transcribe(path)
        # file is deleted here
    """
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp_path = tmp.name
    tmp.close()
    try:
        yield tmp_path
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
            logger.debug("temp_file_deleted", path=tmp_path)


# ── Conversion ────────────────────────────────────────────────────────────────

def convert_to_wav(source_path: str, output_path: str) -> str:
    """Convert any ffmpeg-supported audio file to 16 kHz mono WAV.

    Args:
        source_path:  Path to the input audio file.
        output_path:  Path where the converted WAV will be written.

    Returns:
        ``output_path`` on success.

    Raises:
        RuntimeError: If ffmpeg is not on PATH or conversion fails.
        FileNotFoundError: If ``source_path`` does not exist.
    """
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Source audio not found: {source_path}")

    cmd = [
        "ffmpeg",
        "-y",                        # overwrite output without asking
        "-i", source_path,           # input
        "-ar", str(_TARGET_SAMPLE_RATE),  # resample to 16 kHz
        "-ac", str(_TARGET_CHANNELS),     # mono
        "-f", _TARGET_FORMAT,        # force WAV container
        "-loglevel", "error",        # suppress verbose output
        output_path,
    ]

    logger.debug("audio_convert_start", source=source_path, target=output_path)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        raise RuntimeError(
            "ffmpeg is not installed or not on PATH. "
            "Install ffmpeg: https://ffmpeg.org/download.html"
        )

    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg conversion failed (exit {result.returncode}): {result.stderr[:300]}"
        )

    logger.debug("audio_convert_done", output=output_path)
    return output_path


def save_upload_to_temp(file_bytes: bytes, original_filename: str) -> str:
    """Write raw upload bytes to a temporary file, return path.

    The caller is responsible for deleting the file (use ``managed_audio_file``
    or ``os.unlink`` when done).

    Args:
        file_bytes:         Raw bytes from the upload.
        original_filename:  Used to preserve the extension.

    Returns:
        Absolute path to the saved temp file.
    """
    ext = Path(original_filename).suffix or ".bin"
    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    tmp.write(file_bytes)
    tmp.close()
    logger.debug("upload_saved_to_temp", path=tmp.name, size=len(file_bytes))
    return tmp.name


def prepare_audio_for_inference(source_path: str) -> tuple[str, bool]:
    """Convert source audio to Whisper-compatible WAV if needed.

    If the source is already a .wav at 16 kHz mono, it is returned as-is
    (``needs_cleanup=False``).  Otherwise a converted copy is created
    (``needs_cleanup=True``).

    Args:
        source_path: Path to the uploaded audio file.

    Returns:
        ``(wav_path, needs_cleanup)`` where ``needs_cleanup=True`` means
        the caller must delete ``wav_path`` when done.
    """
    source = Path(source_path)
    ext = source.suffix.lower()

    # Already a WAV – pass through without conversion
    # (Whisper will call ffmpeg internally if sample rate/channels differ)
    if ext == ".wav":
        logger.debug("audio_already_wav", path=source_path)
        return source_path, False

    # Convert to temp WAV
    tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_wav.close()

    convert_to_wav(source_path, tmp_wav.name)
    return tmp_wav.name, True
