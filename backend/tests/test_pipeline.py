from fastapi.testclient import TestClient

from app.core.errors import ValidationFailed
from app.main import app

client = TestClient(app)


def test_empty_transcript_rejected() -> None:
    response = client.post("/api/v1/comprehend/entities", json={"text": ""})
    assert response.status_code == 422
    response = client.post("/api/v1/comprehend/icd10", json={"text": ""})
    assert response.status_code == 422
    response = client.post("/api/v1/comprehend/rxnorm", json={"text": ""})
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

    captured: dict = {}

    monkeypatch.setattr(
        pipeline_service,
        "build_aava_payload",
        lambda text: {
            "entities": [{"Text": "fever", "Category": "MEDICAL_CONDITION"}],
            "icd10": [
                {
                    "text": "fever",
                    "code": "R50.9",
                    "description": "Fever, unspecified",
                    "confidence": 0.7,
                }
            ],
            "rxnorm": [],
        },
    )
    monkeypatch.setattr(
        pipeline_service,
        "generate_soap_note",
        lambda entities, user_inputs=None, timeout=None, interval=None: captured.update(
            payload=entities
        )
        or {
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
    assert captured["payload"]["icd10"][0]["code"] == "R50.9"
    assert captured["payload"]["icd10"][0]["confidence"] == 0.7


def test_detect_entities_rejects_blank() -> None:
    from app.modules.medical_comprehend.app import detect_entities

    try:
        detect_entities("   ")
        assert False, "expected ValidationFailed"
    except ValidationFailed:
        pass


def test_infer_icd10_rejects_blank() -> None:
    from app.modules.medical_comprehend.app import infer_icd10

    try:
        infer_icd10("   ")
        assert False, "expected ValidationFailed"
    except ValidationFailed:
        pass


def test_infer_icd10_returns_concepts(monkeypatch) -> None:
    from app.modules.medical_comprehend import app as comprehend

    class FakeClient:
        def infer_icd10_cm(self, **kwargs):
            assert kwargs["Text"] == "Patient reports high fever for four days."
            assert "PaginationToken" not in kwargs
            return {
                "Entities": [
                    {
                        "Id": 0,
                        "Text": "fever",
                        "Category": "MEDICAL_CONDITION",
                        "Type": "DX_NAME",
                        "Score": 0.99,
                        "BeginOffset": 22,
                        "EndOffset": 27,
                        "Traits": [{"Name": "SYMPTOM", "Score": 0.9}],
                        "ICD10CMConcepts": [
                            {
                                "Description": "Fever, unspecified",
                                "Code": "R50.9",
                                "Score": 0.8,
                            }
                        ],
                    }
                ],
                "ModelVersion": "3.1.0",
            }

    monkeypatch.setattr(comprehend, "_client", lambda: FakeClient())
    response = client.post(
        "/api/v1/comprehend/icd10",
        json={"text": "Patient reports high fever for four days."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ModelVersion"] == "3.1.0"
    assert body["PaginationToken"] is None
    entity = body["Entities"][0]
    assert entity["Text"] == "fever"
    assert entity["Category"] == "MEDICAL_CONDITION"
    assert entity["ICD10CMConcepts"][0]["Code"] == "R50.9"


def test_infer_icd10_follows_pagination_and_offsets(monkeypatch) -> None:
    from app.modules.medical_comprehend import app as comprehend

    calls: list[dict] = []

    class FakeClient:
        def infer_icd10_cm(self, **kwargs):
            calls.append(kwargs)
            if "PaginationToken" not in kwargs:
                return {
                    "Entities": [
                        {
                            "Id": 0,
                            "Text": "fever",
                            "BeginOffset": 0,
                            "EndOffset": 5,
                            "Attributes": [
                                {
                                    "Type": "ACUITY",
                                    "BeginOffset": 6,
                                    "EndOffset": 10,
                                    "Text": "high",
                                }
                            ],
                            "ICD10CMConcepts": [{"Code": "R50.9", "Description": "Fever", "Score": 0.7}],
                        }
                    ],
                    "PaginationToken": "page-2",
                    "ModelVersion": "3.1.0",
                }
            assert kwargs["PaginationToken"] == "page-2"
            return {
                "Entities": [
                    {
                        "Id": 1,
                        "Text": "cough",
                        "BeginOffset": 12,
                        "EndOffset": 17,
                        "ICD10CMConcepts": [{"Code": "R05.9", "Description": "Cough", "Score": 0.6}],
                    }
                ],
                "ModelVersion": "3.1.0",
            }

    monkeypatch.setattr(comprehend, "_client", lambda: FakeClient())
    result = comprehend.infer_icd10("fever high cough")
    assert len(calls) == 2
    assert result["PaginationToken"] is None
    assert [entity["Text"] for entity in result["Entities"]] == ["fever", "cough"]
    assert result["Entities"][0]["Attributes"][0]["BeginOffset"] == 6
    assert result["Entities"][1]["BeginOffset"] == 12


def test_infer_rx_norm_rejects_blank() -> None:
    from app.modules.medical_comprehend.app import infer_rx_norm

    try:
        infer_rx_norm("   ")
        assert False, "expected ValidationFailed"
    except ValidationFailed:
        pass


def test_infer_rx_norm_returns_concepts(monkeypatch) -> None:
    from app.modules.medical_comprehend import app as comprehend

    class FakeClient:
        def infer_rx_norm(self, **kwargs):
            assert kwargs["Text"] == "Start paracetamol 650 mg every 6 hours."
            assert "PaginationToken" not in kwargs
            return {
                "Entities": [
                    {
                        "Id": 0,
                        "Text": "paracetamol",
                        "Category": "MEDICATION",
                        "Type": "GENERIC_NAME",
                        "Score": 0.99,
                        "BeginOffset": 6,
                        "EndOffset": 17,
                        "Attributes": [
                            {
                                "Type": "DOSAGE",
                                "Score": 0.95,
                                "BeginOffset": 18,
                                "EndOffset": 24,
                                "Text": "650 mg",
                            }
                        ],
                        "RxNormConcepts": [
                            {
                                "Description": "acetaminophen",
                                "Code": "161",
                                "Score": 0.88,
                            }
                        ],
                    }
                ],
                "ModelVersion": "3.1.0",
            }

    monkeypatch.setattr(comprehend, "_client", lambda: FakeClient())
    response = client.post(
        "/api/v1/comprehend/rxnorm",
        json={"text": "Start paracetamol 650 mg every 6 hours."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ModelVersion"] == "3.1.0"
    assert body["PaginationToken"] is None
    entity = body["Entities"][0]
    assert entity["Text"] == "paracetamol"
    assert entity["Category"] == "MEDICATION"
    assert entity["Type"] == "GENERIC_NAME"
    assert entity["RxNormConcepts"][0]["Code"] == "161"
    assert entity["Attributes"][0]["Type"] == "DOSAGE"


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


def test_build_aava_payload_includes_codes_with_confidence(monkeypatch) -> None:
    from app.modules.medical_comprehend import app as comprehend

    monkeypatch.setattr(
        comprehend,
        "detect_entities",
        lambda text: [{"Text": "fever", "Category": "MEDICAL_CONDITION"}],
    )
    monkeypatch.setattr(
        comprehend,
        "infer_icd10",
        lambda text: {
            "Entities": [
                {
                    "Text": "fever",
                    "Type": "DX_NAME",
                    "Score": 0.9,
                    "Traits": [{"Name": "SYMPTOM", "Score": 0.8}],
                    "ICD10CMConcepts": [
                        {"Code": "R50.8", "Description": "Other specified fever", "Score": 0.1},
                        {"Code": "R50.9", "Description": "Fever, unspecified", "Score": 0.7},
                    ],
                }
            ]
        },
    )
    monkeypatch.setattr(
        comprehend,
        "infer_rx_norm",
        lambda text: {
            "Entities": [
                {
                    "Text": "aspirin",
                    "Type": "GENERIC_NAME",
                    "Score": 0.8,
                    "Attributes": [{"Type": "DOSAGE", "Text": "81 mg"}],
                    "RxNormConcepts": [
                        {"Code": "1191", "Description": "aspirin", "Score": 0.75},
                    ],
                }
            ]
        },
    )

    payload = comprehend.build_aava_payload("Patient took aspirin for fever.")
    assert payload["entities"][0]["Text"] == "fever"
    assert payload["icd10"][0]["code"] == "R50.9"
    assert payload["icd10"][0]["confidence"] == 0.7
    assert payload["icd10"][0]["entity_confidence"] == 0.9
    assert payload["icd10"][0]["negated"] is False
    assert payload["rxnorm"][0]["code"] == "1191"
    assert payload["rxnorm"][0]["confidence"] == 0.75
    assert payload["rxnorm"][0]["attributes"][0] == {"type": "DOSAGE", "text": "81 mg"}
