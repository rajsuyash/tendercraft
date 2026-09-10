"""Config the unit suite needs, supplied by the suite rather than by the environment.

Every db call in these tests is stubbed, so none of them reaches a project. But reading a
plain scoring constant does: `service.technical_state` asks for `EVAL_VARIANCE_THRESHOLD`,
which constructs the whole `Settings`, and `Settings.__init__` requires
NEXT_PUBLIC_EVAL_SUPABASE_URL before it gets to any threshold. With nothing set, four price
endpoints answered 500 instead of the 409 `test_sealed_bid_api.py` asserts — and a sealed-bid
test that cannot tell a refusal from a crash is not proving the gate.

Setting it here rather than in the workflow fixes the other half of the same defect.
`config._load_dotenv` reads the repo-root `.env`, which is production, so this suite passed
locally only because it picked up real config and failed in CI where there is none. The
loader uses `setdefault`, so the value below wins: the unit tests can no longer resolve a live
project by accident. Same shape as `tests/isolation/target.py` on the bidder side — a suite
whose target depends on what happens to be on the developer's disk is not a suite you can read
a result from.

Deliberately NOT the bidder URL: `Settings` refuses to start when the two match (F13-AC2), and
`.invalid` is reserved by RFC 2606 so nothing here can resolve to a real host either.
"""

from __future__ import annotations

import os

os.environ["NEXT_PUBLIC_EVAL_SUPABASE_URL"] = "https://evaluate-unit-tests.invalid"
