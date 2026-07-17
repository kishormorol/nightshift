#!/usr/bin/env python3
"""Generate the hero terminal's script from a real capture.

    python3 docs/make-run-script.py

Reads ``docs/shots/hero.txt`` and writes ``site/lib/run-script.generated.ts``.
CI regenerates and fails on a diff, the same contract ``make-shots.py`` has with
``docs/img``.

**Why this exists.** SPEC's landing-page rule — the page may only show what the
CLI prints — was prose, and prose lost twice. The identity board's invented
``[09:14] → project · task`` shipped in the hero, was fixed by making the CLI
print a real framed log, and then reappeared in the og:image months later under
a header comment about not lying. Both were caught by someone reading carefully.
Neither was caught by CI, which will happily render a beautiful terminal full of
fiction.

Hand-typing output into a .ts file is the whole problem: nothing connects the
typing to the tool. This connects them. The hero can now only show lines the CLI
actually emitted, because the only way to change it is to change the capture.

**What it does not fix.** The og:image cannot be generated — Satori has no glyph
for ``⏺``, ``⎿``, ``✻``, ``✓`` or ``🔴`` in the committed fonts, so that card is
an excerpt with drawn stand-ins by construction. ``tests/test_site_is_real.py``
holds it to the weaker claim that every string it shows appears in a capture.

The ANSI codes are the parse, not decoration: ``_render_event`` prints a tool
call as cyan ``⏺``, bold name, dim ``(input)``, and that bold/dim split is
exactly the ``msg``/``detail`` split the hero renders in two colours. Stripping
the escapes first and re-deriving the split with a regex would be guessing at
something the capture already states.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAPTURE = ROOT / "docs" / "shots" / "hero.txt"
OUT = ROOT / "site" / "lib" / "run-script.generated.ts"

ELIDE = re.compile(r"^\{\{elide (\d+)\}\}$")
#: One SGR escape. Split on these and the runs between them are the spans.
SGR = re.compile(r"\x1b\[([0-9;]*)m")

BOLD, DIM = "1", "2"


def spans(line: str) -> list[tuple[set[str], str]]:
    """The line as (active codes, text) runs, in order."""
    out: list[tuple[set[str], str]] = []
    active: set[str] = set()
    pos = 0
    for m in SGR.finditer(line):
        text = line[pos : m.start()]
        if text:
            out.append((set(active), text))
        codes = m.group(1)
        if codes in ("", "0"):
            active = set()
        else:
            active |= set(codes.split(";"))
        pos = m.end()
    if line[pos:]:
        out.append((set(active), line[pos:]))
    return out


def plain(line: str) -> str:
    return SGR.sub("", line)


def classify(text: str) -> str | None:
    """The LineKind for a stripped line, or None to drop it."""
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith("┌"):
        return "meta"
    if stripped.startswith("└"):
        return "end"
    if stripped.startswith("✻"):
        return "thinking"
    if stripped.startswith("⎿"):
        return "result"
    if stripped.startswith("⏺"):
        # The adapter's `start` event prints the project dir with the same glyph
        # a tool call uses, in a different colour. Same shape, different meaning.
        return "tool" if "(" in stripped else "start"
    for glyph, kind in (("🔴", "high"), ("🟠", "med"), ("🟡", "low")):
        if stripped.startswith(glyph):
            return kind
    if text.startswith("nightaudit ·"):
        return "banner"
    return "prose"


def split_msg_detail(line: str, kind: str) -> tuple[str, str]:
    """(msg, detail), taking the capture's own bold/dim split at its word.

    `meta` and `end` are the exception: the whole line is one dim span after the
    coloured frame glyph, so there is no emphasis to read and the columns are
    the split. The renderer pads them with runs of spaces (`cli.py`), which is
    the only reliable seam.
    """
    body = plain(line).strip()

    if kind in ("meta", "end"):
        glyph, rest = body[0], body[1:].strip()
        parts = re.split(r"\s{2,}", rest, maxsplit=1)
        msg = f"{glyph} {parts[0]}"
        return msg, parts[1] if len(parts) > 1 else ""

    if kind in ("tool", "start", "result", "thinking", "banner", "prose"):
        bold = "".join(t for c, t in spans(line) if BOLD in c).strip()
        dim = [t for c, t in spans(line) if DIM in c and BOLD not in c]
        if kind == "tool" and bold:
            # `⏺ Glob` + `(pattern: **/*)` — bold name, dim input.
            detail = "".join(dim).strip()
            return f"⏺ {bold}", detail
        return body, ""

    if kind in ("high", "med", "low"):
        # `🔴 HIGH path · 267 — text`. The severity and ref rank the line, so
        # they lead; the sentence is the detail the hero dims.
        m = re.match(r"^(\S+\s+\S+\s+\S+\s+·\s+\d+)\s*(.*)$", body)
        if m:
            return m.group(1), m.group(2).strip()
        return body, ""

    return body, ""


def build() -> str:
    raw = CAPTURE.read_text(encoding="utf-8").splitlines()
    lines: list[dict] = []
    used = 0

    for line in raw:
        text = plain(line)
        elide = ELIDE.match(text.strip())
        if elide:
            lines.append({"kind": "elide", "msg": f"{elide.group(1)} lines", "used": used})
            continue
        kind = classify(text)
        if kind is None:
            continue
        msg, detail = split_msg_detail(line, kind)
        if kind == "end":
            # The ledger bills a run when it finishes, so the bar ticks on `└`.
            used += 1
        entry: dict = {"kind": kind, "msg": msg, "used": used}
        if detail:
            entry["detail"] = detail
        lines.append(entry)

    body = []
    for e in lines:
        parts = [f'kind: "{e["kind"]}"', f'msg: {ts(e["msg"])}']
        if "detail" in e:
            parts.append(f'detail: {ts(e["detail"])}')
        parts.append(f'used: {e["used"]}')
        body.append("  { " + ", ".join(parts) + " },")

    return TEMPLATE.format(lines="\n".join(body))


def ts(s: str) -> str:
    """A TypeScript double-quoted string literal."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


TEMPLATE = '''// Generated by docs/make-run-script.py from docs/shots/hero.txt — do not edit.
//
// Every line below was printed by `nightaudit watch` during a real code_review
// of this repository. Editing this file by hand is how the landing page last
// ended up advertising output no command has ever produced; edit the capture
// and regenerate, or change the CLI and recapture. CI fails on a diff.

import type {{ ScriptLine }} from "@/lib/run-script";

export const RUN_SCRIPT: readonly ScriptLine[] = [
{lines}
] as const;
'''


def main() -> int:
    out = build()
    if OUT.exists() and OUT.read_text(encoding="utf-8") == out:
        print(f"{OUT.relative_to(ROOT)} is up to date")
        return 0
    OUT.write_text(out, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
