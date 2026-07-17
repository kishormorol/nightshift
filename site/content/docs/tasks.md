---
title: "Tasks"
description: "The five that ship, and writing your own."
order: 9
---

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
