"""TypeSafe Jev client — calibrated fit bands for the opportunity feed.

Jev is a System One model: it returns a typed Choice with a probability distribution and a
confidence, no generated text. That is exactly the shape a ranker wants and a drafter does not,
so this module bands and `pipeline/relevance.py` still asks Gemini for the sentence a bidder
reads. Same rules as `pipeline/client.py`: one retry, explicit timeout, tokens logged per call,
question text in a file. Nothing here removes a row from anything (G-9) — a band is an order.

Optional by design: no `TYPESAFE_API_KEY` means `available()` is False and the caller keeps
the Gemini-then-keyword path. The variable is named in `.env.example` and `docs/deploy.md`
because a variable no document mentions is one the next deploy will not set.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from app import http  # shared pooled client (docs/known-pitfalls.md, latency section)

from .client import ModelError

log = logging.getLogger("tendercraft.pipeline")

_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = os.environ.get("TYPESAFE_MODEL", "jev-latest")
_TIMEOUT = float(os.environ.get("TYPESAFE_TIMEOUT", "30"))
_RETRY_CAP = 1
#: Tenders per request. ~60 state tokens + ~45 question tokens each; 100 sits near 11k of the
#: 64k budget with room for a long capability statement. Measured: 22 tenders = 4,651 tokens.
CHUNK = int(os.environ.get("JEV_CHUNK", "100"))
BANDS = ("high", "medium", "low")
_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "jev_relevance.json"
_PROMPT = json.loads(_PROMPT_PATH.read_text())


@dataclass(frozen=True)
class JevBand:
    opportunity_id: str
    band: str
    confidence: float
    probabilities: dict[str, float] = field(default_factory=dict)


def available() -> bool:
    return bool(os.environ.get("TYPESAFE_API_KEY"))


def _tender_line(o: dict) -> dict:
    return {
        "title": (o.get("title") or "")[:400],
        "categories": ", ".join((o.get("category_codes") or [])[:6]),
        "authority": o.get("authority") or "",
    }


def _clamp01(v) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def _post(body: dict) -> dict:
    """One call, one retry, ModelError on anything the caller cannot use."""
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        raise ModelError("TYPESAFE_API_KEY not configured")
    last = "no attempt"
    for attempt in range(_RETRY_CAP + 1):
        try:
            r = http.client.post(
                _URL, json=body, timeout=_TIMEOUT,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            )
        except Exception as exc:  # noqa: BLE001 — transport errors are the retry case
            last = f"transport: {exc}"
        else:
            if r.status_code == 200:
                data = r.json()
                if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
                    raise ModelError("jev: response carried no answers map")
                return data
            last = f"HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code == 429:
                try:
                    time.sleep(min(float(r.headers.get("retry-after", "1")), 5.0))
                except ValueError:
                    time.sleep(1.0)
            elif r.status_code < 500:
                break  # 4xx other than 429 will not change on retry
        log.warning("jev: attempt %d failed (%s)", attempt + 1, last)
    raise ModelError(f"jev call failed after {_RETRY_CAP + 1} attempts: {last}")


def _request(capability: str, keywords: list[str], chunk: list[dict]) -> dict:
    tenders = {str(o["id"]): _tender_line(o) for o in chunk}
    questions = {
        oid: {
            "type": "choice",
            "instructions": _PROMPT["instructions"].replace("{tender_ref}", f"`tenders.{oid}`"),
            "criteria": _PROMPT["criteria"],
        }
        for oid in tenders
    }
    return {
        "state": {
            "bidder": {"capability_statement": capability, "keywords": keywords},
            "tenders": tenders,
        },
        "model": MODEL,
        "questions": questions,
    }


def band_tenders(
    capability: str, keywords: list[str], opportunities: list[dict]
) -> dict[str, JevBand]:
    """→ {opportunity_id: JevBand}. A failed chunk is missing ids, never an exception."""
    out: dict[str, JevBand] = {}
    for start in range(0, len(opportunities), CHUNK):
        chunk = opportunities[start : start + CHUNK]
        try:
            data = _post(_request(capability, keywords, chunk))
        except ModelError as exc:
            log.warning("jev: chunk of %d failed (%s) — those rows fall back", len(chunk), exc)
            continue
        usage = data.get("usage") or {}
        log.info("jev usage model=%s tenders=%d input_tokens=%s output_tokens=%s",
                 MODEL, len(chunk), usage.get("input_tokens"), usage.get("output_tokens"))
        wanted = {str(o["id"]) for o in chunk}
        for oid, ans in data["answers"].items():
            if oid not in wanted or not isinstance(ans, dict):
                continue
            band = str(ans.get("choice", "")).lower()
            if band not in BANDS:
                continue  # an answer outside the enum must not become a silent "medium"
            probs = ans.get("probabilities") or {}
            out[oid] = JevBand(
                opportunity_id=oid, band=band, confidence=_clamp01(ans.get("confidence")),
                probabilities={b: _clamp01(probs.get(b)) for b in BANDS},
            )
    return out
