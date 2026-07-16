from __future__ import annotations

import json
import shutil
import time
from datetime import datetime, timedelta

import pytest

from nightshift import events, report, scheduler
from nightshift.budget import Ledger
from nightshift.lock import Lock
from nightshift.queue import Queue
from tests.conftest import FakeAdapter, build_config

AT_NIGHT = datetime(2026, 7, 14, 3, 0)
AT_NOON = datetime(2026, 7, 14, 12, 0)


@pytest.fixture
def night_cfg(tmp_path, project_dir):
    return build_config(tmp_path, project_dir, windows=["00:00-06:00"])


def run(cfg, get_fake, **kw):
    kw.setdefault("now", AT_NIGHT)
    kw.setdefault("ledger", Ledger(cfg.digest_dir.parent / "ledger.json"))
    kw.setdefault("queue", Queue(cfg.digest_dir.parent / "queue.json"))
    kw.setdefault("get_adapter", get_fake)
    return scheduler.run_once(cfg, **kw)


# ---- gate 1: window ---------------------------------------------------


def test_runs_inside_the_window(night_cfg, get_fake, fake_adapter):
    outcome = run(night_cfg, get_fake, now=AT_NIGHT)
    assert outcome.ran is True
    assert outcome.results[-1].status == "ok"
    assert len(fake_adapter.calls) == 1


def test_outside_the_window_does_nothing(night_cfg, get_fake, fake_adapter):
    outcome = run(night_cfg, get_fake, now=AT_NOON)
    assert outcome.ran is False
    assert "outside configured windows" in outcome.reason
    assert fake_adapter.calls == []


def test_window_crossing_midnight_is_open_at_2am(tmp_path, project_dir, get_fake):
    cfg = build_config(tmp_path, project_dir, windows=["22:00-06:00"])
    assert run(cfg, get_fake, now=datetime(2026, 7, 14, 2, 0)).ran is True


def test_window_crossing_midnight_is_shut_at_noon(tmp_path, project_dir, get_fake):
    cfg = build_config(tmp_path, project_dir, windows=["22:00-06:00"])
    assert run(cfg, get_fake, now=datetime(2026, 7, 14, 12, 0)).ran is False


def test_now_flag_ignores_the_window(night_cfg, get_fake, fake_adapter):
    outcome = run(night_cfg, get_fake, now=AT_NOON, force=True)
    assert outcome.ran is True
    assert len(fake_adapter.calls) == 1


# ---- gate 2: idle -----------------------------------------------------


def test_recent_human_use_blocks_the_run(night_cfg, get_fake, fake_adapter):
    fake_adapter.human_used_at = AT_NIGHT - timedelta(minutes=5)
    outcome = run(night_cfg, get_fake)
    assert outcome.ran is False
    assert "5m ago" in outcome.reason and "60m idle" in outcome.reason
    assert fake_adapter.calls == []


def test_old_human_use_allows_the_run(night_cfg, get_fake, fake_adapter):
    fake_adapter.human_used_at = AT_NIGHT - timedelta(minutes=90)
    assert run(night_cfg, get_fake).ran is True


def test_idle_boundary_is_inclusive(night_cfg, get_fake, fake_adapter):
    fake_adapter.human_used_at = AT_NIGHT - timedelta(minutes=60)
    assert run(night_cfg, get_fake).ran is True


def test_unknown_last_use_is_treated_as_idle(night_cfg, get_fake, fake_adapter):
    # An adapter that cannot tell must not block every run forever.
    fake_adapter.human_used_at = None
    assert run(night_cfg, get_fake).ran is True


def test_now_flag_ignores_idle(night_cfg, get_fake, fake_adapter):
    fake_adapter.human_used_at = AT_NIGHT - timedelta(minutes=1)
    assert run(night_cfg, get_fake, force=True).ran is True


def test_idle_minutes_zero_disables_the_check(tmp_path, project_dir, get_fake, fake_adapter):
    cfg = build_config(tmp_path, project_dir, windows=["00:00-06:00"], idle_minutes=0)
    fake_adapter.human_used_at = AT_NIGHT
    assert run(cfg, get_fake).ran is True


# ---- gate 3: budget ---------------------------------------------------


def test_at_daily_cap_the_run_is_refused(tmp_path, project_dir, get_fake, fake_adapter):
    cfg = build_config(tmp_path, project_dir, windows=["00:00-06:00"], max_day=2)
    ledger = Ledger(tmp_path / "ledger.json")
    for _ in range(2):
        ledger.increment("claude_code", AT_NIGHT)

    outcome = run(cfg, get_fake, ledger=ledger)
    assert outcome.ran is False
    assert "daily budget spent" in outcome.reason
    assert fake_adapter.calls == []


def test_now_flag_does_not_bypass_budget(tmp_path, project_dir, get_fake, fake_adapter):
    cfg = build_config(tmp_path, project_dir, windows=["00:00-06:00"], max_day=1)
    ledger = Ledger(tmp_path / "ledger.json")
    ledger.increment("claude_code", AT_NIGHT)

    outcome = run(cfg, get_fake, ledger=ledger, force=True, now=AT_NOON)
    assert outcome.ran is False
    assert "budget" in outcome.reason
    assert fake_adapter.calls == []


def test_hitting_the_cap_records_one_skip_for_the_digest(
    tmp_path, project_dir, get_fake
):
    cfg = build_config(tmp_path, project_dir, windows=["00:00-06:00"], max_day=1)
    ledger = Ledger(tmp_path / "ledger.json")
    ledger.increment("claude_code", AT_NIGHT)

    run(cfg, get_fake, ledger=ledger)
    stored = report.load_results(cfg, AT_NIGHT.date())
    skips = [r for r in stored if r.status == "skipped"]
    assert len(skips) == 1
    assert "budget" in skips[0].detail


def test_repeated_cron_ticks_do_not_flood_the_log_with_skips(
    tmp_path, project_dir, get_fake
):
    cfg = build_config(tmp_path, project_dir, windows=["00:00-06:00"], max_day=1)
    ledger = Ledger(tmp_path / "ledger.json")
    ledger.increment("claude_code", AT_NIGHT)

    # Cron fires hourly; the cap stays hit all night.
    for hour in range(1, 6):
        run(cfg, get_fake, ledger=ledger, now=AT_NIGHT.replace(hour=hour))

    skips = [r for r in report.load_results(cfg, AT_NIGHT.date()) if r.status == "skipped"]
    assert len(skips) == 1


def test_a_successful_run_increments_the_ledger(night_cfg, get_fake, tmp_path):
    ledger = Ledger(tmp_path / "ledger.json")
    run(night_cfg, get_fake, ledger=ledger)
    assert ledger.count("claude_code", "2026-07-14") == 1


def test_a_failed_run_still_costs_budget(night_cfg, get_fake, fake_adapter, tmp_path):
    # Both the attempt and its one retry consumed quota.
    fake_adapter.results = [("failed", ""), ("failed", "")]
    ledger = Ledger(tmp_path / "ledger.json")
    run(night_cfg, get_fake, ledger=ledger)
    assert ledger.count("claude_code", "2026-07-14") == 2


def test_weekly_cap_refuses_even_with_daily_room(tmp_path, project_dir, get_fake):
    cfg = build_config(
        tmp_path, project_dir, windows=["00:00-06:00"], max_day=6, max_week=6
    )
    ledger = Ledger(tmp_path / "ledger.json")
    monday = datetime(2026, 7, 13, 3, 0)
    for _ in range(6):
        ledger.increment("claude_code", monday)

    outcome = run(cfg, get_fake, ledger=ledger, now=AT_NIGHT)  # Tuesday, 0 spent today
    assert outcome.ran is False
    assert "weekly budget spent" in outcome.reason


# ---- gate 4: lock -----------------------------------------------------


def test_a_live_lock_blocks_the_run(night_cfg, get_fake, fake_adapter, isolated_home):
    held = Lock(isolated_home / "lock", timeout_s=600)
    held.acquire()
    try:
        outcome = run(night_cfg, get_fake)
        assert outcome.ran is False
        assert "in progress" in outcome.reason
        assert fake_adapter.calls == []
    finally:
        held.release()


def test_a_stale_lock_is_broken(night_cfg, get_fake, fake_adapter, isolated_home):
    path = isolated_home / "lock"
    # A day old — abandoned under any threshold the scheduler could compute.
    # This used to say `600 * 3`, which quietly encoded the arithmetic of a
    # single 600s attempt, and broke the moment the lock started sizing for
    # retries. Where the boundary actually falls is test_lock.py's business.
    path.write_text(
        json.dumps({"pid": 999999, "acquired_at": time.time() - 86_400}),
        encoding="utf-8",
    )
    outcome = run(night_cfg, get_fake)
    assert outcome.ran is True
    assert len(fake_adapter.calls) == 1


def test_a_lock_held_by_a_retrying_run_is_left_alone(
    night_cfg, get_fake, fake_adapter, isolated_home
):
    """A holder that retried is slow, not dead.

    The age is derived rather than hardcoded so it stays *between* the two
    thresholds if `timeout_s` or MAX_ATTEMPTS ever move — a literal here would
    fail for arithmetic reasons having nothing to do with the behaviour, which
    is exactly how test_a_stale_lock_is_broken above broke.

    The scheduler grants MAX_ATTEMPTS, so it must size the lock for all of them.
    Size it for one and this live lock is broken, and a second run starts beside
    the first.
    """
    path = isolated_home / "lock"
    one_try = Lock(path, timeout_s=night_cfg.timeout_s, attempts=1).stale_after_s
    retrying = Lock(
        path, timeout_s=night_cfg.timeout_s, attempts=scheduler.MAX_ATTEMPTS
    ).stale_after_s
    assert one_try < retrying, "MAX_ATTEMPTS > 1, or this test asserts nothing"

    # Comfortably past what a single attempt could justify, comfortably inside
    # what the full retry budget can.
    age = (one_try + retrying) / 2
    path.write_text(
        json.dumps({"pid": 999999, "acquired_at": time.time() - age}),
        encoding="utf-8",
    )
    outcome = run(night_cfg, get_fake)
    assert outcome.ran is False
    assert "in progress" in outcome.reason
    assert fake_adapter.calls == []


def test_lock_is_released_after_a_run(night_cfg, get_fake, isolated_home):
    run(night_cfg, get_fake)
    assert not (isolated_home / "lock").exists()


def test_lock_is_released_even_when_the_adapter_explodes(
    night_cfg, get_fake, fake_adapter, isolated_home
):
    fake_adapter.results = [RuntimeError("kaboom"), RuntimeError("kaboom")]
    run(night_cfg, get_fake)
    assert not (isolated_home / "lock").exists()


# ---- retries ----------------------------------------------------------


def test_a_failure_is_retried_exactly_once(night_cfg, get_fake, fake_adapter):
    fake_adapter.results = [("failed", ""), ("ok", "- LOW a.py:1 — x")]
    outcome = run(night_cfg, get_fake)
    assert len(fake_adapter.calls) == 2
    assert [r.status for r in outcome.results] == ["failed", "ok"]
    assert [r.attempt for r in outcome.results] == [1, 2]


def test_a_timeout_is_retried_once(night_cfg, get_fake, fake_adapter):
    fake_adapter.results = [("timeout", ""), ("ok", "- LOW a.py:1 — x")]
    outcome = run(night_cfg, get_fake)
    assert len(fake_adapter.calls) == 2
    assert outcome.results[-1].status == "ok"


def test_two_failures_stop_there(night_cfg, get_fake, fake_adapter):
    fake_adapter.results = [("failed", ""), ("failed", ""), ("ok", "never reached")]
    outcome = run(night_cfg, get_fake)
    assert len(fake_adapter.calls) == 2  # never three
    assert [r.status for r in outcome.results] == ["failed", "failed"]


def test_success_is_not_retried(night_cfg, get_fake, fake_adapter):
    fake_adapter.results = [("ok", "- LOW a.py:1 — x")]
    run(night_cfg, get_fake)
    assert len(fake_adapter.calls) == 1


def test_retry_is_skipped_when_it_would_breach_budget(
    tmp_path, project_dir, get_fake, fake_adapter
):
    cfg = build_config(tmp_path, project_dir, windows=["00:00-06:00"], max_day=1)
    fake_adapter.results = [("failed", ""), ("ok", "would cost a 2nd run")]
    ledger = Ledger(tmp_path / "ledger.json")

    outcome = run(cfg, get_fake, ledger=ledger)
    # The first attempt used the only run available; the retry must not happen.
    assert len(fake_adapter.calls) == 1
    assert [r.status for r in outcome.results] == ["failed"]
    assert ledger.count("claude_code", "2026-07-14") == 1


def test_an_adapter_exception_becomes_a_failed_result(night_cfg, get_fake, fake_adapter):
    fake_adapter.results = [RuntimeError("kaboom"), RuntimeError("kaboom")]
    outcome = run(night_cfg, get_fake)
    assert outcome.ran is True
    assert outcome.results[0].status == "failed"
    assert "kaboom" in outcome.results[0].detail


def test_a_stub_adapter_fails_cleanly_rather_than_crashing(
    night_cfg, get_fake, fake_adapter
):
    fake_adapter.results = [
        NotImplementedError("the codex adapter is a documented stub"),
        NotImplementedError("the codex adapter is a documented stub"),
    ]
    outcome = run(night_cfg, get_fake)
    assert outcome.results[0].status == "failed"
    assert "documented stub" in outcome.results[0].detail


# ---- provider selection ----------------------------------------------


def test_unavailable_provider_is_skipped_with_a_reason(night_cfg, get_fake, fake_adapter):
    fake_adapter.is_available = False
    fake_adapter.unavailable_reason = "`claude` is not on PATH"
    outcome = run(night_cfg, get_fake)
    assert outcome.ran is False
    assert "not on PATH" in outcome.reason


def test_provider_flag_restricts_to_one(tmp_path, project_dir, fake_adapter):
    cfg = build_config(
        tmp_path,
        project_dir,
        windows=["00:00-06:00"],
        providers={"claude_code": {"enabled": True}, "codex": {"enabled": True}},
    )
    asked: list[str] = []

    def get(name):
        asked.append(name)
        fake_adapter.name = name
        return fake_adapter

    outcome = scheduler.run_once(
        cfg,
        now=AT_NIGHT,
        provider="codex",
        ledger=Ledger(tmp_path / "l.json"),
        queue=Queue(tmp_path / "q.json"),
        get_adapter=get,
    )
    assert outcome.ran is True
    assert asked == ["codex"]


def test_unknown_provider_flag_is_refused(night_cfg, get_fake):
    outcome = run(night_cfg, get_fake, provider="nope")
    assert outcome.ran is False
    assert "not enabled" in outcome.reason


def test_falls_through_to_the_second_provider(tmp_path, project_dir):
    cfg = build_config(
        tmp_path,
        project_dir,
        windows=["00:00-06:00"],
        providers={"claude_code": {"enabled": True}, "codex": {"enabled": True}},
    )
    broken = FakeAdapter(name="claude_code", is_available=False)
    working = FakeAdapter(name="codex")

    outcome = scheduler.run_once(
        cfg,
        now=AT_NIGHT,
        ledger=Ledger(tmp_path / "l.json"),
        queue=Queue(tmp_path / "q.json"),
        get_adapter=lambda n: {"claude_code": broken, "codex": working}[n],
    )
    assert outcome.ran is True
    assert len(working.calls) == 1
    assert outcome.results[-1].provider == "codex"


# ---- work selection --------------------------------------------------


def test_consecutive_runs_rotate_through_pairs(tmp_path, project_dir, get_fake, fake_adapter):
    cfg = build_config(
        tmp_path,
        project_dir,
        windows=["00:00-06:00"],
        tasks=["code_review", "deps_audit"],
    )
    ledger = Ledger(tmp_path / "ledger.json")
    queue = Queue(tmp_path / "queue.json")

    first = run(cfg, get_fake, ledger=ledger, queue=queue)
    second = run(cfg, get_fake, ledger=ledger, queue=queue)
    assert first.results[-1].task == "code_review"
    assert second.results[-1].task == "deps_audit"


def test_the_adapter_is_given_the_project_dir_and_timeout(night_cfg, get_fake, fake_adapter, project_dir):
    run(night_cfg, get_fake)
    call = fake_adapter.calls[0]
    assert call["project_dir"] == project_dir
    assert call["timeout_s"] == 600
    assert "read" in call["prompt"].lower()


def test_a_missing_project_dir_fails_the_run_rather_than_crashing(
    tmp_path, project_dir, get_fake, fake_adapter
):
    cfg = build_config(tmp_path, project_dir, windows=["00:00-06:00"])
    shutil.rmtree(project_dir)
    outcome = run(cfg, get_fake)
    assert outcome.results[-1].status == "failed"
    assert "does not exist" in outcome.results[-1].detail
    assert fake_adapter.calls == []


def test_a_missing_prompt_template_fails_the_run(tmp_path, project_dir, get_fake, fake_adapter):
    cfg = build_config(tmp_path, project_dir, windows=["00:00-06:00"], tasks=["nonexistent"])
    outcome = run(cfg, get_fake)
    assert outcome.results[-1].status == "failed"
    assert "no prompt template" in outcome.results[-1].detail
    assert fake_adapter.calls == []


def test_results_are_written_to_disk(night_cfg, get_fake, fake_adapter):
    fake_adapter.started_at = AT_NIGHT
    run(night_cfg, get_fake)
    stored = report.load_results(night_cfg, AT_NIGHT.date())
    assert len(stored) == 1
    assert stored[0].status == "ok"
    assert stored[0].task == "code_review"


def test_scheduler_overwrites_adapter_bookkeeping(night_cfg, get_fake, fake_adapter):
    # The adapter doesn't know the task name; the scheduler owns that.
    outcome = run(night_cfg, get_fake)
    result = outcome.results[-1]
    assert result.task == "code_review"
    assert result.project == "acme-api"
    assert result.provider == "claude_code"


def test_ledger_is_pruned_on_every_run(night_cfg, get_fake, tmp_path):
    ledger = Ledger(tmp_path / "ledger.json")
    ledger.increment("claude_code", datetime(2026, 1, 1))
    run(night_cfg, get_fake, ledger=ledger)
    assert ledger.count("claude_code", "2026-01-01") == 0


# ---- event logs -------------------------------------------------------


def test_a_run_publishes_an_event_log(night_cfg, get_fake):
    # cron's runs are the ones worth watching, and cron passes no renderer —
    # so publishing must not depend on anyone being attached.
    run(night_cfg, get_fake)

    logs = events.recent_logs()
    assert len(logs) == 1
    payloads = events.read(logs[0])
    assert payloads[0]["kind"] == "meta"
    assert payloads[0]["task"] == "code_review"
    assert payloads[-1]["kind"] == "end"
    assert payloads[-1]["status"] == "ok"


def test_the_event_log_records_the_real_outcome(night_cfg, get_fake, fake_adapter):
    # Both attempts fail, so every log written should say so.
    fake_adapter.results = [("failed", ""), ("failed", "")]
    run(night_cfg, get_fake)

    logs = events.recent_logs()
    assert len(logs) == 2
    assert {events.read(p)[-1]["status"] for p in logs} == {"failed"}


def test_a_retry_gets_a_second_log(night_cfg, get_fake, fake_adapter):
    fake_adapter.results = [("failed", ""), ("ok", "- LOW a.py:1 — x")]
    run(night_cfg, get_fake)

    assert len(events.recent_logs()) == 2


def test_a_broken_renderer_does_not_fail_the_run(night_cfg, get_fake):
    def explode(event):
        raise RuntimeError("renderer bug")

    outcome = run(night_cfg, get_fake, on_event=explode)

    assert [r.status for r in outcome.results] == ["ok"]
