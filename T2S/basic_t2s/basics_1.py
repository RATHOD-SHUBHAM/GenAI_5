# Creating a basic text to sql application

# we have to pass database schema for model to understand the database


# ===================================================================================================
# Load the api
# ===================================================================================================
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("ADD DATABASE_URL API")


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("ADD OPENAI_API_KEY API")

# ===================================================================================================
# Make the connection
# ===================================================================================================
engine = create_engine(DATABASE_URL, pool_pre_ping = True)

# ===================================================================================================
# Bring in the schema, and their relationship like public key and foreign key
# ===================================================================================================

def get_schema_info(engine) -> str:
    """
    Build a text description of all user tables for the LLM.
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

        table_info = f"Table : {table_name}\n"

        # --- primary key  ---
        pk = insp.get_pk_constraint(table_name)
        print(" Primary key: ", pk)
        print(" =========================== ")
        print("\n\n")

        if pk and pk.get("constrained_columns"):
            pk_cols = ", ".join(pk["constrained_columns"])
            table_info  += f" Primary key : {pk_cols}\n"
        
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
            table_info += " Foreign Keys: \n"

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
# Now that we have our schema information, let's create a basic prompt:
# ===================================================================================================
def generate_prompt(schema, query):
    prompt = f"""
    You are an AI assistant that converts natural language queries into SQL.
    You are an expert in feild of data engineering and have masters SQL.
    Given the following SQL database schema:
    <schema>
    {schema}
    </schema>

    Convert the following natural language query into SQL:
    <query>
    {query}
    </query>

    Provide only the SQL query in response, enclosed within <sql> tags.
    """

    return prompt


user_query = "What are the names of employee in Engineering Department"
prompt = generate_prompt(schema = schema, query = user_query)
print(" Prompt: ",prompt)
print(" =========================== ")
print("\n\n")


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
sql = result.split("<sql>")[1].split("</sql>")[0].strip()
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
SELECT e.name, d.name AS department
FROM employees e
JOIN departments d ON e.department_id = d.id
WHERE d.name = 'Engineering'
LIMIT 10;
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
    print("SQL was:", sql)
    print(" =========================== ")
    print("\n\n")