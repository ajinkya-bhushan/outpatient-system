"""Authenticate users against the users table."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select

from app.core.config import settings
from app.core.errors import InvalidCredentials
from app.core.security import create_access_token, decode_access_token, verify_password
from app.db import User, get_session
from app.schemas.auth import LoginResponse, UserPublic


@dataclass(frozen=True)
class AuthUser:
    id: uuid.UUID
    provider_id: str
    role: str
    display_name: str | None
    password_hash: str
    is_active: bool


class UserRepository(Protocol):
    def get_by_provider_id(self, provider_id: str) -> AuthUser | None: ...

    def get_by_id(self, user_id: uuid.UUID) -> AuthUser | None: ...


def _to_auth_user(row: User) -> AuthUser:
    return AuthUser(
        id=row.id,
        provider_id=row.provider_id,
        role=row.role,
        display_name=row.display_name,
        password_hash=row.password_hash,
        is_active=bool(row.is_active),
    )


class SqlAlchemyUserRepository:
    def get_by_provider_id(self, provider_id: str) -> AuthUser | None:
        session = get_session()
        try:
            row = session.scalar(select(User).where(User.provider_id == provider_id))
            return _to_auth_user(row) if row is not None else None
        finally:
            session.close()

    def get_by_id(self, user_id: uuid.UUID) -> AuthUser | None:
        session = get_session()
        try:
            row = session.get(User, user_id)
            return _to_auth_user(row) if row is not None else None
        finally:
            session.close()


def _public(user: AuthUser) -> UserPublic:
    return UserPublic(
        id=user.id,
        provider_id=user.provider_id,
        role=user.role,
        display_name=user.display_name,
    )


class AuthService:
    def __init__(self, users: UserRepository | None = None) -> None:
        self.users = users or SqlAlchemyUserRepository()

    def login(self, provider_id: str, password: str, role: str) -> LoginResponse:
        user = self.users.get_by_provider_id(provider_id.strip())
        if (
            user is None
            or not user.is_active
            or user.role != role
            or not verify_password(password, user.password_hash)
        ):
            raise InvalidCredentials()
        token = create_access_token(
            user_id=user.id,
            role=user.role,
            provider_id=user.provider_id,
        )
        return LoginResponse(
            token=token,
            expires_in=settings.AUTH_JWT_EXPIRE_SECONDS,
            user=_public(user),
        )

    def me(self, token: str) -> UserPublic:
        try:
            payload = decode_access_token(token)
            user_id = uuid.UUID(str(payload["sub"]))
        except Exception as exc:
            raise InvalidCredentials("Invalid or expired session") from exc
        user = self.users.get_by_id(user_id)
        if user is None or not user.is_active:
            raise InvalidCredentials("Invalid or expired session")
        return _public(user)
