FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY evaluate ./evaluate
COPY prompts ./prompts
RUN uv sync --frozen --no-dev
RUN useradd --create-home --uid 10001 svc && chown -R svc:svc /app
USER svc
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn evaluate.main:app --host 0.0.0.0 --port ${PORT}"]
