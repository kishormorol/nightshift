const TICKS = ["09:00", "11:00", "13:00", "15:00", "17:00", "18:00"];

const YOUR_DAY = [
  { label: "feature work", span: "flex-[3]" },
  { label: "meetings", span: "flex-[2]" },
  { label: "PR reviews", span: "flex-[2]" },
  { label: "ship", span: "flex-1" },
];

const ITS_DAY = [
  { label: "✓ security", tone: "text-ok", border: "border-[#1c2b1f]", span: "flex-[2]" },
  { label: "🔴 review", tone: "text-bad", border: "border-[#3a1c1a]", span: "flex-[2]" },
  { label: "✓ deps", tone: "text-ok", border: "border-[#1c2b1f]", span: "flex-[2]" },
  { label: "🟠 docs", tone: "text-warn", border: "border-[#3a331a]", span: "flex-[2]" },
  { label: "✓", tone: "text-ok", border: "border-[#1c2b1f]", span: "flex-1" },
];

/**
 * The two-row gantt: your day against its night.
 *
 * The bars need width to say anything — below ~440px they truncate to
 * "feature …" / "meet…" and the comparison is lost. So the label column stays
 * pinned and only the bars scroll, which keeps the two rows readable and still
 * aligned with each other on a phone.
 */
export function BusySplit() {
  return (
    <section className="border-t border-line-900 bg-navy-850 px-6 py-13 sm:px-10">
      <div className="mx-auto max-w-5xl">
        <SectionLabel>while you were busy</SectionLabel>

        <div className="flex gap-3.5">
          {/* Wide enough for the icon plus "nightaudit" at 12px mono — any
              narrower and the label truncates to "nights…". */}
          <div className="flex w-[116px] flex-none flex-col sm:w-[118px]">
            <div className="h-5" aria-hidden="true" />
            <RowLabel icon="◐" tone="text-accent-soft" bg="bg-line-700" name="you" />
            <div className="h-3" aria-hidden="true" />
            <RowLabel icon="☾" tone="text-moon" bg="bg-navy-500" name="nightaudit" />
          </div>

          <div className="min-w-0 flex-1 overflow-x-auto">
            <div className="min-w-[420px]">
              {/* Ticks label the bars below, which carry their own text —
                  reading six bare clock times aloud would add nothing. */}
              <div
                aria-hidden="true"
                className="flex h-5 justify-between px-1 font-mono text-[11px] text-fg-ghost"
              >
                {TICKS.map((t) => (
                  <span key={t}>{t}</span>
                ))}
              </div>

              <div className="flex h-8 gap-1">
                {YOUR_DAY.map((block) => (
                  <div
                    key={block.label}
                    className={`${block.span} flex items-center truncate rounded-md bg-navy-400 px-2.5 text-[11px] text-fg-dim`}
                  >
                    {block.label}
                  </div>
                ))}
              </div>

              <div className="h-3" />

              <div className="flex h-8 gap-1">
                {ITS_DAY.map((block, i) => (
                  <div
                    key={i}
                    className={`${block.span} ${block.border} ${block.tone} flex items-center truncate rounded-md border bg-navy-600 px-2.5 font-mono text-[11px]`}
                  >
                    {block.label}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <p className="mt-7 text-center text-sm text-balance text-fg-dim">
          You never opened a terminal. It ran{" "}
          <strong className="font-semibold text-fg">6 reviews</strong> across your
          projects.
        </p>
      </div>
    </section>
  );
}

function RowLabel({
  icon,
  tone,
  bg,
  name,
}: {
  icon: string;
  tone: string;
  bg: string;
  name: string;
}) {
  return (
    <div className="flex h-8 items-center gap-2.5">
      <span
        aria-hidden="true"
        className={`flex size-[26px] flex-none items-center justify-center rounded-full text-[13px] ${bg} ${tone}`}
      >
        {icon}
      </span>
      <span className="truncate font-mono text-xs text-fg-muted">{name}</span>
    </div>
  );
}

export function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-7 text-center">
      <span className="font-mono text-xs tracking-[0.16em] text-fg-faint uppercase">
        {children}
      </span>
    </div>
  );
}
