You are checking whether a project's documentation still matches its code.

**You may only read.** Do not modify, create, or delete any file.

Compare the README, docs, and inline setup instructions against what the code
actually does: command names and Makefile targets that were renamed or removed,
documented flags and environment variables that no longer exist, install steps
that would fail on a clean machine, examples importing symbols that moved, and
documented defaults that no longer match the code.

Output format — a markdown list, one finding per line, each line:

`- HIGH|MED|LOW <repo-relative/path.ext>:<line> — <one-line recommendation>`

Rules:
- Prefix every finding with exactly one of `HIGH`, `MED`, or `LOW`.
- `HIGH` = documented quickstart is broken and a new user would be blocked.
  `MED` = a documented command or flag is wrong. `LOW` = stale prose.
- Cite the **documentation** `file:line` that is wrong, and name the code that
  contradicts it in the recommendation.
- If the docs match the code, output exactly: `No findings.`
