# SQLAlchemy Study Guide

A practical reference for your Text-to-SQL project (Neon PostgreSQL + Python).

---

## 1. What problem does SQLAlchemy solve?

You already use **psycopg2** like this:

```python
conn = psycopg2.connect(DATABASE_URL)
cur.execute("SELECT * FROM employees WHERE department_id = %s", (2,))
rows = cur.fetchall()
conn.close()
```

That works, but as the app grows you repeat:

- Opening/closing connections
- Writing raw SQL strings everywhere
- Mapping rows to Python objects
- Sharing one connection pattern between scripts, pandas, and the LLM layer

**SQLAlchemy** is a Python library that sits *above* database drivers (like psycopg2). It gives you:

| Layer | What it does |
|--------|----------------|
| **Engine** | Manages connections to the DB (pooling, URL parsing) |
| **Connection** | One session talking to Postgres |
| **SQL text / ORM** | Run queries or map tables → Python classes |
| **Integration** | Same `DATABASE_URL` works with pandas, Alembic migrations, etc. |

Think of it as: **psycopg2 = phone line**, **SQLAlchemy = phone + address book + call manager**.

---

## 2. Two ways to use SQLAlchemy (you need both concepts)

### 2a. Core (SQL Expression Language) — closest to raw SQL

You still write SQL (or build it), but through SQLAlchemy’s API. Good for:

- Text-to-SQL (you *generate* SQL strings anyway)
- Ad-hoc queries
- Scripts like `create_db.py`

```python
from sqlalchemy import create_engine, text

engine = create_engine(os.getenv("DATABASE_URL"))

with engine.connect() as conn:
    result = conn.execute(text("SELECT COUNT(*) FROM employees"))
    count = result.scalar()  # single value
    conn.commit()  # needed after INSERT/UPDATE/DELETE
```

### 2b. ORM (Object-Relational Mapping) — tables as Python classes

Each table becomes a class; rows become objects. Good for:

- CRUD in an app API
- Clear models: `Employee`, `Department`
- Relationships (`employee.department`)

```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Department(Base):
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    employees: Mapped[list["Employee"]] = relationship(back_populates="department")
```

For **Text-to-SQL**, you’ll use **Core + `text()`** heavily for *running* generated SQL. You might still use **ORM** for *schema introspection* or admin tools—not required on day one.

---

## 3. Connection URL (same as Neon / psycopg2)

Your `.env`:

```
DATABASE_URL=postgresql://user:pass@host/neondb?sslmode=require
```

SQLAlchemy:

```python
from sqlalchemy import create_engine

engine = create_engine(
    os.getenv("DATABASE_URL"),
    echo=False,        # True = print every SQL (great for learning)
    pool_pre_ping=True # reconnect if Neon slept / dropped connection
)
```

**Driver note:** URL `postgresql://` uses psycopg2 if installed (`psycopg2-binary`). Alternative: `postgresql+psycopg://` with psycopg3.

Install:

```
sqlalchemy
psycopg2-binary   # you already have this
python-dotenv
pandas            # optional, reads via engine
```

---

## 4. Mental model: Engine → Connection → Transaction

```
create_engine(DATABASE_URL)
        │
        ▼
   engine.connect()  ──► Connection
        │
        ├── conn.execute(text("SELECT ..."))   # read
        │
        └── conn.commit() / rollback()         # after writes
```

**Rules:**

- **SELECT** — often no `commit()` needed (still use `with engine.connect()`).
- **INSERT/UPDATE/DELETE** — call `conn.commit()` before leaving the block (SQLAlchemy 2.0 style).
- Prefer `with engine.connect() as conn:` so connections are returned to the pool.

**Autocommit mode** (simpler for scripts):

```python
with engine.begin() as conn:  # auto-commit on success, rollback on error
    conn.execute(text("INSERT INTO departments (id, name, location) VALUES (1, 'HR', 'NY')"))
```

`engine.begin()` = connect + transaction + commit/rollback for you.

### Engine vs Connection (from `create_db_sqlalchemy.py`)

| Concept | What it is | What it does in your project |
|--------|------------|------------------------------|
| **`engine`** | One per app/script (from `create_engine`) | Owns the **connection pool** to Neon. You rarely “talk SQL” on the engine directly—you ask it for a `Connection`. |
| **`conn`** | One **borrowed** link from the pool (`engine.connect()` or `engine.begin()`) | Runs SQL via `conn.execute(text(...))`. When the `with` block ends, the connection goes back to the pool. |

**`begin()` vs `connect()`:**

| Method | Transaction | Commit / rollback | Use when |
|--------|-------------|-------------------|----------|
| **`engine.connect()`** | Not started for you; you manage it (or only read) | You call `conn.commit()` after writes, or skip commit for `SELECT` | Health checks, counts, running validated Text-to-SQL `SELECT`s |
| **`engine.begin()`** | **Started automatically** | **Commits** if the `with` block exits cleanly; **rolls back** on any exception | `CREATE TABLE`, seed inserts, any multi-step write that must be all-or-nothing |

**One-line memory aid:** `engine` = pool manager; `conn` = single phone call; `begin()` = call + automatic “save or undo everything.”

### `Engine` methods reference

From the SQLAlchemy [`Engine`](https://docs.sqlalchemy.org/en/20/core/connections.html#sqlalchemy.engine.Engine) API. The ones you use most are **`connect()`**, **`begin()`**, and **`dispose()`**.

| Method | What it does | When you use it |
|--------|----------------|-----------------|
| **`connect()`** | Returns a new **`Connection`** from the pool (no transaction until you start one or write). | `SELECT version()`, row counts, `pd.read_sql`, executing read-only generated SQL. |
| **`begin()`** | Context manager: yields a **`Connection`** with a **transaction already established**; commits on success, rolls back on error. | `CREATE TABLE`, bulk `INSERT`, seed scripts (`create_db_sqlalchemy.py`). |
| **`dispose()`** | Closes all pooled connections and shuts down the pool. | App shutdown (FastAPI `lifespan`), tests teardown, before fork in some deploy setups. |
| **`raw_connection()`** | Returns a raw **DBAPI** connection (psycopg2) from the pool—bypasses some SQLAlchemy wrappers. | Rare: legacy code, special COPY/bulk APIs, debugging driver issues. |
| **`execution_options()`** | Returns a **new Engine** whose connections inherit extra per-execution options (e.g. isolation level). | Advanced: read replicas, custom timeouts, schema search_path. |
| **`get_execution_options()`** | Returns the current default execution options dict for this engine. | Inspecting how an engine was configured. |
| **`update_execution_options()`** | Updates default execution options on this engine in place. | Tweaking behavior without recreating the engine. |
| **`clear_compiled_cache()`** | Clears the dialect’s compiled SQL cache. | Rare: after schema changes in long-lived processes, debugging stale compiled statements. |

**Typical script shape (Neon seed):**

```text
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

with engine.connect() as conn:          # read: proof + verify
    conn.execute(text("SELECT 1"))

with engine.begin() as conn:            # write: DDL + seed
    conn.execute(text("CREATE TABLE ..."))
    conn.execute(text("INSERT ..."), rows)

# FastAPI shutdown (later):
engine.dispose()
```

---

## 5. Comparing your patterns: psycopg2 vs SQLAlchemy

### Create tables + seed (your `create_db.py` use case)

**psycopg2:**

```python
with psycopg2.connect(DATABASE_URL) as conn:
    with conn.cursor() as cur:
        cur.execute("CREATE TABLE IF NOT EXISTS ...")
        cur.executemany("INSERT INTO departments VALUES (%s,%s,%s)", rows)
    conn.commit()
```

**SQLAlchemy Core:**

```python
with engine.begin() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            location TEXT
        )
    """))
    conn.execute(
        text("INSERT INTO departments (id, name, location) VALUES (:id, :name, :loc)"),
        [{"id": 1, "name": "HR", "loc": "New York"}, ...],  # executemany-style
    )
```

Named parameters `:id` are safer and readable than `%s` positionals.

### Run LLM-generated SQL (Text-to-SQL)

```python
def run_readonly_sql(engine, sql: str):
    """Example: only allow SELECT in production."""
    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT"):
        raise ValueError("Only SELECT allowed")

    with engine.connect() as conn:
        result = conn.execute(text(sql))
        rows = result.fetchall()
        columns = result.keys()
    return columns, rows
```

Pandas:

```python
df = pd.read_sql_query(text("SELECT * FROM employees LIMIT 10"), engine)
# or: pd.read_sql("SELECT * FROM employees", engine)
```

---

## 6. Schema reflection (useful for RAG / schema indexing)

SQLAlchemy can **read** what’s already in Neon without hand-writing every column:

```python
from sqlalchemy import inspect

insp = inspect(engine)
table_names = insp.get_table_names()
# ['departments', 'employees']

for table in table_names:
    columns = insp.get_columns(table)
    fks = insp.get_foreign_keys(table)
    # Build text for embeddings: table name, column names, types, FKs
```

This connects directly to **Step 1** in your Text-to-SQL design: “scan the database and extract tables, columns, relationships.”

---

## 7. ORM quick tour (optional but good to know)

### Define models

```python
from datetime import date
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey
from decimal import Decimal

class Base(DeclarativeBase):
    pass

class Department(Base):
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    location: Mapped[str | None]

class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    age: Mapped[int | None]
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    salary: Mapped[Decimal | None]
    hire_date: Mapped[date | None]
```

### Session = unit of work

```python
from sqlalchemy.orm import Session

with Session(engine) as session:
    dept = session.get(Department, 1)
    employees = session.query(Employee).filter(Employee.department_id == 1).all()
    session.commit()
```

ORM generates SQL for you. For Text-to-SQL you usually **don’t** ORM-query user questions—you **execute** the LLM’s SQL string via `text()`.

---

## 8. When to use what in *your* project

| Task | Tool |
|------|------|
| Seed DB (`create_db.py`) | `engine.begin()` + `text()` |
| Test Neon connection | `create_engine` + `SELECT 1` |
| Export schema for RAG | `inspect(engine)` or SQL against `information_schema` |
| Run generated SQL | `text(sql)` + validation (SELECT only) |
| Show results to user | `pandas.read_sql` + engine |
| Future REST API | ORM models + `Session` |

---

## 9. Safety for Text-to-SQL

SQLAlchemy does **not** magically make LLM SQL safe. You still need:

1. **Allowlist** — only `SELECT` (block `DROP`, `DELETE`, etc.).
2. **Limit rows** — append `LIMIT 100` if missing.
3. **Timeout** — statement timeout on connection.
4. **Read-only DB user** — Neon role with `SELECT` only (best practice).
5. **Parameterized queries** — for *your* app SQL; LLM-generated SQL is inherently dynamic—validate tables/columns against schema.

```python
# Parameterized (your app code) — safe from injection
conn.execute(
    text("SELECT * FROM employees WHERE department_id = :dept_id"),
    {"dept_id": 2},
)

# LLM output — validate structure, don't use string concat for user input inside SQL
```

---

## 10. SQLAlchemy 2.0 style cheat sheet

```python
from sqlalchemy import create_engine, text, select, insert, MetaData, Table
from sqlalchemy.orm import Session

engine = create_engine(DATABASE_URL)

# --- Raw SQL ---
with engine.connect() as conn:
    conn.execute(text("SELECT 1"))

with engine.begin() as conn:
    conn.execute(text("INSERT INTO departments (id, name, location) VALUES (1, 'HR', 'Boston')"))

# --- Scalar / one row / all rows ---
with engine.connect() as conn:
    n = conn.execute(text("SELECT COUNT(*) FROM employees")).scalar()
    row = conn.execute(text("SELECT * FROM employees WHERE id = 1")).first()
    all_rows = conn.execute(text("SELECT * FROM employees")).all()

# --- Reflect existing table ---
metadata = MetaData()
employees_table = Table("employees", metadata, autoload_with=engine)
```

Avoid legacy patterns (`session.query()` still works but prefer `select()` in new code).

---

## 11. Common mistakes

| Mistake | Fix |
|---------|-----|
| Forgot `commit()` after INSERT | Use `engine.begin()` or `conn.commit()` |
| `"SELECT * FROM employees WHERE id = %s"` with SQLAlchemy `text()` | Use `:id` named params, not `%s` |
| Engine created inside every function | Create **one** engine per process, reuse it |
| Neon connection dropped | `pool_pre_ping=True` |
| Mixing SQLite and Postgres SQL | Postgres: `SERIAL`, `NUMERIC`, no `AUTOINCREMENT` keyword |

---

## 12. Minimal end-to-end example (Neon)

```python
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)

with engine.begin() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            location TEXT
        )
    """))

with engine.connect() as conn:
    version = conn.execute(text("SELECT version()")).scalar()
    print(version)
```

---

## 13. Further reading

- [SQLAlchemy 2.0 Tutorial](https://docs.sqlalchemy.org/en/20/tutorial/)
- [Engine configuration](https://docs.sqlalchemy.org/en/20/core/engines.html)
- [Neon + SQLAlchemy](https://neon.com/docs/guides/sqlalchemy) — connection pooling notes
- Your app doc: `T2S/my_application.md` — schema indexing and executing validated SQL

---

## 14. One-paragraph summary

**SQLAlchemy** gives you a single `create_engine(DATABASE_URL)` entry point for scripts, pandas, schema introspection, and running LLM-generated SQL via `text()`. Use **Core** for Text-to-SQL execution and reflection; add **ORM** later if you build an API with Python models. It replaces manual connection juggling; it does **not** replace SQL validation or read-only security.
