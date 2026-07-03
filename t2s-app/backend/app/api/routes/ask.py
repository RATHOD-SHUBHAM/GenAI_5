"""
api/routes/ask.py — POST /api/ask

Thin HTTP layer: cache check → pipeline → cache store → JSON response.
No SQL or prompts here — that lives in services/pipeline.py.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import AskFailureResponse, AskRequest, AskSuccessResponse
from app.dependencies import get_client, get_engine, get_vectordb
from app.services.cache import get_cached_answer, set_cached_answer
from app.services.nl_answer import generate_nl_answer
from app.services.pipeline import ask_with_self_improvement

router = APIRouter(tags=["ask"])


def _is_valid_success_payload(payload: dict) -> bool:
    """Skip stale/broken Redis cache entries missing row data."""
    return (
        payload.get("success") is True
        and isinstance(payload.get("columns"), list)
        and isinstance(payload.get("rows"), list)
    )


def _ensure_answer(payload: dict, client) -> dict:
    """Backfill NL answer for cache entries stored before Step 9."""
    if payload.get("answer"):
        return payload
    payload["answer"] = generate_nl_answer(
        client=client,
        question=payload["question"],
        columns=payload["columns"],
        rows=payload["rows"],
    )
    return payload


@router.post(
    "/ask",
    response_model=AskSuccessResponse | AskFailureResponse,
)
def ask_question(
    body: AskRequest,
    # Depends(...) = FastAPI calls these functions before ask_question runs
    engine=Depends(get_engine),
    client=Depends(get_client),
    vectordb=Depends(get_vectordb),
):
    question = body.question.strip()

    # 1. Redis cache-aside: identical question → skip LLM + Pinecone + Neon
    cached = get_cached_answer(question)
    if cached and _is_valid_success_payload(cached):
        had_answer = bool(cached.get("answer"))
        cached = _ensure_answer(cached, client)
        cached["cached"] = True
        # Upgrade old cache entries to include answer for next time
        if not had_answer:
            to_store = {k: v for k, v in cached.items() if k != "cached"}
            set_cached_answer(question, to_store)
        return cached

    # 2. Run the basics_5 self-improvement loop (RAG → LLM → SQL → retry)
    try:
        result = ask_with_self_improvement(
            vectordb=vectordb,
            engine=engine,
            client=client,
            user_query=question,
            max_attempts=3,
        )
    except ValueError as e:
        # e.g. Pinecone returned no tables — client error, not server crash
        raise HTTPException(status_code=400, detail=str(e)) from e

    result["cached"] = False

    # 3. Only cache successful answers (not failed retries)
    if result["success"]:
        set_cached_answer(question, result)

    # FastAPI serializes this dict to JSON using response_model for validation
    return result
