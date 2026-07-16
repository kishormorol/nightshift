# TODO

Open work, most consequential first. Anything already done lives in the git
history, not here.

## 1. Decide the `nightaudit run` output format — blocks landing-page honesty

The identity board's hero terminal shows a ticking log:

```
[09:14:02] nightaudit · idle detected · running within budget
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

## 2. Claim `nightaudit` on PyPI before announcing

The distribution is named `nightaudit` because PyPI's `nightaudit` is Ian
Fucci's NMR spectroscopy plotting tool (v1.0.1, live):
<https://pypi.org/project/nightaudit/>. The console script is still
`nightaudit` — the project name and the installed command are independent, so
`pipx install nightaudit` gives you `nightaudit run`.

`nightaudit` was unclaimed when the rename landed, **but names are
first-come and nothing reserves it.** Until it's registered, the README's
quickstart is a promise about a package that doesn't exist yet.

```bash
python -m build
python -m twine upload dist/*      # claims the name
```

Until then, `pipx install nightaudit` fails with "no matching
distribution", which is at least honest — it fails rather than installing the
wrong software, which is what the old name did.

## 3. Record a real asciinema cast

`docs/demo.svg` is generated (`docs/make-demo.py`), not recorded. Its transcript
is real CLI formatting, but the findings come from a stub provider. A real cast
demonstrates the timings instead of asserting them. See `docs/RECORDING.md` —
it also says to repoint `README.md` and delete the generator when you do.

Blocked on (1): no point recording output whose format is about to change.

## 4. Copilot adapter — help wanted, blocked upstream

**Codex shipped** (`nightaudit/adapters/codex.py`), enforcing read-only with the
CLI's own OS sandbox. Its chip on the landing page is now `ready`.

Copilot remains a documented stub raising `NotImplementedError`. The blocker is
not effort — it is that Copilot CLI's denials bind one tool at a time, so a
denied `read(x)` does not stop `shell(cat x)`, and there is no documented
behaviour for an unallowed tool in programmatic mode. `copilot.py`'s docstring
records exactly what was checked and when, so nobody has to rediscover it.

The hard requirement stands: **read-only has to be enforced by the CLI's own
permission system**, not by asking the model nicely. An adapter that cannot do
that should not be merged — "0 files touched" is the product.

If Copilot ships a real allowlist, flip `ready` in
`site/components/pipeline.tsx` and update the caption.

**Verify the Codex adapter against the real CLI.** It was written and tested
against the published `codex exec` reference with a mocked `subprocess` — no
`codex` binary was on the machine. The flags and the NDJSON event names are
documented, not observed. Worth one real run before trusting the digest.

## 5. The site has nowhere to go

`site/app/layout.tsx` sets `metadataBase` to `https://nightaudit.dev`, which is
not registered or deployed. Until it is, the og:image URL in the page metadata
points at a domain that does not resolve. Either register it, point
`metadataBase` at wherever this actually deploys, or expect broken previews.

## 6. Housekeeping

- `feat/landing-page` is unmerged and ahead of `main`.
- The repo is **private**, deliberately — see (2). Flip it with
  `gh repo edit --visibility public` once the install instruction is true.
- CI's first run will be its first real run. Every step was verified locally,
  but "works on my machine" is exactly what CI exists to disprove.
