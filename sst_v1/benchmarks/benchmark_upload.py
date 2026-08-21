"""
benchmarks/benchmark_upload.py
───────────────────────────────
Benchmark utility for the file-upload transcription path.

Usage
-----
    # From the project root
    uv run python benchmarks/benchmark_upload.py \\
        --audio-dir audio_samples/ \\
        --engine whisper \\
        --model base \\
        --device cpu \\
        --output-dir benchmarks/results/

Results are written to both JSON and CSV.

Optional WER/CER
----------------
If a ``<filename>.ref.txt`` exists alongside the audio file, it is used as
the reference transcript and WER/CER are computed.  Reference files are
NEVER auto-generated; only use verified ground-truth transcripts.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Add project root to sys.path so we can import app packages directly
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.core.metrics import Timer, compute_cer, compute_rtf, compute_wer
from app.engines import get_engine


def run_benchmark(
    audio_dir: str,
    engine_name: str,
    model_name: str,
    device: str,
    output_dir: str,
) -> None:
    """Run batch benchmark over all audio files in ``audio_dir``."""
    audio_path = Path(audio_dir)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if not audio_path.exists():
        print(f"[ERROR] Audio directory not found: {audio_dir}")
        sys.exit(1)

    audio_files = list(audio_path.glob("*.wav")) + \
                  list(audio_path.glob("*.mp3")) + \
                  list(audio_path.glob("*.flac")) + \
                  list(audio_path.glob("*.m4a"))

    if not audio_files:
        print(f"[WARN] No audio files found in {audio_dir}")
        return

    print(f"\n{'='*60}")
    print(f"  SST Benchmark: {engine_name} / {model_name} / {device}")
    print(f"  Files: {len(audio_files)}  |  Output: {out_path}")
    print(f"{'='*60}\n")

    # Override model/device settings for this run
    os.environ["WHISPER_MODEL"] = model_name
    os.environ["WHISPER_DEVICE"] = device

    import importlib
    import app.core.config as _cfg
    importlib.reload(_cfg)

    engine = get_engine(engine_name)

    records = []

    for audio_file in sorted(audio_files):
        print(f"  Processing: {audio_file.name} ...", end=" ", flush=True)

        run_id = str(uuid.uuid4())[:8]
        ref_path = audio_file.with_suffix(audio_file.suffix + ".ref.txt")
        reference_transcript = None
        if ref_path.exists():
            reference_transcript = ref_path.read_text(encoding="utf-8").strip()

        record = {
            "run_id": run_id,
            "timestamp": datetime.utcnow().isoformat(),
            "engine": engine_name,
            "model": model_name,
            "device": device,
            "audio_filename": audio_file.name,
            "audio_duration": 0.0,
            "processing_time": 0.0,
            "real_time_factor": 0.0,
            "time_to_first_token_ms": None,
            "total_latency_ms": None,
            "detected_language": None,
            "reference_transcript": reference_transcript,
            "hypothesis_transcript": None,
            "wer": None,
            "cer": None,
            "error": None,
            "success": False,
        }

        try:
            import asyncio
            result = asyncio.run(engine.transcribe(str(audio_file)))

            record["audio_duration"] = result["audio_duration"]
            record["processing_time"] = result["processing_time"]
            record["real_time_factor"] = result["real_time_factor"]
            record["detected_language"] = result.get("language")
            record["hypothesis_transcript"] = result.get("text")
            record["total_latency_ms"] = result["processing_time"] * 1000
            record["success"] = True

            if reference_transcript and result.get("text"):
                record["wer"] = compute_wer(reference_transcript, result["text"])
                record["cer"] = compute_cer(reference_transcript, result["text"])

            print(f"RTF={record['real_time_factor']:.3f}  lang={record['detected_language']}")

        except Exception as exc:
            record["error"] = str(exc)
            print(f"ERROR: {exc}")

        records.append(record)

    # ── Write results ─────────────────────────────────────────────────────────
    slug = f"{engine_name}_{model_name}_{device}"
    json_out = out_path / f"{slug}.json"
    csv_out = out_path / f"{slug}.csv"

    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, default=str)

    if records:
        fieldnames = list(records[0].keys())
        with open(csv_out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)

    # ── Summary ───────────────────────────────────────────────────────────────
    successful = [r for r in records if r["success"]]
    if successful:
        avg_rtf = sum(r["real_time_factor"] for r in successful) / len(successful)
        print(f"\n{'─'*60}")
        print(f"  Completed: {len(successful)}/{len(records)} files")
        print(f"  Average RTF: {avg_rtf:.3f}")
        print(f"  Results written to: {json_out}")
        print(f"                      {csv_out}")
        print(f"{'─'*60}\n")
    else:
        print("\n[WARN] No successful transcriptions.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SST Upload Benchmark")
    parser.add_argument("--audio-dir", default="audio_samples/", help="Directory of audio files")
    parser.add_argument("--engine", default="whisper", help="Engine name")
    parser.add_argument("--model", default="base", help="Model size")
    parser.add_argument("--device", default="cpu", help="cpu | cuda | mps")
    parser.add_argument("--output-dir", default="benchmarks/results/", help="Output directory")

    args = parser.parse_args()
    run_benchmark(args.audio_dir, args.engine, args.model, args.device, args.output_dir)
