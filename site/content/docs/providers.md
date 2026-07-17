---
title: "Providers"
description: "Claude Code, Codex, and why Copilot is a stub."
order: 11
---

The scheduler, ledger, queue, and digest are all provider-agnostic. Enable
whichever CLIs you have; each gets its own budget.

| provider | status | how read-only is enforced |
| --- | --- | --- |
| `claude_code` | working | CLI permission flags — an allowlist of read-class tools, plus a denylist of every mutating one |
| `codex` | working | Codex's own OS sandbox — Seatbelt on macOS, Landlock + seccomp on Linux |
| `copilot` | stub | — see below |

One hard requirement, and it's the whole reason that last column exists: **the
read-only guarantee must be enforced by the CLI's own permission system**, not
by asking the model nicely. An adapter that can't do that won't be merged,
because "0 files touched" is the whole product.

**Copilot: help wanted, but blocked upstream.** It ships as a documented stub
(`nightaudit/adapters/copilot.py`). The obstacle isn't effort — it's that
Copilot CLI has no enforcement primitive that clears the bar. Its file-level
denials don't apply across tools, so `shell(cat x)` walks around a denied
`read(x)`, and [an open issue](https://github.com/github/copilot-cli/issues/2722)
reports `--deny-tool="read(...)"` blocking *all* reads regardless of pattern.
Denials one tool honors and another ignores aren't a permission system. If that
changes upstream, the adapter is an afternoon's work — `codex.py` and
`claude_code.py` are both reference shapes.
