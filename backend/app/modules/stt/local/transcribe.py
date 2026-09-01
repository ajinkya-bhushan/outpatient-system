"""
app/modules/stt/local/transcribe.py
────────────────────────────────────
Whisper transcription with **word-level timestamps**, which is what makes
speaker attribution possible.

Why word timestamps rather than segment timestamps
--------------------------------------------------
Whisper's own segments are cut on acoustic/linguistic boundaries that ignore
speaker changes, so a single segment routinely spans a doctor's question and
the patient's answer. Aligning at word granularity lets a speaker change land
mid-segment, where it belongs.

Two backends are supported behind one interface:

* ``faster-whisper`` (CTranslate2) – 3-5x faster, lower VRAM. Preferred.
* ``openai-whisper``  (pure PyTorch) – reference implementation, guaranteed to
  run wherever torch runs. Used as a fallback.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from app.core.logging import get_logger

logger = get_logger(__name__)

Backend = Literal["faster_whisper", "openai_whisper"]


@dataclass
class Word:
    """One transcribed word with its time span."""

    start: float
    end: float
    text: str
    probability: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "text": self.text,
            "probability": round(self.probability, 4) if self.probability is not None else None,
        }


@dataclass
class TranscriptionResult:
    """Whisper output reduced to what the diarization pipeline needs."""

    text: str
    language: str
    words: list[Word]
    audio_duration: float
    processing_time: float
    backend: str
    model: str
    segments: list[dict[str, Any]] = field(default_factory=list)

    @property
    def real_time_factor(self) -> float:
        return self.processing_time / self.audio_duration if self.audio_duration else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "language": self.language,
            "backend": self.backend,
            "model": self.model,
            "audio_duration": round(self.audio_duration, 3),
            "processing_time": round(self.processing_time, 3),
            "real_time_factor": round(self.real_time_factor, 4),
            "n_words": len(self.words),
        }


class WordLevelTranscriber:
    """Whisper wrapper that always returns word-level timestamps.

    Example::

        stt = WordLevelTranscriber(model_name="small.en", device="cuda")
        result = stt.transcribe("consult.wav")
        print(result.words[0].text, result.words[0].start)
    """

    def __init__(
        self,
        model_name: str = "small.en",
        device: str = "cuda",
        backend: Backend = "faster_whisper",
        compute_type: str = "float16",
        language: str | None = "en",
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.backend: str = backend
        self.compute_type = compute_type
        self.language = language
        self._model: Any = None
        self._lock = threading.Lock()

    # ── Model loading ─────────────────────────────────────────────────────────

    def load(self) -> None:
        """Load the Whisper model, falling back to openai-whisper if needed.

        CTranslate2 wheels do not always ship kernels for the newest GPU
        architectures, so a CUDA failure here is treated as a signal to switch
        backends rather than a fatal error.
        """
        if self._model is not None:
            return

        with self._lock:
            if self._model is not None:
                return

            if self.backend == "faster_whisper":
                try:
                    self._load_faster_whisper()
                    return
                except Exception as exc:
                    logger.warning(
                        "faster_whisper_unavailable_falling_back",
                        error=str(exc)[:300],
                    )
                    self.backend = "openai_whisper"

            self._load_openai_whisper()

    def _load_faster_whisper(self) -> None:
        from faster_whisper import WhisperModel

        # CTranslate2 takes the device and its index as separate arguments and
        # rejects a torch-style "cuda:0" outright, unlike SpeechBrain which
        # requires the index. Split it here rather than weakening the device
        # string the rest of the pipeline relies on.
        device, _, index = self.device.partition(":")
        device_index = int(index) if index.isdigit() else 0

        logger.info(
            "whisper_loading",
            backend="faster_whisper",
            model=self.model_name,
            device=device,
            device_index=device_index,
            compute_type=self.compute_type,
        )
        self._model = WhisperModel(
            self.model_name,
            device=device,
            device_index=device_index,
            compute_type=self.compute_type,
        )
        logger.info("whisper_loaded", backend="faster_whisper", model=self.model_name)

    def _load_openai_whisper(self) -> None:
        import whisper

        logger.info(
            "whisper_loading",
            backend="openai_whisper",
            model=self.model_name,
            device=self.device,
        )
        self._model = whisper.load_model(self.model_name, device=self.device)
        logger.info("whisper_loaded", backend="openai_whisper", model=self.model_name)

    # ── Inference ─────────────────────────────────────────────────────────────

    def transcribe(self, audio_path: str, language: str | None = None) -> TranscriptionResult:
        """Transcribe a file and return words with timestamps."""
        self.load()
        language = language if language is not None else self.language

        started = time.perf_counter()
        if self.backend == "faster_whisper":
            result = self._transcribe_faster(audio_path, language)
        else:
            result = self._transcribe_openai(audio_path, language)
        result.processing_time = time.perf_counter() - started

        logger.info(
            "transcription_done",
            backend=result.backend,
            n_words=len(result.words),
            rtf=round(result.real_time_factor, 3),
        )
        return result

    def _transcribe_faster(self, audio_path: str, language: str | None) -> TranscriptionResult:
        segments_iter, info = self._model.transcribe(
            audio_path,
            language=language,
            word_timestamps=True,
            vad_filter=False,  # the SpeechBrain VAD already owns this decision
            beam_size=5,
        )

        words: list[Word] = []
        segments: list[dict[str, Any]] = []
        texts: list[str] = []

        for segment in segments_iter:
            texts.append(segment.text)
            segments.append(
                {"start": segment.start, "end": segment.end, "text": segment.text.strip()}
            )
            for word in segment.words or []:
                stripped = word.word.strip()
                if stripped:
                    words.append(
                        Word(
                            start=float(word.start),
                            end=float(word.end),
                            text=stripped,
                            probability=float(word.probability),
                        )
                    )

        return TranscriptionResult(
            text="".join(texts).strip(),
            language=info.language,
            words=words,
            audio_duration=float(info.duration),
            processing_time=0.0,
            backend="faster_whisper",
            model=self.model_name,
            segments=segments,
        )

    def _transcribe_openai(self, audio_path: str, language: str | None) -> TranscriptionResult:
        import whisper

        raw = self._model.transcribe(
            audio_path,
            language=language,
            word_timestamps=True,
            fp16=self.device.startswith("cuda"),
            verbose=False,
        )

        words: list[Word] = []
        segments: list[dict[str, Any]] = []

        for segment in raw.get("segments", []):
            segments.append(
                {
                    "start": segment["start"],
                    "end": segment["end"],
                    "text": segment["text"].strip(),
                }
            )
            for word in segment.get("words", []):
                stripped = word["word"].strip()
                if stripped:
                    words.append(
                        Word(
                            start=float(word["start"]),
                            end=float(word["end"]),
                            text=stripped,
                            probability=float(word.get("probability", 0.0)),
                        )
                    )

        audio_duration = float(len(whisper.load_audio(audio_path)) / 16_000)

        return TranscriptionResult(
            text=raw.get("text", "").strip(),
            language=raw.get("language", language or "unknown"),
            words=words,
            audio_duration=audio_duration,
            processing_time=0.0,
            backend="openai_whisper",
            model=self.model_name,
            segments=segments,
        )
