"""
main.py — FastAPI entry point.

uvicorn loads this file:
    uvicorn app.main:app --reload

`app` at the bottom is the ASGI application object uvicorn serves.
Everything else (routes, pipeline, cache) plugs into it here.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from sqlalchemy import create_engine

from app.api.routes import ask, health
from app.config import CORS_ORIGINS, DATABASE_URL, validate_config
from app.core.vector_db import VectorDB
from app.services.pipeline import ensure_index_populated


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs once when the server STARTS, then again when it STOPS.

    Why async?
        FastAPI is an async framework. Lifespan hooks are async so they
        don't block the event loop during startup/shutdown.
        Our DB/LLM calls inside routes are still sync — that's fine for now.

    Why yield?
        Code BEFORE yield  = startup  (create connections, warm Pinecone)
        Code AFTER yield   = shutdown (close connections cleanly)

        `yield` pauses here while the server handles requests.
        When you Ctrl+C uvicorn, execution resumes after yield and runs
        engine.dispose().

    Why app.state?
        A shared bag on the FastAPI instance. We store engine/client/vectordb
        once at startup so every request reuses the same pool — not a new
        connection per request.
    """
    validate_config()

    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    client = OpenAI()
    vectordb = VectorDB()
    ensure_index_populated(vectordb, engine)

    app.state.engine = engine
    app.state.client = client
    app.state.vectordb = vectordb

    yield  # server runs here — handles HTTP requests until shutdown

    engine.dispose()  # release all pooled DB connections


def create_app() -> FastAPI:
    """
    Factory that builds and configures the FastAPI instance.
    Separated from `app = create_app()` so tests can call create_app() too.
    """
    app = FastAPI(title="Text-to-SQL API", lifespan=lifespan)

    # CORS: browsers block frontend (localhost:3000) from calling API
    # (localhost:8000) unless the API explicitly allows that origin.
    # curl/Postman are not browsers — they ignore CORS.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount route modules under /api → GET /api/health, POST /api/ask
    app.include_router(health.router, prefix="/api")
    app.include_router(ask.router, prefix="/api")

    return app


# This is what uvicorn imports:  uvicorn app.main:app
app = create_app()
