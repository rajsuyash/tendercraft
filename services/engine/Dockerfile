# TenderCraft engine — production container.
#
# The repo previously had no production run command at all: README and CLAUDE.md both
# documented `uv run fastapi dev`, which is a single-worker reload server bound for local
# use. This is that missing artifact.

FROM python:3.12-slim AS base

# uv gives us the same locked resolution the test suite runs against.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies as their own layer so application edits don't re-resolve the world.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY pipeline ./pipeline
COPY prompts ./prompts
RUN uv sync --frozen --no-dev

# Run unprivileged. Nothing here writes to disk at runtime.
RUN useradd --create-home --uid 10001 engine && chown -R engine:engine /app
USER engine

# Cloud Run injects PORT and terminates TLS at the edge.
ENV PORT=8080
EXPOSE 8080

# Workers, not --reload. Two is right for a container this size: the handlers are I/O-bound
# (PostgREST + Gemini) and per-page extraction already fans out on its own thread pool, so
# more workers would multiply memory without adding throughput.
# ponytail: fixed at 2. Revisit when a real concurrency measurement says otherwise.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 2 --timeout-keep-alive 65
