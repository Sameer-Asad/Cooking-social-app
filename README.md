# Dastarkhwan — Recipe Bot & Social Feed

A multilingual recipe Q&A bot (text or voice in, text + audio replies out) combined with a food-focused social feed — ask about a dish, get a grounded answer with optional document context, then share what you cooked.

## ✨ Features

- 🗣️ **Multilingual Q&A** — ask by typing or voice, in English, Urdu, Hindi, or beyond; replies come back as text + generated audio
- 🧠 **Agentic bot** — LangGraph-orchestrated agent with web search + tool-calling, backed by Groq
- 📄 **Optional document RAG** — upload a `.txt`, `.md`, `.pdf`, or `.docx` file and the bot answers using it for that conversation
- 💬 **Rolling conversation memory** — older turns are summarized instead of dropped, so long sessions stay coherent without blowing the context window
- 📸 **Social feed** — share photos/videos of what you cooked, like, and comment
- 💳 **Pro subscription** — Lemon Squeezy–powered upgrade for higher daily limits
- 📊 **Full observability** — LangSmith tracing, Prometheus metrics, Grafana dashboards

## 📸 Screenshots / Demo

> _Add screenshots or a short demo GIF here._

| Ask | Feed |
|---|---|
| _screenshot placeholder_ | _screenshot placeholder_ |

## 🗂️ Project Structure

```text
dastarkhwan/
├── backend/
│   ├── app/
│   ├── eval/
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   ├── Dockerfile
│   └── package.json
├── media/
│   ├── audio/
│   ├── images/
│   └── videos/
├── .github/
│   └── workflows/
├── docker-compose.yml
├── .env.example
└── README.md
```

### 🔍 Directory Breakdown & Core Functions

| Folder / File | Core Purpose & Responsibility |
|---|---|
| `backend/app/` | FastAPI application — routes, auth, the bot's LangGraph agent, RAG pipeline, rate limiting, and Celery task definitions |
| `backend/eval/` | Offline evaluation harness — LLM-as-judge scoring against a golden dataset, run separately from normal CI |
| `frontend/src/` | React + Vite client — chat UI, session sidebar, social feed, auth, and billing pages |
| `media/` | Local-disk storage for uploaded post images/videos and generated TTS audio (dev only — swapped for object storage in production) |
| `.github/workflows/` | CI pipeline — backend lint/import checks and frontend test/build checks on every push |
| `docker-compose.yml` | Orchestrates the backend, Celery worker, and frontend as one local stack |
| `.env.example` | Template listing every environment variable the app expects |

## 🛠️ Tech Stack

- 🐍 **Backend:** FastAPI, SQLAlchemy (async), Alembic
- 🕸️ **Agent orchestration:** LangGraph, LangChain Core, Groq (LLM inference)
- 🎙️ **Voice:** OpenAI Whisper (speech-to-text), gTTS (text-to-speech)
- 📚 **RAG:** Qdrant (vector search), sentence-transformers (embeddings)
- ⚙️ **Background jobs:** Celery, CloudAMQP (broker), Upstash Redis (result backend + cache)
- 🐘 **Database:** PostgreSQL (Neon)
- ⚛️ **Frontend:** React, Vite, TypeScript, Vitest + Testing Library
- 💳 **Billing:** Lemon Squeezy
- 📈 **Observability:** LangSmith, Prometheus, Grafana

## 🚀 Installation & Usage

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/dastarkhwan.git
cd dastarkhwan
```

### 2. Configure environment variables

```bash
cp .env.example backend/.env
```

Fill in real values for: Groq API key, Neon Postgres URL (async + sync forms), CloudAMQP broker URL, Upstash Redis URL, Qdrant URL/key (optional, for RAG), Lemon Squeezy API key/store/variant IDs (optional, for billing), and LangSmith API key (optional, for tracing).

### 3. Install dependencies

```bash
# Backend
cd backend
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

### 4. Run database migrations

```bash
cd backend
alembic upgrade head
```

### 5. Start the app

```bash
# Terminal 1 — backend
cd backend
uvicorn app.main:app --reload

# Terminal 2 — Celery worker
cd backend
celery -A app.celery_app worker --loglevel=info

# Terminal 3 — frontend
cd frontend
npm run dev
```

Backend: `http://localhost:8000` (docs at `/docs`) · Frontend: `http://localhost:5173`

### Or, with Docker

```bash
docker-compose up --build
```

## 🧪 Running Tests

```bash
# Frontend
cd frontend
npm run test

# Backend — see backend/eval for the evaluation harness
```

