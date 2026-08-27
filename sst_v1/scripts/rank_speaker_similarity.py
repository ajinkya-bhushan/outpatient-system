"""
scripts/rank_speaker_similarity.py
───────────────────────────────────
Rank LibriSpeech speaker pairs by ECAPA-embedding similarity, to build test
sets that are hard for the *right* reason.

Picking "two speakers of different gender" makes diarization look better than
it is; picking a pair the embedding model itself finds confusable stresses the
clustering stage directly. This computes a mean ECAPA centroid per speaker and
prints the most and least similar pairs.

Usage
-----
    PYTHONPATH=. python scripts/rank_speaker_similarity.py --top 10
"""

from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import librosa  # noqa: E402
import numpy as np  # noqa: E402

from app.diarization.config import DiarizationConfig  # noqa: E402
from app.diarization.embeddings import ECAPAEmbedder, SubSegment  # noqa: E402


def speaker_centroid(
    embedder: ECAPAEmbedder,
    speaker_dir: Path,
    n_utterances: int,
    max_sec: float,
) -> np.ndarray | None:
    """Mean L2-normalised ECAPA embedding across a few of a speaker's files."""
    flac_files = sorted(speaker_dir.rglob("*.flac"))[:n_utterances]
    if not flac_files:
        return None

    vectors = []
    for flac_path in flac_files:
        audio, _ = librosa.load(str(flac_path), sr=16_000, mono=True, duration=max_sec)
        if len(audio) < 16_000:
            continue
        embedding = embedder.embed(
            audio.astype(np.float32),
            [SubSegment(0.0, len(audio) / 16_000)],
        )
        vectors.append(embedding[0])

    if not vectors:
        return None

    centroid = np.mean(vectors, axis=0)
    return centroid / max(np.linalg.norm(centroid), 1e-9)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--librispeech-dir", default="data/LibriSpeech/dev-clean-2")
    parser.add_argument("--n-utterances", type=int, default=4)
    parser.add_argument("--max-sec", type=float, default=8.0)
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    librispeech_dir = Path(args.librispeech_dir)
    speaker_dirs = sorted([d for d in librispeech_dir.iterdir() if d.is_dir()], key=lambda d: d.name)

    embedder = ECAPAEmbedder(DiarizationConfig())
    embedder.load()

    centroids: dict[str, np.ndarray] = {}
    for speaker_dir in speaker_dirs:
        centroid = speaker_centroid(embedder, speaker_dir, args.n_utterances, args.max_sec)
        if centroid is not None:
            centroids[speaker_dir.name] = centroid

    pairs = [
        (a, b, float(centroids[a] @ centroids[b]))
        for a, b in itertools.combinations(sorted(centroids), 2)
    ]
    pairs.sort(key=lambda row: row[2], reverse=True)

    print(f"\n{len(centroids)} speakers, {len(pairs)} pairs\n")
    print(f"MOST similar (hardest to separate) — top {args.top}:")
    for a, b, similarity in pairs[: args.top]:
        print(f"  {a:>6} vs {b:>6}   cosine = {similarity:+.4f}")

    print(f"\nLEAST similar (easiest) — bottom {args.top}:")
    for a, b, similarity in pairs[-args.top :]:
        print(f"  {a:>6} vs {b:>6}   cosine = {similarity:+.4f}")

    # A hard triple: the three speakers with the highest mutual similarity.
    triples = [
        (a, b, c, (centroids[a] @ centroids[b] + centroids[a] @ centroids[c]
                   + centroids[b] @ centroids[c]) / 3)
        for a, b, c in itertools.combinations(sorted(centroids), 3)
    ]
    triples.sort(key=lambda row: row[3], reverse=True)
    print("\nMOST similar triples — top 5:")
    for a, b, c, similarity in triples[:5]:
        print(f"  {a:>6}, {b:>6}, {c:>6}   mean cosine = {similarity:+.4f}")


if __name__ == "__main__":
    main()
