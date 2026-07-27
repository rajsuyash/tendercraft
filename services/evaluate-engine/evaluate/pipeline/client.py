"""The single model-call module. Separate credential from the bidder product (F13-AC3).

Retry cap 1, explicit timeout, cost logged. Structured output only — the caller passes an
allowlisted schema and gets validated JSON or a ModelError it turns into a deterministic
fallback. For the score proposer that fallback is NO PROPOSAL, never a guessed mark.
"""

from __future__ import annotations

import base64
import json
import logging
import os

import httpx

log = logging.getLogger("tendercraft.evaluate.pipeline")

_MODEL = os.environ.get("EVAL_MODEL", "gemini-2.5-flash")
_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_TIMEOUT = float(os.environ.get("EVAL_MODEL_TIMEOUT", "45"))
_RETRY_CAP = 1


class ModelError(Exception):
    """Raised after the retry cap, or on schema-invalid output."""


def generate_json(prompt: str, schema: dict, *, temperature: float = 0.0,
                  image_png: bytes | None = None) -> dict:
    """Structured generation. `image_png` adds a page image for the OCR fallback (F16).

    Same credential, same retry cap, same schema constraint whether or not an image is
    attached — the OCR path is not a second model client, because a second model client is how
    the retry cap and the cost log quietly stop applying to half the calls.
    """
    key = os.environ.get("EVAL_MODEL_API_KEY")
    if not key:
        raise ModelError("EVAL_MODEL_API_KEY not configured")
    parts: list[dict] = [{"text": prompt}]
    if image_png is not None:
        parts.append({"inlineData": {"mimeType": "image/png",
                                     "data": base64.b64encode(image_png).decode("ascii")}})
    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": temperature,
                             "responseMimeType": "application/json",
                             "responseSchema": schema},
    }
    last: Exception | None = None
    for attempt in range(_RETRY_CAP + 1):
        try:
            r = httpx.post(f"{_BASE}/{_MODEL}:generateContent",
                           headers={"x-goog-api-key": key}, json=body, timeout=_TIMEOUT)
            r.raise_for_status()
            payload = r.json()
            usage = payload.get("usageMetadata", {})
            log.info("eval model usage model=%s total=%s", _MODEL, usage.get("totalTokenCount"))
            return json.loads(payload["candidates"][0]["content"]["parts"][0]["text"])
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as exc:
            last = exc
            log.warning("model call failed (attempt %d): %s", attempt + 1, exc)
    raise ModelError(f"model call failed after {_RETRY_CAP + 1} attempts: {last}")
