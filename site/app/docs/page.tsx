import type { Metadata } from "next";
import Link from "next/link";

import { DocsNav } from "@/components/docs-nav";
import { allDocs } from "@/lib/docs";

export const metadata: Metadata = {
  title: "Docs — nightaudit",
  description:
    "How to install, configure and schedule nightaudit — read-only reviews of your projects, one digest every morning.",
};

export default function DocsIndex() {
  const docs = allDocs();
  return (
    <div className="mx-auto flex max-w-6xl gap-12 px-6 py-12 sm:px-10">
      <DocsNav docs={docs} />

      <main className="min-w-0 flex-1">
        <p className="font-mono text-[11px] tracking-wider text-fg-fainter uppercase">
          docs
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-fg">
          nightaudit
        </h1>
        <p className="mt-2 max-w-xl text-fg-faint">
          An audit doesn&apos;t change the books. Start with{" "}
          <Link href="/docs/installation" className="text-accent-soft hover:underline">
            Installation
          </Link>
          , then{" "}
          <Link href="/docs/quick-start" className="text-accent-soft hover:underline">
            Quick Start
          </Link>
          .
        </p>

        <ul className="mt-10 flex flex-col gap-px">
          {docs.map((doc) => (
            <li key={doc.slug}>
              <Link
                href={`/docs/${doc.slug}`}
                className="flex flex-col gap-0.5 rounded-lg px-3 py-3 hover:bg-navy-700"
              >
                <span className="font-mono text-sm text-fg">{doc.title}</span>
                <span className="text-[13px] text-fg-faint">{doc.description}</span>
              </Link>
            </li>
          ))}
        </ul>
      </main>
    </div>
  );
}
