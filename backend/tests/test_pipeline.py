from fastapi.testclient import TestClient

from app.core.errors import ValidationFailed
from app.main import app

client = TestClient(app)


def test_empty_transcript_rejected() -> None:
    response = client.post("/api/v1/comprehend/entities", json={"text": ""})
    assert response.status_code == 422


def test_comprehend_returns_entities(monkeypatch) -> None:
    from app.services import pipeline as pipeline_service

    def fake_detect(text: str):
        assert "fever" in text
        return [
            {
                "Id": 1,
                "Text": "fever",
                "Category": "MEDICAL_CONDITION",
                "Type": "DX_NAME",
                "Score": 0.9,
            }
        ]

    monkeypatch.setattr(pipeline_service, "detect_entities", fake_detect)
    response = client.post(
        "/api/v1/comprehend/entities",
        json={"text": "Patient reports high fever for four days."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["entity_count"] == 1
    assert body["category_counts"]["MEDICAL_CONDITION"] == 1
    assert body["entities"][0]["Text"] == "fever"


def test_soap_requires_entities() -> None:
    response = client.post("/api/v1/soap/generate", json={})
    assert response.status_code == 400


def test_soap_generate(monkeypatch) -> None:
    from app.services import pipeline as pipeline_service

    def fake_generate(entities, user_inputs=None, timeout=None, interval=None):
        assert entities
        return {
            "execution_id": "exec-1",
            "status": "SUCCESS",
            "agent_name": "SOAP Agent",
            "created_at": "2026-08-21T00:00:00Z",
            "soap_markdown": "# MEDICAL SOAP NOTE\n\n## S – SUBJECTIVE\nFever for four days.",
        }

    monkeypatch.setattr(pipeline_service, "generate_soap_note", fake_generate)
    response = client.post(
        "/api/v1/soap/generate",
        json={"entities": [{"Text": "fever", "Category": "MEDICAL_CONDITION"}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert "SUBJECTIVE" in body["soap_markdown"]


def test_pipeline_from_text(monkeypatch) -> None:
    from app.services import pipeline as pipeline_service

    monkeypatch.setattr(
        pipeline_service,
        "detect_entities",
        lambda text: [{"Text": "fever", "Category": "MEDICAL_CONDITION"}],
    )
    monkeypatch.setattr(
        pipeline_service,
        "generate_soap_note",
        lambda entities, user_inputs=None, timeout=None, interval=None: {
            "execution_id": "exec-2",
            "status": "SUCCESS",
            "agent_name": "SOAP Agent",
            "created_at": None,
            "soap_markdown": "## P – PLAN\nRest and fluids.",
        },
    )
    response = client.post(
        "/api/v1/pipeline",
        json={"transcript": "Patient has fever.", "source": "text"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["transcript"]["text"] == "Patient has fever."
    assert body["entity_count"] == 1
    assert "PLAN" in body["soap"]["soap_markdown"]


def test_detect_entities_rejects_blank() -> None:
    from app.modules.medical_comprehend.app import detect_entities

    try:
        detect_entities("   ")
        assert False, "expected ValidationFailed"
    except ValidationFailed:
        pass


def test_comprehend_client_passes_settings_credentials(monkeypatch) -> None:
    from app.core import config
    from app.modules.medical_comprehend import app as comprehend

    captured: dict = {}

    def fake_client(service_name, **kwargs):
        captured["service"] = service_name
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(comprehend, "boto3", type("Boto", (), {"client": staticmethod(fake_client)}))
    monkeypatch.setattr(config.settings, "AWS_ACCESS_KEY_ID", "AKIATEST")
    monkeypatch.setattr(config.settings, "AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setattr(config.settings, "AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setattr(config.settings, "AWS_SESSION_TOKEN", None)

    comprehend._client()
    assert captured["service"] == "comprehendmedical"
    assert captured["kwargs"]["aws_access_key_id"] == "AKIATEST"
    assert captured["kwargs"]["aws_secret_access_key"] == "secret"
    assert captured["kwargs"]["region_name"] == "us-east-1"
    assert "aws_session_token" not in captured["kwargs"]
