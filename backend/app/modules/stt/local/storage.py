"""
app/modules/stt/local/storage.py
─────────────────────────────────
Local persistence for uploaded encounter audio and its transcription result.

Layout — one directory per job, dated so an operator can reason about retention
without opening any files:

    {AUDIO_STORAGE_DIR}/2026-08-27/<job_id>/
    ├── original.<ext>   bytes exactly as uploaded
    ├── audio.wav        16 kHz mono, the samples the models actually consumed
    └── result.json      the full API response

**This audio and the transcript inside ``result.json`` are PHI.** Local disk is
a prototype measure: there is no encryption at rest, no access control beyond
filesystem permissions, and no automatic expiry. Retention policy is still an
open question in the feature spec, so nothing here deletes anything on its own.
Log lines therefore carry identifiers and sizes only, never transcript text.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

RESULT_FILENAME = "result.json"
WAV_FILENAME = "audio.wav"
ORIGINAL_STEM = "original"

_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def is_valid_job_id(job_id: str) -> bool:
    """Job ids are uuid4 hex and nothing else.

    Lookups interpolate the id into a glob pattern, so an id carrying ``..`` or
    a path separator could otherwise reach outside the storage root. Every
    lookup below screens the id through here first.
    """
    return bool(_JOB_ID_RE.match(job_id))


@dataclass
class StoredAudio:
    """Filesystem locations for one job's audio."""

    job_id: str
    job_dir: Path
    original_path: Path
    wav_path: Path

    @property
    def result_path(self) -> Path:
        return self.job_dir / RESULT_FILENAME


def new_job_id() -> str:
    """Opaque, unguessable job identifier."""
    return uuid4().hex


def storage_root() -> Path:
    return Path(settings.AUDIO_STORAGE_DIR).expanduser().resolve()


def job_dir_for(job_id: str, created_on: date | None = None) -> Path:
    day = (created_on or datetime.now(timezone.utc).date()).isoformat()
    return storage_root() / day / job_id


def save_upload(file_bytes: bytes, extension: str, job_id: str | None = None) -> StoredAudio:
    """Write the uploaded bytes to a fresh job directory.

    The converted WAV path is returned but not created; the caller runs the
    ffmpeg conversion into it.
    """
    job_id = job_id or new_job_id()
    job_dir = job_dir_for(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    original_path = job_dir / f"{ORIGINAL_STEM}{extension}"
    original_path.write_bytes(file_bytes)

    logger.info(
        "stt_audio_saved",
        job_id=job_id,
        bytes=len(file_bytes),
        extension=extension,
    )
    return StoredAudio(
        job_id=job_id,
        job_dir=job_dir,
        original_path=original_path,
        wav_path=job_dir / WAV_FILENAME,
    )


def temporary_workspace() -> tempfile.TemporaryDirectory:
    """Scratch directory for requests that opt out of persistence.

    Used when ``save_audio=false``: the audio still has to hit the disk for
    ffmpeg and SpeechBrain's file-based VAD, but it is removed when the context
    manager closes.
    """
    return tempfile.TemporaryDirectory(prefix="stt-transient-")


def save_result(stored: StoredAudio, payload: dict[str, Any]) -> Path:
    """Persist the response payload next to the audio."""
    stored.job_dir.mkdir(parents=True, exist_ok=True)
    stored.result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("stt_result_saved", job_id=stored.job_id)
    return stored.result_path


def load_result(job_id: str) -> dict[str, Any] | None:
    """Return a persisted result payload, or ``None`` if there is no such job."""
    if not is_valid_job_id(job_id):
        return None
    for result_path in storage_root().glob(f"*/{job_id}/{RESULT_FILENAME}"):
        return json.loads(result_path.read_text(encoding="utf-8"))
    return None


def find_job_dir(job_id: str) -> Path | None:
    """Locate a job directory without loading its result."""
    if not is_valid_job_id(job_id):
        return None
    for candidate in storage_root().glob(f"*/{job_id}"):
        if candidate.is_dir():
            return candidate
    return None


def job_audio_path(job_id: str) -> Path | None:
    """Path to a job's converted 16 kHz WAV, or ``None`` if it is not stored.

    Callers wanting playback should use this rather than the original upload:
    turn timestamps are measured against the converted audio the models read.
    """
    job_dir = find_job_dir(job_id)
    if job_dir is None:
        return None
    wav_path = job_dir / WAV_FILENAME
    return wav_path if wav_path.exists() else None


def list_jobs(limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
    """List stored jobs, newest first.

    Returns a summary per job — never the transcript — plus the total count so
    callers can paginate.
    """
    root = storage_root()
    if not root.exists():
        return [], 0

    job_dirs = sorted(
        (path for path in root.glob("*/*") if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    total = len(job_dirs)

    summaries: list[dict[str, Any]] = []
    for job_dir in job_dirs[offset : offset + limit]:
        summary: dict[str, Any] = {
            "job_id": job_dir.name,
            "created_date": job_dir.parent.name,
            "has_result": (job_dir / RESULT_FILENAME).exists(),
            "has_audio": (job_dir / WAV_FILENAME).exists(),
        }
        result_path = job_dir / RESULT_FILENAME
        if result_path.exists():
            try:
                payload = json.loads(result_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {}
            summary.update(
                {
                    "created_at": payload.get("created_at"),
                    "encounter_id": payload.get("encounter_id"),
                    "language": payload.get("language"),
                    "num_speakers": payload.get("num_speakers"),
                    "audio_duration": (payload.get("audio") or {}).get("duration"),
                }
            )
        summaries.append(summary)

    return summaries, total


def delete_job(job_id: str) -> bool:
    """Remove a job directory and everything in it."""
    job_dir = find_job_dir(job_id)
    if job_dir is None:
        return False
    shutil.rmtree(job_dir)
    logger.info("stt_job_deleted", job_id=job_id)
    return True
