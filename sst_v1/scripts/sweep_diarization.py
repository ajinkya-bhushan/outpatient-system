"""
scripts/sweep_diarization.py
─────────────────────────────
Run the diarization + transcription pipeline over every test set (and
optionally several sub-segment window sizes) and print one comparison table.

Models are loaded once and reused across the whole sweep, so the reported RTF
excludes model load time — that matches production, where the service loads at
startup and then serves many consultations.

Usage
-----
    PYTHONPATH=. python scripts/sweep_diarization.py
    PYTHONPATH=. python scripts/sweep_diarization.py --windows 1.0,1.5,2.0
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.diarization.alignment import build_speaker_turns  # noqa: E402
from app.diarization.config import DiarizationConfig  # noqa: E402
from app.diarization.metrics import compute_der, compute_wer, word_speaker_accuracy  # noqa: E402
from app.diarization.pipeline import SpeechBrainDiarizer  # noqa: E402
from app.diarization.transcribe import WordLevelTranscriber  # noqa: E402


def load_testsets(root: Path) -> list[dict]:
    """Load every test set directory under ``root``."""
    testsets = []
    for testset_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        candidates = list(testset_dir.glob("*.json"))
        if not candidates:
            continue
        metadata = json.loads(candidates[0].read_text(encoding="utf-8"))
        metadata["_audio"] = str(testset_dir / metadata["audio_path"])
        metadata["_reference"] = [
            (turn["start"], turn["end"], turn["speaker_id"]) for turn in metadata["turns"]
        ]
        metadata["_reference_text"] = " ".join(turn["text"] for turn in metadata["turns"])
        testsets.append(metadata)
    return testsets


def evaluate(
    diarizer: SpeechBrainDiarizer,
    transcriber: WordLevelTranscriber,
    testset: dict,
    collar: float,
    oracle: bool,
) -> dict:
    """Run the full pipeline on one test set and score it."""
    audio_path = testset["_audio"]
    num_speakers = testset["num_speakers"] if oracle else None

    diarization = diarizer.diarize(audio_path, num_speakers=num_speakers)
    hypothesis = [(s.start, s.end, s.speaker) for s in diarization.segments]

    der = compute_der(
        testset["_reference"],
        hypothesis,
        collar=collar,
        audio_duration=testset["duration"],
    )

    transcription = transcriber.transcribe(audio_path)
    wer = compute_wer(testset["_reference_text"], transcription.text)

    turns = build_speaker_turns(transcription, diarization)
    accuracy = word_speaker_accuracy(
        [(word.start, word.end, turn.speaker) for turn in turns for word in turn.words],
        testset["_reference"],
        der.mapping,
    )

    return {
        "testset": testset["name"],
        "duration": testset["duration"],
        "n_turns": len(testset["turns"]),
        "true_speakers": testset["num_speakers"],
        "found_speakers": diarization.num_speakers,
        "der": der.der * 100,
        "miss": der.missed_speech * 100,
        "false_alarm": der.false_alarm * 100,
        "confusion": der.speaker_confusion * 100,
        "wer": wer["wer_percent"],
        "word_speaker_accuracy": accuracy["word_speaker_accuracy_percent"],
        "diar_rtf": diarization.real_time_factor,
        "stt_rtf": transcription.real_time_factor,
        "n_subsegments": diarization.diagnostics.get("n_subsegments"),
        "mean_cosine": diarization.diagnostics.get("mean_pairwise_cosine"),
        "oracle": oracle,
    }


HEADER = (
    f"{'test set':<14}{'dur':>6}{'turns':>6}{'spk':>5}{'found':>6}"
    f"{'DER%':>8}{'miss':>7}{'FA':>6}{'conf':>7}"
    f"{'WER%':>7}{'wordSpk%':>10}{'dRTF':>7}{'sRTF':>7}"
)


def print_table(title: str, rows: list[dict]) -> None:
    print(f"\n{title}")
    print(HEADER)
    print("─" * len(HEADER))
    for row in rows:
        print(
            f"{row['testset']:<14}{row['duration']:>6.0f}{row['n_turns']:>6}"
            f"{row['true_speakers']:>5}{row['found_speakers']:>6}"
            f"{row['der']:>8.2f}{row['miss']:>7.2f}{row['false_alarm']:>6.2f}"
            f"{row['confusion']:>7.2f}"
            f"{row['wer']:>7.2f}{row['word_speaker_accuracy']:>10.2f}"
            f"{row['diar_rtf']:>7.3f}{row['stt_rtf']:>7.3f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--testset-root", default="data/diar_testset")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--whisper-model", default="small.en")
    parser.add_argument("--whisper-backend", default="faster_whisper")
    parser.add_argument("--compute-type", default="float16")
    parser.add_argument("--collar", type=float, default=0.25)
    parser.add_argument("--windows", default="1.5",
                        help="comma-separated sub-segment window sizes to sweep")
    parser.add_argument("--output", default="benchmarks/results/diar_sweep.json")
    args = parser.parse_args()

    testsets = load_testsets(Path(args.testset_root))
    if not testsets:
        raise SystemExit(f"no test sets in {args.testset_root} — run prepare_diar_testset.py")

    transcriber = WordLevelTranscriber(
        model_name=args.whisper_model,
        device=args.device,
        backend=args.whisper_backend,
        compute_type=args.compute_type,
    )
    transcriber.load()

    all_rows: list[dict] = []

    for window_sec in [float(w) for w in args.windows.split(",")]:
        config = DiarizationConfig(device=args.device)
        config.embedding.window_sec = window_sec
        config.embedding.shift_sec = window_sec / 2
        diarizer = SpeechBrainDiarizer(config)
        diarizer.load()

        for oracle in (False, True):
            rows = [
                evaluate(diarizer, transcriber, testset, args.collar, oracle)
                for testset in testsets
            ]
            for row in rows:
                row["window_sec"] = window_sec
            all_rows.extend(rows)

            mode = "ORACLE speaker count" if oracle else "ESTIMATED speaker count"
            print_table(f"window={window_sec}s / shift={window_sec / 2}s — {mode}", rows)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(all_rows, indent=2), encoding="utf-8")
    print(f"\nSaved → {args.output}")

    print("\nLegend:")
    print("  DER%      diarization error rate = miss + false-alarm + speaker confusion")
    print("  miss      reference speech the system marked as non-speech (VAD too strict)")
    print("  FA        non-speech the system marked as speech (VAD too loose)")
    print("  conf      speech assigned to the wrong speaker (clustering error)")
    print("  wordSpk%  transcribed words given the correct speaker")
    print("  dRTF/sRTF diarization / speech-to-text real-time factor (lower is faster)")


if __name__ == "__main__":
    main()
