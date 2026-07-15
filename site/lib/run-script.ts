/**
 * The run the hero terminal replays.
 *
 * This is a scripted recreation of a real `nightshift run`, not live output —
 * but it must stay honest about what the tool actually does, because it is the
 * first thing a visitor learns. Every line here corresponds to something the
 * CLI genuinely prints:
 *
 *   - budget gating and the 6-runs/day default    (nightshift/budget.py)
 *   - severity-prefixed findings with file:line   (nightshift/prompts/*.md)
 *   - the digest queued for the morning           (nightshift/report.py)
 *
 * `used` tracks the budget bar, which fills as runs complete — the same
 * counter the ledger keeps.
 */

export type LineKind = "muted" | "run" | "high" | "med" | "ok";

export interface ScriptLine {
  /** Wall-clock stamp, as the CLI prints it. */
  t: string;
  msg: string;
  kind: LineKind;
  /** Runs spent after this line, out of the 6/day default. */
  used: number;
}

export const RUN_SCRIPT: readonly ScriptLine[] = [
  {
    t: "09:14:02",
    msg: "nightshift · idle detected · running within budget",
    kind: "muted",
    used: 0,
  },
  {
    t: "09:14:03",
    msg: "→ gradagent · security_audit · claude_code",
    kind: "run",
    used: 0,
  },
  {
    t: "09:14:47",
    msg: "🔴 HIGH  api/auth.py:142 — JWT tokens never expire; set exp claim",
    kind: "high",
    used: 1,
  },
  {
    t: "09:15:10",
    msg: "→ gradagent · code_review · claude_code",
    kind: "run",
    used: 1,
  },
  {
    t: "09:15:52",
    msg: "🟠 MED   worker/queue.py:88 — unbounded retry loop",
    kind: "med",
    used: 2,
  },
  {
    t: "09:16:20",
    msg: "→ payments-web · deps_audit · claude_code",
    kind: "run",
    used: 2,
  },
  {
    t: "09:16:41",
    msg: "✓ 3 findings · 2 projects · digest queued for 06:00",
    kind: "ok",
    used: 3,
  },
] as const;

export const BUDGET_PER_DAY = 6;

/** Milliseconds per line — slow enough to read, quick enough to loop. */
export const LINE_MS = 950;

/** Beats to hold on the finished frame before looping. */
export const HOLD_BEATS = 2;

export const LINE_COLOR: Record<LineKind, string> = {
  muted: "var(--color-fg-fainter)",
  run: "var(--color-accent)",
  high: "var(--color-bad)",
  med: "var(--color-warn)",
  ok: "var(--color-ok)",
};

export const INSTALL_COMMAND = "pipx install nightshift-cli";

export const QUICKSTART = [
  "pipx install nightshift-cli",
  "nightshift init",
  "nightshift run --now",
].join("\n");

export const GITHUB_URL = "https://github.com/kishormorol/nightshift";
