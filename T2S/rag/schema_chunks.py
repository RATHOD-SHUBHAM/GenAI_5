"""
Schema chunks for RAG (Retrieval-Augmented Generation).

This module reads your LIVE Neon/Postgres schema and turns it into text
chunks that get embedded and stored in Pinecone (next step: pinecone_db.py).

Pipeline position:
    Neon DB  →  schema_chunks.py  →  embed  →  Pinecone  →  retrieve  →  LLM prompt

We use ONE chunk per TABLE (not per column) because Text-to-SQL retrieval
usually needs whole tables (e.g. "employees" + "departments"), not single columns.
"""

from sqlalchemy import inspect


# =============================================================================
# Core helpers
# =============================================================================

def _build_table_text(insp, table_name: str) -> str:
    """
    Build a human/LLM-readable description of a single table.

    Args:
        insp: SQLAlchemy Inspector (from inspect(engine)).
        table_name: Table in the public schema (e.g. "employees").

    Returns:
        Multi-line string with table name, primary key, columns, and foreign keys.

    Why PK + FK in the text?
        - Primary key: tells the model which column uniquely identifies a row.
        - Foreign keys: tells the model how to JOIN tables (e.g. department_id → departments.id).
    """
    columns = insp.get_columns(table_name)

    table_info = f"Table: {table_name}\n"

    # --- Primary key (one row = one id) ---
    pk = insp.get_pk_constraint(table_name)
    if pk and pk.get("constrained_columns"):
        pk_cols = ", ".join(pk["constrained_columns"])
        table_info += f"  Primary key: {pk_cols}\n"

    # --- Columns and types (what can appear in SELECT / WHERE) ---
    for col in columns:
        col_name = col["name"]
        col_type = col["type"]
        table_info += f"  - {col_name} ({col_type})\n"

    # --- Foreign keys (how this table links to others) ---
    fks = insp.get_foreign_keys(table_name)
    if fks:
        table_info += "  Foreign keys:\n"
        for fk in fks:
            local_cols = ", ".join(fk["constrained_columns"])
            remote_table = fk["referred_table"]
            remote_cols = ", ".join(fk["referred_columns"])
            table_info += f"    - ({local_cols}) -> {remote_table}({remote_cols})\n"

    return table_info.rstrip()


# =============================================================================
# Public API — used by indexing and by basics_4 RAG prompt
# =============================================================================

def build_schema_chunks(engine) -> list[dict]:
    """
    Read the full schema from Neon and return a list of embeddable chunks.

    This replaces the tutorial's SQLite loop:
        sqlite_master + PRAGMA table_info  →  inspect(engine) per table

    Each list item matches the tutorial's schema_data shape:
        {
            "text": "...",           # what gets embedded (OpenAI)
            "metadata": {            # stored in Pinecone alongside the vector
                "table": "employees",
                "kind": "technical", # later: "business" for YAML definitions
            },
        }

    Args:
        engine: SQLAlchemy engine connected to Neon (from create_engine(DATABASE_URL)).

    Returns:
        One dict per table in the public schema.
    """
    insp = inspect(engine)
    chunks = []

    # schema="public" — Neon/Postgres default; ignores system schemas
    for table_name in insp.get_table_names(schema="public"):
        text = _build_table_text(insp, table_name)
        chunks.append({
            "text": text,
            "metadata": {
                "table": table_name,
                "kind": "technical",
            },
        })

    return chunks


def build_schema_for_tables(engine, table_names: list[str]) -> str:
    """
    Build schema text for ONLY the tables returned by Pinecone search.

    Used after RAG retrieval in basics_4 — instead of sending the entire DB
    schema to the LLM, you send just the top-k relevant tables.

    Args:
        engine: SQLAlchemy engine connected to Neon.
        table_names: e.g. ["employees", "departments"] from vectordb.search() metadata.

    Returns:
        Single string joined with blank lines — same format as one big get_schema_info().
    """
    insp = inspect(engine)
    parts = []
    for table_name in table_names:
        parts.append(_build_table_text(insp, table_name))
    return "\n\n".join(parts)


# =============================================================================
# Smoke test — run this file directly to verify chunks without Pinecone/OpenAI
# =============================================================================
# Usage:
#   python T2S/rag/schema_chunks.py
#
# Expected: Chunk count: 2 (departments, employees) if create_db_sqlalchemy.py ran.
# This is NOT pytest — it's a quick manual check while developing.
# =============================================================================

def _run_smoke_test() -> None:
    """Connect to Neon, build chunks, print summary. Called only when run as script."""
    import os
    from pathlib import Path

    from dotenv import load_dotenv
    from sqlalchemy import create_engine

    # schema_chunks.py lives in T2S/rag/ → repo root (GenAI_5) is two levels up
    ROOT = Path(__file__).resolve().parents[2]
    load_dotenv(ROOT / ".env")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL missing — check GenAI_5/.env")

    engine = create_engine(database_url, pool_pre_ping=True)

    chunks = build_schema_chunks(engine)
    print(f"Smoke test OK — chunk count: {len(chunks)}\n")

    for chunk in chunks:
        print("---")
        print("metadata:", chunk["metadata"])
        print(chunk["text"])
        print()


if __name__ == "__main__":
    _run_smoke_test()
