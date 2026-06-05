# Data Lineage Study Guide

A practical reference for analytics, data engineering, and your Text-to-SQL project.

---

## 1. What is data lineage?

**Data lineage** is the record of **where data came from**, **how it was transformed**, and **where it went** — from source systems to final use (reports, APIs, ML models, Text-to-SQL answers).

Think of it as a **trail** you can follow backward and forward:

```text
Source system  →  transform  →  transform  →  table/view  →  dashboard / app / answer
     │                │              │              │
     └────────────────┴──────────────┴──────────────┴── lineage links each step
```

**One-line summary:** Lineage is the documented path of data from source through every transformation to consumption — so you can explain, debug, and govern values, not just see a final number.

---

## 2. Why teams care

| Need | How lineage helps |
|------|-------------------|
| **Trust** | “Is this revenue number correct?” — trace back to raw transactions |
| **Debugging** | A column is wrong → find which job or SQL introduced the error |
| **Compliance** | GDPR, SOX, audit: prove which personal data flowed where |
| **Impact analysis** | “If we change table X, what breaks?” — see downstream reports and pipelines |
| **AI / analytics** | Know which tables and definitions fed a metric or an LLM answer |

Without lineage, you only see the **end result**. With lineage, you see the **story**.

---

## 3. What lineage usually captures

| Element | Examples |
|---------|----------|
| **Sources** | Databases, files, APIs, Kafka topics, SaaS exports |
| **Operations** | ETL jobs, dbt models, Spark steps, Airflow DAGs, manual SQL |
| **Artifacts** | Tables, views, columns, dashboards, datasets, files |
| **Metadata** | Who ran it, when, environment, code version, run ID |
| **Granularity** | Table-level (“report uses A, B”) or column-level (“revenue = SUM(payment_amount)”) |

**Column-level lineage** is the gold standard: you know exactly how `dashboard.revenue` was built from upstream fields.

---

## 4. Example: end-to-end flow

```text
Stripe API
    → ingestion job (Airflow)
    → raw.payments
    → dbt model stg_payments
    → analytics.payments
    → BI dashboard "Monthly Revenue"
```

Lineage for the dashboard tile **Revenue = 1.2M** might show:

```text
dashboard.revenue
    ← analytics.payments.payment_amount
    ← stg_payments.total
    ← raw.payments
    ← Stripe API
```

If revenue looks wrong, you walk **backward** through the chain instead of guessing.

---

## 5. Lineage vs related concepts

| Term | Focus |
|------|--------|
| **Data lineage** | Flow and dependencies over time (upstream + downstream) |
| **Data catalog** | Searchable inventory of datasets (often *displays* lineage) |
| **Data provenance** | Origin and history (common in research and ML) |
| **Metadata** | Descriptions, owners, tags — supports lineage but is not lineage alone |
| **Observability** | Runtime health of pipelines (logs, alerts, SLAs) — complements lineage |

Lineage answers **“where did this come from?”** Observability answers **“did the job run successfully?”**

---

## 6. How lineage is collected

| Approach | How it works |
|----------|----------------|
| **Manual documentation** | Spreadsheets, Confluence — breaks easily |
| **SQL parsing** | Analyze `INSERT … SELECT`, views, dbt SQL |
| **Runtime capture** | OpenLineage events emitted by Spark, Airflow, Flink |
| **Platform-native** | Snowflake, Databricks, BigQuery lineage graphs |
| **dbt** | `ref()` graph → model dependencies in docs |

Common open standards and tools:

- **OpenLineage** — open standard for lineage events
- **Marquez** — metadata service for OpenLineage
- **DataHub**, **Alation**, **Collibra** — enterprise catalogs with lineage UI
- **dbt docs** — lineage within the transformation layer

---

## 7. Upstream vs downstream

| Direction | Question it answers |
|-----------|---------------------|
| **Upstream** | “What feeds this table/column?” (walk back to sources) |
| **Downstream** | “What breaks if I change this table?” (walk forward to consumers) |

**Impact analysis** before a schema change uses **downstream** lineage: rename `department_id` → see every report and job that references it.

---

## 8. Tie-in to your Text-to-SQL project

Your app design (`T2S/my_application.md`) already has pieces that act like **answer-level lineage** for a single user question:

```text
User question
    → retrieval (which tables + business definitions were selected)
    → LLM (generated SQL)
    → validation + execution (Neon / SQLAlchemy)
    → result rows + natural language explanation
```

| Step in your pipeline | Lineage-like artifact |
|------------------------|------------------------|
| Schema indexing | Which tables/columns exist in the vector index |
| RAG retrieval | Which tables and defs were sent to the LLM |
| SQL generation | Exact `SELECT` string |
| Execution | Rows returned from Neon |
| Response | Explanation tied to SQL + data |

### Lightweight “query lineage” to log (production habit)

For each `/ask` request, store (DB table or JSON logs):

```json
{
  "question": "Who are our top customers by revenue?",
  "retrieved_tables": ["customers", "orders", "payments"],
  "business_definitions_used": ["Revenue = SUM(payment_amount)"],
  "generated_sql": "SELECT ...",
  "execution_status": "success",
  "row_count": 10,
  "model_version": "gpt-4o",
  "schema_index_version": "v3",
  "timestamp": "2026-06-02T12:00:00Z"
}
```

That lets you audit **why** the model joined certain tables and whether the right definition of “revenue” was retrieved — similar to data lineage for one analytical answer.

### Business definitions = semantic lineage

When you write:

> Revenue = `SUM(payment_amount)` from `payments`

you are documenting **semantic lineage**: the meaning of a metric in terms of base columns. That belongs in your RAG knowledge base (YAML/JSON) alongside technical schema from SQLAlchemy `inspect()`.

---

## 9. Lineage and evaluation (your four metrics)

From `my_application.md`:

| Evaluation | Lineage helps when… |
|------------|---------------------|
| **Retrieval** | You log which tables were retrieved vs expected |
| **SQL validity** | You log execution errors and retries |
| **SQL correctness** | You compare generated SQL to expected pattern + definitions used |
| **Answer correctness** | You trace result back through SQL to source tables |

Failed retrieval is a **lineage break** at the context layer — the LLM never saw the right tables.

---

## 10. Celery / async jobs (future)

When you add background tasks (schema indexing, long `/ask` jobs), lineage should include:

- `task_id` / `celery_task_id`
- Worker name, queue, retry count
- Input parameters (e.g. `schema_version`, `table_name`)

Same pattern as at work: **orchestration metadata** sits next to **data metadata**.

---

## 11. Common mistakes

| Mistake | Better practice |
|---------|------------------|
| Only documenting final dashboards | Lineage at transformation layer (dbt, ETL) |
| Table-level only | Add column-level for critical metrics (revenue, churn) |
| Lineage separate from catalog | Link lineage to owners, SLAs, and definitions |
| No logging in AI apps | Log retrieval + SQL + result per question |
| Stale lineage | Re-index schema / refresh when Neon or dbt changes |

---

## 12. Further reading

- [OpenLineage](https://openlineage.io/)
- [dbt docs — lineage](https://docs.getdbt.com/docs/collaborate/govern/model-access)
- Your app spec: `T2S/my_application.md`
- SQLAlchemy schema introspection: `T2S/learning/sqlalchemy_study_guide.md` (Phase 1 — technical side of lineage)

---

## 13. Quick recap

- **Lineage** = source → transforms → consumption, with metadata.
- **Upstream** = where data came from; **downstream** = what depends on it.
- **Text-to-SQL** benefits from **per-query lineage**: question → retrieval → SQL → results.
- **Business definitions** are the semantic layer that explains *what* a column or metric means in the chain.
