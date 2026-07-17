---
title: "Read-only"
description: "How 0 files touched is enforced rather than promised."
order: 5
---

nightaudit's entire value depends on being safe to leave unattended, so
read-only isn't a promise in the docs — it's enforced at the layer that
actually executes tools.

This page is about the AI, and the distinction is deliberate: **0 files touched**
is a claim about the model, not about everything nightaudit runs. If you
configure [checks](/docs/checks), those are your own commands and they run as
you.

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
