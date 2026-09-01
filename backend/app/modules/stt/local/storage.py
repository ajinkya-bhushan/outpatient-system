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

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

RESULT_FILENAME = "result.json"
WAV_FILENAME = "audio.wav"
ORIGINAL_STEM = "original"
PLAIN_TRANSCRIPT_FILENAME = "plain.txt"
LABELLED_TRANSCRIPT_FILENAME = "labelled.txt"

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
    created_date: str
    original_key: str | None = None
    wav_key: str | None = None
    result_key: str | None = None
    plain_text_key: str | None = None
    labelled_text_key: str | None = None
    cleanup: tempfile.TemporaryDirectory | None = None

    @property
    def result_path(self) -> Path:
        return self.job_dir / RESULT_FILENAME

    @property
    def uses_object_storage(self) -> bool:
        return self.wav_key is not None


def new_job_id() -> str:
    """Opaque, unguessable job identifier."""
    return uuid4().hex


def storage_root() -> Path:
    return Path(settings.AUDIO_STORAGE_DIR).expanduser().resolve()


def object_storage_enabled() -> bool:
    return settings.object_storage_enabled


def bucket_name() -> str:
    return settings.OBJECT_STORAGE_BUCKET


def _object_prefix() -> str:
    return settings.OBJECT_STORAGE_PREFIX.strip("/")


def object_key(job_id: str, filename: str, created_on: date | None = None) -> str:
    day = (created_on or datetime.now(timezone.utc).date()).isoformat()
    prefix = _object_prefix()
    base = f"{day}/{job_id}/{filename}"
    return f"{prefix}/{base}" if prefix else base


def object_uri(key: str | None) -> str | None:
    if not key:
        return None
    return f"s3://{bucket_name()}/{key}"


def _s3_client():
    kwargs: dict[str, Any] = {
        "region_name": settings.OBJECT_STORAGE_REGION,
        "config": Config(signature_version="s3v4"),
    }
    if settings.OBJECT_STORAGE_ENDPOINT:
        kwargs["endpoint_url"] = settings.OBJECT_STORAGE_ENDPOINT
    if settings.OBJECT_STORAGE_ACCESS_KEY and settings.OBJECT_STORAGE_SECRET_KEY:
        kwargs["aws_access_key_id"] = settings.OBJECT_STORAGE_ACCESS_KEY
        kwargs["aws_secret_access_key"] = settings.OBJECT_STORAGE_SECRET_KEY
    return boto3.client("s3", **kwargs)


def ensure_bucket() -> None:
    """Create the configured bucket on demand.

    MinIO does not auto-create buckets. Calling this on every upload is cheap
    and keeps local development to a single ``docker compose up``.
    """
    client = _s3_client()
    bucket = bucket_name()
    try:
        client.head_bucket(Bucket=bucket)
        return
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code not in {"404", "NoSuchBucket"} and status != 404:
            raise

    client.create_bucket(Bucket=bucket)


def _upload_file(path: Path, key: str, content_type: str) -> None:
    ensure_bucket()
    _s3_client().upload_file(
        str(path),
        bucket_name(),
        key,
        ExtraArgs={"ContentType": content_type},
    )
    logger.info("stt_object_saved", key=key, bytes=path.stat().st_size)


def _put_text(key: str, text: str, content_type: str = "text/plain; charset=utf-8") -> None:
    ensure_bucket()
    _s3_client().put_object(
        Bucket=bucket_name(),
        Key=key,
        Body=text.encode("utf-8"),
        ContentType=content_type,
    )
    logger.info("stt_object_saved", key=key, bytes=len(text.encode("utf-8")))


def _get_object(key: str, byte_range: str | None = None) -> dict[str, Any] | None:
    kwargs: dict[str, Any] = {"Bucket": bucket_name(), "Key": key}
    if byte_range:
        kwargs["Range"] = byte_range
    try:
        return _s3_client().get_object(**kwargs)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in {"NoSuchKey", "404"} or status == 404:
            return None
        raise


def job_dir_for(job_id: str, created_on: date | None = None) -> Path:
    day = (created_on or datetime.now(timezone.utc).date()).isoformat()
    return storage_root() / day / job_id


def save_upload(file_bytes: bytes, extension: str, job_id: str | None = None) -> StoredAudio:
    """Write the uploaded bytes to a fresh job directory.

    The converted WAV path is returned but not created; the caller runs the
    ffmpeg conversion into it.
    """
    job_id = job_id or new_job_id()
    created_on = datetime.now(timezone.utc).date()
    created_date = created_on.isoformat()

    if object_storage_enabled():
        cleanup = temporary_workspace()
        job_dir = Path(cleanup.name)
    else:
        cleanup = None
        job_dir = job_dir_for(job_id, created_on=created_on)
    job_dir.mkdir(parents=True, exist_ok=True)

    original_path = job_dir / f"{ORIGINAL_STEM}{extension}"
    original_path.write_bytes(file_bytes)
    original_key = object_key(job_id, f"{ORIGINAL_STEM}{extension}", created_on)
    wav_key = object_key(job_id, WAV_FILENAME, created_on)
    result_key = object_key(job_id, RESULT_FILENAME, created_on)
    plain_text_key = object_key(job_id, PLAIN_TRANSCRIPT_FILENAME, created_on)
    labelled_text_key = object_key(job_id, LABELLED_TRANSCRIPT_FILENAME, created_on)

    if object_storage_enabled():
        _upload_file(original_path, original_key, "application/octet-stream")

    logger.info(
        "stt_audio_saved",
        job_id=job_id,
        bytes=len(file_bytes),
        extension=extension,
        storage=settings.OBJECT_STORAGE_PROVIDER,
    )
    return StoredAudio(
        job_id=job_id,
        job_dir=job_dir,
        original_path=original_path,
        wav_path=job_dir / WAV_FILENAME,
        created_date=created_date,
        original_key=original_key if object_storage_enabled() else None,
        wav_key=wav_key if object_storage_enabled() else None,
        result_key=result_key if object_storage_enabled() else None,
        plain_text_key=plain_text_key if object_storage_enabled() else None,
        labelled_text_key=labelled_text_key if object_storage_enabled() else None,
        cleanup=cleanup,
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
    if stored.uses_object_storage:
        if stored.wav_path.exists() and stored.wav_key:
            _upload_file(stored.wav_path, stored.wav_key, "audio/wav")
        if stored.result_key:
            _put_text(
                stored.result_key,
                json.dumps(payload, indent=2),
                "application/json; charset=utf-8",
            )
        text = str(payload.get("text") or "")
        labelled_text = str(payload.get("labelled_text") or "")
        if text and stored.plain_text_key:
            _put_text(stored.plain_text_key, text)
        if labelled_text and stored.labelled_text_key:
            _put_text(stored.labelled_text_key, labelled_text)
    logger.info("stt_result_saved", job_id=stored.job_id)
    return stored.result_path


def load_result(job_id: str) -> dict[str, Any] | None:
    """Return a persisted result payload, or ``None`` if there is no such job."""
    if not is_valid_job_id(job_id):
        return None
    if object_storage_enabled():
        for key in _iter_result_keys_for_job(job_id):
            obj = _get_object(key)
            if obj is None:
                continue
            return json.loads(obj["Body"].read().decode("utf-8"))
        return None
    for result_path in storage_root().glob(f"*/{job_id}/{RESULT_FILENAME}"):
        return json.loads(result_path.read_text(encoding="utf-8"))
    return None


def find_job_dir(job_id: str) -> Path | None:
    """Locate a job directory without loading its result."""
    if not is_valid_job_id(job_id):
        return None
    if object_storage_enabled():
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


def _iter_result_keys_for_job(job_id: str) -> list[str]:
    prefix = _object_prefix()
    search_prefix = f"{prefix}/" if prefix else ""
    client = _s3_client()
    paginator = client.get_paginator("list_objects_v2")
    matches: list[str] = []
    try:
        for page in paginator.paginate(Bucket=bucket_name(), Prefix=search_prefix):
            for item in page.get("Contents", []):
                key = item["Key"]
                if key.endswith(f"/{job_id}/{RESULT_FILENAME}"):
                    matches.append(key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in {"NoSuchBucket", "404"} or status == 404:
            return []
        raise
    return sorted(matches, reverse=True)


def _audio_key_for_job(job_id: str) -> str | None:
    for result_key in _iter_result_keys_for_job(job_id):
        return result_key.rsplit("/", 1)[0] + f"/{WAV_FILENAME}"
    return None


def open_audio_stream(job_id: str, byte_range: str | None = None) -> dict[str, Any] | None:
    """Open a stored WAV object from object storage."""
    if not (is_valid_job_id(job_id) and object_storage_enabled()):
        return None
    key = _audio_key_for_job(job_id)
    if not key:
        return None
    obj = _get_object(key, byte_range=byte_range)
    if obj is None:
        return None
    obj["Key"] = key
    return obj


def audio_reference(stored: StoredAudio | None) -> str | None:
    if stored is None:
        return None
    return object_uri(stored.wav_key) if stored.uses_object_storage else str(stored.wav_path)


def list_jobs(limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
    """List stored jobs, newest first.

    Returns a summary per job — never the transcript — plus the total count so
    callers can paginate.
    """
    if object_storage_enabled():
        keys = _list_result_keys()
        total = len(keys)
        summaries = []
        for key in keys[offset : offset + limit]:
            parts = key.split("/")
            job_id = parts[-2]
            created_date = parts[-3] if len(parts) >= 3 else ""
            payload: dict[str, Any] = {}
            obj = _get_object(key)
            if obj is not None:
                try:
                    payload = json.loads(obj["Body"].read().decode("utf-8"))
                except json.JSONDecodeError:
                    payload = {}
            summaries.append(_summary_from_payload(job_id, created_date, payload))
        return summaries, total

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


def _list_result_keys() -> list[str]:
    prefix = _object_prefix()
    search_prefix = f"{prefix}/" if prefix else ""
    client = _s3_client()
    paginator = client.get_paginator("list_objects_v2")
    keys: list[str] = []
    try:
        for page in paginator.paginate(Bucket=bucket_name(), Prefix=search_prefix):
            keys.extend(
                item["Key"]
                for item in page.get("Contents", [])
                if item["Key"].endswith(RESULT_FILENAME)
            )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in {"NoSuchBucket", "404"} or status == 404:
            return []
        raise
    return sorted(keys, reverse=True)


def _summary_from_payload(job_id: str, created_date: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "created_date": created_date,
        "created_at": payload.get("created_at"),
        "encounter_id": payload.get("encounter_id"),
        "language": payload.get("language"),
        "num_speakers": payload.get("num_speakers"),
        "audio_duration": (payload.get("audio") or {}).get("duration")
        or payload.get("audio_duration"),
        "has_result": True,
        "has_audio": bool((payload.get("audio") or {}).get("stored")),
    }


def delete_job(job_id: str) -> bool:
    """Remove a job directory and everything in it."""
    if object_storage_enabled():
        if not is_valid_job_id(job_id):
            return False
        result_keys = _iter_result_keys_for_job(job_id)
        if not result_keys:
            return False
        client = _s3_client()
        deleted = False
        for result_key in result_keys:
            prefix = result_key.rsplit("/", 1)[0] + "/"
            page = client.list_objects_v2(Bucket=bucket_name(), Prefix=prefix)
            objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if objects:
                client.delete_objects(Bucket=bucket_name(), Delete={"Objects": objects})
                deleted = True
        if deleted:
            logger.info("stt_job_deleted", job_id=job_id, storage=settings.OBJECT_STORAGE_PROVIDER)
        return deleted

    job_dir = find_job_dir(job_id)
    if job_dir is None:
        return False
    shutil.rmtree(job_dir)
    logger.info("stt_job_deleted", job_id=job_id)
    return True
