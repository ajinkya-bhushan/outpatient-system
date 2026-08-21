"""
scripts/verify_whisper.py
──────────────────────────
Step 2 verification CLI.

Runs a full audio file → WhisperEngine → transcript + metrics pipeline
and prints a human-readable report.

Usage
-----
    # Use a built-in synthetic test audio (generated on the fly):
    uv run python scripts/verify_whisper.py

    # Use your own audio file:
    uv run python scripts/verify_whisper.py --audio path/to/audio.wav

    # Override model / device:
    uv run python scripts/verify_whisper.py --model tiny --device cpu

    # Save transcript to a file:
    uv run python scripts/verify_whisper.py --audio sample.wav --output result.txt

Expected output
---------------
    ═══════════════════════════════════════════════════
     SST Step 2 Verification – WhisperEngine
    ═══════════════════════════════════════════════════
    Engine          : whisper
    Model           : base
    Device          : cpu
    Audio file      : sample.wav
    Audio duration  : 5.00 s
    Processing time : 3.12 s
    RTF             : 0.6240   ← < 1.0 = faster than real-time
    Language        : en
    ───────────────────────────────────────────────────
    Transcript:
    Hello, this is a test recording.
    ───────────────────────────────────────────────────
    Segments (2):
      [0.00s → 2.50s] Hello, this is a test recording.
    ═══════════════════════════════════════════════════
"""

from __future__ import annotations

import argparse
import asyncio
import struct
import sys
import tempfile
import wave
from pathlib import Path

# Make sure the project root is on sys.path regardless of how the script is called
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ── Synthetic test audio generator ────────────────────────────────────────────

def generate_synthetic_wav(duration_seconds: float = 3.0, sample_rate: int = 16000) -> str:
    """Generate a 440 Hz sine-wave WAV file for testing.

    Returns the path to a temporary WAV file.  Caller must delete when done.
    """
    import math

    n_samples = int(duration_seconds * sample_rate)
    freq = 440.0  # A4 tone — audible, non-silent, triggers Whisper segments

    samples = [
        int(32767 * math.sin(2 * math.pi * freq * i / sample_rate))
        for i in range(n_samples)
    ]

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False, prefix="sst_verify_")
    with wave.open(tmp.name, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{n_samples}h", *samples))

    return tmp.name


# ── Report printer ────────────────────────────────────────────────────────────

def _bar(width: int = 51) -> str:
    return "=" * width

def _thin(width: int = 51) -> str:
    return "-" * width


def print_report(result: dict, audio_file: str, output_path: str | None = None) -> None:
    """Print a human-readable transcription report to stdout."""

    rtf = result["real_time_factor"]
    rtf_note = "<-- faster than real-time (good)" if rtf < 1.0 else "<-- slower than real-time (consider smaller model or GPU)"
    dur_note = f"{result['audio_duration']:.3f} s"

    lines = [
        _bar(),
        " SST Step 2 Verification - WhisperEngine",
        _bar(),
        f"  Engine          : {result['engine']}",
        f"  Model           : {result['model']}",
        f"  Device          : {result.get('device', 'cpu')}",
        f"  Audio file      : {Path(audio_file).name}",
        f"  Audio duration  : {dur_note}",
        f"  Processing time : {result['processing_time']:.3f} s",
        f"  RTF             : {rtf:.4f}   {rtf_note}",
        f"  Language        : {result['language']}",
        _thin(),
        "  Transcript:",
        "",
        f"    {result['text'] or '(empty - silent audio produces no transcript)'}",
        "",
        _thin(),
    ]

    segments = result.get("segments", [])
    lines.append(f"  Segments ({len(segments)}):")
    if segments:
        for seg in segments:
            lines.append(f"    [{seg['start']:.2f}s → {seg['end']:.2f}s]  {seg['text']}")
    else:
        lines.append("    (none – silent or very short audio)")

    lines.append(_bar())

    report = "\n".join(lines)
    print(report)

    if output_path:
        Path(output_path).write_text(report + "\n", encoding="utf-8")
        print(f"\n  [Saved] Report saved to: {output_path}")


# ── Main async runner ─────────────────────────────────────────────────────────

async def run(
    audio_path: str,
    model_name: str,
    device: str,
    language: str | None,
    task: str,
    output: str | None,
    synthetic: bool,
) -> None:
    # Import here so the script is importable without importing the whole app
    from app.engines.whisper_engine import WhisperEngine

    # Ensure ffmpeg is on PATH (imageio-ffmpeg fallback)
    from app.core.ffmpeg_bootstrap import ensure_ffmpeg
    ensure_ffmpeg()

    print(f"\n  Loading WhisperEngine (model={model_name}, device={device}) ...")
    engine = WhisperEngine(model_name=model_name, device=device)

    print(f"  Transcribing: {Path(audio_path).name} ...\n")

    try:
        result = await engine.transcribe(
            audio_path=audio_path,
            language=language,
            task=task,
        )
    except FileNotFoundError as exc:
        print(f"\n  [ERROR] Audio file not found: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"\n  [ERROR] Transcription failed: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Attach device so the report can show it
    result["device"] = device

    print_report(result, audio_path, output)

    if synthetic:
        import os
        os.unlink(audio_path)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Step 2 Verification – WhisperEngine end-to-end test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--audio", "-a",
        default=None,
        help="Path to audio file.  If omitted, a synthetic 3s test tone is generated.",
    )
    parser.add_argument(
        "--model", "-m",
        default=None,
        help="Whisper model size (tiny|base|small|medium|large). Default: from .env / 'base'.",
    )
    parser.add_argument(
        "--device", "-d",
        default=None,
        help="Compute device: cpu | cuda | mps.  Default: from .env / 'cpu'.",
    )
    parser.add_argument(
        "--language", "-l",
        default=None,
        help="Force language code (e.g. 'en').  Default: auto-detect.",
    )
    parser.add_argument(
        "--task", "-t",
        default="transcribe",
        choices=["transcribe", "translate"],
        help="Task: transcribe or translate to English.",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Save the report to this file path.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=3.0,
        help="Duration of the synthetic test tone in seconds (default: 3).",
    )

    args = parser.parse_args()

    # Resolve model / device (args override env / settings default)
    from app.core.config import settings
    model_name = args.model or settings.WHISPER_MODEL
    device = args.device or settings.WHISPER_DEVICE

    synthetic = False
    audio_path = args.audio

    if audio_path is None:
        print(f"\n  No --audio provided.  Generating a synthetic {args.duration}s test tone ...")
        audio_path = generate_synthetic_wav(duration_seconds=args.duration)
        synthetic = True
        print(f"  Generated: {audio_path}")

    elif not Path(audio_path).exists():
        # Check audio_samples/ as a convenience prefix
        candidate = PROJECT_ROOT / "audio_samples" / audio_path
        if candidate.exists():
            audio_path = str(candidate)
        else:
            print(f"\n  [ERROR] File not found: {audio_path}")
            sys.exit(1)

    # Always resolve to absolute path so Whisper's ffmpeg subprocess finds it
    audio_path = str(Path(audio_path).resolve())

    asyncio.run(
        run(
            audio_path=audio_path,
            model_name=model_name,
            device=device,
            language=args.language,
            task=args.task,
            output=args.output,
            synthetic=synthetic,
        )
    )


if __name__ == "__main__":
    main()
