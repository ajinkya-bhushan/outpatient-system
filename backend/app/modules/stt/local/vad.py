"""
app/modules/stt/local/vad.py
─────────────────────────────
Stage 1 of the diarization pipeline: find the parts of the recording that
actually contain speech, using SpeechBrain's CRDNN VAD.

Why VAD first
-------------
Speaker embeddings extracted from silence or background noise are meaningless
but still get clustered, which inflates the diarization error rate. Restricting
embedding extraction to speech regions is the single biggest accuracy win in
the whole pipeline.

Lazy loading follows the same contract as ``app/engines`` – the model is pulled
on first use, then cached on the instance.
"""

from __future__ import annotations

import threading

from app.core.logging import get_logger
from app.modules.stt.local.config import DiarizationConfig

logger = get_logger(__name__)


class SpeechBrainVAD:
    """Thin wrapper around ``speechbrain.inference.VAD.VAD``.

    Example::

        vad = SpeechBrainVAD(DiarizationConfig())
        regions = vad.get_speech_regions("/tmp/consult.wav")
        # [(0.31, 4.88), (5.42, 9.10), ...]
    """

    def __init__(self, config: DiarizationConfig | None = None) -> None:
        self.config = config or DiarizationConfig()
        self._model = None
        self._lock = threading.Lock()

    # ── Model loading ─────────────────────────────────────────────────────────

    def load(self) -> None:
        """Download / load the VAD model. Idempotent and thread-safe."""
        if self._model is not None:
            return

        with self._lock:
            if self._model is not None:
                return

            from speechbrain.inference.VAD import VAD

            cfg = self.config.vad
            logger.info("vad_loading", source=cfg.source, device=self.config.device)
            self._model = VAD.from_hparams(
                source=cfg.source,
                savedir=cfg.savedir,
                run_opts={"device": self.config.device},
            )
            logger.info("vad_loaded", source=cfg.source)

    # ── Inference ─────────────────────────────────────────────────────────────

    def get_speech_regions(self, audio_path: str) -> list[tuple[float, float]]:
        """Return speech regions as ``(start_sec, end_sec)`` tuples.

        Args:
            audio_path: Path to a 16 kHz mono WAV file.

        Returns:
            Speech regions in chronological order. An empty list means the VAD
            found no speech at all; callers should decide whether to fall back
            to treating the whole file as speech.
        """
        self.load()
        cfg = self.config.vad

        boundaries = self._model.get_speech_segments(
            audio_path,
            activation_th=cfg.activation_th,
            deactivation_th=cfg.deactivation_th,
            close_th=cfg.close_th,
            len_th=cfg.len_th,
            apply_energy_VAD=cfg.apply_energy_vad,
            double_check=cfg.double_check,
            speech_th=cfg.speech_th,
        )

        regions = [(float(row[0]), float(row[1])) for row in boundaries]
        total = sum(end - start for start, end in regions)
        logger.info("vad_done", n_regions=len(regions), speech_seconds=round(total, 2))
        return regions
