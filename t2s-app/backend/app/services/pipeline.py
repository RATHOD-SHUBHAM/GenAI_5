"""
pipeline.py — RAG + self-improvement loop (from T2S/rag/basics_5_self_improve.py).

Refactored for the API:
  - No global engine/client — passed in as arguments
  - No print() — returns a dict for JSON serialization
  - ask_with_self_improvement() is called by api/routes/ask.py
"""

from typing import Any

from openai import OpenAI

from app.core.schema_chunks import build_schema_chunks, build_schema_for_tables
from app.core.vector_db import VectorDB
from app.services.sql_runner import execute_sql_with_feedback
from app.services.nl_answer import generate_nl_answer


def ensure_index_populated(vectordb: VectorDB, engine) -> None:
    if vectordb.vector_count() == 0:
        chunks = build_schema_chunks(engine)
        vectordb.load_data(chunks)


def retrieve_schema_for_question(
    vectordb: VectorDB,
    engine,
    user_query: str,
    k: int = 3,
    similarity_threshold: float = 0.3,
) -> tuple[str, list[str]]:
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


def generate_prompt_with_rag(
    vectordb: VectorDB,
    engine,
    user_query: str,
) -> tuple[str, str, list[str]]:
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


def parse_llm_response(response: str) -> tuple[str, str]:
    thinking = ""
    sql = ""

    if "<thinking>" in response and "</thinking>" in response:
        thinking = response.split("<thinking>")[1].split("</thinking>")[0].strip()

    if "<sql>" in response and "</sql>" in response:
        sql = response.split("<sql>")[1].split("</sql>")[0].strip()
    else:
        raise ValueError("Model did not return <sql> tags")

    return thinking, sql


def generate_sql(client: OpenAI, prompt: str) -> str:
    response = client.responses.create(
        model="gpt-5.5",
        reasoning={"effort": "low"},
        input=[{"role": "user", "content": prompt}],
    )
    return response.output_text


def ask_with_self_improvement(
    vectordb: VectorDB,
    engine,
    client: OpenAI,
    user_query: str,
    max_attempts: int = 3,
) -> dict[str, Any]:
    feedback = None
    sql = None
    retrieved_schema = None
    retrieved_tables: list[str] | None = None
    last_thinking = ""

    for attempt in range(max_attempts):
        if attempt == 0:
            prompt, retrieved_schema, retrieved_tables = generate_prompt_with_rag(
                vectordb, engine, user_query
            )
        else:
            prompt = generate_fix_prompt(
                schema=retrieved_schema,
                user_query=user_query,
                failed_sql=sql,
                db_error=feedback,
            )

        response = generate_sql(client, prompt)
        thinking, sql = parse_llm_response(response)
        last_thinking = thinking

        success, result, feedback = execute_sql_with_feedback(engine, sql)

        if success:
            columns, rows = result
            answer = generate_nl_answer(
                client=client,
                question=user_query,
                columns=columns,
                rows=rows,
            )
            return {
                "success": True,
                "question": user_query,
                "retrieved_tables": retrieved_tables or [],
                "thinking": last_thinking,
                "sql": sql,
                "columns": columns,
                "rows": rows,
                "answer": answer,
                "attempts": attempt + 1,
            }

    return {
        "success": False,
        "question": user_query,
        "retrieved_tables": retrieved_tables or [],
        "thinking": last_thinking,
        "error": "Could not generate valid SQL after all attempts",
        "last_sql": sql,
        "last_error": feedback,
        "attempts": max_attempts,
    }
