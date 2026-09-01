"""
scripts/test_speechbrain_diarization.py
────────────────────────────────────────
End-to-end test of the SpeechBrain diarization + Whisper transcription
pipeline against a ground-truth test set from ``prepare_diar_testset.py``.

Reports:

* **DER** – diarization error rate, split into missed speech / false alarm /
  speaker confusion, so a regression can be traced to the responsible stage
  (VAD tuning vs. clustering).
* **Speaker count** – estimated vs. true, both with and without an oracle
  count, since a live consultation does not know the count in advance.
* **WER** – Whisper accuracy on the same audio, as a transcription baseline.
* **Word-speaker accuracy** – share of transcribed words attributed to the
  right speaker. This is the number a clinician would notice.
* **RTF** – processing time / audio duration per stage, to judge whether the
  offline pass is viable at the end of a consultation.

Usage
-----
    PYTHONPATH=. python scripts/test_speechbrain_diarization.py \
        --testset data/diar_testset/two_party \
        --whisper-model small.en
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.diarization.alignment import build_speaker_turns, format_transcript  # noqa: E402
from app.diarization.config import DiarizationConfig  # noqa: E402
from app.diarization.metrics import (  # noqa: E402
    compute_der,
    compute_wer,
    word_speaker_accuracy,
)
from app.diarization.pipeline import SpeechBrainDiarizer  # noqa: E402
from app.diarization.transcribe import WordLevelTranscriber  # noqa: E402


def load_testset(testset_dir: Path) -> dict:
    """Read the metadata JSON produced by ``prepare_diar_testset.py``."""
    candidates = list(testset_dir.glob("*.json"))
    if not candidates:
        raise SystemExit(f"no test-set JSON found in {testset_dir}")

    metadata = json.loads(candidates[0].read_text(encoding="utf-8"))
    metadata["_dir"] = testset_dir
    metadata["_audio"] = testset_dir / metadata["audio_path"]
    metadata["_reference_segments"] = [
        (turn["start"], turn["end"], turn["speaker_id"]) for turn in metadata["turns"]
    ]
    metadata["_reference_text"] = " ".join(turn["text"] for turn in metadata["turns"])
    return metadata


def banner(title: str) -> None:
    print(f"\n{'─' * 78}\n{title}\n{'─' * 78}")


def run(args: argparse.Namespace) -> dict:
    metadata = load_testset(Path(args.testset))
    audio_path = str(metadata["_audio"])
    reference = metadata["_reference_segments"]
    true_speakers = metadata["num_speakers"]

    banner(f"TEST SET: {metadata['name']}")
    print(f"  audio            : {audio_path}")
    print(f"  duration         : {metadata['duration']}s "
          f"(speech {metadata['speech_duration']}s)")
    print(f"  true speakers    : {true_speakers} {metadata['speakers']}")
    print(f"  turns            : {len(metadata['turns'])}")

    config = DiarizationConfig(device=args.device)
    config.embedding.window_sec = args.window_sec
    config.embedding.shift_sec = args.shift_sec
    config.clustering.max_speakers = args.max_speakers
    if args.pval is not None:
        config.clustering.pval = args.pval

    banner("STAGE 1-3: SpeechBrain diarization")
    diarizer = SpeechBrainDiarizer(config)

    # Estimated speaker count: the realistic live case.
    estimated = diarizer.diarize(audio_path, num_speakers=None)
    # Oracle speaker count: isolates clustering quality from count estimation.
    oracle = diarizer.diarize(audio_path, num_speakers=true_speakers)

    results: dict = {"testset": metadata["name"], "config": {
        "window_sec": args.window_sec,
        "shift_sec": args.shift_sec,
        "pval": args.pval,
        "device": args.device,
    }}

    for label, diarization in (("estimated_speakers", estimated), ("oracle_speakers", oracle)):
        hypothesis = [(s.start, s.end, s.speaker) for s in diarization.segments]
        der = compute_der(
            reference,
            hypothesis,
            collar=args.collar,
            audio_duration=metadata["duration"],
        )
        results[label] = {
            "diarization": diarization.to_dict(),
            "der": der.to_dict(),
        }
        print(f"\n  [{label}]")
        print(f"    speakers found : {diarization.num_speakers} (true {true_speakers})")
        print(f"    segments       : {len(diarization.segments)}")
        print(f"    DER            : {der.der * 100:6.2f}%"
              f"   (miss {der.missed_speech * 100:.2f}%"
              f" / FA {der.false_alarm * 100:.2f}%"
              f" / confusion {der.speaker_confusion * 100:.2f}%)")
        print(f"    RTF            : {diarization.real_time_factor:.3f}"
              f"   stages={diarization.stage_times}")
        print(f"    diagnostics    : {diarization.diagnostics}")

    banner("STAGE 4: Whisper transcription (word-level timestamps)")
    transcriber = WordLevelTranscriber(
        model_name=args.whisper_model,
        device=args.device,
        backend=args.whisper_backend,
        compute_type=args.compute_type,
        language=args.language,
    )
    transcription = transcriber.transcribe(audio_path)
    print(f"  backend          : {transcription.backend}")
    print(f"  model            : {transcription.model}")
    print(f"  words            : {len(transcription.words)}")
    print(f"  RTF              : {transcription.real_time_factor:.3f}")

    wer = compute_wer(metadata["_reference_text"], transcription.text)
    print(f"  WER              : {wer['wer_percent']:6.2f}%   CER {wer['cer_percent']:.2f}%")
    print(f"                     (sub {wer['substitutions']}"
          f" / del {wer['deletions']}"
          f" / ins {wer['insertions']}"
          f" of {wer['reference_words']} ref words)")
    results["transcription"] = transcription.to_dict()
    results["wer"] = wer

    banner("STAGE 5: Alignment → speaker-labelled transcript")
    for label, diarization in (("estimated_speakers", estimated), ("oracle_speakers", oracle)):
        turns = build_speaker_turns(transcription, diarization)
        mapping = results[label]["der"]["mapping"]
        accuracy = word_speaker_accuracy(
            [(word.start, word.end, turn.speaker) for turn in turns for word in turn.words],
            reference,
            mapping,
        )
        results[label]["word_speaker_accuracy"] = accuracy
        results[label]["turns"] = [turn.to_dict() for turn in turns]

        print(f"\n  [{label}] turns={len(turns)}  "
              f"word-speaker accuracy={accuracy['word_speaker_accuracy_percent']:.2f}% "
              f"({accuracy['correct_words']}/{accuracy['scored_words']})")

    banner("HYPOTHESIS TRANSCRIPT (oracle speaker count)")
    oracle_turns = build_speaker_turns(transcription, oracle)
    print(format_transcript(oracle_turns))

    banner("GROUND TRUTH")
    for turn in metadata["turns"]:
        print(f"[{turn['start']:7.2f} - {turn['end']:7.2f}] "
              f"{turn['role']} ({turn['speaker_id']}): {turn['text'][:88]}")

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nSaved detailed results → {args.output}")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--testset", default="data/diar_testset/two_party")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--whisper-model", default="small.en")
    parser.add_argument("--whisper-backend", default="faster_whisper",
                        choices=["faster_whisper", "openai_whisper"])
    parser.add_argument("--compute-type", default="float16")
    parser.add_argument("--language", default="en")
    parser.add_argument("--window-sec", type=float, default=1.5)
    parser.add_argument("--shift-sec", type=float, default=0.75)
    parser.add_argument("--pval", type=float, default=None)
    parser.add_argument("--max-speakers", type=int, default=6)
    parser.add_argument("--collar", type=float, default=0.25)
    parser.add_argument("--output", default=None, help="write full results JSON here")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
