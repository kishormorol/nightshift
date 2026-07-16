"""Checks inside a real run, and in the digest that reports them.

The runner itself is covered in test_checks.py. This is the wiring: that a run
actually runs them, records them, sizes its lock for them, and that a red check
cannot be papered over by a digest calling the day clean.
"""

from __future__ import annotations

import sys
from datetime import date, datetime

import pytest

from nightaudit import report, scheduler
from nightaudit.budget import Ledger
from nightaudit.checks import CheckResult
from nightaudit.config import parse
from nightaudit.queue import Queue

AT = datetime(2026, 7, 14, 3, 0)
ON = date(2026, 7, 14)

#: A check is stamped with the wall clock, exactly as a RunResult is, so it
#: lands in today's day directory however the run's `now` was faked. Tests that
#: read checks back off disk after a real run must look for them there.
TODAY = date.today()


def build(tmp_path, checks=None, tasks=None):
    project_dir = tmp_path / "acme"
    project_dir.mkdir(exist_ok=True)
    entry = {
        "name": "acme",
        "path": str(project_dir),
        "tasks": tasks or ["code_review"],
    }
    if checks:
        entry["checks"] = checks
    return parse(
        {
            "providers": {"claude_code": {"enabled": True}},
            "projects": [entry],
            "schedule": {"windows": ["00:00-23:59"], "idle_minutes": 0},
            "digest": {"dir": str(tmp_path / "reports")},
        }
    )


def run(cfg, tmp_path, get_fake):
    return scheduler.run_once(
        cfg,
        now=AT,
        ledger=Ledger(tmp_path / "ledger.json"),
        queue=Queue(tmp_path / "queue.json"),
        get_adapter=get_fake,
    )


def py(code: str, name: str = "c") -> dict:
    return {"name": name, "run": f"{sys.executable} -c {code!r}"}


# ---- inside a run ------------------------------------------------------


def test_a_run_runs_the_projects_checks_and_records_them(tmp_path, get_fake, real_subprocess):
    cfg = build(tmp_path, checks=[py("print('hello from the check')", name="tests")])
    outcome = run(cfg, tmp_path, get_fake)

    assert outcome.ran is True
    stored = report.load_check_results(cfg, TODAY)
    assert [c.name for c in stored] == ["tests"]
    assert stored[0].status == "pass"
    assert stored[0].project == "acme"
    assert "hello from the check" in stored[0].output


def test_a_failing_check_does_not_fail_the_review(tmp_path, get_fake, real_subprocess):
    # The review is the product. A red check is a finding, not a reason to lose
    # the AI run the user was waiting for.
    cfg = build(tmp_path, checks=[py("import sys; sys.exit(1)", name="tests")])
    outcome = run(cfg, tmp_path, get_fake)

    assert outcome.ran is True
    assert outcome.results[-1].status == "ok"
    assert report.load_check_results(cfg, TODAY)[0].status == "fail"


def test_a_project_with_no_checks_records_none(tmp_path, get_fake):
    cfg = build(tmp_path)
    run(cfg, tmp_path, get_fake)
    assert report.load_check_results(cfg, TODAY) == []
    # And no empty directory left behind to make it look like something ran.
    assert not report.checks_dir(cfg, TODAY).exists()


def test_check_results_are_not_mistaken_for_runs(tmp_path, get_fake, real_subprocess):
    # load_results globs *.json in the day directory. If checks were written
    # there they would be read as malformed RunResults and silently dropped.
    cfg = build(tmp_path, checks=[py("print('x')", name="tests")])
    run(cfg, tmp_path, get_fake)

    runs = report.load_results(cfg, TODAY)
    assert len(runs) == 1
    assert runs[0].task == "code_review"
    assert len(report.load_check_results(cfg, TODAY)) == 1


def test_the_lock_allows_for_the_time_the_checks_will_take(tmp_path, get_fake, real_subprocess):
    # Work done under the lock that the lock does not know about is exactly what
    # makes a healthy holder look dead and get its live lock broken.
    cfg = build(
        tmp_path,
        checks=[
            {"name": "slow", "run": f"{sys.executable} -c 'pass'", "timeout_s": 300},
            {"name": "slower", "run": f"{sys.executable} -c 'pass'", "timeout_s": 200},
        ],
    )
    captured = {}
    real_lock = scheduler.Lock

    def spy(**kw):
        captured.update(kw)
        return real_lock(**kw)

    import nightaudit.scheduler as sched

    original, sched.Lock = sched.Lock, spy
    try:
        run(cfg, tmp_path, get_fake)
    finally:
        sched.Lock = original

    assert captured["extra_s"] == 500
    assert real_lock(**captured).max_run_s == cfg.timeout_s * scheduler.MAX_ATTEMPTS + 500


# ---- in the digest -----------------------------------------------------


def check(name, status, project="acme", exit_code=0, output=""):
    return CheckResult(
        project=project,
        name=name,
        command=f"run-{name}",
        status=status,
        started_at=AT,
        duration_s=1.0,
        exit_code=exit_code,
        output=output,
    )


def test_the_digest_lists_checks_under_their_project(tmp_path, cfg):
    text = report.render_digest(
        cfg, ON, results=[], checks=[check("tests", "pass"), check("lint", "fail", exit_code=1)]
    )
    assert "#### Checks" in text
    assert "✓ `tests`" in text
    assert "✗ `lint`" in text


def test_a_failed_checks_output_is_shown_and_a_passing_ones_is_not(tmp_path, cfg):
    text = report.render_digest(
        cfg,
        ON,
        results=[],
        checks=[
            check("lint", "fail", exit_code=1, output="E501 line too long"),
            check("tests", "pass", output="128 passed, nothing to see"),
        ],
    )
    assert "E501 line too long" in text
    assert "nothing to see" not in text


def test_a_red_check_stops_the_digest_calling_the_day_clean(tmp_path, cfg, fake_adapter):
    # "every run came back clean" is a claim about the AI's reading of the code.
    # It must not be printed over the top of a check that came back red.
    from nightaudit.adapters.base import RunResult

    clean_run = RunResult(
        provider="claude_code",
        project="acme",
        task="code_review",
        status="ok",
        findings_md="No findings.",
        started_at=AT,
        duration_s=1.0,
    )
    text = report.render_digest(
        cfg, ON, results=[clean_run], checks=[check("tests", "fail", exit_code=1)]
    )
    assert "every run came back clean" in text
    assert "1 configured check did not pass" in text
    assert "`tests` (acme)" in text


def test_a_project_seen_only_through_its_checks_still_counts(tmp_path, cfg):
    # Found in a real digest: the header said "0 projects · 0 runs" directly
    # above a project section listing three checks.
    text = report.render_digest(cfg, ON, results=[], checks=[check("tests", "pass")])
    assert "1 project · 0 runs" in text


def test_a_day_of_nothing_at_all_still_says_so(tmp_path, cfg):
    text = report.render_digest(cfg, ON, results=[], checks=[])
    assert "Nothing ran today" in text


def test_no_checks_leaves_the_digest_exactly_as_it_was(tmp_path, cfg):
    text = report.render_digest(cfg, ON, results=[], checks=[])
    assert "Checks" not in text
    assert "did not pass" not in text


@pytest.mark.parametrize(
    "status,mark", [("pass", "✓"), ("fail", "✗"), ("timeout", "⏱"), ("error", "⚠")]
)
def test_every_status_has_its_own_mark(tmp_path, cfg, status, mark):
    text = report.render_digest(cfg, ON, results=[], checks=[check("c", status)])
    assert mark in text


def test_check_results_survive_the_trip_through_disk(tmp_path, cfg):
    written = [check("tests", "fail", exit_code=2, output="boom")]
    report.store_check_results(cfg, written)
    loaded = report.load_check_results(cfg, ON)
    assert loaded == written


def test_an_unreadable_check_file_does_not_sink_the_digest(tmp_path, cfg):
    report.store_check_results(cfg, [check("good", "pass")])
    (report.checks_dir(cfg, ON) / "broken.json").write_text("{not json")
    assert [c.name for c in report.load_check_results(cfg, ON)] == ["good"]
