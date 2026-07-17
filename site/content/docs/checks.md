---
title: "Checks"
description: "Your own commands, run as you, alongside the review."
order: 6
---

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
