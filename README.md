# 🎙️ SST Model Evaluation

A **production-quality Speech-to-Text evaluation and benchmarking framework** built for internal R&D model-selection.

Supports **Whisper (local)**, **WhisperFlow (live streaming)**, **OpenAI Whisper (cloud)**, and a prepared architecture for **Faster-Whisper** — all behind a clean, pluggable engine interface.

---

## ✨ Features

| Feature | Details |
|---|---|
| **Audio file transcription** | POST `/api/v1/transcribe` — returns transcript, segments, RTF |
| **Live microphone streaming** | WebSocket `/api/v1/live` — partial + final transcripts |
| **Pluggable engine architecture** | Add new engines with zero API changes |
| **Benchmarking** | RTF, WER, CER, TTFT — JSON + CSV output |
| **Structured logging** | Loguru, rotating files, per-request correlation IDs |
| **Streamlit UI** | Upload tab + live microphone tab |
| **Full test suite** | pytest, mocked models, WebSocket tests |

---

## 📋 Requirements

| Dependency | Version |
|---|---|
| Python | ≥ 3.11 |
| uv | latest |
| ffmpeg | system-wide install |

---

## 🚀 Quick Start

### 1. Install uv (if not already installed)

```powershell
# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Clone and set up

```bash
cd sst-model-evaluation

# Create .env from the example
copy .env.example .env

# Install all dependencies (creates .venv automatically)
uv sync

# Install UI dependencies
uv sync --extra ui
```

### 3. Install ffmpeg

```powershell
# Windows (via winget)
winget install --id Gyan.FFmpeg

# Or download from https://ffmpeg.org/download.html
# and add to your system PATH
```

Verify:
```bash
ffmpeg -version
ffprobe -version
```

### 4. Pre-download the Whisper model

```bash
uv run python scripts/download_model.py --model base
```

### 5. Start the API server

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs

### 6. Start the Streamlit UI (second terminal)

```bash
uv run streamlit run frontend/streamlit_app.py
```

UI: http://localhost:8501

---

## ⚙️ Configuration

Copy `.env.example` to `.env` and adjust:

```dotenv
WHISPER_MODEL=base          # tiny|base|small|medium|large|large-v3
WHISPER_DEVICE=cpu          # cpu|cuda|mps
WHISPER_LANGUAGE=           # empty = auto-detect
WHISPER_TASK=transcribe     # transcribe|translate
DEFAULT_ENGINE=whisper
MAX_AUDIO_SIZE_MB=50
MAX_AUDIO_DURATION_SECONDS=300
LOG_LEVEL=INFO
```

> **Never** commit the real `.env` file. It is in `.gitignore`.

---

## 🏗️ Architecture

```
STTEngine (abstract base)
├── WhisperEngine          ← local Whisper, lazy loading, thread-pool offload
├── WhisperFlowEngine      ← real-time streaming (optional: uv sync --extra live)
├── OpenAIWhisperEngine    ← cloud API (optional: uv sync --extra openai)
└── FasterWhisperEngine    ← CTranslate2 stub (optional: uv sync --extra faster)
```

**Key design decisions:**

1. **Lazy model loading** — models load on first use, not at import time. API starts instantly.
2. **Load-once singleton** — the engine registry (`app/engines/__init__.py`) caches one instance per engine. No per-request reload.
3. **Thread-pool offload** — blocking ML inference runs in `asyncio`'s thread pool via `run_in_executor`. The FastAPI event loop is never blocked.
4. **Thread-safe loading** — a `threading.Lock` prevents duplicate concurrent loads.
5. **Clean dependency inversion** — API routes depend only on `STTEngine`, never on `WhisperEngine` directly.

---

## 📡 API Reference

### `GET /api/v1/health`
Liveness probe. Returns `{"status": "ok"}`.

### `GET /api/v1/ready`
Readiness probe. Returns engine registry and configuration summary.

### `POST /api/v1/transcribe`

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | File | ✅ | Audio file (mp3, wav, flac, ogg, m4a, webm) |
| `engine` | string | ❌ | `whisper` \| `whisperflow` \| `openai` (default: from settings) |
| `language` | string | ❌ | BCP-47 code (e.g. `en`) or empty for auto-detect |
| `task` | string | ❌ | `transcribe` \| `translate` |

**Response:**
```json
{
  "text": "Hello, this is a transcription.",
  "language": "en",
  "segments": [
    { "id": 0, "start": 0.0, "end": 2.5, "text": "Hello, this is a transcription." }
  ],
  "audio_duration": 5.0,
  "processing_time": 0.5,
  "real_time_factor": 0.1,
  "engine": "whisper",
  "model": "base"
}
```

**RTF explained:**
- `RTF = processing_time / audio_duration`
- RTF < 1.0 → faster than real-time ✅
- RTF > 1.0 → slower than real-time (use a smaller model or GPU)

### `WebSocket /api/v1/live`

**Protocol:**
```json
// Client → Server: start session
{ "type": "start", "engine": "whisper", "language": "en" }

// Server → Client: session confirmed
{ "type": "session_started", "session_id": "abc12345" }

// Client → Server: raw audio bytes (binary frames)

// Server → Client: partial result
{ "type": "partial", "text": "Hello...", "latency_ms": 450.0 }

// Client → Server: end of audio
{ "type": "stop" }

// Server → Client: final result
{ "type": "final", "text": "Hello world.", "latency_ms": 980.0 }
{ "type": "session_ended" }
```

---

## 🧪 Testing

```bash
# Run all tests (no model download needed)
uv run pytest -q

# Run with coverage
uv run pytest --cov=app --cov-report=term-missing

# Run only audio validation tests
uv run pytest tests/test_audio.py -v

# Run only upload API tests
uv run pytest tests/test_upload.py -v

# Run WebSocket tests
uv run pytest tests/test_live.py -v

# Run real-model smoke test (requires model download)
uv run pytest -m real_model -s
```

---

## 📊 Benchmarking

### Upload benchmark (batch)

```bash
# Put audio files in audio_samples/
# Optionally add <filename>.wav.ref.txt for WER/CER

uv run python scripts/benchmark.py upload \
    --audio-dir audio_samples/ \
    --engine whisper \
    --model base \
    --device cpu \
    --output-dir benchmarks/results/
```

### Live benchmark (streaming simulation)

```bash
uv run python scripts/benchmark.py live \
    --audio audio_samples/sample.wav \
    --engine whisper \
    --chunk-ms 500
```

Results are saved to `benchmarks/results/` as both `.json` and `.csv`.

> **Important:** Never fabricate reference transcripts. Only include verified ground-truth `.ref.txt` files.

---

## 🔊 Supported Audio Formats

| Format | Extension | Notes |
|---|---|---|
| WAV | `.wav` | Best quality; recommended |
| MP3 | `.mp3` | Widely supported |
| FLAC | `.flac` | Lossless |
| OGG | `.ogg` | Open format |
| M4A | `.m4a` | AAC container |
| MP4 | `.mp4` | Video + audio |
| WebM | `.webm` | Browser recording |

All formats are converted to 16 kHz mono WAV before inference via ffmpeg.

---

## 🤖 Model Information

| Model | Size | Speed (CPU) | Accuracy |
|---|---|---|---|
| `tiny` | 39M params | Very fast | Low |
| `base` | 74M params | Fast ✅ recommended for dev | Good |
| `small` | 244M params | Moderate | Better |
| `medium` | 769M params | Slow | High |
| `large-v3` | 1550M params | Very slow | Best |

Models are cached at `~/.cache/whisper` after the first download.

---

## ⚠️ Known Limitations

1. **WhisperFlow** — the `whisperflow` package must be installed separately (`uv sync --extra live`). The live tab uses a JS WebSocket client that requires HTTPS in production.
2. **FasterWhisperEngine** — architecture is prepared but implementation is a stub. PRs welcome.
3. **OpenAI engine** — costs money per minute of audio. Monitor usage.
4. **Large models on CPU** — `large-v3` can take many times the audio duration on CPU. Use `base` for development.
5. **Concurrent requests** — model inference is serialised per engine instance (thread lock). Add a worker pool for high concurrency.

---

## 🔧 Troubleshooting

| Problem | Solution |
|---|---|
| `ffmpeg: command not found` | Install ffmpeg and add to PATH |
| Model download slow | Run `scripts/download_model.py` once; then it's cached |
| `RuntimeError: WhisperFlow not installed` | `uv sync --extra live` |
| WebSocket disconnects immediately | Check CORS settings; try `--host 0.0.0.0` |
| `CUDA out of memory` | Use a smaller model or switch to CPU: `WHISPER_DEVICE=cpu` |
| Port 8000 in use | `uv run uvicorn app.main:app --port 8001` |

---

## 📁 Project Structure

```
sst-model-evaluation/
├── app/
│   ├── api/             # FastAPI route handlers
│   ├── audio/           # Validation, conversion, chunking
│   ├── core/            # Config, logging, metrics helpers
│   ├── engines/         # STTEngine base + concrete implementations
│   ├── schemas/         # Pydantic request/response models
│   └── main.py          # App entry point (wiring only)
├── frontend/
│   └── streamlit_app.py # Upload + Live UI
├── tests/               # pytest unit + integration tests
├── benchmarks/          # Benchmark runners + results/
├── scripts/             # download_model, benchmark CLI
├── audio_samples/       # Put test audio files here
├── .env.example         # Config template
└── pyproject.toml       # uv project definition
```

---

## 🔄 Recommended Git Workflow

```bash
# Feature development
git checkout -b feature/add-faster-whisper
# ... make changes ...
uv run pytest -q          # all tests green
uv run ruff check app/    # lint clean
git add -p
git commit -m "feat: implement FasterWhisperEngine"
git push origin feature/add-faster-whisper
# Open pull request → merge to main
```

Never commit: `.env`, `*.pt`, `*.pth`, `audio_samples/*.wav`, `logs/`

---

## 📄 License

MIT — for internal R&D use.
