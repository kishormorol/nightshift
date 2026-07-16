"""The ``nightshift`` command line.

Design rule for everything here: expected conditions exit 0 with one readable
line. Cron runs these commands unattended, and a tool that mails a stack trace
every hour gets uninstalled by lunchtime.
"""

from __future__ import annotations

import logging
import shutil
import sys
import textwrap
import time
from datetime import date, datetime
from pathlib import Path

import click

from nightshift import __version__
from nightshift import adapters as adapter_registry
from nightshift import cron, events, prompts, report, scheduler
from nightshift.adapters.base import Event
from nightshift.budget import Ledger
from nightshift.config import (
    Config,
    ConfigError,
    config_path,
    expand,
    load,
    parse_window,
    state_dir,
)
from nightshift.queue import Queue

DEFAULT_TASKS = ("code_review", "security_audit", "deps_audit")

log = logging.getLogger("nightshift")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        stream=sys.stderr,
    )


def _load_or_exit() -> Config:
    try:
        return load()
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from None


def _echo_quiet(message: str) -> None:
    """A gate refused. One line, exit 0."""
    click.echo(message)


#: Wrapped lines of narration shown per text block. The agent explains itself
#: at length and every word of it reaches the digest; what a live view needs
#: is the shape of the run, so the prose is topped and tailed here.
PROSE_LINES = 2

#: Terminal colour per severity, alongside the digest's emoji.
_SEVERITY_FG = {"HIGH": "red", "MED": "yellow", "LOW": "cyan"}


def _wrap_width() -> int:
    return max(min(shutil.get_terminal_size((80, 24)).columns, 100) - 4, 40)


def _clip(text: str, width: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1] + "…"


def _echo_finding(finding, width: int) -> None:
    """One finding, one line — severity first, because that is what ranks it."""
    head = f"  {finding.emoji} {finding.severity:<4} "
    ref = f"{finding.ref} · " if finding.ref else ""
    body = _clip(f"{ref}{finding.text}", max(width - len(head) + 2, 24))
    click.echo(head + click.style(body, fg=_SEVERITY_FG.get(finding.severity)))


def _echo_prose(lines: list[str], width: int) -> None:
    if not lines:
        return
    wrapped = textwrap.wrap(" ".join(lines), width=width)
    for line in wrapped[:PROSE_LINES]:
        click.echo(click.style(f"    {line}", dim=True))
    if len(wrapped) > PROSE_LINES:
        click.echo(click.style("    …", dim=True))
    lines.clear()


def _render_event(event: Event) -> None:
    """Print one adapter event, Claude-Code style.

    Purely cosmetic — the digest is built from the run's result, so anything
    dropped here costs nothing but the view.
    """
    if event.kind == "start":
        click.echo(click.style("  ⏺ ", fg="green") + click.style(event.text, dim=True))

    elif event.kind == "thinking":
        click.echo(click.style("  ✻ thinking", fg="magenta", dim=True))

    elif event.kind == "tool":
        line = click.style("  ⏺ ", fg="cyan") + click.style(event.tool, bold=True)
        if event.detail:
            line += click.style(f"({event.detail})", dim=True)
        click.echo(line)

    elif event.kind == "tool_result":
        if event.text:
            click.echo(click.style(f"    ⎿  {_clip(event.text, _wrap_width())}", dim=True))

    elif event.kind == "text":
        width = _wrap_width()
        prose: list[str] = []
        for raw in event.text.splitlines():
            if not raw.strip():
                continue
            finding = report.parse_finding_line(raw)
            if finding is None:
                prose.append(raw.strip())
                continue
            # Keep the order the agent wrote in: whatever it said before this
            # finding belongs above it, not collected at the end.
            _echo_prose(prose, width)
            _echo_finding(finding, width)
        _echo_prose(prose, width)

    elif event.kind == "error":
        click.echo(click.style(f"  ✗ {event.text}", fg="red"))


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="nightshift")
def main() -> None:
    """Your AI works the night shift.

    Read-only reviews of your projects while you're busy, one digest every
    morning. nightshift never modifies your code.
    """


# ---------------------------------------------------------------- init


def _detect_providers() -> list[tuple[str, bool, str]]:
    found = []
    for name in adapter_registry.names():
        adapter = adapter_registry.get(name)
        availability = adapter.availability()
        found.append((name, availability.ok, availability.reason))
    return found


def _render_config(
    enabled: list[str],
    projects: list[tuple[str, Path, list[str]]],
    windows: list[str],
    idle_minutes: int,
    digest_dir: Path,
) -> str:
    lines: list[str] = [
        "# nightshift config — https://github.com/kishormorol/nightshift",
        "# Edit freely; `nightshift status` validates it.",
        "",
        "providers:",
    ]
    for name in adapter_registry.names():
        on = name in enabled
        lines.append(f"  {name}:")
        lines.append(f"    enabled: {'true' if on else 'false'}")
        if on:
            lines.append("    budget:")
            lines.append("      max_runs_per_day: 6")
            lines.append("      max_runs_per_week: 30")
    lines.append("")
    lines.append("projects:")
    for name, path, tasks in projects:
        lines.append(f"  - name: {name}")
        lines.append(f"    path: {path}")
        lines.append(f"    tasks: [{', '.join(tasks)}]")
    lines.append("")
    lines.append("schedule:")
    lines.append(f"  windows: [{', '.join(f'{w!r}' for w in windows)}]")
    lines.append(f"  idle_minutes: {idle_minutes}")
    lines.append("")
    lines.append("digest:")
    lines.append(f"  dir: {digest_dir}")
    lines.append("")
    lines.append("run:")
    lines.append("  timeout_s: 600")
    lines.append("")
    return "\n".join(lines)


@main.command()
@click.option("--force", is_flag=True, help="Overwrite an existing config.")
def init(force: bool) -> None:
    """Detect your AI CLIs, register projects, and set the schedule."""
    path = config_path()
    if path.exists() and not force:
        click.echo(f"Config already exists at {path}")
        if not click.confirm("Replace it?", default=False):
            click.echo("Left it alone. Nothing changed.")
            return

    click.echo("Looking for AI CLIs on your PATH…\n")
    detected = _detect_providers()
    enabled: list[str] = []
    for name, ok, reason in detected:
        if ok:
            click.echo(f"  ✓ {name}  {reason}")
            enabled.append(name)
        else:
            click.echo(f"  ✗ {name}  {reason}")
    click.echo()

    if not enabled:
        raise click.ClickException(
            "No usable AI CLI found. Install Claude Code or Codex and re-run "
            "`nightshift init`."
        )

    click.echo("Which projects should nightshift review?")
    click.echo("Enter a path per line; press Enter on a blank line when done.\n")
    projects: list[tuple[str, Path, list[str]]] = []
    while True:
        raw = click.prompt(
            "  project path", default="", show_default=False, type=str
        ).strip()
        if not raw:
            break
        resolved = expand(raw)
        if not resolved.is_dir():
            click.echo(f"    ✗ {resolved} is not a directory — skipped")
            continue
        name = click.prompt("    name", default=resolved.name, type=str).strip()
        if any(p[0] == name for p in projects):
            click.echo(f"    ✗ {name!r} is already registered — skipped")
            continue
        available = prompts.available_tasks()
        default_tasks = [t for t in DEFAULT_TASKS if t in available] or available[:1]
        click.echo(f"    available tasks: {', '.join(available)}")
        chosen = click.prompt(
            "    tasks", default=", ".join(default_tasks), type=str
        )
        tasks = [t.strip() for t in chosen.replace(",", " ").split() if t.strip()]
        unknown = [t for t in tasks if t not in available]
        if unknown:
            click.echo(f"    ✗ unknown task(s): {', '.join(unknown)} — skipped")
            continue
        projects.append((name, resolved, tasks))
        click.echo(f"    ✓ {name} · {', '.join(tasks)}\n")

    if not projects:
        raise click.ClickException("No projects registered — nothing to schedule.")

    click.echo()
    windows_raw = click.prompt(
        "When may nightshift run? (comma-separated HH:MM-HH:MM)",
        default="00:00-06:00",
        type=str,
    )
    windows = [w.strip() for w in windows_raw.split(",") if w.strip()]
    for i, w in enumerate(windows):
        try:
            parse_window(w, f"schedule.windows[{i}]")
        except ConfigError as exc:
            raise click.ClickException(str(exc)) from None

    idle_minutes = click.prompt(
        "Minutes of provider idleness required before a run",
        default=60,
        type=click.IntRange(min=0),
    )
    digest_dir = expand(
        click.prompt("Where should digests go?", default="~/nightshift-reports", type=str)
    )

    text = _render_config(enabled, projects, windows, idle_minutes, digest_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    click.echo(f"\nWrote {path}")

    try:
        cfg = load(path)
    except ConfigError as exc:  # pragma: no cover - we just generated it
        raise click.ClickException(f"generated config is invalid — please report this:\n{exc}")
    cfg.digest_dir.mkdir(parents=True, exist_ok=True)

    click.echo("\nnightshift has no daemon — cron drives it. Add these lines:\n")
    for line in cron.entries():
        click.echo(f"  {line}")
    click.echo()
    if click.confirm("Install them into your crontab now?", default=False):
        try:
            cron.install()
        except RuntimeError as exc:
            click.echo(f"Could not install automatically: {exc}")
            click.echo("Add the lines above with `crontab -e`.")
        else:
            click.echo("Installed.")
    else:
        click.echo("Skipped — add them with `crontab -e` when you're ready.")

    click.echo("\nTry a run right now:  nightshift run --now")


# ----------------------------------------------------------------- run


@main.command()
@click.option("--now", "force", is_flag=True, help="Skip the window and idle checks (not budget).")
@click.option("--provider", default=None, help="Restrict to one provider.")
@click.option(
    "--stream/--no-stream",
    default=None,
    help="Show the run live. Defaults on at a terminal, off under cron.",
)
@click.option("-v", "--verbose", is_flag=True, help="Debug logging.")
def run(force: bool, provider: str | None, stream: bool | None, verbose: bool) -> None:
    """Do one gated run, or exit quietly explaining why not."""
    _setup_logging(verbose)
    cfg = _load_or_exit()

    # Cron gets the quiet single-line summary it has always got; a human at a
    # terminal gets to watch. --stream/--no-stream overrides the guess.
    if stream is None:
        stream = sys.stdout.isatty()

    outcome = scheduler.run_once(
        cfg,
        force=force,
        provider=provider,
        on_event=_render_event if stream else None,
    )
    if not outcome.ran:
        _echo_quiet(f"nothing to do — {outcome.reason}")
        return

    if stream:
        click.echo()

    for result in outcome.results:
        if result.status == "skipped":
            continue
        line = (
            f"{result.status:>7}  {result.project} · {result.task} "
            f"({result.provider}, {report.format_duration(result)})"
        )
        if result.detail:
            line += f" — {result.detail}"
        click.echo(line)
        if result.status == "ok":
            findings = report.parse_findings(result)
            click.echo(
                f"         {len(findings)} finding{'s' if len(findings) != 1 else ''}"
                if findings
                else "         no findings"
            )


# --------------------------------------------------------------- watch


def _fmt_secs(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds}s" if seconds < 60 else f"{seconds // 60}m{seconds % 60:02d}s"


def _render_log_event(payload: dict) -> None:
    """Render one line from an event log, as `watch` sees it."""
    kind = payload.get("kind", "")

    if kind == "meta":
        started = str(payload.get("started_at", ""))[11:19]
        head = f"{payload.get('project', '?')} · {payload.get('task', '?')}"
        attempt = payload.get("attempt", 1)
        if isinstance(attempt, int) and attempt > 1:
            head += f"  retry {attempt - 1}"
        click.echo()
        click.echo(
            click.style("┌ ", fg="blue")
            + click.style(head, bold=True)
            + click.style(f"   {payload.get('provider', '?')} · {started}", dim=True)
        )
        return

    if kind == "end":
        status = str(payload.get("status", "?"))
        colour = {"ok": "green", "failed": "red", "timeout": "yellow"}.get(status, "white")
        mark = {"ok": "✓", "failed": "✗", "timeout": "⧗"}.get(status, "·")
        findings = payload.get("findings", 0)
        tail = f"{findings} finding{'' if findings == 1 else 's'}"
        if payload.get("detail"):
            tail += f" · {payload['detail']}"
        click.echo(
            click.style("└ ", fg="blue")
            + click.style(f"{mark} {status}", fg=colour, bold=True)
            + click.style(f"   {_fmt_secs(payload.get('duration_s', 0))} · {tail}", dim=True)
        )
        return

    _render_event(
        Event(
            kind=kind,  # type: ignore[arg-type]
            text=str(payload.get("text", "")),
            tool=str(payload.get("tool", "")),
            detail=str(payload.get("detail", "")),
        )
    )


@main.command()
@click.option("-n", "--history", default=1, help="Replay this many finished runs first.")
def watch(history: int) -> None:
    """Follow runs as they happen, including ones cron started."""
    click.echo(click.style("nightshift · watching for runs — ctrl-c to stop", dim=True))

    seen: set[Path] = set()

    if history > 0:
        for path in reversed(events.recent_logs(limit=history)):
            seen.add(path)
            for payload in events.read(path):
                _render_log_event(payload)

    # Anything already on disk that we did not just replay is history too;
    # marking it seen keeps `watch` from re-rendering old runs on startup.
    # A log with no `end` is only worth following if it is still being
    # written — an interrupted run leaves one behind forever, and following
    # that would wedge the watcher instead of showing the next real run.
    for path in events.recent_logs(limit=200):
        if events.is_finished(path) or events.is_stale(path):
            seen.add(path)

    try:
        while True:
            fresh = [p for p in events.recent_logs(limit=20) if p not in seen]
            if not fresh:
                time.sleep(events.POLL_S)
                continue
            for path in reversed(fresh):
                seen.add(path)
                # Startup skips abandoned logs; the loop has to as well. A run
                # interrupted while we are watching leaves an `end`-less log,
                # and following it would park the watcher for the whole stale
                # window with real runs going unrendered behind it.
                if not events.is_finished(path) and events.is_stale(path):
                    continue
                for payload in events.follow(path):
                    _render_log_event(payload)
    except KeyboardInterrupt:
        click.echo(click.style("\nstopped watching.", dim=True))


# -------------------------------------------------------------- digest


@main.command()
@click.option(
    "--date",
    "on",
    default=None,
    help="Day to render (YYYY-MM-DD). Defaults to today.",
)
@click.option("--stdout", "to_stdout", is_flag=True, help="Print instead of writing.")
def digest(on: str | None, to_stdout: bool) -> None:
    """Render the morning digest for a day."""
    cfg = _load_or_exit()
    if on is None:
        day = date.today()
    else:
        try:
            day = date.fromisoformat(on)
        except ValueError:
            raise click.ClickException(
                f"--date {on!r} is not a valid date — expected YYYY-MM-DD"
            ) from None

    ledger = Ledger()
    if to_stdout:
        click.echo(report.render_digest(cfg, day, ledger=ledger), nl=False)
        return
    path = report.write_digest(cfg, day, ledger=ledger)
    results = report.load_results(cfg, day)
    click.echo(f"{path}  ({len(results)} run{'s' if len(results) != 1 else ''})")


# -------------------------------------------------------------- status


def _fmt_next(cfg: Config, now: datetime) -> str:
    if cfg.schedule.is_open(now):
        return "now (a window is open)"
    nxt = scheduler.next_eligible(cfg, now)
    if nxt is None:
        return "unknown"
    delta = nxt - now
    hours, rem = divmod(int(delta.total_seconds()), 3600)
    mins = rem // 60
    when = nxt.strftime("%a %H:%M")
    ago = f"in {hours}h{mins:02d}m" if hours else f"in {mins}m"
    return f"{when} ({ago})"


@main.command()
def status() -> None:
    """Budget, recent runs, next window, and provider availability."""
    cfg = _load_or_exit()
    now = datetime.now()
    ledger = Ledger()

    click.echo(f"config    {cfg.source or config_path()}")
    click.echo(f"state     {state_dir()}")
    click.echo(f"digests   {cfg.digest_dir}")
    click.echo()

    click.echo("providers")
    for provider in cfg.providers.values():
        if not provider.enabled:
            click.echo(f"  {provider.name:<12} disabled")
            continue
        try:
            adapter = adapter_registry.get(provider.name, provider.binary)
        except adapter_registry.AdapterError as exc:
            # A `binary` the registry rejects must not take `status` down with
            # it — status is the command you reach for to find out what is wrong.
            click.echo(f"  ✗ {provider.name:<10} {exc}")
            continue
        availability = adapter.availability()
        mark = "✓" if availability.ok else "✗"
        usage = ledger.usage(provider.name, provider.budget, now)
        bar = report.budget_bar(usage.day, usage.max_day)
        click.echo(
            f"  {mark} {provider.name:<10} {bar} "
            f"{usage.day}/{usage.max_day} today · "
            f"{usage.week}/{usage.max_week} week"
        )
        if not availability.ok:
            click.echo(f"      {availability.reason}")
        elif usage.exhausted:
            click.echo(f"      {usage.reason()}")
    click.echo()

    windows = ", ".join(w.raw for w in cfg.schedule.windows)
    click.echo(f"schedule  {windows} · needs {cfg.schedule.idle_minutes}m idle")
    click.echo(f"next run  {_fmt_next(cfg, now)}")

    queue = Queue()
    upcoming = queue.peek(cfg.pairs())
    if upcoming:
        line = f"up next   {upcoming[0]} · {upcoming[1]}"
        pinned = next(
            (p.provider for p in cfg.projects if p.name == upcoming[0] and p.provider),
            None,
        )
        # Only shown for a pin, which is a fact from the config. Naming a
        # provider for an unpinned project would be a guess about who happens to
        # be idle and under budget by the time the window comes round.
        if pinned:
            line += f" · {pinned}"
        click.echo(line)
    click.echo()

    recent = report.load_results(cfg, now.date())
    if not recent:
        yesterday = date.fromordinal(now.date().toordinal() - 1)
        recent = report.load_results(cfg, yesterday)
    if recent:
        click.echo("last runs")
        for r in recent[-5:]:
            detail = f" — {r.detail}" if r.detail else ""
            click.echo(
                f"  {r.started_at.strftime('%H:%M')}  {r.status:<7} "
                f"{r.project} · {r.task}{detail}"
            )
    else:
        click.echo("last runs  none recorded yet")

    missing = [
        t
        for project in cfg.projects
        for t in project.tasks
        if prompts.find(t) is None
    ]
    if missing:
        click.echo()
        click.echo(
            f"warning   no prompt template for: {', '.join(sorted(set(missing)))}"
        )


if __name__ == "__main__":  # pragma: no cover
    main()
