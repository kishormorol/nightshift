---
title: "The Digest"
description: "What lands in the morning, and how to read it."
order: 4
---

Every run appends to `~/nightaudit-reports/YYYY-MM-DD/`. Once a day
`nightaudit digest` renders those into one file, `DIGEST-YYYY-MM-DD.md`:

```markdown
# Nightaudit · morning digest

Wed Jul 15, 2026 · generated 17:57 local · 1 project · 1 run · 48.2k tokens

## Budget remaining

- `claude_code` ▓░░░░░ 1/6 today · 1/30 week

## Highlights

- 🔴 Replace the buffered `subprocess.run(..., timeout=...)` with the same `Popen` +
  `os.killpg` treatment the streaming path uses … — _nightaudit · code_review_ ·
  `nightaudit/adapters/claude_code.py:267`
- 🟠 Have `release()` re-read the lockfile and unlink only when the recorded pid is
  still our own … — _nightaudit · code_review_ · `nightaudit/lock.py:121`

## Tokens

How many tokens each project's reviews took today.

- nightaudit — 48.2k
- **total — 48.2k**

## Run log

| project | task | provider | status | dur | time |
| --- | --- | --- | --- | --- | --- |
| nightaudit | code_review | claude_code | ok | 2m18s | 15:23 |
```

Highest severity first, grouped by project, read in twenty seconds. The
per-run token count also shows on the line `nightaudit run` prints and in
`nightaudit watch`. It is a measure, not a bill — nightaudit budgets in runs,
not tokens — and Claude's figure includes cache reads, so it runs larger than a
plain input-plus-output count. A run whose CLI reports no usage simply omits it.
**[Here is that digest in full](https://github.com/kishormorol/nightaudit/blob/main/docs/sample-digest.md)** — a real one, not a
mock-up.

Skipped and failed runs stay in the log. A run that didn't happen is
information too, and silently dropping it is how you stop trusting the tool.

Want it early, or for a specific day?

```bash
nightaudit digest                    # today, written to the digest dir
nightaudit digest --date 2026-07-14  # a past day
nightaudit digest --stdout           # print it instead of writing it
```
