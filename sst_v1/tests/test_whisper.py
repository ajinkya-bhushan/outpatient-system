"""
tests/test_whisper.py
──────────────────────
Unit tests for WhisperEngine internals.

All tests mock the actual whisper.load_model / model.transcribe calls
so no model weights are downloaded during CI.

A special smoke test (marked ``real_model``) can be run with:
    uv run pytest -m real_model -s
This requires the Whisper base model to be pre-downloaded.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.engines.whisper_engine import WhisperEngine


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _make_engine(model_name: str = "base", device: str = "cpu") -> WhisperEngine:
    return WhisperEngine(model_name=model_name, device=device)


MOCK_WHISPER_RESULT = {
    "text": " Hello test.",
    "language": "en",
    "segments": [
        {"id": 0, "seek": 0, "start": 0.0, "end": 1.5,
         "text": " Hello test.", "tokens": [], "temperature": 0.0,
         "avg_logprob": -0.3, "compression_ratio": 1.0, "no_speech_prob": 0.01}
    ],
}


# ═══════════════════════════════════════════════════════════════════════════
# Initialisation
# ═══════════════════════════════════════════════════════════════════════════

class TestWhisperEngineInit:
    def test_default_model_from_settings(self):
        eng = _make_engine()
        assert eng.model_name  # should be non-empty
        assert eng.ENGINE_NAME == "whisper"

    def test_custom_model_name(self):
        eng = _make_engine(model_name="tiny")
        assert eng.model_name == "tiny"

    def test_model_not_loaded_on_init(self):
        eng = _make_engine()
        assert not eng._model_loaded
        assert eng._model is None

    def test_get_info_before_load(self):
        eng = _make_engine()
        info = eng.get_info()
        assert info["engine"] == "whisper"
        assert info["model_loaded"] == "False"


# ═══════════════════════════════════════════════════════════════════════════
# Lazy loading
# ═══════════════════════════════════════════════════════════════════════════

class TestLazyLoading:
    @patch("app.engines.whisper_engine.whisper.load_model")
    def test_load_model_called_once(self, mock_load):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = MOCK_WHISPER_RESULT
        mock_load.return_value = mock_model

        eng = _make_engine()
        eng._load_model()
        eng._load_model()  # second call should be a no-op

        mock_load.assert_called_once_with("base", device="cpu")
        assert eng._model_loaded is True

    @patch("app.engines.whisper_engine.whisper.load_model")
    def test_model_stored_as_instance_attribute(self, mock_load):
        mock_model = MagicMock()
        mock_load.return_value = mock_model

        eng = _make_engine()
        eng._load_model()

        assert eng._model is mock_model


# ═══════════════════════════════════════════════════════════════════════════
# Transcription (mocked)
# ═══════════════════════════════════════════════════════════════════════════

class TestWhisperTranscribeMocked:
    @pytest.mark.asyncio
    @patch("app.engines.whisper_engine.whisper.load_model")
    async def test_transcribe_returns_expected_keys(self, mock_load):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = MOCK_WHISPER_RESULT
        mock_load.return_value = mock_model

        eng = _make_engine()
        result = await eng.transcribe("/fake/path.wav", language="en")

        required = {"text", "language", "segments", "audio_duration",
                    "processing_time", "real_time_factor", "engine", "model"}
        assert required.issubset(result.keys())

    @pytest.mark.asyncio
    @patch("app.engines.whisper_engine.whisper.load_model")
    async def test_transcribe_text_stripped(self, mock_load):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = MOCK_WHISPER_RESULT
        mock_load.return_value = mock_model

        eng = _make_engine()
        result = await eng.transcribe("/fake/path.wav")
        # Leading/trailing whitespace should be stripped
        assert result["text"] == result["text"].strip()

    @pytest.mark.asyncio
    @patch("app.engines.whisper_engine.whisper.load_model")
    async def test_transcribe_engine_name_correct(self, mock_load):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = MOCK_WHISPER_RESULT
        mock_load.return_value = mock_model

        eng = _make_engine()
        result = await eng.transcribe("/fake/path.wav")
        assert result["engine"] == "whisper"

    @pytest.mark.asyncio
    @patch("app.engines.whisper_engine.whisper.load_model")
    async def test_rtf_non_negative(self, mock_load):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = MOCK_WHISPER_RESULT
        mock_load.return_value = mock_model

        eng = _make_engine()
        result = await eng.transcribe("/fake/path.wav")
        assert result["real_time_factor"] >= 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Segment formatting helper
# ═══════════════════════════════════════════════════════════════════════════

class TestSegmentFormatting:
    def test_format_segments_drops_internal_fields(self):
        raw = MOCK_WHISPER_RESULT["segments"]
        formatted = WhisperEngine._format_segments(raw)
        assert all("tokens" not in seg for seg in formatted)
        assert all("avg_logprob" not in seg for seg in formatted)

    def test_format_segments_required_keys(self):
        raw = MOCK_WHISPER_RESULT["segments"]
        formatted = WhisperEngine._format_segments(raw)
        for seg in formatted:
            assert {"id", "start", "end", "text"}.issubset(seg.keys())

    def test_format_empty_segments(self):
        assert WhisperEngine._format_segments([]) == []


# ═══════════════════════════════════════════════════════════════════════════
# Audio duration extraction
# ═══════════════════════════════════════════════════════════════════════════

class TestExtractAudioDuration:
    def test_duration_from_segments(self):
        """Primary path: uses last segment end time."""
        result = {"segments": [{"end": 5.0}, {"end": 10.25}]}
        dur = WhisperEngine._extract_audio_duration(result, "/fake.wav")
        assert dur == pytest.approx(10.25, abs=0.001)

    def test_duration_empty_segments_returns_zero_no_path(self):
        """No segments and no path → 0.0."""
        dur = WhisperEngine._extract_audio_duration({"segments": []}, "")
        assert dur == 0.0

    def test_duration_segments_with_zero_end_falls_through(self):
        """Segment exists but end=0 → falls through to ffprobe path (then 0 if absent)."""
        result = {"segments": [{"end": 0.0}]}
        dur = WhisperEngine._extract_audio_duration(result, "")
        assert dur == 0.0

    @patch("app.engines.whisper_engine.subprocess.run")
    def test_duration_ffprobe_fallback(self, mock_run):
        """When segments empty, ffprobe provides the duration."""
        import json
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"format": {"duration": "7.5"}}),
        )
        dur = WhisperEngine._extract_audio_duration({"segments": []}, "/fake.wav")
        assert dur == pytest.approx(7.5, abs=0.001)

    @patch("app.engines.whisper_engine.subprocess.run", side_effect=FileNotFoundError)
    def test_duration_ffprobe_absent_returns_zero(self, _mock_run):
        """If ffprobe is not installed, fall back gracefully to 0.0."""
        dur = WhisperEngine._extract_audio_duration({"segments": []}, "/fake.wav")
        assert dur == 0.0

    def test_duration_no_segments_key(self):
        """Result dict with no 'segments' key is handled safely."""
        dur = WhisperEngine._extract_audio_duration({}, "")
        assert dur == 0.0



# ═══════════════════════════════════════════════════════════════════════════
# Real model smoke test (opt-in)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.real_model
@pytest.mark.skip(
    reason=(
        "Requires Whisper 'base' weights pre-downloaded and network access. "
        "Run manually: uv run python scripts/download_model.py --model base "
        "then: uv run pytest -m real_model -s --no-header"
    )
)
class TestWhisperRealModel:
    """Requires actual Whisper 'base' model weights. Run with:
        uv run pytest -m real_model -s
    """

    @pytest.mark.asyncio
    async def test_real_transcription(self, tmp_path):
        """Generate a silent WAV and verify Whisper returns a dict."""
        import wave, struct

        wav_path = str(tmp_path / "silent.wav")
        with wave.open(wav_path, "w") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(16000)
            # 1 second of silence
            f.writeframes(struct.pack("<" + "h" * 16000, *([0] * 16000)))

        eng = WhisperEngine(model_name="base", device="cpu")
        result = await eng.transcribe(wav_path)

        assert isinstance(result["text"], str)
        assert result["engine"] == "whisper"
