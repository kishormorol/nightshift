"""Per-provider run ledger.

Counts *attempts*, not successes: a failed or timed-out run still consumed the
user's quota, so it still costs budget. The ledger is the only thing standing
between a cron job and someone's monthly limit, so it errs toward counting.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from nightaudit.config import Budget, state_dir
from nightaudit.store import read_json, write_json

#: Ledger entries older than this are dropped when the file is loaded.
RETENTION_DAYS = 30


def day_key(d: date) -> str:
    return d.isoformat()


def week_key(d: date) -> str:
    """ISO week key, e.g. ``2026-W29``. ISO weeks start on Monday."""
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


def _week_start(key: str) -> date | None:
    """The Monday of an ISO week key, or ``None`` if unparseable."""
    try:
        year_s, week_s = key.split("-W", 1)
        return date.fromisocalendar(int(year_s), int(week_s), 1)
    except (ValueError, TypeError):
        return None


def _day_start(key: str) -> date | None:
    try:
        return date.fromisoformat(key)
    except (ValueError, TypeError):
        return None


def entry_date(key: str) -> date | None:
    """The date a ledger key refers to, whichever form it takes."""
    return _week_start(key) if "-W" in key else _day_start(key)


@dataclass
class Usage:
    """What a provider has spent, against what it is allowed."""

    day: int
    week: int
    max_day: int
    max_week: int

    @property
    def day_exhausted(self) -> bool:
        return self.day >= self.max_day

    @property
    def week_exhausted(self) -> bool:
        return self.week >= self.max_week

    @property
    def exhausted(self) -> bool:
        return self.day_exhausted or self.week_exhausted

    def reason(self) -> str:
        if self.day_exhausted:
            return f"daily budget spent ({self.day}/{self.max_day} today)"
        if self.week_exhausted:
            return f"weekly budget spent ({self.week}/{self.max_week} this week)"
        return ""


def ledger_path() -> Path:
    return state_dir() / "ledger.json"


class Ledger:
    """A JSON map of ``{provider: {day-or-week key: count}}``."""

    def __init__(self, path: Path | None = None):
        self.path = path or ledger_path()
        self._data: dict[str, dict[str, int]] = self._load()

    def _load(self) -> dict[str, dict[str, int]]:
        raw = read_json(self.path, default={})
        if not isinstance(raw, dict):
            return {}
        data: dict[str, dict[str, int]] = {}
        for provider, entries in raw.items():
            if not isinstance(provider, str) or not isinstance(entries, dict):
                continue
            clean: dict[str, int] = {}
            for key, count in entries.items():
                if isinstance(key, str) and isinstance(count, int) and not isinstance(count, bool):
                    clean[key] = count
            data[provider] = clean
        return data

    def prune(self, today: date | None = None) -> int:
        """Drop entries older than :data:`RETENTION_DAYS`. Returns count removed."""
        today = today or date.today()
        cutoff = today - timedelta(days=RETENTION_DAYS)
        removed = 0
        for provider, entries in self._data.items():
            for key in list(entries):
                when = entry_date(key)
                if when is None or when < cutoff:
                    del entries[key]
                    removed += 1
        return removed

    def count(self, provider: str, key: str) -> int:
        return self._data.get(provider, {}).get(key, 0)

    def usage(self, provider: str, budget: Budget, when: datetime | None = None) -> Usage:
        when = when or datetime.now()
        d = when.date()
        return Usage(
            day=self.count(provider, day_key(d)),
            week=self.count(provider, week_key(d)),
            max_day=budget.max_runs_per_day,
            max_week=budget.max_runs_per_week,
        )

    def increment(self, provider: str, when: datetime | None = None, by: int = 1) -> None:
        """Record ``by`` attempts against ``provider`` and persist immediately.

        Persisting eagerly matters: if the process dies after spending quota but
        before writing, the next run would happily spend it again.
        """
        when = when or datetime.now()
        d = when.date()
        entries = self._data.setdefault(provider, {})
        for key in (day_key(d), week_key(d)):
            entries[key] = entries.get(key, 0) + by
        self.save()

    def save(self) -> None:
        write_json(self.path, self._data)

    def as_dict(self) -> dict[str, dict[str, int]]:
        return {p: dict(e) for p, e in self._data.items()}
