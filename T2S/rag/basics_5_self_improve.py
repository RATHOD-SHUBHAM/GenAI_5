"""
basics_5_self_improve.py — RAG + self-improvement loop (basics_4 + Step 8).

WHEN YOU REVISIT THIS FILE, READ THIS FIRST
-------------------------------------------
basics_4 stops if SQL fails. This file adds a RETRY LOOP:

    Try 1:  RAG finds relevant tables → LLM writes SQL → Neon runs it
            ↓ if Postgres errors (bad column, syntax, etc.)
    Try 2:  Send the ERROR + failed SQL back to LLM → new SQL → run again
            ↓ still failing?
    Try 3:  same fix prompt → last chance
            ↓
            give up (return None)

The key idea: Postgres error messages are ground truth ("column X does not exist").
The LLM often fixes SQL when it sees that — no manual debugging.

Two prompt types:
    - Attempt 1 → generate_prompt_with_rag()  (search Pinecone + full CoT prompt)
    - Attempt 2+ → generate_fix_prompt()      (schema + question + bad SQL + error)

We do NOT re-run Pinecone on retry — same retrieved_schema from attempt 1 is enough.
Wrong SQL is usually a generation bug, not wrong table retrieval.

See also: T2S/learning/text_to_sql_project_guide.md (RAG flow)
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from schema_chunks import build_schema_for_tables, build_schema_chunks
from pinecone_db import VectorDB

# -----------------------------------------------------------------------------
# .env lives at GenAI_5/ (two levels up from T2S/rag/)
# engine  = pooled connection to Neon (reuse for all SQL + inspect)
# client  = OpenAI for both SQL generation and (via pinecone_db) embeddings
# -----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL missing — check GenAI_5/.env")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
client = OpenAI()


# =============================================================================
# RAG (unchanged from basics_4 — only used on ATTEMPT 1)
# =============================================================================

def ensure_index_populated(vectordb: VectorDB, engine) -> None:
    """
    Pinecone must have embedded schema chunks before search works.
    If vector_count == 0, read tables from Neon and upsert (see pinecone_db.py).
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
    Pinecone returns WHICH tables match the question.
    Neon rebuilds the full column/PK/FK text for those tables only.

    Returns (schema_string, table_names) — both needed later:
      - schema_string → goes into LLM prompt
      - table_names   → print for debugging / lineage
    """
    results = vectordb.search(
        user_query,
        k=k,
        similarity_threshold=similarity_threshold,
    )

    if not results:
        raise ValueError("No tables retrieved — lower similarity_threshold or re-index")

    retrieved_tables = list(dict.fromkeys(
        r["metadata"]["table"] for r in results
    ))
    retrieved_schema = build_schema_for_tables(engine, retrieved_tables)

    return retrieved_schema, retrieved_tables


# =============================================================================
# PROMPTS — two different prompts for two different situations
# =============================================================================

def generate_prompt_with_cot(schema: str, query: str) -> str:
    """
    Standard Text-to-SQL prompt: schema + few-shot examples + user question.
    Model must return <thinking> (plan) and <sql> (executable query).
    Used inside generate_prompt_with_rag on attempt 1.
    """
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


def generate_prompt_with_rag(
    vectordb: VectorDB,
    engine,
    user_query: str,
) -> tuple[str, str, list[str]]:
    """
    ATTEMPT 1 ONLY: RAG retrieve → then build CoT prompt.

    We return retrieved_schema separately because retries need the SAME schema
    in generate_fix_prompt — we don't search Pinecone again on attempt 2/3.
    """
    retrieved_schema, retrieved_tables = retrieve_schema_for_question(
        vectordb, engine, user_query, k=3
    )
    prompt = generate_prompt_with_cot(schema=retrieved_schema, query=user_query)
    return prompt, retrieved_schema, retrieved_tables


def generate_fix_prompt(
    schema: str,
    user_query: str,
    failed_sql: str,
    db_error: str,
) -> str:
    """
    ATTEMPT 2+ ONLY: the model already tried once and Postgres rejected it.

    Four things the model needs to fix SQL:
      - schema        → don't invent columns
      - user_query    → remember the original business question
      - failed_sql    → what it wrote wrong
      - db_error      → exact message from Postgres (e.g. "column dept_name does not exist")

    Without db_error, the model guesses blindly. With it, fixes are much better.
    """
    return f"""
        You are a PostgreSQL expert. The SQL below failed on the database.

        <schema>
        {schema}
        </schema>

        <query>
        {user_query}
        </query>

        <failed_sql>
        {failed_sql}
        </failed_sql>

        <database_error>
        {db_error}
        </database_error>

        Analyze the error. Use only tables/columns from the schema.
        Return:
        1. <thinking> what was wrong and what you changed </thinking>
        2. <sql> one corrected PostgreSQL SELECT </sql>
    """


# =============================================================================
# LLM call + run SQL on Neon
# =============================================================================

def parse_llm_response(response: str) -> tuple[str, str]:
    """
    Split model output into thinking (for you) and sql (for Neon).
    ONLY sql goes to run_sql — never execute thinking text.
    """
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
    """One LLM call per loop iteration — returns raw text with XML-like tags."""
    response = client.responses.create(
        model="gpt-5.5",
        reasoning={"effort": "low"},
        input=[{"role": "user", "content": prompt}],
    )
    return response.output_text


def run_sql(engine, sql: str) -> tuple[list, list]:
    """
    Run one SELECT on Neon. RAISES on failure.

    Used directly in basics_4. Here we wrap it in execute_sql_with_feedback
    so a failed query doesn't crash the retry loop.
    """
    cleaned_sql = sql.strip().rstrip(";")

    if not cleaned_sql.upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")

    with engine.connect() as conn:
        result = conn.execute(text(cleaned_sql))
        columns = list(result.keys())
        rows = result.fetchall()

    return columns, rows


def execute_sql_with_feedback(
    engine,
    sql: str,
) -> tuple[bool, tuple | None, str]:
    """
    WHY THIS EXISTS (read this when revisiting):
    ------------------------------------------
    run_sql() raises an exception when SQL is bad → program would exit.
    The self-improvement loop needs to CATCH that error and pass it to the LLM.

    Returns:
        (True,  (columns, rows), "Query executed successfully.")  → stop loop, success
        (False, None,            "column x does not exist...")     → loop continues,
                                                                     this string becomes
                                                                     db_error in fix prompt

    feedback variable in the loop holds that error string between iterations.
    """
    try:
        columns, rows = run_sql(engine, sql)
        return True, (columns, rows), "Query executed successfully."
    except (SQLAlchemyError, ValueError) as e:
        return False, None, str(e)


# =============================================================================
# THE MAIN LOOP — ask_with_self_improvement
# =============================================================================

def ask_with_self_improvement(
    vectordb: VectorDB,
    engine,
    user_query: str,
    max_attempts: int = 3,
) -> tuple[str | None, tuple | None, int]:
    """
    Orchestrates: prompt → LLM → SQL → execute → retry on failure.

    Variables that carry state across loop iterations:
    ┌──────────────────┬────────────────────────────────────────────────────┐
    │ sql              │ last SQL the model generated (sent to fix prompt)  │
    │ feedback         │ Postgres error string from last failed execute     │
    │ retrieved_schema │ schema from attempt 1 (reused on retries)          │
    │ retrieved_tables │ table names from RAG (debug only after attempt 1)  │
    └──────────────────┴────────────────────────────────────────────────────┘

    attempt counter: 0, 1, 2 internally → printed as Attempt 1/3, 2/3, 3/3
    (+1 is only for display; if attempt == 0 still means first try)
    """
    feedback = None       # Postgres error message; None until first failure
    sql = None            # Last generated SQL; passed to fix prompt on retry
    retrieved_schema = None   # Set on attempt 0; kept for attempt 1, 2
    retrieved_tables = None   # For logging which tables RAG picked

    for attempt in range(max_attempts):
        print(f"\n--- Attempt {attempt + 1} / {max_attempts} ---")

        # ── STEP A: Choose which prompt to send ──────────────────────────────
        if attempt == 0:
            # First try: search Pinecone, build small schema, full CoT prompt
            prompt, retrieved_schema, retrieved_tables = generate_prompt_with_rag(
                vectordb, engine, user_query
            )
            print("Retrieved tables:", retrieved_tables)
        else:
            # Retry: don't re-RAG — use same schema + tell model what failed
            prompt = generate_fix_prompt(
                schema=retrieved_schema,
                user_query=user_query,
                failed_sql=sql,       # what we ran last iteration
                db_error=feedback,    # error from execute_sql_with_feedback
            )

        # ── STEP B: LLM generates SQL ───────────────────────────────────────
        response = generate_sql(prompt)
        thinking, sql = parse_llm_response(response)
        print("Thinking:", thinking)
        print("SQL:", sql)

        # ── STEP C: Try running on Neon ───────────────────────────────────────
        success, result, feedback = execute_sql_with_feedback(engine, sql)
        #                                      ↑
        #                         on failure, feedback = Postgres error for next fix prompt

        if success:
            print("SQL executed successfully!")
            return sql, result, attempt + 1   # attempt+1 = human "succeeded on try 2"

        print("SQL failed:", feedback)
        # loop continues → next iteration uses generate_fix_prompt

    # All attempts exhausted
    print("Maximum attempts reached.")
    return None, None, max_attempts


# =============================================================================
# Entry point — change user_query here to test different questions
# =============================================================================

def main() -> None:
    vectordb = VectorDB()
    ensure_index_populated(vectordb, engine)

    # Hard query: needs GROUP BY, MAX/MIN, HAVING — good test for retry loop
    user_query = (
        "For each department, show the ratio of the highest paid employee's "
        "salary to the lowest paid employee's salary, but only for departments "
        "where this ratio is greater than 3"
    )

    final_sql, result, attempts = ask_with_self_improvement(
        vectordb, engine, user_query, max_attempts=3
    )

    if final_sql:
        columns, rows = result
        print("\nFinal SQL:", final_sql)
        print(f"Succeeded on attempt {attempts}")
        print("Columns:", columns)
        for row in rows[:10]:
            print(row)
    else:
        print("Failed to generate valid SQL after all attempts.")


if __name__ == "__main__":
    main()
