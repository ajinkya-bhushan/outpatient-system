# Outpatient Backend

FastAPI service that turns an encounter recording or uploaded audio into a clinician-reviewable SOAP draft.

Full product and implementation specification: [`../docs/FEATURE_SPEC.md`](../docs/FEATURE_SPEC.md).

The pipeline is three modules:

1. **stt** — record live or upload audio, then generate a transcript (`sst_v1`)
2. **medical_comprehend** — extract clinical entities (`soap_create/app.py`)
3. **generate_soap** — call the Aava documentation agent (`soap_create/agent_call.py`)

## Run

```bash
cd backend
cp .env.example .env
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 10200
```

API docs: http://127.0.0.1:10200/docs

## Docker

From the repo root, one compose file starts the backend on **10200** and the frontend on **10100** (host network). Secrets come from `.env` and `database/.env` at runtime; they are not baked into the image.

```bash
docker compose up --build -d
curl -s http://127.0.0.1:10200/api/v1/health
```

Single-service shortcuts still work from `backend/` or `frontend/` (`docker compose up --build -d`).

Seed login (after `database` migration `011_add_user_auth_columns`):

| Role | Provider ID | Password |
|---|---|---|
| Physician | `DR-SMITH` | `Smith#2026` |
| Admin | `ADMIN` | `Admin#2026` |

For live/upload transcription, start `sst_v1` on port 8000 as well:

```bash
cd ../sst_v1
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Main endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | Liveness |
| `GET` | `/api/v1/ready` | Dependency readiness |
| `POST` | `/api/v1/auth/login` | Provider ID + password + role → JWT |
| `GET` | `/api/v1/auth/me` | Current user from Bearer token |
| `POST` | `/api/v1/auth/logout` | Client discard (stateless 204) |
| `POST` | `/api/v1/stt/transcribe` | Upload audio → transcript |
| `WS` | `/api/v1/stt/live` | Live recording proxy to `sst_v1` |
| `POST` | `/api/v1/comprehend/entities` | Transcript → Comprehend Medical entities |
| `POST` | `/api/v1/soap/generate` | Entities → SOAP markdown |
| `POST` | `/api/v1/pipeline` | Audio or transcript → entities + SOAP |

## Tests

```bash
uv run pytest -q
```
