import { SectionLabel } from "@/components/busy-split";

/**
 * The payoff: what you actually wake up to.
 *
 * The board showed two filled budget bars, claude_code and codex. Only
 * claude_code runs today, so codex is drawn as what it is — disabled — rather
 * than as a provider that quietly did four runs overnight.
 */
const BUDGETS = [
  { name: "claude_code", filled: 3, total: 6, enabled: true },
  { name: "codex", filled: 0, total: 6, enabled: false },
];

const FINDINGS = [
  { sev: "🔴", text: "SQL string interpolation", ref: "query.ts:88" },
  { sev: "🔴", text: "Unpinned base image", ref: "Dockerfile:1" },
  { sev: "🟠", text: "Missing auth guard", ref: "metrics.py:42" },
];

export function DigestPayoff() {
  return (
    <section className="border-t border-line-900 bg-[radial-gradient(120%_90%_at_50%_120%,#17203f_0%,#0b1122_60%)] px-6 py-14 sm:px-10">
      <SectionLabel>you wake up to this · 06:00</SectionLabel>

      <div className="mx-auto max-w-xl">
        {/* Laptop shell */}
        <div className="rounded-t-2xl border border-line-500 bg-navy-700 px-2.5 pt-2.5">
          <div className="overflow-hidden rounded-lg border border-line-700 bg-[#0b0f1c]">
            <div className="px-4 py-4">
              <div className="mb-3 flex items-center gap-2.5 border-b border-line-800 pb-3">
                <div
                  className="moon size-[22px] flex-none text-[22px]"
                  aria-hidden="true"
                />
                <span className="font-mono text-sm text-fg">
                  Nightaudit · morning digest
                </span>
                <span className="ml-auto font-mono text-[10px] text-fg-fainter">
                  Jul 14
                </span>
              </div>

              <div className="mb-3.5 flex flex-col gap-1.5 font-mono text-[11px]">
                {BUDGETS.map((b) => (
                  <div key={b.name} className="flex items-center gap-2.5">
                    <span
                      className={`w-[76px] ${b.enabled ? "text-fg-muted" : "text-fg-ghost"}`}
                    >
                      {b.name}
                    </span>
                    <span aria-hidden="true">
                      <span className="text-accent">{"▓".repeat(b.filled)}</span>
                      <span className="text-line-600">
                        {"░".repeat(b.total - b.filled)}
                      </span>
                    </span>
                    <span className="text-fg-faint">
                      {b.enabled ? `${b.filled}/${b.total}` : "disabled"}
                    </span>
                  </div>
                ))}
              </div>

              <ul className="flex flex-col gap-2">
                {FINDINGS.map((f) => (
                  <li key={f.ref} className="flex gap-2.5 text-xs text-fg-muted">
                    <span aria-hidden="true">{f.sev}</span>
                    <span>
                      {f.text} — <span className="text-accent-soft">{f.ref}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
        <div
          aria-hidden="true"
          className="h-3.5 rounded-b-2xl border border-t-0 border-line-500 bg-[linear-gradient(180deg,#1a2036,#0d1326)]"
        />
        <div aria-hidden="true" className="mx-auto h-1.5 w-32 rounded-b-md bg-[#141a2e]" />
      </div>

      <p className="mx-auto mt-7 max-w-xl text-center text-lg text-balance text-[#e6ecf5]">
        Triage over coffee.{" "}
        <span className="text-fg-dim">
          Highest severity first, grouped by project, read in twenty seconds.
        </span>
      </p>
    </section>
  );
}
