"""
cache.py — Redis cache-aside for /api/ask.

Pattern:
    1. GET key before running pipeline
    2. On miss: run pipeline, SETEX result with TTL
    3. On hit: return stored JSON immediately

Uses Redis Cloud (REDIS_URL from .env) — no local Redis container.
"""

import hashlib
import json
from typing import Any

import redis

from app.config import CACHE_TTL_SECONDS, REDIS_URL

CACHE_PREFIX = "t2s:ask:"


def _normalize_question(question: str) -> str:
    """Same question with different spacing/casing → same cache key."""
    return question.strip().lower()


def cache_key(question: str) -> str:
    # Hash keeps keys short and avoids special characters from user input
    normalized = _normalize_question(question)
    digest = hashlib.sha256(normalized.encode()).hexdigest()
    return f"{CACHE_PREFIX}{digest}"


def get_redis_client() -> redis.Redis:
    # decode_responses=True → get() returns str, not bytes (needed for json.loads)
    return redis.from_url(REDIS_URL, decode_responses=True)


def get_cached_answer(question: str) -> dict[str, Any] | None:
    client = get_redis_client()
    raw = client.get(cache_key(question))
    if not raw:
        return None
    return json.loads(raw)


def set_cached_answer(question: str, payload: dict[str, Any]) -> None:
    client = get_redis_client()
    # setex = SET with expiry (seconds). After TTL, Redis auto-deletes the key.
    # default=str handles date/decimal values from SQL rows that aren't JSON-native.
    client.setex(
        cache_key(question),
        CACHE_TTL_SECONDS,
        json.dumps(payload, default=str),
    )
