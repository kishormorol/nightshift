"""Copilot adapter — a documented stub, and currently a blocked one.

**Help wanted, but the obstacle is upstream, not effort.** The scheduler, ledger,
queue, and digest are all provider-agnostic, so this is one class against the
contract in ``nightaudit.adapters.base`` — perhaps an afternoon. It is not
written because Copilot CLI has no enforcement primitive that clears our bar.

What was checked, as of 2026-07, so the next person need not repeat it:

- ``--allow-tool`` / ``--deny-tool`` exist, and deny beats allow. That much is
  the right shape.
- But denials are per-tool, not per-resource: a denied ``read(x)`` does not stop
  ``shell(cat x)``. A rule one tool honours and another ignores is not a
  boundary, it is a suggestion.
- https://github.com/github/copilot-cli/issues/2722 (open) reports
  ``--deny-tool="read(...)"`` blocking *all* file reads regardless of pattern,
  and no persistent permission profile for non-interactive use.
- The docs do not say what happens when the model reaches for a tool that was
  never allowed in programmatic mode. That is the whole guarantee, undocumented.

So the blocker is not "nobody wrote it". It is that nightaudit cannot promise
"0 files touched" on top of that, and the promise is the product. Compare
``codex.py``, which is implemented precisely because Codex hands us an OS-level
sandbox to stand on.

If upstream ships a real allowlist — one that binds every tool, and is
documented for non-interactive runs — then this becomes worth writing:

1. ``availability()`` — is the GitHub Copilot CLI on PATH and authenticated?
2. ``last_human_use()`` — newest mtime of whatever Copilot writes per session,
   so nightaudit stays out of the user's way. Return ``None`` if unknowable.
3. ``run()`` — invoke Copilot headlessly against ``project_dir`` **read-only**,
   and map its exit into ``ok`` / ``failed`` / ``timeout``.

``claude_code.py`` and ``codex.py`` are both reference shapes: the first enforces
read-only with CLI permission flags, the second with a kernel sandbox. Either is
acceptable. Asking the model nicely is not.

https://github.com/kishormorol/nightaudit/issues
"""

from __future__ import annotations

from dataclasses import dataclass

from nightaudit.adapters.base import StubAdapter


@dataclass
class CopilotAdapter(StubAdapter):
    name: str = "copilot"
