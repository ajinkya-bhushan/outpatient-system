"""
tests/test_stt_diarization.py
──────────────────────────────
Fast tests for the STT + diarization module. No model weights are loaded, so
this suite runs in CI without a GPU or a network.

Covers upload validation, local storage layout, word-to-speaker alignment,
speaker-count resolution, engine-mode dispatch, and the response contract.
The real-model integration test lives in ``test_stt_real_model.py``.
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.errors import ConfigurationError, ValidationFailed
from app.main import app

client = TestClient(app)


@pytest.fixture
def storage_dir(tmp_path, monkeypatch):
    """Point audio storage at a temp directory for the duration of a test."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "AUDIO_STORAGE_DIR", str(tmp_path / "audio"))
    return tmp_path / "audio"


def write_silent_wav(path: Path, seconds: float = 1.0, sample_rate: int = 16_000) -> Path:
    """Write a valid but silent 16-bit mono WAV. Enough to exercise plumbing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * int(seconds * sample_rate))
    return path


# ── Upload validation ─────────────────────────────────────────────────────────


def test_empty_upload_rejected() -> None:
    from app.modules.stt.local.audio import validate_upload

    with pytest.raises(ValidationFailed, match="empty"):
        validate_upload("encounter.wav", 0)


def test_unsupported_extension_rejected() -> None:
    from app.modules.stt.local.audio import validate_upload

    with pytest.raises(ValidationFailed, match="Unsupported audio format"):
        validate_upload("encounter.txt", 1024)


def test_missing_extension_rejected() -> None:
    from app.modules.stt.local.audio import validate_upload

    with pytest.raises(ValidationFailed, match="Cannot determine audio format"):
        validate_upload("encounter", 1024)


def test_oversize_upload_rejected() -> None:
    from app.core.config import settings
    from app.modules.stt.local.audio import validate_upload

    with pytest.raises(ValidationFailed, match="exceeds"):
        validate_upload("encounter.wav", settings.max_audio_size_bytes + 1)


def test_browser_and_phone_formats_accepted() -> None:
    from app.modules.stt.local.audio import validate_upload

    assert validate_upload("recording.webm", 2048) == ".webm"
    assert validate_upload("voice memo.m4a", 2048) == ".m4a"
    assert validate_upload("UPPER.WAV", 2048) == ".wav"


def test_over_duration_rejected(monkeypatch) -> None:
    from app.core.config import settings
    from app.modules.stt.local.audio import validate_duration

    monkeypatch.setattr(settings, "MAX_AUDIO_DURATION_SECONDS", 60)
    validate_duration(59.0)
    with pytest.raises(ValidationFailed, match="exceeds"):
        validate_duration(61.0)


def test_transcribe_endpoint_requires_a_file() -> None:
    assert client.post("/api/v1/stt/transcribe").status_code == 422


def test_diarize_endpoint_requires_a_file() -> None:
    assert client.post("/api/v1/stt/diarize").status_code == 422


# ── Form-field parsing ────────────────────────────────────────────────────────


def test_speaker_names_parsing() -> None:
    from app.api.routes_stt import _parse_speaker_names

    assert _parse_speaker_names("") is None
    assert _parse_speaker_names('{"speaker_0": "Doctor"}') == {"speaker_0": "Doctor"}

    with pytest.raises(ValidationFailed, match="JSON object"):
        _parse_speaker_names("not json")
    with pytest.raises(ValidationFailed, match="string to string"):
        _parse_speaker_names('{"speaker_0": 1}')
    with pytest.raises(ValidationFailed, match="string to string"):
        _parse_speaker_names('["speaker_0"]')


def test_optional_int_parsing() -> None:
    from app.api.routes_stt import _parse_optional_int

    assert _parse_optional_int("", "num_speakers") is None
    assert _parse_optional_int("3", "num_speakers") == 3
    with pytest.raises(ValidationFailed, match="must be an integer"):
        _parse_optional_int("two", "num_speakers")


# ── Speaker-count resolution ──────────────────────────────────────────────────


def test_speaker_count_resolution(monkeypatch) -> None:
    """Explicit request wins; blank uses the configured default; 0 means auto."""
    from app.core.config import settings
    from app.modules.stt.local.runner import resolve_num_speakers

    monkeypatch.setattr(settings, "DIARIZATION_NUM_SPEAKERS", 2)
    assert resolve_num_speakers(None) == 2
    assert resolve_num_speakers(3) == 3
    assert resolve_num_speakers(0) is None

    monkeypatch.setattr(settings, "DIARIZATION_NUM_SPEAKERS", None)
    assert resolve_num_speakers(None) is None


# ── Local storage ─────────────────────────────────────────────────────────────


def test_storage_writes_job_directory(storage_dir) -> None:
    from app.modules.stt.local import storage

    stored = storage.save_upload(b"fake audio bytes", ".wav")

    assert stored.original_path.read_bytes() == b"fake audio bytes"
    assert stored.original_path.name == "original.wav"
    assert stored.wav_path.name == "audio.wav"
    # Dated parent directory, so retention can be reasoned about by date.
    assert stored.job_dir.parent.name.count("-") == 2
    assert storage_dir in stored.job_dir.parents


def test_storage_roundtrip_and_listing(storage_dir) -> None:
    from app.modules.stt.local import storage

    stored = storage.save_upload(b"bytes", ".wav")
    storage.save_result(stored, {"job_id": stored.job_id, "language": "en", "num_speakers": 2})

    assert storage.load_result(stored.job_id)["num_speakers"] == 2
    assert storage.load_result("does-not-exist") is None

    jobs, total = storage.list_jobs()
    assert total == 1
    assert jobs[0]["job_id"] == stored.job_id
    assert jobs[0]["num_speakers"] == 2
    # Summaries must not leak transcript text.
    assert "text" not in jobs[0]


def test_storage_delete(storage_dir) -> None:
    from app.modules.stt.local import storage

    stored = storage.save_upload(b"bytes", ".wav")
    assert storage.delete_job(stored.job_id) is True
    assert storage.find_job_dir(stored.job_id) is None
    assert storage.delete_job(stored.job_id) is False


def test_job_id_must_be_uuid_hex(storage_dir) -> None:
    from app.modules.stt.local import storage

    assert storage.is_valid_job_id("0" * 32) is True
    # A glob wildcard would otherwise match a *different* patient's directory,
    # and "../" would climb out of the storage root entirely.
    for hostile in ("*", "?" * 32, "../" + "a" * 29, "0" * 31, "0" * 33, "", "A" * 32):
        assert storage.is_valid_job_id(hostile) is False
        assert storage.find_job_dir(hostile) is None
        assert storage.load_result(hostile) is None
        assert storage.job_audio_path(hostile) is None
        assert storage.delete_job(hostile) is False


def test_job_audio_path_finds_converted_wav(storage_dir) -> None:
    from app.modules.stt.local import storage

    stored = storage.save_upload(b"bytes", ".mp3")
    # Only the original exists until conversion runs.
    assert storage.job_audio_path(stored.job_id) is None

    write_silent_wav(stored.wav_path)
    assert storage.job_audio_path(stored.job_id) == stored.wav_path


# ── Job audio endpoint ────────────────────────────────────────────────────────


def test_get_job_audio_serves_wav(storage_dir) -> None:
    from app.modules.stt.local import storage

    stored = storage.save_upload(b"bytes", ".wav")
    write_silent_wav(stored.wav_path, seconds=0.5)

    response = client.get(f"/api/v1/stt/jobs/{stored.job_id}/audio")

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == stored.wav_path.read_bytes()
    # PHI must not be cached by a shared proxy or written to disk.
    assert "no-store" in response.headers["cache-control"]


def test_get_job_audio_supports_range_requests(storage_dir) -> None:
    """Per-turn playback seeks into the file, so Range must work."""
    from app.modules.stt.local import storage

    stored = storage.save_upload(b"bytes", ".wav")
    write_silent_wav(stored.wav_path, seconds=0.5)

    response = client.get(
        f"/api/v1/stt/jobs/{stored.job_id}/audio",
        headers={"Range": "bytes=0-99"},
    )

    assert response.status_code == 206
    assert len(response.content) == 100


def test_get_job_audio_404_when_missing(storage_dir) -> None:
    from app.modules.stt.local import storage

    unknown = storage.new_job_id()
    assert client.get(f"/api/v1/stt/jobs/{unknown}/audio").status_code == 404

    # Job exists but was uploaded with save_audio=false, so there is no WAV.
    stored = storage.save_upload(b"bytes", ".wav")
    assert client.get(f"/api/v1/stt/jobs/{stored.job_id}/audio").status_code == 404


def test_get_job_audio_rejects_wildcard_job_id(storage_dir) -> None:
    """A bare "*" would glob-match the first stored job of any encounter."""
    from app.modules.stt.local import storage

    stored = storage.save_upload(b"someone elses audio", ".wav")
    write_silent_wav(stored.wav_path)

    response = client.get("/api/v1/stt/jobs/*/audio")

    assert response.status_code == 404


def test_list_jobs_on_empty_storage(storage_dir) -> None:
    from app.modules.stt.local import storage

    assert storage.list_jobs() == ([], 0)


def test_get_unknown_job_returns_404(storage_dir) -> None:
    assert client.get("/api/v1/stt/jobs/nope").status_code == 404


def test_delete_unknown_job_returns_404(storage_dir) -> None:
    assert client.delete("/api/v1/stt/jobs/nope").status_code == 404


def test_job_listing_endpoint(storage_dir) -> None:
    from app.modules.stt.local import storage

    stored = storage.save_upload(b"bytes", ".wav")
    storage.save_result(stored, {"job_id": stored.job_id, "text": "secret", "num_speakers": 2})

    listing = client.get("/api/v1/stt/jobs").json()
    assert listing["total"] == 1
    assert listing["jobs"][0]["job_id"] == stored.job_id

    fetched = client.get(f"/api/v1/stt/jobs/{stored.job_id}").json()
    assert fetched["text"] == "secret"


# ── Word-to-speaker alignment ─────────────────────────────────────────────────


def _make_diarization(segments):
    from app.modules.stt.local.diarizer import DiarizationResult, SpeakerSegment

    return DiarizationResult(
        segments=[SpeakerSegment(start=s, end=e, speaker=spk) for s, e, spk in segments],
        num_speakers=len({spk for *_, spk in segments}),
        audio_duration=segments[-1][1] if segments else 0.0,
        speech_duration=sum(e - s for s, e, _ in segments),
        processing_time=0.1,
    )


def _make_transcription(words):
    from app.modules.stt.local.transcribe import TranscriptionResult, Word

    return TranscriptionResult(
        text=" ".join(text for *_, text in words),
        language="en",
        words=[Word(start=s, end=e, text=text, probability=0.9) for s, e, text in words],
        audio_duration=words[-1][1] if words else 0.0,
        processing_time=0.1,
        backend="stub",
        model="stub",
    )


def test_alignment_groups_words_into_speaker_turns() -> None:
    from app.modules.stt.local.alignment import build_speaker_turns

    diarization = _make_diarization([(0.0, 2.0, "speaker_0"), (2.0, 4.0, "speaker_1")])
    transcription = _make_transcription(
        [(0.1, 0.5, "Any"), (0.6, 1.0, "fever?"), (2.1, 2.5, "Yes,"), (2.6, 3.0, "three days.")]
    )

    turns = build_speaker_turns(transcription, diarization)

    assert [turn.speaker for turn in turns] == ["speaker_0", "speaker_1"]
    assert turns[0].text == "Any fever?"
    assert turns[1].text == "Yes, three days."


def test_alignment_switches_speaker_mid_whisper_segment() -> None:
    """A speaker change inside one Whisper segment must still split the turn."""
    from app.modules.stt.local.alignment import build_speaker_turns

    diarization = _make_diarization([(0.0, 1.0, "speaker_0"), (1.0, 2.0, "speaker_1")])
    transcription = _make_transcription(
        [(0.1, 0.4, "Any"), (0.5, 0.9, "fever?"), (1.1, 1.4, "Yes"), (1.5, 1.9, "doctor")]
    )

    turns = build_speaker_turns(transcription, diarization)
    assert len(turns) == 2
    assert turns[0].speaker != turns[1].speaker


def test_alignment_assigns_by_maximum_overlap() -> None:
    """A word straddling a boundary goes to whichever speaker covers more of it."""
    from app.modules.stt.local.alignment import assign_speaker_to_word
    from app.modules.stt.local.transcribe import Word

    segments = _make_diarization([(0.0, 1.0, "speaker_0"), (1.0, 3.0, "speaker_1")]).segments

    assert assign_speaker_to_word(Word(0.8, 1.6, "hmm"), segments) == "speaker_1"
    assert assign_speaker_to_word(Word(0.2, 1.1, "hmm"), segments) == "speaker_0"


def test_alignment_keeps_unattributable_words() -> None:
    """Words far from any segment are labelled unknown, never dropped."""
    from app.modules.stt.local.alignment import UNKNOWN_SPEAKER, build_speaker_turns

    diarization = _make_diarization([(0.0, 1.0, "speaker_0")])
    transcription = _make_transcription([(0.1, 0.5, "Hello"), (30.0, 30.4, "artefact")])

    turns = build_speaker_turns(transcription, diarization)

    assert [turn.speaker for turn in turns] == ["speaker_0", UNKNOWN_SPEAKER]
    assert "artefact" in turns[-1].text


def test_alignment_applies_speaker_names() -> None:
    from app.modules.stt.local.alignment import build_speaker_turns, format_transcript

    diarization = _make_diarization([(0.0, 1.0, "speaker_0"), (1.0, 2.0, "speaker_1")])
    transcription = _make_transcription([(0.1, 0.5, "Hello"), (1.1, 1.5, "Hi")])

    turns = build_speaker_turns(
        transcription,
        diarization,
        speaker_names={"speaker_0": "Doctor", "speaker_1": "Patient"},
    )

    assert format_transcript(turns, with_times=False) == "Doctor: Hello\nPatient: Hi"


def test_alignment_with_no_words_returns_no_turns() -> None:
    from app.modules.stt.local.alignment import build_speaker_turns

    diarization = _make_diarization([(0.0, 1.0, "speaker_0")])
    assert build_speaker_turns(_make_transcription([]), diarization) == []


# ── Sub-segmentation ──────────────────────────────────────────────────────────


def test_subsegmentation_covers_regions_with_overlap() -> None:
    from app.modules.stt.local.embeddings import build_subsegments

    subsegs = build_subsegments(
        [(0.0, 4.0)], window_sec=1.5, shift_sec=0.75, min_subseg_sec=0.5
    )

    assert len(subsegs) > 1
    assert subsegs[0].start == 0.0
    assert subsegs[-1].end == 4.0
    # Overlapping by design: consecutive windows must share audio.
    assert subsegs[1].start < subsegs[0].end


def test_short_region_yields_one_subsegment() -> None:
    """A brief back-channel turn must not be silently discarded."""
    from app.modules.stt.local.embeddings import build_subsegments

    subsegs = build_subsegments(
        [(1.0, 1.8)], window_sec=1.5, shift_sec=0.75, min_subseg_sec=0.5
    )
    assert len(subsegs) == 1
    assert (subsegs[0].start, subsegs[0].end) == (1.0, 1.8)


def test_regions_below_minimum_are_dropped() -> None:
    from app.modules.stt.local.embeddings import build_subsegments

    assert build_subsegments([(1.0, 1.2)], 1.5, 0.75, 0.5) == []


# ── Engine mode dispatch ──────────────────────────────────────────────────────


def test_local_mode_rejects_live_streaming(monkeypatch) -> None:
    from app.modules.stt.service import STTService

    with pytest.raises(ConfigurationError, match="not implemented for the local"):
        STTService(mode="local").live_url()


def test_missing_dependencies_report_503_not_500(storage_dir, tmp_path, monkeypatch) -> None:
    """A deployment without the ``stt`` extra must say so, not fail opaquely.

    ``alignment`` is blocked here as a stand-in for the whole extra being
    absent: the engine's dependency check has to run before anything that
    imports it, or the caller gets a bare ImportError as a 500.
    """
    import sys

    from app.modules.stt.local.engine import LocalSTTEngine

    monkeypatch.setattr(
        LocalSTTEngine,
        "dependencies_available",
        staticmethod(lambda: (False, "Local STT dependencies are not installed: torch.")),
    )
    monkeypatch.setitem(sys.modules, "app.modules.stt.local.alignment", None)

    wav = write_silent_wav(tmp_path / "encounter.wav")
    with wav.open("rb") as handle:
        response = client.post(
            "/api/v1/stt/diarize",
            files={"file": ("encounter.wav", handle, "audio/wav")},
        )

    assert response.status_code == 503
    assert "not installed" in response.json()["detail"]


def test_remote_mode_builds_websocket_url() -> None:
    from app.modules.stt.service import STTService

    assert STTService(mode="remote").live_url().startswith("ws://")


async def test_remote_mode_rejects_diarization() -> None:
    from app.modules.stt.service import STTService

    with pytest.raises(ConfigurationError, match="requires STT_ENGINE_MODE=local"):
        await STTService(mode="remote").diarize_upload(b"bytes", "a.wav")


async def test_local_mode_rejects_translation() -> None:
    from app.modules.stt.local import runner

    with pytest.raises(ValidationFailed, match="transcribe"):
        await runner.transcribe(b"bytes", "a.wav", task="translate")


async def test_pipeline_upload_seam_is_unchanged(monkeypatch) -> None:
    """``/pipeline/upload`` must keep working through the facade.

    The whole point of routing local inference through ``STTService`` was that
    the pipeline route needs no changes, so pin the call signature it relies on.
    """
    from app.modules.stt.schemas import TranscriptResult
    from app.modules.stt.service import STTService
    from app.services import pipeline as pipeline_service

    captured: dict[str, object] = {}

    async def fake_transcribe_upload(self, **kwargs):
        captured.update(kwargs)
        return TranscriptResult(text="Patient has fever.", language="en")

    monkeypatch.setattr(STTService, "transcribe_upload", fake_transcribe_upload)
    monkeypatch.setattr(
        pipeline_service,
        "build_aava_payload",
        lambda text: {
            "entities": [{"Text": "fever", "Category": "MEDICAL_CONDITION"}],
            "icd10": [],
            "rxnorm": [],
        },
    )
    monkeypatch.setattr(
        pipeline_service,
        "generate_soap_note",
        lambda entities, user_inputs=None, timeout=None, interval=None: {
            "execution_id": "exec-1",
            "status": "SUCCESS",
            "agent_name": "SOAP Agent",
            "created_at": None,
            "soap_markdown": "## P – PLAN\nRest.",
        },
    )

    response = client.post(
        "/api/v1/pipeline/upload",
        files={"file": ("encounter.wav", b"bytes", "audio/wav")},
        data={"language": "en"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["transcript"]["text"] == "Patient has fever."
    assert captured["filename"] == "encounter.wav"
    assert captured["file_bytes"] == b"bytes"
    assert captured["language"] == "en"


def test_engine_endpoint_reports_mode() -> None:
    body = client.get("/api/v1/stt/engine").json()

    assert body["mode"] in {"local", "remote"}
    assert "device" in body
    assert isinstance(body["dependencies_available"], bool)


def test_ready_endpoint_reports_stt_engine() -> None:
    body = client.get("/api/v1/ready").json()

    assert body["status"] == "ready"
    assert "stt_engine" in body
    assert "diarization" in body["modules"]


# ── Response contract ─────────────────────────────────────────────────────────


def test_transcript_result_stays_backwards_compatible() -> None:
    """app.models and app.services.pipeline construct this with old fields only."""
    from app.modules.stt.schemas import TranscriptResult

    result = TranscriptResult(text="hello")

    assert result.language == "unknown"
    assert result.segments == []
    assert result.source == "upload"
    # Additive fields default to None rather than becoming required.
    assert result.job_id is None
    assert result.num_speakers is None


def test_diarized_response_serialises() -> None:
    from app.modules.stt.schemas import (
        AudioMeta,
        DiarizedTranscriptResponse,
        EngineInfo,
        ProcessingMetrics,
        SpeakerTurnOut,
    )

    response = DiarizedTranscriptResponse(
        job_id="abc123",
        created_at="2026-08-27T00:00:00+00:00",
        text="Any fever? Yes.",
        labelled_text="Doctor: Any fever?\nPatient: Yes.",
        language="en",
        num_speakers=2,
        speakers=["speaker_0", "speaker_1"],
        turns=[
            SpeakerTurnOut(
                speaker_id="speaker_0",
                speaker_name="Doctor",
                start=0.0,
                end=1.0,
                text="Any fever?",
                confidence=0.9,
            )
        ],
        segments=[],
        audio=AudioMeta(filename="a.wav", duration=2.0, size_bytes=100, stored=True),
        metrics=ProcessingMetrics(audio_duration=2.0),
        engine=EngineInfo(
            mode="local",
            device="cpu",
            whisper_backend="faster_whisper",
            whisper_model="small.en",
        ),
    )

    payload = json.loads(response.model_dump_json())
    assert payload["turns"][0]["speaker_name"] == "Doctor"
    assert payload["metrics"]["stage_times"]["vad"] == 0.0
    assert payload["diagnostics"]["unknown_speaker_words"] == 0


def test_openapi_documents_the_stt_contract() -> None:
    """The endpoints must appear in the generated OpenAPI schema."""
    spec = app.openapi()

    for path in (
        "/api/v1/stt/transcribe",
        "/api/v1/stt/diarize",
        "/api/v1/stt/engine",
        "/api/v1/stt/jobs",
        "/api/v1/stt/jobs/{job_id}",
    ):
        assert path in spec["paths"], f"{path} missing from OpenAPI schema"

    assert "DiarizedTranscriptResponse" in spec["components"]["schemas"]
