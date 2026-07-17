---
title: "Budget"
description: "Caps per day and per week, and how they are counted."
order: 7
---

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
