import { GITHUB_URL } from "@/lib/run-script";

export function Footer() {
  return (
    <footer className="mt-auto border-t border-line-900 bg-[#070a10] px-6 py-6 sm:px-10">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 font-mono text-xs text-fg-fainter">
        <span>nightshift · MIT · made for the dark hours</span>
        <a
          href={GITHUB_URL}
          className="transition-colors hover:text-fg-muted"
        >
          github.com/kishormorol/nightshift
        </a>
      </div>
    </footer>
  );
}
