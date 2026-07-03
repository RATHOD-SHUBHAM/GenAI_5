"use client";

import { useState } from "react";

import { isAskSuccess, type AskResponse } from "@/lib/api";

type Tab = "results" | "sql" | "thinking";

function formatCell(cell: unknown): string {
  if (cell === null || cell === undefined) return "";
  if (typeof cell === "number") {
    return Number.isInteger(cell) ? String(cell) : cell.toFixed(2);
  }
  return String(cell);
}

export default function ResultsPanel({ result }: { result: AskResponse }) {
  const [tab, setTab] = useState<Tab>("results");

  if (!isAskSuccess(result)) {
    return (
      <div className="panel-card results-card">
        <div className="meta">{metaBadges(result)}</div>
        <h3>Could not answer</h3>
        <p className="error-text">{result.error}</p>
        {result.last_error && <pre className="code-block compact">{result.last_error}</pre>}
        {result.last_sql && (
          <pre className="code-block compact sql-block">{result.last_sql}</pre>
        )}
      </div>
    );
  }

  return (
    <div className="panel-card results-card">
      <div className="meta">{metaBadges(result)}</div>

      <div className="tab-bar">
        <button
          type="button"
          className={`tab ${tab === "results" ? "active" : ""}`}
          onClick={() => setTab("results")}
        >
          Results ({result.rows.length})
        </button>
        <button
          type="button"
          className={`tab ${tab === "sql" ? "active" : ""}`}
          onClick={() => setTab("sql")}
        >
          SQL
        </button>
        <button
          type="button"
          className={`tab ${tab === "thinking" ? "active" : ""}`}
          onClick={() => setTab("thinking")}
        >
          Reasoning
        </button>
      </div>

      <div className="tab-panel">
        {tab === "results" && (
          <div className="tab-results-stack">
            {result.rows.length === 0 ? (
              <p className="empty-results">No rows returned.</p>
            ) : (
              <div className="table-wrap scrollable">
                <table>
                  <thead>
                    <tr>
                      {result.columns.map((col) => (
                        <th key={col}>{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.rows.map((row, i) => (
                      <tr key={i}>
                        {row.map((cell, j) => (
                          <td key={j}>{formatCell(cell)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {result.answer && (
              <div className="nl-answer">
                <span className="nl-answer-icon" aria-hidden="true">🤖</span>
                <p>{result.answer}</p>
              </div>
            )}
          </div>
        )}

        {tab === "sql" && (
          <pre className="code-block compact sql-block">{result.sql}</pre>
        )}

        {tab === "thinking" && (
          <pre className="code-block compact">{result.thinking || "No reasoning captured."}</pre>
        )}
      </div>
    </div>
  );
}

function metaBadges(result: AskResponse) {
  return (
    <>
      <span className="badge">Tables: {result.retrieved_tables.join(", ") || "—"}</span>
      <span className="badge">Attempts: {result.attempts}</span>
      {isAskSuccess(result) && <span className="badge">Rows: {result.rows.length}</span>}
      {result.cached && <span className="badge cached">Cached</span>}
      {!result.success && <span className="badge error">Failed</span>}
      {result.success && !result.cached && <span className="badge success">Fresh</span>}
    </>
  );
}
