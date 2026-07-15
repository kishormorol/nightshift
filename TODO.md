# TODO

Open work, most consequential first. Anything already done lives in the git
history, not here.

## 1. Decide the `nightshift run` output format — blocks landing-page honesty

The identity board's hero terminal shows a ticking log:

```
[09:14:02] nightshift · idle detected · running within budget
[09:14:03] → gradagent · security_audit · claude_code
[09:14:47] 🔴 HIGH  api/auth.py:142 — JWT tokens never expire; set exp claim
```

**The CLI has never printed that.** What `run` actually prints is:

```
     ok  gradagent · security_audit (claude_code, 44s)
         3 findings
```

SPEC.md ("Landing page") requires sample output to match what the CLI actually
prints, so the hero in `site/components/hero-terminal.tsx` is currently out of
compliance with our own rule, and the comment at the top of
`site/lib/run-script.ts` claiming "every line here corresponds to something the
CLI genuinely prints" is true in substance but false in format.

Two honest ways out:

- **Change the page** to show real output. Cheap. Loses the ticking log, which
  is the better hero.
- **Change the CLI** to print a timestamped log, then repoint the page at it.
  More work, touches `cli.py` and its tests, but the board was arguably
  designing the output we *want* — per-line timestamps and severity as it
  happens are genuinely more useful than a summary, especially under `-v`.

Leaning toward changing the CLI. Needs a decision either way; leaving both as
they are means shipping a page that misrepresents the tool.

## 2. Claim `nightshift-cli` on PyPI before announcing

The distribution is named `nightshift-cli` because PyPI's `nightshift` is Ian
Fucci's NMR spectroscopy plotting tool (v1.0.1, live):
<https://pypi.org/project/nightshift/>. The console script is still
`nightshift` — the project name and the installed command are independent, so
`pipx install nightshift-cli` gives you `nightshift run`.

`nightshift-cli` was unclaimed when the rename landed, **but names are
first-come and nothing reserves it.** Until it's registered, the README's
quickstart is a promise about a package that doesn't exist yet.

```bash
python -m build
python -m twine upload dist/*      # claims the name
```

Until then, `pipx install nightshift-cli` fails with "no matching
distribution", which is at least honest — it fails rather than installing the
wrong software, which is what the old name did.

## 3. Record a real asciinema cast

`docs/demo.svg` is generated (`docs/make-demo.py`), not recorded. Its transcript
is real CLI formatting, but the findings come from a stub provider. A real cast
demonstrates the timings instead of asserting them. See `docs/RECORDING.md` —
it also says to repoint `README.md` and delete the generator when you do.

Blocked on (1): no point recording output whose format is about to change.

## 4. Codex and Copilot adapters — help wanted

Both are documented stubs that raise `NotImplementedError`
(`nightshift/adapters/codex.py`, `copilot.py`). Each docstring lists what an
implementation must do. The hard requirement: **read-only has to be enforced by
the CLI's own permission system**, not by asking the model nicely. An adapter
that cannot do that should not be merged — "0 files touched" is the product.

The landing page draws both as `SOON`. When one ships, flip `ready` in
`site/components/pipeline.tsx` and update the caption.

## 5. The site has nowhere to go

`site/app/layout.tsx` sets `metadataBase` to `https://nightshift.dev`, which is
not registered or deployed. Until it is, the og:image URL in the page metadata
points at a domain that does not resolve. Either register it, point
`metadataBase` at wherever this actually deploys, or expect broken previews.

## 6. Housekeeping

- `feat/landing-page` is unmerged and ahead of `main`.
- The repo is **private**, deliberately — see (2). Flip it with
  `gh repo edit --visibility public` once the install instruction is true.
- CI's first run will be its first real run. Every step was verified locally,
  but "works on my machine" is exactly what CI exists to disprove.
