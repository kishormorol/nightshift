"""The adapter contract: what nightaudit needs from any AI coding CLI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Literal, Protocol, runtime_checkable

Status = Literal["ok", "failed", "timeout", "skipped"]

#: Statuses that consumed provider quota and so must hit the ledger.
BILLED_STATUSES: frozenset[str] = frozenset({"ok", "failed", "timeout"})

EventKind = Literal["start", "thinking", "text", "tool", "tool_result", "result", "error"]


class AdapterError(Exception):
    """A problem with an adapter itself, not with the run it attempted."""


@dataclass
class Event:
    """One thing an adapter saw while a run was still in flight.

    Adapters emit these only when a caller asks for them; the digest is built
    from :class:`RunResult`, never from events. Nothing here is load-bearing —
    dropping every event must still leave the run correct.
    """

    kind: EventKind
    #: Assistant prose, a tool result summary, or an error message.
    text: str = ""
    #: Tool name, for ``tool``/``tool_result``.
    tool: str = ""
    #: Short rendering of tool input, e.g. ``pattern: *.py``.
    detail: str = ""


#: Called on the run's thread as events arrive. Must never raise.
OnEvent = Callable[[Event], None]


@dataclass
class RunResult:
    """The outcome of one (project, task) attempt.

    ``skipped`` never comes from an adapter — the scheduler synthesises it when
    a gate refuses the run, so the digest can show what did *not* happen.
    """

    provider: str
    project: str
    task: str
    status: Status
    findings_md: str
    started_at: datetime
    duration_s: float
    #: Populated for skipped/failed runs; shown in the digest run log.
    detail: str = ""
    attempt: int = 1
    #: Total tokens the provider reported for this attempt (input + output, plus
    #: cache reads/writes where a provider counts them). ``0`` means the CLI told
    #: us nothing — an older CLI, a run killed before its usage frame, or a
    #: provider that does not report it — not that the run was free. A measure,
    #: never a bill: nightaudit budgets in runs, not tokens.
    tokens: int = 0

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "project": self.project,
            "task": self.task,
            "status": self.status,
            "findings_md": self.findings_md,
            "started_at": self.started_at.isoformat(),
            "duration_s": round(self.duration_s, 3),
            "detail": self.detail,
            "attempt": self.attempt,
            "tokens": self.tokens,
        }

    @classmethod
    def from_dict(cls, data: dict) -> RunResult:
        return cls(
            provider=data["provider"],
            project=data["project"],
            task=data["task"],
            status=data["status"],
            findings_md=data.get("findings_md", ""),
            started_at=datetime.fromisoformat(data["started_at"]),
            duration_s=float(data.get("duration_s", 0.0)),
            detail=data.get("detail", ""),
            attempt=int(data.get("attempt", 1)),
            tokens=int(data.get("tokens", 0)),
        )

    @property
    def billed(self) -> bool:
        """Did this attempt consume provider quota?"""
        return self.status in BILLED_STATUSES


@dataclass
class Availability:
    """Why an adapter can or cannot be used right now."""

    ok: bool
    reason: str = ""


@runtime_checkable
class Adapter(Protocol):
    """A read-only wrapper around one AI coding CLI."""

    name: str

    def available(self) -> bool:
        """Is the CLI installed, on PATH, and authenticated?"""
        ...

    def availability(self) -> Availability:
        """Like :meth:`available`, but explains itself for ``nightaudit status``."""
        ...

    def last_human_use(self) -> datetime | None:
        """When a human last drove this CLI, or ``None`` if unknowable.

        The scheduler uses this to stay out of the user's way; ``None`` is read
        as "idle", since an adapter that cannot tell should not block runs.
        """
        ...

    def run(
        self,
        prompt: str,
        project_dir: Path,
        timeout_s: int,
        on_event: OnEvent | None = None,
    ) -> RunResult:
        """Execute ``prompt`` against ``project_dir`` read-only.

        When ``on_event`` is given the adapter should report progress as it
        happens; when it is ``None`` the adapter stays silent, which is what
        cron wants. The :class:`RunResult` must not depend on which was used.
        """
        ...


@dataclass
class StubAdapter:
    """Base for adapters that are documented but not yet implemented."""

    name: str = "stub"
    help_wanted_url: str = "https://github.com/kishormorol/nightaudit/issues"

    def available(self) -> bool:
        return False

    def availability(self) -> Availability:
        return Availability(
            ok=False,
            reason=f"the {self.name} adapter is not implemented yet — help wanted: "
            f"{self.help_wanted_url}",
        )

    def last_human_use(self) -> datetime | None:
        return None

    def run(
        self,
        prompt: str,
        project_dir: Path,
        timeout_s: int,
        on_event: OnEvent | None = None,
    ) -> RunResult:
        raise NotImplementedError(
            f"the {self.name} adapter is a documented stub — see {self.help_wanted_url}"
        )
