# Outpatient System (DocConnect)

Clinical documentation stack: capture an outpatient encounter, transcribe it with speaker diarization, extract entities, and draft a SOAP note for clinician review.

```text
outpatient-system/
├── backend/     ← FastAPI (STT local/remote, SOAP, auth)
├── frontend/    ← DocConnect UI (wired to backend)
├── database/    ← Postgres migrations + models
└── docs/        ← product spec and API contracts
```

Full specification: [`docs/FEATURE_SPEC.md`](docs/FEATURE_SPEC.md).

## Run

```bash
# Database (once)
cd database && uv run alembic upgrade head

# API
cd backend
cp .env.example .env
uv sync --extra stt
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 10200

# UI (Vite proxies /api → :10200)
cd frontend && npm install && npm run dev
```

Seed login: `DR-SMITH` / `Smith#2026` (Physician) or `ADMIN` / `Admin#2026`.

Docker from this directory: `docker compose up --build -d` (backend **10200**, frontend **10100**).
