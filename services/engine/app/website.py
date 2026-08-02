"""Read a vendor's own website — a few pages of it — for their product vocabulary.

A capability statement is written in the language of a company describing itself ("expertise in
elevator / crane / oil industry"). A product page is written in the language of the thing
("Wire Rope · Crane Rope · Mining Rope · Elevator Rope"), which is the language a procurement
portal publishes in. That gap is why keyword suggestions read the site at all.

**Jina Reader, with the guarded fetcher as the fallback.** `https://r.jina.ai/<url>` renders the
page and returns markdown, which matters for two reasons: it handles sites that build their
navigation in JavaScript, and it preserves LINKS — so the entry page tells us which product
subpages exist instead of us guessing paths.

**The SSRF check still runs on the vendor's URL, before Jina ever sees it.** This is the part
that is easy to get wrong: handing an unvalidated URL to a third-party fetcher does not remove
the SSRF risk, it relocates it and removes our ability to see it. Jina would happily fetch
`http://169.254.169.254/` on our behalf and hand back the cloud metadata. So the host is
resolved and checked here first, exactly as `knowledge.fetch_url_text` does, and only then is
the URL passed on.

Read only when a vendor asks, never on a schedule. G-10's crawl discipline is about portals we
do not own; a customer's own site deserves the same restraint, and at 4 pages this is a read
rather than a crawl.
"""

from __future__ import annotations

import logging
import os
import re
from urllib.parse import urljoin, urlparse

import httpx

from .envelope import ApiError
from .knowledge import _reject_private_host, fetch_url_text

log = logging.getLogger("tendercraft.engine")

#: Off by default. When unset the guarded fetcher is used alone, which is why every deployment
#: works without this and only extraction quality changes.
JINA_READER = os.environ.get("JINA_READER_URL", "https://r.jina.ai/")
USE_JINA = os.environ.get("USE_JINA_READER", "1") != "0"

#: Four pages: the entry page plus the three most product-shaped links. Enough to reach a
#: products index and two categories; small enough that this stays a read.
MAX_PAGES = 4

#: Per page. A vendor site with a huge press section must not turn one suggestion into an
#: expensive model call.
MAX_CHARS_PER_PAGE = 8000

#: Paths worth a second request. Ordered — a products page beats an about page for vocabulary.
_WORTH_READING = (
    "product", "solution", "service", "capabilit", "what-we-do", "whatwedo",
    "offering", "range", "portfolio", "business", "sector", "industr", "about",
)

#: Never follow these, even on the same host. They are large, generic, and contain none of the
#: vendor's product vocabulary.
_SKIP = (
    "career", "job", "news", "blog", "media", "press", "investor", "contact",
    "privacy", "terms", "cookie", "login", "sitemap", "csr", "award", "event",
)

_MD_LINK = re.compile(r"\[[^\]]*\]\((https?://[^)\s]+)\)")


def _fetch(url: str) -> str:
    """One page. Jina Reader when enabled, the guarded fetcher otherwise.

    The host is validated BEFORE either path — see the module docstring. A failure here is
    raised; the caller decides whether one bad page should cost the whole read.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ApiError(400, "BAD_URL", "only http(s) URLs are allowed")
    if not parsed.hostname:
        raise ApiError(400, "BAD_URL", "missing host")
    _reject_private_host(parsed.hostname)

    if not USE_JINA:
        return fetch_url_text(url)
    try:
        # r.jina.ai is a fixed, trusted host, so this call is not itself an SSRF surface — the
        # vendor's URL was validated above and is only ever a path segment here.
        resp = httpx.get(
            f"{JINA_READER}{url}", timeout=30,
            headers={"User-Agent": "TenderCraft/0.1", "X-Return-Format": "markdown"},
        )
        resp.raise_for_status()
        return resp.text
    except httpx.HTTPError as exc:
        # Degrade to our own fetcher rather than failing: a third-party reader being down must
        # not take a profile screen with it.
        log.info(
            "website: jina reader unavailable for %s (%s) — using the guarded fetcher", url, exc
        )
        return fetch_url_text(url)


def _same_site(a: str | None, b: str | None) -> bool:
    """Host match, ignoring `www.`.

    Not cosmetic: ushamartin.com links to itself WITHOUT the www prefix while the vendor typed
    the URL WITH it, so a strict comparison rejected every product subpage and the read silently
    collapsed to one page. Sites disagreeing with themselves about www is the norm, not the
    exception.
    """
    strip = lambda h: (h or "").lower().removeprefix("www.")  # noqa: E731
    return bool(a and b) and strip(a) == strip(b)


def _worth_reading(link: str, host: str) -> bool:
    parsed = urlparse(link)
    if not _same_site(parsed.hostname, host):
        return False  # same site only: a vendor's LinkedIn is not their product catalogue
    path = (parsed.path or "").lower()
    if any(s in path for s in _SKIP):
        return False
    return any(w in path for w in _WORTH_READING)


def _rank(link: str) -> int:
    path = urlparse(link).path.lower()
    for i, word in enumerate(_WORTH_READING):
        if word in path:
            return i
    return len(_WORTH_READING)


def read_site(url: str, max_pages: int = MAX_PAGES) -> tuple[str, list[str]]:
    """→ (text, pages actually read). Raises only if the ENTRY page cannot be read.

    A subpage that fails is skipped: partial vocabulary is worth more than an error, and the
    caller reports which pages were read so a vendor can see what we based suggestions on.
    """
    entry = _fetch(url)
    read = [url]
    host = urlparse(url).hostname

    candidates: list[str] = []
    for match in _MD_LINK.finditer(entry):
        link = urljoin(url, match.group(1)).split("#")[0].rstrip("/")
        if link not in candidates and link.rstrip("/") != url.rstrip("/") \
                and _worth_reading(link, host or ""):
            candidates.append(link)
    candidates.sort(key=_rank)

    parts = [entry[:MAX_CHARS_PER_PAGE]]
    for link in candidates[: max_pages - 1]:
        try:
            parts.append(_fetch(link)[:MAX_CHARS_PER_PAGE])
            read.append(link)
        except (ApiError, httpx.HTTPError) as exc:
            log.info("website: skipped %s (%s)", link, exc)

    log.info("website: read %d page(s) from %s", len(read), host)
    return "\n\n".join(parts), read
