# Test Questions for Text-to-SQL

Sample questions for the **departments** + **employees** schema (10 departments, 200 employees).

Use these in the UI at http://localhost:3000 or via curl:

```bash
curl -s -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "YOUR QUESTION HERE"}' | jq
```

---

## Schema reminder

**departments:** `id`, `name`, `location`  
**employees:** `id`, `name`, `age`, `department_id`, `salary`, `hire_date`  
**FK:** `employees.department_id` → `departments.id`

---

## Easy — single table, simple aggregates

Good for first tests and cache checks (ask the same question twice).

1. How many employees are in the database?
2. List all department names and their locations.
3. What is the average salary across all employees?
4. Who is the highest paid employee?
5. What is the lowest salary in the company?
6. How many departments are there?
7. List the names of all employees in the Engineering department.
8. Show all employees older than 50.
9. What is the total salary paid to all employees?
10. List employees hired in 2022.

---

## Medium — joins, GROUP BY, filters

11. What is the average salary of employees in each department?
12. How many employees work in each department?
13. Which department has the most employees?
14. Show employee name, department name, and salary for everyone in Sales.
15. List departments located in San Francisco or Seattle.
16. What is the average age of employees in the HR department?
17. Show the top 5 highest paid employees with their department names.
18. How many employees were hired each year?
19. Which departments have an average salary above 100000?
20. List all employees in Finance sorted by salary descending.

---

## Hard — HAVING, subqueries, ratios

Good for testing the **self-improvement retry loop** (up to 3 attempts).

21. For each department, show the ratio of the highest paid employee's salary to the lowest paid employee's salary, but only for departments where this ratio is greater than 3.
22. Which department has the highest average salary?
23. Find departments with more than 25 employees.
24. Who is the youngest employee in each department?
25. Show departments where the max salary is more than double the min salary.
26. What is the total payroll cost per department location?
27. List employees who earn more than the average salary of their department.
28. Which department has the biggest gap between its highest and lowest salary?
29. Show the average salary by department, only for departments with at least 15 employees.
30. Find employees hired before 2020 who earn above 120000, with their department name.

---

## Cache testing (Redis)

Pick any easy question and **ask it twice**:

```text
How many employees are in each department?
```

| Request | Expected |
|---------|----------|
| First | `"cached": false` — full pipeline runs |
| Second | `"cached": true` — instant response from Redis |

Try with different spacing/casing — should still hit cache:

```text
  how many employees are in each department?
```

---

## RAG retrieval testing

Check that Pinecone returns the right tables (shown in the UI badges).

| Question | Expected tables |
|----------|-----------------|
| Average salary by department | `employees`, `departments` |
| Where is the HR office? | `departments` |
| Who earns the most? | `employees` |
| Employees in Chicago departments | `employees`, `departments` |

---

## Edge cases

31. List all employees named John.
32. What is the median salary? (may be tricky — good retry test)
33. Show me revenue by region. (no revenue table — should fail gracefully)
34. Count employees grouped by department and location.
35. Which locations have more than one department?

---

## Suggested test order

```text
1.  How many employees are in each department?     ← easy + cache test
2.  What is the average salary by department?      ← join + group by
3.  Who is the highest paid employee?              ← simple aggregate
4.  Question #21 (ratio query)                     ← hard + retry loop
5.  Repeat question #1                             ← confirm cached: true
```

---

## Quick copy-paste list

```
How many employees are in each department?
What is the average salary of employees in each department?
Who is the highest paid employee?
List all department names and their locations.
Which department has the most employees?
Show the top 5 highest paid employees with their department names.
For each department, show the ratio of the highest paid employee's salary to the lowest paid employee's salary, but only for departments where this ratio is greater than 3.
List employees who earn more than the average salary of their department.
Show me revenue by region.
```
