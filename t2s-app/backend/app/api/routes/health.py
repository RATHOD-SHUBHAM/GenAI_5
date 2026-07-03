"""
api/routes/health.py — GET /api/health

Cheap liveness check: ping Neon + Redis without calling the LLM.
Used by you, Docker, or deploy platforms to see if dependencies are reachable.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.api.schemas import HealthResponse
from app.dependencies import get_engine
from app.services.cache import get_redis_client

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(engine=Depends(get_engine)):
    db_status = "ok"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    redis_status = "ok"
    try:
        get_redis_client().ping()
    except Exception:
        redis_status = "error"

    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"

    return HealthResponse(
        status=overall,
        database=db_status,
        redis=redis_status,
    )
