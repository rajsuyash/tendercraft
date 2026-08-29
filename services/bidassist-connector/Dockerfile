# BidAssist connector — production container.
#
# Mirrors its GeM and TED siblings: same base, same uv-locked resolution, same unprivileged
# user. Two things are specific to this one.
#
#   ONE worker, same reason as the others: the per-host rate cap is a process-local lock, so a
#   second worker silently doubles the rate and the cap becomes a lie. Paying for an API buys
#   access, not the right to hammer it.
#
#   This is the only container in the system that holds a source credential. BIDASSIST_API_KEY
#   is supplied at RUNTIME and never as a build arg — a build arg is baked into an image layer
#   and survives every `docker history` afterwards. Nothing here writes it to a log: the key is
#   read once in app/fetch.py and the /health endpoint reports only whether it is present.

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
