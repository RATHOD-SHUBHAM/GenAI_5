"""
Pydantic models — define the shape of JSON going in and out of the API.

FastAPI uses these to:
  - Parse + validate incoming JSON (AskRequest)
  - Validate outgoing JSON matches the contract (AskSuccessResponse)
  - Auto-generate OpenAPI docs at /docs
"""

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    """POST /api/ask body — what the client sends."""
    question: str = Field(..., min_length=1, max_length=2000)


class AskSuccessResponse(BaseModel):
    """Returned when SQL ran successfully."""
    question: str
    cached: bool
    success: bool = True
    retrieved_tables: list[str]
    thinking: str
    sql: str
    columns: list[str]
    rows: list[list]
    answer: str
    attempts: int


class AskFailureResponse(BaseModel):
    """Returned when all retry attempts exhausted."""
    question: str
    cached: bool
    success: bool = False
    retrieved_tables: list[str]
    thinking: str
    error: str
    last_sql: str | None
    last_error: str | None
    attempts: int


class HealthResponse(BaseModel):
    """GET /api/health response."""
    status: str
    database: str
    redis: str
