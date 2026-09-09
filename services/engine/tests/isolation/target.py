"""Is a Supabase URL a throwaway stack? Pure, importable from anywhere.

Lives here rather than in `conftest.py` because that module raises at IMPORT time when CI has
no Supabase credentials (the fail-closed ET-6 rule). The unit job runs
`pytest tests --ignore=tests/isolation`, so a unit test importing this predicate from conftest
drags that raise into a job that deliberately has no creds and fails collection — which is
exactly what `tests/test_isolation_target_guard.py` did.

A guard's own test has to run in the suite the guard protects. That means the predicate has to
be importable without side effects. Keeping a pure function beside a module-level `raise` was
the actual defect.
"""

from __future__ import annotations

import urllib.parse

#: Hosts that are a throwaway stack. `db` and `kong` are the service names a compose-based CI
#: reaches the stack by; the rest are loopback.
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "db", "kong", "supabase_kong"})


def is_local_target(url: str) -> bool:
    """Is `url` an ephemeral stack we may create and destroy workspaces in?

    Compares the PARSED hostname, never a substring: `https://localhost.evil.example.com`
    contains "localhost" and is not local, and a guard defeated by a substring is decoration.
    An empty url is not local — absent configuration must never read as permission.
    """
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except ValueError:
        return False
    return host in LOCAL_HOSTS
