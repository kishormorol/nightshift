"""Running the user's own commands against a project.

This is the one part of nightaudit that executes rather than reads. Everything
else here hands a prompt to an AI CLI that is held read-only by its own sandbox;
a check is a command the user wrote, and it runs with the user's permissions and
may do whatever they told it to. ``pytest`` writes ``.pytest_cache/``. That is
not a leak in the sandbox — it is outside the sandbox by design, and the promise
in SPEC.md is worded to say exactly that.

Two deliberate limits:

**No shell.** The command is ``shlex.split`` into an argv and executed directly,
so ``&&``, pipes, globs and ``$(...)`` are not interpreted — ``run: rm -rf $HOME``
passes the literal string ``$HOME``. This is not a security boundary (anyone who
can write your config can put a program name in it) but it does mean a check
does only the one thing it appears to do. A user who wants a pipeline can point
a check at a script.

**Never fails a run.** A check that explodes is a finding, not an exception. The
review is the product; a broken command in the config must not cost the user the
AI run they were waiting for.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from nightaudit.config import Check, Project

log = logging.getLogger("nightaudit")

#: Colour codes and cursor moves. Plenty of tools colour their output even with
#: stdout on a pipe — pytest and ruff among them — and the digest is markdown in
#: a file, where an escape sequence renders as `[33m` and nothing else.
_ANSI = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

#: How much of a check's output to keep. Enough to see a pytest summary or the
#: first few ruff violations; not so much that a chatty command drowns the
#: digest it is reported in.
MAX_OUTPUT_LINES = 20
MAX_OUTPUT_CHARS = 4000

#: ``pass`` and ``fail`` are the command's own verdict, by exit code. ``timeout``
#: and ``error`` are ours: it never finished, or it never started.
CheckStatus = str


@dataclass
class CheckResult:
    project: str
    name: str
    command: str
    status: CheckStatus
    started_at: datetime
    duration_s: float
    #: ``None`` when the command never produced one — it timed out, or the
    #: program could not be found at all.
    exit_code: int | None = None
    output: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "pass"

    def to_dict(self) -> dict:
        return {
            "project": self.project,
            "name": self.name,
            "command": self.command,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "duration_s": round(self.duration_s, 3),
            "exit_code": self.exit_code,
            "output": self.output,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> CheckResult:
        return cls(
            project=raw["project"],
            name=raw["name"],
            command=raw["command"],
            status=raw["status"],
            started_at=datetime.fromisoformat(raw["started_at"]),
            duration_s=float(raw["duration_s"]),
            exit_code=raw.get("exit_code"),
            output=raw.get("output", ""),
        )


def tail(text: str) -> str:
    """The last few lines, stripped of ANSI — where a command says what broke."""
    if not text:
        return ""
    text = _ANSI.sub("", text)
    lines = text.strip().splitlines()
    clipped = lines[-MAX_OUTPUT_LINES:]
    if len(lines) > MAX_OUTPUT_LINES:
        clipped.insert(0, f"… {len(lines) - MAX_OUTPUT_LINES} earlier lines omitted")
    out = "\n".join(clipped)
    if len(out) > MAX_OUTPUT_CHARS:
        out = out[-MAX_OUTPUT_CHARS:]
        out = "… truncated\n" + out[out.index("\n") + 1 :] if "\n" in out else out
    return out


def run_check(check: Check, cwd: Path, now: datetime | None = None) -> CheckResult:
    """Run one check. Returns a result for every outcome; raises for none."""
    started = now or datetime.now()

    def finish(status: str, exit_code: int | None, output: str) -> CheckResult:
        return CheckResult(
            project="",  # stamped by the caller, which knows the project
            name=check.name,
            command=check.run,
            status=status,
            started_at=started,
            duration_s=(datetime.now() - started).total_seconds(),
            exit_code=exit_code,
            output=tail(output),
        )

    try:
        proc = subprocess.run(
            check.argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=check.timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        # Whatever it managed to say before we killed it is the best clue as to
        # where it hung, so it is kept rather than thrown away.
        partial = _decode(exc.stdout) + _decode(exc.stderr)
        return finish("timeout", None, partial or f"no output in {check.timeout_s}s")
    except FileNotFoundError:
        return finish("error", None, f"{check.argv[0]}: command not found")
    except OSError as exc:
        return finish("error", None, f"could not run {check.argv[0]}: {exc}")

    output = (proc.stdout or "") + (proc.stderr or "")
    return finish("pass" if proc.returncode == 0 else "fail", proc.returncode, output)


def _decode(value) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else value.decode("utf-8", "replace")


def run_checks(project: Project, now: datetime | None = None) -> list[CheckResult]:
    """Every check for a project, in config order.

    Later checks still run after an earlier one fails: the point is a report of
    what is broken, and stopping at the first would hide the rest of it.
    """
    results: list[CheckResult] = []
    for check in project.checks:
        log.info("check %s · %s", project.name, check.name)
        result = run_check(check, project.path, now)
        result.project = project.name
        results.append(result)
    return results


def budget_s(project: Project) -> int:
    """The longest a project's checks can legitimately take, all told.

    The scheduler hands this to the lock. Work done under the lock that the lock
    does not know about is what makes a healthy holder look dead — see the note
    on ``Lock.stale_after_s``.
    """
    return sum(check.timeout_s for check in project.checks)
