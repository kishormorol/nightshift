import { SectionLabel } from "@/components/busy-split";
import { GITHUB_URL } from "@/lib/run-script";

/**
 * How a run flows: cron → scheduler → gate → adapter → findings → digest.
 *
 * The identity board drew Claude Code, Codex and Copilot as three equal adapter
 * chips. They are not equals, and this list says so: a chip is only `ready` once
 * its adapter actually runs, per SPEC.md ("The page may only claim what the tool
 * does"). Codex shipped and is drawn as real; Copilot remains a documented stub
 * (nightaudit/adapters/copilot.py) and stays marked as what it is.
 */
const ADAPTERS = [
  { name: "Claude Code", ready: true },
  { name: "Codex", ready: true },
  { name: "Copilot", ready: false },
];

export function Pipeline() {
  return (
    <section id="how" className="border-t border-line-900 px-6 py-14 sm:px-10">
      <div className="mx-auto max-w-5xl">
        <SectionLabel>how a run flows</SectionLabel>

        <ol className="relative mx-auto flex max-w-4xl flex-col items-stretch gap-2 md:flex-row md:items-stretch md:justify-between">
          {/* Connector + travelling pulse. Decorative, and it sits behind the
              cards, so it must never eat a click. */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-x-[2%] top-1/2 hidden h-0.5 -translate-y-1/2 bg-[linear-gradient(90deg,#1c243f,#263050,#1c243f)] md:block"
          />
          <div
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 hidden size-[9px] -translate-y-1/2 animate-flow rounded-full bg-accent shadow-[0_0_14px_var(--color-accent)] md:block"
          />

          <Step icon="⏱" name="cron" note="your hours" />
          <Arrow />
          <Step icon="⚙" name="scheduler" note="picks tasks" />
          <Arrow />
          <Step icon="✓✓" iconTone="text-ok" name="budget ✓ idle ✓" note="gate" tight />
          <Arrow />

          <li className="relative flex-[1.4] rounded-xl border border-line-500 bg-navy-600 px-2.5 py-3 text-center shadow-[inset_0_0_0_1px_rgba(139,155,255,.08)]">
            <div className="mb-1.5 font-mono text-[9px] tracking-wider text-fg-faint">
              ADAPTERS
            </div>
            <div className="flex flex-col gap-[3px]">
              {ADAPTERS.map((a) => (
                <span
                  key={a.name}
                  className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${
                    a.ready
                      ? "bg-navy-500 text-fg-muted"
                      : "border border-dashed border-line-600 text-fg-ghost"
                  }`}
                >
                  {a.name}
                  {!a.ready && (
                    <span className="ml-1 text-[8px] tracking-wide uppercase">
                      soon
                    </span>
                  )}
                </span>
              ))}
            </div>
          </li>

          <Arrow />
          <Step icon="🔎" name="findings" note="read-only" />
          <Arrow />

          <li className="flex-1 rounded-xl border border-line-400 bg-navy-500 px-3 py-3 text-center shadow-[0_0_20px_-6px_rgba(255,215,154,.4)]">
            <div className="mb-1.5 text-[15px] text-moon" aria-hidden="true">
              ☾
            </div>
            <div className="font-mono text-[11px] text-fg">digest</div>
            <div className="mt-0.5 text-[9.5px] text-fg-fainter">06:00</div>
          </li>
        </ol>

        <p
          id="providers"
          className="mx-auto mt-7 max-w-2xl scroll-mt-8 text-center font-mono text-xs leading-relaxed text-fg-fainter"
        >
          Claude Code is the working adapter today. Codex and Copilot are
          documented stubs —{" "}
          <a
            href={`${GITHUB_URL}/issues`}
            className="text-accent-soft underline-offset-4 hover:underline"
          >
            help wanted
          </a>
          .
        </p>
      </div>
    </section>
  );
}

function Step({
  icon,
  name,
  note,
  iconTone = "",
  tight = false,
}: {
  icon: string;
  name: string;
  note: string;
  iconTone?: string;
  /** For labels long enough to wrap a trailing glyph onto its own line. */
  tight?: boolean;
}) {
  return (
    <li className="flex-1 rounded-xl border border-line-700 bg-navy-600 px-3 py-3 text-center">
      <div className={`mb-1.5 text-[15px] ${iconTone}`} aria-hidden="true">
        {icon}
      </div>
      <div
        className={`font-mono whitespace-nowrap text-fg-muted ${
          tight ? "text-[10px]" : "text-[11px]"
        }`}
      >
        {name}
      </div>
      <div className="mt-0.5 text-[9.5px] text-fg-fainter">{note}</div>
    </li>
  );
}

function Arrow() {
  return (
    <li
      aria-hidden="true"
      className="flex items-center justify-center text-[#3a4767] md:px-0"
    >
      <span className="hidden md:inline">→</span>
      <span className="md:hidden">↓</span>
    </li>
  );
}
