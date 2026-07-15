<div align="center">

# nightshift

**Your AI works the night shift.**

Put your idle Claude Code subscription to work — read-only reviews of your
projects while you're busy, one digest every morning.

![Two read-only reviews, then the morning digest](docs/demo.svg)

[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)

</div>

---

```bash
pipx install nightshift-cli
nightshift init
nightshift run --now
```

`init` detects the AI CLIs you already have, registers your projects, and
prints the two cron lines that drive everything. `run --now` does one review
immediately so you can see it work.

---

## 0 files touched

nightshift's entire value depends on being safe to leave unattended, so
read-only isn't a promise in the docs — it's enforced at the layer that
actually executes tools.

The Claude Code adapter invokes the CLI with its own permission flags:

```
claude --print "<prompt>"
  --output-format json
  --allowed-tools     Read Grep Glob NotebookRead
  --disallowed-tools  Bash Edit MultiEdit Write NotebookEdit WebFetch WebSearch Task
```

Three things are true because of that:

- **The allowlist is the whole tool budget.** Claude Code cannot call a tool
  that isn't on it. There is no Edit, no Write, no shell.
- **The denylist is belt-and-braces.** It exists so that a future CLI release
  adding a new write-capable tool to the defaults can't silently widen what
  nightshift can do.
- **No fallback.** If the flags are rejected, the run fails and is logged as
  failed. nightshift never retries an unrestricted invocation.

The prompts reinforce it, but prompts are not a security boundary and aren't
treated as one. The flags are.

nightshift also never touches your git state: no commits, no branches, no
pushes. It reads, and it writes exactly one place — the digest directory.

## The digest

Every run appends to `~/nightshift-reports/YYYY-MM-DD/`, and once a day
`nightshift digest` renders those into one file:

```markdown
# Nightshift · morning digest

Tue Jul 14, 2026 · generated 07:30 local · 3 projects · 5 runs

## Budget remaining

- `claude_code` ▓▓▓░░░ 3/6 today · 14/30 week

## Highlights

- 🔴 User input concatenated into SQL — switch to a parameterized statement — _payments-web · security_audit_ · `src/search/query.ts:88`
- 🔴 Base image `python:latest` is unpinned — pin to `python:3.12.4-slim` — _infra-terraform · deps_audit_ · `docker/Dockerfile:1`
- 🟠 Internal `/metrics` route has no auth guard — add `require_service_token` — _acme-api · code_review_ · `api/routes/metrics.py:42`

## By project

### acme-api

2 findings

- 🟠 Internal `/metrics` route has no auth guard — add `require_service_token` — _code_review_ · `api/routes/metrics.py:42`
- 🟡 `make dev` documented but the target is now `make serve` — _docs_drift_ · `README.md:31`

## Run log

| project | task | provider | status | dur | time |
| --- | --- | --- | --- | --- | --- |
| acme-api | code_review | claude_code | ok | 1m12s | 01:04 |
| acme-api | docs_drift | claude_code | ok | 22s | 01:06 |
| payments-web | security_audit | claude_code | ok | 2m03s | 02:15 |
| infra-terraform | deps_audit | claude_code | timeout · no output after 600s | 10m00s | 03:30 |
| — | — | claude_code | skipped · budget · daily budget spent (6/6 today) | — | 04:00 |
```

Highest severity first, grouped by project, read in twenty seconds. Skipped and
failed runs stay in the log — a run that didn't happen is information too, and
silently dropping it is how you stop trusting the tool.

## Budget

nightshift runs on the subscription you already pay for, which means the fastest
way for it to become a problem is to burn your quota. So it counts.

```yaml
providers:
  claude_code:
    enabled: true
    budget:
      max_runs_per_day: 6
      max_runs_per_week: 30
```

- **Every attempt counts** — including failures and timeouts. They spent your
  quota, so they cost budget. Counting only successes would let a broken
  project drain the account in a loop.
- **Both caps bind.** Under the daily cap but at the weekly one? It stops.
- **`--now` skips the window and idle checks, never the budget check.**
- **At the cap it stops and says so**, once, as a `skipped` row in the digest.

A run also only starts if it's inside one of your `schedule.windows` and the
provider has been idle for `idle_minutes` — nightshift watches
`~/.claude/projects` and stays out of your way while you're actually working.

## How it works

No daemon. Cron calls `nightshift run` hourly and the command decides for
itself whether to act, exiting 0 quietly when the answer is no:

```
0 * * * *   nightshift run     # gated: window → idle → budget → lock
30 7 * * *  nightshift digest  # render yesterday's findings
```

Each run pops one `(project, task)` pair from a persistent round-robin queue,
so every project gets its turn and a noisy one can't starve the rest.

## Commands

| command | what it does |
| --- | --- |
| `nightshift init` | Detect CLIs, register projects, write config, offer to install cron |
| `nightshift run [--now]` | One gated run. `--now` skips window+idle checks |
| `nightshift digest [--date]` | Render `DIGEST-YYYY-MM-DD.md` |
| `nightshift status` | Budget bars, recent runs, next window, provider health |

## Configuration

Lives at `~/.nightshift/config.yaml` (override the whole state directory with
`NIGHTSHIFT_HOME`). `nightshift status` validates it.

```yaml
providers:
  claude_code:
    enabled: true
    budget: { max_runs_per_day: 6, max_runs_per_week: 30 }

projects:
  - name: gradagent
    path: ~/projects/gradagent
    tasks: [code_review, deps_audit, docs_drift]

schedule:
  windows: ["09:00-18:00", "00:00-06:00"]   # local time; may cross midnight
  idle_minutes: 60

digest:
  dir: ~/nightshift-reports
run:
  timeout_s: 600
```

## Tasks

A task is just a prompt template. Five ship with nightshift:

`code_review` · `security_audit` · `deps_audit` · `docs_drift` · `dead_links`

Drop any `.md` file into `~/.nightshift/prompts/` and its filename becomes a
valid task name. Use a shipped name to override that template.

Templates must tell the model to prefix each finding with `HIGH`, `MED`, or
`LOW` and cite a `file:line`. Parsing is lenient — an unlabelled finding is
kept and filed as `LOW` rather than dropped.

## Codex & Copilot adapters: help wanted

The scheduler, ledger, queue, and digest are all provider-agnostic. Codex and
Copilot ship as documented stubs — `nightshift/adapters/codex.py` and
`copilot.py` — each listing exactly what an implementation needs to do, with
`claude_code.py` as the reference.

One hard requirement: **the read-only guarantee must be enforced by the CLI's
own permission system**, not by asking the model nicely. An adapter that can't
do that won't be merged, because "0 files touched" is the whole product.

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

The test suite spends zero quota: the scheduler, budget, queue, and digest are
covered against a `FakeAdapter`, and the Claude Code adapter is tested with a
mocked `subprocess`. No test ever shells out to a real AI CLI.

## License

MIT
