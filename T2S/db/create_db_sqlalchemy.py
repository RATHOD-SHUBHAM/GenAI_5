import os
import random
from datetime import datetime, timedelta
from pathlib import Path


from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# =========================================================================================================================================
# Set up connection
# =========================================================================================================================================

# Our .env is two level up, so lets point it there
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

# =========================================================================================================================================
# Establish connection to database
# =========================================================================================================================================

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("Database url missing or not working")

"""
- pool_pre_ping=True: Before using a pooled connection, SQLAlchemy pings Neon. Helps when Neon was idle or dropped the connection.
- Echo: You’ll see every statement in the terminal. Turn echo off once you’re comfortable.
Check: No run yet; this only configures the engine.
"""
engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo = True)


"""
- engine.connect() borrows one connection from the pool.
- text("SELECT version()") is the same SQL as in create_db_neon.py, but through SQLAlchemy.
- .scalar() returns the first column of the first row (the version string).
- Context manager (with) returns the connection to the pool when done.
"""

with engine.connect() as conn:
    version = conn.execute(text("SELECT version()")).scalar()
    print("Connected to: ", version.split(",")[0]) # if this fails there was an error in connection


# =========================================================================================================================================
# Create Table
# =========================================================================================================================================

# CREATE TABLE IF NOT EXISTS: Safe to run multiple times; won’t drop existing tables

# engine.begin(): Opens a transaction; commits on success, rolls back on error.

DDL = """
CREATE TABLE IF NOT EXISTS departments (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL,
    location TEXT
);
CREATE TABLE IF NOT EXISTS employees (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    age             INTEGER,
    department_id   INTEGER REFERENCES departments (id),
    salary          NUMERIC(12, 2),
    hire_date       DATE
);
"""

with engine.begin() as conn:
    conn.execute(text(DDL))

print("Tables created or they already exist")

# =========================================================================================================================================
# Insert into Table
# =========================================================================================================================================

with engine.begin() as conn: # engine.begin(): Opens a transaction; commits on success, rolls back on error.
    count = conn.execute(text("SELECT COUNT(*) FROM departments")).scalar() # COUNT(*) > 0 means you already ran the seed; second run won’t duplicate primary keys.

    if count > 0:
        print("Data already present - skipping seed")
    else:
        print("Empty database - seeding")

        # Insert 10 department
        departments = [
            (1, "HR", "New York"),
            (2, "Engineering", "San Francisco"),
            (3, "Marketing", "Chicago"),
            (4, "Sales", "Los Angeles"),
            (5, "Finance", "Boston"),
            (6, "Customer Support", "Dallas"),
            (7, "Research", "Seattle"),
            (8, "Legal", "Washington D.C."),
            (9, "Product", "Austin"),
            (10, "Operations", "Denver"),
        ]

        conn.execute(
            text(
                "INSERT INTO departments (id, name, location)"
                "VALUES (:id, :name, :location)"                   # :id, :name, :location are bound parameters (not f-strings). Safer and clear.
            ),
            [{"id" : d[0], "name" : d[1], "location" : d[2]} for d in departments], # loop through and keep inserting
        )


        # Insert 200 Employees
        first_names = [
            "John",
            "Jane",
            "Bob",
            "Alice",
            "Charlie",
            "Diana",
            "Edward",
            "Fiona",
            "George",
            "Hannah",
            "Ian",
            "Julia",
            "Kevin",
            "Laura",
            "Michael",
            "Nora",
            "Oliver",
            "Patricia",
            "Quentin",
            "Rachel",
            "Steve",
            "Tina",
            "Ulysses",
            "Victoria",
            "William",
            "Xena",
            "Yannick",
            "Zoe",
        ]
        last_names = [
            "Smith",
            "Johnson",
            "Williams",
            "Jones",
            "Brown",
            "Davis",
            "Miller",
            "Wilson",
            "Moore",
            "Taylor",
            "Anderson",
            "Thomas",
            "Jackson",
            "White",
            "Harris",
            "Martin",
            "Thompson",
            "Garcia",
            "Martinez",
            "Robinson",
            "Clark",
            "Rodriguez",
            "Lewis",
            "Lee",
            "Walker",
            "Hall",
            "Allen",
            "Young",
            "King",
        ]

        employees = []
        for i in range(1, 201):
            employees.append({
                "id" : i,
                "name" : f"{random.choice(first_names)} {random.choice(last_names)}",
                "age": random.randint(22, 65),
                "department_id": random.randint(1, 10),
                "salary": round(random.uniform(40000, 200000), 2),
                "hire_date": (
                    datetime.now() - timedelta(days=random.randint(0, 3650))
                ).strftime("%Y-%m-%d"),
            })

        conn.execute(
            text(
                "INSERT INTO employees"
                "(id, name, age, department_id, salary, hire_date)"
                "VALUES (:id, :name, :age, :department_id, :salary, :hire_date)"
            ),
            employees
        )


        print("Seeded 10 departments and 200 Employees")


# =========================================================================================================================================
# Verify the seed
# =========================================================================================================================================
with engine.connect() as conn:
    dept_count = conn.execute(text("SELECT COUNT(*) FROM departments")).scalar()
    emp_count = conn.execute(text("SELECT COUNT(*) FROM employees")).scalar()

    print(f"departments: {dept_count} rows")
    print(f"employees : {emp_count} rows")


    # Join proves FK relationship works.
    sample = conn.execute(
        text(
            "SELECT e.name, d.name AS dept FROM employees e "      # there is space after e on purpose, it will be employees e JOIN departments
            "JOIN departments d ON e.department_id = d.id LIMIT 3"
        )
    )

    for row in sample:
        print(row)
