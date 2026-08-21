"""Shared API contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.modules.stt.schemas import TranscriptResult


class ErrorBody(BaseModel):
    error: str
    detail: str
    request_id: str | None = None


class TranscriptTextRequest(BaseModel):
    text: str = Field(..., min_length=1)
    language: str | None = None
    encounter_id: str | None = None


class EntityExtractionResponse(BaseModel):
    encounter_id: str
    entity_count: int
    category_counts: dict[str, int] = Field(default_factory=dict)
    entities: list[dict[str, Any]]


class SoapGenerateRequest(BaseModel):
    entities: list[dict[str, Any]] | None = None
    encounter_id: str | None = None
    user_inputs: dict[str, str] = Field(default_factory=dict)


class SoapGenerateResponse(BaseModel):
    encounter_id: str
    execution_id: str
    status: str
    agent_name: str | None = None
    soap_markdown: str
    created_at: str | None = None


class PipelineRequest(BaseModel):
    """Run transcript → entities → SOAP when audio is not uploaded."""

    transcript: str = Field(..., min_length=1)
    encounter_id: str | None = None
    language: str | None = None
    source: Literal["text", "upload", "live"] = "text"


class PipelineResponse(BaseModel):
    encounter_id: str
    transcript: TranscriptResult
    entity_count: int
    category_counts: dict[str, int] = Field(default_factory=dict)
    entities: list[dict[str, Any]]
    soap: SoapGenerateResponse
