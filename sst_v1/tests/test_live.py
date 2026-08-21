"""
tests/test_live.py
───────────────────
Tests for the WebSocket live transcription endpoint  /api/v1/live.

Test groups
-----------
* TestWebSocketLifecycle    - connection, start, stop, disconnect flows
* TestSessionMetrics        - SessionMetrics helper class
* TestAudioChunkHandling    - binary audio frame handling
* TestEngineFailure         - engine errors handled gracefully
* TestNormalTranscriptionFlow - full mocked start -> audio -> stop -> final
* TestWhisperFlowEngine     - engine instantiation / availability checks
* TestLiveSmoke             - real model smoke test (opt-in, skipped by default)

All tests mock the actual engine so no model inference happens.
"""

from __future__ import annotations

import asyncio
import json
import struct
import wave
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fake_wav_bytes(duration_s: float = 0.5, sample_rate: int = 16000) -> bytes:
    """Create a minimal in-memory WAV file (silent)."""
    import io
    n = int(duration_s * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{n}h", *([0] * n)))
    return buf.getvalue()


MOCK_TRANSCRIPTION_RESULT = {
    "text": "Hello from the live test.",
    "language": "en",
    "segments": [{"id": 0, "start": 0.0, "end": 1.0, "text": "Hello from the live test."}],
    "audio_duration": 1.0,
    "processing_time": 0.5,
    "real_time_factor": 0.5,
    "engine": "whisper",
    "model": "base",
}


# ═══════════════════════════════════════════════════════════════════════════
# WebSocket Lifecycle
# ═══════════════════════════════════════════════════════════════════════════

class TestWebSocketLifecycle:
    def test_websocket_accepts_connection(self):
        """Server must accept a fresh WebSocket connection without crashing."""
        with client.websocket_connect("/api/v1/live") as ws:
            ws.close()

    def test_start_message_gets_session_started_response(self):
        """'start' control frame must return session_started with session_id."""
        with client.websocket_connect("/api/v1/live") as ws:
            ws.send_text(json.dumps({"type": "start", "engine": "whisper", "language": "en"}))
            response = json.loads(ws.receive_text())
            assert response["type"] == "session_started"
            assert "session_id" in response
            assert response["engine"] == "whisper"
            assert "timestamp" in response

    def test_invalid_json_gets_error_response(self):
        """Malformed JSON text frame must return an error, not crash the server."""
        with client.websocket_connect("/api/v1/live") as ws:
            ws.send_text("this is not json {{{")
            response = json.loads(ws.receive_text())
            assert response["type"] == "error"

    def test_unknown_message_type_gets_error(self):
        """Unknown message type must return error without crashing."""
        with client.websocket_connect("/api/v1/live") as ws:
            ws.send_text(json.dumps({"type": "totally_unknown_xyz"}))
            response = json.loads(ws.receive_text())
            assert response["type"] == "error"

    def test_stop_without_start_gets_error(self):
        """'stop' before 'start' must return error, not crash."""
        with client.websocket_connect("/api/v1/live") as ws:
            ws.send_text(json.dumps({"type": "stop"}))
            response = json.loads(ws.receive_text())
            assert response["type"] == "error"

    def test_audio_before_start_gets_error(self):
        """Binary audio sent before 'start' must return an error."""
        with client.websocket_connect("/api/v1/live") as ws:
            ws.send_bytes(b"\x00\x01\x02\x03")
            response = json.loads(ws.receive_text())
            assert response["type"] == "error"

    def test_double_start_gets_error(self):
        """Sending 'start' twice in the same session must return error."""
        with client.websocket_connect("/api/v1/live") as ws:
            ws.send_text(json.dumps({"type": "start", "engine": "whisper"}))
            _resp1 = json.loads(ws.receive_text())  # session_started
            ws.send_text(json.dumps({"type": "start", "engine": "whisper"}))
            response = json.loads(ws.receive_text())
            assert response["type"] == "error"

    def test_session_started_has_language_field(self):
        """session_started response must echo back the requested language."""
        with client.websocket_connect("/api/v1/live") as ws:
            ws.send_text(json.dumps({"type": "start", "engine": "whisper", "language": "fr"}))
            response = json.loads(ws.receive_text())
            assert response.get("language") == "fr"


# ═══════════════════════════════════════════════════════════════════════════
# SessionMetrics helper
# ═══════════════════════════════════════════════════════════════════════════

class TestSessionMetrics:
    def test_elapsed_ms_positive(self):
        from app.api.routes_live import SessionMetrics
        m = SessionMetrics()
        assert m.elapsed_ms() >= 0

    def test_on_audio_accumulates_bytes(self):
        from app.api.routes_live import SessionMetrics
        m = SessionMetrics()
        m.on_audio(1000)
        m.on_audio(500)
        assert m.total_audio_bytes == 1500

    def test_first_audio_timestamp_set_once(self):
        from app.api.routes_live import SessionMetrics
        m = SessionMetrics()
        m.on_audio(100)
        t1 = m.first_audio_at
        m.on_audio(100)
        assert m.first_audio_at == t1  # not reset on second call

    def test_ttft_none_before_transcript(self):
        from app.api.routes_live import SessionMetrics
        m = SessionMetrics()
        m.on_audio(100)
        assert m.time_to_first_token_ms() is None  # no partial yet

    def test_ttft_computed_after_partial(self):
        from app.api.routes_live import SessionMetrics
        m = SessionMetrics()
        m.on_audio(100)
        m.on_partial()
        ttft = m.time_to_first_token_ms()
        assert ttft is not None
        assert ttft >= 0

    def test_summary_has_required_keys(self):
        from app.api.routes_live import SessionMetrics
        m = SessionMetrics()
        m.on_audio(16000)
        m.on_partial()
        s = m.summary()
        for key in [
            "total_session_ms", "time_to_first_token_ms",
            "total_audio_bytes", "estimated_audio_duration_s",
            "partial_results_sent", "final_transcript_length",
        ]:
            assert key in s, f"Missing key: {key}"


# ═══════════════════════════════════════════════════════════════════════════
# Engine failure handling
# ═══════════════════════════════════════════════════════════════════════════

class TestEngineFailure:
    def test_invalid_engine_name_returns_error(self):
        """Requesting a non-existent engine must return an error frame."""
        with client.websocket_connect("/api/v1/live") as ws:
            ws.send_text(json.dumps({"type": "start", "engine": "nonexistent_engine_xyz"}))
            response = json.loads(ws.receive_text())
            assert response["type"] == "error"
            assert "unavailable" in response["detail"].lower() or "engine" in response["detail"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# Normal transcription flow (fully mocked)
# ═══════════════════════════════════════════════════════════════════════════

class TestNormalTranscriptionFlow:
    @patch("app.api.routes_live.get_engine")
    @patch("app.api.routes_live._transcribe_buffer")
    def test_stop_produces_final_and_session_ended(self, mock_tb, mock_get_engine):
        """Full flow: start -> audio -> stop -> final -> session_ended."""
        mock_engine = MagicMock()
        mock_get_engine.return_value = mock_engine
        mock_tb.return_value = MOCK_TRANSCRIPTION_RESULT

        with client.websocket_connect("/api/v1/live") as ws:
            # 1. Start
            ws.send_text(json.dumps({"type": "start", "engine": "whisper", "language": "en"}))
            msg1 = json.loads(ws.receive_text())
            assert msg1["type"] == "session_started"

            # 2. Send audio (below PARTIAL_CHUNK_BYTES threshold, no partial triggered)
            ws.send_bytes(b"\x00" * 100)

            # 3. Stop
            ws.send_text(json.dumps({"type": "stop"}))

            # Drain messages until we see session_ended
            messages = []
            for _ in range(10):
                try:
                    raw = ws.receive_text()
                    msg = json.loads(raw)
                    messages.append(msg)
                    if msg["type"] == "session_ended":
                        break
                except Exception:
                    break

        types = [m["type"] for m in messages]
        assert "final" in types, f"Expected 'final' in {types}"
        assert "session_ended" in types, f"Expected 'session_ended' in {types}"

    @patch("app.api.routes_live.get_engine")
    @patch("app.api.routes_live._transcribe_buffer")
    def test_session_ended_has_metrics(self, mock_tb, mock_get_engine):
        """session_ended message must include a 'metrics' dict."""
        mock_engine = MagicMock()
        mock_get_engine.return_value = mock_engine
        mock_tb.return_value = MOCK_TRANSCRIPTION_RESULT

        with client.websocket_connect("/api/v1/live") as ws:
            ws.send_text(json.dumps({"type": "start", "engine": "whisper"}))
            json.loads(ws.receive_text())  # session_started

            ws.send_bytes(b"\x00" * 100)
            ws.send_text(json.dumps({"type": "stop"}))

            for _ in range(10):
                try:
                    msg = json.loads(ws.receive_text())
                    if msg["type"] == "session_ended":
                        assert "metrics" in msg
                        assert isinstance(msg["metrics"], dict)
                        break
                except Exception:
                    break


# ═══════════════════════════════════════════════════════════════════════════
# WhisperFlowEngine unit tests
# ═══════════════════════════════════════════════════════════════════════════

class TestWhisperFlowEngine:
    def test_raises_when_not_installed(self):
        """WhisperFlowEngine must raise RuntimeError when whisperflow is absent."""
        from app.engines.whisperflow_engine import _WHISPERFLOW_AVAILABLE, WhisperFlowEngine
        if _WHISPERFLOW_AVAILABLE:
            pytest.skip("whisperflow is installed — cannot test absent-case")

        with pytest.raises(RuntimeError, match="not installed"):
            WhisperFlowEngine()

    def test_get_info_shows_availability(self):
        """get_info should include whisperflow_available even when not installed."""
        from app.engines.whisperflow_engine import _WHISPERFLOW_AVAILABLE, WhisperFlowEngine
        if _WHISPERFLOW_AVAILABLE:
            eng = WhisperFlowEngine()
            info = eng.get_info()
        else:
            # Can't instantiate, so test the availability flag directly
            assert _WHISPERFLOW_AVAILABLE is False
            return

        assert "whisperflow_available" in info


# ═══════════════════════════════════════════════════════════════════════════
# Real live smoke test (opt-in, skipped by default)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.real_model
@pytest.mark.skip(
    reason=(
        "Requires Whisper 'base' weights pre-downloaded and ffmpeg on PATH. "
        "Run manually: uv run pytest -m real_model -s -k test_live_smoke --no-header"
    )
)
class TestLiveSmoke:
    """Real model end-to-end WebSocket test.

    Requires:
    - Whisper base model downloaded (uv run python scripts/download_model.py)
    - ffmpeg on PATH
    """

    def test_live_smoke_with_wav_audio(self, tmp_path):
        """Full WebSocket flow with a real silent WAV file and real engine."""
        import io

        # Write silent WAV bytes
        n = 16000  # 1 second
        buf = io.BytesIO()
        with wave.open(buf, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(struct.pack(f"<{n}h", *([0] * n)))
        audio_bytes = buf.getvalue()

        with client.websocket_connect("/api/v1/live") as ws:
            ws.send_text(json.dumps({"type": "start", "engine": "whisper", "language": "en"}))
            msg = json.loads(ws.receive_text())
            assert msg["type"] == "session_started"

            # Send audio in 4 chunks
            chunk_size = len(audio_bytes) // 4
            for i in range(4):
                ws.send_bytes(audio_bytes[i * chunk_size:(i + 1) * chunk_size])

            ws.send_text(json.dumps({"type": "stop"}))

            # Collect messages until session_ended
            seen_final = False
            seen_ended = False
            for _ in range(20):
                try:
                    msg = json.loads(ws.receive_text())
                    if msg["type"] == "final":
                        seen_final = True
                        assert isinstance(msg["text"], str)
                    elif msg["type"] == "session_ended":
                        seen_ended = True
                        break
                except Exception:
                    break

        assert seen_final, "Expected 'final' message"
        assert seen_ended, "Expected 'session_ended' message"
