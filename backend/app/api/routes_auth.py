"""Auth routes: login, current user, logout."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import InvalidCredentials
from app.core.logging import get_logger
from app.schemas.auth import LoginRequest, LoginResponse, UserPublic
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])
logger = get_logger(__name__)
bearer = HTTPBearer(auto_error=False)


def get_auth_service() -> AuthService:
    return AuthService()


def _unauthorized(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"error": "invalid_credentials", "detail": detail},
    )


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest, service: AuthService = Depends(get_auth_service)
) -> LoginResponse | JSONResponse:
    try:
        result = service.login(body.provider_id, body.password, body.role)
    except InvalidCredentials:
        logger.info("auth_login_failed", provider_id=body.provider_id, role=body.role)
        return _unauthorized("Invalid provider ID or password")
    logger.info(
        "auth_login_ok",
        provider_id=result.user.provider_id,
        role=result.user.role,
        user_id=str(result.user.id),
    )
    return result


@router.get("/me", response_model=UserPublic)
def me(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    service: AuthService = Depends(get_auth_service),
) -> UserPublic | JSONResponse:
    token = credentials.credentials if credentials else None
    if not token:
        return _unauthorized("Invalid or expired session")
    try:
        return service.me(token)
    except InvalidCredentials:
        return _unauthorized("Invalid or expired session")


@router.post("/logout", status_code=204)
def logout() -> Response:
    return Response(status_code=204)
