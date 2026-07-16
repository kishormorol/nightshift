"""Event logs: the file a run writes so another process can watch it.

``NIGHTAUDIT_HOME`` is redirected by an autouse fixture, so everything here
lands in a tmp dir.
"""

from __future__ import annotations

import os
import stat
import threading
import time
from datetime import date, datetime, timedelta

from nightaudit import events
from nightaudit.adapters.base import Event, RunResult


def a_result(status="ok", findings="- LOW a.py:1 — x", duration=1.5, detail=""):
    return RunResult(
        provider="claude_code",
        project="proj",
        task="code_review",
        status=status,
        findings_md=findings,
        started_at=datetime(2026, 7, 15, 3, 0, 0),
        duration_s=duration,
        detail=detail,
    )


def write_run(project="proj", task="code_review", started=None, kinds=("text",)):
    started = started or datetime(2026, 7, 15, 3, 0, 0)
    log = events.EventLog.open(project, task, "claude_code", started)
    for kind in kinds:
        log.write(Event(kind, text="hello", tool="Grep", detail="pattern: x"))
    log.finish(a_result(), findings=2)
    return log.path


# ---- writing ----------------------------------------------------------


def test_a_run_writes_meta_events_and_end():
    path = write_run(kinds=("text", "tool"))
    kinds = [e["kind"] for e in events.read(path)]

    assert kinds == ["meta", "text", "tool", "end"]


def test_the_meta_line_identifies_the_run():
    path = write_run()
    meta = events.read(path)[0]

    assert meta["project"] == "proj"
    assert meta["task"] == "code_review"
    assert meta["provider"] == "claude_code"


def test_the_end_line_carries_the_outcome():
    path = write_run()
    end = events.read(path)[-1]

    assert end["status"] == "ok"
    assert end["findings"] == 2


def test_logs_are_not_world_readable():
    # They quote the repo under review; the digest being 0644 was already a
    # finding, so a new file holding the same content should not repeat it.
    path = write_run()
    mode = stat.S_IMODE(path.stat().st_mode)

    assert mode == 0o600


def test_the_events_directory_is_private():
    # mkdir's mode applies to the leaf only, so events/ needs creating in its
    # own right or it inherits the umask.
    write_run()
    for directory in (events.events_dir(), events.day_dir(date(2026, 7, 15))):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700


def test_a_retry_gets_its_own_log():
    started = datetime(2026, 7, 15, 3, 0, 0)
    first = events.EventLog.open("proj", "t", "claude_code", started, attempt=1)
    second = events.EventLog.open("proj", "t", "claude_code", started, attempt=2)
    first.close_quietly()
    second.close_quietly()

    assert first.path != second.path
    assert "retry1" in second.path.name


def test_a_log_that_could_not_be_opened_is_inert(monkeypatch, tmp_path):
    # A read-only home must cost the view, not the run.
    def no_open(*args, **kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(events.os, "open", no_open)
    log = events.EventLog.open("proj", "t", "claude_code", datetime.now())

    assert log._fh is None
    log.write(Event("text", text="hi"))  # must not raise
    log.finish(a_result())


def test_a_handle_that_dies_mid_run_does_not_raise():
    log = events.EventLog.open("proj", "t", "claude_code", datetime.now())
    log._fh.close()  # the disk went away under us

    log.write(Event("text", text="hi"))  # must not raise
    log.finish(a_result())


# ---- reading ----------------------------------------------------------


def test_a_torn_line_is_skipped_not_fatal():
    path = write_run()
    with path.open("a") as fh:
        fh.write('{"kind": "text", "te')  # killed mid-append

    assert [e["kind"] for e in events.read(path)] == ["meta", "text", "end"]


def test_is_finished_distinguishes_a_killed_run():
    done = write_run()
    killed = events.EventLog.open("proj", "other", "claude_code", datetime.now())
    killed.close_quietly()  # died before it could write `end`

    assert events.is_finished(done)
    assert not events.is_finished(killed.path)


def test_recent_logs_are_ordered_by_time_not_project_name():
    # The filename starts with the project slug, so sorting by name orders by
    # project and only then by clock — "recent" has to mean recent.
    base = datetime(2026, 7, 15, 3, 0, 0)
    old = write_run(project="zebra", started=base)
    new = write_run(project="apple", started=base + timedelta(minutes=5))
    os.utime(old, (1_000_000, 1_000_000))
    os.utime(new, (2_000_000, 2_000_000))

    assert events.recent_logs()[0] == new


# ---- staleness --------------------------------------------------------


def test_an_old_unfinished_log_is_stale():
    path = write_run()
    os.utime(path, (1_000_000, 1_000_000))

    assert events.is_stale(path)


def test_a_fresh_log_is_not_stale():
    assert not events.is_stale(write_run())


def test_a_missing_log_is_stale():
    assert events.is_stale(events.events_dir() / "gone.ndjson")


def test_follow_gives_up_on_an_abandoned_log():
    # The bug this guards: a run killed mid-flight never writes `end`, and a
    # reader that waits only for `end` blocks forever — taking the watcher
    # with it, so the next real run is never shown.
    log = events.EventLog.open("proj", "t", "claude_code", datetime.now())
    log.write(Event("text", text="started"))
    log.close_quietly()  # SIGKILL: no `end` is ever coming

    seen = []
    done = threading.Event()

    def reader():
        for payload in events.follow(log.path, stale_after_s=0.3):
            seen.append(payload)
        done.set()

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()

    assert done.wait(timeout=5), "follow() never returned on an abandoned log"
    assert [e["kind"] for e in seen] == ["meta", "text"]


def test_follow_returns_on_end():
    path = write_run()
    seen = list(events.follow(path, stale_after_s=5))

    assert [e["kind"] for e in seen] == ["meta", "text", "end"]


def test_follow_picks_up_lines_appended_after_it_starts():
    log = events.EventLog.open("proj", "t", "claude_code", datetime.now())
    seen = []
    done = threading.Event()

    def reader():
        for payload in events.follow(log.path, stale_after_s=5):
            seen.append(payload)
        done.set()

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    time.sleep(0.3)  # reader reaches EOF and waits

    log.write(Event("tool", tool="Grep", detail="pattern: x"))
    log.finish(a_result())

    assert done.wait(timeout=5), "follow() did not see the appended lines"
    assert [e["kind"] for e in seen] == ["meta", "tool", "end"]


# ---- housekeeping -----------------------------------------------------


def test_prune_drops_days_past_the_window():
    write_run(started=datetime(2026, 7, 1, 3, 0, 0))
    write_run(started=datetime(2026, 7, 15, 3, 0, 0))

    removed = events.prune(keep_days=7, today=date(2026, 7, 15))

    assert removed == 1
    assert not events.day_dir(date(2026, 7, 1)).exists()
    assert events.day_dir(date(2026, 7, 15)).exists()


def test_prune_leaves_directories_that_are_not_ours():
    stray = events.events_dir() / "notes"
    stray.mkdir(parents=True)

    events.prune(keep_days=0, today=date(2026, 7, 15))

    assert stray.exists()


def test_prune_on_a_fresh_install_is_a_no_op():
    assert events.prune() == 0
