from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_client import make_asgi_app

from app.api.routes_auth import router as auth_router
from app.api.routes_bot import router as bot_router
from app.api.routes_feed import router as feed_router
from app.api.routes_rag import router as rag_router
from app.api.routes_billing import router as billing_router
from app.bot.stt import load_model as load_whisper_model
from app.celery_app import celery_app
from app.config import settings
from app.observability.metrics import request_latency_seconds, queue_depth

# 1. Resolve absolute path and create the folder immediately on file load
absolute_media_path = os.path.abspath(settings.media_root)
os.makedirs(absolute_media_path, exist_ok=True)

_QUEUE_DEPTH_SAMPLE_INTERVAL_SECONDS = 30


async def _sample_queue_depth() -> None:
    """Periodically samples Celery's queue depth (active + reserved task
    counts across workers) into the queue_depth histogram. Runs as a
    background asyncio task rather than a Celery beat job — beat was
    intentionally removed earlier (see session_tasks.py), and this only
    needs a lightweight in-process loop, not a separate scheduled task.
    control.inspect() calls out to the broker and can be slow/fail if no
    worker is up — wrapped so a bad sample never crashes the loop."""
    inspector = celery_app.control.inspect()
    while True:
        try:
            active = inspector.active() or {}
            reserved = inspector.reserved() or {}
            total = sum(len(tasks) for tasks in active.values()) + sum(
                len(tasks) for tasks in reserved.values()
            )
            queue_depth.labels(queue_name="celery").observe(total)
        except Exception:
            # Broker unreachable or no workers running — skip this sample,
            # try again next interval rather than crashing the app.
            pass
        await asyncio.sleep(_QUEUE_DEPTH_SAMPLE_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Whisper is loaded once at startup, not per-request (Sec 3.1).
    load_whisper_model()

    # LangSmith tracing is enabled via env vars (LANGSMITH_TRACING,
    # LANGSMITH_API_KEY, LANGSMITH_PROJECT) — @traceable calls throughout
    # bot/ pick these up automatically once set.
    os.environ.setdefault("LANGSMITH_TRACING", str(settings.langsmith_tracing).lower())
    os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)
    os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)

    sampler_task = asyncio.create_task(_sample_queue_depth())
    yield
    sampler_task.cancel()


app = FastAPI(title="Recipe Bot & Social Feed API", lifespan=lifespan)

# The frontend runs on a different port (Vite dev server, :5173) than the
# API (:8000) — CORS with allow_credentials is required for the httpOnly
# auth cookies (Sec 6) to be sent/received cross-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def track_request_latency(request: Request, call_next):
    """Sec 5 — request_latency_seconds, labeled by endpoint. Uses
    request.url.path directly rather than the matched route template, so
    it's slightly higher-cardinality for path-parameterized routes (e.g.
    /bot/conversations/<uuid>/messages) than an ideal low-cardinality
    label — acceptable for now given traffic volume, worth revisiting
    with route-template labeling if cardinality becomes a real concern."""
    start = time.monotonic()
    response = await call_next(request)
    elapsed = time.monotonic() - start
    request_latency_seconds.labels(endpoint=request.url.path).observe(elapsed)
    return response


app.include_router(auth_router)
app.include_router(bot_router)
app.include_router(feed_router)
app.include_router(rag_router)
app.include_router(billing_router)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Serves uploaded post media and generated TTS audio (media/ volume,
# Sec 12.1) directly — fine for local dev; swapped for cloud object
# storage + CDN before the cloud-deployment step in Sec 10.
app.mount("/media", StaticFiles(directory=absolute_media_path), name="media")


@app.get("/health")
async def health():
    return {"status": "ok"}
