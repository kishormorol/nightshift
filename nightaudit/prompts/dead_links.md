You are checking a project's documentation for dead references.

**You may only read.** Do not modify, create, or delete any file. Do not fetch
the network — judge links from the repository contents alone.

Look for: relative links and image paths that point at files which do not exist
in the repo, anchors pointing at headings that are absent, references to moved
or deleted docs, links to repositories or paths that contradict the project's
own name and layout, and TODO placeholder URLs left in published docs.

Output format — a markdown list, one finding per line, each line:

`- HIGH|MED|LOW <repo-relative/path.ext>:<line> — <one-line recommendation>`

Rules:
- Prefix every finding with exactly one of `HIGH`, `MED`, or `LOW`.
- `HIGH` = a link in the README's install or quickstart path is broken.
  `MED` = a broken link in body documentation. `LOW` = a cosmetic or TODO link.
- Every finding must cite the repo-relative `file:line` of the link itself.
- Name the correct target in the recommendation when you can infer it.
- If every reference resolves, output exactly: `No findings.`
