# Recipe Bot & Social Feed

Multilingual recipe Q&A bot (text/voice, dual text+audio replies) plus a
food-focused social feed. See `docs/` context in the original PRDs for
the full spec — this README is just "how do I run it."

## Project layout

```
backend/    FastAPI + LangGraph + Celery — see backend/app for the API
frontend/   React + Vite — see frontend/src
eval/       Eval harness (pytest) — see eval/README.md
media/      Local-disk media storage (dev only — Sec 2)
```

## First-time setup

1. **Copy the env template and fill in real values:**

   ```bash
   cp .env.example .env
   ```

   You'll need: a Groq API key, a Neon Postgres connection string (both
   async `postgresql+asyncpg://` and sync `postgresql+psycopg2://`
   forms), a CloudAMQP broker URL, an Upstash Redis URL, and — if you
   want the optional doc-RAG feature — a Qdrant Cloud URL + API key.
   GitHub OAuth client ID/secret are optional (email/password auth works
   without them).

2. **Run the database migration** (against your real Neon Postgres, using
   the sync URL):

   ```bash
   cd backend
   pip install -r requirements.txt
   alembic upgrade head
   ```

3. **Start everything:**

   ```bash
   docker-compose up --build
   ```

   - Backend: http://localhost:8000 (docs at `/docs`)
   - Frontend: http://localhost:5173

   `docker-compose.yml`'s `eval` service is excluded from a plain `up`
   (it's behind the `eval` profile) — run it explicitly:

   ```bash
   docker-compose --profile eval run eval
   ```

## Running without Docker (local dev loop)

```bash
# Terminal 1 — backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# Terminal 2 — celery worker (needed for TTS pre-caching, post-processing,
# session-end memory summarization)
cd backend
celery -A app.celery_app worker --loglevel=INFO

# Terminal 3 — frontend
cd frontend
npm install
npm run dev
```

## Testing

```bash
# Backend / eval (offline-safe subset — no live Groq/network needed)
cd eval
pip install -r ../backend/requirements.txt
pytest -v -m "not requires_network"

# Frontend
cd frontend
npm install
npm run typecheck
npm test
```

## Known gaps (honest, not hidden)

- **Never run through Docker end-to-end** — this was built and tested in
  a sandbox without Docker available. `docker-compose build`/`up` should
  work (the Dockerfiles and compose config were carefully reviewed
  against real, verified library/tool docs) but has not actually been
  executed. Run it locally first and expect to debug at least one small
  issue — a missing env var is the most likely candidate.
- **The Alembic migration has only run against SQLite**, never against a
  real Postgres/Neon instance.
- **Groq, Whisper, Qdrant, and the sentence-transformers injection
  classifier have never made a real network call in testing** — every
  test involving them either mocked the call or was structurally
  verified up to the point of the (sandbox-blocked) network request.
  Expect to debug real-world quality issues here (prompt tuning, Whisper
  model size, etc.) that no amount of code review can substitute for.
- **The MediaRecorder voice-recording path in the frontend has not been
  tested in a real browser.**
- **Cloud deployment (swapping local disk for S3/Cloudinary, moving
  free-tier services to production config) is not done** — by design,
  this comes after local testing succeeds.

See `eval/README.md` for the evaluation framework specifically.
