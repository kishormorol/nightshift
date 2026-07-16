#!/usr/bin/env python3
"""Generate `docs/demo.svg` — the animated terminal above the README fold.

Run: python3 docs/make-demo.py

Why generated rather than recorded: an animated SVG needs no binary in the
repo, stays diffable in review, and renders on GitHub without a CDN. When
someone captures a real asciinema cast (see RECORDING.md), this is what it
replaces.

**Every line below is output the CLI genuinely prints.** That is not a style
preference, it is the rule in SPEC.md ("Landing page"): sample output must
match what the CLI actually prints. If you change `cli.py`'s output, re-run
this. The transcript here was copied from a real run against a stub provider —
real nightaudit, real formatting, invented findings.
"""

from __future__ import annotations

import html
from pathlib import Path

# Brand tokens — the "soft nocturnal" direction from the identity board.
BG = "#0b1122"
CHROME = "#0d1326"
LINE = "#161d33"
DOT = "#26304d"
ACCENT = "#8b9bff"
FG = "#cdd6f4"
DIM = "#5f6c80"
FAINT = "#6472a0"
OK = "#6fdd8b"
MOON = "#ffd79a"
HIGH = "#f38ba8"
MED = "#f9e2af"

FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"
FS = 13
LH = 21
PAD_X = 18
TOP = 46

#: (text, colour). `None` renders a blank spacer line.
#:
#: A real `code_review` of this repo, run on 2026-07-15. The MED shown here is
#: the lock-release race fixed in ff1ae5c; the HIGH is a real limitation of the
#: buffered path, still documented as such in `claude_code.py`. The transcript
#: is trimmed to the lines that carry the story; every line is one the CLI
#: printed.
TRANSCRIPT: list[tuple[str, str] | None] = [
    ("$ nightaudit run --now", ACCENT),
    ("  ⏺ Read(file_path: nightaudit/adapters/claude_code.py)", FAINT),
    ("  ⏺ Read(file_path: nightaudit/lock.py)", FAINT),
    ("  🔴 HIGH nightaudit/adapters/claude_code.py · 267 — Replace the…", HIGH),
    ("  🟠 MED  nightaudit/lock.py · 121 — Have `release()` re-read the…", MED),
    ("     ok  nightaudit · code_review (claude_code, 2m18s)", FG),
    ("         7 findings", DIM),
    None,
    ("$ nightaudit status", ACCENT),
    ("  ✓ claude_code ▓░░░░░ 1/6 today · 1/30 week", FG),
    ("next run  Thu 00:00 (in 2h51m)", FAINT),
    ("up next   nightaudit · security_audit", FAINT),
    None,
    ("$ nightaudit digest", ACCENT),
    ("~/nightaudit-reports/DIGEST-2026-07-15.md  (1 run)", OK),
]

STEP = 0.62  # seconds between lines
HOLD = 2.6  # seconds to rest on the finished frame before looping


def build() -> str:
    rows = [t for t in TRANSCRIPT]
    height = TOP + len(rows) * LH + 22
    width = 760

    reveal_at = [i * STEP for i in range(len(rows))]
    cycle = reveal_at[-1] + HOLD
    # Everything clears together just before the loop restarts, so the replay
    # reads as one run repeating rather than lines flickering independently.
    clear = (reveal_at[-1] + HOLD * 0.82) / cycle * 100

    css: list[str] = [
        f".t{{font-family:{FONT};font-size:{FS}px;white-space:pre;dominant-baseline:middle}}",
        # Anything that animates starts hidden, so a renderer that ignores CSS
        # (some feed readers) still shows a coherent, complete frame.
        "@media (prefers-reduced-motion: reduce){.l,.cur{animation:none!important;opacity:1!important}}",
    ]
    body: list[str] = []

    for i, row in enumerate(rows):
        if row is None:
            continue
        text, colour = row
        start = reveal_at[i] / cycle * 100
        css.append(
            f"@keyframes k{i}{{0%,{start:.2f}%{{opacity:0}}"
            f"{min(start + 0.4, clear):.2f}%,{clear:.2f}%{{opacity:1}}"
            f"{min(clear + 0.4, 100):.2f}%,100%{{opacity:0}}}}"
        )
        css.append(f".l{i}{{animation:k{i} {cycle:.2f}s infinite}}")
        y = TOP + i * LH + LH / 2
        body.append(
            f'<text class="t l l{i}" x="{PAD_X}" y="{y:.0f}" '
            f'fill="{colour}">{html.escape(text)}</text>'
        )

    # The cursor appears only once the last line has landed, then blinks on the
    # held frame. Showing it from the start would park it at the bottom of the
    # canvas while output was still filling in above it.
    cur_y = TOP + len(rows) * LH + 1
    last = reveal_at[-1] / cycle * 100
    css.append(
        f"@keyframes cur{{0%,{last:.2f}%{{opacity:0}}"
        f"{min(last + 0.4, clear):.2f}%,{clear:.2f}%{{opacity:1}}"
        f"{clear + 0.4:.2f}%,100%{{opacity:0}}}}"
    )
    css.append("@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:0}}")
    css.append(f".cur{{animation:cur {cycle:.2f}s infinite, blink 1.1s step-end infinite}}")
    body.append(
        f'<rect class="cur" x="{PAD_X}" y="{cur_y - 11:.0f}" width="8" height="15" fill="{ACCENT}"/>'
    )

    dots = "".join(
        f'<circle cx="{PAD_X + 4 + i * 15}" cy="23" r="4.5" fill="{DOT}"/>' for i in range(3)
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="A nightaudit run: two read-only reviews, then status and digest.">
<title>nightaudit — two read-only reviews, then the morning digest</title>
<style>{"".join(css)}</style>
<rect width="{width}" height="{height}" rx="10" fill="{BG}"/>
<rect width="{width}" height="{TOP - 1}" rx="10" fill="{CHROME}"/>
<rect y="{TOP - 11}" width="{width}" height="10" fill="{CHROME}"/>
<line x1="0" y1="{TOP - 1}" x2="{width}" y2="{TOP - 1}" stroke="{LINE}"/>
{dots}
<text class="t" x="{PAD_X + 56}" y="24" fill="{DIM}" font-size="11">nightaudit — 0 files touched</text>
<text class="t" x="{width - PAD_X}" y="24" fill="{MOON}" font-size="11" text-anchor="end">☾</text>
{chr(10).join(body)}
</svg>
"""


if __name__ == "__main__":
    out = Path(__file__).parent / "demo.svg"
    out.write_text(build(), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes)")
