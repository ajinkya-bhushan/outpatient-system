"""
app/api/routes_upload.py
─────────────────────────
POST /api/v1/transcribe  – file-upload transcription endpoint.

Request
-------
  multipart/form-data:
    file     : audio file (required)
    engine   : str  (optional, default from settings)
    language : str  (optional, default auto-detect)
    task     : str  (optional, "transcribe" | "translate")

Response
--------
  TranscriptionResponse JSON (200 OK)

Error codes
-----------
  400 – validation failure (bad extension, MIME, size, duration)
  422 – pydantic schema validation failure (FastAPI default)
  500 – engine / inference error
  501 – engine not yet implemented

Flow
----
  1. Validate extension, MIME type, size.
  2. Write bytes to a temp file.
  3. ffprobe duration check (validates + fills audio_duration).
  4. Select & initialise engine (singleton from registry).
  5. Run transcription in thread pool (non-blocking).
  6. Return structured JSON response.
  7. Cleanup temp file (always – via finally).
"""

from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.audio.processor import prepare_audio_for_inference, save_upload_to_temp
from app.audio.validator import AudioValidationError, validate_audio_file
from app.core.logging import get_logger, request_id_ctx
from app.engines import get_engine
from app.schemas.transcription import TranscriptionResponse

router = APIRouter(tags=["Transcription"])
logger = get_logger(__name__)


@router.post(
    "/transcribe",
    response_model=TranscriptionResponse,
    summary="Transcribe an uploaded audio file",
    status_code=status.HTTP_200_OK,
)
async def transcribe_upload(
    file: UploadFile = File(..., description="Audio file to transcribe"),
    engine: str = Form(default="", description="Engine: whisper | whisperflow | openai"),
    language: str = Form(default="", description="BCP-47 language code (empty = auto-detect)"),
    task: str = Form(default="transcribe", description="transcribe | translate"),
) -> TranscriptionResponse:
    """Transcribe an uploaded audio file using the selected STT engine.

    Returns a JSON payload containing the transcript, language, timed segments,
    and performance metrics (processing time, RTF).
    """
    req_id = str(uuid.uuid4())[:8]
    request_id_ctx.set(req_id)

    logger.info(
        "upload_request_received",
        req_id=req_id,
        filename=file.filename,
        content_type=file.content_type,
        engine=engine or "default",
    )

    # ── Read upload bytes ─────────────────────────────────────────────────────
    file_bytes = await file.read()
    filename = file.filename or "upload.bin"

    # ── Step 1: validate extension, MIME, size ────────────────────────────────
    try:
        validate_audio_file(
            filename=filename,
            size_bytes=len(file_bytes),
            content_type=file.content_type,
        )
    except AudioValidationError as exc:
        logger.warning("upload_validation_failed", req_id=req_id, error=str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # ── Step 2: save to temp file ─────────────────────────────────────────────
    tmp_source: str | None = None
    tmp_wav: str | None = None
    wav_needs_cleanup = False

    try:
        tmp_source = save_upload_to_temp(file_bytes, filename)

        # ── Step 3: duration check (uses ffprobe) ─────────────────────────────
        try:
            validation_info = validate_audio_file(
                filename=filename,
                size_bytes=len(file_bytes),
                file_path=tmp_source,
                content_type=file.content_type,
            )
        except AudioValidationError as exc:
            logger.warning("duration_validation_failed", req_id=req_id, error=str(exc))
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

        # ── Step 4: convert to WAV if necessary ───────────────────────────────
        try:
            tmp_wav, wav_needs_cleanup = prepare_audio_for_inference(tmp_source)
        except (RuntimeError, FileNotFoundError) as exc:
            logger.error("audio_conversion_failed", req_id=req_id, error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Audio conversion failed: {exc}",
            )

        # ── Step 5: select engine ─────────────────────────────────────────────
        engine_name = engine.strip() or None
        try:
            stt_engine = get_engine(engine_name)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        except NotImplementedError as exc:
            raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc))

        # ── Step 6: transcribe ────────────────────────────────────────────────
        lang = language.strip() or None
        try:
            result = await stt_engine.transcribe(
                audio_path=tmp_wav,
                language=lang,
                task=task or "transcribe",
            )
        except NotImplementedError as exc:
            raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc))
        except Exception as exc:
            logger.error(
                "transcription_failed",
                req_id=req_id,
                engine=engine_name,
                error=str(exc),
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Transcription error: {exc}",
            )

        # Patch duration if ffprobe got it before inference
        if result.get("audio_duration", 0.0) == 0.0 and validation_info.get("duration", 0.0) > 0:
            result["audio_duration"] = validation_info["duration"]

        logger.info(
            "upload_request_completed",
            req_id=req_id,
            engine=result.get("engine"),
            model=result.get("model"),
            rtf=result.get("real_time_factor"),
        )

        return TranscriptionResponse(**result)

    finally:
        # ── Step 7: always clean up temp files ────────────────────────────────
        for path in [tmp_source, tmp_wav if wav_needs_cleanup else None]:
            if path and os.path.exists(path):
                os.unlink(path)
                logger.debug("temp_file_cleaned", path=path)
