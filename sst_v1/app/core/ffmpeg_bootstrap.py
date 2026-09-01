"""
app/core/ffmpeg_bootstrap.py
─────────────────────────────
Ensure `ffmpeg` is findable by Whisper's subprocess call before inference.

Whisper's audio.py hardcodes `ffmpeg` (no extension, no path) in the command
it passes to subprocess.  The strategy here:

1. If `ffmpeg` is already on PATH (system install) -> nothing to do.
2. If `imageio-ffmpeg` is installed, its binary is e.g. `ffmpeg-win-x86_64-v7.1.exe`.
   We create a copy (or symlink) named `ffmpeg.exe` in the same directory and
   prepend that directory to PATH.  Whisper then finds `ffmpeg` via PATH lookup.
3. Log a clear warning if neither strategy succeeds.

Import this module ONCE at app startup before any Whisper inference.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)

_patched: bool = False  # module-level guard: only run once


def ensure_ffmpeg() -> bool:
    """Guarantee `ffmpeg` is on PATH.  Returns True if successful."""
    global _patched
    if _patched:
        return shutil.which("ffmpeg") is not None

    _patched = True

    # 1. Already on PATH?
    if shutil.which("ffmpeg"):
        logger.debug("ffmpeg_found_on_path", path=shutil.which("ffmpeg"))
        return True

    # 2. imageio-ffmpeg bundled binary
    try:
        import imageio_ffmpeg  # type: ignore[import]

        src_exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
        ffmpeg_dir = src_exe.parent

        # Create ffmpeg.exe alias in the same directory
        dest_exe = ffmpeg_dir / "ffmpeg.exe"
        if not dest_exe.exists():
            try:
                # Try hard-link first (no disk space duplication)
                os.link(src_exe, dest_exe)
                logger.debug("ffmpeg_hardlinked", src=str(src_exe), dest=str(dest_exe))
            except (OSError, NotImplementedError):
                # Fall back to copy (cross-device or permissions issue)
                shutil.copy2(src_exe, dest_exe)
                logger.debug("ffmpeg_copied", src=str(src_exe), dest=str(dest_exe))

        # Prepend dir so `ffmpeg` resolves to our alias
        os.environ["PATH"] = str(ffmpeg_dir) + os.pathsep + os.environ.get("PATH", "")

        if shutil.which("ffmpeg"):
            logger.info(
                "ffmpeg_ready_via_imageio",
                binary=str(dest_exe),
                version=src_exe.name,
            )
            return True

    except ImportError:
        pass
    except Exception as exc:
        logger.warning("ffmpeg_imageio_setup_error", error=str(exc))

    # 3. Neither available — warn clearly
    logger.warning(
        "ffmpeg_not_available",
        hint=(
            "Whisper requires ffmpeg to decode audio files. "
            "Install imageio-ffmpeg:  uv add imageio-ffmpeg  "
            "OR install system ffmpeg:  winget install Gyan.FFmpeg"
        ),
    )
    return False
