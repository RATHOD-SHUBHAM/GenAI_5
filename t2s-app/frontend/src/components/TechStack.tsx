const STACK = [
  { name: "Next.js", role: "Frontend", color: "#a78bfa" },
  { name: "FastAPI", role: "API", color: "#009688" },
  { name: "OpenAI", role: "LLM", color: "#10a37f" },
  { name: "Pinecone", role: "Vectors", color: "#3b82f6" },
  { name: "Neon", role: "Postgres", color: "#00e599" },
  { name: "Redis", role: "Cache", color: "#dc382d" },
  { name: "SQLAlchemy", role: "ORM", color: "#f97316" },
  { name: "Docker", role: "Deploy", color: "#2496ed" },
];

export default function TechStack() {
  return (
    <div className="stack-strip" aria-label="Tech stack">
      {STACK.map((item) => (
        <div
          key={item.name}
          className="stack-chip"
          style={{ ["--chip-color" as string]: item.color }}
        >
          <span className="stack-dot" />
          <span className="stack-name">{item.name}</span>
          <span className="stack-role">{item.role}</span>
        </div>
      ))}
    </div>
  );
}
