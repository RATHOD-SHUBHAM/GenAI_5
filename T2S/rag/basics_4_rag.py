"""
basics_4_rag.py — Text-to-SQL with RAG (retrieval-augmented schema).

Pipeline (vs basics_3 which sends FULL schema):
    user question
        → Pinecone search (relevant tables)
        → build_schema_for_tables (only those tables)
        → CoT prompt → LLM → SQL → run on Neon

Prerequisites:
    - Neon seeded (create_db_sqlalchemy.py)
    - Pinecone index (pinecone_db.py smoke test or ensure_index_populated below)
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import create_engine, text

from schema_chunks import build_schema_for_tables, build_schema_chunks
from pinecone_db import VectorDB

# =============================================================================
# Config + database connection
# =============================================================================

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL missing — check GenAI_5/.env")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
client = OpenAI()


# =============================================================================
# RAG helpers
# =============================================================================

def ensure_index_populated(vectordb: VectorDB, engine) -> None:
    """
    Index schema chunks in Pinecone if the index is empty.
    Safe to call every run — skips upsert when vectors already exist.
    """
    if vectordb.vector_count() == 0:
        print("Index empty — upserting schema chunks...")
        chunks = build_schema_chunks(engine)
        vectordb.load_data(chunks)
        print(f"Indexed {len(chunks)} tables")
    else:
        print(f"Pinecone has {vectordb.vector_count()} vectors")


def retrieve_schema_for_question(
    vectordb: VectorDB,
    engine,
    user_query: str,
    k: int = 3,
    similarity_threshold: float = 0.3,
) -> tuple[str, list[str]]:
    """
    Core RAG step (my_application.md Step 4):
        question → embed → Pinecone → table names → schema text for LLM

    Returns:
        (retrieved_schema_string, list_of_table_names)
    """
    results = vectordb.search(
        user_query,
        k=k,
        similarity_threshold=similarity_threshold,
    )

    if not results:
        raise ValueError("No tables retrieved — lower similarity_threshold or re-index")

    # Dedupe table names; preserve search ranking order
    retrieved_tables = list(dict.fromkeys(
        r["metadata"]["table"] for r in results
    ))

    # Rebuild full schema text from Neon for ONLY retrieved tables
    retrieved_schema = build_schema_for_tables(engine, retrieved_tables)

    return retrieved_schema, retrieved_tables


# =============================================================================
# LLM prompt + parsing (same as basics_3 — schema arg is now *retrieved* only)
# =============================================================================

def generate_prompt_with_cot(schema: str, query: str) -> str:
    examples = """
        <example>
        <question>List all employees in the HR department.</question>
        <thinking>
        1. Join employees and departments on department_id.
        2. Filter departments.name = 'HR'.
        </thinking>
        <sql>SELECT e.name FROM employees e JOIN departments d ON e.department_id = d.id WHERE d.name = 'HR';</sql>
        </example>

        <example>
        <question>What is the average salary of employees hired in 2022?</question>
        <thinking>
        1. Use employees table only.
        2. Filter hire_date year = 2022 (PostgreSQL EXTRACT).
        </thinking>
        <sql>SELECT AVG(salary) FROM employees WHERE EXTRACT(YEAR FROM hire_date) = 2022;</sql>
        </example>
        """

    return f"""
        You are a PostgreSQL expert. Convert natural language to exactly one SELECT query.

        <schema>
        {schema}
        </schema>

        <examples>
        {examples}
        </examples>

        <query>
        {query}
        </query>

        Follow this process:
        1. Inside <thinking> tags: which tables, JOIN keys, filters, aggregates.
        2. Inside <sql> tags: one PostgreSQL SELECT only. No other text.
    """


def parse_llm_response(response: str) -> tuple[str, str]:
    """Extract thinking and sql from model output."""
    thinking = ""
    sql = ""

    if "<thinking>" in response and "</thinking>" in response:
        thinking = response.split("<thinking>")[1].split("</thinking>")[0].strip()

    if "<sql>" in response and "</sql>" in response:
        sql = response.split("<sql>")[1].split("</sql>")[0].strip()
    else:
        raise ValueError("Model did not return <sql> tags")

    return thinking, sql


def generate_sql(prompt: str) -> str:
    response = client.responses.create(
        model="gpt-5.5",
        reasoning={"effort": "low"},
        input=[{"role": "user", "content": prompt}],
    )
    return response.output_text


def run_sql(engine, sql: str):
    """Execute validated SELECT against Neon."""
    cleaned_sql = sql.strip().rstrip(";")

    if not cleaned_sql.upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")

    with engine.connect() as conn:
        result = conn.execute(text(cleaned_sql))
        columns = list(result.keys())
        rows = result.fetchall()

    return columns, rows


# =============================================================================
# Main — RAG ask pipeline
# =============================================================================

def main() -> None:
    # --- Setup vector store ---
    vectordb = VectorDB()
    ensure_index_populated(vectordb, engine)

    user_query = (
        "What are the names and hire dates of employees in the Engineering "
        "department, ordered by salary?"
    )

    # --- RAG retrieval (replaces full get_schema_info in basics_3) ---
    retrieved_schema, retrieved_tables = retrieve_schema_for_question(
        vectordb, engine, user_query, k=3
    )

    print("Retrieved tables:", retrieved_tables)
    print("Retrieved schema:\n", retrieved_schema)
    print("=" * 40)

    # -------------------------------------------------------------------------
    # Block 4F — RAG lineage (debug / audit: what context did the LLM get?)
    # Add HERE: right after retrieval, BEFORE building the prompt.
    # Later you can log this to a file/DB (see data_lineage_study_guide.md).
    # -------------------------------------------------------------------------
    print("RAG lineage:")
    print("  question:", user_query)
    print("  retrieved_tables:", retrieved_tables)
    for i, table in enumerate(retrieved_tables):
        print(f"  rank_{i + 1}:", table)
    print("=" * 40)

    # -------------------------------------------------------------------------
    # Block 4G — Optional: compare prompt size (learning exercise)
    # Add HERE: after 4F, still before generate_prompt_with_cot.
    # Shows how RAG shrinks context when you have many tables (2-table DB: small diff).
    # -------------------------------------------------------------------------
    from sqlalchemy import inspect as sa_inspect

    all_tables = sa_inspect(engine).get_table_names(schema="public")
    full_schema = build_schema_for_tables(engine, all_tables)
    print("Schema size comparison (chars):")
    print("  full schema:      ", len(full_schema))
    print("  retrieved schema: ", len(retrieved_schema))
    print("=" * 40)

    # --- Prompt uses RETRIEVED schema only (the whole point of basics_4) ---
    prompt = generate_prompt_with_cot(schema=retrieved_schema, query=user_query)

    # --- LLM → SQL ---
    result = generate_sql(prompt)
    print("Result : ", result)
    print(" =========================== ")
    print("\n\n")
    thinking, sql = parse_llm_response(result)

    print("Thinking:", thinking)
    print("SQL:", sql)
    print("=" * 40)

    # --- Execute ---
    try:
        columns, rows = run_sql(engine, sql)
        print("Query result:")
        print("  columns:", columns)
        for row in rows[:10]:
            print(" ", row)
    except Exception as e:
        print("SQL failed:", e)
        print("SQL was:", sql)


if __name__ == "__main__":
    main()
