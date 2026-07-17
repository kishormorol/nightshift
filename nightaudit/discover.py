"""Find git repositories under a folder, so ``init`` can offer them.

``init`` registers an explicit allowlist: every project it schedules is one a
human named. That is deliberate — this tool hands whole directories to an AI
CLI, and "review everything on the disk" is the wrong default. Discovery does
not change that rule; it only saves the typing. What it finds is *offered*, and
nothing is registered until the person says yes.
"""

from __future__ import annotations

from pathlib import Path

#: Directories never worth descending into. A repository found inside one of
#: these is vendored, a dependency, or a build artifact — someone else's code,
#: not a project you chose to work on. Skipping them also keeps the scan fast.
_SKIP = frozenset(
    {
        "node_modules",
        "venv",
        ".venv",
        "__pycache__",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        "site-packages",
        ".cargo",
        ".rustup",
        ".gradle",
        "Library",
        ".Trash",
    }
)


def find_git_repos(root: Path, max_depth: int = 2) -> list[Path]:
    """Absolute paths of git repositories under ``root``, shallowest first.

    ``max_depth`` counts directory levels below ``root``: depth 1 is its
    immediate children, and the default 2 also covers the ``~/code/org/repo``
    layout that groups repositories under an owner. If ``root`` is itself a
    repository the result is just ``[root]``.

    The walk stops the moment it reaches a ``.git`` — a repository nested inside
    another is a submodule or a vendored copy, not a separate project — and it
    never enters a hidden directory or one of the build/dependency directories
    in :data:`_SKIP`, where every hit would be code you did not write.

    Unreadable directories are skipped, not raised: ``init`` is a convenience,
    and a permission error on one folder is no reason to abandon the scan.
    """
    root = root.expanduser().absolute()
    found: list[Path] = []

    def walk(directory: Path, depth: int) -> None:
        try:
            is_repo = (directory / ".git").exists()
        except OSError:
            return  # can't even stat inside it — unreadable, skip
        if is_repo:
            found.append(directory)
            return  # a repo is a leaf; a repo inside it is not our concern
        if depth >= max_depth:
            return
        try:
            children = sorted(c for c in directory.iterdir() if c.is_dir())
        except OSError:
            return  # unreadable, gone, or not a directory after all — skip it
        for child in children:
            if child.name in _SKIP or child.name.startswith("."):
                continue
            walk(child, depth + 1)

    walk(root, 0)
    return found
