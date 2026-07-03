"""Step 9 — natural language answer from query results."""

import json
from typing import Any

from openai import OpenAI

# Don't send huge result sets to the LLM
_MAX_ROWS_FOR_SUMMARY = 20


def generate_nl_answer(
    client: OpenAI,
    question: str,
    columns: list[str],
    rows: list[list[Any]],
) -> str:
    """
    Second LLM call: turn tabular results into a plain-English sentence.
    Runs only after SQL succeeds.
    """
    sample_rows = rows[:_MAX_ROWS_FOR_SUMMARY]
    truncated = len(rows) > _MAX_ROWS_FOR_SUMMARY

    results_preview = {
        "columns": columns,
        "rows": sample_rows,
        "total_rows": len(rows),
        "truncated": truncated,
    }

    prompt = f"""
        You are a helpful business analyst. A user asked a database question and received query results.

        Write a clear, natural-language answer in 1–3 short sentences.
        - Use the actual numbers and names from the results.
        - Answer the user's question directly (e.g. "There are 200 employees in the database.").
        - Do NOT mention SQL, tables, queries, or databases.
        - If results are empty, say no matching data was found.

        <question>
        {question}
        </question>

        <results>
        {json.dumps(results_preview, default=str)}
        </results>
    """

    response = client.responses.create(
        model="gpt-5.5",
        reasoning={"effort": "low"},
        input=[{"role": "user", "content": prompt}],
    )

    return response.output_text.strip()
