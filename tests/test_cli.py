"""CLI behaviour, with the adapter registry stubbed out.

The rule under test throughout: expected conditions exit 0 with one readable
line. Cron reads stderr, and a tool that mails a traceback every hour gets
uninstalled.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from click.testing import CliRunner

from nightaudit.cli import main
from tests.conftest import FakeAdapter, build_config

AT = datetime(2026, 7, 14, 3, 0)


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def written_cfg(tmp_path, project_dir, isolated_home):
    """A real config file on disk, where the CLI will look for it."""
    cfg = build_config(tmp_path, project_dir, windows=["00:00-23:59"])
    (isolated_home / "config.yaml").write_text(
        f"""
providers:
  claude_code:
    enabled: true
    budget: {{max_runs_per_day: 6, max_runs_per_week: 30}}
projects:
  - name: {project_dir.name}
    path: {project_dir}
    tasks: [code_review]
schedule:
  windows: ["00:00-23:59"]
  idle_minutes: 60
digest:
  dir: {tmp_path / "reports"}
run:
  timeout_s: 600
""".strip(),
        encoding="utf-8",
    )
    return cfg


@pytest.fixture
def stub_registry(monkeypatch):
    adapter = FakeAdapter()

    monkeypatch.setattr(
        "nightaudit.cli.adapter_registry.get", lambda n, binary=None: adapter
    )
    monkeypatch.setattr(
        "nightaudit.scheduler.adapter_registry.get", lambda n, binary=None: adapter
    )
    monkeypatch.setattr(
        "nightaudit.cli.adapter_registry.names", lambda: ["claude_code"]
    )
    return adapter


# ---- top level --------------------------------------------------------


def test_version(runner):
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.3.0" in result.output


def test_help_lists_every_command(runner):
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for cmd in ("init", "run", "digest", "status"):
        assert cmd in result.output


# ---- run --------------------------------------------------------------


def test_run_without_config_fails_with_a_pointer_to_init(runner, isolated_home):
    result = runner.invoke(main, ["run"])
    assert result.exit_code != 0
    assert "nightaudit init" in result.output
    assert "Traceback" not in result.output


def test_invalid_config_reports_cleanly(runner, isolated_home):
    (isolated_home / "config.yaml").write_text("projects: [", encoding="utf-8")
    result = runner.invoke(main, ["run"])
    assert result.exit_code != 0
    assert "not valid YAML" in result.output
    assert "Traceback" not in result.output


def test_run_reports_the_outcome(runner, written_cfg, stub_registry):
    result = runner.invoke(main, ["run", "--now"])
    assert result.exit_code == 0
    assert "ok" in result.output
    assert "code_review" in result.output


def test_run_counts_findings(runner, written_cfg, stub_registry):
    stub_registry.results = [
        ("ok", "- HIGH a.py:1 — x\n- LOW b.py:2 — y")
    ]
    result = runner.invoke(main, ["run", "--now"])
    assert "2 findings" in result.output


def test_run_says_when_there_are_no_findings(runner, written_cfg, stub_registry):
    stub_registry.results = [("ok", "No findings.")]
    result = runner.invoke(main, ["run", "--now"])
    assert "no findings" in result.output


def test_a_blocked_run_exits_zero_and_explains(runner, written_cfg, stub_registry):
    stub_registry.human_used_at = datetime.now()
    result = runner.invoke(main, ["run"])
    # Cron calls this hourly; "not now" is success, not an error.
    assert result.exit_code == 0
    assert "nothing to do" in result.output
    assert stub_registry.calls == []


def test_a_failing_adapter_does_not_produce_a_traceback(runner, written_cfg, stub_registry):
    stub_registry.results = [RuntimeError("boom"), RuntimeError("boom")]
    result = runner.invoke(main, ["run", "--now"])
    assert result.exit_code == 0
    assert "failed" in result.output
    assert "Traceback" not in result.output


# ---- digest -----------------------------------------------------------


def test_digest_writes_the_file(runner, written_cfg, stub_registry):
    runner.invoke(main, ["run", "--now"])
    result = runner.invoke(main, ["digest"])
    assert result.exit_code == 0
    assert "DIGEST-" in result.output
    written = list(written_cfg.digest_dir.glob("DIGEST-*.md"))
    assert len(written) == 1


def test_digest_stdout_prints_without_writing(runner, written_cfg, stub_registry):
    runner.invoke(main, ["run", "--now"])
    result = runner.invoke(main, ["digest", "--stdout"])
    assert result.exit_code == 0
    assert "# Nightaudit · morning digest" in result.output
    assert list(written_cfg.digest_dir.glob("DIGEST-*.md")) == []


def test_digest_for_an_empty_day_still_renders(runner, written_cfg, stub_registry):
    result = runner.invoke(main, ["digest", "--date", "2020-01-01", "--stdout"])
    assert result.exit_code == 0
    assert "Nothing ran today" in result.output


def test_digest_rejects_a_bad_date(runner, written_cfg, stub_registry):
    result = runner.invoke(main, ["digest", "--date", "yesterday"])
    assert result.exit_code != 0
    assert "YYYY-MM-DD" in result.output
    assert "Traceback" not in result.output


# ---- status -----------------------------------------------------------


def test_status_shows_budget_and_schedule(runner, written_cfg, stub_registry):
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0
    assert "0/6 today" in result.output
    assert "0/30 week" in result.output
    assert "00:00-23:59" in result.output
    assert "up next" in result.output


def test_status_reports_an_unavailable_provider(runner, written_cfg, stub_registry):
    stub_registry.is_available = False
    stub_registry.unavailable_reason = "`claude` is not on PATH"
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0
    assert "✗" in result.output
    assert "not on PATH" in result.output


def test_status_lists_recent_runs(runner, written_cfg, stub_registry):
    runner.invoke(main, ["run", "--now"])
    result = runner.invoke(main, ["status"])
    assert "last runs" in result.output
    assert "code_review" in result.output


def test_status_says_when_nothing_has_run(runner, written_cfg, stub_registry):
    result = runner.invoke(main, ["status"])
    assert "none recorded yet" in result.output


def test_status_warns_about_a_missing_prompt_template(
    runner, tmp_path, project_dir, isolated_home, stub_registry
):
    (isolated_home / "config.yaml").write_text(
        f"""
providers:
  claude_code: {{enabled: true}}
projects:
  - name: {project_dir.name}
    path: {project_dir}
    tasks: [not_a_real_task]
digest:
  dir: {tmp_path / "reports"}
""".strip(),
        encoding="utf-8",
    )
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0
    assert "no prompt template for: not_a_real_task" in result.output


# ---- init -------------------------------------------------------------


def test_init_writes_a_config_that_loads_back(
    runner, tmp_path, project_dir, isolated_home, stub_registry
):
    from nightaudit.config import load

    answers = "\n".join(
        [
            str(project_dir),  # project path
            "acme-api",  # name
            "code_review",  # tasks
            "",  # no more projects
            "00:00-06:00",  # windows
            "60",  # idle
            str(tmp_path / "reports"),  # digest dir
            "n",  # don't touch the real crontab
        ]
    )
    result = runner.invoke(main, ["init"], input=answers + "\n")
    assert result.exit_code == 0, result.output

    cfg = load(isolated_home / "config.yaml")
    assert [p.name for p in cfg.enabled_providers()] == ["claude_code"]
    assert cfg.projects[0].name == "acme-api"
    assert cfg.projects[0].tasks == ("code_review",)
    assert cfg.schedule.windows[0].raw == "00:00-06:00"


def test_init_prints_cron_lines_and_can_decline_installing(
    runner, tmp_path, project_dir, isolated_home, stub_registry
):
    answers = "\n".join(
        [str(project_dir), "acme-api", "code_review", "", "00:00-06:00", "60",
         str(tmp_path / "reports"), "n"]
    )
    result = runner.invoke(main, ["init"], input=answers + "\n")
    assert "run" in result.output and "digest" in result.output
    assert "0 * * * *" in result.output
    assert "30 7 * * *" in result.output
    assert "crontab -e" in result.output


def test_init_refuses_when_no_cli_is_installed(runner, monkeypatch, isolated_home):
    dead = FakeAdapter(is_available=False, unavailable_reason="not installed")
    monkeypatch.setattr("nightaudit.cli.adapter_registry.get", lambda n, binary=None: dead)
    monkeypatch.setattr("nightaudit.cli.adapter_registry.names", lambda: ["claude_code"])
    result = runner.invoke(main, ["init"])
    assert result.exit_code != 0
    assert "No usable AI CLI found" in result.output


def test_init_rejects_a_path_that_is_not_a_directory(
    runner, tmp_path, project_dir, isolated_home, stub_registry
):
    answers = "\n".join(
        [
            str(tmp_path / "does-not-exist"),
            str(project_dir),
            "acme-api",
            "code_review",
            "",
            "00:00-06:00",
            "60",
            str(tmp_path / "reports"),
            "n",
        ]
    )
    result = runner.invoke(main, ["init"], input=answers + "\n")
    assert "is not a directory" in result.output
    assert result.exit_code == 0


def test_init_rejects_an_unknown_task(
    runner, tmp_path, project_dir, isolated_home, stub_registry
):
    answers = "\n".join(
        [str(project_dir), "acme-api", "made_up_task", "", "00:00-06:00", "60",
         str(tmp_path / "reports"), "n"]
    )
    result = runner.invoke(main, ["init"], input=answers + "\n")
    assert "unknown task(s): made_up_task" in result.output
    # Every project was rejected, so there is nothing to schedule.
    assert result.exit_code != 0
    assert "No projects registered" in result.output


def test_init_declines_to_clobber_an_existing_config(
    runner, written_cfg, isolated_home, stub_registry
):
    before = (isolated_home / "config.yaml").read_text(encoding="utf-8")
    result = runner.invoke(main, ["init"], input="n\n")
    assert result.exit_code == 0
    assert "Left it alone" in result.output
    assert (isolated_home / "config.yaml").read_text(encoding="utf-8") == before
