---
title: "Configuration"
description: "Every knob in config.yaml, with defaults."
order: 8
---

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
