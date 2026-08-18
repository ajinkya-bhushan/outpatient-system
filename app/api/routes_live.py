"""
app/api/routes_live.py
───────────────────────
WebSocket /api/v1/live  -  live / streaming transcription endpoint.

Protocol  (client -> server)
----------------------------
TEXT frames (JSON control):
  { "type": "start",  "engine": "whisper", "language": "en" }
      -> Server replies: { "type": "session_started", "session_id": "...", "timestamp": ... }

  { "type": "stop" }
      -> Server drains remaining audio, emits final transcript, then:
         { "type": "session_ended", "metrics": {...} }

BINARY frames:
  Raw audio bytes (WebM / PCM / any format the engine accepts).
  Sent by the browser MediaRecorder in timesliced chunks (typically 500ms).

Protocol  (server -> client)
----------------------------
  { "type": "partial",  "text": "...", "latency_ms": 0.0, "timestamp": ... }
  { "type": "final",    "text": "...", "latency_ms": 0.0, "timestamp": ... }
  { "type": "error",    "detail": "..." }
  { "type": "session_started", "session_id": "...", "timestamp": ... }
  { "type": "session_ended",   "metrics": { ... } }

Streaming design
----------------
Producer  : WebSocket receiver task  ->  asyncio.Queue of (bytes | None)
Consumer  : Transcription task that reads from the queue, accumulates a
            rolling audio buffer, and calls the engine every PARTIAL_INTERVAL
            seconds of audio.  Sends partials back to the client in real-time.

On "stop": producer puts None sentinel, consumer drains remaining audio,
emits final result, sends session_ended.

Important limitations documented
---------------------------------
1. WhisperFlow (pip: whisperflow) conflicts with FastAPI >= 0.111.
   When whisperflow is not installed the engine falls back to the plain
   WhisperEngine which is a BATCH model, not truly real-time.
   This means you will NOT get transcript words as they are spoken -
   you get a result after each PARTIAL_INTERVAL seconds of audio.
2. True word-level streaming requires either:
   a) whisperflow installed in an isolated venv (separate process / microservice)
   b) faster-whisper with streaming API
   c) a third-party real-time ASR service
3. Browser MediaRecorder emits audio/webm which Whisper accepts via ffmpeg.
   Ensure ffmpeg is on PATH.
4. Latency on CPU with base model: typically 1-4x real-time RTF.
   Use tiny model for lower latency at the cost of accuracy.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.audio.chunker import AudioChunker
from app.core.logging import get_logger, request_id_ctx
from app.engines import get_engine

router = APIRouter(tags=["Live Transcription"])
logger = get_logger(__name__)

# How many seconds of audio to accumulate before a partial transcription attempt.
# Lower = more responsive but higher compute load.  Higher = lower load but lag.
PARTIAL_INTERVAL_SECONDS: float = 2.0

# 16 kHz mono 16-bit PCM: 16000 * 2 * PARTIAL_INTERVAL_SECONDS bytes
# Used as the rolling buffer threshold.
PARTIAL_CHUNK_BYTES: int = int(16_000 * 2 * PARTIAL_INTERVAL_SECONDS)


# ── Session metrics tracker ────────────────────────────────────────────────────

class SessionMetrics:
    """Track per-session latency and audio statistics."""

    def __init__(self) -> None:
        self.session_start: float = time.perf_counter()
        self.first_audio_at: float | None = None
        self.first_transcript_at: float | None = None
        self.total_audio_bytes: int = 0
        self.partial_count: int = 0
        self.final_text: str = ""

    def on_audio(self, n_bytes: int) -> None:
        if self.first_audio_at is None:
            self.first_audio_at = time.perf_counter()
        self.total_audio_bytes += n_bytes

    def on_partial(self) -> None:
        if self.first_transcript_at is None:
            self.first_transcript_at = time.perf_counter()
        self.partial_count += 1

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self.session_start) * 1000

    def time_to_first_token_ms(self) -> float | None:
        if self.first_audio_at and self.first_transcript_at:
            return round((self.first_transcript_at - self.first_audio_at) * 1000, 1)
        return None

    def summary(self) -> dict[str, Any]:
        total_ms = self.elapsed_ms()
        audio_duration_s = self.total_audio_bytes / (16_000 * 2) if self.total_audio_bytes else 0.0
        return {
            "total_session_ms": round(total_ms, 1),
            "time_to_first_token_ms": self.time_to_first_token_ms(),
            "total_audio_bytes": self.total_audio_bytes,
            "estimated_audio_duration_s": round(audio_duration_s, 2),
            "partial_results_sent": self.partial_count,
            "final_transcript_length": len(self.final_text),
        }


# ── WebSocket endpoint ─────────────────────────────────────────────────────────

@router.websocket("/live")
async def live_transcribe(ws: WebSocket) -> None:
    """WebSocket endpoint for real-time audio transcription.

    See module docstring for full protocol documentation.
    """
    await ws.accept()

    session_id = str(uuid.uuid4())[:8]
    request_id_ctx.set(session_id)
    metrics = SessionMetrics()

    logger.info("ws_session_opened", session_id=session_id)

    # ── Session state ──────────────────────────────────────────────────────────
    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=128)
    engine_name: str = "whisper"
    language: str | None = None
    session_active: bool = False
    transcription_task: asyncio.Task | None = None

    try:
        while True:
            message = await ws.receive()

            # ── Binary: audio chunk ────────────────────────────────────────────
            if message["type"] == "websocket.receive" and "bytes" in message and message["bytes"]:
                if not session_active:
                    await _send_error(ws, "Send 'start' before audio data")
                    continue

                chunk_bytes = message["bytes"]
                metrics.on_audio(len(chunk_bytes))

                try:
                    await asyncio.wait_for(audio_queue.put(chunk_bytes), timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning("ws_audio_queue_full", session_id=session_id)
                    await _send_error(ws, "Audio buffer full – reduce chunk rate")
                continue

            # ── Text: JSON control frame ───────────────────────────────────────
            if message["type"] == "websocket.receive" and "text" in message:
                try:
                    payload = json.loads(message["text"])
                except json.JSONDecodeError:
                    await _send_error(ws, "Invalid JSON control frame")
                    continue

                msg_type = payload.get("type", "")

                # ── start ──────────────────────────────────────────────────────
                if msg_type == "start":
                    if session_active:
                        await _send_error(ws, "Session already started")
                        continue

                    engine_name = payload.get("engine", "whisper")
                    language = payload.get("language") or None

                    # Validate engine exists before accepting
                    try:
                        get_engine(engine_name)
                    except (ValueError, RuntimeError) as exc:
                        await _send_error(ws, f"Engine unavailable: {exc}")
                        continue

                    session_active = True
                    metrics = SessionMetrics()  # reset metrics for new session

                    logger.info(
                        "ws_session_started",
                        session_id=session_id,
                        engine=engine_name,
                        language=language,
                    )

                    now_ts = time.time()
                    await ws.send_text(json.dumps({
                        "type": "session_started",
                        "session_id": session_id,
                        "engine": engine_name,
                        "language": language,
                        "timestamp": now_ts,
                    }))

                    # Launch background streaming transcription task
                    transcription_task = asyncio.create_task(
                        _stream_transcription(
                            ws=ws,
                            audio_queue=audio_queue,
                            engine_name=engine_name,
                            language=language,
                            session_id=session_id,
                            metrics=metrics,
                        )
                    )

                # ── stop ───────────────────────────────────────────────────────
                elif msg_type == "stop":
                    if not session_active or transcription_task is None:
                        await _send_error(ws, "No active session")
                        continue

                    session_active = False
                    # Signal end-of-stream to the transcription task
                    await audio_queue.put(None)

                    # Wait for the transcription task to drain and finish
                    try:
                        await asyncio.wait_for(transcription_task, timeout=60.0)
                    except asyncio.TimeoutError:
                        logger.warning("ws_transcription_timeout", session_id=session_id)
                        transcription_task.cancel()

                    summary = metrics.summary()
                    logger.info("ws_session_completed", session_id=session_id, **summary)

                    await ws.send_text(json.dumps({
                        "type": "session_ended",
                        "session_id": session_id,
                        "timestamp": time.time(),
                        "metrics": summary,
                    }))
                    break

                else:
                    await _send_error(ws, f"Unknown message type: '{msg_type}'")

            # ── WebSocket disconnect frame ──────────────────────────────────────
            elif message["type"] == "websocket.disconnect":
                logger.info("ws_client_disconnected_mid_session", session_id=session_id)
                break

    except WebSocketDisconnect:
        logger.info("ws_client_disconnected", session_id=session_id)

    except Exception as exc:
        logger.error("ws_session_error", session_id=session_id, error=str(exc), exc_info=True)
        try:
            await _send_error(ws, f"Internal error: {exc}")
            await ws.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass

    finally:
        # Cancel transcription task if still running (e.g. on abrupt disconnect)
        if transcription_task and not transcription_task.done():
            transcription_task.cancel()
            try:
                await transcription_task
            except (asyncio.CancelledError, Exception):
                pass
        logger.info("ws_session_closed", session_id=session_id)


# ── Streaming transcription background task ────────────────────────────────────

async def _stream_transcription(
    ws: WebSocket,
    audio_queue: asyncio.Queue,
    engine_name: str,
    language: str | None,
    session_id: str,
    metrics: SessionMetrics,
) -> None:
    """Background task: consume audio queue, emit partials, emit final.

    Limitation notice
    -----------------
    When using WhisperEngine (batch model) this function accumulates
    PARTIAL_INTERVAL_SECONDS of audio before each transcription pass.
    This means latency is at minimum PARTIAL_INTERVAL_SECONDS + inference time.

    WhisperFlowEngine (if installed) processes each chunk incrementally
    and has lower latency, but is not truly word-by-word real-time either.
    """
    stt = get_engine(engine_name)

    accumulated = bytearray()   # rolling audio buffer (all chunks so far)
    last_partial_size = 0       # bytes at the time of last partial
    partial_text_history: list[str] = []

    try:
        while True:
            try:
                chunk = await asyncio.wait_for(audio_queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning("ws_audio_queue_timeout", session_id=session_id)
                break

            if chunk is None:
                # End-of-stream sentinel — proceed to final transcription
                break

            accumulated.extend(chunk)

            # Attempt a partial transcription every PARTIAL_CHUNK_BYTES of NEW audio
            new_bytes = len(accumulated) - last_partial_size
            if new_bytes >= PARTIAL_CHUNK_BYTES:
                partial_result = await _transcribe_buffer(
                    stt, bytes(accumulated), language, session_id
                )
                if partial_result is not None:
                    text = partial_result.get("text", "").strip()
                    if text and text not in partial_text_history:
                        partial_text_history.append(text)
                        metrics.on_partial()
                        await _safe_send(ws, {
                            "type": "partial",
                            "text": text,
                            "latency_ms": round(metrics.elapsed_ms(), 1),
                            "timestamp": time.time(),
                            "chunk_audio_s": round(len(accumulated) / (16_000 * 2), 2),
                        })
                last_partial_size = len(accumulated)

        # ── Final transcription ────────────────────────────────────────────────
        if accumulated:
            final_result = await _transcribe_buffer(
                stt, bytes(accumulated), language, session_id
            )
            if final_result is not None:
                final_text = final_result.get("text", "").strip()
                metrics.final_text = final_text
                audio_dur = final_result.get("audio_duration", 0.0)
                proc_time = final_result.get("processing_time", 0.0)

                await _safe_send(ws, {
                    "type": "final",
                    "text": final_text,
                    "language": final_result.get("language", "unknown"),
                    "audio_duration": audio_dur,
                    "processing_time": round(proc_time, 4),
                    "real_time_factor": final_result.get("real_time_factor", 0.0),
                    "latency_ms": round(metrics.elapsed_ms(), 1),
                    "timestamp": time.time(),
                })
        else:
            await _safe_send(ws, {
                "type": "final",
                "text": "",
                "latency_ms": round(metrics.elapsed_ms(), 1),
                "timestamp": time.time(),
                "note": "No audio received",
            })

    except asyncio.CancelledError:
        logger.info("ws_transcription_task_cancelled", session_id=session_id)
        raise
    except Exception as exc:
        logger.error("ws_transcription_error", session_id=session_id, error=str(exc), exc_info=True)
        await _safe_send(ws, {"type": "error", "detail": f"Transcription error: {exc}"})


async def _transcribe_buffer(
    stt,
    audio_bytes: bytes,
    language: str | None,
    session_id: str,
) -> dict | None:
    """Write audio bytes to a temp WAV file and call engine.transcribe().

    stt.transcribe() is already async and handles its own thread-pool offload
    internally, so we simply await it directly.
    """
    import os
    import tempfile

    tmp_path = None
    try:
        # Browser MediaRecorder sends audio/webm; write as-is so ffmpeg can decode it
        with tempfile.NamedTemporaryFile(
            suffix=".webm", delete=False, prefix=f"sst_live_{session_id}_"
        ) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        result = await stt.transcribe(tmp_path, language=language)
        return result

    except Exception as exc:
        logger.warning(
            "ws_partial_transcription_failed",
            session_id=session_id,
            error=str(exc),
        )
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _send_error(ws: WebSocket, detail: str) -> None:
    """Send a JSON error frame without raising."""
    await _safe_send(ws, {"type": "error", "detail": detail})


async def _safe_send(ws: WebSocket, payload: dict) -> None:
    """Send JSON without raising if socket is already closed."""
    try:
        await ws.send_text(json.dumps(payload))
    except Exception:
        pass
