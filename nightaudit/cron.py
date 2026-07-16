"""Crontab entries for the two scheduled commands.

nightaudit has no daemon: cron calls ``run`` hourly and the command decides for
itself whether to act.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

MARKER = "# nightaudit (managed — edit via `nightaudit init`)"
END_MARKER = "# end nightaudit"

HOURLY_RUN = "0 * * * *"
DAILY_DIGEST = "30 7 * * *"


def executable() -> str:
    """Absolute path to the installed ``nightaudit`` entry point."""
    found = shutil.which("nightaudit")
    if found:
        return found
    # Running from a source checkout or a venv that isn't on cron's PATH.
    return f"{Path(sys.executable)} -m nightaudit"


def entries(binary: str | None = None) -> list[str]:
    exe = binary or executable()
    return [
        f"{HOURLY_RUN} {exe} run >> /tmp/nightaudit-cron.log 2>&1",
        f"{DAILY_DIGEST} {exe} digest >> /tmp/nightaudit-cron.log 2>&1",
    ]


def block(binary: str | None = None) -> str:
    lines = [MARKER, *entries(binary), END_MARKER]
    return "\n".join(lines) + "\n"


def read_crontab() -> str:
    """Current crontab, or empty string if there isn't one."""
    try:
        proc = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout


def strip_block(existing: str) -> str:
    """Remove a previously installed nightaudit block."""
    out: list[str] = []
    skipping = False
    for line in existing.splitlines():
        if line.strip() == MARKER:
            skipping = True
            continue
        if skipping:
            if line.strip() == END_MARKER:
                skipping = False
            continue
        out.append(line)
    return "\n".join(out).strip("\n")


def merged(existing: str, binary: str | None = None) -> str:
    """The crontab that would result from installing our block."""
    base = strip_block(existing)
    parts = [p for p in (base, block(binary).rstrip("\n")) if p]
    return "\n".join(parts) + "\n"


def install(binary: str | None = None) -> None:
    """Replace the user's crontab with one containing our block.

    Raises ``RuntimeError`` if ``crontab`` isn't usable — the caller prints the
    lines so the user can paste them in by hand.
    """
    if shutil.which("crontab") is None:
        raise RuntimeError("`crontab` is not on PATH")
    new = merged(read_crontab(), binary)
    try:
        proc = subprocess.run(
            ["crontab", "-"], input=new, text=True, capture_output=True, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"could not run `crontab -`: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        raise RuntimeError(f"`crontab -` failed: {detail}")
