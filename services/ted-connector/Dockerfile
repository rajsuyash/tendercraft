# TED connector — production container.
#
# Mirrors services/engine/Dockerfile deliberately: same base, same uv-locked resolution, same
# unprivileged user. The differences are the interesting part.
#
#   ONE worker, same reason as the GeM connector: the per-host rate cap is a process-local lock,
#   so a second worker silently doubles the rate against a public API and the cap becomes a lie.
#   BOAMP is an open-data API under Licence Ouverte rather than a scraped portal, but politeness
#   toward a free public service is not conditional on the licence.

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
