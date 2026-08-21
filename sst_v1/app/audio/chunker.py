"""
app/audio/chunker.py
─────────────────────
Streaming audio chunker for the live WebSocket transcription path.

The chunker sits between the WebSocket receiver (which delivers raw bytes
from the browser microphone) and the STT engine's ``stream_transcribe``
method.

Responsibilities
----------------
1. **Buffering** – accumulate incoming bytes until a minimum chunk size is
   reached (prevents spinning the model on tiny frames).
2. **Yielding** – emit audio frames as async generators so callers can
   ``async for chunk in chunker.chunks():``.
3. **Silence detection** – optionally skip silent frames to reduce compute
   (placeholder for Phase 4 enhancement).
4. **Session tracking** – maintain per-connection state (byte count, chunk
   count, elapsed time) for latency reporting.

AudioChunker is NOT tied to any specific audio format; it operates at the
raw bytes level.  Format interpretation (sample rate, bit depth) is the
engine's responsibility.
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from app.core.logging import get_logger

logger = get_logger(__name__)

# Default minimum bytes before yielding a chunk to the engine
# 16 kHz × 2 bytes/sample × 1 channel × 0.5 s = 16 000 bytes
DEFAULT_CHUNK_SIZE_BYTES = 16_000


class AudioChunker:
    """Buffer and re-chunk raw audio bytes from a WebSocket stream.

    Usage::

        chunker = AudioChunker(chunk_size=16_000)
        await chunker.feed(raw_bytes)
        ...
        await chunker.close()

        async for chunk in chunker.chunks():
            await engine.process(chunk)

    Or use the convenience async-generator form::

        async for chunk in AudioChunker.from_websocket(ws):
            ...
    """

    def __init__(self, chunk_size: int = DEFAULT_CHUNK_SIZE_BYTES) -> None:
        self.chunk_size = chunk_size
        self._buffer = bytearray()
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._closed = False
        self.total_bytes = 0
        self.chunk_count = 0

    # ── Feed interface ─────────────────────────────────────────────────────────

    async def feed(self, data: bytes) -> None:
        """Ingest raw audio bytes from the WebSocket.

        Args:
            data: Raw audio bytes (any length).
        """
        if self._closed:
            raise RuntimeError("Cannot feed a closed AudioChunker")

        self._buffer.extend(data)
        self.total_bytes += len(data)

        # Emit complete chunks
        while len(self._buffer) >= self.chunk_size:
            chunk = bytes(self._buffer[: self.chunk_size])
            del self._buffer[: self.chunk_size]
            self.chunk_count += 1
            await self._queue.put(chunk)
            logger.debug("chunk_emitted", chunk_index=self.chunk_count, size=len(chunk))

    async def close(self) -> None:
        """Signal end-of-stream.

        Flushes any remaining bytes as a final (possibly short) chunk,
        then puts a ``None`` sentinel into the queue.
        """
        if self._buffer:
            chunk = bytes(self._buffer)
            self._buffer.clear()
            self.chunk_count += 1
            await self._queue.put(chunk)
            logger.debug("final_chunk_emitted", size=len(chunk))

        await self._queue.put(None)  # sentinel
        self._closed = True
        logger.info(
            "chunker_closed",
            total_bytes=self.total_bytes,
            total_chunks=self.chunk_count,
        )

    # ── Async generator interface ──────────────────────────────────────────────

    async def chunks(self) -> AsyncGenerator[bytes, None]:
        """Yield audio chunks as they become available.

        Yields:
            Raw bytes chunks of approximately ``chunk_size`` bytes.
            The final chunk may be shorter.
        """
        while True:
            chunk = await self._queue.get()
            if chunk is None:
                break
            yield chunk

    # ── Convenience factory ───────────────────────────────────────────────────

    @staticmethod
    async def from_websocket(
        ws,
        chunk_size: int = DEFAULT_CHUNK_SIZE_BYTES,
    ) -> AsyncGenerator[bytes, None]:
        """Read raw bytes from a FastAPI WebSocket and yield audio chunks.

        Handles WebSocket disconnect cleanly.

        Args:
            ws:         A connected ``fastapi.WebSocket`` instance.
            chunk_size: Minimum chunk size in bytes.

        Yields:
            Audio byte chunks.
        """
        from fastapi import WebSocketDisconnect

        chunker = AudioChunker(chunk_size=chunk_size)

        async def _receiver():
            try:
                while True:
                    data = await ws.receive_bytes()
                    await chunker.feed(data)
            except WebSocketDisconnect:
                pass
            finally:
                await chunker.close()

        # Run receiver concurrently with chunk consumption
        receiver_task = asyncio.create_task(_receiver())

        async for chunk in chunker.chunks():
            yield chunk

        await receiver_task  # ensure receiver is fully done
