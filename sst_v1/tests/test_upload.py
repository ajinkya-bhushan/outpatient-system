"""
tests/test_upload.py
─────────────────────
Integration-style tests for the POST /api/v1/transcribe endpoint.

All tests use FastAPI's ``TestClient`` (synchronous httpx wrapper).
The actual Whisper model is MOCKED so tests run without downloading
model weights and complete in milliseconds.

Test groups
-----------
* HealthCheck        – basic liveness tests
* UploadValidation   – bad extension, oversized file, missing file
* UploadTranscription – happy-path with mocked engine
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

client = TestClient(app, raise_server_exceptions=False)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _fake_wav_bytes(n: int = 44) -> bytes:
    """Return a syntactically valid (but silent) WAV header."""
    # 44-byte WAV header with zero data
    header = bytearray(44)
    header[0:4] = b"RIFF"
    header[4:8] = (36).to_bytes(4, "little")  # chunk size
    header[8:12] = b"WAVE"
    header[12:16] = b"fmt "
    header[16:20] = (16).to_bytes(4, "little")
    header[20:22] = (1).to_bytes(2, "little")   # PCM
    header[22:24] = (1).to_bytes(2, "little")   # mono
    header[24:28] = (16000).to_bytes(4, "little")  # 16 kHz
    header[28:32] = (32000).to_bytes(4, "little")
    header[32:34] = (2).to_bytes(2, "little")
    header[34:36] = (16).to_bytes(2, "little")
    header[36:40] = b"data"
    header[40:44] = (0).to_bytes(4, "little")
    return bytes(header)


MOCK_TRANSCRIPTION_RESULT = {
    "text": "Hello world this is a test.",
    "language": "en",
    "segments": [
        {"id": 0, "start": 0.0, "end": 2.5, "text": "Hello world this is a test."}
    ],
    "audio_duration": 5.0,
    "processing_time": 0.5,
    "real_time_factor": 0.1,
    "engine": "whisper",
    "model": "base",
}


# ═══════════════════════════════════════════════════════════════════════════
# Health checks
# ═══════════════════════════════════════════════════════════════════════════

class TestHealthCheck:
    def test_health_returns_200(self):
        r = client.get("/api/v1/health")
        assert r.status_code == 200

    def test_health_body_has_status_ok(self):
        r = client.get("/api/v1/health")
        assert r.json()["status"] == "ok"

    def test_ready_returns_200(self):
        r = client.get("/api/v1/ready")
        assert r.status_code == 200

    def test_ready_body_has_engines(self):
        r = client.get("/api/v1/ready")
        body = r.json()
        assert "available_engines" in body
        assert "whisper" in body["available_engines"]


# ═══════════════════════════════════════════════════════════════════════════
# Upload validation – bad requests (no model required)
# ═══════════════════════════════════════════════════════════════════════════

class TestUploadValidation:
    def test_no_file_returns_422(self):
        """Missing required `file` field → FastAPI 422."""
        r = client.post("/api/v1/transcribe", data={"engine": "whisper"})
        assert r.status_code == 422

    def test_unsupported_extension_returns_400(self):
        """PDF file → 400 Bad Request."""
        r = client.post(
            "/api/v1/transcribe",
            files={"file": ("document.pdf", b"%PDF-1.4", "application/pdf")},
            data={"engine": "whisper"},
        )
        assert r.status_code == 400
        assert "extension" in r.json()["detail"].lower()

    def test_oversized_file_returns_400(self):
        """File > MAX_AUDIO_SIZE_MB → 400 Bad Request."""
        big_bytes = b"0" * (51 * 1024 * 1024)  # 51 MB
        r = client.post(
            "/api/v1/transcribe",
            files={"file": ("audio.wav", big_bytes, "audio/wav")},
            data={"engine": "whisper"},
        )
        assert r.status_code == 400
        assert "exceeds" in r.json()["detail"].lower()

    def test_invalid_engine_returns_400(self):
        """Unknown engine name → 400 Bad Request (mocked to avoid model load)."""
        r = client.post(
            "/api/v1/transcribe",
            files={"file": ("a.wav", _fake_wav_bytes(), "audio/wav")},
            data={"engine": "nonexistent_engine_xyz"},
        )
        assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# Happy-path upload with mocked engine
# ═══════════════════════════════════════════════════════════════════════════

# Sentinel validation result returned by the mock – matches what a real
# ffprobe call would return for a valid audio file.
_MOCK_VALIDATION_INFO = {"extension": ".wav", "mime_type": "audio/wav", "duration": 5.0}


class TestUploadTranscription:
    @patch("app.api.routes_upload.get_engine")
    @patch("app.api.routes_upload.prepare_audio_for_inference")
    @patch("app.api.routes_upload.validate_audio_file")
    def test_successful_transcription(self, mock_validate, mock_prepare, mock_get_engine):
        """Mock engine + prepare_audio + validate so no real ffmpeg/model needed."""
        # validate_audio_file returns a valid info dict (no ffprobe needed)
        mock_validate.return_value = _MOCK_VALIDATION_INFO
        # prepare_audio returns the input path unchanged, no cleanup needed
        mock_prepare.return_value = ("/tmp/fake.wav", False)

        # Engine returns mock result
        mock_engine = MagicMock()
        mock_engine.transcribe = AsyncMock(return_value=MOCK_TRANSCRIPTION_RESULT)
        mock_get_engine.return_value = mock_engine

        r = client.post(
            "/api/v1/transcribe",
            files={"file": ("audio.wav", _fake_wav_bytes(), "audio/wav")},
            data={"engine": "whisper", "language": "en", "task": "transcribe"},
        )

        assert r.status_code == 200
        body = r.json()
        assert body["text"] == "Hello world this is a test."
        assert body["language"] == "en"
        assert body["engine"] == "whisper"
        assert body["model"] == "base"
        assert "real_time_factor" in body
        assert isinstance(body["segments"], list)

    @patch("app.api.routes_upload.get_engine")
    @patch("app.api.routes_upload.prepare_audio_for_inference")
    @patch("app.api.routes_upload.validate_audio_file")
    def test_response_schema_complete(self, mock_validate, mock_prepare, mock_get_engine):
        """All required response fields must be present."""
        mock_validate.return_value = _MOCK_VALIDATION_INFO
        mock_prepare.return_value = ("/tmp/fake.wav", False)

        mock_engine = MagicMock()
        mock_engine.transcribe = AsyncMock(return_value=MOCK_TRANSCRIPTION_RESULT)
        mock_get_engine.return_value = mock_engine

        r = client.post(
            "/api/v1/transcribe",
            files={"file": ("audio.wav", _fake_wav_bytes(), "audio/wav")},
            data={"engine": "whisper"},
        )

        body = r.json()
        required_fields = {
            "text", "language", "segments",
            "audio_duration", "processing_time",
            "real_time_factor", "engine", "model",
        }
        assert required_fields.issubset(body.keys())
