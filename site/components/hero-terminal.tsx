"use client";

import { useEffect, useState } from "react";
import {
  BUDGET_PER_DAY,
  HOLD_BEATS,
  LINE_COLOR,
  LINE_INDENT,
  LINE_MS,
  RUN_SCRIPT,
} from "@/lib/run-script";

/**
 * The fake-live terminal. Replays a recorded `nightaudit watch` on a loop.
 *
 * It renders the finished frame on the server and during the first paint, so
 * the hero is never an empty box: crawlers, RSS readers and anyone whose JS
 * hasn't arrived still see the whole run, findings and all. The animation only
 * takes over once mounted.
 */
export function HeroTerminal() {
  // `null` means "not animating yet" — the state the server renders and the
  // state the first client render must agree on, or hydration complains. The
  // interval flips it to 0 on its first tick and the replay takes over, so no
  // state is ever set from inside the effect body itself.
  const [tick, setTick] = useState<number | null>(null);

  useEffect(() => {
    const id = setInterval(() => {
      setTick((t) =>
        t === null || t + 1 > RUN_SCRIPT.length + HOLD_BEATS ? 0 : t + 1,
      );
    }, LINE_MS);
    return () => clearInterval(id);
  }, []);

  const shown = tick === null ? RUN_SCRIPT.length : Math.min(tick, RUN_SCRIPT.length);
  const lines = RUN_SCRIPT.slice(0, shown);
  const used = shown > 0 ? RUN_SCRIPT[shown - 1].used : 0;

  return (
    <div className="overflow-hidden rounded-xl border border-line-700 bg-navy-900 text-left shadow-[0_30px_70px_-30px_rgba(0,0,0,.9)]">
      <div className="flex items-center gap-2.5 border-b border-line-900 bg-navy-700 px-3.5 py-2.5">
        <div className="flex gap-1.5" aria-hidden="true">
          <span className="size-2.5 rounded-full bg-line-500" />
          <span className="size-2.5 rounded-full bg-line-500" />
          <span className="size-2.5 rounded-full bg-line-500" />
        </div>
        <span className="font-mono text-[11px] text-fg-fainter">
          nightaudit watch
        </span>
        <span className="ml-auto inline-flex items-center gap-1.5 font-mono text-[10px] text-ok">
          <span className="size-[7px] animate-rec rounded-full bg-[#6fdd8b]" />
          LIVE
        </span>
      </div>

      <div className="px-4 pt-4 pb-3.5 font-mono text-[13px] sm:min-h-[268px]">
        <div className="mb-2 text-fg-fainter">
          <span className="text-accent">$</span> nightaudit watch
        </div>

        {/* The run is a log, and a log read by a screen reader mid-replay is
            noise — announce nothing, and expose the finished transcript below. */}
        <div aria-hidden="true">
          {lines.map((line, i) =>
            // The one line here the CLI did not print: a rule standing for the
            // lines we cut. Drawn as chrome — rules and a centred count — so it
            // cannot be mistaken for output, the same treatment make-shots.py
            // gives it in the README stills.
            line.kind === "elide" ? (
              <div
                key={i}
                className="flex items-center gap-3 py-[2.5px] leading-[1.45]"
              >
                <span className="h-px flex-1 bg-line-700" />
                <span className="text-[10.5px] text-fg-ghost">{line.msg}</span>
                <span className="h-px flex-1 bg-line-700" />
              </div>
            ) : (
              <div
                key={i}
                className={`${LINE_INDENT[line.kind]} py-[2.5px] leading-[1.45] ${
                  line.kind === "meta" && i > 0 ? "mt-2.5" : ""
                }`}
              >
                <span
                  className="break-words"
                  style={{ color: LINE_COLOR[line.kind] }}
                >
                  {line.msg}
                </span>
                {line.detail ? (
                  <span className="ml-1.5 break-words text-fg-ghost">
                    {line.detail}
                  </span>
                ) : null}
              </div>
            ),
          )}
          <div className="py-[2.5px]">
            <span className="inline-block h-4 w-[9px] animate-blink bg-accent align-text-bottom" />
          </div>
        </div>

        <BudgetBar used={used} />
      </div>

      {/* The transcript, for anyone the animation cannot reach. It describes
          the same run the terminal replays and must be rewritten when the
          capture changes — it once narrated a JWT bug in a project called
          gradagent, months after neither was on screen, because nothing here
          connects the two. `test_the_hero_transcript_matches_the_run` is that
          connection. Prose rather than a line dump: a screen reader reading 14
          rows of glyphs and column padding conveys nothing. */}
      <p className="sr-only">
        A recorded nightaudit watch session. At 15:23 it reviews the nightaudit
        repository itself with Claude Code, reading the project files and
        reasoning aloud as it goes. It reports seven findings, most severe
        first: a high-severity one in nightaudit/adapters/claude_code.py at line
        267, about replacing a buffered subprocess call; a medium-severity one
        in nightaudit/lock.py at line 121; and a low-severity one in
        nightaudit/cron.py at line 27. The run finishes in 2 minutes 18 seconds
        while nobody is watching, spending 1 of the 6 runs allowed per day.
      </p>
    </div>
  );
}

function BudgetBar({ used }: { used: number }) {
  const pct = (used / BUDGET_PER_DAY) * 100;
  return (
    <div className="mt-3.5 flex items-center gap-3 border-t border-line-900 pt-3 text-xs">
      <span className="flex-none text-fg-faint">budget · claude_code</span>
      <div className="h-[7px] flex-1 overflow-hidden rounded-sm bg-line-700">
        <div
          className="h-full rounded-sm bg-accent transition-[width] duration-700 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="flex-none tabular-nums text-accent-soft">
        {used}/{BUDGET_PER_DAY} today
      </span>
    </div>
  );
}
