#!/usr/bin/env python3
"""Render the README's terminal screenshots from real captured output.

Run: python3 docs/make-shots.py

Each `docs/shots/<name>.txt` is a transcript captured from a real `nightshift`
invocation, ANSI escapes and all. This renders each one to `docs/img/<name>.svg`
— a terminal window you can drop straight into Markdown.

Why generated rather than a PNG: SVG stays diffable in review, needs no binary
in the repo, and renders on GitHub without a CDN. Why captured rather than
hand-written: SPEC.md ("Landing page") requires sample output to match what the
CLI actually prints, and a transcript nobody can regenerate is a transcript that
starts lying the first time `cli.py` changes.

To refresh one after changing the CLI, see RECORDING.md — recapture the `.txt`,
then re-run this.
"""

from __future__ import annotations

import html
import re
import unicodedata
from pathlib import Path

# Brand tokens — the "soft nocturnal" direction, shared with make-demo.py.
BG = "#0b1122"
CHROME = "#0d1326"
LINE = "#161d33"
DOT = "#26304d"
FG = "#cdd6f4"
DIM = "#5f6c80"
MOON = "#ffd79a"

#: SGR colour number -> hex. Only what the CLI actually emits.
ANSI_FG = {
    "31": "#f38ba8",  # red     — HIGH
    "32": "#6fdd8b",  # green   — ok
    "33": "#f9e2af",  # yellow  — MED, timeout
    "34": "#89b4fa",  # blue    — run frame
    "35": "#cba6f7",  # magenta — thinking
    "36": "#89dceb",  # cyan    — tool, LOW
    "37": FG,
}

FONT = (
    "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace, "
    "'Apple Color Emoji', 'Segoe UI Emoji', 'Noto Color Emoji'"
)
FS = 13.0
CW = FS * 0.6005  # advance width of one cell in the stack above
LH = 20.0
PAD_X = 18.0
TOP = 44.0  # title bar height
BOTTOM = 16.0

#: A cut in a transcript too tall for the README. Rendered as chrome, never as
#: terminal output — the CLI does not print this, and it must not look like it.
ELIDE = re.compile(r"^\{\{elide (\d+)\}\}$")

SGR = re.compile(r"\x1b\[([0-9;]*)m")


class Style:
    __slots__ = ("fg", "bold", "dim")

    def __init__(self) -> None:
        self.fg = FG
        self.bold = False
        self.dim = False

    def copy(self) -> "Style":
        s = Style()
        s.fg, s.bold, s.dim = self.fg, self.bold, self.dim
        return s

    def apply(self, params: str) -> None:
        for p in (params or "0").split(";"):
            if p in ("", "0"):
                self.fg, self.bold, self.dim = FG, False, False
            elif p == "1":
                self.bold = True
            elif p == "2":
                self.dim = True
            elif p == "22":
                # Normal intensity — cancels bold *and* dim, leaves the colour.
                self.bold = self.dim = False
            elif p == "39":
                # Default foreground — leaves intensity alone.
                self.fg = FG
            elif p in ANSI_FG:
                self.fg = ANSI_FG[p]


def cell_width(ch: str) -> int:
    """Terminal columns one character occupies.

    Emoji and CJK take two cells. Getting this wrong walks every span after it
    out of alignment, which is exactly what you notice in a screenshot.
    """
    if unicodedata.combining(ch):
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    # Emoji outside the East Asian Wide ranges (✓ ✗ ⏺ ✻ stay single-width;
    # the 🔴🟠🟡 severity dots are Wide and caught above).
    return 1


def parse(line: str) -> list[tuple[str, Style]]:
    """Split one ANSI line into (text, style) spans."""
    spans: list[tuple[str, Style]] = []
    style = Style()
    pos = 0
    for m in SGR.finditer(line):
        if m.start() > pos:
            spans.append((line[pos : m.start()], style.copy()))
        style.apply(m.group(1))
        pos = m.end()
    if pos < len(line):
        spans.append((line[pos:], style.copy()))
    return [(t, s) for t, s in spans if t]


def render(name: str, transcript: str, title: str) -> str:
    raw = transcript.rstrip("\n").split("\n")

    # Width is the widest line, so the window fits its content rather than
    # padding every shot out to 88 columns of empty space.
    cols = 0
    for line in raw:
        if ELIDE.match(line.strip()):
            continue
        cols = max(cols, sum(cell_width(c) for t, _ in parse(line) for c in t))
    cols = max(cols, len(title) + 24)

    width = round(PAD_X * 2 + cols * CW)
    height = round(TOP + len(raw) * LH + BOTTOM)

    body: list[str] = []
    for i, line in enumerate(raw):
        y = TOP + i * LH + LH / 2
        elide = ELIDE.match(line.strip())
        if elide:
            n = elide.group(1)
            body.append(
                f'<line x1="{PAD_X}" y1="{y:.0f}" x2="{width / 2 - 46:.0f}" y2="{y:.0f}" stroke="{LINE}"/>'
                f'<line x1="{width / 2 + 46:.0f}" y1="{y:.0f}" x2="{width - PAD_X:.0f}" y2="{y:.0f}" stroke="{LINE}"/>'
                f'<text class="t" x="{width / 2:.0f}" y="{y:.0f}" fill="{DIM}" '
                f'font-size="10.5" text-anchor="middle">{n} lines</text>'
            )
            continue

        col = 0
        for text, style in parse(line):
            x = PAD_X + col * CW
            cells = sum(cell_width(c) for c in text)
            col += cells
            if not text.strip():
                continue
            attrs = f'fill="{style.fg}"'
            if style.bold:
                attrs += ' font-weight="600"'
            if style.dim:
                attrs += ' opacity="0.62"'
            # Pin the advance to the grid. Without this, every span renders at
            # the font's own advance width, which differs per renderer — long
            # lines then drift out of column and off the right edge.
            attrs += f' textLength="{cells * CW:.1f}" lengthAdjust="spacing"'
            body.append(
                f'<text class="t" x="{x:.1f}" y="{y:.0f}" {attrs}>{html.escape(text)}</text>'
            )

    dots = "".join(
        f'<circle cx="{PAD_X + 4 + i * 15:.0f}" cy="22" r="4.5" fill="{DOT}"/>' for i in range(3)
    )
    label = html.escape(title)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{label}">
<title>{label}</title>
<style>.t{{font-family:{FONT};font-size:{FS}px;white-space:pre;dominant-baseline:middle}}</style>
<rect width="{width}" height="{height}" rx="10" fill="{BG}"/>
<rect width="{width}" height="{TOP - 1:.0f}" rx="10" fill="{CHROME}"/>
<rect y="{TOP - 11:.0f}" width="{width}" height="10" fill="{CHROME}"/>
<line x1="0" y1="{TOP - 1:.0f}" x2="{width}" y2="{TOP - 1:.0f}" stroke="{LINE}"/>
{dots}
<text class="t" x="{PAD_X + 56:.0f}" y="23" fill="{DIM}" font-size="11">{label}</text>
<text class="t" x="{width - PAD_X:.0f}" y="23" fill="{MOON}" font-size="11" text-anchor="end">☾</text>
{chr(10).join(body)}
</svg>
"""


#: shot name -> the title bar caption.
SHOTS = {
    "init": "nightshift init — one-time setup",
    "watch": "nightshift watch — a review in flight",
    "status": "nightshift status — budget and schedule",
}


def main() -> None:
    here = Path(__file__).parent
    out_dir = here / "img"
    out_dir.mkdir(exist_ok=True)
    for name, title in SHOTS.items():
        src = here / "shots" / f"{name}.txt"
        svg = render(name, src.read_text(encoding="utf-8"), title)
        dest = out_dir / f"{name}.svg"
        dest.write_text(svg, encoding="utf-8")
        print(f"wrote {dest.relative_to(here.parent)} ({dest.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
