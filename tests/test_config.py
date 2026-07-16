from __future__ import annotations

from datetime import datetime, time

import pytest

from nightaudit.config import (
    DEFAULT_CHECK_TIMEOUT_S,
    ConfigError,
    Schedule,
    load,
    parse,
    parse_window,
)


def test_parses_the_spec_example(tmp_path):
    cfg = parse(
        {
            "providers": {
                "claude_code": {
                    "enabled": True,
                    "budget": {"max_runs_per_day": 6, "max_runs_per_week": 30},
                },
                "codex": {"enabled": False},
                "copilot": {"enabled": False},
            },
            "projects": [
                {
                    "name": "gradagent",
                    "path": "~/projects/gradagent",
                    "tasks": ["code_review", "deps_audit", "docs_drift"],
                }
            ],
            "schedule": {
                "windows": ["09:00-18:00", "00:00-06:00"],
                "idle_minutes": 60,
            },
            "digest": {"dir": "~/nightaudit-reports"},
            "run": {"timeout_s": 600},
        }
    )
    assert [p.name for p in cfg.enabled_providers()] == ["claude_code"]
    assert cfg.provider("claude_code").budget.max_runs_per_day == 6
    assert cfg.projects[0].tasks == ("code_review", "deps_audit", "docs_drift")
    assert cfg.timeout_s == 600


def test_expands_tilde_in_every_path():
    cfg = parse(
        {
            "providers": {"claude_code": {"enabled": True}},
            "projects": [{"name": "p", "path": "~/somewhere", "tasks": ["code_review"]}],
            "digest": {"dir": "~/reports"},
        }
    )
    assert "~" not in str(cfg.projects[0].path)
    assert cfg.projects[0].path.is_absolute()
    assert "~" not in str(cfg.digest_dir)
    assert cfg.digest_dir.is_absolute()


def test_defaults_applied_when_sections_omitted():
    cfg = parse(
        {
            "providers": {"claude_code": {"enabled": True}},
            "projects": [{"name": "p", "path": "/tmp/p", "tasks": ["code_review"]}],
        }
    )
    assert cfg.timeout_s == 600
    assert cfg.schedule.idle_minutes == 60
    assert cfg.provider("claude_code").budget.max_runs_per_day == 6
    assert cfg.provider("claude_code").budget.max_runs_per_week == 30


def test_pairs_are_project_major_in_config_order():
    cfg = parse(
        {
            "providers": {"claude_code": {"enabled": True}},
            "projects": [
                {"name": "a", "path": "/tmp/a", "tasks": ["code_review", "deps_audit"]},
                {"name": "b", "path": "/tmp/b", "tasks": ["docs_drift"]},
            ],
        }
    )
    assert cfg.pairs() == [
        ("a", "code_review"),
        ("a", "deps_audit"),
        ("b", "docs_drift"),
    ]


def test_duplicate_tasks_within_a_project_collapse():
    cfg = parse(
        {
            "providers": {"claude_code": {"enabled": True}},
            "projects": [
                {"name": "a", "path": "/tmp/a", "tasks": ["code_review", "code_review"]}
            ],
        }
    )
    assert cfg.projects[0].tasks == ("code_review",)


# ---- windows ----------------------------------------------------------


@pytest.mark.parametrize(
    "raw,at,expected",
    [
        ("09:00-18:00", time(8, 59), False),
        ("09:00-18:00", time(9, 0), True),
        ("09:00-18:00", time(17, 59), True),
        ("09:00-18:00", time(18, 0), False),  # end is exclusive
        # Crossing midnight is the case that quietly breaks naive comparisons.
        ("22:00-06:00", time(21, 59), False),
        ("22:00-06:00", time(22, 0), True),
        ("22:00-06:00", time(23, 59), True),
        ("22:00-06:00", time(0, 0), True),
        ("22:00-06:00", time(5, 59), True),
        ("22:00-06:00", time(6, 0), False),
        ("22:00-06:00", time(12, 0), False),
    ],
)
def test_window_contains(raw, at, expected):
    assert parse_window(raw, "w").contains(at) is expected


def test_window_knows_when_it_crosses_midnight():
    assert parse_window("22:00-06:00", "w").crosses_midnight is True
    assert parse_window("09:00-18:00", "w").crosses_midnight is False


def test_schedule_is_open_across_midnight():
    sched = Schedule(windows=(parse_window("00:00-06:00", "w"),), idle_minutes=0)
    assert sched.is_open(datetime(2026, 7, 14, 3, 0)) is True
    assert sched.is_open(datetime(2026, 7, 14, 7, 0)) is False


def test_schedule_next_open_finds_tomorrow_morning():
    sched = Schedule(windows=(parse_window("00:00-06:00", "w"),), idle_minutes=0)
    nxt = sched.next_open(datetime(2026, 7, 14, 9, 0))
    assert nxt == datetime(2026, 7, 15, 0, 0)


def test_schedule_next_open_returns_now_when_already_open():
    sched = Schedule(windows=(parse_window("00:00-06:00", "w"),), idle_minutes=0)
    now = datetime(2026, 7, 14, 3, 0)
    assert sched.next_open(now) == now


@pytest.mark.parametrize(
    "raw",
    ["09:00", "0900-1800", "09:00-", "25:00-26:00", "09:70-10:00", "", "nine to five"],
)
def test_malformed_windows_rejected(raw):
    with pytest.raises(ConfigError):
        parse_window(raw, "schedule.windows[0]")


def test_zero_length_window_rejected_with_a_hint():
    with pytest.raises(ConfigError, match="same time"):
        parse_window("09:00-09:00", "schedule.windows[0]")


# ---- validation errors are for humans ---------------------------------


def test_no_projects_is_an_error():
    with pytest.raises(ConfigError, match="nightaudit init"):
        parse({"providers": {"claude_code": {"enabled": True}}})


def test_empty_project_list_is_an_error():
    with pytest.raises(ConfigError, match="nothing to review"):
        parse({"providers": {"claude_code": {"enabled": True}}, "projects": []})


def test_all_providers_disabled_is_an_error():
    with pytest.raises(ConfigError, match="every provider is disabled"):
        parse(
            {
                "providers": {"claude_code": {"enabled": False}},
                "projects": [{"name": "p", "path": "/tmp/p", "tasks": ["code_review"]}],
            }
        )


def test_unknown_provider_names_the_known_ones():
    with pytest.raises(ConfigError, match="claude_code"):
        parse({"providers": {"claude_kode": {"enabled": True}}, "projects": []})


def _with_checks(checks):
    return {
        "providers": {"claude_code": {"enabled": True}},
        "projects": [
            {"name": "p", "path": "/tmp/p", "tasks": ["code_review"], "checks": checks}
        ],
    }


def test_a_project_has_no_checks_by_default():
    cfg = parse(
        {
            "providers": {"claude_code": {"enabled": True}},
            "projects": [{"name": "p", "path": "/tmp/p", "tasks": ["code_review"]}],
        }
    )
    assert cfg.projects[0].checks == ()


def test_checks_are_parsed_in_order():
    cfg = parse(
        _with_checks(
            [
                {"name": "tests", "run": "pytest -q"},
                {"name": "lint", "run": "ruff check .", "timeout_s": 30},
            ]
        )
    )
    checks = cfg.projects[0].checks
    assert [c.name for c in checks] == ["tests", "lint"]
    assert checks[0].run == "pytest -q"
    assert checks[0].timeout_s == DEFAULT_CHECK_TIMEOUT_S
    assert checks[1].timeout_s == 30


def test_a_command_is_split_into_argv_not_handed_to_a_shell():
    check = parse(_with_checks([{"name": "t", "run": "pytest -q -k 'not slow'"}])).projects[0].checks[0]
    assert check.argv == ["pytest", "-q", "-k", "not slow"]


def test_an_unbalanced_quote_is_caught_while_you_are_editing_the_file():
    # Rather than at 3am, in a digest, as a check that mysteriously never ran.
    with pytest.raises(ConfigError, match="is not a valid command"):
        parse(_with_checks([{"name": "t", "run": "pytest -k 'unclosed"}]))


def test_a_check_that_names_no_command_is_rejected():
    with pytest.raises(ConfigError, match="expected a command"):
        parse(_with_checks([{"name": "t", "run": "   "}]))


def test_duplicate_check_names_are_rejected():
    with pytest.raises(ConfigError, match="duplicate check name"):
        parse(_with_checks([{"name": "t", "run": "a"}, {"name": "t", "run": "b"}]))


def test_an_unknown_check_field_names_the_expected_ones():
    with pytest.raises(ConfigError, match="expected name, run, timeout_s"):
        parse(_with_checks([{"name": "t", "run": "a", "shell": True}]))


@pytest.mark.parametrize("value", [0, -1, "soon", True])
def test_a_check_timeout_must_be_a_positive_number(value):
    with pytest.raises(ConfigError, match=r"checks\[0\].timeout_s"):
        parse(_with_checks([{"name": "t", "run": "a", "timeout_s": value}]))


def test_an_empty_checks_list_says_to_drop_the_key():
    with pytest.raises(ConfigError, match="drop the key"):
        parse(_with_checks([]))


def test_a_check_naming_a_program_that_does_not_exist_still_parses():
    # Same reason as providers.*.binary: what is installed depends on the
    # machine, not the file. The runner reports it as an error, in the digest.
    cfg = parse(_with_checks([{"name": "t", "run": "/nowhere/nonesuch --fast"}]))
    assert cfg.projects[0].checks[0].argv == ["/nowhere/nonesuch", "--fast"]


def _with_binary(value):
    return {
        "providers": {"codex": {"enabled": True, "binary": value}},
        "projects": [{"name": "p", "path": "/tmp/p", "tasks": ["code_review"]}],
    }


def test_binary_defaults_to_none_so_the_adapter_keeps_its_own_name():
    cfg = parse(
        {
            "providers": {"claude_code": {"enabled": True}},
            "projects": [{"name": "p", "path": "/tmp/p", "tasks": ["code_review"]}],
        }
    )
    assert cfg.provider("claude_code").binary is None


def test_binary_takes_a_path():
    path = "/Applications/ChatGPT.app/Contents/Resources/codex"
    assert parse(_with_binary(path)).provider("codex").binary == path


def test_binary_is_stripped():
    assert parse(_with_binary("  codex  ")).provider("codex").binary == "codex"


@pytest.mark.parametrize("value", ["", "   ", 42, True, ["codex"]])
def test_binary_rejects_anything_that_is_not_a_command(value):
    with pytest.raises(ConfigError, match="providers.codex.binary"):
        parse(_with_binary(value))


def test_a_missing_binary_path_still_parses():
    # Config load must not depend on what happens to be installed: the adapter
    # reports an absent CLI as unavailable, which is a skip with a reason. A
    # ConfigError here would instead stop every other project from running.
    cfg = parse(_with_binary("/nowhere/codex"))
    assert cfg.provider("codex").binary == "/nowhere/codex"


def test_unknown_top_level_key_is_rejected():
    with pytest.raises(ConfigError, match="unknown top-level key"):
        parse(
            {
                "providers": {"claude_code": {"enabled": True}},
                "projects": [{"name": "p", "path": "/tmp/p", "tasks": ["code_review"]}],
                "schedual": {},
            }
        )


def test_typo_in_project_field_is_rejected():
    with pytest.raises(ConfigError, match="unknown field"):
        parse(
            {
                "providers": {"claude_code": {"enabled": True}},
                "projects": [
                    {"name": "p", "path": "/tmp/p", "task": ["code_review"]}
                ],
            }
        )


def test_duplicate_project_names_rejected():
    with pytest.raises(ConfigError, match="duplicate"):
        parse(
            {
                "providers": {"claude_code": {"enabled": True}},
                "projects": [
                    {"name": "p", "path": "/tmp/a", "tasks": ["code_review"]},
                    {"name": "p", "path": "/tmp/b", "tasks": ["code_review"]},
                ],
            }
        )


def test_weekly_cap_below_daily_cap_is_rejected():
    with pytest.raises(ConfigError, match="unreachable"):
        parse(
            {
                "providers": {
                    "claude_code": {
                        "enabled": True,
                        "budget": {"max_runs_per_day": 10, "max_runs_per_week": 5},
                    }
                },
                "projects": [{"name": "p", "path": "/tmp/p", "tasks": ["code_review"]}],
            }
        )


def test_zero_budget_is_rejected():
    with pytest.raises(ConfigError, match="greater than 0"):
        parse(
            {
                "providers": {
                    "claude_code": {"enabled": True, "budget": {"max_runs_per_day": 0}}
                },
                "projects": [{"name": "p", "path": "/tmp/p", "tasks": ["code_review"]}],
            }
        )


def test_bool_is_not_accepted_as_an_int():
    # yaml turns `max_runs_per_day: true` into a bool, which int() would accept.
    with pytest.raises(ConfigError, match="whole number"):
        parse(
            {
                "providers": {
                    "claude_code": {"enabled": True, "budget": {"max_runs_per_day": True}}
                },
                "projects": [{"name": "p", "path": "/tmp/p", "tasks": ["code_review"]}],
            }
        )


def test_bad_task_name_is_rejected():
    with pytest.raises(ConfigError, match="not a valid task name"):
        parse(
            {
                "providers": {"claude_code": {"enabled": True}},
                "projects": [
                    {"name": "p", "path": "/tmp/p", "tasks": ["../../etc/passwd"]}
                ],
            }
        )


# ---- loading from disk ------------------------------------------------


def test_missing_file_points_at_init(tmp_path):
    with pytest.raises(ConfigError, match="nightaudit init"):
        load(tmp_path / "nope.yaml")


def test_invalid_yaml_names_the_file(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("providers: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load(path)


def test_empty_file_is_an_error(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ConfigError, match="empty"):
        load(path)


def test_load_prefixes_errors_with_the_path(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("providers:\n  claude_code:\n    enabled: true\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=str(path)):
        load(path)
