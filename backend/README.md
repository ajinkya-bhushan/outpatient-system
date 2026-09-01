# Outpatient Backend

FastAPI service that turns an encounter recording or uploaded audio into a clinician-reviewable SOAP draft.

Full product and implementation specification: [`../docs/FEATURE_SPEC.md`](../docs/FEATURE_SPEC.md).

The pipeline is three modules:

1. **stt** — upload audio, then transcribe it with speaker diarization
   (SpeechBrain + Whisper, in-process). See
   [`docs/STT_DIARIZATION_API.md`](docs/STT_DIARIZATION_API.md).
2. **medical_comprehend** — extract clinical entities
3. **generate_soap** — call the Aava documentation agent

SOAP create (transcript → entities → note) is documented in
[`../docs/SOAP_CREATE_API.md`](../docs/SOAP_CREATE_API.md).

## Run

```bash
cd backend
cp .env.example .env
uv sync --extra stt          # omit --extra stt for STT_ENGINE_MODE=remote
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 10200
```

API docs: http://127.0.0.1:10200/docs

The `stt` extra pulls in PyTorch, SpeechBrain and Whisper (several GB) and
**ffmpeg must be on `PATH`**. Model weights download on first use into
`MODEL_CACHE_DIR`. Without a GPU the engine falls back to CPU, which works but
is slower than real time with `small.en`.

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

Transcription runs inside this service by default (`STT_ENGINE_MODE=local`).
To delegate it to an external STT HTTP service instead — a CPU-only host, or
comparing engines — set `STT_ENGINE_MODE=remote` and `STT_BASE_URL`.

Diarization is unavailable in remote mode, and live streaming is available only
in remote mode.

## Main endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | Liveness |
| `GET` | `/api/v1/ready` | Dependency readiness |
| `POST` | `/api/v1/auth/login` | Provider ID + password + role → JWT |
| `GET` | `/api/v1/auth/me` | Current user from Bearer token |
| `POST` | `/api/v1/auth/logout` | Client discard (stateless 204) |
| `POST` | `/api/v1/stt/diarize` | Upload audio → speaker-labelled transcript |
| `POST` | `/api/v1/stt/transcribe` | Upload audio → transcript |
| `GET` | `/api/v1/stt/engine` | Active engine, device, model readiness |
| `GET` | `/api/v1/stt/jobs` | Stored transcription jobs |
| `GET`/`DELETE` | `/api/v1/stt/jobs/{job_id}` | Fetch or delete a stored result |
| `GET` | `/api/v1/stt/jobs/{job_id}/audio` | Stream the converted WAV (`Range` supported, for per-turn playback) |
| `WS` | `/api/v1/stt/live` | Live recording proxy to a remote STT service (remote mode only) |
| `POST` | `/api/v1/comprehend/entities` | Transcript → Comprehend Medical entities |
| `POST` | `/api/v1/comprehend/icd10` | Transcript → InferICD10CM entities and ICD-10-CM codes |
| `POST` | `/api/v1/comprehend/rxnorm` | Transcript → InferRxNorm entities and RxNorm concept IDs |
| `POST` | `/api/v1/soap/create` | Transcript → Comprehend → Aava job (`202`) |
| `GET` | `/api/v1/soap/jobs/{soap_job_id}` | Poll SOAP job status |
| `GET` | `/api/v1/soap/notes/{soap_note_id}` | Persisted SOAP note |
| `GET` | `/api/v1/soap/encounters/{encounter_id}` | Current SOAP note for an encounter |
| `POST` | `/api/v1/soap/generate` | Entities → SOAP markdown (sync replay) |
| `POST` | `/api/v1/pipeline` | Audio or transcript → entities + SOAP |

## Tests

```bash
uv run pytest -q -m "not real_model"   # fast, no model weights needed
uv run pytest -q -m real_model         # real SpeechBrain + Whisper end to end
```

`real_model` tests load real weights and run against audio under
`tests/fixtures/diar_testset/`; they skip themselves when the fixtures, ffmpeg,
or the `stt` extra are missing.
