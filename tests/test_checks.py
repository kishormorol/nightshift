"""The check runner — the one part of nightaudit that executes rather than reads.

These tests spawn real processes (see the ``real_subprocess`` fixture). Every
command is ``sys.executable``, so nothing needs installing and no quota is spent.
A runner tested only against a mocked ``subprocess`` has never run anything.
"""

from __future__ import annotations

import sys
from datetime import datetime

import pytest

from nightaudit import checks
from nightaudit.checks import CheckResult, run_check, run_checks, tail
from nightaudit.config import Check, Project

AT = datetime(2026, 7, 14, 3, 0)


def py(code: str, name: str = "c", timeout_s: int = 30) -> Check:
    """A check that runs `code` in this interpreter — portable and free."""
    return Check(name=name, run=f"{sys.executable} -c {code!r}", timeout_s=timeout_s)


def project(tmp_path, *checks_: Check) -> Project:
    return Project(
        name="acme", path=tmp_path, tasks=("code_review",), checks=tuple(checks_)
    )


# ---- one check ---------------------------------------------------------


def test_exit_zero_passes(tmp_path, real_subprocess):
    result = run_check(py("print('all good')"), tmp_path)
    assert result.status == "pass"
    assert result.ok is True
    assert result.exit_code == 0
    assert "all good" in result.output


def test_a_nonzero_exit_fails_and_keeps_the_output(tmp_path, real_subprocess):
    result = run_check(py("import sys; print('3 failed'); sys.exit(1)"), tmp_path)
    assert result.status == "fail"
    assert result.ok is False
    assert result.exit_code == 1
    assert "3 failed" in result.output


def test_stderr_is_kept_too(tmp_path, real_subprocess):
    # Most tools say what broke on stderr; a digest without it is useless.
    result = run_check(py("import sys; print('boom', file=sys.stderr); sys.exit(2)"), tmp_path)
    assert result.exit_code == 2
    assert "boom" in result.output


def test_a_hanging_check_times_out_rather_than_wedging_the_run(tmp_path, real_subprocess):
    result = run_check(py("import time; time.sleep(30)", timeout_s=1), tmp_path)
    assert result.status == "timeout"
    assert result.ok is False
    assert result.exit_code is None


def test_a_missing_command_is_a_result_not_an_exception(tmp_path, real_subprocess):
    # A typo'd check must not cost the user the AI review they were waiting for.
    result = run_check(Check(name="nope", run="definitely-not-a-real-binary-xyz"), tmp_path)
    assert result.status == "error"
    assert "not found" in result.output
    assert result.exit_code is None


def test_the_check_runs_in_the_project_directory(tmp_path, real_subprocess):
    (tmp_path / "marker.txt").write_text("here")
    result = run_check(py("import os; print(os.path.exists('marker.txt'))"), tmp_path)
    assert "True" in result.output


def test_no_shell_means_no_shell(tmp_path, real_subprocess):
    # argv, not a shell line: $HOME arrives as four literal characters. A user
    # who wants a pipeline points a check at a script.
    result = run_check(Check(name="echo", run=f"{sys.executable} -c 'print(1)' && rm -rf $HOME"), tmp_path)
    # `&&` and everything after it are argv to python -c, not a second command.
    assert result.status in {"pass", "fail", "error"}
    assert (tmp_path / "..").exists()  # nothing was removed


# ---- a project's checks ------------------------------------------------


def test_checks_run_in_config_order(tmp_path, real_subprocess):
    p = project(tmp_path, py("print('first')", name="one"), py("print('second')", name="two"))
    results = run_checks(p, AT)
    assert [r.name for r in results] == ["one", "two"]
    assert all(r.project == "acme" for r in results)


def test_a_failing_check_does_not_stop_the_next_one(tmp_path, real_subprocess):
    # The point is a report of what is broken; stopping at the first would hide
    # the rest of it.
    p = project(
        tmp_path,
        py("import sys; sys.exit(1)", name="broken"),
        py("print('ran anyway')", name="after"),
    )
    results = run_checks(p, AT)
    assert [r.status for r in results] == ["fail", "pass"]


def test_a_project_with_no_checks_runs_none(tmp_path):
    assert run_checks(project(tmp_path), AT) == []


def test_budget_is_the_sum_of_every_timeout(tmp_path):
    p = project(tmp_path, py("", name="a", timeout_s=30), py("", name="b", timeout_s=90))
    assert checks.budget_s(p) == 120


def test_budget_of_no_checks_is_zero(tmp_path):
    assert checks.budget_s(project(tmp_path)) == 0


# ---- output trimming ---------------------------------------------------


def test_tail_keeps_the_end_where_the_error_is():
    text = "\n".join(str(i) for i in range(100))
    out = tail(text)
    assert "99" in out
    assert "0\n1\n2" not in out
    assert "earlier lines omitted" in out


def test_tail_leaves_short_output_alone():
    assert tail("just this") == "just this"


def test_tail_strips_the_colour_real_tools_emit():
    # Found by running a real pytest as a check: it colours its output even on a
    # pipe, and the digest is markdown in a file, where "\x1b[33m" renders as
    # the literal text "[33m". Every fake in this suite emitted clean ASCII, so
    # nothing here could have caught it.
    assert tail("\x1b[33mno tests ran\x1b[0m") == "no tests ran"
    assert tail("\x1b[31mERROR: not found\x1b[0m\n") == "ERROR: not found"


def test_tail_leaves_bracketed_text_that_is_not_an_escape_alone():
    assert tail("[33m is not an escape sequence") == "[33m is not an escape sequence"


def test_a_real_command_reaches_the_digest_without_escape_codes(tmp_path, real_subprocess):
    result = run_check(py("print('\\x1b[31mred\\x1b[0m text')"), tmp_path)
    assert "\x1b" not in result.output
    assert "red text" in result.output


def test_tail_of_nothing_is_nothing():
    assert tail("") == ""


def test_tail_caps_a_single_enormous_line():
    out = tail("x" * 50_000)
    assert len(out) <= checks.MAX_OUTPUT_CHARS + 20


# ---- serialisation -----------------------------------------------------


def test_a_result_survives_a_round_trip():
    original = CheckResult(
        project="acme",
        name="tests",
        command="pytest -q",
        status="fail",
        started_at=AT,
        duration_s=1.25,
        exit_code=1,
        output="3 failed",
    )
    assert CheckResult.from_dict(original.to_dict()) == original


@pytest.mark.parametrize("missing", ["project", "name", "command", "status"])
def test_a_result_missing_a_required_field_is_rejected(missing):
    raw = CheckResult(
        project="a", name="n", command="c", status="pass", started_at=AT, duration_s=0.0
    ).to_dict()
    del raw[missing]
    with pytest.raises(KeyError):
        CheckResult.from_dict(raw)
