"""
scripts/test_websocket.py
──────────────────────────
Manual WebSocket test client for the /api/v1/live endpoint.

Usage
-----
  # Requires the FastAPI backend to be running:
  # Terminal 1: uv run uvicorn app.main:app --reload --port 8000
  #
  # Terminal 2: uv run python scripts/test_websocket.py

  # With a real audio file:
  uv run python scripts/test_websocket.py --audio audio_samples/test_speech_3s.wav

  # With a generated tone (no audio file needed):
  uv run python scripts/test_websocket.py --duration 3

  # Target a different backend:
  uv run python scripts/test_websocket.py --url ws://localhost:8000/api/v1/live

Expected output
---------------
  [WS] Connecting to ws://localhost:8000/api/v1/live ...
  [WS] Connected. Session: abc12345
  [WS] Sending 6 audio chunks (3.0s total) ...
  [PARTIAL] (chunk 2) latency=2341ms | "Hello this is a test"
  [FINAL]   latency=4123ms | audio=3.00s | RTF=1.374 | "Hello this is a test."
  [METRICS] TTFT=2341ms | total=4500ms | partials=1 | audio_est=3.00s
  [WS] Session closed cleanly.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import struct
import sys
import time
import wave
from pathlib import Path

try:
    import websockets
except ImportError:
    print("[ERROR] websockets not installed. Run: uv add websockets --dev")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _generate_tone(duration_s: float = 3.0, sample_rate: int = 16000) -> bytes:
    """Generate a 440Hz sine WAV in memory."""
    import io
    n = int(duration_s * sample_rate)
    samples = [int(32767 * 0.5 * math.sin(2 * math.pi * 440 * i / sample_rate)) for i in range(n)]
    buf = io.BytesIO()
    with wave.open(buf, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{n}h", *samples))
    return buf.getvalue()


async def run_test(url: str, audio_bytes: bytes, engine: str, language: str, chunk_size: int) -> None:
    print(f"\n[WS] Connecting to {url} ...")

    start_time = time.perf_counter()
    first_partial_ms: float | None = None

    try:
        async with websockets.connect(url) as ws:
            print("[WS] Connected.")

            # 1. Start
            await ws.send(json.dumps({"type": "start", "engine": engine, "language": language or ""}))
            resp = json.loads(await ws.recv())
            if resp.get("type") != "session_started":
                print(f"[ERROR] Expected session_started, got: {resp}")
                return
            session_id = resp.get("session_id", "?")
            print(f"[WS] Session started: {session_id}  (engine={engine})")

            # 2. Stream audio in chunks
            chunks = [audio_bytes[i:i+chunk_size] for i in range(0, len(audio_bytes), chunk_size)]
            print(f"[WS] Sending {len(chunks)} audio chunks ({len(audio_bytes)/1024:.1f} KB total) ...")

            async def _sender():
                for i, chunk in enumerate(chunks):
                    await ws.send(chunk)
                    await asyncio.sleep(0.05)  # simulate real-time pacing
                await ws.send(json.dumps({"type": "stop"}))

            # Receive loop
            send_task = asyncio.create_task(_sender())

            async for raw_msg in ws:
                msg = json.loads(raw_msg)
                t_ms = (time.perf_counter() - start_time) * 1000

                if msg["type"] == "partial":
                    if first_partial_ms is None:
                        first_partial_ms = t_ms
                    text = msg.get("text", "")
                    lat = msg.get("latency_ms", 0)
                    print(f"  [PARTIAL] latency={lat:.0f}ms | \"{text}\"")

                elif msg["type"] == "final":
                    text = msg.get("text", "")
                    lat = msg.get("latency_ms", 0)
                    audio_dur = msg.get("audio_duration", 0)
                    rtf = msg.get("real_time_factor", 0)
                    print(f"  [FINAL]   latency={lat:.0f}ms | audio={audio_dur:.2f}s | RTF={rtf:.4f}")
                    print(f"            \"{text}\"")

                elif msg["type"] == "session_ended":
                    m = msg.get("metrics", {})
                    ttft = m.get("time_to_first_token_ms")
                    total = m.get("total_session_ms", 0)
                    partials = m.get("partial_results_sent", 0)
                    audio_est = m.get("estimated_audio_duration_s", 0)
                    print(
                        f"\n  [METRICS] TTFT={ttft}ms | total={total:.0f}ms | "
                        f"partials={partials} | audio_est={audio_est:.2f}s"
                    )
                    break

                elif msg["type"] == "error":
                    print(f"  [ERROR] {msg.get('detail', '?')}")
                    break

            await send_task
            print("\n[WS] Session closed cleanly.")

    except ConnectionRefusedError:
        print(f"\n[ERROR] Cannot connect to {url}. Is the backend running?")
        print("        Start it with: uv run uvicorn app.main:app --reload --port 8000")
    except Exception as exc:
        print(f"\n[ERROR] {exc}")
        import traceback
        traceback.print_exc()


def main() -> None:
    parser = argparse.ArgumentParser(description="WebSocket live transcription test client")
    parser.add_argument("--url", default="ws://localhost:8000/api/v1/live")
    parser.add_argument("--audio", default=None, help="Audio file to stream")
    parser.add_argument("--duration", type=float, default=3.0, help="Synthetic tone duration (s)")
    parser.add_argument("--engine", default="whisper", choices=["whisper", "whisperflow"])
    parser.add_argument("--language", default="", help="Force language code (e.g. en)")
    parser.add_argument("--chunk-size", type=int, default=8192, help="Audio bytes per WebSocket frame")
    args = parser.parse_args()

    if args.audio:
        audio_path = Path(args.audio)
        if not audio_path.exists():
            audio_path = PROJECT_ROOT / "audio_samples" / args.audio
        if not audio_path.exists():
            print(f"[ERROR] Audio file not found: {args.audio}")
            sys.exit(1)
        audio_bytes = audio_path.read_bytes()
        print(f"[INFO] Using audio file: {audio_path.name}  ({len(audio_bytes)/1024:.1f} KB)")
    else:
        print(f"[INFO] Generating {args.duration}s test tone ...")
        audio_bytes = _generate_tone(args.duration)
        print(f"[INFO] Generated {len(audio_bytes)/1024:.1f} KB of audio")

    asyncio.run(run_test(
        url=args.url,
        audio_bytes=audio_bytes,
        engine=args.engine,
        language=args.language,
        chunk_size=args.chunk_size,
    ))


if __name__ == "__main__":
    main()
