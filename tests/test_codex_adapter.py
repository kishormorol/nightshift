"""Codex adapter, driven entirely through a mocked ``subprocess``.

Nothing here launches a real CLI or spends a token. The fake stands in for
``Popen`` rather than for ``stream_ndjson``, so these tests exercise the real
process machinery — the reader, the deadline, the reap — and not a convenient
simplification of it.
"""

from __future__ import annotations

import io
import json
import subprocess
from datetime import datetime, timedelta

import pytest

from nightaudit import sessions
from nightaudit.adapters.codex import APPROVAL, SANDBOX, CodexAdapter


@pytest.fixture
def adapter():
    return CodexAdapter()


class FakePopen:
    """Just enough Popen to drive the streaming reader.

    The streams are ``StringIO`` rather than plain iterators so they behave like
    the real pipes: iterable, and closeable on the way out.
    """

    def __init__(self, lines, returncode=0, stderr_lines=()):
        self.stdout = io.StringIO("".join(lines))
        self.stderr = io.StringIO("".join(stderr_lines))
        self.returncode = returncode
        self.pid = 424242

    def wait(self, timeout=None):
        return self.returncode

    def poll(self):
        return self.returncode

    def kill(self):
        pass


def line(payload: dict) -> str:
    return json.dumps(payload) + "\n"


def item(kind: str, item_type: str, **fields) -> str:
    return line({"type": kind, "item": {"id": "i1", "type": item_type, **fields}})


ANSWER = "- HIGH api/auth.py:142 — no exp claim on the JWT"

#: A realistic run: thread starts, model reasons, greps, then answers.
STREAM = [
    line({"type": "thread.started", "thread_id": "thread-abc-123"}),
    line({"type": "turn.started"}),
    item("item.completed", "reasoning", text="Let me look at the auth code."),
    item("item.started", "command_execution", command="rg -n jwt api/"),
    item(
        "item.completed",
        "command_execution",
        command="rg -n jwt api/",
        aggregated_output="api/auth.py:142\napi/x.py:9",
        exit_code=0,
        status="completed",
    ),
    item("item.completed", "agent_message", text=ANSWER),
    line({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}),
]


@pytest.fixture
def popen_spy(monkeypatch):
    calls: list[dict] = []
    box = {"proc": FakePopen(STREAM), "raises": None}

    def fake_popen(cmd, **kwargs):
        calls.append({"cmd": cmd, **kwargs})
        if box["raises"] is not None:
            raise box["raises"]
        return box["proc"]

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    return type("Spy", (), {"calls": calls, "box": box})()


def collect(adapter, project_dir):
    seen = []
    result = adapter.run("review", project_dir, 600, on_event=seen.append)
    return result, seen


# ---- read-only enforcement -------------------------------------------


def test_the_sandbox_is_demanded_explicitly(adapter, popen_spy, project_dir):
    """`--sandbox` defaults to config.toml, so the default is not a guarantee."""
    adapter.run("review this", project_dir, 600)
    cmd = popen_spy.calls[0]["cmd"]
    assert "--sandbox" in cmd
    assert cmd[cmd.index("--sandbox") + 1] == "read-only"
    assert SANDBOX == "read-only"


def test_user_config_cannot_widen_the_sandbox(adapter, popen_spy, project_dir):
    adapter.run("review this", project_dir, 600)
    assert "--ignore-user-config" in popen_spy.calls[0]["cmd"]


def test_the_run_can_never_be_asked_to_escalate(adapter, popen_spy, project_dir):
    adapter.run("review this", project_dir, 600)
    cmd = popen_spy.calls[0]["cmd"]
    assert cmd[cmd.index("--ask-for-approval") + 1] == "never"
    assert APPROVAL == "never"


def test_no_writable_sandbox_is_ever_requested(adapter, popen_spy, project_dir):
    adapter.run("review this", project_dir, 600)
    cmd = " ".join(popen_spy.calls[0]["cmd"])
    for forbidden in (
        "workspace-write",
        "danger-full-access",
        "--dangerously-bypass-approvals-and-sandbox",
        "--full-auto",
        "--yolo",
    ):
        assert forbidden not in cmd


def test_prompt_carries_the_read_only_preamble(adapter, popen_spy, project_dir):
    adapter.run("review this", project_dir, 600)
    prompt = popen_spy.calls[0]["cmd"][-1]
    assert "read-only sandbox" in prompt
    assert prompt.endswith("review this")


# ---- command shape ----------------------------------------------------


def test_runs_the_exec_subcommand_with_ndjson(adapter, popen_spy, project_dir):
    adapter.run("review this", project_dir, 600)
    cmd = popen_spy.calls[0]["cmd"]
    assert cmd[0] == "codex" and cmd[1] == "exec"
    assert "--json" in cmd


def test_a_project_need_not_be_a_git_repo(adapter, popen_spy, project_dir):
    adapter.run("review this", project_dir, 600)
    assert "--skip-git-repo-check" in popen_spy.calls[0]["cmd"]


def test_runs_in_the_project_directory(adapter, popen_spy, project_dir):
    adapter.run("review this", project_dir, 600)
    assert popen_spy.calls[0]["cwd"] == str(project_dir)


def test_stdin_is_closed_so_a_prompt_cannot_hang_cron(adapter, popen_spy, project_dir):
    adapter.run("review this", project_dir, 600)
    assert popen_spy.calls[0]["stdin"] is subprocess.DEVNULL


def test_child_gets_its_own_process_group(adapter, popen_spy, project_dir):
    adapter.run("review this", project_dir, 600)
    assert popen_spy.calls[0]["start_new_session"] is True


# ---- findings ---------------------------------------------------------


def test_findings_come_from_the_final_agent_message(adapter, popen_spy, project_dir):
    result, _ = collect(adapter, project_dir)
    assert result.status == "ok"
    assert result.findings_md == ANSWER


def test_only_the_last_message_is_the_answer(adapter, popen_spy, project_dir):
    """Codex's own --output-last-message treats the last one as the result.

    Joining them would file the model's narration into the digest as findings.
    """
    popen_spy.box["proc"] = FakePopen(
        [
            line({"type": "thread.started", "thread_id": "t1"}),
            item("item.completed", "agent_message", text="Let me start by reading."),
            item("item.completed", "agent_message", text=ANSWER),
        ]
    )
    result, _ = collect(adapter, project_dir)
    assert result.findings_md == ANSWER
    assert "Let me start" not in result.findings_md


def test_a_run_with_no_message_is_a_failure(adapter, popen_spy, project_dir):
    popen_spy.box["proc"] = FakePopen([line({"type": "thread.started", "thread_id": "t"})])
    result, _ = collect(adapter, project_dir)
    assert result.status == "failed"
    assert result.detail == "no output"


def test_malformed_lines_are_skipped_not_fatal(adapter, popen_spy, project_dir):
    popen_spy.box["proc"] = FakePopen(["not json\n", "\n", "[1,2]\n", *STREAM])
    result, _ = collect(adapter, project_dir)
    assert result.status == "ok"
    assert result.findings_md == ANSWER


# ---- the sandbox tripwire ---------------------------------------------


def test_a_reported_file_change_fails_the_run(adapter, popen_spy, project_dir):
    """A read-only sandbox cannot let this happen. If it does, nothing holds."""
    popen_spy.box["proc"] = FakePopen(
        [
            line({"type": "thread.started", "thread_id": "t1"}),
            item(
                "item.completed",
                "file_change",
                status="completed",
                changes=[{"path": "src/app.py", "kind": "update"}],
            ),
            item("item.completed", "agent_message", text=ANSWER),
        ]
    )
    result, _ = collect(adapter, project_dir)
    assert result.status == "failed"
    assert "sandbox breach" in result.detail
    assert "src/app.py" in result.detail
    # The evidence must survive into the digest.
    assert result.findings_md == ANSWER


def test_the_tripwire_beats_a_clean_exit(adapter, popen_spy, project_dir):
    """Exiting 0 is not the headline when files changed."""
    popen_spy.box["proc"] = FakePopen(
        [
            item(
                "item.completed",
                "file_change",
                status="completed",
                changes=[{"path": "a.py", "kind": "add"}],
            ),
            item("item.completed", "agent_message", text=ANSWER),
        ],
        returncode=0,
    )
    result, _ = collect(adapter, project_dir)
    assert result.status == "failed"


def test_a_blocked_write_is_the_sandbox_working_not_a_breach(adapter, popen_spy, project_dir):
    """A *failed* file_change is the sandbox refusing. Not an alarm."""
    popen_spy.box["proc"] = FakePopen(
        [
            item(
                "item.completed",
                "file_change",
                status="failed",
                changes=[{"path": "src/app.py", "kind": "update"}],
            ),
            item("item.completed", "agent_message", text=ANSWER),
        ]
    )
    result, _ = collect(adapter, project_dir)
    assert result.status == "ok"
    assert "breach" not in result.detail


# ---- events -----------------------------------------------------------


def test_events_describe_the_run_as_it_happens(adapter, popen_spy, project_dir):
    _, seen = collect(adapter, project_dir)
    kinds = [e.kind for e in seen]
    assert kinds[0] == "start"
    assert "thinking" in kinds
    assert "tool" in kinds
    assert "tool_result" in kinds
    assert "text" in kinds


def test_a_command_is_named_by_its_program(adapter, popen_spy, project_dir):
    _, seen = collect(adapter, project_dir)
    tool = next(e for e in seen if e.kind == "tool")
    assert tool.tool == "rg"
    assert tool.detail == "-n jwt api/"


def test_an_unattended_run_emits_nothing_and_still_works(adapter, popen_spy, project_dir):
    result = adapter.run("review", project_dir, 600)
    assert result.status == "ok"
    assert result.findings_md == ANSWER


def test_a_broken_renderer_cannot_fail_a_billed_run(adapter, popen_spy, project_dir):
    def explode(event):
        raise RuntimeError("the renderer is the caller's problem")

    result = adapter.run("review", project_dir, 600, on_event=explode)
    assert result.status == "ok"


# ---- failure modes ----------------------------------------------------


def test_a_turn_failure_names_the_reason(adapter, popen_spy, project_dir):
    popen_spy.box["proc"] = FakePopen(
        [
            line({"type": "thread.started", "thread_id": "t"}),
            line({"type": "turn.failed", "error": {"message": "model overloaded"}}),
        ],
        returncode=1,
    )
    result, _ = collect(adapter, project_dir)
    assert result.status == "failed"
    assert result.detail == "model overloaded"


def test_a_stream_error_is_preferred_over_raw_stderr(adapter, popen_spy, project_dir):
    popen_spy.box["proc"] = FakePopen(
        [line({"type": "error", "message": "usage limit reached"})],
        returncode=1,
        stderr_lines=["some noisy traceback\n"],
    )
    result, _ = collect(adapter, project_dir)
    assert result.detail == "usage limit reached"


def test_nonzero_exit_falls_back_to_stderr(adapter, popen_spy, project_dir):
    popen_spy.box["proc"] = FakePopen(STREAM, returncode=2, stderr_lines=["boom\n"])
    result, _ = collect(adapter, project_dir)
    assert result.status == "failed"
    assert result.detail == "boom"


def test_a_failed_run_keeps_what_was_said(adapter, popen_spy, project_dir):
    """The attempt was billed either way, so its output still reaches the digest."""
    popen_spy.box["proc"] = FakePopen(STREAM, returncode=1, stderr_lines=["died late\n"])
    result, _ = collect(adapter, project_dir)
    assert result.status == "failed"
    assert result.findings_md == ANSWER
    assert result.detail == "died late"


def test_missing_binary_is_a_failure_not_a_crash(adapter, popen_spy, project_dir):
    popen_spy.box["raises"] = FileNotFoundError()
    result, _ = collect(adapter, project_dir)
    assert result.status == "failed"
    assert "not on PATH" in result.detail


def test_os_error_is_a_failure_not_a_crash(adapter, popen_spy, project_dir):
    popen_spy.box["raises"] = OSError("no fork for you")
    result, _ = collect(adapter, project_dir)
    assert result.status == "failed"
    assert "could not start" in result.detail


def test_missing_project_dir_fails_before_spawning(adapter, popen_spy, tmp_path):
    result = adapter.run("review", tmp_path / "gone", 600)
    assert result.status == "failed"
    assert "does not exist" in result.detail
    assert popen_spy.calls == []


def test_records_duration_and_start_time(adapter, popen_spy, project_dir):
    before = datetime.now()
    result, _ = collect(adapter, project_dir)
    assert before <= result.started_at <= datetime.now()
    assert result.duration_s >= 0


# ---- availability -----------------------------------------------------


def test_unavailable_when_not_on_path(adapter, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    availability = adapter.availability()
    assert availability.ok is False
    assert "not on PATH" in availability.reason


def test_available_when_version_succeeds(adapter, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/codex")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: type("P", (), {"returncode": 0, "stdout": "codex-cli 0.9\n", "stderr": ""})(),
    )
    availability = adapter.availability()
    assert availability.ok is True
    assert "codex-cli 0.9" in availability.reason


def test_unavailable_when_version_fails(adapter, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/codex")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: type("P", (), {"returncode": 1, "stdout": "", "stderr": "not logged in\n"})(),
    )
    availability = adapter.availability()
    assert availability.ok is False
    assert "not logged in" in availability.reason


# ---- idle detection ---------------------------------------------------


def test_last_human_use_is_none_when_codex_never_ran(adapter, tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "nope"))
    assert adapter.last_human_use() is None


def test_last_human_use_finds_the_newest_session(adapter, tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    day = tmp_path / "sessions" / "2026" / "07" / "15"
    day.mkdir(parents=True)
    old = day / "rollout-2026-07-15T01-00-00-aaaa.jsonl"
    new = day / "rollout-2026-07-15T02-00-00-bbbb.jsonl"
    old.write_text("{}")
    new.write_text("{}")
    recent = datetime.now() - timedelta(minutes=5)
    import os

    os.utime(old, (recent.timestamp() - 3600, recent.timestamp() - 3600))
    os.utime(new, (recent.timestamp(), recent.timestamp()))

    seen = adapter.last_human_use()
    assert seen is not None
    assert abs((seen - recent).total_seconds()) < 2


def test_our_own_sessions_are_not_read_as_a_human(adapter, tmp_path, monkeypatch, isolated_home):
    """Counting our own runs would make nightaudit gate itself out after each."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    day = tmp_path / "sessions"
    day.mkdir(parents=True)
    # Codex names the file for the thread id, it is not the whole stem.
    (day / "rollout-2026-07-15T03-00-00-thread-abc-123.jsonl").write_text("{}")
    sessions.record("thread-abc-123")

    assert adapter.last_human_use() is None


def test_a_human_session_alongside_ours_still_counts(adapter, tmp_path, monkeypatch, isolated_home):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    day = tmp_path / "sessions"
    day.mkdir(parents=True)
    (day / "rollout-1-thread-ours.jsonl").write_text("{}")
    (day / "rollout-2-thread-theirs.jsonl").write_text("{}")
    sessions.record("thread-ours")

    assert adapter.last_human_use() is not None


def test_a_directory_alone_is_not_evidence_of_a_human(adapter, tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    (tmp_path / "sessions" / "2026").mkdir(parents=True)
    assert adapter.last_human_use() is None


def test_the_streaming_path_claims_its_session(adapter, popen_spy, project_dir, isolated_home):
    collect(adapter, project_dir)
    assert "thread-abc-123" in sessions.ours()
