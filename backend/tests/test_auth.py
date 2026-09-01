from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.api.routes_auth import get_auth_service
from app.core.security import hash_password
from app.main import app
from app.services.auth import AuthService, AuthUser

client = TestClient(app)

PHYSICIAN_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
PASSWORD = "Smith#2026"


class InMemoryUsers:
    def __init__(self, users: list[AuthUser]) -> None:
        self._users = users

    def get_by_provider_id(self, provider_id: str) -> AuthUser | None:
        return next((user for user in self._users if user.provider_id == provider_id), None)

    def get_by_id(self, user_id: uuid.UUID) -> AuthUser | None:
        return next((user for user in self._users if user.id == user_id), None)


def _physician(**overrides: object) -> AuthUser:
    data: dict[str, object] = {
        "id": PHYSICIAN_ID,
        "provider_id": "DR-SMITH",
        "role": "Physician",
        "display_name": "Dr. Smith",
        "password_hash": hash_password(PASSWORD),
        "is_active": True,
    }
    data.update(overrides)
    return AuthUser(**data)  # type: ignore[arg-type]


def _override(users: list[AuthUser]) -> None:
    service = AuthService(InMemoryUsers(users))
    app.dependency_overrides[get_auth_service] = lambda: service


def setup_function() -> None:
    _override([_physician()])


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_login_success() -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"provider_id": "DR-SMITH", "password": PASSWORD, "role": "Physician"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 28800
    assert body["token"]
    assert body["user"]["provider_id"] == "DR-SMITH"
    assert body["user"]["role"] == "Physician"
    assert body["user"]["display_name"] == "Dr. Smith"
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]


def test_login_bad_password() -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"provider_id": "DR-SMITH", "password": "wrong", "role": "Physician"},
    )
    assert response.status_code == 401
    assert response.json() == {
        "error": "invalid_credentials",
        "detail": "Invalid provider ID or password",
    }


def test_login_unknown_provider() -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"provider_id": "NOPE", "password": PASSWORD, "role": "Physician"},
    )
    assert response.status_code == 401
    assert response.json()["error"] == "invalid_credentials"


def test_login_role_mismatch() -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"provider_id": "DR-SMITH", "password": PASSWORD, "role": "Admin"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid provider ID or password"


def test_login_inactive_user() -> None:
    _override([_physician(is_active=False)])
    response = client.post(
        "/api/v1/auth/login",
        json={"provider_id": "DR-SMITH", "password": PASSWORD, "role": "Physician"},
    )
    assert response.status_code == 401


def test_login_validation_error() -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"provider_id": "  ", "password": PASSWORD, "role": "Physician"},
    )
    assert response.status_code == 422


def test_me_with_token() -> None:
    token = client.post(
        "/api/v1/auth/login",
        json={"provider_id": "DR-SMITH", "password": PASSWORD, "role": "Physician"},
    ).json()["token"]
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["provider_id"] == "DR-SMITH"


def test_me_without_token() -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json() == {
        "error": "invalid_credentials",
        "detail": "Invalid or expired session",
    }


def test_me_with_bad_token() -> None:
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401
    assert response.json()["error"] == "invalid_credentials"


def test_logout() -> None:
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    assert response.content == b""
