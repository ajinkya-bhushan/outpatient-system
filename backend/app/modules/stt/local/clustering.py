"""
app/modules/stt/local/clustering.py
────────────────────────────────────
Stage 3 of the diarization pipeline: group ECAPA embeddings into speakers.

Primary algorithm is SpeechBrain's ``Spec_Clust_unorm`` – unnormalised spectral
clustering on a cosine-similarity affinity matrix, with the speaker count
estimated from the largest eigen-gap.

Two things about the SpeechBrain implementation need wrapping:

1. **``p_val`` is length-dependent.** Pruning keeps roughly ``p_val * N``
   neighbours per row, so a value tuned on hour-long AMI meetings disconnects
   the affinity graph of a 60-second consultation. We derive ``p_val`` from a
   target neighbour count instead.
2. **It can never return one speaker.** The eigen-gap estimate is
   ``argmax(gaps) + 2`` and is then clamped to ``min_num_spkrs``. A single-voice
   recording (a doctor dictating a note) would be split into two phantom
   speakers, so we screen for that case up front.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.core.logging import get_logger
from app.modules.stt.local.config import ClusteringConfig

logger = get_logger(__name__)


@dataclass
class ClusteringResult:
    """Cluster assignment plus the diagnostics used to reach it."""

    labels: np.ndarray
    num_speakers: int
    method: str
    pval: float | None
    mean_pairwise_cosine: float


def _mean_pairwise_cosine(embeddings: np.ndarray) -> float:
    """Mean off-diagonal cosine similarity of L2-normalised embeddings.

    A useful single-number summary of how "mixed" a recording is: high means
    every sub-segment sounds like the same person.
    """
    if len(embeddings) < 2:
        return 1.0

    sim = embeddings @ embeddings.T
    n = len(sim)
    off_diagonal = (sim.sum() - np.trace(sim)) / (n * (n - 1))
    return float(off_diagonal)


def _resolve_pval(config: ClusteringConfig, n_subsegs: int) -> float:
    """Pick the affinity-pruning parameter for a recording of this length."""
    if config.pval is not None:
        return config.pval

    neighbors = max(config.min_neighbors, min(config.target_neighbors, n_subsegs - 1))
    return float(np.clip(neighbors / n_subsegs, 0.0, 0.95))


def _agglomerative(embeddings: np.ndarray, num_speakers: int) -> np.ndarray:
    """Cosine-distance AHC – fallback for very short recordings."""
    from sklearn.cluster import AgglomerativeClustering

    model = AgglomerativeClustering(
        n_clusters=num_speakers,
        metric="cosine",
        linkage="average",
    )
    return model.fit_predict(embeddings)


def cluster_embeddings(
    embeddings: np.ndarray,
    config: ClusteringConfig,
    num_speakers: int | None = None,
) -> ClusteringResult:
    """Assign a speaker label to every embedding.

    Args:
        embeddings:   ``(n_subsegs, dim)`` L2-normalised ECAPA embeddings.
        config:       Clustering configuration.
        num_speakers: Known speaker count ("oracle"), or ``None`` to estimate.

    Returns:
        A :class:`ClusteringResult` whose ``labels`` align element-wise with
        ``embeddings``.
    """
    n = len(embeddings)
    cohesion = _mean_pairwise_cosine(embeddings)

    if n == 0:
        return ClusteringResult(np.zeros(0, dtype=int), 0, "empty", None, cohesion)

    if n == 1 or num_speakers == 1:
        return ClusteringResult(np.zeros(n, dtype=int), 1, "trivial", None, cohesion)

    # Screen for the single-speaker case that spectral clustering cannot express.
    if (
        num_speakers is None
        and config.min_speakers <= 1
        and cohesion >= config.single_speaker_cosine_th
    ):
        logger.info("clustering_single_speaker", mean_cosine=round(cohesion, 3))
        return ClusteringResult(np.zeros(n, dtype=int), 1, "single_speaker_screen", None, cohesion)

    # Too few points for a meaningful eigen-gap: fall back to AHC.
    if n < config.min_subsegs_for_spectral:
        k = num_speakers or min(config.min_speakers, n)
        labels = _agglomerative(embeddings, k)
        logger.info("clustering_ahc_fallback", n_subsegs=n, num_speakers=k)
        return ClusteringResult(labels, len(set(labels)), "agglomerative", None, cohesion)

    from speechbrain.integrations.alignment.diarization import Spec_Clust_unorm

    pval = _resolve_pval(config, n)
    clusterer = Spec_Clust_unorm(
        min_num_spkrs=max(2, config.min_speakers),
        max_num_spkrs=config.max_speakers,
    )
    # SpeechBrain mutates the affinity/Laplacian matrices in place; the input
    # embeddings themselves are only read, but copy for safety.
    clusterer.do_spec_clust(embeddings.astype(np.float64, copy=True), num_speakers, pval)
    labels = np.asarray(clusterer.labels_, dtype=int)

    result = ClusteringResult(
        labels=labels,
        num_speakers=len(set(labels.tolist())),
        method="spectral",
        pval=pval,
        mean_pairwise_cosine=cohesion,
    )
    logger.info(
        "clustering_done",
        method=result.method,
        n_subsegs=n,
        num_speakers=result.num_speakers,
        pval=round(pval, 4),
        mean_cosine=round(cohesion, 3),
    )
    return result
