import { Wordmark } from "@/components/logo";
import { GITHUB_URL } from "@/lib/run-script";

const LINKS = [
  { label: "How it works", href: "#how" },
  { label: "Providers", href: "#providers" },
  { label: "Docs", href: `${GITHUB_URL}#readme` },
];

export function Nav() {
  return (
    <header className="border-b border-line-900">
      <nav className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-4 sm:px-10">
        <a
          href="#top"
          className="rounded-sm focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent"
        >
          <Wordmark size={30} />
          <span className="sr-only">nightaudit home</span>
        </a>
        <div className="flex items-center gap-6 text-[13.5px] text-fg-dim">
          {LINKS.map((link) => (
            <a
              key={link.label}
              href={link.href}
              className="hidden transition-colors hover:text-fg-muted sm:inline"
            >
              {link.label}
            </a>
          ))}
          <a
            href={GITHUB_URL}
            className="rounded-md border border-line-500 px-3 py-1.5 font-mono text-[12.5px] text-fg-muted transition-colors hover:border-line-400 hover:text-fg"
          >
            ★ GitHub
          </a>
        </div>
      </nav>
    </header>
  );
}
