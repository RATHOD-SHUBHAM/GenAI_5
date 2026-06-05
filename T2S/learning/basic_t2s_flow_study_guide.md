# Basic Text-to-SQL Flow Study Guide

A walkthrough of `T2S/basic_t2s/basics_1.py` — schema introspection, LLM SQL generation, and safe execution on Neon via SQLAlchemy.

---

## 1. What this script does (end-to-end)

This is a **minimal Text-to-SQL pipeline** (no RAG yet — the full schema goes into every prompt):

```text
Load config (.env)
    → create_engine (Neon)
    → get_schema_info(engine)     # Step 1: database understanding
    → generate_prompt(schema, query)
    → generate_sql(prompt)        # OpenAI
    → parse SQL from <sql> tags
    → run_sql(engine, sql)        # validate + execute
    → print results
```

This matches early steps in `T2S/my_application.md`. Later you will **retrieve** only relevant tables instead of sending the whole schema.

---

## 2. Phase-by-phase: what each block does

### Phase A — Load config (lines 9–25)

```python
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
```

| Piece | Why |
|--------|-----|
| `parents[2]` | Script is in `T2S/basic_t2s/`; `.env` lives at repo root `GenAI_5/` |
| `DATABASE_URL` | Neon Postgres connection string |
| `OPENAI_API_KEY` | LLM for natural language → SQL |

---

### Phase B — Engine (lines 27–30)

```python
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
```

| Piece | Why |
|--------|-----|
| `engine` | One connection pool to Neon for the whole script |
| `pool_pre_ping=True` | Reconnect if Neon dropped an idle connection |

**Not** `sqlite3.connect(path)` — there is no local `.db` file.

---

### Phase C — `get_schema_info(engine)` (lines 36–106)

**Goal:** Turn live Postgres metadata into **text** the LLM can read.

**Flow inside the function:**

```text
inspect(engine)
    → for each table_name in get_table_names():
          1. Table header
          2. Primary key        ← Block 5
          3. Columns + types    ← Block 2
          4. Foreign keys       ← Block 3
          5. append to schema_parts
    → return joined string
```

| SQLite tutorial | This script (SQLAlchemy + Neon) |
|-----------------|----------------------------------|
| `sqlite_master` | `insp.get_table_names()` |
| `PRAGMA table_info` | `insp.get_columns(table_name)` |
| (not shown) | `insp.get_pk_constraint()` |
| (not shown) | `insp.get_foreign_keys()` |

---

### Phase D — Prompt (`basics_1.py` / `basics_2.py`)

```python
generate_prompt(schema, user_query)
```

Wraps schema + user question in `<schema>` and `<query>` tags. Asks the model to return SQL inside `<sql>` tags only.

| Script | Prompt level |
|--------|----------------|
| `basics_1.py` | Basic — schema + query only |
| `basics_2.py` | Improved — adds **few-shot** `<examples>` before the user query |

**Example question in both scripts:**  
*"What are the names of employee in Engineering Department"*

**Go deeper:** See `T2S/learning/prompt_improvements_t2s_study_guide.md` for few-shot, chain-of-thought, system/user split, dialect rules, and how to test prompt changes.

---

### Phase E — Generate SQL (lines 152–175)

```python
generate_sql(prompt)  # OpenAI Responses API
sql = result.split("<sql>")[1].split("</sql>")[0].strip()
```

| Piece | Why |
|--------|-----|
| LLM call | Converts English + schema → SQL string |
| Tag parsing | Extracts SQL from model output |

**Fragile spot:** If the model omits `<sql>` tags, parsing fails before `run_sql`.

---

### Phase F — `run_sql(engine, sql)` (lines 182–193)

```python
with engine.connect() as conn:
    result = conn.execute(text(cleaned_sql))
    columns = list(result.keys())
    rows = result.fetchall()
return columns, rows
```

| Piece | Why |
|--------|-----|
| `text(cleaned_sql)` | SQLAlchemy 2.0 wrapper — must `import text` from `sqlalchemy` |
| `startswith("SELECT")` | Basic safety — block destructive SQL |
| `engine.connect()` | Read-only; no `begin()` needed for SELECT |
| `with` | Returns connection to pool (no manual `close()`) |

**Two tests in the script:**

1. **Manual** — hardcoded JOIN query (proves DB + `run_sql` work).
2. **LLM** — runs parsed `sql` inside `try/except`.

---

## 3. Why primary keys and foreign keys in schema text?

Columns alone are not enough for good JOINs. PK and FK lines are **hints for the LLM**, read from Postgres (not invented).

### Primary key — “unique row identifier”

**What it is:** Column(s) that uniquely identify each row in **this** table.

**Example output:**

```text
Table: employees
  Primary key: id
  - id (INTEGER)
  - name (TEXT)
  ...
```

**Why add it:**

- JOINs should use stable IDs (`departments.id`), not ambiguous names when possible.
- Aggregations and `GROUP BY` need the right grain (one row per `id`).

**Code:** `insp.get_pk_constraint(table_name)` → `constrained_columns`.

**Where in the loop:** Right after `table_info = f"Table: ..."`, **before** the column loop.

---

### Foreign key — “how this table links to another”

**What it is:** Rule that values in column A must exist in column B of another table.

**Example output:**

```text
  Foreign keys:
    - (department_id) -> departments(id)
```

**Why add it:**

- Question: *employees in Engineering* needs  
  `JOIN departments d ON e.department_id = d.id`
- Without FK text, the model sees `department_id` and two tables named `id` and may JOIN wrong.

**Code:** `insp.get_foreign_keys(table_name)` → `constrained_columns`, `referred_table`, `referred_columns`.

**Where in the loop:** **After** listing all columns, **before** `schema_parts.append(...)`.

---

### Visual: your two tables

```text
departments                    employees
┌─────────────────┐           ┌──────────────────────────┐
│ id  (PK)        │◄──────────│ department_id (FK)       │
│ name            │           │ id (PK)                  │
│ location        │           │ name, age, salary, ...   │
└─────────────────┘           └──────────────────────────┘
```

---

### Three layers in schema text

| Layer | Answers |
|--------|---------|
| Columns + types | What fields exist? |
| Primary key | What uniquely identifies a row? |
| Foreign keys | How do I JOIN to other tables? |

---

## 4. Don’t confuse these terms

| Term | Meaning |
|------|---------|
| **Primary key** | Unique row ID on a table (what we add in schema text) |
| **Foreign key** | Column pointing to another table (JOIN hint) |
| **`public` schema** | Postgres namespace for tables — not a “key” |

---

## 5. Expected SQL for the example question

```sql
SELECT e.name
FROM employees e
JOIN departments d ON e.department_id = d.id
WHERE d.name = 'Engineering';
```

The manual `test_sql` in `basics_1.py` is this pattern with `LIMIT 10`.

---

## 6. Mental model: engine vs conn in this script

| Object | Role in `basics_1.py` |
|--------|------------------------|
| `engine` | Created once; used by `inspect`, `get_schema_info`, and `run_sql` |
| `conn` | Short-lived inside `with engine.connect()` only in `run_sql` |

You do **not** loop the engine. You pass `engine` into functions that need the database.

---

## 7. What’s next (toward full app)

| Done in `basics_1.py` | Later (`my_application.md`) |
|------------------------|-------------------------------|
| Full schema in prompt | RAG — retrieve relevant tables only |
| Basic SELECT guard | Stronger validation (tables, columns, LIMIT) |
| Single-shot LLM | Error correction loop on DB errors |
| Script | FastAPI `/ask` + optional Celery |
| Debug `print`s | Query lineage logging |

---

## 8. Common issues

| Error | Fix |
|-------|-----|
| `NameError: text` | `from sqlalchemy import create_engine, inspect, text` |
| `DATABASE_URL missing` | Check `.env` path (`parents[2]`) |
| Parse error on `<sql>` | Model didn’t use tags — fix prompt or parse defensively |
| SQL runs manually but not from LLM | Problem is generation/parsing, not Neon |
| Wrong JOIN | Improve schema text (PK/FK) or add business definitions |

---

## 9. One-paragraph summary

`basics_1.py` connects to Neon with SQLAlchemy, **inspects** schema into text (including **primary keys** for row identity and **foreign keys** for JOIN paths), sends that plus a user question to OpenAI, parses the returned SQL, and **executes** it safely with `text()` and a SELECT-only check. PK/FK are not created here — they are **read** from Postgres and written into the prompt so the model can generate correct Postgres JOINs.

---

## Related files

- `T2S/basic_t2s/basics_1.py` — basic prompt + full pipeline
- `T2S/basic_t2s/basics_2.py` — few-shot prompt variant
- `T2S/db/create_db_sqlalchemy.py` — seeds `departments` / `employees` (defines PK/FK in DDL)
- `T2S/my_application.md` — full product pipeline
- `T2S/learning/sqlalchemy_study_guide.md` — Engine, `text()`, `inspect()`
- `T2S/learning/data_lineage_study_guide.md` — logging question → SQL → results
- `T2S/learning/prompt_improvements_t2s_study_guide.md` — few-shot, CoT, rules, testing
