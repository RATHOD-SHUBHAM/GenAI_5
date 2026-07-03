"use client";

import { useEffect, useState } from "react";

const NODES = [
  { id: "you", label: "Your question", icon: "💬", detail: "Natural language input" },
  { id: "cache", label: "Redis", icon: "⚡", detail: "Cache hit → instant" },
  { id: "rag", label: "Pinecone", icon: "🔍", detail: "Find relevant tables" },
  { id: "llm", label: "GPT", icon: "🧠", detail: "Write PostgreSQL" },
  { id: "db", label: "Neon", icon: "🐘", detail: "Run + retry SQL" },
  { id: "out", label: "Results", icon: "📊", detail: "Table · SQL · tabs" },
];

type Mode = "idle" | "loading";

export default function PipelineViz({ mode }: { mode: Mode }) {
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    if (mode !== "loading") return;
    const interval = setInterval(() => {
      setActiveIndex((i) => (i + 1) % NODES.length);
    }, 1400);
    return () => clearInterval(interval);
  }, [mode]);

  return (
    <div className={`pipeline-viz ${mode}`}>
      <div className="pipeline-viz-header">
        {mode === "loading" && <span className="btn-spinner pipeline-viz-spinner" />}
        <div>
          <h3>
            {mode === "loading"
              ? "Pipeline running…"
              : "What happens when you click Ask"}
          </h3>
          <p>
            {mode === "loading"
              ? "Your question is moving through the stack right now"
              : "Six steps from English to database rows"}
          </p>
        </div>
      </div>

      <div className="pipeline-flow-grid">
        {NODES.map((node, i) => {
          const isActive = mode === "loading" && i === activeIndex;
          const isDone = mode === "loading" && i < activeIndex;

          return (
            <div
              key={node.id}
              className={`pipeline-node ${isActive ? "active" : ""} ${isDone ? "done" : ""}`}
              style={{ animationDelay: `${i * 0.15}s` }}
            >
              <span className="node-step">{i + 1}</span>
              <span className="node-icon">{node.icon}</span>
              <span className="node-label">{node.label}</span>
              <span className="node-detail">{node.detail}</span>
              {isActive && <span className="node-pulse" />}
            </div>
          );
        })}
      </div>

      {mode === "idle" && (
        <div className="pipeline-hint">
          <span className="hint-dot" />
          Press <strong>Ask the database</strong> on the left → results appear here
        </div>
      )}
    </div>
  );
}
