"""
scripts/download_model.py
──────────────────────────
One-time utility to pre-download a Whisper model before the first request.

Run this once after setting up the environment so the first API call
does not block for model download time.

Usage
-----
    uv run python scripts/download_model.py
    uv run python scripts/download_model.py --model small
    uv run python scripts/download_model.py --model large-v3 --device cuda
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Allow running from project root or scripts/
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings


def download(model_name: str, device: str) -> None:
    print(f"\n  Downloading Whisper model: '{model_name}'  device={device}")
    print("  (Models are cached in ~/.cache/whisper after the first download)\n")

    try:
        import whisper
    except ImportError:
        print("[ERROR] openai-whisper is not installed. Run: uv sync")
        sys.exit(1)

    start = time.perf_counter()
    model = whisper.load_model(model_name, device=device)
    elapsed = time.perf_counter() - start

    print(f"\n  ✅ Model '{model_name}' ready in {elapsed:.1f}s")
    print(f"     Parameters: {sum(p.numel() for p in model.parameters()):,}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download a Whisper model")
    parser.add_argument(
        "--model",
        default=settings.WHISPER_MODEL,
        help=f"Model size (default: {settings.WHISPER_MODEL})",
    )
    parser.add_argument(
        "--device",
        default=settings.WHISPER_DEVICE,
        help=f"Device (default: {settings.WHISPER_DEVICE})",
    )
    args = parser.parse_args()
    download(args.model, args.device)
