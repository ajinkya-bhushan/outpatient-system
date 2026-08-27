"""
app/modules/stt/local/embeddings.py
────────────────────────────────────
Stage 2 of the diarization pipeline: turn speech regions into a sequence of
fixed-length ECAPA-TDNN speaker embeddings.

Sub-segmentation
----------------
A VAD region can span a whole minute and contain several speakers, so regions
are cut into short overlapping *sub-segments* (default 1.5 s window / 0.75 s
shift). Each sub-segment gets one 192-dim ECAPA embedding, and clustering then
operates on that sequence. Sub-segment length is the core accuracy trade-off:

* longer  → more reliable embeddings, coarser speaker-change resolution
* shorter → sharper turn boundaries, noisier embeddings
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

import numpy as np
import torch

from app.core.logging import get_logger
from app.modules.stt.local.config import DiarizationConfig

logger = get_logger(__name__)


@dataclass(frozen=True)
class SubSegment:
    """A short slice of audio that receives exactly one speaker embedding."""

    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def build_subsegments(
    regions: list[tuple[float, float]],
    window_sec: float,
    shift_sec: float,
    min_subseg_sec: float,
) -> list[SubSegment]:
    """Slice speech regions into overlapping fixed-length sub-segments.

    A region shorter than ``window_sec`` yields a single sub-segment covering
    the whole region (provided it clears ``min_subseg_sec``), so short
    back-channel turns like "mhm" are not silently dropped.
    """
    subsegs: list[SubSegment] = []

    for region_start, region_end in regions:
        region_duration = region_end - region_start
        if region_duration < min_subseg_sec:
            continue

        if region_duration <= window_sec:
            subsegs.append(SubSegment(region_start, region_end))
            continue

        start = region_start
        while start < region_end:
            end = min(start + window_sec, region_end)
            if end - start >= min_subseg_sec:
                subsegs.append(SubSegment(start, end))
            if end >= region_end:
                break
            start += shift_sec

    return subsegs


class ECAPAEmbedder:
    """ECAPA-TDNN speaker-embedding extractor.

    Example::

        embedder = ECAPAEmbedder(DiarizationConfig())
        emb = embedder.embed(waveform, subsegs)   # (n_subsegs, 192)
    """

    def __init__(self, config: DiarizationConfig | None = None) -> None:
        self.config = config or DiarizationConfig()
        self._model = None
        self._lock = threading.Lock()

    # ── Model loading ─────────────────────────────────────────────────────────

    def load(self) -> None:
        """Download / load the ECAPA model. Idempotent and thread-safe."""
        if self._model is not None:
            return

        with self._lock:
            if self._model is not None:
                return

            from speechbrain.inference.speaker import EncoderClassifier

            cfg = self.config.embedding
            logger.info("ecapa_loading", source=cfg.source, device=self.config.device)
            self._model = EncoderClassifier.from_hparams(
                source=cfg.source,
                savedir=cfg.savedir,
                run_opts={"device": self.config.device},
            )
            logger.info("ecapa_loaded", source=cfg.source)

    # ── Inference ─────────────────────────────────────────────────────────────

    @torch.inference_mode()
    def embed(self, waveform: np.ndarray, subsegs: list[SubSegment]) -> np.ndarray:
        """Extract one L2-normalised embedding per sub-segment.

        Args:
            waveform: Mono float32 samples at ``config.sample_rate``.
            subsegs:  Sub-segments to embed.

        Returns:
            Array of shape ``(len(subsegs), 192)``. Empty input yields an
            ``(0, 192)`` array so downstream code needs no special-casing.
        """
        self.load()

        if not subsegs:
            return np.zeros((0, 192), dtype=np.float32)

        sr = self.config.sample_rate
        device = self.config.device
        batch_size = self.config.embedding.batch_size
        n_samples = len(waveform)

        vectors: list[np.ndarray] = []

        for batch_start in range(0, len(subsegs), batch_size):
            batch = subsegs[batch_start : batch_start + batch_size]

            clips: list[torch.Tensor] = []
            for sub in batch:
                lo = max(0, round(sub.start * sr))
                hi = min(n_samples, round(sub.end * sr))
                clips.append(torch.from_numpy(np.ascontiguousarray(waveform[lo:hi])))

            # Right-pad to the longest clip and tell ECAPA the true relative
            # lengths so statistics pooling ignores the padding.
            lengths = torch.tensor([c.shape[0] for c in clips], dtype=torch.float32)
            longest = int(lengths.max().item())
            padded = torch.zeros(len(clips), longest, dtype=torch.float32)
            for i, clip in enumerate(clips):
                padded[i, : clip.shape[0]] = clip

            embeddings = self._model.encode_batch(
                padded.to(device),
                (lengths / longest).to(device),
            )
            # encode_batch returns (batch, 1, emb_dim)
            vectors.append(embeddings.squeeze(1).float().cpu().numpy())

        stacked = np.concatenate(vectors, axis=0)
        norms = np.linalg.norm(stacked, axis=1, keepdims=True)
        stacked = stacked / np.maximum(norms, 1e-9)

        logger.info("ecapa_done", n_subsegs=len(subsegs), dim=int(stacked.shape[1]))
        return stacked
