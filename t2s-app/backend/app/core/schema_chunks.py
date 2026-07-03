"""
Schema chunks for RAG — one chunk per table from live Neon/Postgres schema.
"""

from sqlalchemy import inspect


def _build_table_text(insp, table_name: str) -> str:
    columns = insp.get_columns(table_name)
    table_info = f"Table: {table_name}\n"

    pk = insp.get_pk_constraint(table_name)
    if pk and pk.get("constrained_columns"):
        pk_cols = ", ".join(pk["constrained_columns"])
        table_info += f"  Primary key: {pk_cols}\n"

    for col in columns:
        col_name = col["name"]
        col_type = col["type"]
        table_info += f"  - {col_name} ({col_type})\n"

    fks = insp.get_foreign_keys(table_name)
    if fks:
        table_info += "  Foreign keys:\n"
        for fk in fks:
            local_cols = ", ".join(fk["constrained_columns"])
            remote_table = fk["referred_table"]
            remote_cols = ", ".join(fk["referred_columns"])
            table_info += f"    - ({local_cols}) -> {remote_table}({remote_cols})\n"

    return table_info.rstrip()


def build_schema_chunks(engine) -> list[dict]:
    insp = inspect(engine)
    chunks = []

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
    insp = inspect(engine)
    parts = []
    for table_name in table_names:
        parts.append(_build_table_text(insp, table_name))
    return "\n\n".join(parts)
