/**
 * The run the hero terminal replays.
 *
 * **The format here is verbatim.** Every glyph, every column, every header and
 * footer is what `nightshift watch` actually prints — checked against real
 * captured output, not remembered:
 *
 *   ┌ project · task   provider · HH:MM:SS   run began   (cli.py `_render_log_event`)
 *     ⏺ Tool(input)                          a tool call (cli.py `_render_event`)
 *       ⎿  one-line result                   what it returned
 *     ✻ thinking                             the agent reasoning
 *     🔴 HIGH  ref · text                    a finding   (report.py `parse_finding_line`)
 *   └ ✓ ok   1m42s · 2 findings              the outcome
 *
 * **The projects and findings are illustrative.** Real captured output reviews
 * nightshift's own internals — true, but unreadable to someone meeting the tool
 * for the first time. So the shape is real and the subject is an example, which
 * is the honest trade for a hero: a visitor should recognise the output when
 * they run it, and picture their own repo in it.
 *
 * Two runs, because that is what a watcher sees over a night — cron ticks, the
 * queue rotates to the next (project, task) pair, and the budget ticks up one
 * per completed run. `used` drives the bar, the same counter the ledger keeps.
 */

export type LineKind =
  | "banner" // what `watch` prints while idle
  | "meta" // ┌ a run began
  | "tool" // ⏺ a tool call
  | "result" // ⎿ what it returned
  | "thinking" // ✻ reasoning
  | "prose" // narration, capped at two lines in the real renderer
  | "high"
  | "med"
  | "end"; // └ the outcome

export interface ScriptLine {
  kind: LineKind;
  /** The line itself, as printed. */
  msg: string;
  /** Trailing dim text: tool input, timings, counts. */
  detail?: string;
  /** Runs spent once this line has printed, out of the 6/day default. */
  used: number;
}

export const RUN_SCRIPT: readonly ScriptLine[] = [
  {
    kind: "banner",
    msg: "nightshift · watching for runs — ctrl-c to stop",
    used: 0,
  },

  // 02:14 — cron ticks, the gate opens, the queue hands over the first pair.
  {
    kind: "meta",
    msg: "┌ gradagent · security_audit",
    detail: "claude_code · 02:14:03",
    used: 0,
  },
  { kind: "tool", msg: "⏺ Grep", detail: "(pattern: jwt|token|secret)", used: 0 },
  { kind: "result", msg: "⎿  api/auth.py:142", detail: "(+18 lines)", used: 0 },
  { kind: "thinking", msg: "✻ thinking", used: 0 },
  {
    kind: "prose",
    msg: "The tokens are signed, but I can't find an expiry claim anywhere.",
    used: 0,
  },
  {
    kind: "high",
    msg: "🔴 HIGH  api/auth.py:142",
    detail: "· JWT tokens never expire; set an exp claim",
    used: 0,
  },
  { kind: "end", msg: "└ ✓ ok", detail: "1m42s · 2 findings", used: 1 },

  // 03:09 — next tick, next pair. Nobody is awake for either of them.
  {
    kind: "meta",
    msg: "┌ payments-web · code_review",
    detail: "claude_code · 03:09:20",
    used: 1,
  },
  {
    kind: "tool",
    msg: "⏺ Read",
    detail: "(file_path: worker/queue.py)",
    used: 1,
  },
  {
    kind: "med",
    msg: "🟠 MED   worker/queue.py:88",
    detail: "· retry loop has no ceiling",
    used: 1,
  },
  { kind: "end", msg: "└ ✓ ok", detail: "2m20s · 3 findings", used: 2 },
] as const;

export const BUDGET_PER_DAY = 6;

/** Milliseconds per line — slow enough to read, quick enough to loop. */
export const LINE_MS = 850;

/** Beats to hold on the finished frame before looping. */
export const HOLD_BEATS = 3;

/** Indent per kind, mirroring the renderer's own columns. */
export const LINE_INDENT: Record<LineKind, string> = {
  banner: "pl-0",
  meta: "pl-0",
  tool: "pl-2",
  result: "pl-6",
  thinking: "pl-2",
  prose: "pl-4",
  high: "pl-2",
  med: "pl-2",
  end: "pl-0",
};

export const LINE_COLOR: Record<LineKind, string> = {
  banner: "var(--color-fg-ghost)",
  meta: "var(--color-fg)",
  tool: "var(--color-accent)",
  result: "var(--color-fg-ghost)",
  // The agent thinking in the small hours; the moon is the identity's own
  // second colour and the one moment in a run that earns it.
  thinking: "var(--color-moon)",
  prose: "var(--color-fg-faint)",
  high: "var(--color-bad)",
  med: "var(--color-warn)",
  end: "var(--color-ok)",
};

export const INSTALL_COMMAND = "pipx install nightshift-cli";

export const QUICKSTART = [
  "pipx install nightshift-cli",
  "nightshift init",
  "nightshift run --now",
].join("\n");

export const GITHUB_URL = "https://github.com/kishormorol/nightshift";
