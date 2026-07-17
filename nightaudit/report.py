"""Persisting run results and rendering the morning digest."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from nightaudit.adapters.base import RunResult
from nightaudit.budget import Ledger
from nightaudit.checks import CheckResult
from nightaudit.config import Config
from nightaudit.store import read_json, write_json

NO_FINDINGS = "No findings."

#: Stands in for project/task on a run that never picked any work — currently
#: only budget skips. Not a real project, so it must not be counted as one.
PLACEHOLDER = "—"

SEVERITY_RANK = {"HIGH": 0, "MED": 1, "LOW": 2}
SEVERITY_EMOJI = {"HIGH": "🔴", "MED": "🟠", "LOW": "🟡"}

#: Normalises whatever the model actually wrote into our three levels.
_SEVERITY_ALIASES = {
    "CRITICAL": "HIGH",
    "CRIT": "HIGH",
    "SEV1": "HIGH",
    "HIGH": "HIGH",
    "MEDIUM": "MED",
    "MED": "MED",
    "MODERATE": "MED",
    "WARN": "MED",
    "WARNING": "MED",
    "LOW": "LOW",
    "MINOR": "LOW",
    "INFO": "LOW",
    "NIT": "LOW",
}

_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?P<body>.+?)\s*$")
_SEVERITY_PREFIX = re.compile(
    r"^(?:[\[(]\s*)?(?:\*\*|__|`)?\s*"
    r"(?P<sev>[A-Za-z]+)"
    r"\s*(?:\*\*|__|`)?(?:\s*[\])])?"
    r"\s*(?:[:\-–—]\s*|\s+)",
)
_FILE_REF = re.compile(r"(?P<ref>(?:[\w.@+-]+/)*[\w.@+-]+\.[A-Za-z0-9]+(?::\d+)?)")
_LEADING_EMOJI = re.compile(r"^[\U0001F300-\U0001FAFF☀-➿️\s]+")


@dataclass(frozen=True)
class Finding:
    severity: str
    text: str
    project: str
    task: str
    provider: str
    ref: str = ""

    @property
    def rank(self) -> int:
        return SEVERITY_RANK.get(self.severity, 2)

    @property
    def emoji(self) -> str:
        return SEVERITY_EMOJI.get(self.severity, "🟡")


def normalise_severity(token: str) -> str | None:
    return _SEVERITY_ALIASES.get(token.strip().upper().strip(":-—–"))


def parse_finding_line(
    line: str,
    project: str = "",
    task: str = "",
    provider: str = "",
) -> Finding | None:
    """One markdown list item as a :class:`Finding`, or ``None``.

    Split out of :func:`parse_findings` so a live view can classify a line the
    instant it arrives and still agree with the digest — one severity model,
    not two that drift.
    """
    item = _LIST_ITEM.match(line)
    if not item:
        return None
    body = _LEADING_EMOJI.sub("", item.group("body")).strip()
    if not body:
        return None

    severity = "LOW"
    match = _SEVERITY_PREFIX.match(body)
    if match:
        candidate = normalise_severity(match.group("sev"))
        if candidate:
            severity = candidate
            body = body[match.end():].strip()

    ref_match = _FILE_REF.search(body)
    ref = ref_match.group("ref") if ref_match else ""
    body = _LEADING_EMOJI.sub("", body).strip(" -–—:")
    # The documented format leads with the ref, and we render it separately
    # — keeping it inline too would print the path twice on every line. The
    # model almost always writes it as `code`, so match through the markup
    # rather than only against a bare path.
    if ref:
        lead = re.match(
            r"^[`*_]*" + re.escape(ref) + r"[`*_]*\s*[-–—:]*\s*",
            body,
        )
        if lead:
            body = body[lead.end() :].strip(" -–—:")
    if not body:
        # A finding that was *only* a file ref still deserves to be seen.
        body = ref
    if not body:
        return None
    return Finding(
        severity=severity,
        text=body,
        project=project,
        task=task,
        provider=provider,
        ref=ref,
    )


def parse_findings(result: RunResult) -> list[Finding]:
    """Pull structured findings out of an adapter's markdown.

    Deliberately forgiving: models drift from the requested format, and a
    finding we can't classify is still worth showing, so anything unlabelled
    lands at LOW rather than being dropped.
    """
    text = (result.findings_md or "").strip()
    if not text or text.lower().startswith(NO_FINDINGS.lower()):
        return []

    findings: list[Finding] = []
    for line in text.splitlines():
        finding = parse_finding_line(line, result.project, result.task, result.provider)
        if finding is not None:
            findings.append(finding)
    return findings


def day_dir(cfg: Config, on: date) -> Path:
    return cfg.digest_dir / on.isoformat()


def digest_path(cfg: Config, on: date) -> Path:
    return cfg.digest_dir / f"DIGEST-{on.isoformat()}.md"


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-") or "unknown"


def _unique_stem(directory: Path, stem: str) -> str:
    """Disambiguate a stem that already exists.

    Filenames are second-granular, so two runs of the same (project, task)
    inside one second would collide and the later one would overwrite the
    earlier. Hourly cron makes that unlikely, but `run --now` in a loop hits it
    immediately — and a silently discarded run is precisely what the digest
    promises never happens.
    """
    if not (directory / f"{stem}.json").exists():
        return stem
    for n in range(2, 1000):
        candidate = f"{stem}-{n}"
        if not (directory / f"{candidate}.json").exists():
            return candidate
    return f"{stem}-{os.getpid()}"


def store_result(cfg: Config, result: RunResult) -> Path:
    """Write the full RunResult as JSON, plus its findings as markdown."""
    directory = day_dir(cfg, result.started_at.date())
    directory.mkdir(parents=True, exist_ok=True)
    when = result.started_at.strftime("%H%M%S")
    if result.project == PLACEHOLDER:
        # No work was picked, so "unknown-unknown-030000" would be the filename.
        stem = f"skipped-{_slug(result.provider)}-{when}"
    else:
        stem = f"{_slug(result.project)}-{_slug(result.task)}-{when}"
    if result.attempt > 1:
        stem += f"-retry{result.attempt - 1}"
    stem = _unique_stem(directory, stem)

    json_path = directory / f"{stem}.json"
    write_json(json_path, result.to_dict())

    md_path = directory / f"{stem}.md"
    header = (
        f"# {result.project} · {result.task}\n\n"
        f"- provider: `{result.provider}`\n"
        f"- status: `{result.status}`\n"
        f"- started: {result.started_at.isoformat(timespec='seconds')}\n"
        f"- duration: {format_duration(result)}\n"
    )
    if result.tokens > 0:
        header += f"- tokens: {format_tokens(result.tokens)}\n"
    if result.detail:
        header += f"- detail: {result.detail}\n"
    body = (result.findings_md or "").strip() or NO_FINDINGS
    md_path.write_text(f"{header}\n{body}\n", encoding="utf-8")
    return json_path


def checks_dir(cfg: Config, on: date) -> Path:
    """Check results live under the day, not in it.

    A subdirectory rather than a discriminator field in the JSON, because
    :func:`load_results` globs ``*.json`` non-recursively: a check result in the
    day directory would be read as a malformed RunResult and silently dropped by
    the guard there, which is a confusing way to find out about a design choice.
    """
    return day_dir(cfg, on) / "checks"


def store_check_results(cfg: Config, results: list[CheckResult]) -> Path | None:
    """Write one project's checks from one run as a single JSON file."""
    if not results:
        return None
    directory = checks_dir(cfg, results[0].started_at.date())
    directory.mkdir(parents=True, exist_ok=True)
    when = results[0].started_at.strftime("%H%M%S")
    stem = _unique_stem(directory, f"{_slug(results[0].project)}-{when}")
    path = directory / f"{stem}.json"
    write_json(path, {"checks": [r.to_dict() for r in results]})
    return path


def load_check_results(cfg: Config, on: date) -> list[CheckResult]:
    """Every recorded check for a day, oldest first."""
    directory = checks_dir(cfg, on)
    if not directory.is_dir():
        return []
    results: list[CheckResult] = []
    for path in sorted(directory.glob("*.json")):
        raw = read_json(path, default=None)
        if not isinstance(raw, dict):
            continue
        for entry in raw.get("checks", []):
            try:
                results.append(CheckResult.from_dict(entry))
            except (KeyError, ValueError, TypeError):
                # One unreadable check must not sink the digest, same as a run.
                continue
    results.sort(key=lambda r: r.started_at)
    return results


def load_results(cfg: Config, on: date) -> list[RunResult]:
    """Every recorded result for a day, oldest first."""
    directory = day_dir(cfg, on)
    if not directory.is_dir():
        return []
    results: list[RunResult] = []
    for path in sorted(directory.glob("*.json")):
        raw = read_json(path, default=None)
        if not isinstance(raw, dict):
            continue
        try:
            results.append(RunResult.from_dict(raw))
        except (KeyError, ValueError, TypeError):
            # A single unreadable result must not sink the whole digest.
            continue
    results.sort(key=lambda r: r.started_at)
    return results


def format_duration(result: RunResult) -> str:
    if result.status == "skipped":
        return "—"
    total = int(round(result.duration_s))
    if total < 60:
        return f"{total}s"
    return f"{total // 60}m{total % 60:02d}s"


def format_tokens(n: int) -> str:
    """Compact token count for a status line: ``482``, ``48.2k``, ``1.2M``.

    A measure, not a bill — see :attr:`RunResult.tokens`.
    """
    n = int(n)
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{n / 1000:.1f}k"
    return f"{n / 1_000_000:.1f}M"


def tokens_by_project(results: list[RunResult]) -> dict[str, int]:
    """Total tokens each project spent today, across every status that ran.

    A failed or timed-out run still burned tokens, so it counts; ``skipped``
    reports zero and drops out on its own. Projects that reported nothing are
    left out entirely — a row of zeros is not information.
    """
    totals: dict[str, int] = {}
    for r in results:
        if r.project == PLACEHOLDER or r.tokens <= 0:
            continue
        totals[r.project] = totals.get(r.project, 0) + r.tokens
    return totals


def budget_bar(used: int, cap: int, width: int = 12) -> str:
    """``▓▓▓░░░`` — one cell per run when the cap is small, scaled when it isn't."""
    if cap <= 0:
        return ""
    cells = min(cap, width)
    filled = min(cells, round(used / cap * cells)) if cap else 0
    if used > 0 and filled == 0:
        filled = 1  # never render spent budget as an empty bar
    return "▓" * filled + "░" * (cells - filled)


def _budget_lines(cfg: Config, ledger: Ledger, on: date) -> list[str]:
    when = datetime.combine(on, datetime.min.time())
    lines = []
    for provider in cfg.enabled_providers():
        usage = ledger.usage(provider.name, provider.budget, when)
        bar = budget_bar(usage.day, usage.max_day)
        lines.append(
            f"- `{provider.name}` {bar} "
            f"{usage.day}/{usage.max_day} today · {usage.week}/{usage.max_week} week"
        )
    return lines


def dedupe(findings: list[Finding]) -> list[Finding]:
    """Collapse findings that are literally the same finding.

    Two runs of the same task on the same day surface the same problems, and
    three copies of one issue would push real findings out of the top five.
    The task stays in the key: the same file flagged by ``security_audit`` and
    by ``code_review`` is two different observations and both are worth seeing.
    """
    seen: set[tuple[str, str, str, str, str]] = set()
    unique: list[Finding] = []
    for f in findings:
        key = (f.severity, f.project, f.task, f.ref, f.text)
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    return unique


def _highlights(findings: list[Finding], limit: int = 5) -> list[Finding]:
    ordered = sorted(findings, key=lambda f: (f.rank, f.project, f.task))
    return ordered[:limit]


def _fmt_finding(f: Finding, *, with_project: bool) -> str:
    context = f"{f.project} · {f.task}" if with_project else f.task
    ref = f" · `{f.ref}`" if f.ref else ""
    return f"- {f.emoji} {f.text} — _{context}_{ref}"


#: A check reports its own verdict; these are not severities. A failing check is
#: a fact ("exit 1"), not a judgement call the way a model's HIGH is.
CHECK_MARK = {"pass": "✓", "fail": "✗", "timeout": "⏱", "error": "⚠"}


def _check_lines(checks: list[CheckResult]) -> list[str]:
    """One line per check, plus the output of any that did not pass."""
    out: list[str] = []
    for c in sorted(checks, key=lambda c: (c.project, c.started_at, c.name)):
        mark = CHECK_MARK.get(c.status, "⚠")
        detail = f"exit {c.exit_code}" if c.exit_code is not None else c.status
        out.append(f"- {mark} `{c.name}` — `{c.command}` · {detail}")
        if not c.ok and c.output:
            out.append("")
            out.append("  ```")
            out.extend(f"  {line}" for line in c.output.splitlines())
            out.append("  ```")
            out.append("")
    return out


def render_digest(
    cfg: Config,
    on: date,
    ledger: Ledger | None = None,
    results: list[RunResult] | None = None,
    generated_at: datetime | None = None,
    checks: list[CheckResult] | None = None,
) -> str:
    """Render ``DIGEST-YYYY-MM-DD.md`` for a day."""
    ledger = ledger if ledger is not None else Ledger()
    results = load_results(cfg, on) if results is None else results
    checks = load_check_results(cfg, on) if checks is None else checks
    generated_at = generated_at or datetime.now()

    findings: list[Finding] = []
    for r in results:
        if r.status == "ok":
            findings.extend(parse_findings(r))
    findings = dedupe(findings)

    # Checks count: a digest that renders a project section under a header
    # claiming "0 projects" is arguing with itself.
    projects_seen = sorted(
        {r.project for r in results if r.project != PLACEHOLDER}
        | {c.project for c in checks}
    )
    token_totals = tokens_by_project(results)
    total_tokens = sum(token_totals.values())

    out: list[str] = []
    out.append("# Nightaudit · morning digest")
    out.append("")
    summary = (
        f"{on.strftime('%a %b')} {on.day}, {on.year} · generated "
        f"{generated_at.strftime('%H:%M')} local · "
        f"{len(projects_seen)} project{'s' if len(projects_seen) != 1 else ''} · "
        f"{len(results)} run{'s' if len(results) != 1 else ''}"
    )
    if total_tokens > 0:
        summary += f" · {format_tokens(total_tokens)} tokens"
    out.append(summary)
    out.append("")

    out.append("## Budget remaining")
    out.append("")
    out.extend(_budget_lines(cfg, ledger, on) or ["- _no providers enabled_"])
    out.append("")

    if not results and not checks:
        out.append("## Highlights")
        out.append("")
        out.append("Nothing ran today — no runs were recorded.")
        out.append("")
        return "\n".join(out).rstrip() + "\n"

    failed_checks = [c for c in checks if not c.ok]

    out.append("## Highlights")
    out.append("")
    highlights = _highlights(findings)
    if highlights:
        out.extend(_fmt_finding(f, with_project=True) for f in highlights)
    elif any(r.status == "ok" for r in results):
        # "Clean" is a claim about the AI's reading of the code, and it must not
        # be made over the top of a check that came back red.
        out.append("No findings — every run came back clean.")
    else:
        out.append("No findings — no run completed successfully today.")
    if failed_checks:
        out.append("")
        names = ", ".join(sorted({f"`{c.name}` ({c.project})" for c in failed_checks}))
        out.append(
            f"{len(failed_checks)} configured "
            f"check{'s' if len(failed_checks) != 1 else ''} did not pass: {names}."
        )
    out.append("")

    by_project: dict[str, list[Finding]] = {}
    for f in findings:
        by_project.setdefault(f.project, []).append(f)

    checks_by_project: dict[str, list[CheckResult]] = {}
    for c in checks:
        checks_by_project.setdefault(c.project, []).append(c)

    with_content = sorted(set(by_project) | set(checks_by_project))
    if with_content:
        out.append("## By project")
        out.append("")
        for project in with_content:
            out.append(f"### {project}")
            out.append("")

            project_checks = checks_by_project.get(project, [])
            if project_checks:
                out.append("#### Checks")
                out.append("")
                out.extend(_check_lines(project_checks))
                out.append("")

            items = sorted(by_project.get(project, []), key=lambda f: (f.rank, f.task))
            if items or not project_checks:
                if project_checks:
                    out.append("#### Findings")
                    out.append("")
                line = f"{len(items)} finding{'s' if len(items) != 1 else ''}"
                if token_totals.get(project):
                    line += f" · {format_tokens(token_totals[project])} tokens"
                out.append(line)
                out.append("")
                out.extend(_fmt_finding(f, with_project=False) for f in items)
                out.append("")

    if total_tokens > 0:
        out.append("## Tokens")
        out.append("")
        out.append("How many tokens each project's reviews took today.")
        out.append("")
        for project in sorted(token_totals, key=lambda p: (-token_totals[p], p)):
            out.append(f"- {project} — {format_tokens(token_totals[project])}")
        out.append(f"- **total — {format_tokens(total_tokens)}**")
        out.append("")

    out.append("## Run log")
    out.append("")
    out.append("| project | task | provider | status | dur | time |")
    out.append("| --- | --- | --- | --- | --- | --- |")
    for r in sorted(results, key=lambda r: (r.started_at, r.project)):
        status = r.status
        if r.detail and r.status != "ok":
            status = f"{r.status} · {r.detail}"
        out.append(
            f"| {r.project} | {r.task} | {r.provider} | {status} | "
            f"{format_duration(r)} | {r.started_at.strftime('%H:%M')} |"
        )
    out.append("")
    out.append(
        "_Skipped and failed runs stay in the log so nothing silently "
        "disappears._"
    )
    out.append("")
    return "\n".join(out).rstrip() + "\n"


def write_digest(
    cfg: Config,
    on: date,
    ledger: Ledger | None = None,
    generated_at: datetime | None = None,
) -> Path:
    text = render_digest(cfg, on, ledger=ledger, generated_at=generated_at)
    path = digest_path(cfg, on)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
