# ── Stage 1: builder ─────────────────────────────────────────────────────
# Full Python image so pip can compile any wheels that need build tools.
# Nothing from this stage ships except the installed site-packages.
FROM python:3.12 AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --target=/build/deps -r requirements.txt

# ── Stage 2: runtime ─────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# ffmpeg is required by openai-whisper for audio decoding.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m appuser
WORKDIR /app

# Dependency layer copied in before app code — editing app/ never busts
# this cache layer (Sec 12.4, point 3).
COPY --from=builder /build/deps /usr/local/lib/python3.12/site-packages

COPY app/ ./app/

RUN mkdir -p /app/media && chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/usr/local/lib/python3.12/site-packages

EXPOSE 8000

# Default command for the `backend` service; `celery-worker` overrides
# this in docker-compose.yml with the same image (Sec 12.2).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
