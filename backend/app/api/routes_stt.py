"""
app/api/routes_stt.py
──────────────────────
Speech-to-text and speaker-diarization endpoints.

    POST   /api/v1/stt/transcribe      audio file → plain transcript
    POST   /api/v1/stt/diarize         audio file → speaker-labelled transcript
    GET    /api/v1/stt/engine          active engine, device, model, readiness
    GET    /api/v1/stt/jobs            list stored jobs
    GET    /api/v1/stt/jobs/{job_id}   fetch a stored result
    GET    /api/v1/stt/jobs/{id}/audio stream a stored job's converted audio
    DELETE /api/v1/stt/jobs/{job_id}   delete a stored job and its audio
    WS     /api/v1/stt/live            live recording (remote engine only)

Full contract: backend/docs/STT_DIARIZATION_API.md
"""

from __future__ import annotations

import json
import uuid

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse

from app.api.errors import raise_app_error
from app.core.config import settings
from app.core.errors import AppError, ValidationFailed
from app.core.logging import get_logger, request_id_ctx
from app.modules.stt.local import storage
from app.modules.stt.schemas import (
    DiarizedTranscriptResponse,
    EngineStatusResponse,
    JobListResponse,
    JobSummary,
    TranscriptResult,
)
from app.modules.stt.service import get_stt_service
from app.services import pipeline as pipeline_service

router = APIRouter(prefix="/stt", tags=["STT"])
logger = get_logger(__name__)


def _parse_speaker_names(raw: str) -> dict[str, str] | None:
    """Parse the optional ``speaker_names`` JSON map from the form body."""
    if not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationFailed(
            f"speaker_names must be a JSON object such as "
            f'{{"speaker_0": "Doctor", "speaker_1": "Patient"}} — {exc}'
        ) from exc

    if not isinstance(parsed, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in parsed.items()
    ):
        raise ValidationFailed("speaker_names must be a JSON object of string to string.")
    return parsed


def _parse_optional_int(raw: str, field: str) -> int | None:
    """Parse an optional integer form field, treating blank as unset."""
    if not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ValidationFailed(f"{field} must be an integer, got {raw!r}.") from exc


@router.post(
    "/transcribe",
    response_model=TranscriptResult,
    summary="Transcribe an audio file to text",
)
async def transcribe_upload(
    file: UploadFile = File(..., description="Encounter audio file"),
    engine: str = Form(default="", description="Engine hint; honoured in remote mode only"),
    language: str = Form(default="", description="BCP-47 language code, blank to auto-detect"),
    task: str = Form(default="transcribe", description="transcribe (local supports this only)"),
    encounter_id: str = Form(default="", description="Attach the transcript to this encounter"),
) -> TranscriptResult:
    """Transcribe audio with no speaker labels.

    Use ``/diarize`` instead when the recording has more than one speaker and
    the caller needs to know who said what.
    """
    request_id_ctx.set(str(uuid.uuid4())[:8])
    file_bytes = await file.read()
    try:
        result = await get_stt_service().transcribe_upload(
            file_bytes=file_bytes,
            filename=file.filename or "upload.bin",
            content_type=file.content_type,
            engine=engine or None,
            language=language or None,
            task=task or "transcribe",
        )
    except AppError as exc:
        raise_app_error(exc)

    pipeline_service.save_transcript(
        result.text,
        encounter_id=encounter_id or None,
        language=result.language,
        source="upload",
        extra=result.model_dump(),
    )
    return result


@router.post(
    "/diarize",
    response_model=DiarizedTranscriptResponse,
    summary="Transcribe an audio file and label each turn with a speaker",
)
async def diarize_upload(
    file: UploadFile = File(..., description="Encounter audio file"),
    num_speakers: str = Form(
        default="",
        description="Known speaker count. Blank uses DIARIZATION_NUM_SPEAKERS "
        "(default 2); 0 forces automatic estimation, which is less reliable.",
    ),
    min_speakers: str = Form(default="", description="Lower bound when estimating"),
    max_speakers: str = Form(default="", description="Upper bound when estimating"),
    language: str = Form(default="", description="BCP-47 language code, blank to auto-detect"),
    speaker_names: str = Form(
        default="",
        description='JSON map of speaker id to display name, e.g. {"speaker_0": "Doctor"}',
    ),
    encounter_id: str = Form(default="", description="Attach the transcript to this encounter"),
    save_audio: bool = Form(default=True, description="Persist the audio and result to disk"),
) -> DiarizedTranscriptResponse:
    """Produce a speaker-labelled transcript from an audio file.

    Speaker labels are anonymous cluster ids (``speaker_0``, ``speaker_1``).
    Mapping them to real roles is a separate step: pass ``speaker_names``, or
    let the caller assign them in the UI.
    """
    request_id_ctx.set(str(uuid.uuid4())[:8])
    file_bytes = await file.read()

    try:
        result = await get_stt_service().diarize_upload(
            file_bytes=file_bytes,
            filename=file.filename or "upload.bin",
            num_speakers=_parse_optional_int(num_speakers, "num_speakers"),
            min_speakers=_parse_optional_int(min_speakers, "min_speakers"),
            max_speakers=_parse_optional_int(max_speakers, "max_speakers"),
            language=language or None,
            speaker_names=_parse_speaker_names(speaker_names),
            encounter_id=encounter_id or None,
            save_audio=save_audio,
        )
    except AppError as exc:
        raise_app_error(exc)

    if result.text.strip():
        pipeline_service.save_transcript(
            result.text,
            encounter_id=encounter_id or None,
            language=result.language,
            source="upload",
            extra={
                "segments": [
                    {
                        "id": index,
                        "start": turn.start,
                        "end": turn.end,
                        "text": f"{turn.speaker_name}: {turn.text}",
                    }
                    for index, turn in enumerate(result.turns)
                ],
                "audio_duration": result.metrics.audio_duration,
                "processing_time": result.metrics.total_seconds,
                "real_time_factor": result.metrics.total_rtf,
                "engine": f"local:{result.engine.whisper_backend}+diarization",
                "model": result.engine.whisper_model,
                "job_id": result.job_id,
                "num_speakers": result.num_speakers,
            },
        )
    return result


@router.get(
    "/engine",
    response_model=EngineStatusResponse,
    summary="Active STT engine, device and model readiness",
)
async def engine_status() -> EngineStatusResponse:
    """Report the engine without loading models, for probes and diagnostics."""
    return get_stt_service().engine_status()


@router.get("/jobs", response_model=JobListResponse, summary="List stored transcription jobs")
async def list_jobs(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> JobListResponse:
    """List stored jobs, newest first. Summaries only — no transcript text."""
    jobs, total = storage.list_jobs(limit=limit, offset=offset)
    return JobListResponse(
        total=total,
        limit=limit,
        offset=offset,
        jobs=[JobSummary(**job) for job in jobs],
    )


@router.get("/jobs/{job_id}", summary="Fetch a stored transcription result")
async def get_job(job_id: str) -> dict:
    """Return the persisted result payload for a job.

    The shape matches whichever endpoint created it: ``DiarizedTranscriptResponse``
    for ``/diarize``, ``TranscriptResult`` for ``/transcribe``.
    """
    payload = storage.load_result(job_id)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No stored result for job {job_id!r}.",
        )
    return payload


@router.get(
    "/jobs/{job_id}/audio",
    response_class=FileResponse,
    summary="Stream a stored job's converted audio",
)
async def get_job_audio(job_id: str, request: Request) -> FileResponse | StreamingResponse:
    """Stream the 16 kHz mono WAV a job was transcribed from.

    Clients play back individual turns by seeking to ``turn.start``, so this
    serves the *converted* audio rather than the original upload: the turn
    timestamps are measured against what the models actually read, and a lossy
    original can drift from it by ~100 ms over a minute.

    Starlette implements ``Range`` on ``FileResponse``, so seeking works
    without extra handling here.
    """
    if storage.object_storage_enabled():
        obj = storage.open_audio_stream(job_id, request.headers.get("range"))
        if obj is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No stored audio for job {job_id!r}.",
            )
        headers = {
            "Cache-Control": "private, no-store",
            "Accept-Ranges": "bytes",
        }
        if obj.get("ContentRange"):
            headers["Content-Range"] = obj["ContentRange"]
        if obj.get("ContentLength") is not None:
            headers["Content-Length"] = str(obj["ContentLength"])
        return StreamingResponse(
            obj["Body"].iter_chunks(),
            status_code=status.HTTP_206_PARTIAL_CONTENT
            if obj.get("ContentRange")
            else status.HTTP_200_OK,
            media_type=obj.get("ContentType") or "audio/wav",
            headers=headers,
        )

    wav_path = storage.job_audio_path(job_id)
    if wav_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No stored audio for job {job_id!r}.",
        )
    return FileResponse(
        wav_path,
        media_type="audio/wav",
        headers={"Cache-Control": "private, no-store"},
    )


@router.delete("/jobs/{job_id}", summary="Delete a stored job and its audio")
async def delete_job(job_id: str) -> dict:
    """Remove a job directory, including the PHI audio it holds."""
    if not storage.delete_job(job_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No stored job {job_id!r}.",
        )
    return {"job_id": job_id, "deleted": True}


@router.websocket("/live")
async def live_proxy(ws: WebSocket) -> None:
    """Proxy live recording frames to sst_v1.

    Only available with ``STT_ENGINE_MODE=remote``. The local engine is
    file-based; incremental streaming diarization is future work.
    """
    await ws.accept()

    service = get_stt_service()
    try:
        upstream_url = service.live_url()
    except AppError as exc:
        await ws.send_text(json.dumps({"type": "error", "detail": exc.message}))
        await ws.close(code=1011)
        return

    import websockets

    logger.info("stt_live_proxy_started", upstream=upstream_url)
    try:
        async with websockets.connect(
            upstream_url, max_size=settings.max_audio_size_bytes
        ) as upstream:

            async def client_to_upstream() -> None:
                try:
                    while True:
                        message = await ws.receive()
                        if message["type"] == "websocket.disconnect":
                            await upstream.close()
                            return
                        if "bytes" in message and message["bytes"] is not None:
                            await upstream.send(message["bytes"])
                        elif "text" in message and message["text"] is not None:
                            await upstream.send(message["text"])
                except WebSocketDisconnect:
                    await upstream.close()

            async def upstream_to_client() -> None:
                async for payload in upstream:
                    if isinstance(payload, bytes):
                        await ws.send_bytes(payload)
                        continue

                    await ws.send_text(payload)
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if data.get("type") == "final" and data.get("text"):
                        pipeline_service.save_transcript(
                            data["text"],
                            language=data.get("language"),
                            source="live",
                            extra={
                                "audio_duration": data.get("audio_duration") or 0.0,
                                "processing_time": data.get("processing_time") or 0.0,
                                "real_time_factor": data.get("real_time_factor") or 0.0,
                                "engine": "live",
                                "model": "sst_v1",
                            },
                        )

            import asyncio

            await asyncio.gather(client_to_upstream(), upstream_to_client())
    except Exception as exc:
        logger.error("stt_live_proxy_failed", error=str(exc))
        try:
            await ws.send_text(json.dumps({"type": "error", "detail": str(exc)}))
        except Exception:
            pass
        await ws.close()
