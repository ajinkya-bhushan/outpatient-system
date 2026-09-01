from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready_reports_modules() -> None:
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["modules"] == ["stt", "diarization", "medical_comprehend", "generate_soap"]
