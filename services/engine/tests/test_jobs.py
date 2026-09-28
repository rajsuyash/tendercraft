# services/engine/tests/test_jobs.py
"""Job lifecycle. No network: db is stubbed at the function the module actually calls."""
from __future__ import annotations

from app import jobs
from app.envelope import ApiError


class FakeDB:
    def __init__(self, active=None):
        self.rows = {}
        self.active = active
        self.updates = []

    def get_active_job_for_tender(self, workspace_id, tender_id, kind):
        return self.active

    def create_job(self, workspace_id, tender_id, kind):
        row = {"id": "j1", "workspace_id": workspace_id, "tender_id": tender_id,
               "kind": kind, "state": "queued", "done_stages": [], "attempts": 0}
        self.rows["j1"] = row
        return row

    def get_job(self, job_id, workspace_id=None):
        return self.rows.get(job_id)

    def update_job(self, job_id, patch):
        self.rows.setdefault(job_id, {}).update(patch)
        self.updates.append(patch)
        return self.rows[job_id]


def test_start_creates_a_queued_job(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(jobs, "db", fake)
    row = jobs.start("w1", "t1", "prepare")
    assert row["state"] == "queued" and row["id"] == "j1"


def test_start_returns_the_existing_job_rather_than_a_second_one(monkeypatch):
    existing = {"id": "j0", "state": "running", "stage": "analysis"}
    monkeypatch.setattr(jobs, "db", FakeDB(active=existing))
    assert jobs.start("w1", "t1", "prepare") is existing


def test_claim_marks_running_and_counts_the_attempt(monkeypatch):
    fake = FakeDB()
    fake.rows["j1"] = {"id": "j1", "state": "queued", "attempts": 0, "done_stages": []}
    monkeypatch.setattr(jobs, "db", fake)
    jobs.claim("j1")
    patch = fake.updates[-1]
    assert patch["state"] == "running" and patch["attempts"] == 1 and patch["started_at"]


def test_a_finished_stage_is_skipped_on_redelivery(monkeypatch):
    fake = FakeDB()
    fake.rows["j1"] = {"id": "j1", "state": "running", "done_stages": ["lock", "analysis"]}
    monkeypatch.setattr(jobs, "db", fake)
    assert jobs.should_run("j1", "analysis") is False
    assert jobs.should_run("j1", "draft") is True


def test_finishing_a_stage_appends_without_losing_the_earlier_ones(monkeypatch):
    fake = FakeDB()
    fake.rows["j1"] = {"id": "j1", "state": "running", "done_stages": ["lock"]}
    monkeypatch.setattr(jobs, "db", fake)
    jobs.finish_stage("j1", "analysis")
    assert fake.rows["j1"]["done_stages"] == ["lock", "analysis"]


def test_fail_records_the_code_and_message_not_a_generic_string(monkeypatch):
    fake = FakeDB()
    fake.rows["j1"] = {"id": "j1", "state": "running", "done_stages": []}
    monkeypatch.setattr(jobs, "db", fake)
    jobs.fail("j1", ApiError(409, "LOCK_BLOCKED", "3 unconfirmed requirements"))
    row = fake.rows["j1"]
    assert row["state"] == "failed" and row["error_code"] == "LOCK_BLOCKED"
    assert "unconfirmed" in row["error_message"] and row["finished_at"]


def test_fail_on_an_unexpected_exception_still_names_a_code(monkeypatch):
    fake = FakeDB()
    fake.rows["j1"] = {"id": "j1", "state": "running", "done_stages": []}
    monkeypatch.setattr(jobs, "db", fake)
    jobs.fail("j1", RuntimeError("boom"))
    assert fake.rows["j1"]["error_code"] == "JOB_FAILED"
    # The message is recorded for the operator, and it is not a stack trace.
    assert "Traceback" not in (fake.rows["j1"]["error_message"] or "")


def test_succeed_clears_the_stage_and_stamps_finished(monkeypatch):
    fake = FakeDB()
    fake.rows["j1"] = {"id": "j1", "state": "running", "done_stages": ["lock"]}
    monkeypatch.setattr(jobs, "db", fake)
    jobs.succeed("j1")
    assert fake.rows["j1"]["state"] == "succeeded" and fake.rows["j1"]["finished_at"]
