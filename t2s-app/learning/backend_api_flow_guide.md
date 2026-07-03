# Backend & API Flow Guide

This guide explains how the **t2s-app** backend works — file by file, request by request.

It builds on what you learned in `T2S/rag/basics_5_self_improve.py` and shows how that script became a production-style FastAPI service.

---

## What changed from learning scripts to the app?

| Learning (`T2S/`) | App (`t2s-app/backend/`) |
|-------------------|--------------------------|
| Run `python basics_5_self_improve.py` | Run `uvicorn app.main:app` |
| `print()` results | Return JSON over HTTP |
| Global `engine`, `client` at module level | Created once in `lifespan`, stored on `app.state` |
| `main()` entry point | `POST /api/ask` route |
| No cache | Redis Cloud cache for duplicate questions |
| No Docker | `Dockerfile` + `docker-compose.yml` |

**The brain (RAG + self-improvement) did not change.** We wrapped it in HTTP, config, cache, and deployment.

---

## Project layout

```text
t2s-app/
├── docker-compose.yml          # run api (+ frontend) as containers
├── learning/
│   └── backend_api_flow_guide.md   ← you are here
└── backend/
    ├── Dockerfile              # package API into a container image (uv)
    ├── pyproject.toml          # Python dependencies (uv)
    ├── uv.lock                 # locked versions (commit this)
    └── app/
        ├── main.py             # FastAPI app + startup/shutdown (lifespan)
        ├── config.py           # read GenAI_5/.env
        ├── dependencies.py     # inject shared clients into routes
        ├── api/
        │   ├── schemas.py      # Pydantic request/response models
        │   └── routes/
        │       ├── ask.py      # POST /api/ask
        │       └── health.py   # GET /api/health
        ├── services/
        │   ├── pipeline.py     # RAG + self-improvement loop (from basics_5)
        │   ├── sql_runner.py   # execute SQL on Neon
        │   └── cache.py        # Redis cache-aside
        └── core/
            ├── schema_chunks.py  # build schema text from Neon
            └── vector_db.py      # Pinecone + OpenAI embeddings
```

**Rule:** `T2S/` learning scripts are untouched. The app **copied** the useful parts into `core/` and `services/` — it does not import from `T2S/`.

---

## Layer mental map

Think of the backend as four layers:

```text
┌─────────────────────────────────────────────────────────┐
│  HTTP layer        api/routes/     (ask.py, health.py)  │
├─────────────────────────────────────────────────────────┤
│  Contracts         api/schemas.py  (JSON in/out shapes) │
├─────────────────────────────────────────────────────────┤
│  Business logic    services/       (pipeline, cache)    │
├─────────────────────────────────────────────────────────┤
│  Tools             core/           (schema, Pinecone)   │
└─────────────────────────────────────────────────────────┘
         ↑ wired together by main.py + dependencies.py
         ↑ settings from config.py (GenAI_5/.env)
```

| Layer | Job | Analogy |
|-------|-----|---------|
| `config.py` | Load secrets and settings | Settings panel |
| `main.py` | Start server, create shared clients once | Power switch |
| `dependencies.py` | Hand routes the shared clients | Outlet plugs |
| `api/routes/` | Handle HTTP requests/responses | Reception desk |
| `api/schemas.py` | Validate JSON shapes | Forms + receipts |
| `services/` | Run the Text-to-SQL pipeline | The actual work |
| `core/` | RAG primitives (schema, vectors) | Toolbox |

---

## How the server starts

### Command

```bash
cd t2s-app/backend
uv sync
uv run uvicorn app.main:app --reload
```

- **uv** = creates `.venv`, installs deps from `pyproject.toml` / `uv.lock`
- **uv run** = runs a command inside that venv (no `source activate`)
- **uvicorn** = ASGI web server (runs FastAPI)
- **`app.main:app`** = import variable `app` from module `app.main`
- **`--reload`** = restart on file changes (dev only)

### uv workflow (local dev)

| Command | What it does |
|---------|--------------|
| `uv sync` | Create/update `.venv`, install deps from `uv.lock` |
| `uv run <cmd>` | Run a command inside the project venv |
| `uv add <pkg>` | Add a dependency (updates `pyproject.toml` + `uv.lock`) |
| `uv lock` | Regenerate lockfile after editing `pyproject.toml` manually |

Deps live in `backend/pyproject.toml`. `backend/uv.lock` pins exact versions — commit it for reproducible installs (local + Docker).

### Startup sequence

```text
1. uvicorn imports app.main
2. app = create_app() runs
3. FastAPI registers lifespan hook
4. On server start → lifespan() runs code BEFORE yield:
       validate_config()
       create_engine()      → Neon connection pool
       OpenAI()             → LLM client
       VectorDB()           → Pinecone client
       ensure_index_populated() → upsert schema if Pinecone empty
       store all on app.state
5. yield → server is live, accepts HTTP requests
6. On Ctrl+C / shutdown → engine.dispose()
```

---

## `main.py` — entry point

**File:** `backend/app/main.py`

### `lifespan` — startup and shutdown

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP (runs once)
    validate_config()
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    client = OpenAI()
    vectordb = VectorDB()
    ensure_index_populated(vectordb, engine)

    app.state.engine = engine
    app.state.client = client
    app.state.vectordb = vectordb

    yield  # ← server handles requests here

    # SHUTDOWN (runs once)
    engine.dispose()
```

#### Why `async`?

FastAPI is an **async framework**. Lifespan hooks are declared `async` so startup/shutdown don't block the event loop.

Our route handlers and pipeline calls are still **synchronous** (`def ask_question`, not `async def`). That is fine for this learning app. A later optimization would be `async def` routes or running sync work in a thread pool.

#### Why `yield`?

`yield` splits lifespan into two phases:

| Phase | When | What runs |
|-------|------|-----------|
| **Before `yield`** | Server starting | Create DB pool, OpenAI, Pinecone, warm index |
| **At `yield`** | Server running | Handle all HTTP requests |
| **After `yield`** | Server stopping | `engine.dispose()` — close DB connections |

Think of it like:

```text
open shop  →  yield  →  serve customers all day  →  resume after yield  →  close shop
```

#### Why `app.state`?

`app.state` is a shared bag on the FastAPI instance.

- **Bad:** create `create_engine()` inside every request → slow, exhausts connections
- **Good:** create once at startup, reuse for every request → connection pooling

Same pattern as your learning scripts (one `engine` at the top), but tied to **server lifetime** instead of script lifetime.

### `create_app()` — wire everything together

```python
def create_app() -> FastAPI:
    app = FastAPI(title="Text-to-SQL API", lifespan=lifespan)

    app.add_middleware(CORSMiddleware, ...)   # browser security
    app.include_router(health.router, prefix="/api")
    app.include_router(ask.router, prefix="/api")

    return app

app = create_app()
```

#### CORS (Cross-Origin Resource Sharing)

Browsers block a page on `http://localhost:3000` from calling `http://localhost:8000` unless the API explicitly allows it.

- **Frontend in browser** → needs CORS
- **curl / Postman** → ignores CORS (not a browser)

`CORS_ORIGINS` in `.env` defaults to `http://localhost:3000`.

#### Routers

`include_router(health.router, prefix="/api")` mounts routes:

- `health.router` defines `GET /health` → becomes **`GET /api/health`**
- `ask.router` defines `POST /ask` → becomes **`POST /api/ask`**

---

## `config.py` — settings from `.env`

**File:** `backend/app/config.py`

```python
ROOT = Path(__file__).resolve().parents[3]   # → GenAI_5/
load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL")
# ...
```

### Path math

```text
GenAI_5/t2s-app/backend/app/config.py
         ↑ parents[3] walks up to GenAI_5/
```

Same `.env` file your learning scripts use. Docker injects the same variables via `env_file` in compose — `os.getenv` works in both cases.

### `validate_config()`

Called at startup. If `DATABASE_URL` or `REDIS_URL` is missing, the server **fails immediately** with a clear error instead of crashing on the first request.

---

## `dependencies.py` — dependency injection

**File:** `backend/app/dependencies.py`

```python
def get_engine(request: Request):
    return request.app.state.engine
```

### What is `Depends`?

In a route:

```python
def ask_question(engine=Depends(get_engine)):
    ...
```

FastAPI does this **before** your function runs:

1. Call `get_engine(request)`
2. Pass return value as the `engine` argument

### Why bother?

- Routes declare **what they need**, not **how to build it**
- Same engine/client/vectordb for every request (from `app.state`)
- Easier to test later (swap in a fake engine)

---

## `api/schemas.py` — JSON contracts

**File:** `backend/app/api/schemas.py`

Uses **Pydantic** `BaseModel` classes.

| Model | Direction | Purpose |
|-------|-----------|---------|
| `AskRequest` | Incoming | `{"question": "..."}` — validated, min 1 char, max 2000 |
| `AskSuccessResponse` | Outgoing | SQL succeeded — includes rows, sql, thinking |
| `AskFailureResponse` | Outgoing | All retries failed — includes last_error |
| `HealthResponse` | Outgoing | `status`, `database`, `redis` |

FastAPI also uses these to auto-generate interactive docs at **http://localhost:8000/docs**.

---

## `api/routes/health.py` — liveness check

**Endpoint:** `GET /api/health`

```text
1. Try SELECT 1 on Neon        → database: ok | error
2. Try Redis PING              → redis: ok | error
3. Return overall status       → ok | degraded
```

**Why it exists:** Check dependencies without running a full LLM query (slow + costs money). Useful for you, Docker, and deploy platforms.

---

## `api/routes/ask.py` — main endpoint

**Endpoint:** `POST /api/ask`

**Body:**

```json
{ "question": "How many employees are in each department?" }
```

### Step-by-step flow

```text
1. FastAPI parses JSON → AskRequest (validates question)
2. Depends injects engine, client, vectordb from app.state
3. Check Redis cache (services/cache.py)
       hit  → return cached JSON with "cached": true
       miss → continue
4. Call ask_with_self_improvement() (services/pipeline.py)
5. On ValueError (e.g. no tables from Pinecone) → HTTP 400
6. On success → store result in Redis (setex with TTL)
7. Return dict → FastAPI serializes to JSON
```

The route is **thin** — no SQL, no prompts. Only HTTP concerns: cache, status codes, JSON shape.

---

## Full request flow (sequence diagram)

```mermaid
sequenceDiagram
    participant Client
    participant ask.py
    participant cache.py
    participant pipeline.py
    participant vector_db.py
    participant Neon
    participant OpenAI
    participant Redis

    Client->>ask.py: POST /api/ask {"question": "..."}
    ask.py->>cache.py: get_cached_answer()
    cache.py->>Redis: GET t2s:ask:{hash}

    alt cache hit
        Redis-->>cache.py: JSON string
        cache.py-->>ask.py: parsed dict
        ask.py-->>Client: response (cached: true)
    else cache miss
        ask.py->>pipeline.py: ask_with_self_improvement()
        pipeline.py->>vector_db.py: search (attempt 1 only)
        vector_db.py->>OpenAI: embed question
        vector_db.py-->>pipeline.py: table names
        pipeline.py->>Neon: build_schema_for_tables
        pipeline.py->>OpenAI: generate SQL
        pipeline.py->>Neon: execute SQL
        loop up to 3 attempts on failure
        pipeline.py-->>ask.py: result dict
        ask.py->>cache.py: set_cached_answer() if success
        cache.py->>Redis: SETEX with TTL
        ask.py-->>Client: JSON response (cached: false)
    end
```

---

## `services/cache.py` — Redis cache-aside

**File:** `backend/app/services/cache.py`

Uses **Redis Cloud** via `REDIS_URL` in `.env`. No local Redis container.

### Cache-aside pattern

```text
READ:  GET key from Redis before running pipeline
WRITE: SET key after successful pipeline (only successes, not failures)
```

### Key design

```python
normalized = question.strip().lower()
digest = sha256(normalized)
key = f"t2s:ask:{digest}"
```

- `"How many employees?"` and `"  how many employees?  "` → **same key**
- Hash avoids storing raw user text as Redis key

### TTL

`setex(key, CACHE_TTL_SECONDS, json)` — default **600 seconds (10 min)**.

After TTL, Redis auto-deletes the key. Answers can go stale if DB data changes — that is intentional for a learning cache.

### `decode_responses=True`

Redis returns strings (not bytes) so `json.loads()` works directly.

### `default=str` in `json.dumps`

SQL rows may contain `date` or `Decimal` objects. `default=str` converts them for JSON storage.

---

## `services/pipeline.py` — the brain (from basics_5)

**File:** `backend/app/services/pipeline.py`

This is `T2S/rag/basics_5_self_improve.py` refactored for the API.

### Key functions

| Function | When used | What it does |
|----------|-----------|--------------|
| `ensure_index_populated` | Server startup | If Pinecone empty → embed + upsert schema chunks |
| `retrieve_schema_for_question` | Attempt 1 | Pinecone search → table names → schema text |
| `generate_prompt_with_rag` | Attempt 1 | RAG retrieve + CoT prompt |
| `generate_fix_prompt` | Attempts 2–3 | Failed SQL + Postgres error → fix prompt |
| `generate_sql` | Every attempt | OpenAI call |
| `parse_llm_response` | Every attempt | Extract `<thinking>` and `<sql>` |
| `ask_with_self_improvement` | Per request | Orchestrates the retry loop |

### Self-improvement loop

```text
attempt 0 (displayed as 1/3):
    RAG → Pinecone finds tables → build small schema → CoT prompt
    → LLM → SQL → execute on Neon
    ↓ if Postgres error

attempt 1 (2/3):
    fix prompt (same schema + failed SQL + error message)
    → LLM → SQL → execute
    ↓ still failing

attempt 2 (3/3):
    same fix prompt → last chance
    ↓
    return { success: false, last_sql, last_error }
```

**We do NOT re-run Pinecone on retry** — same `retrieved_schema` from attempt 1 is reused. Wrong SQL is usually a generation bug, not wrong table retrieval.

### Return shape (API vs script)

| basics_5 script | pipeline.py (API) |
|-----------------|-----------------|
| `return sql, result, attempts` | `return { "success": True, "sql": ..., "rows": ... }` |
| `print(...)` | No prints — dict goes to JSON |

---

## `services/sql_runner.py` — execute SQL safely

**File:** `backend/app/services/sql_runner.py`

| Function | Behavior |
|----------|----------|
| `run_sql` | Run SELECT on Neon. **Raises** on failure. SELECT-only guard. |
| `execute_sql_with_feedback` | Wraps `run_sql`. **Catches** errors. Returns `(success, result, error_message)`. |

The retry loop needs `execute_sql_with_feedback` so a bad query does not crash the API — the Postgres error becomes input to the fix prompt.

Rows are converted to plain lists for JSON:

```python
rows = [list(row) for row in result.fetchall()]
```

---

## `core/schema_chunks.py` — schema text from Neon

**File:** `backend/app/core/schema_chunks.py`

Copied from `T2S/rag/schema_chunks.py`.

| Function | Used when |
|----------|-----------|
| `build_schema_chunks(engine)` | Indexing — one embeddable chunk per table |
| `build_schema_for_tables(engine, table_names)` | After RAG — prompt text for only retrieved tables |

Uses SQLAlchemy `inspect(engine)` to read live schema: columns, PKs, FKs.

---

## `core/vector_db.py` — Pinecone + embeddings

**File:** `backend/app/core/vector_db.py`

Copied from `T2S/rag/pinecone_db.py`.

| Method | Purpose |
|--------|---------|
| `embed_texts` / `embed_query` | OpenAI `text-embedding-3-large`, 1024 dimensions |
| `load_data` | Embed chunks, upsert to Pinecone |
| `search` | Embed question, cosine similarity, filter by threshold |
| `vector_count` | Check if index needs population |

Pinecone stores **table name metadata only**. Full schema text is rebuilt from Neon via `build_schema_for_tables`.

---

## API response examples

### Success

```json
{
  "question": "How many employees are in each department?",
  "cached": false,
  "success": true,
  "retrieved_tables": ["departments", "employees"],
  "thinking": "Join employees to departments, group by department name, count...",
  "sql": "SELECT d.name, COUNT(e.id) FROM employees e JOIN departments d ...",
  "columns": ["name", "count"],
  "rows": [["Engineering", 25], ["HR", 18]],
  "attempts": 1
}
```

### Cached (second identical question)

Same JSON but `"cached": true` and returns in ~milliseconds.

### Failure (all retries exhausted)

```json
{
  "question": "...",
  "cached": false,
  "success": false,
  "retrieved_tables": ["employees"],
  "thinking": "...",
  "error": "Could not generate valid SQL after all attempts",
  "last_sql": "SELECT ...",
  "last_error": "column foo does not exist",
  "attempts": 3
}
```

---

## External services (not in Docker)

```text
┌─────────────────┐
│  t2s-app API    │
│  (FastAPI)      │
└────────┬────────┘
         │ internet
         ├──────────► Neon Postgres     (DATABASE_URL)
         ├──────────► OpenAI            (OPENAI_API_KEY)
         ├──────────► Pinecone          (PINECONE_API_KEY)
         └──────────► Redis Cloud        (REDIS_URL)
```

All are managed/cloud services. The API container only needs outbound internet and env vars.

---

## Docker

### `backend/Dockerfile`

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY app ./app
ENV PYTHONPATH=/app
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

| Line | Why |
|------|-----|
| `uv:python3.12-bookworm-slim` | Official uv image with Python preinstalled |
| `pyproject.toml` + `uv.lock` copied first | Docker layer caching — deps rebuild only when lockfile changes |
| `uv sync --frozen --no-dev` | Reproducible install from lockfile |
| `COPY app ./app` only | **No `.env` in image** — secrets at runtime |
| `PYTHONPATH=/app` | Python finds `app.main` module |
| `uv run --no-sync` | Use deps from build; don't re-sync on every container start |
| `--host 0.0.0.0` | Listen on all interfaces inside container (required for port mapping) |

### `docker-compose.yml`

```yaml
services:
  api:
    build: ./backend
    env_file:
      - ../.env
    ports:
      - "8000:8000"
```

- **`env_file: ../.env`** injects `GenAI_5/.env` at **runtime**
- **No Redis service** — uses Redis Cloud from `REDIS_URL`
- **`8000:8000`** maps host port → container port

### Run with Docker

```bash
cd t2s-app
docker compose up --build
```

API: http://localhost:8000/docs

---

## Environment variables

All live in **`GenAI_5/.env`** (see `.env.example`).

| Variable | Used by | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | SQLAlchemy | Neon Postgres connection |
| `OPENAI_API_KEY` | OpenAI client | SQL generation + embeddings |
| `PINECONE_API_KEY` | VectorDB | Vector search |
| `PINECONE_INDEX_NAME` | VectorDB | Index name (e.g. `t2s-schema`) |
| `REDIS_URL` | cache.py | Redis Cloud connection |
| `CACHE_TTL_SECONDS` | cache.py | Cache expiry (default 600) |
| `CORS_ORIGINS` | main.py | Allowed browser origins |

**Never commit `.env`. Never `COPY .env` in Dockerfile.**

---

## How to test

### Health

```bash
curl -s http://localhost:8000/api/health | jq
```

Expected: `"status": "ok"`, `"database": "ok"`, `"redis": "ok"`

### Ask

```bash
curl -s -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "How many employees are in each department?"}' | jq
```

Run the same command twice — second response should have `"cached": true`.

### Interactive docs

http://localhost:8000/docs

---

## Suggested reading order (when exploring the code)

1. `config.py` — what the app needs from `.env`
2. `main.py` — startup (`yield`), CORS, routers
3. `dependencies.py` — how `Depends` works
4. `api/routes/ask.py` — per-request flow
5. `services/cache.py` — Redis before/after pipeline
6. `services/pipeline.py` — the loop you already know from basics_5
7. `core/` — RAG tools
8. `Dockerfile` + `docker-compose.yml` — deployment

---

## Mapping back to learning files

```text
T2S/rag/basics_5_self_improve.py  →  services/pipeline.py + sql_runner.py
T2S/rag/schema_chunks.py          →  core/schema_chunks.py
T2S/rag/pinecone_db.py            →  core/vector_db.py
basics_5 main() + prints          →  main.py lifespan + api/routes/ask.py
(new)                             →  services/cache.py
(new)                             →  api/schemas.py, health.py
(new)                             →  Dockerfile, docker-compose.yml
```

---

## What we intentionally skipped (for this learning app)

| Skipped | Why |
|---------|-----|
| Celery | Sync `/ask` + Redis cache is enough |
| Local Redis | You use Redis Cloud only |
| Auth | Not the learning goal |
| Importing from `T2S/` | App is self-contained for Docker |
| Async pipeline | Sync is simpler; optimize later if needed |

---

## Quick reference: one POST /api/ask request

```text
Client
  → ask.py (HTTP)
    → cache.py (Redis GET)
      → [hit] return cached JSON
      → [miss] pipeline.py
          → vector_db.py (Pinecone, attempt 1)
          → OpenAI (generate SQL)
          → sql_runner.py (Neon execute, retry up to 3x)
        → cache.py (Redis SETEX on success)
  → JSON response
```

That is the entire backend flow.
