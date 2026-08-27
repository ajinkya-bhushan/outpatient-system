# SOAP Create API

Transcript in, reviewable SOAP draft out. Served by the unified backend at
`/api/v1/soap/*`; the interactive OpenAPI schema is at `/docs`.

This folder (`soap_create/`) is the prototype: `app.py` calls Amazon
Comprehend Medical, `agent_call.py` submits the entities to the Aava agent.
The live service is the same pipeline inside the backend
(`medical_comprehend` + `generate_soap`). Do not run a second HTTP server
from here.

- [Architecture](#architecture)
- [Status machine](#status-machine)
- [Endpoints](#endpoints)
- [Field reference](#field-reference)
- [Error codes](#error-codes)
- [Configuration](#configuration)

---

## Architecture

```
labelled transcript
        │
        ▼
POST /api/v1/soap/create  →  job (202, status=queued)
        │
        ├─ extracting  →  Comprehend Medical DetectEntitiesV2
        ├─ generating  →  Aava agent 54818 (upload entities, poll)
        ├─ parse       →  S / O / A / P sections
        └─ persist     →  soap_notes + soap_note_sections
                │
                ▼
GET /api/v1/soap/jobs/{soap_job_id}   (generation screen polls)
GET /api/v1/soap/notes/{soap_note_id}
GET /api/v1/soap/encounters/{encounter_id}
```

The recording screen has already transcribed. **Generate Note** sends the
**edited** speaker-labelled text (`Doctor:` / `Patient:` lines), not the
original stored STT payload.

`POST /api/v1/soap/generate` remains for replay when entities are already in
hand. The UI uses `/soap/create`.

Jobs live in process memory. The durable result is Postgres. Restarting the
backend drops in-flight jobs; the generation screen can resume a finished
note via `encounter_id`.

---

## Status machine

| `status` | Meaning | Generation UI |
|---|---|---|
| `queued` | Accepted, worker not started | Transcribing done; Extracting pending |
| `extracting` | Comprehend Medical running | Extracting active |
| `generating` | Aava submitted / polling | Extracting done; Generating active |
| `done` | Markdown parsed and DB written | All steps done; enable **Review Draft Note** |
| `failed` | Comprehend, Aava, parse, or DB error | Error + Retry; transcript kept |

Each job also carries `steps[]` with `id` ∈ `transcribing` | `extracting` |
`generating` and `status` ∈ `queued` | `active` | `done` | `failed`.
Transcribing is `done` as soon as the job is accepted (STT already finished).

Cancel on the generation screen only stops polling. The backend job may still
finish; reload review by `encounter_id`.

---

## Endpoints

### `POST /api/v1/soap/create`

Start SOAP generation from a labelled transcript. Returns immediately.

**Request** — `application/json`

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `transcript` | string | yes | — | Speaker-labelled text. Same 20 000 character cap as Comprehend (`MAX_TRANSCRIPT_CHARS`). |
| `encounter_id` | UUID string | no | seeded Marcus encounter | Postgres `encounters.id`. Omitted → `uuid5(6ba7b810-9dad-11d1-80b4-00c04fd430c8, "outpatient-frontend-seed\|encounter:marcus-2026-08-19")` = `9809b5b7-07fc-5582-b567-f6cc8abc89e1`. |
| `job_id` | string | no | — | STT job the transcript came from (audit only). |
| `language` | string | no | — | BCP-47 hint; not sent to Comprehend. |
| `user_inputs` | object | no | `{}` | Extra Aava `userInputs` placeholders. |

**Response `202`**

```json
{
  "soap_job_id": "3f2a0c1e-7b84-4d2e-9c1a-0b5d6e8f9a10",
  "encounter_id": "9809b5b7-07fc-5582-b567-f6cc8abc89e1",
  "soap_note_id": null,
  "status": "queued",
  "steps": [
    { "id": "transcribing", "status": "done" },
    { "id": "extracting", "status": "queued" },
    { "id": "generating", "status": "queued" }
  ],
  "entity_count": null,
  "category_counts": {},
  "execution_id": null,
  "soap_note": null,
  "error": null
}
```

**Errors:** `400` empty or too-long transcript, or malformed `encounter_id`;
`404` unknown `encounter_id`; `503` AWS, Aava, or `DATABASE_URL` not configured.

---

### `GET /api/v1/soap/jobs/{soap_job_id}`

Polled by the generation screen (every ~2 seconds).

**Response `200` (done)**

```json
{
  "soap_job_id": "3f2a0c1e-7b84-4d2e-9c1a-0b5d6e8f9a10",
  "encounter_id": "9809b5b7-07fc-5582-b567-f6cc8abc89e1",
  "soap_note_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "done",
  "steps": [
    { "id": "transcribing", "status": "done" },
    { "id": "extracting", "status": "done" },
    { "id": "generating", "status": "done" }
  ],
  "entity_count": 42,
  "category_counts": { "MEDICAL_CONDITION": 12 },
  "execution_id": "aava-execution-id",
  "soap_note": {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "status": "needs_physician_review",
    "soap_markdown": "# MEDICAL SOAP NOTE\n…",
    "sections": [
      { "section_type": "subjective", "ai_generated_text": "…" },
      { "section_type": "objective", "ai_generated_text": "…" },
      { "section_type": "assessment", "ai_generated_text": "…" },
      { "section_type": "plan", "ai_generated_text": "…" }
    ]
  },
  "error": null
}
```

On `failed`, `error` is `{ "code": "upstream_unavailable", "detail": "…" }`
and `soap_note` is null. The transcript is not deleted.

**Errors:** `404` unknown `soap_job_id` (including after process restart).

---

### `GET /api/v1/soap/notes/{soap_note_id}`

Load a persisted note. Same `soap_note` object as above (top-level, not
wrapped in a job). Used by review after the generation session is gone.

**Errors:** `404` unknown id; `503` database not configured.

---

### `GET /api/v1/soap/encounters/{encounter_id}`

Load the current SOAP note for an encounter (`soap_notes.encounter_id` is
unique). Same body as `/notes/{id}`.

**Errors:** `404` no note for that encounter; `400` malformed UUID; `503`
database not configured.

---

### `POST /api/v1/soap/generate` (existing)

Entities in, markdown out, synchronous. Kept for tests and SOAP-only replay.

**Body:** `{ "entities": [...], "encounter_id": "optional", "user_inputs": {} }`  
**Response `200`:** `{ encounter_id, execution_id, status, agent_name, soap_markdown, created_at }`

Does not write `soap_note_sections`. Prefer `/soap/create` for the UI path.

---

## Field reference

### Job

| Field | Type | Description |
|---|---|---|
| `soap_job_id` | UUID string | In-memory job id. |
| `encounter_id` | UUID string | Postgres encounter this draft belongs to. |
| `soap_note_id` | UUID string or null | Set when `status=done`. |
| `status` | string | See [status machine](#status-machine). |
| `steps` | array | Three pipeline steps for the generation screen. |
| `entity_count` | int or null | Comprehend entity total, once extracting finishes. |
| `category_counts` | object | Counts keyed by Comprehend `Category`. |
| `execution_id` | string or null | Aava `agentExecutionId`. |
| `soap_note` | object or null | Parsed draft; see below. |
| `error` | object or null | `{ code, detail }` when `status=failed`. |

### SOAP note

| Field | Type | Description |
|---|---|---|
| `id` | UUID string | `soap_notes.id`. |
| `status` | string | `needs_physician_review` on create/regenerate. |
| `soap_markdown` | string | Raw Aava markdown (reconstructed from sections when loaded from DB). |
| `sections` | array | Always four items: `subjective`, `objective`, `assessment`, `plan`. |

Section headings recognised (case-insensitive): `## S – SUBJECTIVE`,
`## SUBJECTIVE`, `S - SUBJECTIVE`, and the O/A/P counterparts. Text before
the first heading is prepended to Subjective. Missing headings yield an
empty `ai_generated_text`.

Regenerating a note for an encounter **replaces** the four sections, sets
`status=needs_physician_review`, and clears `approved_at`.

---

## Error codes

| HTTP | When |
|---|---|
| 400 | Empty/whitespace transcript; over `MAX_TRANSCRIPT_CHARS`; `encounter_id` is not a UUID. |
| 404 | Unknown `encounter_id`, `soap_job_id`, `soap_note_id`, or encounter with no note. |
| 502 | Comprehend or Aava returned a failure (surfaced on the **job**, not the create response). |
| 503 | Missing AWS keys, `AAVA_JWT_TOKEN`, or `DATABASE_URL`. |
| 504 | Aava poll exceeded `AAVA_POLL_TIMEOUT_SECONDS` (job `failed`). |

Failed jobs use `error.code`: `validation_failed`, `not_found`,
`configuration_error`, `upstream_unavailable`, `upstream_timeout`,
`internal_error`.

---

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Comprehend Medical | required for create |
| `AWS_DEFAULT_REGION` | Comprehend region | `us-east-1` |
| `AAVA_JWT_TOKEN` | Aava bearer token | required for create |
| `AAVA_EXECUTE_ENDPOINT` | Submit URL | `https://int-ai.aava.ai/agents/execute/agent-executions` |
| `AAVA_HISTORY_ENDPOINT` | Poll URL | `https://int-ai.aava.ai/agents/execute/history/execution` |
| `AAVA_AGENT_ID` | SOAP agent | `54818` |
| `AAVA_POLL_INTERVAL_SECONDS` | Poll interval | `10` |
| `AAVA_POLL_TIMEOUT_SECONDS` | Poll timeout | `600` |
| `MAX_TRANSCRIPT_CHARS` | Input cap | `20000` |
| `DATABASE_URL` | Postgres for `soap_notes` | required for create |

Gold sample: dengue/Gaia conversation in this folder → `entities.json` →
`soap_note.md`.
