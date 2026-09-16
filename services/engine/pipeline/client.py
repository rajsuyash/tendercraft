"""Gemini client — the single model-call module (docs/conventions.md).

One retry, explicit timeout, token/cost logged per call. Structured output only: the
caller passes an allowlisted schema and gets validated JSON back, or a ModelError that
the caller turns into a deterministic fallback. Never raises raw provider errors upward.
"""

from __future__ import annotations

import json
import logging
import os
from collections import deque

import httpx

logger = logging.getLogger("tendercraft.pipeline")

_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
# v1beta (JSON mode / responseSchema lives here) + key in the x-goog-api-key header
# (the AQ.-format keys 403 on the ?key= query param).
_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_TIMEOUT = float(os.environ.get("GEMINI_TIMEOUT", "45"))
_RETRY_CAP = 1  # PRD: unbounded retries = cost blowup

#: Gemini 2.5 Flash thinks by default, and thinking tokens bill as OUTPUT. Unset leaves the
#: model's own dynamic budget, which is today's behaviour; `0` disables thinking; a positive
#: integer caps it. An env var rather than a constant so the two configurations can be
#: measured against the same eval sets before either is made the default — the quality cost of
#: turning it off is a per-stage question, and extraction is not drafting.
_THINKING_BUDGET = os.environ.get("GEMINI_THINKING_BUDGET")


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

    config: dict = {
        "temperature": temperature,
        "responseMimeType": "application/json",
        "responseSchema": schema,
    }
    if _THINKING_BUDGET is not None:
        config["thinkingConfig"] = {"thinkingBudget": int(_THINKING_BUDGET)}
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": config}
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
    """Token accounting for one call.

    `thoughtsTokenCount` is reported separately by the API and is NOT included in
    `candidatesTokenCount`, but it bills as output — so a line without it understates the
    billed output by however much the model thought. Logged explicitly for that reason.
    """
    usage = payload.get("usageMetadata", {})
    thoughts = usage.get("thoughtsTokenCount") or 0
    answer = usage.get("candidatesTokenCount") or 0
    logger.info(
        "gemini usage model=%s prompt_tokens=%s answer_tokens=%s thought_tokens=%s "
        "billed_output=%s total=%s",
        _MODEL,
        usage.get("promptTokenCount"),
        answer,
        thoughts,
        answer + thoughts,
        usage.get("totalTokenCount"),
    )
    _USAGE.append({"prompt": usage.get("promptTokenCount") or 0,
                   "answer": answer, "thoughts": thoughts})


#: In-process token tape. The `_log_cost` INFO line has never reached Cloud Logging (no
#: logging config anywhere in the engine, so the root logger sits at WARNING), which is why
#: per-stage attribution has only ever been inference. This makes a measurement possible
#: without depending on the log pipeline being fixed first.
#:
#: BOUNDED, because this module lives in a long-running service: an unbounded list appended
#: to on every model call is a slow leak that would only show up after the container had been
#: warm for days. A deque discards the oldest instead, which is the right trade for a tape
#: nobody reads except a measurement run.
_USAGE: deque[dict] = deque(maxlen=500)


def usage_tape() -> list[dict]:
    return list(_USAGE)


def reset_usage() -> None:
    _USAGE.clear()
