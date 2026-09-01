from pathlib import Path

from fastapi.testclient import TestClient

from app.core.errors import ValidationFailed
from app.main import app
from app.modules.generate_soap.parse import parse_soap_markdown, sections_as_list
from app.schemas.api import SoapNoteOut, SoapSectionOut
from app.services import soap_jobs, soap_store
from app.services.soap_store import DEFAULT_ENCOUNTER_ID

client = TestClient(app)

_SOAP_NOTE = Path(__file__).resolve().parents[2] / "soap_create" / "soap_note.md"

_MINI_NOTE = """# MEDICAL SOAP NOTE

Patient Information:
- Name: Gaia

## S – SUBJECTIVE

Fever for four days.

## O – OBJECTIVE

Temperature elevated.

## A – ASSESSMENT

Suspected dengue.

## P – PLAN

Rest and fluids.
"""


def _stub_create(monkeypatch, markdown: str = _MINI_NOTE) -> None:
    soap_jobs.reset_jobs()
    monkeypatch.setattr(soap_jobs, "require_soap_dependencies", lambda: None)
    monkeypatch.setattr(soap_store, "encounter_exists", lambda _id: True)
    monkeypatch.setattr(soap_jobs, "enqueue", soap_jobs.run_job)
    monkeypatch.setattr(
        soap_jobs,
        "detect_entities",
        lambda text: [{"Text": "fever", "Category": "MEDICAL_CONDITION"}],
    )
    monkeypatch.setattr(
        soap_jobs,
        "generate_soap_note",
        lambda entities, user_inputs=None, timeout=None, interval=None: {
            "execution_id": "exec-create",
            "status": "SUCCESS",
            "agent_name": "SOAP Agent",
            "created_at": None,
            "soap_markdown": markdown,
        },
    )

    def fake_persist(encounter_id, markdown_text, sections):
        return SoapNoteOut(
            id="00000000-0000-0000-0000-000000000001",
            status="needs_physician_review",
            soap_markdown=markdown_text,
            sections=[SoapSectionOut(**row) for row in sections],
        )

    monkeypatch.setattr(soap_store, "persist_soap_note", fake_persist)


def test_parse_gold_soap_note() -> None:
    markdown = _SOAP_NOTE.read_text(encoding="utf-8")
    sections = parse_soap_markdown(markdown)
    assert "feeling really unwell" in sections["subjective"]
    assert "Vital Signs" in sections["objective"]
    assert "Dengue" in sections["assessment"]
    assert "Paracetamol" in sections["plan"]
    rows = sections_as_list(sections)
    assert [row["section_type"] for row in rows] == [
        "subjective",
        "objective",
        "assessment",
        "plan",
    ]


def test_parse_preamble_joins_subjective() -> None:
    sections = parse_soap_markdown(_MINI_NOTE)
    assert "Name: Gaia" in sections["subjective"]
    assert "Fever for four days." in sections["subjective"]
    assert sections["objective"] == "Temperature elevated."
    assert sections["plan"] == "Rest and fluids."


def test_parse_without_headings_is_subjective() -> None:
    sections = parse_soap_markdown("Patient reports fever.")
    assert sections["subjective"] == "Patient reports fever."
    assert sections["objective"] == ""
    assert sections["assessment"] == ""
    assert sections["plan"] == ""


def test_soap_create_rejects_blank_transcript() -> None:
    response = client.post("/api/v1/soap/create", json={"transcript": "   "})
    assert response.status_code == 400


def test_soap_create_rejects_bad_encounter_id(monkeypatch) -> None:
    monkeypatch.setattr(soap_jobs, "require_soap_dependencies", lambda: None)
    response = client.post(
        "/api/v1/soap/create",
        json={"transcript": "Doctor: Hello.\nPatient: Hi.", "encounter_id": "not-a-uuid"},
    )
    assert response.status_code == 400


def test_soap_create_unknown_encounter(monkeypatch) -> None:
    monkeypatch.setattr(soap_jobs, "require_soap_dependencies", lambda: None)
    monkeypatch.setattr(soap_store, "encounter_exists", lambda _id: False)
    response = client.post(
        "/api/v1/soap/create",
        json={"transcript": "Doctor: Hello.\nPatient: Hi."},
    )
    assert response.status_code == 404


def test_soap_create_job_completes(monkeypatch) -> None:
    _stub_create(monkeypatch)
    response = client.post(
        "/api/v1/soap/create",
        json={"transcript": "Doctor: What brings you in?\nPatient: Fever for four days."},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "done"
    assert body["encounter_id"] == DEFAULT_ENCOUNTER_ID
    assert body["entity_count"] == 1
    assert body["execution_id"] == "exec-create"
    types = [section["section_type"] for section in body["soap_note"]["sections"]]
    assert types == ["subjective", "objective", "assessment", "plan"]
    by_type = {
        section["section_type"]: section["ai_generated_text"]
        for section in body["soap_note"]["sections"]
    }
    assert "Fever for four days." in by_type["subjective"]
    assert by_type["plan"] == "Rest and fluids."
    assert all(step["status"] == "done" for step in body["steps"])

    polled = client.get(f"/api/v1/soap/jobs/{body['soap_job_id']}")
    assert polled.status_code == 200
    assert polled.json()["soap_note_id"] == "00000000-0000-0000-0000-000000000001"


def test_soap_job_unknown() -> None:
    response = client.get("/api/v1/soap/jobs/does-not-exist")
    assert response.status_code == 404


def test_soap_create_failed_job(monkeypatch) -> None:
    _stub_create(monkeypatch)

    def boom(_text: str):
        raise ValidationFailed("Transcript text is empty.")

    monkeypatch.setattr(soap_jobs, "detect_entities", boom)
    response = client.post(
        "/api/v1/soap/create",
        json={"transcript": "Doctor: Hello.\nPatient: Hi."},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "failed"
    assert body["soap_note"] is None
    assert body["error"]["code"] == "validation_failed"
    extracting = next(step for step in body["steps"] if step["id"] == "extracting")
    assert extracting["status"] == "failed"


def test_get_note_and_encounter(monkeypatch) -> None:
    note = SoapNoteOut(
        id="00000000-0000-0000-0000-000000000001",
        status="needs_physician_review",
        soap_markdown=_MINI_NOTE,
        sections=sections_as_list(parse_soap_markdown(_MINI_NOTE)),
    )
    monkeypatch.setattr(soap_store, "get_soap_note", lambda _id: note)
    monkeypatch.setattr(soap_store, "get_soap_note_by_encounter", lambda _id: note)

    by_id = client.get("/api/v1/soap/notes/00000000-0000-0000-0000-000000000001")
    assert by_id.status_code == 200
    assert by_id.json()["sections"][3]["section_type"] == "plan"

    by_enc = client.get(f"/api/v1/soap/encounters/{DEFAULT_ENCOUNTER_ID}")
    assert by_enc.status_code == 200
    assert "Fever" in by_enc.json()["sections"][0]["ai_generated_text"]
