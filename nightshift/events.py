"""Append-only event logs, so a run can be watched from another process.

cron starts each run in its own process, so a dashboard opened at 2am has no
callback to subscribe to and no way back into a run that began an hour ago.
Every run therefore publishes what it sees to a file as it goes, and
``nightshift watch`` tails it.

Nothing here is load-bearing. The digest is built from stored results, never
from these logs; a run whose event log could not be written is still a correct
run, and deleting the whole directory loses nothing but the view.

The files hold tool inputs and snippets of the repo being reviewed, so they are
created ``0600`` under a ``0700`` directory rather than left world-readable.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

from nightshift.adapters.base import Event, RunResult
from nightshift.config import state_dir

#: Event logs older than this are pruned on the next run.
KEEP_DAYS = 14

#: How long a reader waits before checking a file for new lines again.
POLL_S = 0.2

#: A log with no new line for this long is treated as abandoned. Its writer
#: was killed, or wedged, and no ``end`` is ever coming — a reader that waits
#: for one would block forever. Comfortably longer than the default run
#: timeout so a slow-but-live run is never mistaken for a dead one.
STALE_AFTER_S = 900.0


def events_dir() -> Path:
    return state_dir() / "events"


def day_dir(on: date) -> Path:
    return events_dir() / on.isoformat()


def _slug(text: str) -> str:
    keep = [c if (c.isalnum() or c in "-_") else "-" for c in text.strip().lower()]
    return "".join(keep).strip("-") or "unknown"


def log_path(project: str, task: str, started: datetime, attempt: int = 1) -> Path:
    stem = f"{_slug(project)}-{_slug(task)}-{started.strftime('%H%M%S')}"
    if attempt > 1:
        stem += f"-retry{attempt - 1}"
    return day_dir(started.date()) / f"{stem}.ndjson"


class EventLog:
    """One run's events, appended as newline-delimited JSON.

    Every method swallows its own errors. A full disk or a read-only home must
    cost the view, not the run.
    """

    def __init__(self, path: Path):
        self.path = path
        self._fh = None

    # ---- writing ------------------------------------------------------

    @classmethod
    def open(
        cls,
        project: str,
        task: str,
        provider: str,
        started: datetime,
        attempt: int = 1,
    ) -> EventLog:
        log = cls(log_path(project, task, started, attempt))
        try:
            # mkdir's mode applies to the leaf only, so events/ itself would
            # otherwise be born with whatever the umask says.
            events_dir().mkdir(parents=True, exist_ok=True, mode=0o700)
            log.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(str(log.path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            log._fh = os.fdopen(fd, "a", encoding="utf-8")
        except OSError:
            log._fh = None
            return log
        log._append(
            {
                "kind": "meta",
                "project": project,
                "task": task,
                "provider": provider,
                "started_at": started.isoformat(),
                "attempt": attempt,
            }
        )
        return log

    def _append(self, payload: dict) -> None:
        if self._fh is None:
            return
        payload.setdefault("t", datetime.now().isoformat(timespec="milliseconds"))
        try:
            # One json.dumps per line, flushed but not fsynced: a reader in
            # another process sees it immediately, and a lost tail on a crash
            # costs nothing the result file does not already hold.
            self._fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self._fh.flush()
        except (OSError, ValueError, TypeError):
            self.close_quietly()

    def write(self, event: Event) -> None:
        """Record one adapter event. Safe to pass straight to ``on_event``."""
        self._append(
            {
                "kind": event.kind,
                "text": event.text,
                "tool": event.tool,
                "detail": event.detail,
            }
        )

    def finish(self, result: RunResult, findings: int = 0) -> None:
        self._append(
            {
                "kind": "end",
                "status": result.status,
                "duration_s": round(result.duration_s, 3),
                "detail": result.detail,
                "findings": findings,
            }
        )
        self.close_quietly()

    def close_quietly(self) -> None:
        fh, self._fh = self._fh, None
        if fh is None:
            return
        try:
            fh.close()
        except OSError:
            pass


# ---- reading ----------------------------------------------------------


def parse(line: str) -> dict | None:
    """One event, or ``None`` for a blank, torn, or unreadable line."""
    line = line.strip()
    if not line:
        return None
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def read(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [p for p in (parse(line) for line in text.splitlines()) if p is not None]


def is_finished(path: Path) -> bool:
    events = read(path)
    return bool(events) and events[-1].get("kind") == "end"


def is_stale(path: Path, stale_after_s: float = STALE_AFTER_S) -> bool:
    """Has nothing been appended to ``path`` for a long time?

    An interrupted run leaves a log with no ``end``; without this a reader
    cannot tell it from a run still in flight, and waits on it forever.
    """
    try:
        return (time.time() - path.stat().st_mtime) > stale_after_s
    except OSError:
        return True


def logs_for(on: date) -> list[Path]:
    try:
        return sorted(day_dir(on).glob("*.ndjson"))
    except OSError:
        return []


def recent_logs(limit: int = 20) -> list[Path]:
    """Newest run logs first, across every day we still keep.

    Ordered by mtime rather than by name: a log's name starts with the project
    slug, so sorting on it groups by project and only then by clock — which is
    not "recent" at all once two projects are registered.
    """
    try:
        found = list(events_dir().rglob("*.ndjson"))
    except OSError:
        return []

    def when(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    found.sort(key=when, reverse=True)
    return found[:limit]


def follow(
    path: Path,
    stop_after_end: bool = True,
    stale_after_s: float = STALE_AFTER_S,
) -> Iterator[dict]:
    """Yield events from ``path``, waiting for more until the run ends.

    Returns on the ``end`` event, or once the log has gone quiet for
    ``stale_after_s``. Waiting only for ``end`` would hang forever on the log
    of a run that was killed, and take the whole watcher down with it.

    A partial final line — the writer was mid-append — is left alone and
    retried rather than parsed as garbage.
    """
    try:
        fh = path.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return
    try:
        buffer = ""
        last_line_at = time.monotonic()
        while True:
            chunk = fh.readline()
            if not chunk:
                if time.monotonic() - last_line_at > stale_after_s:
                    return
                time.sleep(POLL_S)
                continue
            last_line_at = time.monotonic()
            buffer += chunk
            if not buffer.endswith("\n"):
                # Torn write: wait for the writer to finish the line.
                continue
            payload = parse(buffer)
            buffer = ""
            if payload is None:
                continue
            yield payload
            if stop_after_end and payload.get("kind") == "end":
                return
    finally:
        try:
            fh.close()
        except OSError:
            pass


# ---- housekeeping -----------------------------------------------------


def prune(keep_days: int = KEEP_DAYS, today: date | None = None) -> int:
    """Delete event logs older than ``keep_days``. Returns days removed."""
    today = today or date.today()
    removed = 0
    try:
        days = [d for d in events_dir().iterdir() if d.is_dir()]
    except OSError:
        return 0
    for directory in days:
        try:
            on = date.fromisoformat(directory.name)
        except ValueError:
            continue  # not ours; leave it alone
        if (today - on).days <= keep_days:
            continue
        try:
            for child in directory.iterdir():
                child.unlink()
            directory.rmdir()
            removed += 1
        except OSError:
            continue
    return removed
