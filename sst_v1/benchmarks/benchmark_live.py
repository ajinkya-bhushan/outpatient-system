"""
benchmarks/benchmark_live.py
─────────────────────────────
Benchmark utility for the live / streaming transcription path.

Simulates a real-time audio stream by feeding a pre-existing audio file
chunk by chunk into the engine's ``stream_transcribe`` method.

Measures:
* Time-to-first-token (TTFT) in milliseconds
* Total latency
* RTF over the full file

Usage
-----
    uv run python benchmarks/benchmark_live.py \\
        --audio audio_samples/sample.wav \\
        --engine whisper \\
        --chunk-ms 500 \\
        --output-dir benchmarks/results/
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.audio.validator import get_audio_duration
from app.engines import get_engine


async def _simulate_stream(audio_path: str, chunk_ms: int):
    """Yield audio file content in ``chunk_ms``-millisecond chunks.

    Simulates real-time streaming by reading the file in fixed-size chunks
    sized for ``chunk_ms`` at 16 kHz mono 16-bit PCM.
    """
    bytes_per_ms = 16000 * 2 // 1000  # 16 kHz, 2 bytes/sample, /1000 ms
    chunk_size = bytes_per_ms * chunk_ms

    with open(audio_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk
            await asyncio.sleep(chunk_ms / 1000)  # simulate real-time pacing


async def run_live_benchmark(
    audio_file: str,
    engine_name: str,
    chunk_ms: int,
    output_dir: str,
) -> None:
    audio_path = Path(audio_file)
    if not audio_path.exists():
        print(f"[ERROR] File not found: {audio_file}")
        sys.exit(1)

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  Live Benchmark: {engine_name}  chunk={chunk_ms}ms")
    print(f"  File: {audio_path.name}")
    print(f"{'='*60}\n")

    audio_duration = get_audio_duration(str(audio_path))
    engine = get_engine(engine_name)

    partials = []
    ttft_ms = None
    start = time.perf_counter()

    async for partial in engine.stream_transcribe(
        audio_chunks=_simulate_stream(str(audio_path), chunk_ms)
    ):
        elapsed_ms = (time.perf_counter() - start) * 1000
        if ttft_ms is None and partial.get("text"):
            ttft_ms = elapsed_ms
        partials.append({"text": partial.get("text", ""), "is_final": partial.get("is_final", False), "latency_ms": elapsed_ms})
        print(f"  [{elapsed_ms:.0f}ms] {'FINAL' if partial.get('is_final') else 'partial'}: {partial.get('text', '')[:60]}")

    total_latency_ms = (time.perf_counter() - start) * 1000
    final_text = next((p["text"] for p in reversed(partials) if p["is_final"]), partials[-1]["text"] if partials else "")

    run_id = str(uuid.uuid4())[:8]
    record = {
        "run_id": run_id,
        "timestamp": datetime.utcnow().isoformat(),
        "engine": engine_name,
        "audio_filename": audio_path.name,
        "audio_duration": audio_duration,
        "chunk_ms": chunk_ms,
        "time_to_first_token_ms": round(ttft_ms, 1) if ttft_ms else None,
        "total_latency_ms": round(total_latency_ms, 1),
        "real_time_factor": round(total_latency_ms / 1000 / audio_duration, 4) if audio_duration > 0 else 0.0,
        "partial_count": len(partials),
        "final_transcript": final_text,
    }

    slug = f"live_{engine_name}_{audio_path.stem}"
    json_out = out_path / f"{slug}.json"
    csv_out = out_path / f"{slug}.csv"

    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, default=str)

    with open(csv_out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(record.keys()))
        writer.writeheader()
        writer.writerow(record)

    print(f"\n  TTFT:          {record['time_to_first_token_ms']} ms")
    print(f"  Total latency: {record['total_latency_ms']} ms")
    print(f"  RTF:           {record['real_time_factor']}")
    print(f"  Results:       {json_out}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SST Live Benchmark")
    parser.add_argument("--audio", required=True, help="Path to audio file")
    parser.add_argument("--engine", default="whisper", help="Engine name")
    parser.add_argument("--chunk-ms", type=int, default=500, help="Chunk size in milliseconds")
    parser.add_argument("--output-dir", default="benchmarks/results/", help="Output directory")
    args = parser.parse_args()

    asyncio.run(run_live_benchmark(args.audio, args.engine, args.chunk_ms, args.output_dir))
