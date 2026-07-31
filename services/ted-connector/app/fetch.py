"""The only way this service talks to BOAMP.

Same guarded-fetch contract as the GeM connector — robots.txt, an identified user agent with a
contact address, a per-host rate cap, backoff, a byte cap, a host allowlist and no automatic
redirects — because G-10 is about our conduct, not about how permissive a particular source
happens to be.

**Why TED and not BOAMP.** BOAMP has better French coverage — it carries below-threshold
notices, which TED does not — but its API is `Disallow: /api/` for every agent except Googlebot.
That is almost certainly a search-indexing rule rather than an access-control statement, since
DILA publishes the data under Licence Ouverte v2.0 and promotes the API on api.gouv.fr. It is
not our call to make quietly: the check that refused it had just caught a mistake a truncated
read of the same file had missed, and narrowing a guardrail because we have reasoned our way
around it is the failure the guardrail exists to prevent. Recorded as a decision for a human,
with the option of a written OK from DILA.

TED needs no such argument. No robots restrictions, no authentication, no reproduction clause —
and being EU-wide, this one connector serves a German or Spanish client later for the price of a
query change. The tradeoff accepted: TED is above EU threshold only (~EUR 143k for services), so
it fits a consultancy-scale bidder and misses smaller French tenders.

The politeness controls stay regardless. A free public service run for the public benefit is
exactly the thing not to hammer.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

log = logging.getLogger("tendercraft.ted")

BASE_URL = "https://api.ted.europa.eu"
ALLOWED_HOSTS = frozenset({"api.ted.europa.eu"})

DEFAULT_USER_AGENT = (
    "TenderCraftBot/0.1 (+https://tendercraft.aisewak.com/bot; "
    "public tender discovery; contact bot@tendercraft.aisewak.com)"
)
USER_AGENT = os.environ.get("TED_USER_AGENT", DEFAULT_USER_AGENT)

MIN_INTERVAL_S = float(os.environ.get("TED_MIN_INTERVAL_S", "1.0"))
MAX_BYTES = int(os.environ.get("TED_MAX_BYTES", str(16 * 1024 * 1024)))
MAX_RETRIES = 3
ROBOTS_TTL_S = 3600.0


class FetchRefused(Exception):
    """A guardrail said no. Never retried, never worked around."""


@dataclass
class _RobotsEntry:
    parser: urllib.robotparser.RobotFileParser
    fetched_at: float


class GuardedFetcher:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(30.0, connect=8.0),
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

    def post_json(self, path: str, body: dict) -> httpx.Response:
        return self._request(path, json_body=body)

    def get(self, path: str, params: dict[str, str] | None = None) -> httpx.Response:
        return self._request(path, params=params)

    def _request(
        self, path: str, *, params: dict[str, str] | None = None, json_body: dict | None = None
    ) -> httpx.Response:
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        host = self._assert_host_allowed(url)
        self._assert_robots_allows(url, host)

        backoff = 1.0
        last_status: int | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            self._wait_for_rate_slot(host)
            request = self._client.build_request(
                "POST" if json_body is not None else "GET",
                url,
                params=params,
                json=json_body,
            )
            response = self._read_capped(request)
            last_status = response.status_code

            if response.status_code == 429 or response.status_code >= 500:
                log.warning(
                    "BOAMP returned %s for %s (attempt %d/%d) — backing off %.1fs",
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
        # describe the body; carrying them over makes httpx gunzip an already-gunzipped payload
        # and raise DecodingError on the first fetch. Learned on the GeM connector, and BOAMP
        # gzips everything, so this is not theoretical here.
        clean = httpx.Headers(
            [(k, v) for k, v in headers.items()
             if k.lower() not in ("content-encoding", "content-length")]
        )
        return httpx.Response(status_code=status, headers=clean, content=body, request=request)

    def close(self) -> None:
        self._client.close()
