"""In-memory encounter artifacts for the current POC."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.modules.stt.schemas import TranscriptResult


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class EncounterRecord:
    id: str
    created_at: str
    source: str = "text"
    transcript: TranscriptResult | None = None
    entities: list[dict[str, Any]] = field(default_factory=list)
    soap_markdown: str | None = None
    soap_execution_id: str | None = None
    soap_status: str | None = None


class EncounterStore:
    def __init__(self) -> None:
        self._items: dict[str, EncounterRecord] = {}

    def create(self, encounter_id: str | None = None, source: str = "text") -> EncounterRecord:
        record = EncounterRecord(
            id=encounter_id or str(uuid4()),
            created_at=_now(),
            source=source,
        )
        self._items[record.id] = record
        return record

    def get(self, encounter_id: str) -> EncounterRecord | None:
        return self._items.get(encounter_id)

    def get_or_create(self, encounter_id: str | None, source: str = "text") -> EncounterRecord:
        if encounter_id and encounter_id in self._items:
            return self._items[encounter_id]
        return self.create(encounter_id, source=source)


store = EncounterStore()
