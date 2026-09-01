"""
tests/test_stt_real_model.py
─────────────────────────────
End-to-end test with real model weights, over a recording whose speaker
timeline and transcript are known exactly.

Marked ``real_model`` and skipped unless the optional ``stt`` dependencies, the
fixture, and ffmpeg are all present, so a normal CI run is unaffected::

    pytest tests/test_stt_real_model.py -m real_model -v

The fixture is built from mini-LibriSpeech by ``sst_v1/scripts/prepare_diar_testset.py``:
real voices, verified transcripts, and turn boundaries accurate to the sample.

Scope: this asserts *functional correctness* — the right number of speakers,
turns that alternate, text that is actually there, and a persisted job. Accuracy
regression (diarization error rate, word error rate) is measured by the sweep
harness in ``sst_v1/scripts/sweep_diarization.py``, which is the benchmark
surface; duplicating it here would make the backend suite slow and flaky.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from itertools import pairwise
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "sst_v1" / "data" / "diar_testset" / "two_party"
FIXTURE_WAV = FIXTURE_DIR / "two_party.wav"
FIXTURE_JSON = FIXTURE_DIR / "two_party.json"


def _missing_requirements() -> str | None:
    if not FIXTURE_WAV.exists():
        return (
            f"fixture not found at {FIXTURE_WAV}; build it with "
            f"sst_v1/scripts/prepare_diar_testset.py"
        )
    if shutil.which("ffmpeg") is None:
        return "ffmpeg not on PATH"
    for module in ("torch", "speechbrain", "soundfile", "sklearn"):
        if importlib.util.find_spec(module) is None:
            return f"{module} not installed (uv sync --extra stt)"
    if all(importlib.util.find_spec(m) is None for m in ("faster_whisper", "whisper")):
        return "no Whisper backend installed (uv sync --extra stt)"
    return None


_SKIP_REASON = _missing_requirements()

pytestmark = [
    pytest.mark.real_model,
    pytest.mark.skipif(_SKIP_REASON is not None, reason=_SKIP_REASON or ""),
]


@pytest.fixture(scope="module")
def ground_truth() -> dict:
    return json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test client with storage redirected to a temp directory."""
    from fastapi.testclient import TestClient

    from app.core.config import settings

    monkeypatch.setattr(settings, "AUDIO_STORAGE_DIR", str(tmp_path / "audio"))
    monkeypatch.setattr(settings, "STT_ENGINE_MODE", "local")

    from app.main import app

    return TestClient(app)


def _post_diarize(client, path: Path, **form: object):
    with path.open("rb") as handle:
        return client.post(
            "/api/v1/stt/diarize",
            files={"file": (path.name, handle, "audio/wav")},
            data={"num_speakers": "2", **form},
        )


def test_diarize_two_party_recording(client, ground_truth, tmp_path) -> None:
    """The core case: a two-party encounter with the speaker count supplied."""
    response = _post_diarize(
        client,
        FIXTURE_WAV,
        speaker_names=json.dumps({"speaker_0": "Doctor", "speaker_1": "Patient"}),
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["num_speakers"] == ground_truth["num_speakers"] == 2
    assert sorted(body["speakers"]) == ["speaker_0", "speaker_1"]

    # Duration should match the fixture to within the ffmpeg rounding margin.
    assert abs(body["audio"]["duration"] - ground_truth["duration"]) < 0.5

    # A conversation must alternate: consecutive turns cannot share a speaker,
    # since same-speaker runs are merged during alignment.
    speakers = [turn["speaker_id"] for turn in body["turns"]]
    assert all(a != b for a, b in pairwise(speakers))
    assert len(body["turns"]) >= ground_truth["num_speakers"]

    # Turns must be chronological and non-degenerate.
    for previous, current in pairwise(body["turns"]):
        assert current["start"] >= previous["start"]
    for turn in body["turns"]:
        assert turn["end"] > turn["start"]
        assert turn["text"].strip()
        assert turn["speaker_name"] in {"Doctor", "Patient"}

    # Recognisable content from the reference transcript, not just any text.
    transcript = body["text"].upper()
    assert "EARS" in transcript
    assert len(transcript.split()) > 50

    assert body["labelled_text"].startswith(("Doctor:", "Patient:"))
    assert body["engine"]["mode"] == "local"
    assert body["metrics"]["total_rtf"] > 0
    assert body["diagnostics"]["oracle_num_speakers"] == 2


def test_diarized_job_is_persisted(client) -> None:
    """The audio and the result must be retrievable after the request."""
    body = _post_diarize(client, FIXTURE_WAV).json()
    job_id = body["job_id"]

    stored_wav = Path(body["audio"]["stored_path"])
    assert stored_wav.exists()
    assert (stored_wav.parent / "result.json").exists()
    assert (stored_wav.parent / "original.wav").exists()

    fetched = client.get(f"/api/v1/stt/jobs/{job_id}")
    assert fetched.status_code == 200
    assert fetched.json()["text"] == body["text"]

    listing = client.get("/api/v1/stt/jobs").json()
    assert job_id in [job["job_id"] for job in listing["jobs"]]

    assert client.delete(f"/api/v1/stt/jobs/{job_id}").status_code == 200
    assert client.get(f"/api/v1/stt/jobs/{job_id}").status_code == 404
    assert not stored_wav.exists()


def test_save_audio_false_leaves_nothing_behind(client) -> None:
    """Opting out of persistence must not leave PHI on disk."""
    from app.core.config import settings

    body = _post_diarize(client, FIXTURE_WAV, save_audio="false").json()

    assert body["audio"]["stored"] is False
    assert body["audio"]["stored_path"] is None
    assert body["text"].strip()

    storage_root = Path(settings.AUDIO_STORAGE_DIR)
    assert not list(storage_root.glob("*/*")) if storage_root.exists() else True


@pytest.mark.parametrize("target_format", ["mp3", "webm"])
def test_lossy_and_browser_formats_are_transcoded(client, tmp_path, target_format) -> None:
    """Browser WebM/Opus and lossy MP3 must work, since that is what clients send."""
    converted = tmp_path / f"encounter.{target_format}"
    codec = ["-c:a", "libopus"] if target_format == "webm" else ["-c:a", "libmp3lame"]
    subprocess.run(
        ["ffmpeg", "-nostdin", "-y", "-i", str(FIXTURE_WAV), *codec, str(converted)],
        capture_output=True,
        check=True,
        timeout=300,
    )

    response = _post_diarize(client, converted)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["num_speakers"] == 2
    assert "EARS" in body["text"].upper()
    assert body["audio"]["filename"] == converted.name
    assert body["audio"]["sample_rate"] == 16_000


def test_plain_transcription_of_real_audio(client) -> None:
    """``/transcribe`` must serve the unchanged text-only contract locally."""
    with FIXTURE_WAV.open("rb") as handle:
        response = client.post(
            "/api/v1/stt/transcribe",
            files={"file": (FIXTURE_WAV.name, handle, "audio/wav")},
        )
    assert response.status_code == 200, response.text
    body = response.json()

    assert "EARS" in body["text"].upper()
    assert body["segments"]
    assert body["language"].startswith("en")
    assert body["engine"].startswith("local:")
    assert 0 < body["real_time_factor"] < 5


def test_corrupt_audio_is_rejected(client, tmp_path) -> None:
    """A file with an audio extension but no audio must fail cleanly, not 500."""
    fake = tmp_path / "not-really.wav"
    fake.write_bytes(b"this is not audio" * 100)

    response = _post_diarize(client, fake)
    assert response.status_code == 400
    assert "detail" in response.json()


def test_engine_reports_loaded_models(client) -> None:
    """After a real request the engine must report loaded models and a device."""
    _post_diarize(client, FIXTURE_WAV)

    body = client.get("/api/v1/stt/engine").json()
    assert body["mode"] == "local"
    assert body["models_loaded"] is True
    assert body["dependencies_available"] is True
    assert body["device"] in {"cpu"} or body["device"].startswith("cuda")
