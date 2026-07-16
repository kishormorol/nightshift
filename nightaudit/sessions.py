"""Which AI CLI sessions were ours rather than a human's.

``last_human_use`` decides whether a human is at the keyboard by reading the
newest mtime under the CLI's own session directory — ``~/.claude/projects`` for
Claude Code, ``$CODEX_HOME/sessions`` for Codex. nightaudit's own runs write
their transcripts into that same directory — the same directory, not merely a
similar one — so without this every run would leave a fresh mtime that the next
cron tick reads as human activity, and nightaudit would gate itself out for
``idle_minutes`` after each run. It would put itself to sleep.

Filtering by project path cannot fix that: a human running the CLI inside a
registered project is precisely when nightaudit must stay away. The only honest
discriminator is which session the transcript belongs to, and both CLIs hand us
an id for the session they just ran — ``session_id`` from Claude Code,
``thread_id`` from Codex's ``thread.started``.

Ids from every provider share one set. They are opaque and provider-unique, so a
Codex id can never match a Claude transcript or the reverse; keeping one set
means one thing to prune and one thing to lose.

This is a cache, not a record. Losing it makes nightaudit shy for an hour, not
wrong, so every function here fails quiet.
"""

from __future__ import annotations

from nightaudit.config import state_dir
from nightaudit.store import read_json, write_json

#: Session ids kept. Only ones newer than the idle window matter, so this need
#: only outlive a night's runs — it is not history.
KEEP = 64


def path():
    return state_dir() / "sessions.json"


def ours() -> set[str]:
    """Session ids nightaudit started."""
    data = read_json(path(), {})
    ids = data.get("ids") if isinstance(data, dict) else None
    return {str(i) for i in ids} if isinstance(ids, list) else set()


def record(session_id: str) -> None:
    """Remember that ``session_id`` was ours, not a human's."""
    session_id = (session_id or "").strip()
    if not session_id:
        return
    data = read_json(path(), {})
    ids = data.get("ids") if isinstance(data, dict) else None
    kept = [str(i) for i in ids] if isinstance(ids, list) else []
    if session_id in kept:
        return
    kept.append(session_id)
    try:
        write_json(path(), {"ids": kept[-KEEP:]})
    except OSError:
        # A run that cannot write this is still a correct run; the cost is one
        # idle window of unnecessary shyness.
        pass
