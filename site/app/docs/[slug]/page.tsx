import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { DocsNav } from "@/components/docs-nav";
import { allDocs, getDoc, renderMarkdown } from "@/lib/docs";

/**
 * One docs page, rendered from `content/docs/<slug>.md` at build.
 *
 * `params` is a Promise in this version of Next and must be awaited — see
 * node_modules/next/dist/docs/01-app/03-api-reference/04-functions/generate-static-params.md.
 */

export function generateStaticParams() {
  return allDocs().map((doc) => ({ slug: doc.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const doc = getDoc(slug);
  if (!doc) return {};
  return {
    title: `${doc.title} — nightaudit docs`,
    description: doc.description,
    openGraph: { title: `${doc.title} — nightaudit`, description: doc.description },
  };
}

export default async function DocPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const doc = getDoc(slug);
  if (!doc) notFound();

  const docs = allDocs();
  const at = docs.findIndex((d) => d.slug === slug);
  const prev = docs[at - 1];
  const next = docs[at + 1];

  return (
    <div className="mx-auto flex max-w-6xl gap-12 px-6 py-12 sm:px-10">
      <DocsNav docs={docs} current={slug} />

      <main className="min-w-0 flex-1">
        <p className="font-mono text-[11px] tracking-wider text-fg-fainter uppercase">
          docs
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-fg">{doc.title}</h1>
        {doc.description ? (
          <p className="mt-2 text-fg-faint">{doc.description}</p>
        ) : null}

        {/* Our own committed markdown, rendered at build. Nothing user-supplied
            reaches this, which is what makes the raw HTML safe. */}
        <article
          className="prose-docs mt-8"
          dangerouslySetInnerHTML={{ __html: renderMarkdown(doc.body) }}
        />

        <nav className="mt-16 flex justify-between gap-4 border-t border-line-900 pt-6 text-sm">
          {prev ? (
            <Link href={`/docs/${prev.slug}`} className="text-accent-soft hover:underline">
              ← {prev.title}
            </Link>
          ) : (
            <span />
          )}
          {next ? (
            <Link href={`/docs/${next.slug}`} className="text-accent-soft hover:underline">
              {next.title} →
            </Link>
          ) : (
            <span />
          )}
        </nav>
      </main>
    </div>
  );
}
