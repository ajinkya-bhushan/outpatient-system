"""
app/diarization
────────────────
SpeechBrain-based speaker diarization, and the glue that turns a Whisper
transcript into a speaker-labelled one.

Stage layout (see ``pipeline.py`` for the wiring):

    vad.py         SpeechBrain CRDNN VAD          → speech regions
    embeddings.py  SpeechBrain ECAPA-TDNN         → per-sub-segment embeddings
    clustering.py  SpeechBrain spectral clustering→ speaker labels
    pipeline.py    orchestration                  → speaker timeline
    transcribe.py  Whisper / Faster-Whisper       → words + timestamps
    alignment.py   overlap-based join             → speaker-labelled turns
    metrics.py     DER / WER                      → evaluation

Typical use::

    from app.diarization import SpeechBrainDiarizer, WordLevelTranscriber
    from app.diarization.alignment import build_speaker_turns, format_transcript

    diarization = SpeechBrainDiarizer().diarize("consult.wav", num_speakers=2)
    transcription = WordLevelTranscriber().transcribe("consult.wav")
    print(format_transcript(build_speaker_turns(transcription, diarization)))
"""

from app.diarization.alignment import SpeakerTurn, build_speaker_turns, format_transcript
from app.diarization.config import DiarizationConfig
from app.diarization.pipeline import DiarizationResult, SpeakerSegment, SpeechBrainDiarizer
from app.diarization.transcribe import TranscriptionResult, WordLevelTranscriber

__all__ = [
    "DiarizationConfig",
    "DiarizationResult",
    "SpeakerSegment",
    "SpeakerTurn",
    "SpeechBrainDiarizer",
    "TranscriptionResult",
    "WordLevelTranscriber",
    "build_speaker_turns",
    "format_transcript",
]
