import Link from "next/link";

import type { Doc } from "@/lib/docs";

/** The sidebar. Reading order, which is why `order` exists in the frontmatter. */
export function DocsNav({ docs, current }: { docs: Doc[]; current?: string }) {
  return (
    <nav
      aria-label="Documentation"
      className="hidden w-52 shrink-0 md:block"
    >
      <div className="sticky top-12">
        <Link
          href="/"
          className="font-mono text-[13px] text-fg-muted hover:text-fg"
        >
          ← nightaudit
        </Link>
        <ul className="mt-6 flex flex-col gap-0.5">
          {docs.map((doc) => (
            <li key={doc.slug}>
              <Link
                href={`/docs/${doc.slug}`}
                aria-current={doc.slug === current ? "page" : undefined}
                className={`block rounded px-2 py-1 text-[13px] ${
                  doc.slug === current
                    ? "bg-navy-600 text-fg"
                    : "text-fg-faint hover:text-fg-muted"
                }`}
              >
                {doc.title}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}
