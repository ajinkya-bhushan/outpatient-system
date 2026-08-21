"""STT routes: upload transcription and live recording proxy."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, File, Form, UploadFile, WebSocket, WebSocketDisconnect

from app.api.errors import raise_app_error
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger, request_id_ctx
from app.modules.stt.service import get_stt_service
from app.services import pipeline as pipeline_service

router = APIRouter(prefix="/stt", tags=["STT"])
logger = get_logger(__name__)


@router.post("/transcribe")
async def transcribe_upload(
    file: UploadFile = File(..., description="Encounter audio"),
    engine: str = Form(default=""),
    language: str = Form(default=""),
    task: str = Form(default="transcribe"),
    encounter_id: str = Form(default=""),
):
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


@router.websocket("/live")
async def live_proxy(ws: WebSocket) -> None:
    """Proxy live recording WebSocket frames to sst_v1."""
    await ws.accept()
    import websockets

    upstream_url = get_stt_service().live_url()
    logger.info("stt_live_proxy_started", upstream=upstream_url)
    try:
        async with websockets.connect(upstream_url, max_size=settings.max_audio_size_bytes) as upstream:
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
                    else:
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
