"""
config.py — read settings from GenAI_5/.env once at import time.

Imported by many modules; load_dotenv runs the first time this file loads.
Docker injects the same vars via env_file in compose — os.getenv works either way.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# backend/app/config.py → parents[3] = GenAI_5/
ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
# .strip() avoids accidental leading spaces in .env (e.g. "  t2s-schema")
PINECONE_INDEX_NAME = (os.getenv("PINECONE_INDEX_NAME") or "").strip()
REDIS_URL = (os.getenv("REDIS_URL") or "").strip()
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "600"))

# Comma-separated list in .env: CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]


def validate_config() -> None:
    """Fail fast at startup if a required secret is missing — not mid-request."""
    missing = []
    if not DATABASE_URL:
        missing.append("DATABASE_URL")
    if not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    if not PINECONE_API_KEY:
        missing.append("PINECONE_API_KEY")
    if not PINECONE_INDEX_NAME:
        missing.append("PINECONE_INDEX_NAME")
    if not REDIS_URL:
        missing.append("REDIS_URL")
    if missing:
        raise ValueError(f"Missing required env vars: {', '.join(missing)}")
