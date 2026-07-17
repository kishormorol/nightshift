# TODO

Open work, most consequential first. Anything already done lives in the git
history, not here.

## 1. Nothing enforces that sample output is real

SPEC.md ("Landing page") says the page may only show what the CLI prints. That
rule has now been broken twice by the same invented format — the identity
board's ticking `[09:14:02] → project · task`, which no command has ever
printed.

It was caught in the hero and fixed properly: `cli.py` grew `_render_log_event`,
`watch` prints a framed log, and `site/lib/run-script.ts` replays a real capture
with a comment mapping every glyph to the function that emits it. Then it turned
up again in `opengraph-image.tsx`, months later, in the one asset that reaches
people before anything else — under a header comment about not lying. Fixed too,
now, against `docs/shots/watch.txt`.

Twice is a pattern, and the pattern is that the rule is prose. Both fixes were
found by a person reading carefully; neither was found by CI, which is happy to
render a beautiful card full of fiction.

What would actually hold:

- **Generate the samples.** `docs/make-shots.py` already renders committed SVGs
  from `docs/shots/*.txt` and CI fails if they drift. Nothing equivalent exists
  for the site — `run-script.ts` and the og:image are hand-typed from captures.
  A generator that emits the TS from the same captures would make drift
  impossible rather than discouraged.
- **Or test the claim.** Assert every finding ref and command string in the site
  appears in a capture. Weaker, but cheap, and it would have caught both.

The blocker is that the og:image cannot show a screenshot even in principle:
JetBrains Mono has no `⏺`, `⎿`, `✻`, `✓` or `🔴`, so that card will always be an
excerpt with drawn stand-ins. "Verbatim" is not the testable property. "Every
string here appears in a real capture" is.

## 2. Retire the `nightshift` alias and the `~/.nightshift` fallback at 1.0

0.4.1 made upgrading from 0.3.0 a no-op: the old command still works, the old
state directory is read where it is, and `init` replaces the old crontab block.
See `state_dir()` in config.py, the alias in pyproject's `[project.scripts]`,
and `_warn_if_invoked_by_the_old_name` in cli.py — all three say they are
temporary.

They cannot go quietly. Removing them re-breaks exactly the installs they were
added to protect, which is a breaking change and so waits for 1.0. Before it
lands, the alias's notice needs to have been in a release long enough that a
cron-driven install has plausibly printed it into a log someone eventually read.

Tests are in `tests/test_upgrade_from_nightshift.py`; deleting them is part of
the same change.

## 3. Record a real asciinema cast

`docs/demo.svg` is generated (`docs/make-demo.py`), not recorded. A real cast
demonstrates the timings instead of asserting them. See `docs/RECORDING.md` —
it also says to repoint `README.md` and delete the generator when you do.

No longer blocked. It waited on the output format being settled, and it is —
`watch` prints the framed log `_render_log_event` emits, and `docs/shots/` holds
real captures of it.

**It has since gone stale, which raises the priority.** `make-demo.py` says its
transcript is "real formatting", and it is not: the lines read
``path · 267 — text`` where `_echo_finding` prints ``path:line · text``. That is
the same drift the 07-15 `watch.txt` had, still live in the one image at the top
of the README and of the PyPI page — the first thing anyone sees. It survived
because that transcript is a hand-typed constant in a .py file, which nothing
compares to anything.

The fix is the fix that worked everywhere else: generate it from
`docs/shots/`, the way `make-run-script.py` builds the hero, rather than
recording a cast and inheriting the same problem in a new format. A cast still
buys real timings; the format drift does not need to wait for one.

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

~~Verify the Codex adapter against the real CLI.~~ **Done, and it was right to
worry.** The adapter had never run: `--ask-for-approval` is real on `codex` and
rejected by `codex exec`, so every run died at argument parsing while all 38
mocked tests stayed green. Fixed in 0.4.1. The NDJSON event names turned out
exact, and the sandbox refuses a write at the kernel as claimed.

The general lesson outlived the bug and is now enforced: `tests/
test_flag_contract.py` and CI's `contract` job check every flag both adapters
pass against the real CLI's `--help`. "Documented, not observed" is a defect
class, not a one-off.

## 5. `nightaudit.dev` — optional now, and free while it lasts

~~The site has nowhere to go.~~ It was already deployed the whole time, on
Railway at <https://nightshift-site-production.up.railway.app>, building from
`main` with no config in this repo — which is why nothing here knew. This item
said "not registered or deployed" and was half wrong in the more expensive
direction: the previews were broken, but not for the reason written down.

Fixed. `metadataBase` came from intent — a hardcoded `https://nightaudit.dev`
that has never resolved — so the card rendered at the real URL while every
unfurl asked a nameserver that does not exist. It now comes from the platform
(`RAILWAY_PUBLIC_DOMAIN`), and `NEXT_PUBLIC_SITE_URL` overrides it.

What is left is a want, not a bug. `nightaudit.dev` was unregistered as of
2026-07-17 (NXDOMAIN); `nightshift.dev` is taken, which is the argument for not
sitting on it. To take it: register anywhere, add it as a custom domain in
Railway, set `NEXT_PUBLIC_SITE_URL=https://nightaudit.dev` there. No code change
— that is the point of the env var.

The deploy is worth writing down somewhere the repo can see. Nothing in here
records that Railway exists, so the next person to read `metadataBase` learns
where the site lives from a fallback string.

## 6. Housekeeping

- The v0.4.0 release notes are marked superseded rather than rewritten: they
  told people to hand-migrate, and 0.4.1 made that unnecessary. The struck-
  through steps stay because they are what readers were actually given.
- 0.4.0 is on PyPI and not yanked. It works for anyone new, and yanking it to
  fix an upgrade 0.4.1 already fixes would call every working install a mistake.
