# syntax=docker/dockerfile:1

FROM python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=10200

WORKDIR /app/backend

COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/app ./app
COPY database/models.py /app/database/models.py
RUN uv sync --frozen --no-dev

EXPOSE 10200

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD ["uv", "run", "--no-dev", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:10200/api/v1/health')"]

CMD ["sh", "-c", "uv run --no-dev uvicorn app.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-10200}"]
