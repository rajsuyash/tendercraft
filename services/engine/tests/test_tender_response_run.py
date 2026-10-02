"""evals/tender_response/run.py — the CLI: missing-env named error, self-check on the
synthetic fixture, and the printed input count. No network, no model calls, no $TC_GOLDEN_DIR
needed beyond the committed fixtures dir.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.tender_response import golden, run

FIXTURES = Path(__file__).parent.parent / "evals" / "tender_response" / "fixtures"


def test_main_requires_pred_or_self_check(monkeypatch):
    monkeypatch.setenv(golden.ENV_VAR, str(FIXTURES))
    with pytest.raises(SystemExit) as exc:
        run.main([])
    assert exc.value.code != 0


def test_main_fails_named_when_env_var_unset(monkeypatch, capsys):
    monkeypatch.delenv(golden.ENV_VAR, raising=False)
    code = run.main(["--self-check"])
    assert code != 0
    err = capsys.readouterr().err
    assert golden.ENV_VAR in err


def test_self_check_on_fixtures_reports_1_requirements_and_one_tender(monkeypatch, capsys):
    monkeypatch.setenv(golden.ENV_VAR, str(FIXTURES))
    code = run.main(["--self-check"])
    out = capsys.readouterr().out
    assert code == 0
    assert "tenders=1 requirements=3" in out
    assert "FIX_DEMO_001" in out


def test_self_check_respects_tender_filter(monkeypatch, capsys):
    monkeypatch.setenv(golden.ENV_VAR, str(FIXTURES))
    code = run.main(["--self-check", "--tender", "FIX_DEMO_001"])
    assert code == 0
    out = capsys.readouterr().out
    assert "tenders=1" in out


def test_self_check_unknown_tender_is_a_named_error(monkeypatch, capsys):
    monkeypatch.setenv(golden.ENV_VAR, str(FIXTURES))
    code = run.main(["--self-check", "--tender", "NO_SUCH_TENDER"])
    assert code != 0
    assert "ERROR" in capsys.readouterr().err
