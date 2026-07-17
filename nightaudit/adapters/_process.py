"""Process machinery shared by adapters that drive a streaming CLI.

Extracted when the Codex adapter arrived. Both it and Claude Code spawn a CLI,
read newline-delimited JSON off its stdout, and must guarantee the child tree
dies at the deadline instead of living on holding provider quota while cron sits
on the lock.

That guarantee is the reason this module exists rather than a second copy of it.
Getting it right took two fixes — a deadline disarmed before the child was
reaped (13c0d3f) and a kill aimed at a pid that could already have been reused
— and a duplicate would have needed both, twice, discovered twice.

Nothing here knows what any event *means*. Translating lines into findings is
each adapter's job; this only promises the process starts, is read to the end,
and is dead when we return.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from nightaudit.adapters.base import Event, OnEvent

#: Slack given to a process that should already be dying, before we conclude the
#: deadline timer failed and kill the tree ourselves.
REAP_GRACE_S = 10


@dataclass
class StreamOutcome:
    """How a streamed run ended. Says nothing about what it produced."""

    returncode: int
    timed_out: bool
    stderr_lines: list[str] = field(default_factory=list)

    @property
    def stderr_head(self) -> str:
        """First line of stderr, or an exit-code summary — for ``detail``."""
        stderr = "\n".join(self.stderr_lines).strip()
        if stderr:
            return stderr.splitlines()[0]
        return f"exit {self.returncode}"


def parse_line(line: str) -> dict | None:
    """One NDJSON event, or ``None`` for anything we can't read.

    A malformed line is skipped rather than fatal: the stream is telemetry, and
    the run's outcome must not hinge on our parsing every frame of it.
    """
    line = line.strip()
    if not line:
        return None
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


#: The token counters a provider may put in a ``usage`` object. Both CLIs use
#: ``input_tokens``/``output_tokens``; Claude adds the two cache counters, which
#: are real tokens the model processed and so belong in an honest total. A
#: provider that omits a key simply contributes zero for it.
_USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def tokens_from_usage(usage: object) -> int:
    """Sum the token counts in a provider's ``usage`` object.

    Defensive on purpose: usage is telemetry riding on the same stream as the
    findings, and a malformed or partial frame must never turn a billed run into
    an exception. Anything unreadable counts as zero.
    """
    if not isinstance(usage, dict):
        return 0
    total = 0
    for key in _USAGE_KEYS:
        value = usage.get(key)
        if isinstance(value, bool):  # bool is an int subclass; not a token count
            continue
        if isinstance(value, (int, float)):
            total += int(value)
    return total


def clip(text: str, limit: int) -> str:
    text = str(text or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def format_input(value: object, limit: int = 60) -> str:
    """Render tool input as ``key: value``, short enough for one line."""
    if not isinstance(value, dict) or not value:
        return ""
    return ", ".join(f"{k}: {clip(v, limit)}" for k, v in list(value.items())[:2])


def summarize(content: object, limit: int = 70) -> str:
    """One line describing a tool result."""
    if isinstance(content, list):
        content = " ".join(
            str(b.get("text", "")) for b in content if isinstance(b, dict)
        )
    text = str(content or "").strip()
    if not text:
        return ""
    lines = text.splitlines()
    first = lines[0]
    if len(first) > limit:
        first = first[: limit - 1] + "…"
    if len(lines) > 1:
        first += f"  (+{len(lines) - 1} lines)"
    return first


def emit(on_event: OnEvent, event: Event) -> None:
    """A broken renderer must not fail a run that has already been billed."""
    try:
        on_event(event)
    except Exception:  # noqa: BLE001 - the callback is the caller's problem
        pass


def _drain(stream, sink: list[str]) -> None:
    if stream is None:
        return
    try:
        for line in stream:
            sink.append(line.rstrip("\n"))
    except (OSError, ValueError):
        pass


def kill_tree(proc: subprocess.Popen) -> None:
    """Kill the CLI and anything it spawned.

    ``start_new_session`` made it a process-group leader precisely so this can
    reach its children.
    """
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            proc.kill()
        except OSError:
            pass


def stream_ndjson(
    argv: list[str],
    cwd: Path,
    timeout_s: int,
    on_line: Callable[[dict], None],
) -> StreamOutcome:
    """Run ``argv``, feeding each NDJSON line on stdout to ``on_line``.

    Returns once the child is reaped. Raises ``FileNotFoundError`` / ``OSError``
    if it could not be started at all — the caller owns that story, since only it
    knows which binary was missing.

    ``on_line`` runs on this thread and must not raise.
    """
    proc = subprocess.Popen(
        argv,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        start_new_session=True,
    )

    timed_out = threading.Event()
    guard = threading.Lock()
    reaped = False

    def on_deadline() -> None:
        # The timer races the normal exit. Once the process has been waited for,
        # its pid can be reused — killing "it" would then SIGKILL an unrelated
        # process group.
        with guard:
            if reaped or proc.poll() is not None:
                return
            timed_out.set()
            kill_tree(proc)

    deadline = time.monotonic() + timeout_s
    timer = threading.Timer(timeout_s, on_deadline)
    timer.daemon = True
    timer.start()

    stderr_lines: list[str] = []
    drain = threading.Thread(target=_drain, args=(proc.stderr, stderr_lines), daemon=True)
    drain.start()

    try:
        for line in proc.stdout or ():
            payload = parse_line(line)
            if payload is not None:
                on_line(payload)
    finally:
        # The timer stays armed across the wait, because it is the only thing
        # that can end a child which closed stdout and then hung — an EOF here
        # does not mean the process is going to exit. Cancelling it before an
        # unbounded wait() left nothing to terminate such a run, and cron would
        # sit on the lock until someone noticed.
        try:
            proc.wait(timeout=max(deadline - time.monotonic(), 0) + REAP_GRACE_S)
        except subprocess.TimeoutExpired:
            # The timer should have fired by now; it did not, so do its job.
            kill_tree(proc)
            try:
                proc.wait(timeout=REAP_GRACE_S)
            except subprocess.TimeoutExpired:
                pass
        timer.cancel()
        with guard:
            # Only now may on_deadline be told to keep its hands off: the process
            # is reaped and its pid is free to be reused.
            reaped = True
        drain.join(timeout=2)
        # Close the pipes rather than leaving them to the collector.
        for pipe in (proc.stdout, proc.stderr):
            try:
                if pipe is not None:
                    pipe.close()
            except OSError:
                pass

    return StreamOutcome(
        returncode=proc.returncode,
        timed_out=timed_out.is_set(),
        stderr_lines=stderr_lines,
    )
