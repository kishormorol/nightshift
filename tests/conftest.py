"""Shared fixtures.

Two invariants hold across the whole suite:

1. **No test spends quota.** No test sends a prompt to a real AI CLI; the
   scheduler is driven by :class:`FakeAdapter` and the adapters are tested
   against a mocked ``subprocess``. ``test_flag_contract.py`` does spawn the
   real binaries, and does not breach this: ``--help`` and ``--version`` parse
   arguments and exit without reaching a model. That file explains why asking
   the CLI directly is the only way to catch what mocks cannot.
2. **No test touches the real home directory.** ``NIGHTAUDIT_HOME`` is pointed
   at a tmp_path for every test, so a stray ``Ledger()`` can never read or
   write the developer's actual ledger.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pytest

#: Captured at import, before ``no_real_subprocesses`` can patch them, so
#: ``real_subprocess`` has the genuine articles to put back. All four, not just
#: ``run``: the real ``run`` is built on ``Popen``, so restoring ``run`` alone
#: leaves it calling a blocked ``Popen`` one layer down — which surfaces as
#: "tried to spawn a real subprocess" from a line that plainly did not.
_REAL_SUBPROCESS = {
    name: getattr(subprocess, name) for name in ("run", "Popen", "check_output", "call")
}

from nightaudit.adapters.base import Availability, RunResult
from nightaudit.config import Config, parse


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Point all nightaudit state at a throwaway directory."""
    home = tmp_path / "state"
    home.mkdir()
    monkeypatch.setenv("NIGHTAUDIT_HOME", str(home))
    return home


@pytest.fixture(autouse=True)
def no_real_subprocesses(monkeypatch, request):
    """Hard stop: no test may spawn a real process.

    This exists because the leak it guards against is *silent*. A default
    argument bound at import time (``get_adapter=adapter_registry.get``) once
    made the CLI tests fall through to the real `claude` binary — they still
    passed, just slower and billed to a live subscription. Nothing failed, so
    nothing announced it.

    Tests that need to drive subprocess behaviour install their own mock on top
    of this one (see ``test_claude_code_adapter.py``); this fixture only catches
    the calls nobody meant to make. Tests of the check runner ask for
    ``real_subprocess`` instead — see the note there.
    """

    def forbidden(cmd, *args, **kwargs):
        raise AssertionError(
            f"test tried to spawn a real subprocess: {cmd!r}\n"
            f"Tests must spend zero quota — stub the adapter, or mock "
            f"subprocess.run in the test itself."
        )

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "check_output", forbidden)
    monkeypatch.setattr(subprocess, "call", forbidden)


@pytest.fixture
def real_subprocess(monkeypatch, no_real_subprocesses):
    """Let this test actually spawn processes.

    Depends on ``no_real_subprocesses`` for the ordering, not the behaviour: it
    has to have installed its block before this can lift it, and naming it is
    the only way to say so.

    ``no_real_subprocesses`` exists to stop a test silently billing an AI
    subscription. A check is not an AI CLI — it is the user's own command, and
    spawning it *is* the behaviour under test. Mocking subprocess here would
    leave run_check's timeout, exit code and command-not-found handling asserted
    only against a fake that agrees with whatever we already assumed, which is
    how you ship a runner that has never run anything.

    Every command in those tests is ``sys.executable``, so this spends no quota
    and depends on nothing being installed.
    """
    for name, original in _REAL_SUBPROCESS.items():
        monkeypatch.setattr(subprocess, name, original)


@dataclass
class FakeAdapter:
    """A scriptable stand-in for a real provider CLI.

    ``results`` is consumed one entry per :meth:`run`; each entry is either a
    ``(status, findings_md)`` tuple or an exception instance to raise.
    """

    name: str = "claude_code"
    #: Whatever binary override the registry was asked for, recorded so a test
    #: can prove the config value actually reached the adapter.
    binary: str | None = None
    results: list = field(default_factory=list)
    is_available: bool = True
    unavailable_reason: str = "not installed"
    human_used_at: datetime | None = None
    duration_s: float = 1.0
    #: Stamped onto every result, like a provider's reported usage. Default 0 is
    #: "the CLI said nothing", which is what most tests want.
    tokens: int = 0
    calls: list[dict] = field(default_factory=list)
    #: Stamped onto results. Leave ``None`` for the real clock; set it when a
    #: test asserts which day directory a result lands in, so the assertion
    #: doesn't quietly depend on when the suite happens to run.
    started_at: datetime | None = None

    def availability(self) -> Availability:
        return Availability(
            ok=self.is_available, reason="" if self.is_available else self.unavailable_reason
        )

    def available(self) -> bool:
        return self.is_available

    def last_human_use(self) -> datetime | None:
        return self.human_used_at

    def run(
        self,
        prompt: str,
        project_dir: Path,
        timeout_s: int,
        on_event=None,
    ) -> RunResult:
        self.calls.append(
            {
                "prompt": prompt,
                "project_dir": project_dir,
                "timeout_s": timeout_s,
                "on_event": on_event,
            }
        )
        if self.results:
            outcome = self.results.pop(0)
        else:
            outcome = ("ok", "- LOW src/thing.py:1 — tidy this up")
        if isinstance(outcome, BaseException):
            raise outcome
        status, findings = outcome
        return RunResult(
            provider=self.name,
            project=project_dir.name,
            task="",
            status=status,
            findings_md=findings,
            started_at=self.started_at or datetime.now(),
            duration_s=self.duration_s,
            tokens=self.tokens,
        )


@pytest.fixture
def fake_adapter():
    return FakeAdapter()


@pytest.fixture
def get_fake(fake_adapter):
    """A drop-in for ``adapters.get`` that always yields the fake.

    It takes ``binary`` because the real ``get`` does. A double whose signature
    has drifted from the thing it doubles is how a seam stops being tested
    without any test going red.
    """

    def _get(name: str, binary: str | None = None):
        fake_adapter.name = name
        fake_adapter.binary = binary
        return fake_adapter

    return _get


@pytest.fixture
def project_dir(tmp_path) -> Path:
    d = tmp_path / "acme-api"
    d.mkdir()
    (d / "main.py").write_text("print('hi')\n", encoding="utf-8")
    return d


def build_config(
    tmp_path: Path,
    project_dir: Path,
    *,
    windows: list[str] | None = None,
    idle_minutes: int = 60,
    tasks: list[str] | None = None,
    max_day: int = 6,
    max_week: int = 30,
    providers: dict | None = None,
) -> Config:
    raw = {
        "providers": providers
        or {
            "claude_code": {
                "enabled": True,
                "budget": {
                    "max_runs_per_day": max_day,
                    "max_runs_per_week": max_week,
                },
            }
        },
        "projects": [
            {
                "name": project_dir.name,
                "path": str(project_dir),
                "tasks": tasks or ["code_review"],
            }
        ],
        "schedule": {
            "windows": windows or ["00:00-23:59"],
            "idle_minutes": idle_minutes,
        },
        "digest": {"dir": str(tmp_path / "reports")},
        "run": {"timeout_s": 600},
    }
    return parse(raw)


@pytest.fixture
def cfg(tmp_path, project_dir) -> Config:
    return build_config(tmp_path, project_dir)
