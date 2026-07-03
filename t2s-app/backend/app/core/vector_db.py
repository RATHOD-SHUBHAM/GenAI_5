"""Pinecone + OpenAI embeddings for schema RAG."""

import os

from openai import OpenAI
from pinecone import Pinecone


class VectorDB:
    def __init__(self):
        pinecone_api_key = os.getenv("PINECONE_API_KEY")
        index_name = (os.getenv("PINECONE_INDEX_NAME") or "").strip()

        if not pinecone_api_key or not index_name:
            raise ValueError("PINECONE_API_KEY and PINECONE_INDEX_NAME required in .env")

        self.pc = Pinecone(api_key=pinecone_api_key)
        self.index = self.pc.Index(index_name)
        self.openai = OpenAI()
        self.embed_model = "text-embedding-3-large"
        self.embed_dimensions = 1024

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        response = self.openai.embeddings.create(
            model=self.embed_model,
            input=texts,
            dimensions=self.embed_dimensions,
        )
        return [item.embedding for item in response.data]

    def embed_query(self, query: str) -> list[float]:
        return self.embed_texts([query])[0]

    def load_data(self, data: list[dict]) -> None:
        if not data:
            raise ValueError("No chunks to index")

        texts = [item["text"] for item in data]
        embeddings = self.embed_texts(texts)

        vectors = []
        for i, item in enumerate(data):
            table = item["metadata"]["table"]
            kind = item["metadata"].get("kind", "technical")
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

    def search(
        self,
        query: str,
        k: int = 5,
        similarity_threshold: float = 0.3,
    ) -> list[dict]:
        query_vector = self.embed_query(query)

        response = self.index.query(
            vector=query_vector,
            top_k=k,
            include_metadata=True,
        )

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

    def vector_count(self) -> int:
        stats = self.index.describe_index_stats()
        return stats.total_vector_count
