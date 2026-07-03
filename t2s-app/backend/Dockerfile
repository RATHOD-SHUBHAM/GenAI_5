# Uses uv for fast, reproducible installs (see pyproject.toml + uv.lock)
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Install deps first — Docker caches this layer when only app code changes
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app

ENV PYTHONPATH=/app

EXPOSE 8000

# --no-sync: use deps from image build, don't re-resolve on container start
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
