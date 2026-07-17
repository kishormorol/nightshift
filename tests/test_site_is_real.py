"""The landing page may only show output the CLI printed.

SPEC.md says so, and prose lost twice. The identity board's invented
``[09:14] → project · task`` shipped in the hero, was fixed by teaching the CLI
to print a real framed log, and then reappeared in the og:image months later
under a header comment about not lying. A person reading carefully caught both.
CI caught neither, because CI has never been told what "real" means.

This file tells it, in the two ways the two surfaces allow:

- The hero is **generated** from ``docs/shots/hero.txt`` by
  ``docs/make-run-script.py``, so its lines cannot be invented — only captured.
  What still needs saying is that ``hero.txt`` is itself real: a cut of
  ``watch.txt``, never a retyping of it.
- The og:image **cannot** be generated. Satori has no glyph for ``⏺``, ``⎿``,
  ``✻``, ``✓`` or ``🔴`` in the committed fonts, so that card is an excerpt with
  drawn stand-ins by construction. It is held to the weaker claim it can meet:
  every string it shows appears in a capture.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WATCH = ROOT / "docs" / "shots" / "watch.txt"
HERO = ROOT / "docs" / "shots" / "hero.txt"
GENERATED = ROOT / "site" / "lib" / "run-script.generated.ts"
OG_IMAGE = ROOT / "site" / "app" / "opengraph-image.tsx"
HERO_TERMINAL = ROOT / "site" / "components" / "hero-terminal.tsx"

SGR = re.compile(r"\x1b\[[0-9;]*m")
ELIDE = re.compile(r"^\{\{elide (\d+)\}\}$")


def plain(text: str) -> list[str]:
    return [SGR.sub("", line) for line in text.splitlines()]


@pytest.fixture(scope="module")
def watch() -> list[str]:
    return plain(WATCH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def hero() -> list[str]:
    return plain(HERO.read_text(encoding="utf-8"))


# ---- the hero's capture is a cut, not a rewrite -----------------------


def test_every_hero_line_was_printed_by_the_cli(watch, hero):
    """Each line of hero.txt appears verbatim in watch.txt.

    RECORDING.md's rule for trimming a transcript: "Cut whole lines or
    recapture; do not trim by rewriting what the CLI said." This is that rule,
    enforced. A typo'd path or a punched-up finding fails here.
    """
    printed = set(watch)
    invented = [
        line
        for line in hero
        if line.strip() and not ELIDE.match(line.strip()) and line not in printed
    ]

    assert not invented, (
        "hero.txt contains lines watch.txt never printed:\n  "
        + "\n  ".join(invented)
        + "\n\nCut whole lines from the capture; do not retype them."
    )


def _kept_indices(watch: list[str], hero: list[str]) -> list[int]:
    """Where each real hero line sits in the capture, matched in order.

    Positional, not by value, and that distinction is the whole test: `✻
    thinking` occurs four times in a run. Asking "is this line in the capture?"
    says yes for all four the moment the hero keeps one, which silently counts
    three dropped lines as kept.
    """
    out: list[int] = []
    cursor = 0
    for line in hero:
        if not line.strip() or ELIDE.match(line.strip()):
            continue
        while cursor < len(watch) and watch[cursor] != line:
            cursor += 1
        assert cursor < len(watch), f"hero.txt line is not in watch.txt, in order: {line!r}"
        out.append(cursor)
        cursor += 1
    return out


def test_the_hero_keeps_the_captures_order(watch, hero):
    """A subsequence, not a shuffle. Reordering a run tells a story the run did
    not — findings before the reads that found them. `_kept_indices` walks
    forward only, so it raises if a line appears out of order."""
    positions = _kept_indices(watch, hero)

    assert positions == sorted(set(positions)), "hero.txt reorders the capture"


def test_the_elided_count_is_the_truth(watch, hero):
    """`{{elide N}}` renders as "N lines". N must be what was actually dropped.

    The subtlety that got this wrong when the capture was cut: watch.txt has its
    *own* elide marker, so dropping that line hides the 31 lines it stood for as
    well as itself. Counting each marker as one line advertises 24 where the run
    printed 54.
    """
    kept = set(_kept_indices(watch, hero))
    dropped = 0
    for i, line in enumerate(watch):
        if not line.strip() or i in kept:
            continue
        marker = ELIDE.match(line.strip())
        dropped += int(marker.group(1)) if marker else 1

    claimed = [int(m.group(1)) for m in (ELIDE.match(l.strip()) for l in hero) if m]

    assert claimed, "hero.txt has no elide marker; nothing stands for the cut lines"
    assert sum(claimed) == dropped, (
        f"hero.txt says {sum(claimed)} lines were cut; watch.txt says {dropped}"
    )


# ---- the generated script matches the capture ------------------------


def test_the_generated_script_is_current(real_subprocess):
    """CI runs the generator and fails on a diff. So does this, so a
    contributor hears about it before pushing.

    Hand-editing the generated file is the failure it exists to prevent: the
    hero's lines came from a real run precisely because nobody typed them.
    """
    before = GENERATED.read_text(encoding="utf-8")
    subprocess.run(
        [sys.executable, str(ROOT / "docs" / "make-run-script.py")],
        check=True,
        capture_output=True,
    )

    assert GENERATED.read_text(encoding="utf-8") == before, (
        "run-script.generated.ts is stale or hand-edited — "
        "run `python3 docs/make-run-script.py`"
    )


def test_the_generated_script_invents_nothing(watch):
    """Every `msg` in the generated file traces to a captured line.

    The generator splits a line into msg/detail on the capture's own bold/dim
    spans, so this is really a test that the split never fabricates: each msg is
    a substring of something the CLI printed.
    """
    generated = GENERATED.read_text(encoding="utf-8")
    printed = "\n".join(watch)
    msgs = re.findall(r'msg: "((?:[^"\\]|\\.)*)"', generated)
    msgs = [m.replace('\\"', '"').replace("\\\\", "\\") for m in msgs]

    assert msgs, "no lines in the generated script — the generator is broken"

    strays = [
        m
        for m in msgs
        # The elide caption is ours, and `⏺ Glob` is a real line's bold span
        # with its dim `(input)` split off — both are checked elsewhere.
        if not m.endswith(" lines") and m not in printed and m.lstrip("⏺ ") not in printed
    ]

    assert not strays, f"generated msgs the capture never printed: {strays}"


# ---- the transcript nobody looks at ----------------------------------


def test_the_hero_transcript_matches_the_run(watch):
    """The `sr-only` narration must describe the run on screen.

    It is the one surface where drift is invisible to the people who could
    report it: it narrated a JWT bug in a project called `gradagent` months
    after neither was on screen, and only a screen-reader user would ever have
    known. Sighted readers got the real run; everyone else got fiction.

    Prose cannot be generated from a capture, so this checks the load-bearing
    part — every file and line it cites was actually reported.
    """
    source = HERO_TERMINAL.read_text(encoding="utf-8")
    match = re.search(r'<p className="sr-only">(.*?)</p>', source, flags=re.S)

    assert match, "the hero has no screen-reader transcript"

    text = " ".join(match.group(1).split())
    printed = "\n".join(watch)
    cited = re.findall(r"([\w./-]+\.py) at line (\d+)", text)

    assert cited, f"the transcript cites no findings; it reads: {text!r}"

    missing = [f"{p} · {n}" for p, n in cited if f"{p} · {n}" not in printed]

    assert not missing, (
        "the transcript describes findings the run never reported: "
        + ", ".join(missing)
    )


# ---- the og:image, held to what it can promise -----------------------


def test_the_og_card_shows_only_captured_strings(watch):
    """The card cannot be a screenshot — the fonts have no `⏺`, `⎿`, `✻`, `✓`
    or `🔴`, so it is an excerpt with drawn stand-ins. What it can promise is
    that every line it prints was printed by the tool.

    This is the check that would have caught `[09:14] → gradagent`.
    """
    source = OG_IMAGE.read_text(encoding="utf-8")
    printed = "\n".join(watch)

    # The terminal lines are `<Line ... text="..." />`; the surrounding chrome
    # (headline, install command) is prose about the tool, not output from it.
    texts = re.findall(r'<Line\b[^>]*?\btext="([^"]*)"', source, flags=re.S)

    assert texts, "no Line rows found — has the card been restructured?"

    strays = [
        t
        for t in texts
        # `$ nightaudit watch` is the prompt, not output. `┌`/`└` rows carry the
        # frame glyph in `stamp`, so the text is the rest of a real line.
        if t not in ("nightaudit watch",) and t not in printed
    ]

    assert not strays, (
        "the og:image shows lines the CLI never printed:\n  "
        + "\n  ".join(strays)
        + f"\n\nEvery row must appear in {WATCH.relative_to(ROOT)}."
    )
