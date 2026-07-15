"""Codex adapter — a documented stub.

**Help wanted.** The scheduler, budget ledger, queue, and digest are all
provider-agnostic; shipping Codex support means implementing this one class
against the contract in ``nightshift.adapters.base``.

What an implementation needs to do:

1. ``availability()`` — is the ``codex`` CLI on PATH and authenticated?
2. ``last_human_use()`` — newest mtime of whatever Codex writes per session, so
   nightshift stays out of the user's way. Return ``None`` if unknowable.
3. ``run()`` — invoke Codex headlessly against ``project_dir`` **read-only**,
   and map its exit into ``ok`` / ``failed`` / ``timeout``.

The read-only guarantee is the hard requirement: nightshift promises it never
writes to your code, so an adapter that cannot *enforce* read-only at the CLI
level should not be merged. See ``claude_code.py`` for the reference shape.

https://github.com/kishormorol/nightshift/issues
"""

from __future__ import annotations

from dataclasses import dataclass

from nightshift.adapters.base import StubAdapter


@dataclass
class CodexAdapter(StubAdapter):
    name: str = "codex"
