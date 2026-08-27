"""
app/modules/stt/local
──────────────────────
Local in-process speech-to-text and speaker diarization.

Stage layout:

    audio.py       ffmpeg validation + 16 kHz mono conversion
    vad.py         SpeechBrain CRDNN VAD           → speech regions
    embeddings.py  SpeechBrain ECAPA-TDNN          → per-sub-segment embeddings
    clustering.py  SpeechBrain spectral clustering → speaker labels
    diarizer.py    orchestration                   → speaker timeline
    transcribe.py  Whisper / Faster-Whisper        → words + timestamps
    alignment.py   overlap-based join              → speaker-labelled turns
    engine.py      model lifecycle + GPU serialisation
    storage.py     local audio + result persistence

Callers should go through :mod:`app.modules.stt.service`, which selects between
this engine and the remote sst_v1 client based on ``STT_ENGINE_MODE``.
"""
