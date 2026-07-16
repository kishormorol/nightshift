# The README's images

Two kinds, one rule: **every line in them is a line the CLI actually printed.**
SPEC.md ("Landing page") requires sample output to match real output, and an
image is the easiest place to quietly break that — nobody diffs a picture.

| what | source | generator | output |
| --- | --- | --- | --- |
| The hero animation | `make-demo.py`'s `TRANSCRIPT` | `python3 docs/make-demo.py` | `docs/demo.svg` |
| The screenshots | `docs/shots/*.txt` | `python3 docs/make-shots.py` | `docs/img/*.svg` |

Both emit SVG rather than GIF or PNG: it animates on GitHub, keeps a binary out
of the repo, stays diffable in review, and needs no CDN.

## The screenshots

`docs/shots/<name>.txt` is a transcript captured from a real `nightshift` run,
ANSI escapes and all. `make-shots.py` parses the escapes and renders each to a
terminal window in `docs/img/<name>.svg`. To add one, drop in a `.txt` and add
it to `SHOTS` with its title-bar caption.

The current shots — `init`, `watch`, `status` — were captured on 2026-07-15
from a real `code_review` of this repository. The findings in `watch.txt` are
real bugs: `claude_code.py:366` became 13c0d3f and `lock.py:121` became ff1ae5c.

### Capturing one

The CLI colours output only at a TTY, so drive it through a pty rather than a
pipe. `script -q /dev/null nightshift status > docs/shots/status.txt` covers the
non-interactive commands; `watch` and `init` need a throwaway `pty.fork()`
script that can feed them input and stop them.

Then, **before you commit it**:

- **Scrub your home directory.** `/Users/you/projects/foo` → `~/projects/foo`.
  Check the digest path too — a careless prefix replace turns
  `~/nightshift-reports` into `~/projects/nightshift-reports`.
- **Use a throwaway `NIGHTSHIFT_HOME`** for anything that writes config, so
  capturing a screenshot never touches your real setup.
- **No real secrets, no private project names.**

### Trimming

A 70-line `watch` transcript is taller than anyone will scroll. Replace the
boring middle with `{{elide N}}` on its own line and `make-shots.py` renders it
as a captioned rule — visibly chrome, never mistakable for CLI output. Cut
whole lines or recapture; do not trim by rewriting what the CLI said.

## The hero

The animation above the fold is the whole pitch: see it → want it → install in
one paste. It sits directly above the `pipx install nightshift-cli` line, so
whatever it shows is the first thing a visitor learns about the tool.

`make-demo.py` animates a trimmed transcript line by line. It is generated
rather than recorded, and the honest limitation is that it *asserts* its
timings rather than demonstrating them — the `2m18s` is real, but the animation
does not take 2m18s.

A real asciinema cast would be better, because it demonstrates the timings. If
you record one:

```bash
asciinema rec --cols 90 --rows 22 demo.cast
agg --font-size 15 --theme asciinema demo.cast docs/demo.gif
```

Target roughly a **14 second loop** — long enough to read, short enough to loop
before someone scrolls past. Point `README.md` at the result, delete
`make-demo.py`, and **keep `demo.cast` in the repo**: re-recording from scratch
to change one line is how a demo goes stale and starts lying about the product.

## What an image must never show

- **A write.** The whole promise is "0 files touched". A cast showing an edit, a
  commit, or a shell command contradicts the product on the way in.
- **Anything that identifies you.** See the scrub list above.

## When the CLI's output changes

Re-run the generator for whatever moved. If you changed what `cli.py` prints,
the committed `.txt` captures are now wrong — recapture them rather than editing
them by hand, or the images start describing a CLI that no longer exists.
