"""The gate: decide whether to run, pick the work, run it, record it.

``nightshift run`` fires from cron every hour and is expected to do nothing
most of the time. Every refusal exits 0 with a single line of explanation —
cron mail full of stack traces is how a tool gets uninstalled.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from nightshift import adapters as adapter_registry
from nightshift import events, prompts, report
from nightshift.adapters.base import Adapter, OnEvent, RunResult
from nightshift.budget import Ledger
from nightshift.config import Config, Project, Provider
from nightshift.lock import Lock, LockBusy
from nightshift.queue import Queue

log = logging.getLogger("nightshift")

#: A failed or timed-out run gets exactly one immediate retry. Both attempts
#: count against budget, so this can never be more than one.
MAX_ATTEMPTS = 2


@dataclass
class Outcome:
    """What one invocation of ``nightshift run`` did."""

    ran: bool
    reason: str = ""
    results: list[RunResult] = field(default_factory=list)

    @property
    def status(self) -> str:
        return self.results[-1].status if self.results else "skipped"


def _now() -> datetime:
    return datetime.now()


def _project_by_name(cfg: Config, name: str) -> Project | None:
    for p in cfg.projects:
        if p.name == name:
            return p
    return None


def is_idle(adapter: Adapter, idle_minutes: int, now: datetime) -> tuple[bool, str]:
    """Has the human left this provider alone for long enough?"""
    if idle_minutes <= 0:
        return True, ""
    try:
        last = adapter.last_human_use()
    except Exception as exc:  # pragma: no cover - defensive
        log.debug("idle check failed for %s: %s", adapter.name, exc)
        return True, ""
    if last is None:
        # Can't tell — don't let an unknowable signal block every run.
        return True, ""
    quiet_for = now - last
    if quiet_for < timedelta(minutes=idle_minutes):
        mins = int(quiet_for.total_seconds() // 60)
        return False, f"{adapter.name} used {mins}m ago (needs {idle_minutes}m idle)"
    return True, ""


def _already_logged_budget_skip(cfg: Config, provider: str, on: date) -> bool:
    """Has a budget skip for this provider already been recorded today?

    Cron ticks hourly; without this the digest run log would carry a wall of
    identical "skipped · budget" rows for every hour after the cap was hit.
    """
    for r in report.load_results(cfg, on):
        if r.provider == provider and r.status == "skipped" and "budget" in r.detail:
            return True
    return False


def _record_skip(cfg: Config, provider: str, detail: str, now: datetime) -> RunResult:
    result = RunResult(
        provider=provider,
        project=report.PLACEHOLDER,
        task=report.PLACEHOLDER,
        status="skipped",
        findings_md="",
        started_at=now,
        duration_s=0.0,
        detail=detail,
    )
    report.store_result(cfg, result)
    return result


@dataclass
class ProviderChoice:
    provider: Provider | None
    adapter: Adapter | None
    reason: str = ""
    skips: list[RunResult] = field(default_factory=list)


def choose_provider(
    cfg: Config,
    ledger: Ledger,
    now: datetime,
    *,
    force: bool = False,
    only: str | None = None,
    get_adapter=None,
) -> ProviderChoice:
    """First enabled provider that is installed, idle, and under budget.

    ``--now`` (``force``) skips the idle check but never the budget check —
    budget is the promise that nightshift won't eat someone's quota.
    """
    # Resolved here rather than as a default argument: a default would bind the
    # real registry at import time and quietly ignore any later patching.
    get_adapter = get_adapter or adapter_registry.get
    enabled = cfg.enabled_providers()
    if only:
        enabled = [p for p in enabled if p.name == only]
        if not enabled:
            return ProviderChoice(None, None, f"provider {only!r} is not enabled")

    skips: list[RunResult] = []
    reasons: list[str] = []

    for provider in enabled:
        try:
            adapter = get_adapter(provider.name)
        except Exception as exc:
            reasons.append(f"{provider.name}: {exc}")
            continue

        availability = adapter.availability()
        if not availability.ok:
            reasons.append(f"{provider.name}: {availability.reason}")
            continue

        if not force:
            idle, why = is_idle(adapter, cfg.schedule.idle_minutes, now)
            if not idle:
                reasons.append(why)
                continue

        usage = ledger.usage(provider.name, provider.budget, now)
        if usage.exhausted:
            detail = f"budget · {usage.reason()}"
            reasons.append(f"{provider.name}: {usage.reason()}")
            if not _already_logged_budget_skip(cfg, provider.name, now.date()):
                skips.append(_record_skip(cfg, provider.name, detail, now))
            continue

        return ProviderChoice(provider, adapter, skips=skips)

    return ProviderChoice(
        None, None, "; ".join(reasons) or "no providers enabled", skips=skips
    )


def _tee(*sinks: OnEvent | None) -> OnEvent:
    """Fan one event out to the event log and, if attended, the renderer."""
    live = [s for s in sinks if s is not None]

    def fan(event) -> None:
        for sink in live:
            try:
                sink(event)
            except Exception:  # noqa: BLE001 - a sink must not fail a run
                log.debug("event sink raised", exc_info=True)

    return fan


def _attempt(
    adapter: Adapter,
    prompt: str,
    project: Project,
    task: str,
    timeout_s: int,
    attempt: int,
    on_event: OnEvent | None = None,
) -> RunResult:
    started = _now()
    try:
        result = adapter.run(prompt, project.path, timeout_s, on_event=on_event)
    except NotImplementedError as exc:
        return RunResult(
            provider=adapter.name,
            project=project.name,
            task=task,
            status="failed",
            findings_md="",
            started_at=started,
            duration_s=0.0,
            detail=str(exc),
            attempt=attempt,
        )
    except Exception as exc:  # adapter blew up in a way it didn't anticipate
        log.debug("adapter %s raised", adapter.name, exc_info=True)
        return RunResult(
            provider=adapter.name,
            project=project.name,
            task=task,
            status="failed",
            findings_md="",
            started_at=started,
            duration_s=(_now() - started).total_seconds(),
            detail=f"{type(exc).__name__}: {exc}",
            attempt=attempt,
        )
    result.attempt = attempt
    # Trust the adapter's own timing, but never its bookkeeping.
    result.project = project.name
    result.task = task
    result.provider = adapter.name
    return result


def run_once(
    cfg: Config,
    *,
    now: datetime | None = None,
    force: bool = False,
    provider: str | None = None,
    ledger: Ledger | None = None,
    queue: Queue | None = None,
    get_adapter=None,
    on_event: OnEvent | None = None,
) -> Outcome:
    """One gated run. Returns without acting whenever a gate says no.

    ``on_event`` is passed straight to the adapter: pass a renderer for an
    attended run, leave it ``None`` under cron.
    """
    get_adapter = get_adapter or adapter_registry.get
    now = now or _now()
    ledger = ledger if ledger is not None else Ledger()
    ledger.prune(now.date())
    ledger.save()
    queue = queue if queue is not None else Queue()

    # 1. Window — skipped by --now.
    if not force and not cfg.schedule.is_open(now):
        windows = ", ".join(w.raw for w in cfg.schedule.windows)
        return Outcome(False, f"outside configured windows ({windows})")

    # 2 + 3. Idle and budget.
    choice = choose_provider(
        cfg, ledger, now, force=force, only=provider, get_adapter=get_adapter
    )
    if choice.provider is None or choice.adapter is None:
        return Outcome(False, choice.reason, results=choice.skips)

    # 4. Lock.
    events.prune()
    # The lock must size its stale threshold against the whole budget we might
    # spend, not one attempt of it, or a healthy run that retries looks dead.
    lock = Lock(timeout_s=cfg.timeout_s, attempts=MAX_ATTEMPTS)
    try:
        lock.acquire()
    except LockBusy as exc:
        return Outcome(False, str(exc), results=choice.skips)

    results = list(choice.skips)
    try:
        pair = queue.pop(cfg.pairs())
        if pair is None:
            return Outcome(False, "no (project, task) pairs configured", results=results)
        project_name, task = pair
        project = _project_by_name(cfg, project_name)
        if project is None:  # pragma: no cover - pairs() derives from cfg
            return Outcome(False, f"project {project_name!r} vanished from config")

        if not project.path.is_dir():
            result = RunResult(
                provider=choice.provider.name,
                project=project.name,
                task=task,
                status="failed",
                findings_md="",
                started_at=now,
                duration_s=0.0,
                detail=f"project path does not exist: {project.path}",
            )
            report.store_result(cfg, result)
            results.append(result)
            return Outcome(True, result.detail, results=results)

        try:
            prompt = prompts.load(task)
        except prompts.PromptError as exc:
            result = RunResult(
                provider=choice.provider.name,
                project=project.name,
                task=task,
                status="failed",
                findings_md="",
                started_at=now,
                duration_s=0.0,
                detail=str(exc),
            )
            report.store_result(cfg, result)
            results.append(result)
            return Outcome(True, str(exc), results=results)

        for attempt in range(1, MAX_ATTEMPTS + 1):
            # Every run publishes, attended or not: `nightshift watch` is a
            # separate process and cannot subscribe to a callback in this one.
            event_log = events.EventLog.open(
                project.name, task, choice.provider.name, _now(), attempt
            )
            try:
                result = _attempt(
                    choice.adapter,
                    prompt,
                    project,
                    task,
                    cfg.timeout_s,
                    attempt,
                    _tee(event_log.write, on_event),
                )
            except BaseException:
                # Ctrl-C and the like: leave the log unfinished, which is the
                # truth — the run did not end, it was interrupted.
                event_log.close_quietly()
                raise
            event_log.finish(result, len(report.parse_findings(result)))
            # Spend is recorded before the report is written: if the disk is
            # full we would rather lose the findings than lose the count.
            if result.billed:
                ledger.increment(choice.provider.name, now)
            report.store_result(cfg, result)
            results.append(result)

            if result.status == "ok":
                break
            if attempt >= MAX_ATTEMPTS:
                break
            usage = ledger.usage(choice.provider.name, choice.provider.budget, now)
            if usage.exhausted:
                log.info("not retrying %s/%s — %s", project.name, task, usage.reason())
                break
            log.info("retrying %s/%s after %s", project.name, task, result.status)

        return Outcome(True, "", results=results)
    finally:
        lock.release()


def next_eligible(cfg: Config, now: datetime | None = None) -> datetime | None:
    now = now or _now()
    return cfg.schedule.next_open(now)
