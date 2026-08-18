# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.12 AS uv

FROM python:3.14-slim AS builder
COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies from the lockfile first (layer-cached across builds)
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project --no-editable

# Install the project itself (non-editable, so the runtime stage only needs .venv)
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.14-slim AS runtime

# The mlx LLM backend is Apple-Silicon-only, so the image defaults to the
# OpenAI-compatible backend (LM Studio / Ollama) via BANKBOT_* env overrides.
ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    BANKBOT_LLM_BACKEND=openai \
    BANKBOT_LLM_HOST=host.docker.internal \
    BANKBOT_LLM_PORT=1234

# tesseract-ocr is required to OCR scanned FNB statements.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/data /app/statements

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY config.yaml.example config.yaml

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["bankbot", "serve", "--host", "0.0.0.0", "--port", "8000"]
