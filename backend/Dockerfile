# syntax=docker/dockerfile:1

# No CUDA base image is needed even for GPU inference: the PyTorch wheels bundle
# their own CUDA runtime, and the NVIDIA container runtime injects the host
# driver. That keeps this image a few GB smaller than an nvidia/cuda base.
FROM python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /usr/local/bin/uv

# Build without the speech stack for a lean orchestrator that proxies to a
# remote STT service (STT_ENGINE_MODE=remote):  --build-arg INSTALL_STT=false
ARG INSTALL_STT=true

# Override when the host GPU needs a CUDA build other than the one on PyPI.
# Blackwell cards (compute capability 12.0, RTX 50-series) need CUDA >= 12.8;
# an older wheel installs cleanly and then fails at the first GPU operation
# with "no kernel image is available for execution on the device".
#   --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cu128
ARG TORCH_INDEX_URL=""

# HF_HOME and XDG_CACHE_HOME point every model cache at one directory, so a
# single volume covers all of them: HF for faster-whisper and SpeechBrain, XDG
# for openai-whisper.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=10200 \
    AUDIO_STORAGE_DIR=/app/backend/data/audio \
    MODEL_CACHE_DIR=/app/backend/data/models \
    HF_HOME=/app/backend/data/models/huggingface \
    XDG_CACHE_HOME=/app/backend/data/models/cache

# ffmpeg and ffprobe are required to accept audio uploads: every file is
# transcoded to 16 kHz mono WAV before inference, and ffprobe reads duration.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN if [ "$INSTALL_STT" = "true" ]; then \
        uv sync --frozen --no-dev --no-install-project --extra stt; \
    else \
        uv sync --frozen --no-dev --no-install-project; \
    fi \
    && if [ "$INSTALL_STT" = "true" ] && [ -n "$TORCH_INDEX_URL" ]; then \
        uv pip install --index-url "$TORCH_INDEX_URL" torch torchaudio; \
    fi

COPY backend/app ./app
COPY database/models.py /app/database/models.py
RUN if [ "$INSTALL_STT" = "true" ]; then \
        uv sync --frozen --no-dev --extra stt; \
    else \
        uv sync --frozen --no-dev; \
    fi

# Mount volumes here in production: audio is PHI and model weights are large.
RUN mkdir -p "$AUDIO_STORAGE_DIR" "$MODEL_CACHE_DIR"

EXPOSE 10200

# --no-sync matters now that dependencies live in an optional extra: without it
# `uv run` reconciles the environment against the lockfile's default set and
# uninstalls torch and friends on every start.
#
# /api/v1/health is deliberate rather than /api/v1/ready: readiness reports on
# model loading, which is lazy by default, so a cold container is healthy but
# not yet "ready".
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD ["uv", "run", "--no-sync", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:10200/api/v1/health')"]

CMD ["sh", "-c", "uv run --no-sync uvicorn app.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-10200}"]
