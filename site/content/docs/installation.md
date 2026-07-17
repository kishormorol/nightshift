---
title: "Installation"
description: "Install it, upgrade it, and what it needs."
order: 1
---

## Requirements

- **Python 3.10+**
- **At least one AI CLI**, installed and already logged in — either
  [Claude Code](https://claude.com/claude-code) or
  [Codex](https://developers.openai.com/codex). Run `claude --version` or
  `codex --version`; if that works, nightaudit will find it. Have both and it
  will use both, each with its own budget.
- **cron** — standard on macOS and Linux. Windows works via WSL.

You do not need an API key. nightaudit drives the same CLIs you use by hand, on
the subscriptions you already have.

## Installation

```bash
pipx install nightshift-cli
nightaudit --version
```

That is not a typo. The tool is `nightaudit` everywhere except the install
line: it was published as `nightshift-cli` before the rename, and PyPI has no
way to rename a project without stranding everyone already on the old one. So
the package keeps its old name and the command gets the new one. You type
`nightshift-cli` once, today, and never again.

(`uv tool install nightshift-cli` and `pip install nightshift-cli` work too;
pipx and uv just keep it out of your other environments. The command is
`nightaudit` either way.)

**Upgrading from 0.3.0, when this was called nightshift?** `pipx upgrade
nightshift-cli` and carry on. Your config, budget history and queue are read
where they already are, in `~/.nightshift`, and the old `nightshift` command
still works so the crontab you already have keeps running — it prints a notice
and does the job. Neither is forever: run `nightaudit init` when convenient and
it rewrites the old cron block in place. The alias goes away in 1.0. To move
the state whenever you like, `mv ~/.nightshift ~/.nightaudit` — it is picked up
on the next run.
