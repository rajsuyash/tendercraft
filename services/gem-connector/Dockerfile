# GeM connector — production container.
#
# Mirrors services/engine/Dockerfile deliberately: same base, same uv-locked resolution, same
# unprivileged user. The differences are the interesting part.
#
#   ONE worker, not two. Every outbound request passes a per-host rate cap held in a process
#   -local lock (app/fetch.py). Two workers would mean two independent locks and therefore two
#   requests per second against a government portal instead of one — the cap would silently
#   become a lie, which under G-10 is worse than having no cap because we would believe it.
#   Scale this service by making sweeps less frequent, never by adding workers.

FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 connector && chown -R connector:connector /app
USER connector

ENV PORT=8080
EXPOSE 8080

# A sweep sleeps between portal requests, so keep-alive and request timeouts have to outlast a
# full run rather than a typical HTTP call.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --timeout-keep-alive 120
