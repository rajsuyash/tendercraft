"""The only way this service talks to the BidAssist partner API.

**This is the first credentialed source in the system, and that deserves an argument rather
than a shrug.**

G-8 says: adapters never log in, never replay a session cookie, never store a portal
credential, never solve a bot check. Read literally, an `X-API-KEY` header looks like a
breach. It is not, and the distinction is the whole reason this file may exist:

  * G-8's subject is a **portal** — a system whose operator did not agree to be read by us.
    Sending credentials there converts a public-page reader into a credentialed scraper and
    puts base PRD §9 ("no credentialed scraping in violation of portal terms") in the past
    tense. That is the act being forbidden.
  * BidAssist is a **licensed data vendor**. It issued this key to DONNA AI LABS under a paid
    partner agreement, for exactly this use, and the endpoint is called
    `/api/public/v1/tender/search`. Using the key is not circumventing consent; it *is* the
    consent. It is the same category of secret as `ANTHROPIC_API_KEY`, not the same category
    as a GeM seller login.

The distinction that matters operationally: **we hold no credential belonging to a customer,
and none belonging to a portal.** UML's GeM login stays untouchable (G-1), and every refusal
in `docs/feedback/usha-martin.md` still stands. What changed is that a third party we pay is
now willing to hand us data it already collected.

That said, this is a written guardrail and the reading above is a proposal, not a ruling —
`docs/discovery/source-bidassist.md` records it as a divergence awaiting human ratification,
per CLAUDE.md's rule that reality contradicting the PRD is proposed rather than silently
drifted. Until it is ratified the registry row carries the argument with it.

**Why the key lives here and not in `services/engine/app/discovery/`.** The guardrail script
greps that tree for `Authorization` headers and session vocabulary, and it must keep doing so
unconditionally. An exception carved into a guardrail is eventually used for the thing the
guardrail was written to forbid. The GeM connector exists for exactly this reason (its WAF
cookie), so the pattern is established: the source that needs a credential lives outside the
guarded tree, and the engine talks only to our own service.

The politeness controls stay regardless of the licence — rate cap, byte cap, backoff, no
automatic redirects, host allowlist. We are paying for this data, which buys us access, not
the right to hammer someone's API gateway.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

log = logging.getLogger("tendercraft.bidassist")

BASE_URL = "https://partner-api.bidassist.in"
ALLOWED_HOSTS = frozenset({"partner-api.bidassist.in"})

DEFAULT_USER_AGENT = (
    "TenderCraftBot/0.1 (+https://tendercraft.aisewak.com/bot; "
    "licensed partner feed; contact bot@tendercraft.aisewak.com)"
)
USER_AGENT = os.environ.get("BIDASSIST_USER_AGENT", DEFAULT_USER_AGENT)

MIN_INTERVAL_S = float(os.environ.get("BIDASSIST_MIN_INTERVAL_S", "1.0"))
MAX_BYTES = int(os.environ.get("BIDASSIST_MAX_BYTES", str(16 * 1024 * 1024)))
MAX_RETRIES = 3
ROBOTS_TTL_S = 3600.0


class FetchRefused(Exception):
    """A guardrail said no. Never retried, never worked around."""


class UpstreamError(Exception):
    """BidAssist answered, and the answer was a refusal.

    Separate from `FetchRefused` because the causes are opposite: one is us declining to make
    a request, the other is the vendor declining to serve it. Conflating them would let a
    misconfigured feed id read as a guardrail trip in the logs.
    """


@dataclass
class _RobotsEntry:
    parser: urllib.robotparser.RobotFileParser
    fetched_at: float


def api_key() -> str:
    """The partner key, or a named failure.

    Fails loudly and at the boundary rather than returning "" and sweeping zero rows. An
    aggregator that returns nothing is indistinguishable from a market with no tenders in it,
    which is the ET-7 failure mode wearing a friendly face — and it is exactly how
    `GEM_CONNECTOR_URL` stayed unset in production for weeks (docs/known-pitfalls.md).
    """
    key = os.environ.get("BIDASSIST_API_KEY", "").strip()
    if not key:
        raise UpstreamError(
            "BIDASSIST_API_KEY is unset — refusing to sweep, because an empty feed and an "
            "unconfigured feed look identical downstream"
        )
    return key


class GuardedFetcher:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(60.0, connect=8.0),
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
        )
        self._robots: dict[str, _RobotsEntry] = {}
        self._last_fetch: dict[str, float] = {}
        self._lock = threading.Lock()

    def _assert_host_allowed(self, url: str) -> str:
        host = (urlparse(url).hostname or "").lower()
        if host not in ALLOWED_HOSTS:
            raise FetchRefused(f"host {host!r} is not in the allowlist (G-10 / SSRF)")
        return host

    def _robots_parser(self, host: str) -> urllib.robotparser.RobotFileParser:
        entry = self._robots.get(host)
        now = time.monotonic()
        if entry and now - entry.fetched_at < ROBOTS_TTL_S:
            return entry.parser
        parser = urllib.robotparser.RobotFileParser()
        try:
            self._wait_for_rate_slot(host)
            response = self._client.get(f"https://{host}/robots.txt")
            # Measured 2026-08-29: this host is an API gateway and answers 403 with
            # `{"message":"Missing Authentication Token"}` on every unrouted path, robots.txt
            # included. No robots file means no robots rule, which is treated as "allowed" —
            # the same as the TED connector does, and the rate cap still applies.
            parser.parse(response.text.splitlines() if response.status_code == 200 else [])
        except httpx.HTTPError as exc:
            log.warning("robots.txt unreachable for %s (%s) — proceeding", host, exc)
            parser.parse([])
        self._robots[host] = _RobotsEntry(parser=parser, fetched_at=now)
        return parser

    def _assert_robots_allows(self, url: str, host: str) -> None:
        if not self._robots_parser(host).can_fetch(USER_AGENT, url):
            raise FetchRefused(f"robots.txt disallows {url} (G-10)")

    def _wait_for_rate_slot(self, host: str) -> None:
        with self._lock:
            last = self._last_fetch.get(host)
            if last is not None:
                elapsed = time.monotonic() - last
                if elapsed < MIN_INTERVAL_S:
                    time.sleep(MIN_INTERVAL_S - elapsed)
            self._last_fetch[host] = time.monotonic()

    def search(self, path: str, body: dict) -> dict:
        """POST a search body and return the parsed payload, or raise.

        **The status line is not the answer.** BidAssist returns HTTP 200 for a rejected
        request and puts the refusal in the body as `{"data": null, "success": false,
        "errorCode": …}` — measured 2026-08-29 on an over-large page size, an unknown filter
        key and a bogus feed id. `raise_for_status()` sees 200 and a caller reading
        `body["data"]` gets `None`, so the error is checked HERE, once, rather than trusted to
        every call site.
        """
        response = self._request(path, json_body=body)
        try:
            payload = json.loads(response.text)
        except ValueError as exc:
            raise UpstreamError(f"BidAssist returned non-JSON ({exc})") from exc

        if not isinstance(payload, dict):
            raise UpstreamError(f"BidAssist returned {type(payload).__name__}, expected object")

        if payload.get("data") is None:
            code = payload.get("errorCode") or "UNKNOWN"
            message = (payload.get("errorMessage") or "no message").strip()
            raise UpstreamError(f"BidAssist refused the search [{code}]: {message}")
        return payload

    def _request(self, path: str, *, json_body: dict) -> httpx.Response:
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        host = self._assert_host_allowed(url)
        self._assert_robots_allows(url, host)

        headers = {"X-API-KEY": api_key(), "Content-Type": "application/json"}

        backoff = 1.0
        last_status: int | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            self._wait_for_rate_slot(host)
            request = self._client.build_request("POST", url, json=json_body, headers=headers)
            response = self._read_capped(request)
            last_status = response.status_code

            if response.status_code == 429 or response.status_code >= 500:
                log.warning(
                    "BidAssist returned %s for %s (attempt %d/%d) — backing off %.1fs",
                    response.status_code, url, attempt, MAX_RETRIES, backoff,
                )
                if attempt < MAX_RETRIES:
                    time.sleep(backoff)
                    backoff *= 2
                continue

            if 300 <= response.status_code < 400:
                raise FetchRefused(
                    f"{url} redirected to {response.headers.get('location', '')!r}; "
                    "redirects are not followed automatically (G-10)"
                )
            if response.status_code in (401, 403):
                # Never retried: a rejected key is rejected, and retrying a credential is the
                # shape of a brute-force attempt whoever is reading the vendor's logs.
                raise UpstreamError(
                    f"BidAssist rejected the partner key ({response.status_code}) — "
                    "check BIDASSIST_API_KEY; not retried"
                )
            return response

        raise FetchRefused(f"{url} failed after {MAX_RETRIES} attempts (last {last_status})")

    def _read_capped(self, request: httpx.Request) -> httpx.Response:
        with self._client.stream(
            request.method, request.url, headers=request.headers, content=request.content
        ) as response:
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > MAX_BYTES:
                    raise FetchRefused(f"response from {request.url} exceeded {MAX_BYTES} bytes")
                chunks.append(chunk)
            body = b"".join(chunks)
            status, headers = response.status_code, response.headers

        # `iter_bytes()` yields DECODED bytes, so the transfer-encoding headers no longer
        # describe the body; carrying them over makes httpx gunzip an already-gunzipped
        # payload. Learned on the GeM connector, kept here for the same reason.
        clean = httpx.Headers(
            [(k, v) for k, v in headers.items()
             if k.lower() not in ("content-encoding", "content-length")]
        )
        return httpx.Response(status_code=status, headers=clean, content=body, request=request)

    def close(self) -> None:
        self._client.close()
