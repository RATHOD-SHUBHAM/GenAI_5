"use client";

import { FormEvent, useState } from "react";

import Footer from "@/components/Footer";
import PipelineViz from "@/components/PipelineViz";
import ResultsPanel from "@/components/ResultsPanel";
import TechStack from "@/components/TechStack";
import { askQuestion, type AskResponse } from "@/lib/api";

export default function HomePage() {
  const [question, setQuestion] = useState(
    "What is the average salary of employees in each department?"
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AskResponse | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await askQuestion(question.trim());
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page-shell">
      <div className="bg-orb bg-orb-1" />
      <div className="bg-orb bg-orb-2" />
      <div className="bg-grid" />

      <header className="site-header">
        <div className="header-copy">
          <span className="hero-badge">RAG · Self-improve · Cache</span>
          <h1>
            Ask your database
            <span className="hero-accent"> in plain English</span>
          </h1>
          <p>
            Vector search finds tables → GPT writes SQL → Neon runs it → Redis
            caches repeat questions. Up to 3 auto-retries on failure.
          </p>
        </div>
        <TechStack />
      </header>

      <main className="workspace">
        <aside className="ask-panel">
          <form className="panel-card ask-form" onSubmit={handleSubmit}>
            <div className="ask-form-top">
              <h2>Your question</h2>
              <p>Employees · departments · salaries · hires</p>
            </div>
            <textarea
              id="question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. Which department has the highest average salary?"
              rows={5}
              disabled={loading}
            />
            <button type="submit" className="ask-btn" disabled={loading || !question.trim()}>
              {loading ? (
                <>
                  <span className="btn-spinner" />
                  Running…
                </>
              ) : (
                <>
                  <span className="btn-icon">▶</span>
                  Ask the database
                </>
              )}
            </button>
          </form>
        </aside>

        <section className="results-panel">
          {loading && (
            <div className="panel-card results-card">
              <PipelineViz mode="loading" />
            </div>
          )}

          {error && (
            <div className="panel-card results-card error-card">
              <h3>Something went wrong</h3>
              <p className="error-text">{error}</p>
            </div>
          )}

          {!loading && !result && !error && (
            <div className="panel-card results-card">
              <PipelineViz mode="idle" />
            </div>
          )}

          {result && !loading && (
            <div className="results-card-wrap">
              <ResultsPanel result={result} />
            </div>
          )}
        </section>
      </main>

      <Footer />
    </div>
  );
}
