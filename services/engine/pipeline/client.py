"""Gemini client — the single model-call module (docs/conventions.md).

One retry, explicit timeout, token/cost logged per call. Structured output only: the
caller passes an allowlisted schema and gets validated JSON back, or a ModelError that
the caller turns into a deterministic fallback. Never raises raw provider errors upward.
"""

from __future__ import annotations

import json
import logging
import os

import httpx

logger = logging.getLogger("tendercraft.pipeline")

_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
# v1beta (JSON mode / responseSchema lives here) + key in the x-goog-api-key header
# (the AQ.-format keys 403 on the ?key= query param).
_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_TIMEOUT = float(os.environ.get("GEMINI_TIMEOUT", "45"))
_RETRY_CAP = 1  # PRD: unbounded retries = cost blowup


class ModelError(Exception):
    """Raised after the retry cap is exhausted or output fails schema validation."""


def generate_json(prompt: str, schema: dict, *, temperature: float = 0.0) -> dict:
    """Call Gemini with an enforced response schema; return parsed JSON.

    Retries once on transient/parse failure, then raises ModelError so the caller can
    fall back deterministically (queue for human) — never crash, never invent.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ModelError("GEMINI_API_KEY not configured")

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
            "responseSchema": schema,
        },
    }
    url = f"{_BASE}/{_MODEL}:generateContent"

    last_err: Exception | None = None
    for attempt in range(_RETRY_CAP + 1):
        try:
            resp = httpx.post(
                url,
                headers={"x-goog-api-key": api_key},
                json=body,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json()
            _log_cost(payload)
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as exc:
            last_err = exc
            logger.warning("gemini call failed (attempt %d): %s", attempt + 1, exc)

    raise ModelError(f"model call failed after {_RETRY_CAP + 1} attempts: {last_err}")


def _log_cost(payload: dict) -> None:
    usage = payload.get("usageMetadata", {})
    logger.info(
        "gemini usage model=%s prompt_tokens=%s candidates_tokens=%s total=%s",
        _MODEL,
        usage.get("promptTokenCount"),
        usage.get("candidatesTokenCount"),
        usage.get("totalTokenCount"),
    )
