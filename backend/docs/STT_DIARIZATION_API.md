# STT + Speaker Diarization API

Audio file in, speaker-labelled text out. Served by the backend itself at
`/api/v1/stt/*`; the interactive OpenAPI schema is at `/docs`.

- [Architecture](#architecture)
- [Endpoints](#endpoints)
- [Field reference](#field-reference)
- [Error codes](#error-codes)
- [Configuration](#configuration)
- [Local storage and PHI](#local-storage-and-phi)
- [Accuracy and performance](#accuracy-and-performance)
- [Not implemented yet](#not-implemented-yet)

---

## Architecture

Two independent models run over the same audio and their outputs are joined on
the time axis:

- **Who spoke when** — SpeechBrain: CRDNN voice-activity detection, ECAPA-TDNN
  speaker embeddings over overlapping sub-segments, spectral clustering.
- **What was said** — Whisper (Faster-Whisper by default) with word-level
  timestamps.
- **Join** — each word is assigned to the speaker whose segments overlap it
  most, then consecutive words with the same speaker become one turn.

```
upload → validate → ffmpeg to 16 kHz mono WAV ─┬─→ SpeechBrain diarization ─┐
                                               │                            ├─→ align → turns
                                               └─→ Whisper word timestamps ──┘
```

Both models read the identical converted WAV. That is deliberate: alignment
compares Whisper word timestamps to SpeechBrain segment boundaries, so the two
must share one time base.

Word-level timestamps matter for the same reason. Whisper's own segments break
on acoustic and linguistic boundaries that ignore speaker changes, so a single
segment routinely spans a clinician's question and the patient's answer.
Aligning per word lets a speaker change land mid-sentence, where it belongs.

### Engine modes

`STT_ENGINE_MODE` selects what backs the endpoints:

- `local` (default) — models load in the backend process. Requires the optional
  dependency group: `uv sync --extra stt`.
- `remote` — proxy to the standalone `sst_v1` service at `STT_BASE_URL`. No
  diarization; `/diarize` returns 503.

---

## Endpoints

### `POST /api/v1/stt/diarize`

Transcribe an audio file and label each turn with a speaker. This is the main
endpoint.

**Request** — `multipart/form-data`

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `file` | file | yes | — | Encounter audio. See [supported formats](#supported-formats). |
| `num_speakers` | int | no | `DIARIZATION_NUM_SPEAKERS` (2) | Known speaker count. Blank uses the configured default. `0` forces automatic estimation. |
| `min_speakers` | int | no | `1` | Lower bound when estimating. |
| `max_speakers` | int | no | `6` | Upper bound when estimating. |
| `language` | string | no | `en` | BCP-47 code. Blank auto-detects. |
| `speaker_names` | JSON string | no | — | Map cluster ids to display names, e.g. `{"speaker_0": "Doctor", "speaker_1": "Patient"}`. |
| `encounter_id` | string | no | — | Attach the transcript to an existing encounter. |
| `save_audio` | bool | no | `true` | Persist audio and result to disk. |

**Supply `num_speakers` when you know it.** Automatic estimation is the least
reliable part of the pipeline: on the most acoustically confusable evaluation
pair it found three speakers instead of two and diarization error rose from
0.40% to 14.59%. An outpatient encounter is usually two-party, which is why the
default is 2 rather than automatic.

**Response** — `200 OK`, `DiarizedTranscriptResponse`

```json
{
  "job_id": "9f2c1d7a4b8e4c1fa0d3e5b6c7a8d9e0",
  "encounter_id": null,
  "created_at": "2026-08-27T05:31:12.482913+00:00",
  "text": "What symptoms are you experiencing? I have had a fever for three days.",
  "labelled_text": "Doctor: What symptoms are you experiencing?\nPatient: I have had a fever for three days.",
  "language": "en",
  "num_speakers": 2,
  "speakers": ["speaker_0", "speaker_1"],
  "turns": [
    {
      "speaker_id": "speaker_0",
      "speaker_name": "Doctor",
      "start": 0.52,
      "end": 3.18,
      "text": "What symptoms are you experiencing?",
      "confidence": 0.941
    },
    {
      "speaker_id": "speaker_1",
      "speaker_name": "Patient",
      "start": 3.86,
      "end": 7.02,
      "text": "I have had a fever for three days.",
      "confidence": 0.917
    }
  ],
  "segments": [
    { "start": 0.5, "end": 3.24, "speaker_id": "speaker_0", "speaker_name": "Doctor" },
    { "start": 3.8, "end": 7.1, "speaker_id": "speaker_1", "speaker_name": "Patient" }
  ],
  "audio": {
    "filename": "encounter.wav",
    "duration": 7.6,
    "sample_rate": 16000,
    "size_bytes": 243244,
    "stored": true,
    "stored_path": "/app/backend/data/audio/2026-08-27/9f2c1d.../audio.wav"
  },
  "metrics": {
    "audio_duration": 7.6,
    "diarization_seconds": 0.31,
    "transcription_seconds": 0.22,
    "total_seconds": 0.71,
    "diarization_rtf": 0.0408,
    "transcription_rtf": 0.0289,
    "total_rtf": 0.0934,
    "stage_times": { "vad": 0.24, "embedding": 0.05, "clustering": 0.02 }
  },
  "engine": {
    "mode": "local",
    "device": "cuda:0",
    "whisper_backend": "faster_whisper",
    "whisper_model": "small.en",
    "vad_model": "speechbrain/vad-crdnn-libriparty",
    "embedding_model": "speechbrain/spkrec-ecapa-voxceleb",
    "clustering_method": "spectral"
  },
  "diagnostics": {
    "n_vad_regions": 2,
    "n_subsegments": 9,
    "mean_pairwise_cosine": 0.2666,
    "clustering_pval": 0.8889,
    "oracle_num_speakers": 2,
    "unknown_speaker_words": 0
  }
}
```

```bash
curl -X POST http://127.0.0.1:10200/api/v1/stt/diarize \
  -F "file=@encounter.wav" \
  -F "num_speakers=2" \
  -F 'speaker_names={"speaker_0":"Doctor","speaker_1":"Patient"}'
```

### `POST /api/v1/stt/transcribe`

Transcribe to plain text with no speaker labels. Request and response are
unchanged from the previous sst_v1-proxy implementation, so existing callers
keep working.

**Request** — `multipart/form-data`

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `file` | file | yes | — | Encounter audio. |
| `engine` | string | no | — | Engine hint. Honoured in `remote` mode only. |
| `language` | string | no | `en` | BCP-47 code. Blank auto-detects. |
| `task` | string | no | `transcribe` | Local mode supports `transcribe` only. |
| `encounter_id` | string | no | — | Attach the transcript to an encounter. |

**Response** — `200 OK`, `TranscriptResult`

```json
{
  "text": "Patient reports a fever for three days.",
  "language": "en",
  "segments": [{ "id": 0, "start": 0.0, "end": 3.4, "text": "Patient reports a fever for three days." }],
  "audio_duration": 3.6,
  "processing_time": 0.19,
  "real_time_factor": 0.0528,
  "engine": "local:faster_whisper",
  "model": "small.en",
  "source": "upload",
  "job_id": "1a2b3c...",
  "num_speakers": null
}
```

```bash
curl -X POST http://127.0.0.1:10200/api/v1/stt/transcribe -F "file=@encounter.wav"
```

### `GET /api/v1/stt/engine`

Active engine, device and model readiness. Does not trigger a model load, so it
is safe for probes.

```json
{
  "mode": "local",
  "device": "cuda:0",
  "whisper_model": "small.en",
  "whisper_backend": "faster_whisper",
  "compute_type": "float16",
  "diarization_enabled": true,
  "default_num_speakers": 2,
  "models_loaded": true,
  "dependencies_available": true,
  "detail": null,
  "extra": {}
}
```

### `GET /api/v1/stt/jobs`

List stored jobs, newest first. Summaries only — no transcript text.

Query parameters: `limit` (1–500, default 50), `offset` (default 0).

```json
{
  "total": 12,
  "limit": 50,
  "offset": 0,
  "jobs": [
    {
      "job_id": "9f2c1d7a...",
      "created_date": "2026-08-27",
      "created_at": "2026-08-27T05:31:12.482913+00:00",
      "encounter_id": null,
      "language": "en",
      "num_speakers": 2,
      "audio_duration": 7.6,
      "has_result": true,
      "has_audio": true
    }
  ]
}
```

### `GET /api/v1/stt/jobs/{job_id}`

Return the persisted result payload. The shape matches whichever endpoint
created it: `DiarizedTranscriptResponse` for `/diarize`, `TranscriptResult` for
`/transcribe`. `404` if there is no such job.

### `GET /api/v1/stt/jobs/{job_id}/audio`

Stream the audio a job was transcribed from, as `audio/wav`. `404` if the job
does not exist or was created with `save_audio=false`.

This serves the **converted** 16 kHz mono WAV, not the original upload, because
turn timestamps are measured against the audio the models read. On the same
source the two disagree: a 47.196 s mp3 converted to a 47.097 s WAV, so seeking
in the original would drift by ~100 ms.

`Range` is supported (Starlette answers with `206 Partial Content`), which is
what lets a client seek straight to `turn.start` to replay a single turn:

```js
audio.src = `/api/v1/stt/jobs/${jobId}/audio`;
audio.currentTime = turn.start;
audio.play();
```

The response is marked `Cache-Control: private, no-store` — this is PHI and
should not land in a shared or disk cache.

`job_id` must be 32 hex characters. Lookups interpolate it into a glob pattern,
so anything else is rejected as a non-existent job before touching the
filesystem; the same guard covers the two endpoints below.

### `DELETE /api/v1/stt/jobs/{job_id}`

Delete a job directory including its audio. `404` if there is no such job.

```json
{ "job_id": "9f2c1d7a...", "deleted": true }
```

### `WS /api/v1/stt/live`

Live-recording proxy to sst_v1. Available in `remote` mode only; in `local` mode
it accepts the socket, sends `{"type": "error", "detail": "..."}` and closes.
See [Not implemented yet](#not-implemented-yet).

### Supported formats

`.wav` `.mp3` `.flac` `.ogg` `.oga` `.opus` `.m4a` `.mp4` `.aac` `.webm` `.mkv`
`.wma` `.aiff` `.amr`

Everything is converted to 16 kHz mono 16-bit PCM WAV by ffmpeg before
inference, so browser `MediaRecorder` WebM/Opus works without client-side
transcoding.

---

## Field reference

Fields whose meaning is not obvious from the name:

- **`speaker_id`** — an *anonymous* cluster label (`speaker_0`, `speaker_1`).
  Diarization determines that two stretches of audio are the same voice; it has
  no idea which one is the clinician. Numbering is not stable across requests:
  `speaker_0` in one recording is unrelated to `speaker_0` in another.
- **`speaker_name`** — the display name from `speaker_names`, falling back to
  `speaker_id`. Words that could not be attributed to any speaker get
  `unknown`.
- **`turns` vs `segments`** — `turns` carry text and are what you render;
  `segments` are the raw diarization timeline with no text, useful for a
  waveform overlay or for debugging a mislabelled turn.
- **`confidence`** — mean Whisper word probability for the turn. This is
  *transcription* confidence. Speaker-attribution confidence is not currently
  exposed.
- **`real_time_factor`** — processing seconds per audio second. Below 1.0 is
  faster than real time.
- **`metrics.total_seconds`** — the whole request: validation, ffmpeg
  conversion, waiting for the device, and inference. Under load it exceeds
  `diarization_seconds + transcription_seconds` because requests queue for the
  single GPU. Use the stage numbers to judge model speed and this one to judge
  the latency a caller sees.
- **`mean_pairwise_cosine`** — average cosine similarity between speaker
  embeddings across the recording. High values on a multi-speaker recording
  mean the voices were hard to tell apart, which is the main predictor of
  speaker confusion.
- **`clustering_method`** — `spectral` normally; `agglomerative` on very short
  recordings where the eigen-gap heuristic is unreliable;
  `single_speaker_screen` when every embedding looked like one person;
  `trivial` for a single sub-segment.
- **`unknown_speaker_words`** — transcribed words that overlapped no speaker
  segment. Usually Whisper producing text over audio the VAD rejected. These
  words are kept in the transcript under the `unknown` speaker rather than
  dropped, because losing clinical content is worse than an unlabelled line.

---

## Error codes

| Status | Meaning | Typical cause |
|---|---|---|
| 400 | Validation failed | Empty file, unsupported extension, over `MAX_AUDIO_SIZE_MB`, over `MAX_AUDIO_DURATION_SECONDS`, corrupt audio, malformed `speaker_names` JSON, `task=translate` in local mode |
| 404 | Not found | Unknown `job_id` |
| 422 | Schema validation failed | Missing `file`, out-of-range query parameter |
| 500 | Inference error | Unexpected model failure |
| 502 | Upstream unavailable | `remote` mode and sst_v1 is unreachable |
| 503 | Not configured | `stt` extra not installed, models cannot load, ffmpeg missing, diarization disabled, `/diarize` in `remote` mode |
| 504 | Upstream timeout | `remote` mode and sst_v1 exceeded `STT_TIMEOUT_SECONDS` |

Errors use FastAPI's standard shape:

```json
{ "detail": "Audio is 78.3 MB, which exceeds the 50 MB limit." }
```

### Concurrency

There is one GPU and the models are not safe to call concurrently, so requests
are queued by a semaphore and run one at a time. Concurrent callers **wait**;
they do not fail. Size client timeouts for queueing delay under load, not just
for a single request's inference time.

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `STT_ENGINE_MODE` | `local` | `local` runs models in-process; `remote` proxies to sst_v1 |
| `STT_DEVICE` | `auto` | `auto`, `cuda`, or `cpu`. `auto` uses CUDA when available |
| `STT_MODEL_PRELOAD` | `false` | Load models at startup instead of on first request |
| `WHISPER_MODEL` | `small.en` | Whisper model identifier |
| `WHISPER_BACKEND` | `faster_whisper` | `faster_whisper` or `openai_whisper` |
| `WHISPER_COMPUTE_TYPE` | `float16` | CTranslate2 compute type; auto-downgraded to `int8` on CPU |
| `WHISPER_LANGUAGE` | `en` | Default language; blank auto-detects |
| `DIARIZATION_ENABLED` | `true` | When false, `/diarize` returns 503 and no diarization models load |
| `DIARIZATION_NUM_SPEAKERS` | `2` | Default speaker count. Blank means estimate |
| `DIARIZATION_MIN_SPEAKERS` | `1` | Lower bound when estimating |
| `DIARIZATION_MAX_SPEAKERS` | `6` | Upper bound when estimating |
| `DIARIZATION_WINDOW_SEC` | `1.5` | Sub-segment window for speaker embeddings |
| `DIARIZATION_SHIFT_SEC` | `0.75` | Sub-segment hop |
| `DIARIZATION_VAD_SOURCE` | `speechbrain/vad-crdnn-libriparty` | VAD model |
| `DIARIZATION_EMBEDDING_SOURCE` | `speechbrain/spkrec-ecapa-voxceleb` | Speaker-embedding model |
| `AUDIO_STORAGE_DIR` | `backend/data/audio` | Where audio and results are written |
| `MODEL_CACHE_DIR` | `backend/data/models` | Downloaded model weights |
| `MAX_AUDIO_SIZE_MB` | `50` | Upload size ceiling |
| `MAX_AUDIO_DURATION_SECONDS` | `3600` | Recording length ceiling |

`DIARIZATION_WINDOW_SEC` is the core accuracy trade-off: longer windows give
more reliable embeddings but blur turn boundaries; shorter windows sharpen
boundaries but produce noisier embeddings.

### Requirements

- **ffmpeg and ffprobe on `PATH`.** Missing ffmpeg returns 503 on any upload.
- **The `stt` extra**: `uv sync --extra stt`.
- **A matching torch build.** The wheel must target the host GPU architecture.
  Blackwell cards (compute capability 12.0, RTX 50-series) need CUDA 12.8 or
  newer; an older build installs cleanly and then fails at the first GPU
  operation with `no kernel image is available for execution on the device`.

CPU-only hosts work: if CUDA is unavailable or model loading on GPU fails, the
engine falls back to CPU and logs a warning rather than taking the API down.
Expect a real-time factor well above 1.0 on CPU with `small.en`.

---

## Local storage and PHI

`save_audio=true` (the default) writes one directory per job:

```
{AUDIO_STORAGE_DIR}/2026-08-27/<job_id>/
├── original.<ext>   bytes exactly as uploaded
├── audio.wav        16 kHz mono, the samples the models consumed
└── result.json      the full API response
```

**The audio and the transcript inside `result.json` are PHI.** Local disk is a
prototype measure with real gaps, all of which are open items rather than
solved problems:

- No encryption at rest and no access control beyond filesystem permissions.
- No automatic expiry — nothing is deleted unless `DELETE /jobs/{job_id}` is
  called. The retention period for audio versus transcript is still an open
  question in the feature spec.
- The `/jobs`, `/jobs/{job_id}` and `/jobs/{job_id}/audio` endpoints are not yet JWT-gated, matching the
  rest of the STT and SOAP routes. RBAC is specified but not implemented.

Log lines carry job ids, durations and sizes only, never transcript text.
`save_audio=false` routes the audio through a temporary directory that is
removed when the request finishes; the file still has to touch the disk because
ffmpeg and SpeechBrain's VAD are file-based.

---

## Accuracy and performance

Measured on an RTX 5060 Ti with `small.en`, against test recordings built from
mini-LibriSpeech (real voices, verified transcripts, exact speaker timelines).
Reproduce with the harness in `sst_v1/scripts/`.

| Test recording | Speakers | DER | WER | Word-speaker accuracy |
|---|---|---|---|---|
| Two-party, long turns | 2 | 1.50% | 3.76% | 100% |
| Control, long turns | 2 | 1.12% | 3.82% | 100% |
| Short turns (16 turns / 34 s) | 2 | 0.40% | 5.26% | 100% |
| Most confusable pair, count given | 2 | 0.40% | 8.47% | 100% |
| Most confusable pair, count estimated | 2 → **3 found** | **14.59%** | 8.47% | 90.17% |
| Three-party | 3 | 0.47% | 8.48% | 98.64% |

Real-time factors: diarization 0.008–0.05, transcription 0.02–0.03. A 15-minute
consultation transcribes in roughly 30–60 seconds of wall clock.

Read these as an optimistic bound. The recordings have clean turn-taking: no
overlapping speech, no interruptions, no crosstalk, and read prose rather than
clinical dialogue in a room with background noise. The two numbers to watch on
real audio are `speaker_confusion` and `mean_pairwise_cosine`.

The single clear weakness is speaker-count estimation, hence the default of 2.

---

## Not implemented yet

- **Live streaming diarization.** The local engine is file-based. Streaming
  needs a rolling buffer, incremental clustering with cluster identity carried
  across windows, provisional labels sent to the UI, revision events when a
  label changes, and a full offline pass at the end of the recording to correct
  the transcript. `WS /api/v1/stt/live` currently only proxies to sst_v1.
- **Speaker identification.** Labels are anonymous clusters. Mapping them to
  real people needs either manual assignment in the UI (supported today via
  `speaker_names`) or voice enrolment: store a reference ECAPA embedding per
  clinician and match live embeddings against it, falling back to
  `unknown` below a confidence threshold.
- **Overlapping speech.** Segments are non-overlapping by construction:
  overlaps between adjacent sub-segments are split down the middle. Genuine
  simultaneous speech is assigned to one speaker. SpeechBrain's SepFormer
  could separate overlapping voices if this proves to matter.
- **Speaker-attribution confidence.** `confidence` reports transcription
  confidence only. A per-word attribution score (embedding distance to the
  assigned cluster centroid) would let the UI flag uncertain turns.
- **Async job submission.** Requests are synchronous. Long recordings hold the
  connection open for their whole processing time; a submit-and-poll interface
  would be needed for hour-long audio at scale.
- **RBAC.** No route here is JWT-gated yet.
