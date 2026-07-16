from __future__ import annotations

from nightaudit import cron


def test_entries_match_the_documented_schedule():
    hourly, daily = cron.entries("/usr/local/bin/nightaudit")
    assert hourly.startswith("0 * * * *")
    assert " run " in hourly
    assert daily.startswith("30 7 * * *")
    assert " digest " in daily


def test_block_is_fenced_by_markers():
    block = cron.block("/usr/local/bin/nightaudit")
    assert block.startswith(cron.MARKER)
    assert block.rstrip("\n").endswith(cron.END_MARKER)


def test_installing_preserves_unrelated_entries():
    existing = "0 9 * * * /usr/bin/backup.sh\n"
    merged = cron.merged(existing, "/usr/local/bin/nightaudit")
    assert "/usr/bin/backup.sh" in merged
    assert "nightaudit run" in merged


def test_reinstalling_replaces_rather_than_duplicates():
    first = cron.merged("", "/usr/local/bin/nightaudit")
    second = cron.merged(first, "/usr/local/bin/nightaudit")
    assert second.count("nightaudit run") == 1
    assert second.count(cron.MARKER) == 1


def test_reinstalling_after_a_path_change_drops_the_old_line():
    first = cron.merged("", "/old/path/nightaudit")
    second = cron.merged(first, "/new/path/nightaudit")
    assert "/old/path/nightaudit" not in second
    assert "/new/path/nightaudit" in second


def test_strip_block_removes_only_our_lines():
    existing = cron.merged("0 9 * * * /usr/bin/backup.sh", "/usr/local/bin/nightaudit")
    stripped = cron.strip_block(existing)
    assert stripped.strip() == "0 9 * * * /usr/bin/backup.sh"
    assert "nightaudit" not in stripped


def test_strip_block_on_a_crontab_we_never_touched_is_a_noop():
    existing = "0 9 * * * /usr/bin/backup.sh"
    assert cron.strip_block(existing).strip() == existing


def test_merged_output_ends_with_a_newline():
    # crontab(1) rejects a file whose last line has no terminator.
    assert cron.merged("", "/usr/local/bin/nightaudit").endswith("\n")
    assert cron.merged("0 9 * * * x", "/usr/local/bin/nightaudit").endswith("\n")
