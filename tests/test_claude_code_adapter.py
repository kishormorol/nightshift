"""Claude Code adapter, driven entirely through a mocked ``subprocess``.

Nothing here launches a real CLI or spends a token.
"""

from __future__ import annotations

import io
import json
import subprocess
from datetime import datetime, timedelta

import pytest

from nightaudit import sessions
from nightaudit.adapters.claude_code import (
    ALLOWED_TOOLS,
    DISALLOWED_TOOLS,
    ClaudeCodeAdapter,
)


@pytest.fixture
def adapter():
    return ClaudeCodeAdapter()


class FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def envelope(text: str) -> str:
    return json.dumps({"type": "result", "is_error": False, "result": text})


@pytest.fixture
def spy(monkeypatch):
    """Capture the subprocess call and return a scripted result."""
    calls: list[dict] = []
    box = {"proc": FakeProc(stdout=envelope("- LOW a.py:1 — x")), "raises": None}

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": cmd, **kwargs})
        if box["raises"] is not None:
            raise box["raises"]
        return box["proc"]

    monkeypatch.setattr(subprocess, "run", fake_run)
    return type("Spy", (), {"calls": calls, "box": box})()


# ---- read-only enforcement -------------------------------------------


def test_read_only_is_enforced_by_cli_flags(adapter, spy, project_dir):
    adapter.run("review this", project_dir, 600)
    cmd = spy.calls[0]["cmd"]

    assert "--allowed-tools" in cmd
    assert "--disallowed-tools" in cmd

    allowed = cmd[cmd.index("--allowed-tools") + 1 : cmd.index("--disallowed-tools")]
    assert allowed == list(ALLOWED_TOOLS)


def test_no_write_capable_tool_is_ever_allowed(adapter, spy, project_dir):
    adapter.run("review this", project_dir, 600)
    cmd = spy.calls[0]["cmd"]
    allowed = cmd[cmd.index("--allowed-tools") + 1 : cmd.index("--disallowed-tools")]

    # This is the product promise: 0 files touched.
    for tool in ("Bash", "Edit", "MultiEdit", "Write", "NotebookEdit"):
        assert tool not in allowed


def test_mutating_tools_are_explicitly_denied(adapter, spy, project_dir):
    adapter.run("review this", project_dir, 600)
    cmd = spy.calls[0]["cmd"]
    denied = cmd[cmd.index("--disallowed-tools") + 1 :]
    for tool in ("Bash", "Edit", "Write", "NotebookEdit"):
        assert tool in denied
    assert set(DISALLOWED_TOOLS).isdisjoint(set(ALLOWED_TOOLS))


def test_never_skips_permissions(adapter, spy, project_dir):
    adapter.run("review this", project_dir, 600)
    joined = " ".join(spy.calls[0]["cmd"])
    assert "--dangerously-skip-permissions" not in joined
    assert "--allow-dangerously-skip-permissions" not in joined
    assert "bypassPermissions" not in joined


def test_runs_headless_with_json_output(adapter, spy, project_dir):
    adapter.run("review this", project_dir, 600)
    cmd = spy.calls[0]["cmd"]
    assert cmd[0] == "claude"
    assert "--print" in cmd
    assert cmd[cmd.index("--output-format") + 1] == "json"


def test_prompt_carries_the_read_only_preamble(adapter, spy, project_dir):
    adapter.run("review this", project_dir, 600)
    prompt = spy.calls[0]["cmd"][2]
    assert "read-only" in prompt.lower()
    assert "review this" in prompt


def test_runs_in_the_project_directory(adapter, spy, project_dir):
    adapter.run("review this", project_dir, 600)
    assert spy.calls[0]["cwd"] == str(project_dir)


def test_stdin_is_closed_so_a_prompt_cannot_hang_cron(adapter, spy, project_dir):
    adapter.run("review this", project_dir, 600)
    assert spy.calls[0]["stdin"] is subprocess.DEVNULL


def test_timeout_is_passed_through(adapter, spy, project_dir):
    adapter.run("review this", project_dir, 42)
    assert spy.calls[0]["timeout"] == 42


def test_child_gets_its_own_process_group(adapter, spy, project_dir):
    # So a timeout kills the whole tree instead of orphaning children.
    adapter.run("review this", project_dir, 600)
    assert spy.calls[0]["start_new_session"] is True


# ---- output handling --------------------------------------------------


def test_extracts_result_text_from_the_json_envelope(adapter, spy, project_dir):
    spy.box["proc"] = FakeProc(stdout=envelope("- HIGH auth.py:1 — no expiry"))
    result = adapter.run("p", project_dir, 600)
    assert result.status == "ok"
    assert result.findings_md == "- HIGH auth.py:1 — no expiry"


def test_malformed_json_keeps_raw_stdout_as_findings(adapter, spy, project_dir):
    # A completed run cost quota — never discard it.
    spy.box["proc"] = FakeProc(stdout="- HIGH a.py:1 — not json but useful")
    result = adapter.run("p", project_dir, 600)
    assert result.status == "ok"
    assert result.findings_md == "- HIGH a.py:1 — not json but useful"


def test_unexpected_envelope_shape_keeps_raw_stdout(adapter, spy, project_dir):
    spy.box["proc"] = FakeProc(stdout=json.dumps({"surprise": "new schema"}))
    result = adapter.run("p", project_dir, 600)
    assert result.status == "ok"
    assert "new schema" in result.findings_md


def test_json_array_output_keeps_raw_stdout(adapter, spy, project_dir):
    spy.box["proc"] = FakeProc(stdout=json.dumps([{"result": "x"}]))
    result = adapter.run("p", project_dir, 600)
    assert result.status == "ok"
    assert result.findings_md.startswith("[")


def test_empty_output_is_a_failure(adapter, spy, project_dir):
    spy.box["proc"] = FakeProc(stdout="   ")
    result = adapter.run("p", project_dir, 600)
    assert result.status == "failed"
    assert result.detail == "no output"


def test_records_duration_and_start_time(adapter, spy, project_dir):
    before = datetime.now()
    result = adapter.run("p", project_dir, 600)
    assert before <= result.started_at <= datetime.now()
    assert result.duration_s >= 0


# ---- failure modes ----------------------------------------------------


def test_timeout_is_reported_as_timeout(adapter, spy, project_dir):
    spy.box["raises"] = subprocess.TimeoutExpired(cmd="claude", timeout=600)
    result = adapter.run("p", project_dir, 600)
    assert result.status == "timeout"
    assert "600s" in result.detail


def test_nonzero_exit_is_a_failure_naming_the_reason(adapter, spy, project_dir):
    spy.box["proc"] = FakeProc(returncode=1, stderr="Invalid API key\nmore detail")
    result = adapter.run("p", project_dir, 600)
    assert result.status == "failed"
    assert result.detail == "Invalid API key"


def test_nonzero_exit_still_keeps_any_output(adapter, spy, project_dir):
    spy.box["proc"] = FakeProc(returncode=2, stdout="partial findings", stderr="boom")
    result = adapter.run("p", project_dir, 600)
    assert result.status == "failed"
    assert result.findings_md == "partial findings"


def test_missing_binary_is_a_failure_not_a_crash(adapter, spy, project_dir):
    spy.box["raises"] = FileNotFoundError()
    result = adapter.run("p", project_dir, 600)
    assert result.status == "failed"
    assert "not on PATH" in result.detail


def test_os_error_is_a_failure_not_a_crash(adapter, spy, project_dir):
    spy.box["raises"] = OSError("exec format error")
    result = adapter.run("p", project_dir, 600)
    assert result.status == "failed"
    assert "could not start" in result.detail


def test_missing_project_dir_fails_before_spawning(adapter, spy, tmp_path):
    result = adapter.run("p", tmp_path / "gone", 600)
    assert result.status == "failed"
    assert "does not exist" in result.detail
    assert spy.calls == []  # never spent quota


# ---- availability -----------------------------------------------------


def test_unavailable_when_not_on_path(adapter, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    availability = adapter.availability()
    assert availability.ok is False
    assert "not on PATH" in availability.reason
    assert adapter.available() is False


def test_available_when_version_succeeds(adapter, spy, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/claude")
    spy.box["proc"] = FakeProc(stdout="2.0.1 (Claude Code)")
    assert adapter.available() is True
    assert adapter.availability().reason == "2.0.1 (Claude Code)"


def test_unavailable_when_version_fails(adapter, spy, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/claude")
    spy.box["proc"] = FakeProc(returncode=1, stderr="not logged in")
    availability = adapter.availability()
    assert availability.ok is False
    assert "not logged in" in availability.reason


def test_unavailable_when_version_hangs(adapter, spy, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/claude")
    spy.box["raises"] = subprocess.TimeoutExpired(cmd="claude", timeout=20)
    assert adapter.availability().ok is False


# ---- idle detection ---------------------------------------------------


def test_last_human_use_is_none_when_claude_never_ran(adapter, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "nightaudit.adapters.claude_code.CLAUDE_PROJECTS_DIR", tmp_path / "absent"
    )
    # No directory means a fresh install, which reads as idle — not as busy.
    assert adapter.last_human_use() is None


def test_last_human_use_is_none_for_an_empty_dir(adapter, tmp_path, monkeypatch):
    empty = tmp_path / "projects"
    empty.mkdir()
    monkeypatch.setattr("nightaudit.adapters.claude_code.CLAUDE_PROJECTS_DIR", empty)
    assert adapter.last_human_use() is None


def _age(path, when: datetime) -> None:
    import os

    os.utime(path, (when.timestamp(), when.timestamp()))


def test_last_human_use_finds_the_newest_mtime(adapter, tmp_path, monkeypatch):
    root = tmp_path / "projects"
    (root / "proj-a").mkdir(parents=True)
    old = root / "proj-a" / "old.jsonl"
    new = root / "proj-a" / "new.jsonl"
    old.write_text("{}", encoding="utf-8")
    new.write_text("{}", encoding="utf-8")

    now = datetime.now()
    recent = now - timedelta(minutes=3)
    # Age the whole tree: a session five hours old leaves no fresh mtimes
    # anywhere, directories included.
    _age(old, now - timedelta(hours=5))
    _age(root / "proj-a", now - timedelta(hours=5))
    _age(new, recent)

    monkeypatch.setattr("nightaudit.adapters.claude_code.CLAUDE_PROJECTS_DIR", root)
    found = adapter.last_human_use()
    assert found is not None
    assert abs(found.timestamp() - recent.timestamp()) < 2


def test_a_directory_alone_is_not_evidence_of_a_human(adapter, tmp_path, monkeypatch):
    # This used to assert the opposite: a directory's mtime counted, erring
    # toward "busy". That inverted once we learned nightaudit's own runs write
    # transcripts into these same directories — our write bumps the parent, so
    # a directory mtime cannot be attributed to a human, and counting it would
    # make every run gate the next one no matter which sessions we skip.
    root = tmp_path / "projects"
    (root / "proj-a").mkdir(parents=True)
    _age(root / "proj-a", datetime.now() - timedelta(minutes=2))

    monkeypatch.setattr("nightaudit.adapters.claude_code.CLAUDE_PROJECTS_DIR", root)
    assert adapter.last_human_use() is None


# ---- our sessions vs theirs ------------------------------------------


def _session(root, name, when):
    path = root / "proj-a" / f"{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    _age(path, when)
    return path


def test_our_own_session_is_not_mistaken_for_a_human(adapter, tmp_path, monkeypatch):
    # The bug this guards: `claude --print` writes its transcript into the same
    # directory a human's session does, so every run left a fresh mtime that the
    # next cron tick read as "someone is typing" — nightaudit gated itself out
    # for idle_minutes after every single run.
    root = tmp_path / "projects"
    _session(root, "ours-1234", datetime.now() - timedelta(minutes=1))
    sessions.record("ours-1234")

    monkeypatch.setattr("nightaudit.adapters.claude_code.CLAUDE_PROJECTS_DIR", root)
    assert adapter.last_human_use() is None


def test_a_human_session_is_still_seen(adapter, tmp_path, monkeypatch):
    root = tmp_path / "projects"
    recent = datetime.now() - timedelta(minutes=4)
    _session(root, "a-human-session", recent)

    monkeypatch.setattr("nightaudit.adapters.claude_code.CLAUDE_PROJECTS_DIR", root)
    found = adapter.last_human_use()
    assert found is not None
    assert abs(found.timestamp() - recent.timestamp()) < 2


def test_a_human_in_the_same_project_still_blocks_us(adapter, tmp_path, monkeypatch):
    # Filtering by project path would have hidden exactly this person — someone
    # working in a repo nightaudit also reviews, which is when it must back off.
    root = tmp_path / "projects"
    theirs = datetime.now() - timedelta(minutes=2)
    _session(root, "ours-1234", datetime.now() - timedelta(minutes=1))  # newer!
    _session(root, "theirs-9999", theirs)
    sessions.record("ours-1234")

    monkeypatch.setattr("nightaudit.adapters.claude_code.CLAUDE_PROJECTS_DIR", root)
    found = adapter.last_human_use()
    assert found is not None
    assert abs(found.timestamp() - theirs.timestamp()) < 2


def test_the_streaming_path_claims_its_session(adapter, popen_spy, project_dir):
    popen_spy.box["proc"] = FakePopen(
        [line({"type": "system", "subtype": "init", "session_id": "sess-abc"}), *STREAM]
    )
    adapter.run("review", project_dir, 600, on_event=lambda e: None)

    assert "sess-abc" in sessions.ours()


def test_the_buffered_path_claims_its_session(adapter, spy, project_dir):
    # cron's path before `watch` existed, and any caller that wants no events.
    spy.box["proc"] = FakeProc(
        stdout=json.dumps(
            {"type": "result", "is_error": False, "result": "- LOW a.py:1 — x",
             "session_id": "sess-xyz"}
        )
    )
    adapter.run("review", project_dir, 600)

    assert "sess-xyz" in sessions.ours()


def test_a_session_claimed_twice_is_stored_once(adapter):
    sessions.record("sess-dup")
    sessions.record("sess-dup")
    assert [i for i in sessions.ours() if i == "sess-dup"] == ["sess-dup"]


def test_claiming_survives_a_missing_session_id(adapter, spy, project_dir):
    spy.box["proc"] = FakeProc(stdout=envelope("- LOW a.py:1 — x"))
    adapter.run("review", project_dir, 600)  # must not raise
    assert sessions.ours() == set()


# ---- streaming --------------------------------------------------------


class FakePopen:
    """Just enough Popen to drive the streaming reader.

    The streams are ``StringIO`` rather than plain iterators so they behave
    like the real pipes: iterable, and closeable on the way out.
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


def assistant(*blocks) -> str:
    return line({"type": "assistant", "message": {"content": list(blocks)}})


#: A realistic stream: init, prose, a tool call, its result, then the answer.
STREAM = [
    line({"type": "system", "subtype": "init", "cwd": "/repo"}),
    assistant({"type": "text", "text": "Looking at the auth code."}),
    assistant({"type": "tool_use", "name": "Grep", "input": {"pattern": "jwt"}}),
    line(
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "content": "api/auth.py:142\napi/x.py:9"}
                ]
            },
        }
    ),
    line({"type": "result", "is_error": False, "result": "- HIGH api/auth.py:142 — no exp"}),
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


def test_a_callback_switches_the_cli_to_stream_json(adapter, popen_spy, project_dir):
    collect(adapter, project_dir)
    cmd = popen_spy.calls[0]["cmd"]

    assert "stream-json" in cmd
    # The CLI only streams under --print when --verbose is set too.
    assert "--verbose" in cmd


def test_streaming_still_enforces_read_only(adapter, popen_spy, project_dir):
    collect(adapter, project_dir)
    cmd = popen_spy.calls[0]["cmd"]

    for tool in ALLOWED_TOOLS:
        assert tool in cmd
    for tool in DISALLOWED_TOOLS:
        assert tool in cmd


def test_no_callback_keeps_the_buffered_path(adapter, spy, project_dir):
    # cron passes no renderer and must keep getting the single-envelope form.
    adapter.run("review", project_dir, 600)
    assert "json" in spy.calls[0]["cmd"]
    assert "stream-json" not in spy.calls[0]["cmd"]


def test_events_describe_the_run_as_it_happens(adapter, popen_spy, project_dir):
    _, seen = collect(adapter, project_dir)
    kinds = [e.kind for e in seen]

    assert kinds == ["start", "text", "tool", "tool_result", "result"]

    tool = seen[2]
    assert tool.tool == "Grep"
    assert "jwt" in tool.detail


def test_streaming_findings_match_the_result_event(adapter, popen_spy, project_dir):
    result, _ = collect(adapter, project_dir)

    assert result.status == "ok"
    assert result.findings_md == "- HIGH api/auth.py:142 — no exp"


def test_streaming_captures_token_usage_from_the_result_event(
    adapter, popen_spy, project_dir
):
    """The result frame's usage — including cache reads, real tokens — is the
    run's token total."""
    popen_spy.box["proc"] = FakePopen(
        [
            line(
                {
                    "type": "result",
                    "is_error": False,
                    "result": "- LOW a.py:1 — x",
                    "usage": {
                        "input_tokens": 1000,
                        "output_tokens": 200,
                        "cache_read_input_tokens": 5000,
                    },
                }
            )
        ]
    )
    result, _ = collect(adapter, project_dir)

    assert result.status == "ok"
    assert result.tokens == 6200


def test_a_stream_without_usage_reports_zero_tokens(adapter, popen_spy, project_dir):
    """The default stream carries no usage; that is zero, not a crash."""
    result, _ = collect(adapter, project_dir)

    assert result.status == "ok"
    assert result.tokens == 0


def test_the_buffered_path_captures_token_usage(adapter, spy, project_dir):
    spy.box["proc"] = FakeProc(
        stdout=json.dumps(
            {
                "type": "result",
                "is_error": False,
                "result": "- LOW a.py:1 — x",
                "usage": {"input_tokens": 800, "output_tokens": 100},
            }
        )
    )
    result = adapter.run("review", project_dir, 600)

    assert result.status == "ok"
    assert result.tokens == 900


def test_a_malformed_line_is_skipped_not_fatal(adapter, popen_spy, project_dir):
    popen_spy.box["proc"] = FakePopen(["not json\n", "\n", *STREAM])
    result, seen = collect(adapter, project_dir)

    assert result.status == "ok"
    assert [e.kind for e in seen] == ["start", "text", "tool", "tool_result", "result"]


def test_a_broken_renderer_does_not_lose_a_billed_run(adapter, popen_spy, project_dir):
    def explode(event):
        raise RuntimeError("renderer bug")

    result = adapter.run("review", project_dir, 600, on_event=explode)

    assert result.status == "ok"
    assert result.findings_md == "- HIGH api/auth.py:142 — no exp"


def test_prose_is_kept_when_the_result_event_never_arrives(adapter, popen_spy, project_dir):
    # A stream cut short still cost quota, so whatever was said is the findings.
    popen_spy.box["proc"] = FakePopen(STREAM[:2])
    result, _ = collect(adapter, project_dir)

    assert result.status == "ok"
    assert result.findings_md == "Looking at the auth code."


def test_a_nonzero_exit_reports_stderr(adapter, popen_spy, project_dir):
    popen_spy.box["proc"] = FakePopen(STREAM, returncode=2, stderr_lines=["boom\n"])
    result, _ = collect(adapter, project_dir)

    assert result.status == "failed"
    assert result.detail == "boom"
    # The findings survive a bad exit code.
    assert "api/auth.py:142" in result.findings_md


def test_an_error_result_becomes_an_error_event(adapter, popen_spy, project_dir):
    popen_spy.box["proc"] = FakePopen(
        [line({"type": "result", "is_error": True, "result": "rate limited"})]
    )
    _, seen = collect(adapter, project_dir)

    assert [e.kind for e in seen] == ["error"]
    assert seen[0].text == "rate limited"


# ---- the child that will not die ---------------------------------------


class HangingPopen:
    """stdout reaches EOF, but the process keeps running.

    Real and reproducible: a child that calls ``os.close(1)`` and carries on.
    An EOF on our end says every writer let go of the pipe — it does not say
    the process is exiting.
    """

    def __init__(self, lines):
        self.stdout = io.StringIO("".join(lines))
        self.stderr = io.StringIO("")
        self.pid = 999_999
        self.returncode = None
        self.killed = False
        self.waits: list[float | None] = []

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.waits.append(timeout)
        if timeout is None:
            # The bug in one assertion: with the timer already cancelled, an
            # unbounded wait here never returns and cron holds the lock forever.
            raise AssertionError("unbounded wait() — nothing left to end the child")
        if self.killed:
            self.returncode = -9
            return -9
        raise subprocess.TimeoutExpired(cmd="claude", timeout=timeout)

    def kill(self):
        self.killed = True
        self.returncode = -9


def test_a_child_that_closes_stdout_and_hangs_is_still_killed(
    adapter, popen_spy, project_dir
):
    # Shipped in the pid-reuse fix: the finally cancelled the deadline timer
    # and then waited without one, so a run whose stdout ended early — but
    # whose process lived on — wedged forever, holding the scheduler's lock.
    hanging = HangingPopen([line({"type": "system", "subtype": "init"})])
    popen_spy.box["proc"] = hanging

    result = adapter.run("review", project_dir, 600, on_event=lambda e: None)

    assert hanging.killed, "the child was left running"
    assert None not in hanging.waits, "waited with no deadline to save it"
    assert result.status in {"failed", "timeout"}


def test_the_deadline_survives_until_the_process_is_reaped(
    adapter, popen_spy, project_dir
):
    hanging = HangingPopen([line({"type": "system", "subtype": "init"})])
    popen_spy.box["proc"] = hanging

    adapter.run("review", project_dir, 5, on_event=lambda e: None)

    # Every wait is bounded, and the first is bounded by what is left of the
    # run's own deadline rather than by nothing at all.
    assert hanging.waits
    assert all(w is not None for w in hanging.waits)
