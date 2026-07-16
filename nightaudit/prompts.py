"""Prompt template resolution.

Two sources, in order: the user's own ``~/.nightaudit/prompts/`` and the
templates packaged with nightaudit. Any ``.md`` file in either directory is a
valid task name, so a user can add a task by dropping in a file — and can
override a shipped template by using the same filename.
"""

from __future__ import annotations

from pathlib import Path

from nightaudit.config import state_dir

PACKAGED_PROMPTS = Path(__file__).parent / "prompts"


class PromptError(Exception):
    """A prompt template could not be resolved."""


def user_prompts() -> Path:
    return state_dir() / "prompts"


def prompt_dirs() -> list[Path]:
    """Search path, highest precedence first."""
    return [user_prompts(), PACKAGED_PROMPTS]


def available_tasks() -> list[str]:
    """Every task name resolvable right now."""
    tasks: set[str] = set()
    for directory in prompt_dirs():
        if not directory.is_dir():
            continue
        for path in directory.glob("*.md"):
            if path.is_file():
                tasks.add(path.stem)
    return sorted(tasks)


def find(task: str) -> Path | None:
    for directory in prompt_dirs():
        candidate = directory / f"{task}.md"
        if candidate.is_file():
            return candidate
    return None


def load(task: str) -> str:
    """Read the template for ``task``."""
    path = find(task)
    if path is None:
        known = ", ".join(available_tasks()) or "none found"
        raise PromptError(
            f"no prompt template for task {task!r} — looked in "
            f"{', '.join(str(d) for d in prompt_dirs())}. Available tasks: {known}"
        )
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise PromptError(f"cannot read prompt {path}: {exc}") from exc
    if not text:
        raise PromptError(f"prompt template {path} is empty")
    return text
