# nightaudit — Implementation Spec (v1)

> An audit doesn't change the books. A Python CLI that puts your idle AI coding
> subscription (Claude Code; Codex/Copilot later) to work while you're busy:
> read-only reviews of your projects during configured hours, one markdown
> digest every morning. It NEVER lets a provider modify any project file.

> **On that "NEVER".** It used to read "It NEVER modifies any project file",
> which stopped being true the moment projects could configure `checks:` —
> commands of the user's own that nightaudit executes. The guarantee that
> matters is the one nightaudit can actually enforce, and it enforces it against
> the AI: a provider gets a read-only sandbox and cannot escape it. A check is
> the user's command, run with the user's permissions, and `pytest` writes
> `.pytest_cache/` because they asked it to. Narrowing the sentence is not a
> weakening of the sandbox — the sandbox is unchanged — it is the sentence
> catching up with what is inside it and what is outside.

## Goals / non-goals

**v1 goals:** cron-driven scheduler, budget guardrails, working Claude Code
adapter (read-only enforced), round-robin project/task queue, daily markdown
digest, `init/run/digest/status` CLI, tests that spend zero quota, and a
landing page + `og:image` built from the identity board (see "Landing page").

**Explicitly out of scope for v1:** token-level accounting, web dashboard,
Slack/email delivery, any write-mode, working Codex/Copilot adapters (ship as
documented stubs marked "help wanted").

> **Amended:** the landing page was originally out of scope for v1 and was
> added later, after the CLI was implemented. It ships in `site/` and is
> independent of the Python package — the wheel does not contain it and the
> CLI does not depend on it.

> **Amended:** the Codex adapter shipped, so "working Codex/Copilot adapters"
> is only half a non-goal now. Codex earned it by having something to stand on:
> `codex exec` runs under an OS sandbox (Seatbelt / Landlock+seccomp), which
> enforces read-only more strongly than the Claude adapter's tool allowlist —
> the kernel refuses the write rather than the agent declining to ask. Copilot
> remains a stub, and remains one for a reason recorded in `copilot.py`: its
> denials do not bind every tool, so it cannot clear the bar below. The bar did
> not move to let Codex in; Codex met it.

## Tech

- Python 3.10+, installable via pipx (`pyproject.toml`, console script `nightaudit`)
- Dependencies: keep minimal — `pyyaml`, `click` (or `typer`), stdlib elsewhere
- No daemon. System cron invokes `nightaudit run` hourly; the command decides
  internally whether to act and exits 0 quietly otherwise.

## Repo structure

```
nightaudit/
├── README.md
├── pyproject.toml
├── nightaudit/
│   ├── __init__.py
│   ├── cli.py           # init | run | digest | status
│   ├── config.py        # load + validate YAML config
│   ├── scheduler.py     # window/idle/budget/lock gate + queue pop
│   ├── budget.py        # per-provider run ledger
│   ├── queue.py         # persistent round-robin (project, task) queue
│   ├── report.py        # store RunResults, render digest
│   ├── store.py         # atomic JSON state writes
│   ├── lock.py          # lockfile, breaks stale locks
│   ├── prompts.py       # prompt template resolution
│   ├── cron.py          # crontab entries
│   ├── prompts/         # shipped templates — see note below
│   │   ├── code_review.md
│   │   ├── security_audit.md
│   │   ├── deps_audit.md
│   │   ├── docs_drift.md
│   │   └── dead_links.md
│   └── adapters/
│       ├── base.py      # Adapter protocol + RunResult
│       ├── _process.py  # spawn/stream/deadline/reap, shared by both adapters
│       ├── claude_code.py
│       ├── codex.py     # read-only enforced by Codex's OS sandbox
│       └── copilot.py   # stub: raises NotImplementedError, blocked upstream
├── docs/RECORDING.md    # how to shoot the README hero GIF
├── site/                # the landing page (see "Landing page")
└── tests/
```

> **Amended:** prompt templates live in `nightaudit/prompts/` rather than a
> top-level `prompts/`. A top-level directory is not package data and would not
> survive `pipx install`, which makes every task unresolvable for exactly the
> users who installed the documented way. User templates still override the
> shipped ones from `~/.nightaudit/prompts/`, so the "drop in a `.md`, get a
> task" contract below is unchanged. CI asserts the wheel carries them.

## State & files

All state lives under `~/.nightaudit/`:
- `config.yaml` — user config (below)
- `ledger.json` — budget counts per provider per day/week
- `queue.json` — round-robin position
- `lock` — lockfile during a run
Reports go to the configured `digest.dir` (default `~/nightaudit-reports/`).

## Config schema (`~/.nightaudit/config.yaml`)

```yaml
providers:
  claude_code:
    enabled: true
    budget: { max_runs_per_day: 6, max_runs_per_week: 30 }
  codex:    { enabled: false }
  copilot:  { enabled: false }

projects:
  - name: gradagent
    path: ~/projects/gradagent
    tasks: [code_review, deps_audit, docs_drift]

schedule:
  windows: ["09:00-18:00", "00:00-06:00"]   # local time; may cross midnight
  idle_minutes: 60

digest:
  dir: ~/nightaudit-reports
run:
  timeout_s: 600
```

Validate on load; fail with a clear human message on any invalid field.
Expand `~` in all paths.

## Adapter interface (`adapters/base.py`)

```python
@dataclass
class RunResult:
    provider: str
    project: str
    task: str
    status: Literal["ok", "failed", "timeout"]
    findings_md: str
    started_at: datetime
    duration_s: float

class Adapter(Protocol):
    name: str
    def available(self) -> bool: ...   # CLI on PATH and authenticated
    def run(self, prompt: str, project_dir: Path, timeout_s: int) -> RunResult: ...
```

### Claude Code adapter

- Invoke headless: `claude -p "<prompt>" --output-format json` with cwd set to
  the project dir.
- **Read-only is enforced via Claude Code's own permission flags: allow only
  Read/Grep/Glob-class tools; disallow Edit, Write, and Bash.** Use the
  current CLI flags for tool restriction (check `claude --help` at build time
  rather than assuming flag names).
- Parse the JSON result for the text output; on malformed output, keep raw
  stdout as `findings_md` with status `ok` — never discard a completed run.
- `available()`: binary on PATH + a cheap auth check.

## Scheduler (`nightaudit run`)

Proceed only if ALL pass, otherwise exit 0 with a one-line log reason:
1. **Window** — now is inside a configured window (handle windows crossing midnight).
2. **Idle** — provider not used by the human in the last `idle_minutes`.
   For Claude Code: newest mtime under `~/.claude/projects/`. If the directory
   doesn't exist, treat as idle.
3. **Budget** — ledger below both daily and weekly caps for the provider.
4. **Lock** — acquire lockfile; stale locks (> 2× timeout) are broken.

Then: pop next `(project, task)` from the persistent round-robin queue, load
the prompt template, run the adapter, record the result, increment the ledger,
release the lock. `--now` flag skips checks 1–2 (not budget) for testing.

**Retries:** a failed/timeout run may be retried at most once, immediately,
and both attempts count against budget. Never more.

## Budget (`budget.py`)

JSON ledger: `{provider: {"YYYY-MM-DD": n, "YYYY-Www": n}}`. Increment on
every attempt (including failures — they consumed quota). Prune entries older
than 30 days on load. At cap → scheduler records a `skipped` entry in the run
log so the digest shows it.

## Reporting & digest

Each run writes `reports/YYYY-MM-DD/<project>-<task>-<HHMMSS>.json` (full
RunResult) and `.md` (findings). `nightaudit digest` renders
`DIGEST-YYYY-MM-DD.md`:

1. **Header** — date + budget bar per provider:
   `claude_code ▓▓▓░░░ 3/6 today · 14/30 week`
2. **Highlights** — top 3–5 findings across projects, highest severity first.
3. **Per-project sections** — each finding: severity badge (🔴 HIGH / 🟠 MED /
   🟡 LOW), task name, repo-relative `path/to/file.py:LINE`, one-line
   recommendation.
4. **Run log footer** — table: project | task | provider | status
   (ok/failed/timeout/skipped) | duration | timestamp. Skipped and failed runs
   must appear here.

Severity parsing: prompts instruct the model to prefix each finding with
`HIGH|MED|LOW`; parse leniently, default to LOW when missing. No extra model
call to summarize in v1.

## Prompt templates

Markdown files. Resolved from `~/.nightaudit/prompts/` first, then the
templates shipped in `nightaudit/prompts/` — so any `.md` in either directory
is a valid task name, and a user file shadows a shipped one of the same name.
Each template must instruct the model to: only read, never
modify; output findings as a markdown list; prefix each finding with
`HIGH|MED|LOW`; include `file:line` repo-relative references; give a one-line
recommendation per finding; say "No findings." if clean.

## CLI

- `nightaudit init` — interactive: detect installed provider CLIs, prompt for
  project paths, write config, print (and offer to install) cron entries:
  hourly `nightaudit run`, daily 07:30 `nightaudit digest`.
- `nightaudit run [--now]` — one gated run.
- `nightaudit digest [--date YYYY-MM-DD]` — render digest.
- `nightaudit status` — budget bars, last 5 runs, next eligible window,
  provider availability.

## Error handling

Timeout → kill subprocess tree, status `timeout`. Missing/unauthed CLI →
skip with a note, exit 0. Every failure degrades to a line in the digest run
log; the tool must never leave a stack trace in cron mail for expected
conditions.

## Testing

- `FakeAdapter` for scheduler, budget, queue, and digest tests — zero real calls.
- Claude Code adapter tested with mocked `subprocess`.
- Cover: window crossing midnight, idle detection, both budget caps, retry-once,
  stale lock recovery, digest rendering incl. empty day and all-failed day.
- GitHub Actions CI running pytest, and building the wheel + the landing page.
  The suite must never spawn a real process: an autouse fixture fails any test
  that tries, because a leak here is silent — it still passes, just slower and
  billed to a live subscription.

## Landing page

Lives in `site/` (Next.js App Router + Tailwind). Built from the Nightaudit
identity board, turn 3: the "soft nocturnal" direction refined into `3a` (the
page) and `3b` (the 1280×640 `og:image`). Every route prerenders static.

It is deliberately a sibling of the Python package, not part of it: the wheel
does not ship it and the CLI does not import it. `pyproject.toml` packages only
`nightaudit`.

**The page may only claim what the tool does.** The board is a mockup and a
mockup can promise anything; a published page is a claim. Concretely, and
non-negotiably:

- No provider is advertised as working until its adapter actually runs. Codex
  shipped and its chip is now `ready`; Copilot is drawn as a stub and captioned
  as such. If it ships, flip `ready` in `components/pipeline.tsx` — do not
  restore the board's wording.
- No fabricated metrics. The board's "★ 2.4k" is not on the page and no star
  count, download count, or user count goes on it that isn't real and sourced.
- Sample output must match what the CLI actually prints.

`site/README.md` records each departure from the board and why.

## README requirements

GIF/asciinema placeholder above the fold, then exactly:

```bash
pipx install nightaudit
nightaudit init
nightaudit run --now
```

Then the "0 files touched" trust story (how read-only is enforced), digest
sample, budget explanation, and "Codex & Copilot adapters: help wanted."
