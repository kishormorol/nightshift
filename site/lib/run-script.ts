/**
 * How the hero terminal replays a run. The run itself is generated — see
 * `run-script.generated.ts` and `docs/make-run-script.py`.
 *
 * This file used to hold the script by hand, and said of it: *the projects and
 * findings are illustrative — real captured output reviews nightaudit's own
 * internals, true but unreadable to someone meeting the tool for the first
 * time.* That was a considered trade, disclosed where it was made, and it is
 * the reason `gradagent` and a JWT bug lived here for months.
 *
 * It is reversed now, for a reason the trade did not anticipate: the shape was
 * supposed to be the real part, and twice it was not. The identity board's
 * invented `[09:14] → project · task` shipped in this hero, was fixed by
 * teaching the CLI to print a real framed log, and then reappeared in the
 * og:image under a comment about not lying. A hand-typed file has no way to
 * tell the difference between a subject that is illustrative on purpose and a
 * format that is wrong by accident. Generating it removes the question: the
 * only way to change what the hero shows is to change what the CLI printed.
 *
 * The cost is real and was correctly identified — a visitor now meets findings
 * about `nightaudit/adapters/claude_code.py` rather than an auth bug they would
 * recognise. What they get back is that it happened. The README already leans on
 * this ("those are real bugs"), and so does the og:image; the hero was the last
 * place telling a different story.
 *
 * `used` drives the budget bar, the same counter the ledger keeps — one per
 * completed run, ticking on `└`.
 */

export type LineKind =
  | "banner" // what `watch` prints while idle
  | "meta" // ┌ a run began
  | "start" // ⏺ the project dir, as the adapter opens
  | "tool" // ⏺ a tool call
  | "result" // ⎿ what it returned
  | "thinking" // ✻ reasoning
  | "prose" // narration, capped at two lines in the real renderer
  | "high"
  | "med"
  | "low"
  | "elide" // not the CLI: our rule over lines we cut. See make-run-script.py.
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

export { RUN_SCRIPT } from "@/lib/run-script.generated";

export const BUDGET_PER_DAY = 6;

/** Milliseconds per line — slow enough to read, quick enough to loop. */
export const LINE_MS = 850;

/** Beats to hold on the finished frame before looping. */
export const HOLD_BEATS = 3;

/** Indent per kind, mirroring the renderer's own columns. */
export const LINE_INDENT: Record<LineKind, string> = {
  banner: "pl-0",
  meta: "pl-0",
  start: "pl-2",
  tool: "pl-2",
  result: "pl-6",
  thinking: "pl-2",
  prose: "pl-4",
  high: "pl-2",
  med: "pl-2",
  low: "pl-2",
  elide: "pl-0",
  end: "pl-0",
};

export const LINE_COLOR: Record<LineKind, string> = {
  banner: "var(--color-fg-ghost)",
  meta: "var(--color-fg)",
  // `start` and `tool` share the ⏺ glyph and differ by colour in the terminal —
  // green for the project opening, cyan for each call. Same here.
  start: "var(--color-ok)",
  tool: "var(--color-accent)",
  result: "var(--color-fg-ghost)",
  // The agent thinking in the small hours; the moon is the identity's own
  // second colour and the one moment in a run that earns it.
  thinking: "var(--color-moon)",
  prose: "var(--color-fg-faint)",
  // Mirrors cli.py's `_SEVERITY_FG`: HIGH red, MED yellow, LOW cyan — and cyan
  // is what a tool call is too, so `low` and `tool` share a colour here exactly
  // as they do in the terminal. Not a collision; the same one.
  high: "var(--color-bad)",
  med: "var(--color-warn)",
  low: "var(--color-accent)",
  // Chrome, not output — dim enough to read as ours rather than the CLI's.
  elide: "var(--color-fg-ghost)",
  end: "var(--color-ok)",
};

export const INSTALL_COMMAND = "pipx install nightshift-cli";

export const QUICKSTART = [
  "pipx install nightshift-cli",
  "nightaudit init",
  "nightaudit run --now",
].join("\n");

export const GITHUB_URL = "https://github.com/kishormorol/nightaudit";
