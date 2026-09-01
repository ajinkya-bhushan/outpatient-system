"""
scripts/prepare_diar_testset.py
────────────────────────────────
Build a multi-speaker test recording with exact ground truth, so diarization
and transcription accuracy can be *measured* rather than eyeballed.

Source material is mini-LibriSpeech (``dev-clean-2``): real human voices with
verified transcripts and one speaker per file. Alternating whole utterances
from different speakers gives a synthetic two-party conversation whose speaker
timeline and reference text are both known exactly.

    curl -LO https://www.openslr.org/resources/31/dev-clean-2.tar.gz
    tar xzf dev-clean-2.tar.gz -C data/

Each utterance is silence-trimmed before placement, so the RTTM boundaries mark
actual speech rather than LibriSpeech's leading/trailing padding — otherwise a
correct VAD gets penalised as "missed speech".

What this is and is not
-----------------------
Turn-taking is clean: no overlapping speech, no interruptions, no crosstalk,
and read prose rather than clinical dialogue. It measures the pipeline's
speaker-discrimination and alignment mechanics, and is a deliberate optimistic
bound on real consultation-room audio.

Usage
-----
    python scripts/prepare_diar_testset.py --name two_party --turns 8
    python scripts/prepare_diar_testset.py --name short_turns --turns 14 \
        --min-utt-sec 1.5 --max-utt-sec 4.0
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

SAMPLE_RATE = 16_000
DEFAULT_ROLES = ["Doctor", "Patient", "Nurse", "Caregiver"]


@dataclass
class Turn:
    """One utterance placed on the conversation timeline."""

    index: int
    speaker_id: str
    role: str
    start: float
    end: float
    text: str
    source_file: str


def find_utterances(
    speaker_dir: Path,
    min_sec: float,
    max_sec: float,
) -> list[tuple[Path, str, float]]:
    """Return ``(flac_path, transcript, duration)`` for one LibriSpeech speaker."""
    utterances: list[tuple[Path, str, float]] = []

    for transcript_file in sorted(speaker_dir.rglob("*.trans.txt")):
        transcripts = {}
        for line in transcript_file.read_text(encoding="utf-8").splitlines():
            utterance_id, _, text = line.partition(" ")
            transcripts[utterance_id] = text.strip()

        for flac_path in sorted(transcript_file.parent.glob("*.flac")):
            text = transcripts.get(flac_path.stem)
            if not text:
                continue
            duration = sf.info(str(flac_path)).duration
            if min_sec <= duration <= max_sec:
                utterances.append((flac_path, text, duration))

    return utterances


def load_trimmed(flac_path: Path, top_db: float = 30.0) -> np.ndarray:
    """Load a utterance at 16 kHz mono with leading/trailing silence removed."""
    audio, _ = librosa.load(str(flac_path), sr=SAMPLE_RATE, mono=True)
    trimmed, _ = librosa.effects.trim(audio, top_db=top_db)
    return trimmed.astype(np.float32)


def build_conversation(
    librispeech_dir: Path,
    n_speakers: int,
    n_turns: int,
    min_utt_sec: float,
    max_utt_sec: float,
    gap_range: tuple[float, float],
    lead_in_sec: float,
    seed: int,
    speaker_ids: list[str] | None,
) -> tuple[np.ndarray, list[Turn]]:
    """Assemble an alternating-turn conversation and its ground-truth timeline."""
    rng = random.Random(seed)

    available = sorted(
        [d for d in librispeech_dir.iterdir() if d.is_dir()],
        key=lambda d: d.name,
    )
    if not available:
        raise SystemExit(f"no speaker directories under {librispeech_dir}")

    if speaker_ids:
        chosen_dirs = [librispeech_dir / speaker_id for speaker_id in speaker_ids]
        missing = [str(d) for d in chosen_dirs if not d.is_dir()]
        if missing:
            raise SystemExit(f"speaker directories not found: {missing}")
    else:
        chosen_dirs = rng.sample(available, min(n_speakers, len(available)))

    pools: dict[str, list[tuple[Path, str, float]]] = {}
    for speaker_dir in chosen_dirs:
        pool = find_utterances(speaker_dir, min_utt_sec, max_utt_sec)
        if not pool:
            raise SystemExit(
                f"speaker {speaker_dir.name} has no utterances in "
                f"[{min_utt_sec}, {max_utt_sec}]s — widen the range"
            )
        rng.shuffle(pool)
        pools[speaker_dir.name] = pool

    speaker_order = [d.name for d in chosen_dirs]
    roles = {
        speaker_id: DEFAULT_ROLES[i % len(DEFAULT_ROLES)]
        for i, speaker_id in enumerate(speaker_order)
    }

    chunks: list[np.ndarray] = [np.zeros(int(lead_in_sec * SAMPLE_RATE), dtype=np.float32)]
    turns: list[Turn] = []
    cursor = lead_in_sec

    for turn_index in range(n_turns):
        speaker_id = speaker_order[turn_index % len(speaker_order)]
        pool = pools[speaker_id]
        if not pool:
            print(
                f"WARNING: speaker {speaker_id} ran out of utterances in "
                f"[{min_utt_sec}, {max_utt_sec}]s after {turn_index} turns. "
                f"Requested {n_turns}. Pick a speaker with more files or widen "
                f"the duration range."
            )
            break

        flac_path, text, _ = pool.pop()
        audio = load_trimmed(flac_path)
        # Peak-normalise so no single voice dominates purely by recording level.
        peak = float(np.abs(audio).max())
        if peak > 0:
            audio = audio * (0.7 / peak)

        duration = len(audio) / SAMPLE_RATE
        turns.append(
            Turn(
                index=turn_index,
                speaker_id=speaker_id,
                role=roles[speaker_id],
                start=round(cursor, 3),
                end=round(cursor + duration, 3),
                text=text,
                source_file=str(flac_path.relative_to(librispeech_dir)),
            )
        )
        chunks.append(audio)
        cursor += duration

        if turn_index < n_turns - 1:
            gap = rng.uniform(*gap_range)
            chunks.append(np.zeros(int(gap * SAMPLE_RATE), dtype=np.float32))
            cursor += gap

    # Trailing silence, so the final turn is not clipped by the file boundary.
    chunks.append(np.zeros(int(0.5 * SAMPLE_RATE), dtype=np.float32))
    return np.concatenate(chunks), turns


def write_outputs(out_dir: Path, name: str, audio: np.ndarray, turns: list[Turn]) -> None:
    """Write audio, RTTM ground truth, JSON metadata and a readable transcript."""
    out_dir.mkdir(parents=True, exist_ok=True)

    audio_path = out_dir / f"{name}.wav"
    sf.write(str(audio_path), audio, SAMPLE_RATE, subtype="PCM_16")

    # RTTM: SPEAKER <rec> 1 <start> <dur> <NA> <NA> <spk> <NA> <NA>
    rttm_lines = [
        f"SPEAKER {name} 1 {turn.start:.3f} {turn.end - turn.start:.3f} "
        f"<NA> <NA> {turn.speaker_id} <NA> <NA>"
        for turn in turns
    ]
    (out_dir / f"{name}.rttm").write_text("\n".join(rttm_lines) + "\n", encoding="utf-8")

    speakers = sorted({turn.speaker_id for turn in turns})
    metadata = {
        "name": name,
        "sample_rate": SAMPLE_RATE,
        "audio_path": audio_path.name,
        "duration": round(len(audio) / SAMPLE_RATE, 3),
        "speech_duration": round(sum(turn.end - turn.start for turn in turns), 3),
        "num_speakers": len(speakers),
        "speakers": speakers,
        "roles": {turn.speaker_id: turn.role for turn in turns},
        "turns": [asdict(turn) for turn in turns],
    }
    (out_dir / f"{name}.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    # Reference transcript: full text for WER, plus a labelled version.
    (out_dir / f"{name}.ref.txt").write_text(
        " ".join(turn.text for turn in turns) + "\n", encoding="utf-8"
    )
    (out_dir / f"{name}.labelled.txt").write_text(
        "\n".join(
            f"[{turn.start:7.2f} - {turn.end:7.2f}] {turn.role} ({turn.speaker_id}): {turn.text}"
            for turn in turns
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"\nWrote test set '{name}' to {out_dir}")
    print(f"  audio      : {audio_path.name}  ({metadata['duration']}s)")
    print(f"  speakers   : {len(speakers)} {speakers}")
    print(f"  turns      : {len(turns)}")
    print(f"  speech     : {metadata['speech_duration']}s "
          f"({100 * metadata['speech_duration'] / metadata['duration']:.1f}% of audio)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--librispeech-dir", default="data/LibriSpeech/dev-clean-2")
    parser.add_argument("--out-dir", default="data/diar_testset")
    parser.add_argument("--name", default="two_party")
    parser.add_argument("--speakers", type=int, default=2, help="number of distinct speakers")
    parser.add_argument("--speaker-ids", default=None, help="comma-separated LibriSpeech speaker IDs")
    parser.add_argument("--turns", type=int, default=8)
    parser.add_argument("--min-utt-sec", type=float, default=3.0)
    parser.add_argument("--max-utt-sec", type=float, default=9.0)
    parser.add_argument("--min-gap-sec", type=float, default=0.3)
    parser.add_argument("--max-gap-sec", type=float, default=0.8)
    parser.add_argument("--lead-in-sec", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    librispeech_dir = Path(args.librispeech_dir)
    if not librispeech_dir.is_dir():
        raise SystemExit(
            f"{librispeech_dir} not found. Download mini-LibriSpeech first:\n"
            "  curl -LO https://www.openslr.org/resources/31/dev-clean-2.tar.gz\n"
            "  tar xzf dev-clean-2.tar.gz -C data/"
        )

    speaker_ids = args.speaker_ids.split(",") if args.speaker_ids else None

    audio, turns = build_conversation(
        librispeech_dir=librispeech_dir,
        n_speakers=args.speakers,
        n_turns=args.turns,
        min_utt_sec=args.min_utt_sec,
        max_utt_sec=args.max_utt_sec,
        gap_range=(args.min_gap_sec, args.max_gap_sec),
        lead_in_sec=args.lead_in_sec,
        seed=args.seed,
        speaker_ids=speaker_ids,
    )
    write_outputs(Path(args.out_dir) / args.name, args.name, audio, turns)


if __name__ == "__main__":
    main()
