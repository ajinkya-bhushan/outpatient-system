"""
scripts/generate_test_audio.py
───────────────────────────────
Generate a sample WAV file in audio_samples/ for local testing.

Creates two files:
  audio_samples/test_tone_3s.wav   – 3-second 440 Hz sine tone (triggers Whisper)
  audio_samples/test_silence_1s.wav – 1-second silence (tests edge-case handling)

Usage
-----
    uv run python scripts/generate_test_audio.py

The generated files are excluded from git via .gitignore (audio_samples/*).
"""

from __future__ import annotations

import math
import struct
import sys
import wave
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUDIO_DIR = PROJECT_ROOT / "audio_samples"


def write_wav(
    path: Path,
    samples: list[int],
    sample_rate: int = 16000,
    n_channels: int = 1,
    sampwidth: int = 2,
) -> None:
    """Write a list of 16-bit PCM samples to a WAV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    print(f"  [OK] Written: {path}  ({len(samples) / sample_rate:.1f}s, {path.stat().st_size} bytes)")


def generate_sine(freq: float, duration: float, sample_rate: int = 16000, amplitude: float = 0.8) -> list[int]:
    """Return 16-bit PCM samples for a sine wave."""
    n = int(duration * sample_rate)
    peak = int(32767 * amplitude)
    return [int(peak * math.sin(2 * math.pi * freq * i / sample_rate)) for i in range(n)]


def generate_silence(duration: float, sample_rate: int = 16000) -> list[int]:
    """Return silent (zero) PCM samples."""
    return [0] * int(duration * sample_rate)


def generate_speech_simulation(duration: float = 3.0, sample_rate: int = 16000) -> list[int]:
    """
    Simulate a speech-like waveform using multiple sine tones at human-voice
    frequencies (fundamental + harmonics).  Not real speech, but close enough
    to trigger Whisper to produce segments rather than treating it as silence.
    """
    n = int(duration * sample_rate)
    samples = []
    for i in range(n):
        t = i / sample_rate
        # Fundamental (150 Hz) + harmonics (300, 450, 600 Hz) - vowel-like
        val = (
            0.4 * math.sin(2 * math.pi * 150 * t)
            + 0.25 * math.sin(2 * math.pi * 300 * t)
            + 0.15 * math.sin(2 * math.pi * 450 * t)
            + 0.10 * math.sin(2 * math.pi * 600 * t)
        )
        # Amplitude envelope: fade in/out to reduce click artefacts
        fade = min(t / 0.05, 1.0, (duration - t) / 0.05)
        samples.append(int(32767 * val * fade))
    return samples


def main() -> None:
    print(f"\n  Generating test audio files in: {AUDIO_DIR}\n")

    # 1. 3-second 440 Hz tone
    write_wav(
        AUDIO_DIR / "test_tone_3s.wav",
        generate_sine(freq=440.0, duration=3.0),
    )

    # 2. 3-second speech-simulation (voice-frequency harmonics)
    write_wav(
        AUDIO_DIR / "test_speech_3s.wav",
        generate_speech_simulation(duration=3.0),
    )

    # 3. 1-second silence (edge-case: audio_duration fallback path)
    write_wav(
        AUDIO_DIR / "test_silence_1s.wav",
        generate_silence(duration=1.0),
    )

    print(
        "\n  Usage:\n"
        "    uv run python scripts/verify_whisper.py --audio audio_samples/test_tone_3s.wav\n"
        "    uv run python scripts/verify_whisper.py --audio audio_samples/test_speech_3s.wav\n"
        "    uv run python scripts/verify_whisper.py --audio audio_samples/test_silence_1s.wav\n"
    )


if __name__ == "__main__":
    main()
