"""The isolation suite must be unable to run against a hosted project.

Not a hypothetical. `conftest.py` reads the repo-root `.env`, which is production, and
`requires_supabase` only checked whether credentials EXIST — so on any machine with a working
`.env`, a bare `uv run pytest` ran the 89-test ET-6 suite against the live database. Measured
2026-09-07: 148 of 347 production workspaces were test debris, in dated batches matching
full-suite runs.

It fails in the worst possible direction. Production has the same schema, so the suite PASSES;
nothing errors, and the run is reported as clean verification. The cost is silent and permanent
— `audit_events` is append-only, so those workspaces can never be deleted, and that has already
blocked a schema change once (docs/known-pitfalls.md).

This lives in the unit suite, not in tests/isolation/, on purpose: a guard that only runs when
you already reached the thing it guards is not a guard.
"""

from __future__ import annotations

from tests.isolation.target import is_local_target


class TestHostedProjectsAreRefused:
    def test_the_production_project_is_not_a_local_target(self):
        assert not is_local_target("https://dgbtlcumzqkzjivwmjqe.supabase.co")

    def test_any_supabase_co_host_is_refused(self):
        assert not is_local_target("https://anything.supabase.co")

    def test_an_empty_url_is_not_local(self):
        """Absent config must not read as permission."""
        assert not is_local_target("")

    def test_a_hostname_merely_containing_localhost_is_refused(self):
        """Substring matching is how a guard like this gets defeated."""
        assert not is_local_target("https://localhost.evil.example.com")
        assert not is_local_target("https://127.0.0.1.evil.example.com")


class TestLocalTargetsAreAllowed:
    def test_the_supabase_cli_default(self):
        assert is_local_target("http://127.0.0.1:54321")

    def test_a_shifted_port(self):
        """Running beside another project's stack is normal and must not trip the guard."""
        assert is_local_target("http://127.0.0.1:54421")

    def test_localhost_by_name(self):
        assert is_local_target("http://localhost:54321")

    def test_ipv6_loopback(self):
        assert is_local_target("http://[::1]:54321")

    def test_the_compose_service_name_ci_would_use(self):
        assert is_local_target("http://db:54321")
        assert is_local_target("http://kong:8000")
