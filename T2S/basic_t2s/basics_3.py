# Using Chain-of-Thought Prompting
# Chain-of-thought prompting encourages the model to break down complex problems into steps. For Text to SQL tasks, this can help with more complex queries that require multiple operations or careful consideration of the database schema.


# ===================================================================================================
# Load the api
# ===================================================================================================
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine , inspect, text

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("ADD DATABASE_URL API")


# ===================================================================================================
# Make the connection
# ===================================================================================================
engine = create_engine(DATABASE_URL, pool_pre_ping = True)


# ===================================================================================================
# Bring in the schema, and their relationship like public key and foreign key
# ===================================================================================================
def get_schema_info(engine) -> str:
    """
    Build a text description of all user tables for LLM.
    """

    insp = inspect(engine) # inspect is SQLAlchemy’s schema reader — it asks Postgres what tables/columns exist.
    print(" insp: ", insp)
    print(" =========================== ")
    print("\n\n")

    schema_parts = []

    for table_name in insp.get_table_names():
        columns = insp.get_columns(table_name)
        print(" Columns: ", columns)
        print(" =========================== ")
        print("\n\n")

        table_info = f"Table: {table_name}\n"

        # --- primary key  ---
        pk = insp.get_pk_constraint(table_name)
        print(" Primary key: ", pk)
        print(" =========================== ")
        print("\n\n")

        if pk and pk.get("constrained_columns"):
            pk_cols = ", ".join(pk["constrained_columns"])
            table_info += f" Primary key : {pk_cols}\n"
        
        print(" table info 1: ", table_info)
        print(" =========================== ")
        print("\n\n")

        # --- Schema ---
        for col in columns:
            # col is a dict: name, type, nullable, default, ...
            col_name = col["name"]
            col_type = col["type"]
            table_info += f" -{col_name} ({col_type})\n"
        
        print(" table info 2: ", table_info)
        print(" =========================== ")
        print("\n\n")
        
        # --- foreign keys  ---
        fks = insp.get_foreign_keys(table_name)
        print(" Foreign Key: ", fks)
        print(" =========================== ")
        print("\n\n")

        if fks:
            table_info += "Foreign Keys: \n"

            for fk in fks:
                local_cols = ", ".join(fk["constrained_columns"])
                remote_table = fk["referred_table"]
                remote_cols = ", ".join(fk["referred_columns"])
                table_info += f"  - ({local_cols}) -> {remote_table}({remote_cols})\n"
            
            print(" table info 3: ", table_info)
            print(" =========================== ")
            print("\n\n")
        
        schema_parts.append(table_info.rstrip())

        print("schema : ", schema_parts)
        print(" =========================== ")
        print("\n\n")
    
    return "\n\n".join(schema_parts)


schema = get_schema_info(engine)
print(schema)
print(" =========================== ")
print("\n\n")



# ===================================================================================================
# Now that we have our schema information, let's create a improved prompt from previous basic prompt:
# ===================================================================================================
def generate_prompt_with_cot(schema, query):
    examples = """
        <example>
        <question>List all employees in the HR department.</question>
        <thinking>
        1. We need to join the employees and departments tables.
        2. We'll match employees.department_id with departments.id.
        3. We'll filter for the HR department.
        4. We only need to return the employee names.
        </thinking>
        <sql>SELECT e.name FROM employees e JOIN departments d ON e.department_id = d.id WHERE d.name = 'HR';</sql>
        </example>

        <example>
        <question>What is the average salary of employees hired in 2022?</question>
        <thinking>
        1. We need to work with the employees table.
        2. We need to filter for employees hired in 2022.
        3. We'll use the YEAR function to extract the year from the hire_date.
        4. We'll calculate the average of the salary column for the filtered rows.
        </thinking>
        <sql>SELECT AVG(salary) FROM employees WHERE YEAR(hire_date) = 2022;</sql>
        </example>
        """

    prompt = f"""
        You are an AI assistant that converts natural language queries into SQL.
        You are an expert in feild of data engineering and have mastered SQL.

        Given the following SQL Database schema:
        <schema>
        {schema}
        </schema>

        Here are some examples of how to convert natural language queries into SQL:
        <examples>
        {examples}
        </examples>

        Convert the following natural language query into SQL:
        <query>
        {query}
        </query>

        Within tags follow this process:
        1. Inside <thinking> tags, explain your thought process for creating the SQL query, briefly explain:
        - Which tables you need and why
        - Which JOIN keys you will use (from foreign keys in the schema)
        - Which columns, filters, and aggregates apply

        2. Inside <sql> tags, output exactly ONE PostgreSQL SELECT query.
        No text outside these tags except the two tag blocks.
    """

    return prompt

# Test the new prompt
user_query = "What are the names and hire dates of employees in the Engineering department, ordered by their salary?"
prompt = generate_prompt_with_cot(schema, user_query)
print(" Prompt: ",prompt)
print(" =========================== ")
print("\n\n")


# ===================================================================================================
# Parse SQL and Thinking Block form LLM:
# ===================================================================================================
def parse_llm_response(response:str) -> tuple[str, str]:
    """
    Return (thinking, sql).
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


# ===================================================================================================
# Now let's use this prompt to generate SQL:
# ===================================================================================================
from openai import OpenAI
client = OpenAI()

def generate_sql(prompt):
    response = client.responses.create(
        model="gpt-5.5",
        reasoning={"effort": "low"},
        input=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    print(response.output_text)
    print(" =========================== ")
    print("\n\n")
    return response.output_text

# Generate SQL
result = generate_sql(prompt)
print("Generated result : ", result)
print(" =========================== ")
print("\n\n")
thinking, sql =  parse_llm_response(result)
print("Generated thinking : ", thinking)
print(" =========================== ")
print("\n\n")
print("Generated SQL : ", sql)
print(" =========================== ")
print("\n\n")
    

# ===================================================================================================
# Test the generated SQL query
# ===================================================================================================

def run_sql(engine, sql:str):
    cleaned_sql = sql.strip().rstrip(";")

    if not cleaned_sql.upper().startswith("SELECT"):
        raise ValueError("Only SELECT QUERIES ARE ALLOWED FOR THIS TEST")
    
    with engine.connect() as conn:
        result = conn.execute(text(cleaned_sql))
        columns = list(result.keys())
        rows = result.fetchall()
    
    return columns, rows



# Test 
# 1. Manual Test
test_sql = """
SELECT e.name, e.hire_date 
FROM employees e 
JOIN departments d ON e.department_id = d.id 
WHERE d.name = 'Engineering' 
ORDER BY e.salary;
"""
print(run_sql(engine, test_sql))
print(" =========================== ")
print("\n\n")

# 2. LLM SQL TEST
try:
    result = run_sql(engine, sql)
    print("Query result:")
    print(result)
    print(" =========================== ")
    print("\n\n")
    columns, rows = result 
    print(columns)
    for row in rows:
        print(row)
    print(" =========================== ")
    print("\n\n")
except Exception as e:
    print("SQL failed:", e)
    print("Thinking was:", thinking)
    print(" =========================== ")
    print("\n\n")
    print("SQL was:", sql)
    print(" =========================== ")
    print("\n\n")