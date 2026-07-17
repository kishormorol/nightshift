---
title: "Troubleshooting"
description: "It said nothing to do, and other normal things."
order: 12
---

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
