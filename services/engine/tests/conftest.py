"""Config the unit suite needs, supplied by the suite rather than by the developer's disk.

`app.config.Settings.__init__` raises `missing required env var: NEXT_PUBLIC_SUPABASE_URL`
before it reaches anything else, and `db._headers()` raises `ENGINE_MISCONFIGURED` without a
service key. Every database call in these tests is stubbed, so none of them reaches a project
— but constructing `Settings` at all is enough to fail, so a checkout with no repo-root `.env`
(which is what CI is, and what every git worktree is) could not run the suite. Individual test
modules had begun working around it with `monkeypatch.setenv` + `get_settings.cache_clear()`;
nobody owned the shared fix.

This is the same defect, and the same fix, as `services/evaluate-engine/tests/conftest.py`,
where it read as a product bug: four sealed-bid endpoints returned 500 where the test asserts
409, and a gate test that cannot tell a refusal from a crash is not proving the gate.

Two properties this relies on, both deliberate:

  * `config._load_dotenv` uses `os.environ.setdefault`, and this module runs at collection
    time — before any `Settings()` — so these values WIN over the repo-root `.env`. That is
    the point: `.env` is production, and a unit suite whose target depends on what happens to
    be on the developer's disk is not a suite you can read a result from.
  * `setdefault` here, so an explicitly exported value still wins. Pointing the suite at a
    local Supabase stack keeps working exactly as documented.

`.invalid` is reserved by RFC 2606, so nothing here can resolve to a real host either. And
`SUPABASE_ANON_JWT` is deliberately NOT set: `tests/isolation/conftest.py` treats a missing
anon key as "no credentials" and skips, which is what CI should keep doing. Its hard
non-loopback guard is untouched — with a local stack exported, the exports win here too.
"""

from __future__ import annotations

import os

os.environ.setdefault("NEXT_PUBLIC_SUPABASE_URL", "https://engine-unit-tests.invalid")
os.environ.setdefault("SUPABASE_SERVICE_JWT", "unit-test-service-key")
