from __future__ import annotations

import json
import os
import time

import pytest

from nightshift.lock import Lock, LockBusy


def test_acquire_creates_and_release_removes(tmp_path):
    lock = Lock(tmp_path / "lock", timeout_s=600)
    lock.acquire()
    assert (tmp_path / "lock").exists()
    lock.release()
    assert not (tmp_path / "lock").exists()


def test_second_acquire_is_refused(tmp_path):
    path = tmp_path / "lock"
    first = Lock(path, timeout_s=600)
    first.acquire()
    with pytest.raises(LockBusy, match="in progress"):
        Lock(path, timeout_s=600).acquire()
    first.release()


def test_release_after_refusal_lets_the_next_run_in(tmp_path):
    path = tmp_path / "lock"
    first = Lock(path, timeout_s=600)
    first.acquire()
    first.release()
    second = Lock(path, timeout_s=600)
    second.acquire()  # must not raise
    second.release()


def test_context_manager_releases_on_exception(tmp_path):
    path = tmp_path / "lock"
    with pytest.raises(RuntimeError):
        with Lock(path, timeout_s=600):
            raise RuntimeError("boom")
    assert not path.exists()


def test_stale_lock_is_broken_and_reacquired(tmp_path):
    path = tmp_path / "lock"
    # A run that was killed 3× the timeout ago and never cleaned up.
    stale_age = time.time() - (600 * 3)
    path.write_text(json.dumps({"pid": 999999, "acquired_at": stale_age}), encoding="utf-8")

    lock = Lock(path, timeout_s=600)
    assert lock.is_stale() is True
    lock.acquire()  # must not raise
    assert lock.read().pid != 999999
    lock.release()


def test_lock_just_under_stale_threshold_still_blocks(tmp_path):
    path = tmp_path / "lock"
    # 2× timeout is the threshold; a hair under it is still a live run.
    recent = time.time() - (600 * 2) + 30
    path.write_text(json.dumps({"pid": 999999, "acquired_at": recent}), encoding="utf-8")
    lock = Lock(path, timeout_s=600)
    assert lock.is_stale() is False
    with pytest.raises(LockBusy):
        lock.acquire()


def test_stale_threshold_scales_with_configured_timeout(tmp_path):
    path = tmp_path / "lock"
    age = time.time() - 700
    path.write_text(json.dumps({"pid": 1, "acquired_at": age}), encoding="utf-8")

    # A 600s-timeout run goes stale at 1200s — 700s is still live.
    assert Lock(path, timeout_s=600).is_stale() is False
    # A 60s-timeout run goes stale at 120s — 700s is long abandoned.
    assert Lock(path, timeout_s=60).is_stale() is True


def test_stale_threshold_sizes_for_every_attempt(tmp_path):
    path = tmp_path / "lock"
    path.write_text(
        json.dumps({"pid": 999999, "acquired_at": time.time() - 1400}), encoding="utf-8"
    )

    # One attempt goes stale at 2 × 600s — 1400s is abandoned.
    assert Lock(path, timeout_s=600, attempts=1).is_stale() is True
    # Two attempts go stale at 2 × 2 × 600s — the same lock is a slow run.
    assert Lock(path, timeout_s=600, attempts=2).is_stale() is False


def test_a_holder_that_used_its_whole_retry_budget_is_still_live(tmp_path):
    """The regression `attempts` exists to prevent.

    A holder that spent every attempt at its full timeout is as old as a healthy
    run can legitimately get. Size the threshold for one attempt and that run
    lands *on* it — any overhead tips it past, its live lock is broken, and a
    second run starts alongside it.
    """
    path = tmp_path / "lock"
    lock = Lock(path, timeout_s=600, attempts=2)
    overran_but_healthy = time.time() - (lock.max_run_s + 60)
    path.write_text(
        json.dumps({"pid": 999999, "acquired_at": overran_but_healthy}), encoding="utf-8"
    )

    assert lock.is_stale() is False
    with pytest.raises(LockBusy):
        lock.acquire()


def test_attempts_below_one_cannot_collapse_the_threshold(tmp_path):
    """A bad `attempts` must not make every lock instantly stale.

    Zero would zero out `max_run_s`, so any lock at all would look abandoned and
    the lock would stop excluding anything.
    """
    path = tmp_path / "lock"
    path.write_text(
        json.dumps({"pid": 999999, "acquired_at": time.time() - 30}), encoding="utf-8"
    )
    lock = Lock(path, timeout_s=600, attempts=0)

    assert lock.attempts == 1
    assert lock.stale_after_s == 1200
    assert lock.is_stale() is False


def test_unreadable_lock_falls_back_to_mtime_and_can_go_stale(tmp_path):
    path = tmp_path / "lock"
    path.write_text("this is not json", encoding="utf-8")
    import os

    old = time.time() - (600 * 3)
    os.utime(path, (old, old))

    lock = Lock(path, timeout_s=600)
    assert lock.is_stale() is True
    lock.acquire()  # a garbage lock must not wedge nightshift forever
    lock.release()


def test_fresh_unreadable_lock_still_blocks(tmp_path):
    path = tmp_path / "lock"
    path.write_text("this is not json", encoding="utf-8")
    with pytest.raises(LockBusy):
        Lock(path, timeout_s=600).acquire()


def test_release_is_idempotent_and_never_steals(tmp_path):
    path = tmp_path / "lock"
    holder = Lock(path, timeout_s=600)
    holder.acquire()

    # A Lock that never acquired must not delete someone else's lockfile.
    other = Lock(path, timeout_s=600)
    other.release()
    assert path.exists()

    holder.release()
    holder.release()
    assert not path.exists()


def test_release_does_not_delete_a_lock_that_was_broken_and_retaken(tmp_path):
    # The overrun path: a run exceeds the stale threshold, a later tick breaks
    # its lock and starts working, and then the slow run finishes and tidies up
    # — deleting the *new* owner's lockfile and letting a third run join a live
    # one. The lock's own cleanup defeating the lock.
    path = tmp_path / "lock"
    # timeout_s=0 makes any elapsed time stale, so the test need not wait 20min.
    slow = Lock(path, timeout_s=0)
    slow.acquire()
    time.sleep(0.02)

    newcomer = Lock(path, timeout_s=0)
    newcomer.acquire()

    slow.release()

    assert path.exists(), "release() deleted a lock it no longer owned"
    assert newcomer.read().pid == os.getpid()


def test_the_new_owner_can_still_release_normally(tmp_path):
    path = tmp_path / "lock"
    slow = Lock(path, timeout_s=0)
    slow.acquire()
    time.sleep(0.02)
    newcomer = Lock(path, timeout_s=0)
    newcomer.acquire()

    slow.release()
    newcomer.release()

    assert not path.exists()


def test_a_pid_alone_cannot_prove_ownership(tmp_path):
    # Both locks live in this process and so share a pid; only the acquisition
    # stamp distinguishes them. A pid check would have called this ours.
    path = tmp_path / "lock"
    first = Lock(path, timeout_s=0)
    first.acquire()
    time.sleep(0.02)
    second = Lock(path, timeout_s=0)
    second.acquire()

    assert first.read().pid == os.getpid()
    assert not first._is_ours(first.read())
    assert second._is_ours(second.read())


def test_release_tolerates_a_lock_that_vanished(tmp_path):
    path = tmp_path / "lock"
    lock = Lock(path, timeout_s=600)
    lock.acquire()
    path.unlink()

    lock.release()  # must not raise
    assert not path.exists()


def test_read_returns_none_when_absent(tmp_path):
    assert Lock(tmp_path / "nope", timeout_s=600).read() is None
    assert Lock(tmp_path / "nope", timeout_s=600).is_stale() is False
