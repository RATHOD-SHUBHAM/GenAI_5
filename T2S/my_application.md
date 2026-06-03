# Text-to-SQL Application

## What Am I Building?

I am building a **Text-to-SQL application** that allows users to ask business questions in natural language and receive answers from a database **without writing SQL**.

### The Core Problem

Users speak **business language**, while databases are organized using **table names**, **column names**, and **relationships**.

### The Approach

To bridge that gap, I use a **Retrieval-Augmented Generation (RAG)** architecture **before** SQL generation.

---

## How Does It Work?

### Step 1: Database Understanding (One-Time Process)

Before any user asks questions, I scan the database and extract:

- Tables
- Columns
- Relationships
- Primary Keys
- Foreign Keys
- Descriptions
- Business Definitions

**Example — technical schema:**

```
Table: orders

Columns:
  order_id
  customer_id
  amount
  order_date
```

**Example — business description:**

- Contains customer purchases.
- Used for revenue reporting.
- One row per order.

---

### Step 2: Create Embeddings

For every table, I create **two embeddings**:

**Technical embedding**

```
Table: orders

Columns:
  order_id
  customer_id
  amount
  order_date
```

**Business embedding**

- Contains customer purchases.
- Used for revenue reporting.
- Tracks customer spending.

These embeddings are stored in a **vector database**, creating a searchable knowledge base of the database schema.

---

### Step 3: User Asks a Question

**Example:**

> Who are our top customers by revenue?

---

### Step 4: Retrieval Layer (NLP Table Search)

Instead of sending the entire database schema to the LLM, I first search the vector database.

The retrieval system finds relevant tables, for example:

- `customers`
- `orders`
- `payments`

along with relevant business definitions such as:

- Revenue = `SUM(payment_amount)`

This reduces noise and gives the model only the information needed for the question.

---

### Step 5: SQL Generation

The LLM receives:

- User question
- Relevant tables
- Relevant columns
- Business definitions
- Relationships

and generates SQL.

**Example:**

```sql
SELECT
    c.customer_name,
    SUM(p.payment_amount) AS revenue
FROM customers c
JOIN orders o
    ON c.customer_id = o.customer_id
JOIN payments p
    ON o.order_id = p.order_id
GROUP BY c.customer_name
ORDER BY revenue DESC
LIMIT 10;
```

---

### Step 6: SQL Validation

Before execution, the query is validated.

**Checks include:**

- Only `SELECT` statements allowed
- Table exists
- Column exists
- Syntax valid

---

### Step 7: Query Execution

The validated SQL is executed against the database.

---

### Step 8: Error Correction Loop

If execution fails, the following are sent back to the LLM:

- Question
- Generated SQL
- Database error

The model generates a corrected query and retries.

---

### Step 9: Final Response

The user receives:

- Result table
- Generated SQL
- Natural language explanation
- One-line summary

---

## Pipeline Summary (One Line)

I first convert the database into a searchable knowledge base using embeddings, retrieve the most relevant schema and business context for a user's question, and then use an LLM to generate, validate, and execute SQL safely.

---

## Evaluation Framework

For Text-to-SQL there are **four things to evaluate**:

### 1. Retrieval

**Question:** Did we retrieve the correct tables?

| | |
|---|---|
| **Question** | Top customers by revenue |
| **Expected tables** | `customers`, `orders`, `payments` |

---

### 2. SQL Validity

**Question:** Can the SQL run?

**Checks:**

- Syntax valid
- Tables exist
- Columns exist

---

### 3. SQL Correctness

**Question:** Does SQL satisfy the business intent?

| | |
|---|---|
| **Question** | Revenue by month |

**Checks:**

- Uses revenue definition
- Groups by month
- Aggregates correctly

This is where **LLM-as-a-judge** is often used.

---

### 4. Answer Correctness

**Question:** Does the final answer match expected behavior?

| | |
|---|---|
| **Expected** | Revenue = 1.2M |
| **Generated** | Revenue = 1.2M |
| **Result** | Pass |
