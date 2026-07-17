"""The README and the docs must not say the same thing twice.

The README used to carry all 518 lines of it. The docs site now carries the
detail and the README points at it, which is only an improvement while there is
exactly one copy of each sentence. Two copies is not documentation, it is a
promise to keep them in step — and this repo has already broken that promise
several times over, each time in a way nobody noticed for months: a hero
advertising a CLI format the CLI had dropped, an og:image citing findings from a
run that no longer existed, a screen-reader transcript describing a project that
was never on screen.

Every one of those was true when it was typed. That is the failure mode. Nothing
warns you, because nothing is comparing.

So: these tests compare.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
DOCS_DIR = ROOT / "site" / "content" / "docs"
PAGE = ROOT / "site" / "app" / "docs" / "[slug]" / "page.tsx"
PUBLIC_IMG = ROOT / "site" / "public" / "img"


def paragraphs(text: str) -> list[str]:
    """Prose paragraphs, with code fences and tables dropped.

    Code blocks are exempt on purpose: `pipx install nightshift-cli` belongs in
    both places, and a shared command is not a duplicated explanation. Prose is
    what rots.
    """
    without_fences = re.sub(r"```.*?```", "", text, flags=re.S)
    out = []
    for block in without_fences.split("\n\n"):
        block = " ".join(block.split())
        if not block or block.startswith(("#", "|", "-", "*", ">", "[!")):
            continue
        out.append(block)
    return out


@pytest.fixture(scope="module")
def docs() -> list[Path]:
    return sorted(DOCS_DIR.glob("*.md"))


def test_there_are_docs(docs):
    assert docs, f"no markdown under {DOCS_DIR.relative_to(ROOT)}"


def test_the_readme_does_not_repeat_the_docs(docs):
    """The exact bug this split exists to prevent.

    A paragraph in both places is one someone will fix in one of them.
    """
    readme = set(paragraphs(README.read_text(encoding="utf-8")))
    dupes = []
    for path in docs:
        for para in paragraphs(path.read_text(encoding="utf-8")):
            if len(para) > 80 and para in readme:
                dupes.append(f"{path.name}: {para[:70]}…")

    assert not dupes, "the README repeats the docs verbatim:\n  " + "\n  ".join(dupes)


def test_every_doc_has_the_frontmatter_the_site_reads(docs):
    """`allDocs()` throws on a missing title, and orders by `order`. A page
    without one sorts to 999 and lands at the end of the nav silently."""
    problems = []
    for path in docs:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            problems.append(f"{path.name}: no frontmatter")
            continue
        head = text.split("---", 2)[1]
        for key in ("title", "description", "order"):
            if not re.search(rf"^{key}:", head, re.M):
                problems.append(f"{path.name}: no {key}")

    assert not problems, "\n  ".join(problems)


def test_the_nav_order_is_unambiguous(docs):
    """Two pages sharing an `order` fall back to slug order, which is a coin
    toss dressed as a decision."""
    orders = {}
    for path in docs:
        m = re.search(r"^order:\s*(\d+)", path.read_text(encoding="utf-8"), re.M)
        if m:
            orders.setdefault(int(m.group(1)), []).append(path.name)
    clashes = {o: names for o, names in orders.items() if len(names) > 1}

    assert not clashes, f"pages share an order: {clashes}"


def test_the_docs_never_use_repo_relative_paths(docs):
    """`docs/img/x.svg` reads fine on GitHub and 404s on the site, where it
    resolves against `/docs/<slug>/`. These files are rendered only by the site,
    so their links have to be the site's."""
    strays = []
    for path in docs:
        for link in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if link.startswith(("http://", "https://", "/", "#")):
                continue
            strays.append(f"{path.name}: {link}")

    assert not strays, (
        "repo-relative links in docs rendered at /docs/<slug>:\n  " + "\n  ".join(strays)
    )


def test_every_image_the_docs_reference_is_served(docs):
    """The site cannot read `../docs`, so `make-shots.py` writes `site/public/img`
    too. A missing file here is a broken image on a page that still builds."""
    missing = []
    for path in docs:
        for src in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if not src.startswith("/img/"):
                continue
            if not (PUBLIC_IMG / Path(src).name).is_file():
                missing.append(f"{path.name}: {src}")

    assert not missing, (
        "docs reference images that are not in site/public/img:\n  " + "\n  ".join(missing)
    )


def test_the_readme_links_reach_real_pages(docs):
    """The README is now mostly a table of links into the docs. A typo'd slug is
    a dead link on the first page anyone reads."""
    slugs = {p.stem for p in docs}
    text = README.read_text(encoding="utf-8")
    linked = set(re.findall(r"/docs/([a-z-]+)\b", text))
    dead = sorted(s for s in linked if s not in slugs)

    assert not dead, f"README links to docs pages that do not exist: {dead}"


def test_the_readme_stayed_short(docs):
    """It was 518 lines and nobody read to the bottom. The docs exist so this
    page can be a decision, not a manual — if the detail creeps back, the split
    bought nothing and there are two copies again."""
    lines = len(README.read_text(encoding="utf-8").splitlines())

    assert lines < 200, (
        f"README is {lines} lines. Detail belongs in site/content/docs — "
        f"this page is the pitch and the links."
    )
