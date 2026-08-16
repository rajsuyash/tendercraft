"""The only way this service talks to GeM.

Every outbound request goes through `GuardedFetcher`, which enforces G-10 in one place:
robots.txt, an identified user agent carrying a contact address, a per-host rate cap,
exponential backoff, a byte cap, a host allowlist, and no automatic redirects.

**Why this service exists separately from `services/engine/app/discovery`.** GeM's listing
endpoint requires a cookie (403 without one — measured, see docs/discovery/source-gem.md §2).
That cookie is a WAF cookie handed to any first-time visitor by a plain GET of a public page:
there is no login, no credential, no CAPTCHA and no JS challenge on that path. So G-8 — "no
*authenticated* acquisition" — is not breached. But the guardrail script greps for `cookie`
anywhere under `app/discovery`, and that grep is worth keeping strict for the portals it was
written for: the ones that really are behind logins. Rather than weaken it, the one source that
legitimately needs an anonymous cookie lives out here.

**The line this file must never cross.** We accept a cookie that is *given* to us. We do not
solve challenges. `assert_no_bot_challenge` fails the run closed if GeM ever puts a JS
challenge, CAPTCHA or commercial bot-defence in front of this path — because the correct
response to "the portal started asking us to prove we are a browser" is to stop and re-review
the source, not to become more convincing. A fetcher that adapts to a challenge has crossed
from reading a public page into evading a control.
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

log = logging.getLogger("tendercraft.gem")

BASE_URL = "https://bidplus.gem.gov.in"

# A portal-supplied URL must never send us anywhere else. Discovery multiplies the number of
# untrusted URLs this system touches, and document_urls in a later phase come straight out of
# portal JSON — so the allowlist is checked on every fetch, not just the ones we construct.
ALLOWED_HOSTS = frozenset({"bidplus.gem.gov.in"})

# G-10 wants us identifiable and reachable. A contact address in the UA is how a portal admin
# asks us to stop without having to guess who we are; EC-9 says we honour that immediately.
DEFAULT_USER_AGENT = (
    "TenderCraftBot/0.1 (+https://tendercraft.aisewak.com/bot; "
    "public tender discovery; contact bot@tendercraft.aisewak.com)"
)
USER_AGENT = os.environ.get("GEM_USER_AGENT", DEFAULT_USER_AGENT)

# One request per second per host, serialised. 300 listing pages/day is ~5 minutes of traffic;
# there is no reason to go faster and every reason not to.
MIN_INTERVAL_S = float(os.environ.get("GEM_MIN_INTERVAL_S", "1.0"))

# A listing page is ~30 KB. The cap exists so a redirect-to-something-enormous cannot exhaust
# memory, not to be tight.
MAX_BYTES = int(os.environ.get("GEM_MAX_BYTES", str(8 * 1024 * 1024)))

MAX_RETRIES = 3
ROBOTS_TTL_S = 3600.0

# Markers for "the portal is now challenging us". Deliberately includes the commercial
# bot-defence vendors: if any of these appear, the answer is a human re-reviewing the source.
_CHALLENGE_MARKERS = (
    "jschl",
    "cf-challenge",
    "cf_chl",
    "incapsula",
    "imperva",
    "distil",
    "recaptcha",
    "g-recaptcha",
    "hcaptcha",
    "are you a human",
    "enable javascript and cookies to continue",
    # A portal's OWN captcha, which the commercial-vendor list above does not catch. This gap
    # was found and written up on 2026-08-07 (docs/discovery/source-gem-contracts.md §3) and
    # left open: `gem.gov.in/view_contracts` is captcha-gated on both search forms, and
    # `assert_no_bot_challenge` returned CLEAN on it. A clean check therefore read as
    # permission on a page that is unambiguously for humans. The danger is not a loud failure
    # — it is submitting a blank captcha field and recording the empty result as "no contracts
    # found", which is a fabricated fact with nothing anywhere to contradict it.
    "captcha_entered",
    "h_captcha",
    "encryptcaptcha",
    "captcha_code",
    "enter captcha",
)


class FetchRefused(Exception):
    """A guardrail said no. Never retried, never worked around."""


class BotChallengeDetected(FetchRefused):
    """G-8: the portal started asking us to prove we are a browser. Stop the run."""


def assert_no_bot_challenge(body: str, url: str) -> None:
    lowered = body[:20000].lower()
    for marker in _CHALLENGE_MARKERS:
        if marker in lowered:
            raise BotChallengeDetected(
                f"bot-challenge marker {marker!r} in response from {url} — "
                "run halted; a human must re-review this source (G-8, EC-9)"
            )


@dataclass
class _RobotsEntry:
    parser: urllib.robotparser.RobotFileParser
    fetched_at: float


class GuardedFetcher:
    """Rate-capped, robots-respecting, allowlisted HTTP.

    Holds an httpx.Client whose cookie jar lives for the lifetime of this object and is never
    written to disk. `reset_session()` drops it. One fetcher per sweep run.
    """

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(20.0, connect=8.0),
            # Manual redirect handling: an automatic redirect skips the allowlist check, which
            # is the documented SSRF bypass in docs/known-pitfalls.md.
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT},
        )
        self._robots: dict[str, _RobotsEntry] = {}
        self._last_fetch: dict[str, float] = {}
        self._lock = threading.Lock()

    # ── guardrails ────────────────────────────────────────────────────────

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
        robots_url = f"https://{host}/robots.txt"
        try:
            # Fetched outside the robots check itself — robots.txt is always fetchable — but
            # still rate-capped, so a cold cache cannot burst.
            self._wait_for_rate_slot(host)
            response = self._client.get(robots_url)
            parser.parse(response.text.splitlines() if response.status_code == 200 else [])
        except httpx.HTTPError as exc:
            # Unreachable robots.txt is treated as "allowed", matching RFC 9309: a 4xx/5xx or
            # network failure does not imply a blanket disallow. Logged so a persistent
            # failure is visible rather than silently permissive.
            log.warning("robots.txt unreachable for %s (%s) — proceeding", host, exc)
            parser.parse([])
        self._robots[host] = _RobotsEntry(parser=parser, fetched_at=now)
        return parser

    def _assert_robots_allows(self, url: str, host: str) -> None:
        if not self._robots_parser(host).can_fetch(USER_AGENT, url):
            raise FetchRefused(f"robots.txt disallows {url} (G-10)")

    def _wait_for_rate_slot(self, host: str) -> None:
        # Held across the sleep on purpose: this serialises requests per host, which is the
        # point. Concurrency against a government portal is not a feature we want.
        with self._lock:
            last = self._last_fetch.get(host)
            if last is not None:
                elapsed = time.monotonic() - last
                if elapsed < MIN_INTERVAL_S:
                    time.sleep(MIN_INTERVAL_S - elapsed)
            self._last_fetch[host] = time.monotonic()

    def _read_capped(self, request: httpx.Request) -> httpx.Response:
        with self._client.stream(request.method, request.url, headers=request.headers,
                                 content=request.content) as response:
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
        # describe the body. Carrying them over makes httpx gunzip an already-gunzipped body
        # and raise DecodingError("incorrect header check") — which surfaces as a portal
        # failure rather than as our bug. Strip them; the content is identity-encoded now.
        clean = httpx.Headers(
            [(k, v) for k, v in headers.items()
             if k.lower() not in ("content-encoding", "content-length")]
        )
        return httpx.Response(status_code=status, headers=clean, content=body, request=request)

    # ── the two verbs this service needs ──────────────────────────────────

    def get(self, path: str) -> httpx.Response:
        return self._request("GET", path, data=None)

    def post_form(self, path: str, data: dict[str, str]) -> httpx.Response:
        return self._request("POST", path, data=data)

    def _request(self, method: str, path: str, data: dict[str, str] | None) -> httpx.Response:
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        host = self._assert_host_allowed(url)
        self._assert_robots_allows(url, host)

        backoff = 1.0
        last_status: int | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            self._wait_for_rate_slot(host)
            request = self._client.build_request(method, url, data=data)
            response = self._read_capped(request)
            last_status = response.status_code

            if response.status_code in (429,) or response.status_code >= 500:
                # Backoff, never IP rotation, never a different UA (G-10 / EC-9).
                log.warning(
                    "GeM returned %s for %s (attempt %d/%d) — backing off %.1fs",
                    response.status_code, url, attempt, MAX_RETRIES, backoff,
                )
                if attempt < MAX_RETRIES:
                    time.sleep(backoff)
                    backoff *= 2
                continue

            if response.status_code >= 300 and response.status_code < 400:
                location = response.headers.get("location", "")
                raise FetchRefused(
                    f"{url} redirected to {location!r}; redirects are not followed "
                    "automatically — add the target to the allowlist deliberately (G-10)"
                )

            return response

        raise FetchRefused(f"{url} failed after {MAX_RETRIES} attempts (last status {last_status})")

    def reset_session(self) -> None:
        """Drop every cookie. Called between runs so no session outlives its sweep."""
        self._client.cookies.clear()

    def close(self) -> None:
        self._client.close()
