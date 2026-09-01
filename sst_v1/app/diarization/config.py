"""
app/diarization/config.py
──────────────────────────
Tunable knobs for the SpeechBrain diarization pipeline.

Kept as a plain dataclass (not pydantic-settings) because these are
*algorithmic* parameters that get swept during evaluation, not deployment
secrets.  The service-level defaults live in ``app/core/config.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


def _default_device() -> str:
    try:
        import torch

        return "cuda:0" if torch.cuda.is_available() else "cpu"
    except Exception:  # pragma: no cover - torch is a hard dependency in practice
        return "cpu"


def normalise_device(device: str) -> str:
    """Expand a bare ``"cuda"`` to ``"cuda:0"``.

    SpeechBrain parses ``run_opts["device"]`` by splitting on ``":"`` and warns
    noisily on a bare ``"cuda"``, so pin the index explicitly.
    """
    return "cuda:0" if device == "cuda" else device


@dataclass
class VADConfig:
    """SpeechBrain CRDNN voice-activity-detection settings."""

    source: str = "speechbrain/vad-crdnn-libriparty"
    savedir: str = "models/vad-crdnn"

    activation_th: float = 0.5
    deactivation_th: float = 0.25
    # Merge speech regions separated by less than this many seconds.
    close_th: float = 0.25
    # Drop speech regions shorter than this many seconds.
    len_th: float = 0.25
    # The neural VAD tends to merge close segments; the energy pass splits them.
    apply_energy_vad: bool = True
    double_check: bool = True
    speech_th: float = 0.5


@dataclass
class EmbeddingConfig:
    """ECAPA-TDNN speaker-embedding settings."""

    source: str = "speechbrain/spkrec-ecapa-voxceleb"
    savedir: str = "models/ecapa"

    # Sliding sub-segment geometry. 1.5s/0.75s is a good compromise for
    # conversational turns; the AMI recipe uses 3.0s/1.5s for long meetings.
    window_sec: float = 1.5
    shift_sec: float = 0.75
    # Sub-segments shorter than this are dropped: ECAPA embeddings from very
    # short audio are dominated by phonetic rather than speaker content.
    min_subseg_sec: float = 0.5
    batch_size: int = 32


@dataclass
class ClusteringConfig:
    """Spectral-clustering settings (SpeechBrain ``Spec_Clust_unorm``)."""

    min_speakers: int = 2
    max_speakers: int = 6

    # SpeechBrain prunes the affinity matrix so that roughly ``pval * N``
    # neighbours survive in each row. That makes a fixed pval dependent on
    # recording length, so by default we derive it from a target neighbour
    # count instead. Set ``pval`` explicitly to override.
    pval: float | None = None
    target_neighbors: int = 8
    min_neighbors: int = 3

    # Below this many sub-segments the eigen-gap heuristic is unreliable and
    # we fall back to agglomerative clustering.
    min_subsegs_for_spectral: int = 6

    # Spectral clustering cannot return a single cluster, so a one-voice
    # recording is screened out beforehand: if the mean pairwise cosine
    # similarity of all embeddings exceeds this, everything is one speaker.
    # Only consulted when ``min_speakers <= 1``.
    single_speaker_cosine_th: float = 0.55


@dataclass
class DiarizationConfig:
    """Top-level configuration for the diarization pipeline."""

    sample_rate: int = 16_000
    device: str = field(default_factory=_default_device)

    vad: VADConfig = field(default_factory=VADConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    clustering: ClusteringConfig = field(default_factory=ClusteringConfig)

    def __post_init__(self) -> None:
        self.device = normalise_device(self.device)
