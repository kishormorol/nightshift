import { CopyButton } from "@/components/copy-button";
import { HeroTerminal } from "@/components/hero-terminal";
import { INSTALL_COMMAND, QUICKSTART } from "@/lib/run-script";

const STATS = [
  { value: "6", label: "runs / day", tone: "text-fg" },
  { value: "0", label: "files touched", tone: "text-ok" },
  { value: "1", label: "morning digest", tone: "text-moon" },
];

export function Hero() {
  return (
    <section id="top" className="starfield relative px-6 pt-14 pb-12 sm:px-10">
      <div className="relative mx-auto max-w-3xl text-center">
        <h1 className="mb-6 text-3xl leading-[1.15] font-semibold tracking-[-0.01em] text-balance text-fg sm:text-[30px]">
          An audit doesn&apos;t change the books.
        </h1>

        <HeroTerminal />

        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <code className="rounded-lg bg-accent px-5 py-3 font-mono text-sm font-semibold text-ink shadow-[0_0_24px_-6px_rgba(139,155,255,.8)]">
            {INSTALL_COMMAND}
          </code>
          <CopyButton text={QUICKSTART} />
        </div>

        <dl className="mt-9 flex justify-center">
          {STATS.map((stat, i) => (
            <div
              key={stat.label}
              className={`px-6 sm:px-8 ${i === 1 ? "border-x border-line-700" : ""}`}
            >
              <dd className={`text-3xl font-bold ${stat.tone}`}>{stat.value}</dd>
              <dt className="mt-0.5 font-mono text-[11px] text-fg-faint">
                {stat.label}
              </dt>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}
