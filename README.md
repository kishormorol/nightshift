<div align="center">

# nightaudit

**An audit doesn't change the books.**

Put your idle Claude Code subscription to work — read-only reviews of your
projects while you're busy, one digest every morning.

![A real code_review of this repo: two HIGH findings, then the morning digest](docs/demo.svg)

[![PyPI](https://img.shields.io/pypi/v/nightaudit)](https://pypi.org/project/nightaudit/)
[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)

</div>

---

## What this is

You already pay for Claude Code. It sits idle most of the day, and definitely
all night. nightaudit spends that idle time reviewing the projects you point it
at, and leaves the results in one Markdown file you read with your coffee.

It never edits your code. It has no daemon and no server — cron calls it, it
decides whether to run, and it goes back to sleep. Everything it knows lives in
two directories you can delete at any time.

That's the whole tool. The rest of this page is how to use it.

## Before you start

- **Python 3.10+**
- **At least one AI CLI**, installed and already logged in — either
  [Claude Code](https://claude.com/claude-code) or
  [Codex](https://developers.openai.com/codex). Run `claude --version` or
  `codex --version`; if that works, nightaudit will find it. Have both and it
  will use both, each with its own budget.
- **cron** — standard on macOS and Linux. Windows works via WSL.

You do not need an API key. nightaudit drives the same CLIs you use by hand, on
the subscriptions you already have.

## Install it

```bash
pipx install nightaudit
nightaudit --version
```

(`uv tool install nightaudit` and `pip install nightaudit` work too;
pipx and uv just keep it out of your other environments. The command is
`nightaudit` either way.)

## Set it up

Run `nightaudit init` once. It finds your AI CLIs, asks which projects to
review and when, writes a config file, and offers to install the cron lines
that drive everything:

![nightaudit init walks you through detection, projects, schedule, and cron](docs/img/init.svg)

The project path is the only thing it needs from you. Everything else has a
working default you can accept with Enter:

| It asks | It means | Default |
| --- | --- | --- |
| **project path** | A repo to review. Enter as many as you like; blank line to finish. | — |
| **name** | What to call it in the digest. | the directory's name |
| **tasks** | Which reviews to run on it. | `code_review, security_audit, deps_audit` |
| **windows** | Hours it's allowed to run, local time. | `00:00-06:00` |
| **idle minutes** | How long you must be away from Claude Code first. | `60` |
| **digest dir** | Where the morning digest lands. | `~/nightaudit-reports` |

Everything it writes goes to `~/.nightaudit/config.yaml`. Edit it by hand
whenever you like — it's plain YAML, and `nightaudit status` validates it.

## See it work

Don't wait until tonight. Force a run right now:

```bash
nightaudit run --now
```

`--now` skips the window and idle checks, so you get a review immediately. At a
terminal, nightaudit streams it live — you see the same reads and reasoning you
would if you'd run `claude` yourself:

![A live nightaudit run: reads, reasoning, then seven findings ranked by severity](docs/img/watch.svg)

That is a real run of nightaudit against its own repository, and those are real
bugs. Two of them became commits the same evening: a run that could hang forever
holding the scheduler's lock (`claude_code.py:366`), and a lock that could be
released by the wrong owner (`lock.py:121`).

Findings are ranked 🔴 HIGH, 🟠 MED, 🟡 LOW, and each one cites a `file:line`
so you can jump straight to it.

## Then forget about it

If you let `init` install the cron lines, you're already done. Cron calls
`nightaudit run` every hour; the command decides for itself whether to act and
exits quietly when the answer is no:

```
0 * * * * ~/.local/bin/nightaudit run    >> /tmp/nightaudit-cron.log 2>&1
30 7 * * * ~/.local/bin/nightaudit digest >> /tmp/nightaudit-cron.log 2>&1
```

The hourly line is the gated one; the 07:30 line renders yesterday's findings.
`init` writes the absolute path to the binary because cron runs with a minimal
`PATH` that almost certainly doesn't include yours, and redirects both streams
to a log because there is nowhere else for cron's output to go.

A run happens only when **all four gates** open:

1. **Window** — the clock is inside one of your `schedule.windows`.
2. **Idle** — you haven't touched Claude Code for `idle_minutes`. nightaudit
   watches `~/.claude/projects` and stays out of your way while you're working.
3. **Budget** — you have runs left today and this week.
4. **Lock** — no other run is already in flight.

Any gate saying no is normal, not an error. It prints one line and exits 0:

```
$ nightaudit run
nothing to do — outside configured windows (00:00-06:00)
```

Each run pops one `(project, task)` pair from a persistent round-robin queue,
so every project gets its turn and a noisy one can't starve the rest.

To check on it any time, ask:

![nightaudit status: budget bars, next window, what's up next, recent runs](docs/img/status.svg)

And to watch a run that cron started — including one already in progress —
`nightaudit watch` follows along live and replays the last finished run first.

## Read the digest

Every run appends to `~/nightaudit-reports/YYYY-MM-DD/`. Once a day
`nightaudit digest` renders those into one file, `DIGEST-YYYY-MM-DD.md`:

```markdown
# Nightaudit · morning digest

Wed Jul 15, 2026 · generated 17:57 local · 1 project · 1 run

## Budget remaining

- `claude_code` ▓░░░░░ 1/6 today · 1/30 week

## Highlights

- 🔴 Replace the buffered `subprocess.run(..., timeout=...)` with the same `Popen` +
  `os.killpg` treatment the streaming path uses … — _nightaudit · code_review_ ·
  `nightaudit/adapters/claude_code.py:267`
- 🟠 Have `release()` re-read the lockfile and unlink only when the recorded pid is
  still our own … — _nightaudit · code_review_ · `nightaudit/lock.py:121`

## Run log

| project | task | provider | status | dur | time |
| --- | --- | --- | --- | --- | --- |
| nightaudit | code_review | claude_code | ok | 2m18s | 15:23 |
```

Highest severity first, grouped by project, read in twenty seconds.
**[Here is that digest in full](docs/sample-digest.md)** — a real one, not a
mock-up.

Skipped and failed runs stay in the log. A run that didn't happen is
information too, and silently dropping it is how you stop trusting the tool.

Want it early, or for a specific day?

```bash
nightaudit digest                    # today, written to the digest dir
nightaudit digest --date 2026-07-14  # a past day
nightaudit digest --stdout           # print it instead of writing it
```

## 0 files touched by the AI

nightaudit's entire value depends on being safe to leave unattended, so
read-only isn't a promise in the docs — it's enforced at the layer that
actually executes tools.

This section is about the AI, and the heading says so on purpose. If you
configure [checks](#checks), those are your commands and they run as you — see
below.

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
  nightaudit can do.
- **No fallback.** If the flags are rejected, the run fails and is logged as
  failed. nightaudit never retries an unrestricted invocation.

The prompts reinforce it, but prompts are not a security boundary and aren't
treated as one. The flags are.

nightaudit also never touches your git state: no commits, no branches, no
pushes. Left to itself it reads, and writes exactly one place — the digest
directory.

## Checks

A task is a prompt for an AI that cannot write. A **check** is a command of
your own, and nightaudit runs it:

```yaml
projects:
  - name: gradagent
    tasks: [code_review]
    checks:
      - name: tests
        run: pytest -q
      - name: lint
        run: ruff check .
        timeout_s: 30
```

Each one runs in the project directory before the review, and lands in the
digest with its exit code and the tail of its output:

```
### gradagent

#### Checks

- ✗ `tests` — `pytest -q` · exit 1

  ```
  3 failed, 128 passed
  ```

- ✓ `lint` — `ruff check .` · exit 0
```

**A check is outside the sandbox, and that is the point.** The AI is held
read-only by flags it cannot argue with. Your check is your command, run with
your permissions: `pytest` writes `.pytest_cache/` because you told it to.
nightaudit does not sandbox it and does not pretend to.

Two things worth knowing before you add one:

- **No shell.** The command is split into arguments and run directly, so `&&`,
  pipes, `*` and `$(...)` are not interpreted — `run: rm -rf $HOME` passes the
  four characters `$HOME` to `rm`. If you want a pipeline, point a check at a
  script.
- **`config.yaml` now executes.** Before checks it was inert data; anything that
  can write it can now run commands as you, from cron. That is inherent to
  asking a config file to run your tests. `~/.nightaudit/prompts/` never gained
  this property — a prompt is only ever text handed to a model.

A check that fails, times out, or names a program that isn't installed is
reported and nothing more. It never fails the review — the review is what you
were waiting for.

## Don't let it burn your quota

nightaudit runs on the subscription you already pay for, which means the
fastest way for it to become a problem is to burn through your quota. So it
counts.

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

Start low. Six runs a day is already a lot of review.

## Configuration

Lives at `~/.nightaudit/config.yaml`. Here it is in full — this is every knob
there is:

```yaml
providers:
  claude_code:
    enabled: true
    budget: { max_runs_per_day: 6, max_runs_per_week: 30 }
  codex:
    enabled: true
    budget: { max_runs_per_day: 6, max_runs_per_week: 30 }
    # Optional. Only needed when the CLI isn't on PATH under its own name —
    # e.g. the Codex bundled inside ChatGPT.app:
    binary: /Applications/ChatGPT.app/Contents/Resources/codex

projects:
  - name: gradagent
    path: ~/projects/gradagent
    tasks: [code_review, deps_audit, docs_drift]
  - name: nightaudit
    path: ~/projects/nightaudit
    tasks: [code_review]
    # Optional. Pin this project to one provider. Without it, whichever enabled
    # provider is idle and under budget takes the project.
    provider: codex
    # Optional. Your own commands, run before the review. Unlike a task, these
    # are NOT sandboxed — see "Checks".
    checks:
      - name: tests
        run: pytest -q
        timeout_s: 120

schedule:
  windows: ["09:00-18:00", "00:00-06:00"]   # local time; may cross midnight
  idle_minutes: 60

digest:
  dir: ~/nightaudit-reports
run:
  timeout_s: 600
```

Run `nightaudit status` after editing — it validates the file and tells you
exactly what's wrong if anything is.

Set `NIGHTAUDIT_HOME` to move the whole state directory somewhere else.

## Tasks

A task is just a prompt template. Five ship with nightaudit:

| task | what it looks for |
| --- | --- |
| `code_review` | Bugs, races, and correctness problems |
| `security_audit` | Injection, authz gaps, unsafe defaults |
| `deps_audit` | Unpinned, stale, or risky dependencies |
| `docs_drift` | Docs that no longer match the code |
| `dead_links` | Links and image paths pointing at things that aren't there |

Give each project the tasks that suit it — a Terraform repo probably wants
`security_audit` and `deps_audit`, not `dead_links`.

**Write your own:** drop any `.md` file into `~/.nightaudit/prompts/` and its
filename becomes a valid task name. Use a shipped name to override that
template.

Templates must tell the model to prefix each finding with `HIGH`, `MED`, or
`LOW` and cite a `file:line`. Parsing is lenient — an unlabelled finding is
kept and filed as `LOW` rather than dropped.

## Commands

| command | what it does |
| --- | --- |
| `nightaudit init` | Detect CLIs, register projects, write config, offer to install cron |
| `nightaudit run [--now]` | One gated run. `--now` skips window+idle checks |
| `nightaudit watch [-n N]` | Follow runs live, including ones cron started |
| `nightaudit digest [--date]` | Render `DIGEST-YYYY-MM-DD.md` |
| `nightaudit status` | Budget bars, recent runs, next window, provider health |

Each takes `--help`.

## Troubleshooting

**`nothing to do — outside configured windows (00:00-06:00)`**
Working as designed — it's not in a window. Use `nightaudit run --now` to run
anyway, or widen `schedule.windows`.

**`nothing to do — claude_code used 12m ago (needs 60m idle)`**
You've been using Claude Code, so nightaudit is staying out of your way. Use
`--now`, or lower `idle_minutes` (`0` disables the check).

**`nothing to do — claude_code: daily budget spent (6/6 today)`**
Out of quota for today. Raise `max_runs_per_day` if you want more.

**``No usable AI CLI found. Install Claude Code or Codex and re-run `nightaudit init`.``**
Neither CLI is on your `PATH`. Check `claude --version` / `codex --version` in
the same shell.

**Cron never runs it.** Cron uses a minimal `PATH`, which is why `init` writes
the absolute path to the binary into your crontab. Check
`/tmp/nightaudit-cron.log` — everything cron runs is logged there. On macOS,
cron may also need Full Disk Access to read your projects.

**A run is stuck.** Runs are killed at `run.timeout_s` (default 600s) and
recorded as `timeout`. There is nothing to clean up by hand.

## Uninstall

nightaudit keeps no state anywhere else, so removing it is three lines:

```bash
crontab -e                    # delete the block (see below)
rm -rf ~/.nightaudit          # config, ledger, queue, event logs
pipx uninstall nightaudit
```

`init` fences its crontab lines between two markers — delete them and
everything between:

```
# nightaudit (managed — edit via `nightaudit init`)
...
# end nightaudit
```

Your digests in `~/nightaudit-reports` are yours — delete them or don't.

## Providers

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

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

The test suite spends zero quota: the scheduler, budget, queue, and digest are
covered against a `FakeAdapter`, and the Claude Code adapter is tested with a
mocked `subprocess`. No test ever shells out to a real AI CLI.

The images on this page are generated from real captured output — see
[docs/RECORDING.md](docs/RECORDING.md) if you change what the CLI prints.

## License

MIT
