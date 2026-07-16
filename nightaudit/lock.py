"""A cooperative lockfile so two cron ticks never run at once."""

from __future__ import annotations

import errno
import json
import logging
import os
import time as _time
from dataclasses import dataclass
from pathlib import Path

from nightaudit.config import state_dir

log = logging.getLogger("nightaudit")

#: How far past the longest legitimate run a lock may live before we presume
#: its holder died. This multiplies the *whole* run budget — every attempt at
#: its full timeout — and must exceed it rather than equal it: a threshold a
#: healthy run can reach is a live lock waiting to be broken.
STALE_MULTIPLIER = 2


def lock_path() -> Path:
    return state_dir() / "lock"


class LockBusy(Exception):
    """Another nightaudit run holds the lock."""


@dataclass
class LockInfo:
    pid: int
    acquired_at: float

    @property
    def age_s(self) -> float:
        return max(0.0, _time.time() - self.acquired_at)


class Lock:
    """An exclusive lock built on ``O_CREAT | O_EXCL``.

    Stale locks — left behind by a run that was killed before it could clean up
    — are broken automatically once they outlive :attr:`stale_after_s`.

    That threshold is measured against the longest a healthy holder can take,
    which is every attempt running to its full timeout, not one. This docstring
    used to say "twice the run timeout, strictly longer than any healthy run can
    survive"; with two attempts allowed and a multiplier of two those were the
    same number, so a healthy run that used its whole budget landed exactly on
    the threshold and any overhead put it past. Its live lock would be broken
    and a second run would start beside it — the one thing the lock exists to
    prevent.

    Callers that retry must therefore say so via ``attempts``, or the lock will
    size the threshold for a single run. Callers that do other work under the
    lock — running a project's configured checks, say — must declare it via
    ``extra_s`` for the same reason.
    """

    def __init__(
        self,
        path: Path | None = None,
        timeout_s: int = 600,
        attempts: int = 1,
        extra_s: float = 0,
    ):
        self.path = path or lock_path()
        self.timeout_s = timeout_s
        #: Time the holder may spend under the lock on work that is not an
        #: adapter attempt — currently the project's configured checks. Same
        #: hazard as ``attempts``: work the threshold does not know about is
        #: exactly what makes a healthy holder look dead.
        self.extra_s = max(float(extra_s), 0.0)
        #: Total tries the holder may make, each up to ``timeout_s`` — the first
        #: one included, not retries stacked on top of it. ``attempts=2`` is one
        #: try and one retry, matching the scheduler's ``range(1, MAX_ATTEMPTS + 1)``.
        #: Read as "retries" it would double the threshold it was meant to set.
        self.attempts = max(int(attempts), 1)
        self._held = False
        #: Stamp we wrote when we took the lock. Together with the pid it is
        #: what makes a lockfile *ours* rather than merely present — see
        #: :meth:`release`. A pid alone cannot say: two Lock objects in one
        #: process share one, and the OS reuses pids.
        self._acquired_at: float | None = None

    @property
    def max_run_s(self) -> float:
        """The longest a healthy holder can legitimately take."""
        return self.timeout_s * self.attempts + self.extra_s

    @property
    def stale_after_s(self) -> float:
        return self.max_run_s * STALE_MULTIPLIER

    def read(self) -> LockInfo | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return LockInfo(pid=int(data["pid"]), acquired_at=float(data["acquired_at"]))
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, KeyError, ValueError, OSError, TypeError):
            # An unreadable lock is indistinguishable from an abandoned one; fall
            # back to its mtime so it can still go stale and be broken.
            try:
                return LockInfo(pid=-1, acquired_at=self.path.stat().st_mtime)
            except OSError:
                return None

    def is_stale(self, info: LockInfo | None = None) -> bool:
        info = info or self.read()
        return info is not None and info.age_s > self.stale_after_s

    def _write(self) -> None:
        acquired_at = _time.time()
        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"pid": os.getpid(), "acquired_at": acquired_at}, fh)
        self._acquired_at = acquired_at

    def _is_ours(self, info: LockInfo | None) -> bool:
        """Is the lockfile on disk the one *we* wrote?

        The pid cannot settle this alone: two Lock objects in one process share
        it, and the OS reuses pids. The acquisition stamp can — nothing else
        wrote that float.
        """
        if info is None or self._acquired_at is None:
            return False
        return info.pid == os.getpid() and info.acquired_at == self._acquired_at

    def acquire(self) -> None:
        """Take the lock, breaking it first if it has gone stale.

        Raises :class:`LockBusy` if a live run holds it.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._write()
            self._held = True
            return
        except FileExistsError:
            pass
        except OSError as exc:  # pragma: no cover - platform dependent
            if exc.errno != errno.EEXIST:
                raise

        info = self.read()
        if info is None:
            # Vanished between the failed create and the read — retry once.
            try:
                self._write()
                self._held = True
                return
            except FileExistsError:
                raise LockBusy("another nightaudit run just took the lock") from None

        if not self.is_stale(info):
            raise LockBusy(
                f"another nightaudit run is in progress (pid {info.pid}, "
                f"started {info.age_s:.0f}s ago)"
            )

        self.break_stale()
        try:
            self._write()
            self._held = True
        except FileExistsError:
            raise LockBusy("another nightaudit run just took the lock") from None

    def break_stale(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def release(self) -> None:
        """Give up the lock, but only if the lockfile is still ours.

        A run that overran had its lock broken as stale, and someone else is
        working now. Unlinking on the way out would delete *their* lockfile and
        let a third run start alongside a live one — the exact thing the lock
        exists to prevent, brought about by the cleanup rather than the overrun.
        """
        if not self._held:
            return
        self._held = False

        if not self._is_ours(self.read()):
            log.debug("not releasing %s — it is no longer our lock", self.path)
            return

        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def __enter__(self) -> Lock:
        self.acquire()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()
