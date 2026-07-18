<div align="center">

[![nightaudit — your repos, reviewed overnight; a stylized morning digest showing per-provider run budgets, tokens used, and findings surfaced](https://raw.githubusercontent.com/kishormorol/nightaudit/main/docs/hero.png)](https://pypi.org/project/nightshift-cli/)

# nightaudit

**An audit doesn't change the books.**

Put your idle Claude Code or Codex subscription to work — read-only reviews of
your projects while you're busy, one digest every morning.

![nightaudit's morning digest: a code_review of a sample repo turns up a SQL injection, a hardcoded secret, and a timing-unsafe compare — ranked by severity with a file:line, and how many tokens the review took](https://raw.githubusercontent.com/kishormorol/nightaudit/main/docs/demo.gif)

[![PyPI](https://img.shields.io/pypi/v/nightshift-cli)](https://pypi.org/project/nightshift-cli/)
[![license](https://img.shields.io/badge/license-MIT-blue)](https://github.com/kishormorol/nightaudit/blob/main/LICENSE)
[![python](https://img.shields.io/badge/python-3.10%2B-blue)](https://github.com/kishormorol/nightaudit/blob/main/pyproject.toml)

**[Docs](https://nightshift-site-production.up.railway.app/docs)** · [Quick Start](https://nightshift-site-production.up.railway.app/docs/quick-start) · [Configuration](https://nightshift-site-production.up.railway.app/docs/configuration) · [CLI Reference](https://nightshift-site-production.up.railway.app/docs/cli-reference)

</div>

---

## What this is

You already pay for Claude Code or ChatGPT. That subscription sits idle most of
the day, and definitely all night. nightaudit spends that idle time reviewing
the projects you point it at, and leaves the results in one Markdown file you
read with your coffee.

Either CLI works — Claude Code or Codex, whichever you have. Have both and it
uses both, each with its own budget.

It never edits your code. It has no daemon and no server — cron calls it, it
decides whether to run, and it goes back to sleep. Everything it knows lives in
two directories you can delete at any time.

That's the whole tool. Everything below is how to start; the
[docs](https://nightshift-site-production.up.railway.app/docs) are the detail.

## Features

- **Read-only, and not on the honour system.** Enforced by the AI CLI's own
  permission layer — an allowlist Claude Code applies, or the kernel sandbox
  Codex runs under. A bug in the model cannot touch the disk.
- **Uses the subscription you already pay for.** No API key. It drives the same
  `claude` or `codex` you use by hand, on your own plan.
- **Budget-aware.** Hard caps per day and per week, per provider, counted in a
  ledger it keeps itself.
- **Stays out of your way.** It only runs inside the hours you choose, and only
  once you've been away from the CLI long enough.
- **Multi-project.** Add repos one path at a time, or point `--discover` at a
  folder and it finds every git repo under it. A round-robin queue means a noisy
  repo can't starve the rest.
- **One digest a morning.** Every finding ranked by severity with a `file:line`,
  in a single Markdown file — with how many tokens each project's reviews took.
- **No daemon, no server.** Cron calls it, it decides whether to run, it exits.
  Everything it knows lives in two directories you can delete.

## Installation

```bash
pipx install nightshift-cli
nightaudit --version
```

That is not a typo: the tool is `nightaudit` everywhere except the install line.
It was published as `nightshift-cli` before the rename, and PyPI has no way to
rename a project without stranding everyone on the old one. You type it once.

Full guide, including upgrading from 0.3.0: **[Installation](https://nightshift-site-production.up.railway.app/docs/installation)**.

## Getting Started

```bash
nightaudit init                 # find your CLIs, pick projects and hours, write cron
nightaudit init --discover ~/code   # or scan a folder and pick from what it finds
nightaudit run --now            # don't wait until tonight
nightaudit status               # budget, next window, what's up next
```

`init` asks for a project path and gives everything else a working default —
or type `scan <folder>` at the prompt (or pass `--discover`) to add every git
repo under a folder from a checklist. Then cron takes over: it runs in the hours
you chose, once you've been away long enough, until the budget says stop.

Full guide: **[Quick Start](https://nightshift-site-production.up.railway.app/docs/quick-start)** · **[Scheduling](https://nightshift-site-production.up.railway.app/docs/scheduling)**

## Everything else

| | |
| --- | --- |
| [Read-only](https://nightshift-site-production.up.railway.app/docs/read-only) | How "0 files touched" is enforced rather than promised |
| [Configuration](https://nightshift-site-production.up.railway.app/docs/configuration) | Every knob in `config.yaml` |
| [Tasks](https://nightshift-site-production.up.railway.app/docs/tasks) | The five that ship, and writing your own |
| [Checks](https://nightshift-site-production.up.railway.app/docs/checks) | Your own commands, run as you |
| [Budget](https://nightshift-site-production.up.railway.app/docs/budget) | Caps per day and per week |
| [The digest](https://nightshift-site-production.up.railway.app/docs/digest) | What lands in the morning |
| [CLI reference](https://nightshift-site-production.up.railway.app/docs/cli-reference) | Every command |
| [Providers](https://nightshift-site-production.up.railway.app/docs/providers) | Claude Code, Codex, and why Copilot is a stub |
| [Troubleshooting](https://nightshift-site-production.up.railway.app/docs/troubleshooting) | It said "nothing to do", and other normal things |

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

The test suite spends zero quota: the scheduler, budget, queue, and digest are
covered against a `FakeAdapter`, and the Claude Code adapter is tested with a
mocked `subprocess`. No test ever shells out to a real AI CLI.

The images on this page are generated from real captured output — see
[docs/RECORDING.md](https://github.com/kishormorol/nightaudit/blob/main/docs/RECORDING.md) if you change what the CLI prints.

## License

MIT
