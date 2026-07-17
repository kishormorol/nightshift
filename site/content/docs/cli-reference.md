---
title: "CLI Reference"
description: "Every command."
order: 10
---

| command | what it does |
| --- | --- |
| `nightaudit init` | Detect CLIs, register projects, write config, offer to install cron |
| `nightaudit run [--now]` | One gated run. `--now` skips window+idle checks |
| `nightaudit watch [-n N]` | Follow runs live, including ones cron started |
| `nightaudit digest [--date]` | Render `DIGEST-YYYY-MM-DD.md` |
| `nightaudit status` | Budget bars, recent runs, next window, provider health |

Each takes `--help`.
