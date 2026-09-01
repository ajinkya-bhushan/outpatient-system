# DocConnect Architecture

## System Overview

```mermaid
flowchart LR
  clinician[Clinician browser]

  subgraph frontend[React frontend - Vite]
    app[App.jsx screen router]
    authClient[api/auth.js]
    sttClient[api/stt.js]
    soapClient[api/soap.js]
    recorder[useEncounterRecorder]
    screens[Clinical screens]
    components[Shared UI components]
    session[(sessionStorage)]
  end

  subgraph backend[FastAPI backend]
    main[app/main.py]
    authRoutes[Auth routes]
    sttRoutes[STT routes]
    soapRoutes[SOAP routes]
    pipelineRoutes[Pipeline routes]
    authService[Auth service]
    sttService[STT service]
    artifactStore[STT artifact storage adapter]
    soapJobs[SOAP job service]
    pipeline[Pipeline service]
    soapStore[SOAP store]
  end

  subgraph data[Data and external services]
    postgres[(Postgres / Supabase)]
    objectStore[(MinIO / S3 object storage)]
    audioScratch[(Local temp audio scratch)]
    aws[AWS Comprehend Medical]
    aava[Aava SOAP agent]
    models[(Whisper + SpeechBrain models)]
  end

  clinician --> app
  app --> screens
  screens --> components
  screens --> authClient
  screens --> sttClient
  screens --> soapClient
  screens --> recorder
  app <--> session

  authClient -->|POST /api/v1/auth/login| authRoutes
  sttClient -->|POST /api/v1/stt/diarize| sttRoutes
  soapClient -->|POST /api/v1/soap/create| soapRoutes
  soapClient -->|GET /api/v1/soap/jobs/:id| soapRoutes

  main --> authRoutes
  main --> sttRoutes
  main --> soapRoutes
  main --> pipelineRoutes

  authRoutes --> authService
  authService --> postgres

  sttRoutes --> sttService
  sttService --> audioScratch
  sttService --> artifactStore
  artifactStore --> objectStore
  sttService --> models

  soapRoutes --> soapJobs
  soapJobs --> aws
  soapJobs --> aava
  soapJobs --> soapStore
  soapStore --> postgres

  pipelineRoutes --> pipeline
  pipeline --> sttService
  pipeline --> aws
  pipeline --> aava
  pipeline --> soapStore
```

## Encounter To SOAP Sequence

```mermaid
sequenceDiagram
  autonumber
  actor Clinician
  participant UI as React UI
  participant Auth as auth.js
  participant STT as stt.js
  participant SOAP as soap.js
  participant API as FastAPI
  participant DB as Postgres
  participant Store as MinIO/S3
  participant Speech as Whisper/SpeechBrain
  participant AWS as Comprehend Medical
  participant Aava as Aava SOAP Agent

  Clinician->>UI: Sign in
  UI->>Auth: login(provider_id, password, role)
  Auth->>API: POST /api/v1/auth/login
  API->>DB: Verify user credentials
  DB-->>API: User
  API-->>Auth: JWT + user
  Auth-->>UI: Store token in sessionStorage

  Clinician->>UI: Record or upload encounter audio
  UI->>STT: diarizeAudio(file)
  STT->>API: POST /api/v1/stt/diarize
  API->>Store: Persist original audio artifact
  API->>Speech: Transcribe and diarize
  Speech-->>API: Speaker-labelled turns
  API->>Store: Persist audio.wav, result.json, plain.txt, labelled.txt
  API-->>STT: job_id + transcript turns
  STT-->>UI: Editable transcript

  Clinician->>UI: Generate Note
  UI->>SOAP: createSoap(labelled transcript)
  SOAP->>API: POST /api/v1/soap/create
  API->>DB: Resolve encounter
  API-->>SOAP: soap_job_id
  SOAP-->>UI: Queued job

  par Background SOAP job
    API->>AWS: Extract clinical entities
    AWS-->>API: Entities and category counts
    API->>Aava: Generate SOAP markdown
    Aava-->>API: SOAP markdown
    API->>DB: Persist note, sections, conversation text
  and UI polling
    UI->>SOAP: getSoapJob(soap_job_id)
    SOAP->>API: GET /api/v1/soap/jobs/:id
    API-->>SOAP: queued / extracting / generating / done
    SOAP-->>UI: Step status + SOAP note when ready
  end

  Clinician->>UI: Review, edit plan, approve
  UI->>UI: Navigate to EHR sync confirmation
```

## Frontend Component Structure

```mermaid
flowchart TD
  main[main.jsx] --> app[App.jsx]

  app --> login[LoginScreen]
  app --> shell[ClinicalShell]
  app --> transaction[TransactionFrame]
  app --> recording[RecordingScreen]
  app --> review[ReviewScreen]

  shell --> schedule[ScheduleScreen]
  shell --> previsit[PreVisitScreen]
  shell --> sync[SyncScreen]
  shell --> analytics[AnalyticsScreen]

  transaction --> generation[GenerationScreen]

  login --> icon[Icon]
  schedule --> patientCard[PatientCard]
  previsit --> resourceRow[ResourceRow]
  recording --> transcriptBubble[TranscriptBubble]
  recording --> extractionTag[ExtractionTag]
  recording --> recorderHook[useEncounterRecorder]
  generation --> step[Step]
  review --> reviewNoteCard[ReviewNoteCard]
  review --> suggestedCode[SuggestedCode]
  review --> statusBadge[StatusBadge]

  app --> clinicalData[clinicalData.js]
  login --> authApi[api/auth.js]
  recording --> sttApi[api/stt.js]
  recording --> soapApi[api/soap.js]
  generation --> soapApi
  review --> soapApi
```

## Runtime Notes

- Frontend dev server runs on port `10100`.
- Backend API is expected on port `10200`.
- Vite proxies `/api` to the backend during dev.
- Login is normally database-backed through the `users` table.
- The current local frontend includes a demo fallback for `DR-SMITH` / `Smith#2026` when the backend cannot be reached.
- SOAP generation depends on AWS credentials and `AAVA_JWT_TOKEN`.
- STT can run locally with Whisper/SpeechBrain or proxy to the standalone `sst_v1` service in remote mode.
- Persisted encounter audio and transcript artifacts can be stored in MinIO through the S3-compatible object storage adapter by setting `OBJECT_STORAGE_PROVIDER=minio`.
- The local STT engine still uses temporary local files for ffmpeg, Whisper, and SpeechBrain, then uploads durable artifacts to object storage.
- MinIO stores PHI-heavy artifacts while Postgres keeps relational encounter/note metadata and object keys.
