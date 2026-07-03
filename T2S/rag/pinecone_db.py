"""
Vector store for schema RAG using Pinecone + OpenAI embeddings.

Pipeline:
    build_schema_chunks()  →  VectorDB.load_data()  →  Pinecone index
    user question          →  VectorDB.search()     →  relevant table names

OpenAI: turns text into vectors (numbers).
Pinecone: stores vectors and finds similar ones on search.

Index settings (must match your Pinecone console):
    - Model: text-embedding-3-large
    - Dimensions: 1024  (pass dimensions=1024 to OpenAI — large defaults to 3072)
    - Metric: cosine
"""

import os

from openai import OpenAI
from pinecone import Pinecone


# =============================================================================
# VectorDB — embed, store, search schema chunks
# =============================================================================

class VectorDB:
    """
    OpenAI embed + Pinecone index
    """

    def __init__(self):
        pinecone_api_key = os.getenv("PINECONE_API_KEY")
        index_name = os.getenv("PINECONE_INDEX_NAME")

        if not pinecone_api_key or not index_name:
            raise ValueError("PINECONE_API_KEY and PINECONE_INDEX_NAME required in .env")

        # Pinecone client + handle to your index (e.g. t2s-schema)
        self.pc = Pinecone(api_key=pinecone_api_key)
        self.index = self.pc.Index(index_name)

        # OpenAI client for embeddings (uses OPENAI_API_KEY from env)
        self.openai = OpenAI()

        # Must match Pinecone index: dimension 1024 + text-embedding-3-large tag
        self.embed_model = "text-embedding-3-large"
        self.embed_dimensions = 1024

    # -------------------------------------------------------------------------
    # Embedding (replaces VoyageAI in the tutorial)
    # -------------------------------------------------------------------------

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of strings — one vector per string.

        Used by load_data() for all schema chunk texts.
        dimensions=1024 is required so vectors fit a 1024-dim Pinecone index.
        """
        response = self.openai.embeddings.create(
            model=self.embed_model,
            input=texts,
            dimensions=self.embed_dimensions,
        )
        return [item.embedding for item in response.data]

    def embed_query(self, query: str) -> list[float]:
        """
        Embed a single user question.

        Used by search(). Must use the same model + dimensions as indexing.
        """
        return self.embed_texts([query])[0]

    # -------------------------------------------------------------------------
    # Indexing (replaces load_data + save_db / pickle)
    # -------------------------------------------------------------------------

    def load_data(self, data: list[dict]) -> None:
        """
        Embed schema chunks and upsert into Pinecone.

        Args:
            data: Output of build_schema_chunks(engine) from schema_chunks.py.
                  Each item: {"text": "...", "metadata": {"table": "...", "kind": "technical"}}

        We store only table + kind in Pinecone metadata (not full schema text).
        Full text is rebuilt later via build_schema_for_tables(engine, table_names).
        """
        if not data:
            raise ValueError("No chunks to index")

        texts = [item["text"] for item in data]
        embeddings = self.embed_texts(texts)

        vectors = []
        for i, item in enumerate(data):
            table = item["metadata"]["table"]
            kind = item["metadata"].get("kind", "technical")

            # Unique ID per chunk — upsert overwrites if you re-index the same table
            vector_id = f"{table}-{kind}"

            vectors.append({
                "id": vector_id,
                "values": embeddings[i],
                "metadata": {
                    "table": table,
                    "kind": kind,
                },
            })

        self.index.upsert(vectors=vectors)

    # -------------------------------------------------------------------------
    # Retrieval (replaces numpy dot-product similarity in the tutorial)
    # -------------------------------------------------------------------------

    def search(
        self,
        query: str,
        k: int = 5,
        similarity_threshold: float = 0.3,
    ) -> list[dict]:
        """
        Find schema chunks most similar to the user question.

        Steps:
            1. Embed the question (same model as load_data).
            2. Pinecone cosine similarity vs stored vectors.
            3. Filter by similarity_threshold (tutorial default: 0.3).
            4. Return metadata (table name) for prompt building.

        Returns:
            List of {"metadata": {"table": "...", "kind": "..."}, "similarity": float}.
        """
        query_vector = self.embed_query(query)

        response = self.index.query(
            vector=query_vector,
            top_k=k,
            include_metadata=True,
        )

        # Pinecone SDK returns an object with .matches (not always a dict)
        raw_matches = response.matches if hasattr(response, "matches") else response["matches"]

        matches = []
        for match in raw_matches:
            score = match.score if hasattr(match, "score") else match["score"]
            metadata = match.metadata if hasattr(match, "metadata") else match["metadata"]

            if score >= similarity_threshold:
                matches.append({
                    "metadata": metadata,
                    "similarity": score,
                })

        return matches

    # -------------------------------------------------------------------------
    # Index stats (replaces "if not vectordb.embeddings" on pickle file)
    # -------------------------------------------------------------------------

    def vector_count(self) -> int:
        """How many vectors are in the index (0 = run load_data first)."""
        stats = self.index.describe_index_stats()
        return stats.total_vector_count


# =============================================================================
# Smoke test — index chunks + search (needs network + API keys)
# Usage (from repo root):
#   python T2S/rag/pinecone_db.py
# =============================================================================

def _run_smoke_test() -> None:
    """Index schema if empty, then run a sample similarity search."""
    import sys
    from pathlib import Path

    from dotenv import load_dotenv
    from sqlalchemy import create_engine

    # Allow importing schema_chunks from the same rag/ folder
    rag_dir = Path(__file__).resolve().parent
    if str(rag_dir) not in sys.path:
        sys.path.insert(0, str(rag_dir))

    from schema_chunks import build_schema_chunks

    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL missing — check GenAI_5/.env")

    engine = create_engine(database_url, pool_pre_ping=True)

    vectordb = VectorDB()

    if vectordb.vector_count() == 0:
        print("Index empty — loading schema chunks...")
        chunks = build_schema_chunks(engine)
        vectordb.load_data(chunks)
        print(f"Upserted {len(chunks)} vectors")
    else:
        print(f"Index already has {vectordb.vector_count()} vectors — skipping upsert")

    test_query = "What is the average salary of employees in each department?"
    results = vectordb.search(test_query, k=5)

    print("\nSearch results:")
    for r in results:
        print(f"  similarity={r['similarity']:.3f}  metadata={r['metadata']}")

    # Sanity check: embedding length must match Pinecone index dimension
    vec_len = len(vectordb.embed_query("test"))
    print(f"\nEmbedding dimension check: {vec_len} (expect 1024)")


if __name__ == "__main__":
    _run_smoke_test()
