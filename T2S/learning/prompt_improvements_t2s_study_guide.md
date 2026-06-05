# Prompt Improvements for Text-to-SQL

Ways to improve the basic prompt in `basics_1.py` / `basics_2.py` — few-shot, chain-of-thought, constraints, and production tradeoffs.

---

## 1. What’s wrong with the “basic” prompt?

`basics_1.py` uses a simple template: role + full schema + user question + “return SQL in `<sql>` tags.”

That works for learning, but models often fail when:

| Problem | Symptom |
|---------|---------|
| Vague role | Extra prose, wrong dialect, markdown fences |
| No dialect | SQLite-style SQL on Postgres (or vice versa) |
| No JOIN pattern | Wrong join keys despite FK in schema |
| No output rules | Missing `<sql>` tags → parse crash |
| No examples | Inconsistent style across questions |
| Schema too long | Lost columns, hallucinated tables |

Prompt engineering here means **reducing ambiguity** and **showing the pattern you want**.

---

## 2. Improvement ladder (easiest → advanced)

```text
1. Clear system rules + Postgres dialect
2. Structured tags (<schema>, <query>, <sql>)
3. Few-shot examples (basics_2.py)
4. Chain-of-thought (reason → then SQL)
5. Decomposed steps (tables → SQL → validate)
6. RAG (only relevant schema) — not prompt-only, but biggest win at scale
```

---

## 3. Stronger system instructions (no examples yet)

Replace fluffy role text with **checklist-style rules**:

```text
You are a PostgreSQL expert. Convert the user's question into exactly ONE read-only SQL query.

Rules:
- Dialect: PostgreSQL (Neon). Use standard JOIN syntax.
- Only SELECT. No INSERT, UPDATE, DELETE, DROP, or DDL.
- Use ONLY tables and columns from <schema>. Do not invent names.
- Use foreign keys in the schema to choose JOIN conditions.
- Prefer table aliases (e, d) for readability.
- String literals: use single quotes for text values.
- If the question implies one row (oldest, highest), use ORDER BY ... LIMIT 1.
- If listing many rows, add LIMIT 100 unless the user specifies otherwise.
- Output ONLY the SQL inside <sql>...</sql> tags. No explanation outside tags.
```

**Why it helps:** Each rule fixes a **class** of mistakes you’ve seen in `run_sql` failures.

---

## 4. Few-shot prompting (`basics_2.py`)

**Idea:** Show 2–4 **question → SQL** pairs that match **your** schema (`employees`, `departments`) before the real user question.

**What each example should teach:**

| Example type | Teaches |
|--------------|---------|
| JOIN + WHERE on department name | `employees` ↔ `departments` via `department_id` |
| `AVG(salary)` + JOIN | Aggregations with filter |
| `ORDER BY` + `LIMIT 1` | Superlatives (oldest, top) |

**Format — pick ONE style and stay consistent:**

```text
<example>
<question>List all employees in the HR department.</question>
<sql>SELECT e.name FROM employees e JOIN departments d ON e.department_id = d.id WHERE d.name = 'HR';</sql>
</example>
```

**Tips:**

- Use **real table/column names** from your Neon DB — not `orders` / `customers` unless you have them.
- Keep examples **short**; 3 strong examples beat 10 noisy ones.
- Match **output format** to your parser (`<sql>` tags if you split on those).
- Fix typos in tags (e.g. `</query>` not `</<query>`) — broken XML confuses the model.

**Why it helps:** Few-shot is **pattern matching** — the model copies JOIN structure and alias style from examples.

---

## 5. Chain-of-thought (CoT)

**Idea:** Ask the model to **reason briefly** before writing SQL.

### Option A — Think inside the prompt, SQL only in tags (recommended for parsing)

```text
Before writing SQL, briefly reason inside <thinking> tags:
1. Which tables are needed?
2. Which JOIN keys from foreign keys?
3. Which filters and aggregates?

Then output the final query ONLY inside <sql>...</sql>.
```

**Parse only `<sql>`** for `run_sql` — ignore `<thinking>` for execution.

**Why it helps:** Reduces wrong JOINs and missing `WHERE` clauses; you still get one executable string.

### Option B — Reasoning in the API (`reasoning={"effort": "low"}`)

You already use this in `generate_sql` with the Responses API. That’s **hidden CoT** — the model thinks before `output_text`.

**Tradeoff:** You don’t see the reasoning unless the API exposes it; harder to debug retrieval/JOIN choices.

### When CoT hurts

- Very long reasoning blows the context window.
- If you accidentally execute `<thinking>` as SQL, you break `run_sql`.
- Production: always **strip and validate** — only run what’s inside `<sql>`.

---

## 6. Split system vs user messages

Instead of one giant string, use **roles** (Chat Completions / Responses):

| Role | Content |
|------|---------|
| **System** | Dialect, safety rules, output format |
| **User** | `<schema>` + few-shot examples + actual `<query>` |

**Why it helps:** Models treat system instructions as higher priority; schema and question stay in user content.

Example shape:

```python
input=[
    {"role": "system", "content": SYSTEM_RULES},
    {"role": "user", "content": f"<schema>{schema}</schema>\n<examples>...</examples>\n<query>{query}</query>"},
]
```

---

## 7. Other high-impact tweaks

### PostgreSQL dialect hint

```text
Database: PostgreSQL 16 on Neon. Use DATE columns as-is. Use NUMERIC for salary.
```

Stops SQLite-isms like `AUTOINCREMENT` or wrong date functions.

### Negative instructions (what NOT to do)

```text
Do NOT use tables not listed in the schema.
Do NOT use SELECT * unless the user asks for all columns.
Do NOT add explanations outside <sql> tags.
```

Often as effective as positive rules.

### Column grounding

```text
When filtering by department name, use departments.name, not employees.name.
```

One line can fix your Engineering department question class.

### Consistent aliases

```text
Always alias employees as e and departments as d.
```

Matches your few-shot examples — consistency matters.

---

## 8. Multi-step “chain” (beyond single prompt)

Not the same as CoT in one message — **multiple LLM calls**:

```text
Step 1: "List only table names needed for this question"  →  [employees, departments]
Step 2: "Given these tables and schema, write SQL"        →  SELECT ...
Step 3 (on error): "This SQL failed with: ... Fix it"     →  corrected SELECT
```

Maps to your full app (`my_application.md` Steps 4–8):

| Step | Technique |
|------|-----------|
| Retrieval | Shrinks schema (RAG) |
| Generation | Few-shot + rules |
| Error loop | Fix-up prompt with Postgres error message |

---

## 9. Comparison table

| Technique | Pros | Cons | Use in your project |
|-----------|------|------|---------------------|
| **Better rules** | Free, easy | Still full schema | Now (`basics_2`) |
| **Few-shot** | Better JOINs/aggregations | Uses tokens; examples must be correct | Now (`basics_2`) |
| **CoT (`<thinking>`)** | Fewer logic errors | Parsing complexity | Try in `basics_2` variant |
| **System/user split** | Clearer priorities | Two strings to maintain | Before FastAPI |
| **Error retry prompt** | Fixes real DB errors | Extra latency/cost | Phase 8 in app doc |
| **RAG** | Scales to large schemas | Infra (embeddings) | After basics |

---

## 10. Example: evolved prompt skeleton

Combines rules + few-shot + CoT + strict output:

```text
[System]
PostgreSQL Text-to-SQL assistant. SELECT only. Tables/columns from schema only.
Output: <thinking> brief plan </thinking> then <sql> one query </sql>.

[User]
<schema>...</schema>

<examples>
  ... 2–3 examples ...
</examples>

<query>What are the names of employees in the Engineering department?</query>
```

**Your parser:**

```python
sql = response.split("<sql>")[1].split("</sql>")[0].strip()
# optional: thinking = response.split("<thinking>")[1].split("</thinking>")[0]
```

---

## 11. How to test if a prompt change helped

Keep the same `user_query` and compare:

| Check | Pass |
|-------|------|
| SQL runs in `run_sql` | No exception |
| Correct JOIN | `e.department_id = d.id` |
| Correct filter | `d.name = 'Engineering'` |
| SELECT only | Passes your guard |
| Tags present | `<sql>` parse works |

Try 3–5 questions:

- Employees in Engineering (JOIN + WHERE)
- Average salary by department (GROUP BY or filtered AVG)
- Oldest employee (ORDER BY + LIMIT 1)
- Count employees per department (GROUP BY + COUNT)

Log **before/after** SQL for each prompt version.

---

## 12. Common mistakes when improving prompts

| Mistake | Fix |
|---------|-----|
| Examples use wrong table names | Match `create_db_sqlalchemy.py` schema |
| Mixed example formats (XML vs User/SQL) | One format everywhere |
| Ask for SQL + essay, parse only SQL | Strict “only inside `<sql>`” |
| Too many examples | 3–5 targeted ones |
| CoT without tag discipline | Never run `<thinking>` in `run_sql` |
| Full schema + huge examples | Token limit; move to RAG later |

---

## 13. One-paragraph summary

Start with **clear Postgres rules** and **consistent `<sql>` output**, add **few-shot** examples that mirror your `employees` / `departments` JOINs (`basics_2.py`), optionally add **chain-of-thought** in `<thinking>` tags while parsing only `<sql>` for execution, then graduate to **error-retry** and **RAG** for production. Prompt improvements fix **generation**; `run_sql` + SELECT guard still fix **safety**.

---

## Related files

- `T2S/basic_t2s/basics_1.py` — basic prompt
- `T2S/basic_t2s/basics_2.py` — few-shot examples
- `T2S/learning/basic_t2s_flow_study_guide.md` — end-to-end pipeline
- `T2S/my_application.md` — RAG + validation + retry loop
