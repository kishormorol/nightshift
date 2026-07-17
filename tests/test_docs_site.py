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
    # Only the docs site's own URLs. A bare `/docs/(\w+)` also matches
    # raw.githubusercontent.com/.../main/docs/demo.svg, which is a file in the
    # repo and not a page — the first version of this test failed on it.
    linked = set(
        re.findall(
            r"https://(?!raw\.githubusercontent\.com|github\.com)[^)\s]+/docs/([a-z-]+)(?![\w.-])",
            text,
        )
    )
    dead = sorted(s for s in linked if s not in slugs)

    assert not dead, f"README links to docs pages that do not exist: {dead}"


def test_the_readme_has_no_relative_links():
    """PyPI renders this file with no repo to resolve against.

    `](docs/demo.svg)` is an image on GitHub and a broken one on PyPI, where the
    same markdown is the project description and there is nothing to be relative
    to. `](LICENSE)` is a 404 there. Nobody sees it unless they look at the
    package page, which is the one place a stranger decides whether to install.

    Third time this shape of bug has landed: the docs site resolved the same
    paths to /docs/docs/img/… and the og:image pointed at a host with no DNS.
    Absolute renders correctly everywhere, so there is no reason to keep a
    relative one.
    """
    text = README.read_text(encoding="utf-8")
    targets = re.findall(r"\]\(([^)]+)\)", text)
    relative = [t for t in targets if not t.startswith(("http://", "https://", "#"))]

    assert not relative, (
        "the README has relative targets, which break on PyPI:\n  "
        + "\n  ".join(relative)
    )


def test_the_site_points_at_its_own_docs(docs):
    """The nav's "Docs" link went to the GitHub README, and stayed there after
    the docs moved to /docs. The site was the last thing pointing at the old
    address, and the only visitor who would notice is one who clicked it.
    """
    nav = (ROOT / "site" / "components" / "nav.tsx").read_text(encoding="utf-8")
    labelled_docs = re.findall(r'label:\s*"Docs",\s*href:\s*(?:`|")([^`"]+)', nav)

    assert labelled_docs, "no Docs link in the site nav"
    for href in labelled_docs:
        assert href.startswith("/docs"), (
            f'the nav sends "Docs" to {href!r}; the docs are at /docs'
        )


def test_the_install_command_is_checkable(docs):
    """`pipx install nightshift-cli` for a tool called nightaudit reads as a
    typo. Wherever the site says it, it has to be possible to go and look.
    """
    hero = (ROOT / "site" / "components" / "hero.tsx").read_text(encoding="utf-8")
    install_doc = (DOCS_DIR / "installation.md").read_text(encoding="utf-8")

    assert "PYPI_URL" in hero, "the hero shows the install command with no way to verify it"
    assert "pypi.org/project/nightshift-cli" in install_doc, (
        "the installation page never links the package it tells you to install"
    )


def test_the_readme_stayed_short(docs):
    """It was 518 lines and nobody read to the bottom. The docs exist so this
    page can be a decision, not a manual — if the detail creeps back, the split
    bought nothing and there are two copies again."""
    lines = len(README.read_text(encoding="utf-8").splitlines())

    assert lines < 200, (
        f"README is {lines} lines. Detail belongs in site/content/docs — "
        f"this page is the pitch and the links."
    )
