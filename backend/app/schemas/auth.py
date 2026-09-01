"""Auth request and response contracts."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    provider_id: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)

    @field_validator("provider_id", "role")
    @classmethod
    def strip_nonempty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class UserPublic(BaseModel):
    id: uuid.UUID
    provider_id: str
    role: str
    display_name: str | None = None


class LoginResponse(BaseModel):
    ok: bool = True
    token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic
