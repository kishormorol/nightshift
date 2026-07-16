from __future__ import annotations

from datetime import date, datetime, timedelta

from nightaudit.budget import Ledger, day_key, entry_date, week_key
from nightaudit.config import Budget


def test_week_key_uses_iso_weeks():
    # 2026-01-01 is a Thursday, so it belongs to ISO week 1 of 2026.
    assert week_key(date(2026, 1, 1)) == "2026-W01"
    # ISO weeks start Monday: the 2026-07-14 (Tue) week began 2026-07-13.
    assert week_key(date(2026, 7, 13)) == week_key(date(2026, 7, 14))
    # Sunday closes the same ISO week; Monday opens the next one.
    assert week_key(date(2026, 7, 19)) == week_key(date(2026, 7, 13))
    assert week_key(date(2026, 7, 20)) != week_key(date(2026, 7, 13))


def test_week_key_handles_year_boundary():
    # 2027-01-01 is a Friday and belongs to ISO week 53 of *2026*.
    assert week_key(date(2027, 1, 1)) == "2026-W53"


def test_entry_date_round_trips_both_key_shapes():
    assert entry_date(day_key(date(2026, 7, 14))) == date(2026, 7, 14)
    assert entry_date(week_key(date(2026, 7, 14))) == date(2026, 7, 13)  # the Monday
    assert entry_date("garbage") is None


def test_increment_bumps_both_day_and_week(tmp_path):
    ledger = Ledger(tmp_path / "ledger.json")
    when = datetime(2026, 7, 14, 3, 0)
    ledger.increment("claude_code", when)
    ledger.increment("claude_code", when)
    assert ledger.count("claude_code", "2026-07-14") == 2
    assert ledger.count("claude_code", "2026-W29") == 2


def test_increment_persists_immediately(tmp_path):
    path = tmp_path / "ledger.json"
    when = datetime(2026, 7, 14, 3, 0)
    Ledger(path).increment("claude_code", when)
    # A second process must see the spend — a crash mid-run must not refund it.
    assert Ledger(path).count("claude_code", "2026-07-14") == 1


def test_usage_reports_against_caps(tmp_path):
    ledger = Ledger(tmp_path / "ledger.json")
    when = datetime(2026, 7, 14, 3, 0)
    for _ in range(3):
        ledger.increment("claude_code", when)
    usage = ledger.usage("claude_code", Budget(6, 30), when)
    assert (usage.day, usage.week, usage.max_day, usage.max_week) == (3, 3, 6, 30)
    assert usage.exhausted is False


def test_daily_cap_binds(tmp_path):
    ledger = Ledger(tmp_path / "ledger.json")
    when = datetime(2026, 7, 14, 3, 0)
    for _ in range(6):
        ledger.increment("claude_code", when)
    usage = ledger.usage("claude_code", Budget(6, 30), when)
    assert usage.exhausted is True
    assert usage.day_exhausted is True
    assert usage.week_exhausted is False
    assert "daily budget spent" in usage.reason()


def test_weekly_cap_binds_even_when_daily_has_room(tmp_path):
    ledger = Ledger(tmp_path / "ledger.json")
    monday = datetime(2026, 7, 13, 3, 0)
    # Spread 30 runs across the week without ever hitting the 6/day cap.
    for offset in range(5):
        for _ in range(6):
            ledger.increment("claude_code", monday + timedelta(days=offset))
    saturday = monday + timedelta(days=5)
    usage = ledger.usage("claude_code", Budget(6, 30), saturday)
    assert usage.day == 0  # nothing spent today
    assert usage.week == 30
    assert usage.day_exhausted is False
    assert usage.week_exhausted is True
    assert usage.exhausted is True
    assert "weekly budget spent" in usage.reason()


def test_counts_are_per_provider(tmp_path):
    ledger = Ledger(tmp_path / "ledger.json")
    when = datetime(2026, 7, 14, 3, 0)
    ledger.increment("claude_code", when)
    assert ledger.usage("codex", Budget(6, 30), when).day == 0


def test_prune_drops_entries_older_than_retention(tmp_path):
    ledger = Ledger(tmp_path / "ledger.json")
    today = date(2026, 7, 14)
    ledger.increment("claude_code", datetime(2026, 7, 14))
    ledger.increment("claude_code", datetime(2026, 5, 1))  # ~74 days earlier
    ledger.prune(today)
    assert ledger.count("claude_code", "2026-07-14") == 1
    assert ledger.count("claude_code", "2026-05-01") == 0


def test_prune_keeps_entries_inside_retention(tmp_path):
    ledger = Ledger(tmp_path / "ledger.json")
    today = date(2026, 7, 14)
    recent = datetime(2026, 7, 1)  # 13 days ago
    ledger.increment("claude_code", recent)
    ledger.prune(today)
    assert ledger.count("claude_code", "2026-07-01") == 1


def test_prune_drops_unparseable_keys(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text('{"claude_code": {"not-a-date": 4}}', encoding="utf-8")
    ledger = Ledger(path)
    ledger.prune(date(2026, 7, 14))
    assert ledger.count("claude_code", "not-a-date") == 0


def test_corrupt_ledger_starts_from_empty_rather_than_crashing(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text("{not json at all", encoding="utf-8")
    ledger = Ledger(path)
    assert ledger.count("claude_code", "2026-07-14") == 0
    ledger.increment("claude_code", datetime(2026, 7, 14))
    assert Ledger(path).count("claude_code", "2026-07-14") == 1


def test_non_int_counts_are_ignored_on_load(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text('{"claude_code": {"2026-07-14": "lots"}}', encoding="utf-8")
    assert Ledger(path).count("claude_code", "2026-07-14") == 0
