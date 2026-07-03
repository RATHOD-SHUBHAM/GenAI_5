"""
dependencies.py — FastAPI dependency injection helpers.

Depends(get_engine) in a route tells FastAPI:
    "Before running this endpoint, call get_engine(request) and pass
     the return value as the `engine` argument."

This keeps routes thin — they declare what they need, not how to build it.
The actual objects live on app.state (created once in main.py lifespan).
"""

from fastapi import Request


def get_engine(request: Request):
    """SQLAlchemy engine — pooled connection to Neon."""
    return request.app.state.engine


def get_client(request: Request):
    """OpenAI client — shared across requests."""
    return request.app.state.client


def get_vectordb(request: Request):
    """Pinecone wrapper — shared across requests."""
    return request.app.state.vectordb
