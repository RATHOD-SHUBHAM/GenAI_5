"""
sql_runner.py — execute generated SQL on Neon.

run_sql() raises on failure (used internally).
execute_sql_with_feedback() catches errors so the retry loop in pipeline.py
can pass the Postgres error message back to the LLM without crashing the API.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError


def _json_safe_value(value):
    """Convert Postgres types (Decimal, date, etc.) to JSON-safe Python types."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def run_sql(engine, sql: str) -> tuple[list, list]:
    cleaned_sql = sql.strip().rstrip(";")

    if not cleaned_sql.upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")

    with engine.connect() as conn:
        result = conn.execute(text(cleaned_sql))
        columns = list(result.keys())
        rows = [
            [_json_safe_value(cell) for cell in row]
            for row in result.fetchall()
        ]

    return columns, rows


def execute_sql_with_feedback(
    engine,
    sql: str,
) -> tuple[bool, tuple | None, str]:
    try:
        columns, rows = run_sql(engine, sql)
        return True, (columns, rows), "Query executed successfully."
    except (SQLAlchemyError, ValueError) as e:
        return False, None, str(e)
