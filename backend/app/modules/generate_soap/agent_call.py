"""Submit Comprehend Medical entities to the Aava agent and return a SOAP note.

The Aava execute API rejects application/json file uploads, so the payload is
sent as text/plain. The agent reads the upload from the capital-F ``Files``
field and the ``{{input1}}`` userInputs placeholder. SOAP create uploads
DetectEntitiesV2 plus InferICD10CM / InferRxNorm codes with confidence.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import requests

from app.core.config import settings
from app.core.errors import (
    ConfigurationError,
    UpstreamTimeout,
    UpstreamUnavailable,
    ValidationFailed,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

UPLOAD_MIME = "text/plain"
UPLOAD_NAME = "entities.txt"
FILE_FIELD = "Files"
INLINE_KEY = "{{input1}}"
TERMINAL_STATUSES = {"SUCCESS", "COMPLETED", "FAILED", "FAILURE", "ERROR", "CANCELLED"}
SUCCESS_STATUSES = {"SUCCESS", "COMPLETED"}


def _auth_headers() -> dict[str, str]:
    token = settings.AAVA_JWT_TOKEN
    if not token:
        raise ConfigurationError("AAVA_JWT_TOKEN is not set. Add it to the backend .env file.")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/plain, */*",
    }


def _as_text(entities: list[dict[str, Any]] | dict[str, Any] | str) -> str:
    if isinstance(entities, str):
        text = entities.strip()
    else:
        text = json.dumps(entities, indent=2, ensure_ascii=False)
    if not text:
        raise ValidationFailed("Entity payload is empty.")
    return text


def submit(
    entities: list[dict[str, Any]] | dict[str, Any] | str,
    user_inputs: dict[str, str] | None = None,
    send_execution_id: bool = False,
) -> str:
    """Upload entities and return the agentExecutionId to poll."""
    payload_text = _as_text(entities)
    inputs = dict(user_inputs or {})
    inputs.setdefault(INLINE_KEY, payload_text)

    form: dict[str, str] = {
        "agentId": settings.AAVA_AGENT_ID,
        "userInputs": json.dumps(inputs),
    }
    if send_execution_id:
        form["executionId"] = str(uuid.uuid4())

    logger.info(
        "soap_agent_submit_started",
        agent_id=settings.AAVA_AGENT_ID,
        chars=len(payload_text),
    )
    try:
        response = requests.post(
            settings.AAVA_EXECUTE_ENDPOINT,
            headers=_auth_headers(),
            data=form,
            files={FILE_FIELD: (UPLOAD_NAME, payload_text.encode("utf-8"), UPLOAD_MIME)},
            timeout=120,
        )
    except requests.Timeout as exc:
        raise UpstreamTimeout("Aava SOAP agent submit timed out.") from exc
    except requests.RequestException as exc:
        raise UpstreamUnavailable(f"Aava SOAP agent submit failed: {exc}") from exc

    if response.status_code != 200:
        raise UpstreamUnavailable(
            f"SOAP agent submit failed: HTTP {response.status_code} {response.text}"
        )

    data = response.json().get("data") or {}
    execution_id = data.get("agentExecutionId")
    if not execution_id:
        raise UpstreamUnavailable("SOAP agent submit did not return agentExecutionId.")
    logger.info("soap_agent_submitted", execution_id=execution_id, job_id=data.get("jobId"))
    return str(execution_id)


def fetch_execution(execution_id: str) -> dict[str, Any]:
    try:
        response = requests.get(
            settings.AAVA_HISTORY_ENDPOINT,
            headers=_auth_headers(),
            params={"execution_id": execution_id},
            timeout=60,
        )
        response.raise_for_status()
    except requests.Timeout as exc:
        raise UpstreamTimeout("Aava SOAP agent poll timed out.") from exc
    except requests.RequestException as exc:
        raise UpstreamUnavailable(f"Aava SOAP agent poll failed: {exc}") from exc
    return response.json()


def poll(
    execution_id: str,
    timeout: int | None = None,
    interval: int | None = None,
) -> dict[str, Any]:
    timeout = timeout or settings.AAVA_POLL_TIMEOUT_SECONDS
    interval = interval or settings.AAVA_POLL_INTERVAL_SECONDS
    deadline = time.monotonic() + timeout
    started = time.monotonic()

    while True:
        record = fetch_execution(execution_id)
        status = (record.get("status") or "PENDING").upper()
        elapsed = time.monotonic() - started
        logger.info("soap_agent_poll", execution_id=execution_id, status=status, elapsed_s=round(elapsed, 1))
        if status in TERMINAL_STATUSES:
            return record
        if time.monotonic() >= deadline:
            raise UpstreamTimeout(
                f"SOAP agent execution {execution_id} still {status} after {timeout}s"
            )
        time.sleep(interval)


def generate_soap_note(
    entities: list[dict[str, Any]] | dict[str, Any] | str,
    user_inputs: dict[str, str] | None = None,
    timeout: int | None = None,
    interval: int | None = None,
) -> dict[str, Any]:
    """Submit entities, wait for the agent, and return SOAP markdown plus metadata."""
    execution_id = submit(entities, user_inputs=user_inputs)
    record = poll(execution_id, timeout=timeout, interval=interval)
    status = (record.get("status") or "").upper()
    output = record.get("output") or ""
    if status not in SUCCESS_STATUSES or not output:
        raise UpstreamUnavailable(
            f"SOAP agent did not produce output (status {status or 'UNKNOWN'})."
        )
    logger.info(
        "soap_agent_completed",
        execution_id=execution_id,
        chars=len(output),
        agent=record.get("agentName"),
    )
    return {
        "execution_id": execution_id,
        "status": status,
        "agent_name": record.get("agentName"),
        "created_at": record.get("createdAt"),
        "soap_markdown": output,
    }
