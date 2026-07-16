"""Load and validate ``~/.nightaudit/config.yaml``.

Every failure raised from here is meant to be read by a human at a terminal, so
messages name the offending field and say what a valid value looks like.
"""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

import yaml

KNOWN_PROVIDERS = ("claude_code", "codex", "copilot")

DEFAULT_STATE_DIR = Path("~/.nightaudit")
DEFAULT_DIGEST_DIR = Path("~/nightaudit-reports")
DEFAULT_WINDOWS = ("00:00-06:00",)
DEFAULT_IDLE_MINUTES = 60
DEFAULT_TIMEOUT_S = 600
DEFAULT_MAX_RUNS_PER_DAY = 6
DEFAULT_MAX_RUNS_PER_WEEK = 30
#: Checks are local commands, not model calls — a test suite that hasn't spoken
#: in two minutes is likely wedged. Raise it per check for a genuinely slow one.
DEFAULT_CHECK_TIMEOUT_S = 120

_TASK_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_WINDOW_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*$")


class ConfigError(Exception):
    """A human-readable configuration problem."""


def expand(p: str | Path) -> Path:
    """Expand ``~`` and ``$VARS``, returning an absolute path."""
    return Path(os.path.expandvars(os.path.expanduser(str(p)))).absolute()


def state_dir() -> Path:
    """Where ledger/queue/lock/config live. Override with ``NIGHTAUDIT_HOME``."""
    return expand(os.environ.get("NIGHTAUDIT_HOME", DEFAULT_STATE_DIR))


def config_path() -> Path:
    return state_dir() / "config.yaml"


@dataclass(frozen=True)
class Budget:
    max_runs_per_day: int = DEFAULT_MAX_RUNS_PER_DAY
    max_runs_per_week: int = DEFAULT_MAX_RUNS_PER_WEEK


@dataclass(frozen=True)
class Provider:
    name: str
    enabled: bool = False
    budget: Budget = field(default_factory=Budget)
    #: Where the CLI lives, when it isn't simply on PATH under its usual name.
    #: ``None`` means "look up the adapter's default name on PATH". Set this for
    #: an install that PATH can't see — Codex bundled inside ChatGPT.app, say.
    binary: str | None = None


@dataclass(frozen=True)
class Check:
    """One command of the user's own, run in the project directory.

    Unlike a task — which is a prompt handed to a read-only AI — a check is
    executed. nightaudit makes no attempt to sandbox it: it runs as the user who
    runs nightaudit, with their permissions, and may write whatever it likes.
    ``pytest`` leaves ``.pytest_cache/`` behind because it was asked to.
    """

    name: str
    run: str
    timeout_s: int = DEFAULT_CHECK_TIMEOUT_S

    @property
    def argv(self) -> list[str]:
        """The command as a list. Parsed at config time, so it can't fail here."""
        return shlex.split(self.run)


@dataclass(frozen=True)
class Project:
    name: str
    path: Path
    tasks: tuple[str, ...]
    #: Pin this project to one provider. ``None`` means "whichever enabled
    #: provider can run right now". A pin is hard: if the named provider is out
    #: of budget, still in use, or not installed, the project waits rather than
    #: being reviewed by someone else.
    provider: str | None = None
    #: Commands to run before the review. Empty for a project that only wants
    #: an AI to read it, which is every project until someone asks otherwise.
    checks: tuple[Check, ...] = ()


@dataclass(frozen=True)
class Window:
    """A local-time window. ``start > end`` means it crosses midnight."""

    start: time
    end: time
    raw: str

    @property
    def crosses_midnight(self) -> bool:
        return self.start > self.end

    def contains(self, t: time) -> bool:
        if self.crosses_midnight:
            # e.g. 22:00-06:00 — inside if at/after start OR before end.
            return t >= self.start or t < self.end
        return self.start <= t < self.end


@dataclass(frozen=True)
class Schedule:
    windows: tuple[Window, ...]
    idle_minutes: int = DEFAULT_IDLE_MINUTES

    def is_open(self, now: datetime) -> bool:
        return any(w.contains(now.time()) for w in self.windows)

    def next_open(self, now: datetime) -> datetime | None:
        """The next minute at which a window opens, searching 48h ahead."""
        if self.is_open(now):
            return now
        probe = now.replace(second=0, microsecond=0)
        for _ in range(48 * 60):
            probe += timedelta(minutes=1)
            if self.is_open(probe):
                return probe
        return None


@dataclass(frozen=True)
class Config:
    providers: dict[str, Provider]
    projects: tuple[Project, ...]
    schedule: Schedule
    digest_dir: Path
    timeout_s: int = DEFAULT_TIMEOUT_S
    source: Path | None = None

    def enabled_providers(self) -> list[Provider]:
        return [p for p in self.providers.values() if p.enabled]

    def provider(self, name: str) -> Provider:
        try:
            return self.providers[name]
        except KeyError:
            raise ConfigError(f"unknown provider {name!r}") from None

    def pairs(self) -> list[tuple[str, str]]:
        """Every ``(project, task)`` combination, in config order."""
        return [(p.name, t) for p in self.projects for t in p.tasks]


def _require_mapping(value: Any, where: str) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{where}: expected a mapping, got {_typename(value)}")
    return value


def _typename(value: Any) -> str:
    return type(value).__name__


def _parse_positive_int(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{where}: expected a whole number, got {value!r}")
    if value <= 0:
        raise ConfigError(f"{where}: must be greater than 0, got {value}")
    return value


def parse_window(raw: Any, where: str) -> Window:
    if not isinstance(raw, str):
        raise ConfigError(f'{where}: expected a string like "09:00-18:00", got {raw!r}')
    m = _WINDOW_RE.match(raw)
    if not m:
        raise ConfigError(f'{where}: expected "HH:MM-HH:MM", got {raw!r}')
    sh, sm, eh, em = (int(g) for g in m.groups())
    for hh, mm, side in ((sh, sm, "start"), (eh, em, "end")):
        if hh > 23 or mm > 59:
            raise ConfigError(
                f"{where}: {side} time {hh:02d}:{mm:02d} is not a real clock time "
                f'(in {raw!r})'
            )
    start, end = time(sh, sm), time(eh, em)
    if start == end:
        raise ConfigError(
            f"{where}: {raw!r} starts and ends at the same time — a window must "
            f'have a duration (use "00:00-23:59" for all day)'
        )
    return Window(start=start, end=end, raw=raw.strip())


def _parse_budget(raw: Any, where: str) -> Budget:
    data = _require_mapping(raw, where)
    unknown = set(data) - {"max_runs_per_day", "max_runs_per_week"}
    if unknown:
        raise ConfigError(
            f"{where}: unknown field(s) {sorted(unknown)} — "
            f"expected max_runs_per_day, max_runs_per_week"
        )
    day = data.get("max_runs_per_day", DEFAULT_MAX_RUNS_PER_DAY)
    week = data.get("max_runs_per_week", DEFAULT_MAX_RUNS_PER_WEEK)
    budget = Budget(
        max_runs_per_day=_parse_positive_int(day, f"{where}.max_runs_per_day"),
        max_runs_per_week=_parse_positive_int(week, f"{where}.max_runs_per_week"),
    )
    if budget.max_runs_per_week < budget.max_runs_per_day:
        raise ConfigError(
            f"{where}: max_runs_per_week ({budget.max_runs_per_week}) is below "
            f"max_runs_per_day ({budget.max_runs_per_day}) — the weekly cap would "
            f"make the daily cap unreachable"
        )
    return budget


def _parse_providers(raw: Any) -> dict[str, Provider]:
    data = _require_mapping(raw, "providers")
    unknown = set(data) - set(KNOWN_PROVIDERS)
    if unknown:
        raise ConfigError(
            f"providers: unknown provider(s) {sorted(unknown)} — "
            f"known providers are {', '.join(KNOWN_PROVIDERS)}"
        )
    providers: dict[str, Provider] = {}
    for name in KNOWN_PROVIDERS:
        entry = _require_mapping(data.get(name), f"providers.{name}")
        unknown_fields = set(entry) - {"enabled", "budget", "binary"}
        if unknown_fields:
            raise ConfigError(
                f"providers.{name}: unknown field(s) {sorted(unknown_fields)} — "
                f"expected enabled, budget, binary"
            )
        enabled = entry.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ConfigError(
                f"providers.{name}.enabled: expected true or false, got {enabled!r}"
            )
        providers[name] = Provider(
            name=name,
            enabled=enabled,
            budget=_parse_budget(entry.get("budget"), f"providers.{name}.budget"),
            binary=_parse_binary(entry.get("binary"), f"providers.{name}.binary"),
        )
    return providers


def _parse_checks(raw: Any, where: str) -> tuple[Check, ...]:
    """Validate a project's ``checks:`` list.

    The command is split here rather than at run time so that a quoting mistake
    is a config error you see while editing the file, not a 3am failure in a
    digest. Whether the program *exists* is left alone for the same reason
    ``providers.*.binary`` is: that depends on the machine, not the file.
    """
    if raw is None:
        return ()
    if not isinstance(raw, list) or not raw:
        raise ConfigError(
            f"{where}: expected a non-empty list of checks, got {raw!r} — drop "
            f"the key entirely if this project has none"
        )

    checks: list[Check] = []
    seen: set[str] = set()
    for i, entry in enumerate(raw):
        at = f"{where}[{i}]"
        data = _require_mapping(entry, at)
        unknown = set(data) - {"name", "run", "timeout_s"}
        if unknown:
            raise ConfigError(
                f"{at}: unknown field(s) {sorted(unknown)} — expected name, run, "
                f"timeout_s"
            )

        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError(f"{at}.name: expected a non-empty string, got {name!r}")
        name = name.strip()
        if name in seen:
            raise ConfigError(
                f"{at}.name: duplicate check name {name!r} — names identify a "
                f"check in the digest, so they must be unique within a project"
            )
        seen.add(name)

        command = data.get("run")
        if not isinstance(command, str) or not command.strip():
            raise ConfigError(
                f'{at}.run: expected a command, e.g. "pytest -q", got {command!r}'
            )
        try:
            argv = shlex.split(command)
        except ValueError as exc:
            raise ConfigError(f"{at}.run: {command!r} is not a valid command — {exc}") from None
        if not argv:
            raise ConfigError(f"{at}.run: {command!r} has no command in it")

        timeout_s = data.get("timeout_s", DEFAULT_CHECK_TIMEOUT_S)
        checks.append(
            Check(
                name=name,
                run=command.strip(),
                timeout_s=_parse_positive_int(timeout_s, f"{at}.timeout_s"),
            )
        )
    return tuple(checks)


def _parse_binary(value: Any, where: str) -> str | None:
    """A command name or a path to one. Existence is the adapter's problem.

    Deliberately not checked for existence here: config parsing runs on a
    developer's laptop and in CI, and a path that is missing on one is routinely
    present on the other. An adapter that can't find its binary already reports
    that as unavailable, with a reason — which is a skip, not a crash. Rejecting
    it here would turn one absent CLI into a config file that won't load at all.
    """
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(
            f"{where}: expected a command name or a path to one, got {value!r}"
        )
    return value.strip()


def _parse_projects(raw: Any) -> tuple[Project, ...]:
    if raw is None:
        raise ConfigError(
            "projects: no projects configured — add at least one, or run "
            "`nightaudit init`"
        )
    if not isinstance(raw, list):
        raise ConfigError(f"projects: expected a list, got {_typename(raw)}")
    if not raw:
        raise ConfigError(
            "projects: the list is empty — nightaudit has nothing to review"
        )

    projects: list[Project] = []
    seen: set[str] = set()
    for i, entry in enumerate(raw):
        where = f"projects[{i}]"
        data = _require_mapping(entry, where)
        unknown = set(data) - {"name", "path", "tasks", "provider", "checks"}
        if unknown:
            raise ConfigError(
                f"{where}: unknown field(s) {sorted(unknown)} — "
                f"expected name, path, tasks, provider, checks"
            )

        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError(f"{where}.name: expected a non-empty string, got {name!r}")
        name = name.strip()
        if name in seen:
            raise ConfigError(
                f"{where}.name: duplicate project name {name!r} — names must be unique"
            )
        seen.add(name)

        raw_path = data.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ConfigError(
                f"{where}.path: expected a filesystem path, got {raw_path!r}"
            )

        tasks_raw = data.get("tasks")
        if tasks_raw is None:
            raise ConfigError(
                f"{where}.tasks: no tasks listed — e.g. [code_review, deps_audit]"
            )
        if not isinstance(tasks_raw, list) or not tasks_raw:
            raise ConfigError(
                f"{where}.tasks: expected a non-empty list, got {tasks_raw!r}"
            )
        tasks: list[str] = []
        for task in tasks_raw:
            if not isinstance(task, str) or not _TASK_RE.match(task):
                raise ConfigError(
                    f"{where}.tasks: {task!r} is not a valid task name — use the "
                    f"stem of a prompt file, e.g. code_review"
                )
            if task not in tasks:
                tasks.append(task)

        pinned = data.get("provider")
        if pinned is not None:
            if not isinstance(pinned, str) or not pinned.strip():
                raise ConfigError(
                    f"{where}.provider: expected a provider name, got {pinned!r}"
                )
            pinned = pinned.strip()
            if pinned not in KNOWN_PROVIDERS:
                raise ConfigError(
                    f"{where}.provider: unknown provider {pinned!r} — known "
                    f"providers are {', '.join(KNOWN_PROVIDERS)}"
                )

        projects.append(
            Project(
                name=name,
                path=expand(raw_path),
                tasks=tuple(tasks),
                provider=pinned,
                checks=_parse_checks(data.get("checks"), f"{where}.checks"),
            )
        )
    return tuple(projects)


def _parse_schedule(raw: Any) -> Schedule:
    data = _require_mapping(raw, "schedule")
    unknown = set(data) - {"windows", "idle_minutes"}
    if unknown:
        raise ConfigError(
            f"schedule: unknown field(s) {sorted(unknown)} — "
            f"expected windows, idle_minutes"
        )
    windows_raw = data.get("windows", list(DEFAULT_WINDOWS))
    if not isinstance(windows_raw, list) or not windows_raw:
        raise ConfigError(
            f'schedule.windows: expected a non-empty list like ["09:00-18:00"], '
            f"got {windows_raw!r}"
        )
    windows = tuple(
        parse_window(w, f"schedule.windows[{i}]") for i, w in enumerate(windows_raw)
    )
    idle = data.get("idle_minutes", DEFAULT_IDLE_MINUTES)
    if isinstance(idle, bool) or not isinstance(idle, int) or idle < 0:
        raise ConfigError(
            f"schedule.idle_minutes: expected 0 or a positive whole number, got {idle!r}"
        )
    return Schedule(windows=windows, idle_minutes=idle)


def parse(data: Any, source: Path | None = None) -> Config:
    """Validate a already-deserialised config mapping."""
    root = _require_mapping(data, "config")
    unknown = set(root) - {"providers", "projects", "schedule", "digest", "run"}
    if unknown:
        raise ConfigError(
            f"config: unknown top-level key(s) {sorted(unknown)} — "
            f"expected providers, projects, schedule, digest, run"
        )

    providers = _parse_providers(root.get("providers"))
    if not any(p.enabled for p in providers.values()):
        raise ConfigError(
            "providers: every provider is disabled — enable at least one, e.g.\n"
            "  providers:\n"
            "    claude_code:\n"
            "      enabled: true"
        )

    projects = _parse_projects(root.get("projects"))
    # Cross-field, so it can't live in _parse_projects: a pin at a disabled
    # provider is a contradiction inside one file — the project could never run,
    # on any machine, at any hour. Refused here for the same reason the check
    # above refuses a config with every provider disabled. Contrast
    # `providers.*.binary`, which is left to the adapter precisely because
    # whether a path exists depends on the machine rather than the file.
    for project in projects:
        if project.provider and not providers[project.provider].enabled:
            raise ConfigError(
                f"project {project.name!r} is pinned to provider "
                f"{project.provider!r}, which is disabled — so it could never be "
                f"reviewed. Either set providers.{project.provider}.enabled: true, "
                f"or drop the `provider:` line to let any enabled provider take it."
            )

    digest = _require_mapping(root.get("digest"), "digest")
    unknown_digest = set(digest) - {"dir"}
    if unknown_digest:
        raise ConfigError(
            f"digest: unknown field(s) {sorted(unknown_digest)} — expected dir"
        )
    digest_dir = digest.get("dir", str(DEFAULT_DIGEST_DIR))
    if not isinstance(digest_dir, str) or not digest_dir.strip():
        raise ConfigError(f"digest.dir: expected a filesystem path, got {digest_dir!r}")

    run = _require_mapping(root.get("run"), "run")
    unknown_run = set(run) - {"timeout_s"}
    if unknown_run:
        raise ConfigError(
            f"run: unknown field(s) {sorted(unknown_run)} — expected timeout_s"
        )
    timeout_s = _parse_positive_int(
        run.get("timeout_s", DEFAULT_TIMEOUT_S), "run.timeout_s"
    )

    return Config(
        providers=providers,
        projects=projects,
        schedule=_parse_schedule(root.get("schedule")),
        digest_dir=expand(digest_dir),
        timeout_s=timeout_s,
        source=source,
    )


def load(path: Path | None = None) -> Config:
    """Read and validate the config file."""
    path = path or config_path()
    if not path.exists():
        raise ConfigError(
            f"no config at {path} — run `nightaudit init` to create one"
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML:\n{exc}") from exc
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    if raw is None:
        raise ConfigError(f"{path} is empty — run `nightaudit init` to populate it")
    try:
        return parse(raw, source=path)
    except ConfigError as exc:
        raise ConfigError(f"{path}: {exc}") from None
