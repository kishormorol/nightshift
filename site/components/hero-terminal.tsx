"use client";

import { useEffect, useState } from "react";
import {
  BUDGET_PER_DAY,
  HOLD_BEATS,
  LINE_COLOR,
  LINE_MS,
  RUN_SCRIPT,
} from "@/lib/run-script";

/**
 * The fake-live terminal. Replays a scripted `nightshift run` on a loop.
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
          nightshift run — live
        </span>
        <span className="ml-auto inline-flex items-center gap-1.5 font-mono text-[10px] text-bad">
          <span className="size-[7px] animate-rec rounded-full bg-[#ff5b52]" />
          REC
        </span>
      </div>

      <div className="px-4 pt-4 pb-3.5 font-mono text-[13px] sm:min-h-[210px]">
        <div className="mb-2 text-fg-fainter">
          <span className="text-accent">$</span> nightshift run
        </div>

        {/* The run is a log, and a log read by a screen reader mid-replay is
            noise — announce nothing, and expose the finished transcript below. */}
        <div aria-hidden="true">
          {lines.map((line, i) => (
            <div key={i} className="flex gap-3 py-[2.5px] leading-[1.4]">
              <span className="flex-none text-fg-ghost">[{line.t}]</span>
              <span
                className="min-w-0 break-words"
                style={{ color: LINE_COLOR[line.kind] }}
              >
                {line.msg}
              </span>
            </div>
          ))}
          <div className="flex gap-3 py-[2.5px]">
            <span className="text-fg-ghost">[live]</span>
            <span className="inline-block h-4 w-[9px] animate-blink bg-accent" />
          </div>
        </div>

        <BudgetBar used={used} />
      </div>

      <p className="sr-only">
        A recorded nightshift run. It reviews gradagent and payments-web, finds
        a high-severity issue at api/auth.py line 142 where JWT tokens never
        expire, a medium-severity unbounded retry loop at worker/queue.py line
        88, spends 3 of its 6 daily runs, and queues the digest for 06:00.
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
