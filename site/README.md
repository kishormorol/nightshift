# nightaudit.dev

The landing page, built from the **Nightaudit visual identity** design board —
turn 3, the "soft nocturnal" direction (2b) as refined into `3a` (landing) and
`3b` (social card).

```bash
npm install
npm run dev     # http://localhost:3000
npm run build   # every route prerenders static
```

## Where things live

| path | what |
| --- | --- |
| `app/page.tsx` | composes the sections |
| `app/opengraph-image.tsx` | the `3b` card, 1280×640, generated at build |
| `app/icon.tsx` | favicon, generated |
| `lib/run-script.ts` | the run the hero terminal replays |
| `components/` | one file per section |

Design tokens — the palette, the two fonts, the keyframes — live in
`app/globals.css` under `@theme`. Change a colour there, not in a component.

## Where this departs from the board, and why

The board is a **mockup**, and a mockup can claim anything. A live page cannot.
Three changes, all in the same direction: the page only says things the tool
actually does.

1. **"Idle Claude Code, Codex & Copilot" → Claude Code only.** Codex and
   Copilot ship as documented stubs that raise `NotImplementedError`
   (`nightaudit/adapters/codex.py`). The pipeline draws them dashed and marked
   `SOON`, and the caption says so outright.
2. **"★ 2.4k" is gone.** It appeared four times on the board. Inventing a star
   count is fabricated social proof.
3. **The digest's `codex 4/6` bar reads `disabled`.** It cannot have run four
   reviews overnight when the adapter does not exist.

Two board elements were dropped as scaffolding rather than design: the fake
browser chrome around the hero, and the dashed `◉ RECORDING SPEC` annotation —
that one was a note *to us* about shooting the README GIF, and it now lives in
`docs/RECORDING.md`.

If an adapter actually ships, the honest fix is to flip `ready` in
`components/pipeline.tsx` and update the copy — not to quietly restore the
board's original wording.

## Notes for whoever touches this next

- **The og:image needs the fonts in `assets/fonts/`.** Satori never sees
  `next/font`; without them the card silently falls back to system sans, which
  still builds and still looks wrong. It also cannot render `🔴`/`✓` — it goes
  to the network for a glyph and fails the build — so severities there are
  drawn dots.
- **The hero terminal renders its finished frame on the server**, so the run is
  visible without JavaScript and to crawlers. Keep it that way; the transcript
  is the pitch.
- Motion follows `prefers-reduced-motion`. The terminal keeps advancing — that
  is content — but the blink, drift and pulse stop.
