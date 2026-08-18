"""
scripts/benchmark.py
─────────────────────
Unified benchmark entry point – delegates to benchmark_upload or benchmark_live.

Usage
-----
    # Upload benchmark (all files in audio_samples/)
    uv run python scripts/benchmark.py upload \\
        --audio-dir audio_samples/ \\
        --engine whisper --model base --device cpu

    # Live benchmark (single file)
    uv run python scripts/benchmark.py live \\
        --audio audio_samples/sample.wav \\
        --engine whisper --chunk-ms 500
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    parser = argparse.ArgumentParser(description="SST Benchmark Runner")
    sub = parser.add_subparsers(dest="mode", required=True)

    # ── upload ─────────────────────────────────────────────────────────────
    upload_p = sub.add_parser("upload", help="Benchmark file-upload transcription")
    upload_p.add_argument("--audio-dir", default="audio_samples/")
    upload_p.add_argument("--engine", default="whisper")
    upload_p.add_argument("--model", default="base")
    upload_p.add_argument("--device", default="cpu")
    upload_p.add_argument("--output-dir", default="benchmarks/results/")

    # ── live ───────────────────────────────────────────────────────────────
    live_p = sub.add_parser("live", help="Benchmark streaming / live transcription")
    live_p.add_argument("--audio", required=True)
    live_p.add_argument("--engine", default="whisper")
    live_p.add_argument("--chunk-ms", type=int, default=500)
    live_p.add_argument("--output-dir", default="benchmarks/results/")

    args = parser.parse_args()

    if args.mode == "upload":
        from benchmarks.benchmark_upload import run_benchmark
        run_benchmark(args.audio_dir, args.engine, args.model, args.device, args.output_dir)

    elif args.mode == "live":
        import asyncio
        from benchmarks.benchmark_live import run_live_benchmark
        asyncio.run(run_live_benchmark(args.audio, args.engine, args.chunk_ms, args.output_dir))


if __name__ == "__main__":
    main()
