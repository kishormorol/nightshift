import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { marked } from "marked";

/**
 * The docs, read from `content/docs/*.md` at build.
 *
 * The markdown is the source and the only copy. These pages were the README's
 * middle — the configuration table, the read-only argument, the budget maths —
 * and they moved here whole rather than being retyped, because a second copy of
 * a sentence is a sentence that will be wrong in a month. This repo has shipped
 * that bug more than once: a hero advertising a CLI format the CLI had dropped,
 * an og:image citing findings from a run that no longer existed. Both were
 * hand-typed from something true at the time.
 *
 * So the README now links here rather than repeating it, and
 * `tests/test_docs_site.py` fails if the two ever say the same thing twice.
 *
 * Content lives under `site/` and not the repo's `docs/` for a dull reason worth
 * writing down: Railway builds this service with `site/` as its root, so `../`
 * does not exist at build time. Repo-root markdown would work locally and break
 * on deploy — which is the worst shape a bug can take.
 */

const DOCS_DIR = join(process.cwd(), "content", "docs");

export interface Doc {
  slug: string;
  title: string;
  description: string;
  order: number;
  /** The markdown body, frontmatter stripped. */
  body: string;
}

/** `--- title: "x" ---` → the pairs, and the body after it. */
function parseFrontmatter(raw: string): [Record<string, string>, string] {
  const match = /^---\n([\s\S]*?)\n---\n/.exec(raw);
  if (!match) return [{}, raw];
  const meta: Record<string, string> = {};
  for (const line of match[1].split("\n")) {
    const at = line.indexOf(":");
    if (at === -1) continue;
    meta[line.slice(0, at).trim()] = line
      .slice(at + 1)
      .trim()
      .replace(/^"|"$/g, "");
  }
  return [meta, raw.slice(match[0].length)];
}

export function allDocs(): Doc[] {
  const docs = readdirSync(DOCS_DIR)
    .filter((f) => f.endsWith(".md"))
    .map((file) => {
      const [meta, body] = parseFrontmatter(readFileSync(join(DOCS_DIR, file), "utf-8"));
      const slug = file.replace(/\.md$/, "");
      if (!meta.title) throw new Error(`content/docs/${file} has no title in its frontmatter`);
      return {
        slug,
        title: meta.title,
        description: meta.description ?? "",
        // Unordered pages would sort alphabetically, which puts Uninstall
        // before Quick Start. The nav is a reading order, not a listing.
        order: Number(meta.order ?? 999),
        body,
      };
    });
  return docs.sort((a, b) => a.order - b.order || a.slug.localeCompare(b.slug));
}

export function getDoc(slug: string): Doc | undefined {
  return allDocs().find((d) => d.slug === slug);
}

export function renderMarkdown(body: string): string {
  // Sync, and the input is our own committed markdown — no user content ever
  // reaches this, which is what makes the raw HTML safe downstream.
  return marked.parse(body, { async: false, gfm: true });
}
