"""Submit entities.json to the Aava agent, poll for completion, and save the SOAP note."""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

EXECUTE_ENDPOINT = "https://int-ai.aava.ai/agents/execute/agent-executions"
HISTORY_ENDPOINT = "https://int-ai.aava.ai/agents/execute/history/execution"
AGENT_ID = "54818"
DEFAULT_INPUT_PATH = "entities.json"
DEFAULT_OUTPUT_PATH = "soap_note.md"

# The API rejects application/json uploads, so the payload is sent as plain text.
UPLOAD_MIME = "text/plain"
UPLOAD_NAME = "entities.txt"

# The agent only reads the upload from the capital-F field; lowercase "files"
# is accepted at submit time but the run then fails with no output.
FILE_FIELD = "Files"

# The agent's prompt template reads the entity JSON from this placeholder.
INLINE_KEY = "{{input1}}"

USER_INPUTS = {
    "{{DocumentationTitle}}": "",
    "{{IntendedAudience}}": "",
    "{{DocumentationPurpose}}": "",
    "{{Requirements}}": "",
    "{{APIDocumentationLink}}": "",
}

TERMINAL_STATUSES = {"SUCCESS", "COMPLETED", "FAILED", "FAILURE", "ERROR", "CANCELLED"}


def auth_headers() -> dict[str, str]:
    token = os.getenv("AAVA_JWT_TOKEN")
    if not token:
        raise RuntimeError("AAVA_JWT_TOKEN is not set. Add it to your .env file.")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/plain, */*",
    }


def submit(
    input_path: Path,
    user_inputs: dict[str, str],
    upload_name: str = UPLOAD_NAME,
    mime_type: str = UPLOAD_MIME,
    file_field: str = FILE_FIELD,
    send_execution_id: bool = False,
) -> str:
    """Upload the entity file and return the agentExecutionId to poll."""
    print(f"POST {EXECUTE_ENDPOINT}")
    print(f"  agentId={AGENT_ID} file={input_path} as {upload_name} ({mime_type})")
    summary = {k: f"<{len(v)} chars>" if len(v) > 60 else v for k, v in user_inputs.items()}
    print(f"  field={file_field} userInputs={json.dumps(summary)}")

    form: dict[str, str] = {
        "agentId": AGENT_ID,
        "userInputs": json.dumps(user_inputs),
    }
    if send_execution_id:
        form["executionId"] = str(uuid.uuid4())

    with input_path.open("rb") as f:
        response = requests.post(
            EXECUTE_ENDPOINT,
            headers=auth_headers(),
            data=form,
            files={file_field: (upload_name, f, mime_type)},
            timeout=120,
        )

    if response.status_code != 200:
        raise RuntimeError(f"Submit failed: HTTP {response.status_code} {response.text}")

    data = response.json()["data"]
    print(f"  submitted: jobId={data['jobId']} executionId={data['agentExecutionId']}")
    return data["agentExecutionId"]


def fetch_execution(execution_id: str) -> dict[str, Any]:
    response = requests.get(
        HISTORY_ENDPOINT,
        headers=auth_headers(),
        params={"execution_id": execution_id},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def poll(execution_id: str, timeout: int, interval: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    started = time.monotonic()

    while True:
        record = fetch_execution(execution_id)
        status = (record.get("status") or "PENDING").upper()
        elapsed = time.monotonic() - started
        print(f"  [{elapsed:6.1f}s] status={status}")

        if status in TERMINAL_STATUSES:
            return record
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Execution {execution_id} still {status} after {timeout}s"
            )
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--interval", type=int, default=10)
    parser.add_argument(
        "--execution-id",
        default=None,
        help="Fetch an existing execution instead of submitting a new one.",
    )
    parser.add_argument(
        "--user-inputs",
        default=None,
        help="JSON object for userInputs; defaults to an empty object.",
    )
    parser.add_argument(
        "--inline-key",
        default=INLINE_KEY,
        help="userInputs placeholder to fill with the input file's contents.",
    )
    parser.add_argument("--upload-name", default=UPLOAD_NAME)
    parser.add_argument("--mime", default=UPLOAD_MIME)
    parser.add_argument("--file-field", default=FILE_FIELD)
    parser.add_argument("--send-execution-id", action="store_true")
    args = parser.parse_args()

    user_inputs = json.loads(args.user_inputs) if args.user_inputs else {}
    if args.inline_key and not args.execution_id:
        user_inputs[args.inline_key] = Path(args.input).read_text(encoding="utf-8")

    execution_id = args.execution_id or submit(
        Path(args.input),
        user_inputs,
        args.upload_name,
        args.mime,
        args.file_field,
        args.send_execution_id,
    )

    print(f"\nPolling {HISTORY_ENDPOINT}?execution_id={execution_id}")
    record = poll(execution_id, args.timeout, args.interval)

    status = (record.get("status") or "").upper()
    output = record.get("output") or ""
    print(f"\nagent: {record.get('agentName')}")
    print(f"status: {status}  created: {record.get('createdAt')}")

    if status not in {"SUCCESS", "COMPLETED"} or not output:
        print(json.dumps(record, indent=2)[:2000])
        raise SystemExit(f"Execution did not produce output (status {status})")

    Path(args.output).write_text(output, encoding="utf-8")
    print(f"\nWrote SOAP note to {args.output} ({len(output)} chars)")


if __name__ == "__main__":
    main()
