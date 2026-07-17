"""What `init`'s repo discovery finds, and — as much — what it refuses to.

The whole reason discovery is allowed to exist is that it does not weaken the
allowlist: it proposes repositories a human then confirms. These tests pin the
proposing. The confirming is `init`'s, and lives in test_cli.py.
"""

from __future__ import annotations

from pathlib import Path

from nightaudit.discover import find_git_repos


def make_repo(path: Path) -> Path:
    """A directory that looks like a git checkout to the walker."""
    (path / ".git").mkdir(parents=True)
    return path


def test_finds_repos_one_level_down(tmp_path):
    a = make_repo(tmp_path / "a")
    b = make_repo(tmp_path / "b")
    (tmp_path / "not-a-repo").mkdir()

    assert find_git_repos(tmp_path) == [a, b]


def test_finds_repos_two_levels_down_for_org_layouts(tmp_path):
    """`~/code/org/repo` is the layout that groups repos under an owner."""
    repo = make_repo(tmp_path / "org" / "repo")

    assert find_git_repos(tmp_path) == [repo]


def test_stops_at_the_default_depth(tmp_path):
    """Three levels down is past `max_depth=2`; a scan is not a full-disk crawl."""
    make_repo(tmp_path / "a" / "b" / "too-deep")

    assert find_git_repos(tmp_path) == []


def test_a_root_that_is_itself_a_repo_returns_just_itself(tmp_path):
    make_repo(tmp_path)

    assert find_git_repos(tmp_path) == [tmp_path]


def test_does_not_descend_into_a_repo(tmp_path):
    """A repo inside a repo is a submodule or a vendored copy, not a project."""
    outer = make_repo(tmp_path / "outer")
    make_repo(outer / "vendored")

    assert find_git_repos(tmp_path) == [outer]


def test_skips_dependency_and_build_directories(tmp_path):
    """A repo under node_modules/ is code you installed, not code you wrote."""
    make_repo(tmp_path / "node_modules" / "left-pad")
    mine = make_repo(tmp_path / "mine")

    assert find_git_repos(tmp_path) == [mine]


def test_skips_hidden_directories(tmp_path):
    make_repo(tmp_path / ".cache" / "something")
    mine = make_repo(tmp_path / "mine")

    assert find_git_repos(tmp_path) == [mine]


def test_survives_an_unreadable_directory(tmp_path):
    """A permission error on one folder is no reason to abandon the scan."""
    make_repo(tmp_path / "reachable")
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o000)
    try:
        found = find_git_repos(tmp_path)
    finally:
        locked.chmod(0o755)  # so pytest can clean tmp_path up

    assert tmp_path / "reachable" in found


def test_results_are_absolute(tmp_path):
    make_repo(tmp_path / "a")

    assert all(p.is_absolute() for p in find_git_repos(tmp_path))
