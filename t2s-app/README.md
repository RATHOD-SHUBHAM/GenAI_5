# Text-to-SQL App

Full-stack Text-to-SQL application built on top of the learning code in `T2S/`.

## Stack

- **Backend:** FastAPI, SQLAlchemy, OpenAI, Pinecone, Redis Cloud
- **Frontend:** Next.js, CSS
- **Infra:** Docker (no local Redis — uses Redis Cloud from `.env`)

## Project layout

```text
t2s-app/
  backend/     FastAPI API
  frontend/    Next.js UI
  docker-compose.yml
```

Learning scripts stay in `T2S/` and are not imported by this app.

**Backend deep dive:** see [`learning/backend_api_flow_guide.md`](learning/backend_api_flow_guide.md) for file-by-file flow, `yield`, `Depends`, Redis cache, and Docker.

**Test questions:** see [`learning/test_questions.md`](learning/test_questions.md) for sample queries (easy → hard + cache tests).

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Python 3.12+ (uv can install it: `uv python install 3.12`)
- Node 20+
- `GenAI_5/.env` with all required keys (see `.env.example`)

## Run locally (without Docker)

### Backend

```bash
cd t2s-app/backend
uv sync
uv run uvicorn app.main:app --reload
```

`uv sync` creates `.venv` and installs locked deps from `uv.lock`.  
`uv run` executes inside that venv — no `source activate` needed.

Add a dependency later: `uv add <package>` (updates `pyproject.toml` and `uv.lock`).

API: http://localhost:8000  
Docs: http://localhost:8000/docs

### Frontend

```bash
cd t2s-app/frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

If you see `__webpack_modules__[moduleId] is not a function` after many UI edits, clear the dev cache:

```bash
npm run dev:clean
# or: rm -rf .next && npm run dev
```

UI: http://localhost:3000

## API

### `GET /api/health`

Checks Neon (`SELECT 1`) and Redis (`PING`).

### `POST /api/ask`

```json
{ "question": "average salary by department?" }
```

Successful responses are cached in Redis Cloud for `CACHE_TTL_SECONDS` (default 600).

## Docker

From `t2s-app/`:

```bash
docker compose up --build
```

Uses `../.env` for API secrets. No Redis container — API connects to Redis Cloud over the internet.

## Docker Hub

Build and push (replace `youruser`):

```bash
docker build -t youruser/t2s-api ./backend
docker build -t youruser/t2s-frontend --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000 ./frontend

docker push youruser/t2s-api
docker push youruser/t2s-frontend
```

Run pulled images with your own env vars — never bake secrets into images.

## Test with curl

```bash
curl -s http://localhost:8000/api/health | jq

curl -s -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "How many employees are in each department?"}' | jq
```

Ask the same question twice — second response should have `"cached": true`.
