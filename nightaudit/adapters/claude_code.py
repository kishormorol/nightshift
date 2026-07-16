"""The Claude Code adapter.

Read-only is not a convention here, it is enforced by the CLI's own permission
system: we hand Claude Code an allowlist of read-class tools and an explicit
denylist of every tool that can mutate a repo. If those flags ever stop
working, the correct behaviour is to fail the run, not to fall back to an
unrestricted invocation.

Flag names were checked against `claude --help` (CLI v2.x) rather than assumed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from nightaudit import sessions
from nightaudit.adapters._process import (
    emit as _emit,
)
from nightaudit.adapters._process import (
    format_input as _format_input,
)
from nightaudit.adapters._process import (
    stream_ndjson,
)
from nightaudit.adapters._process import (
    summarize as _summarize,
)
from nightaudit.adapters.base import Availability, Event, OnEvent, RunResult

#: Tools Claude Code may use: inspect the repo, nothing else.
ALLOWED_TOOLS = ("Read", "Grep", "Glob", "NotebookRead")

#: Tools that can change a repo or reach the network. Belt and braces — the
#: allowlist above should already exclude these, but a denylist survives a
#: future release adding a new write-capable tool to the default set.
DISALLOWED_TOOLS = (
    "Bash",
    "Edit",
    "MultiEdit",
    "Write",
    "NotebookEdit",
    "WebFetch",
    "WebSearch",
    "Task",
)

#: Where Claude Code records the user's own sessions; the newest mtime under
#: here is our proxy for "a human is using this right now".
CLAUDE_PROJECTS_DIR = Path("~/.claude/projects")

_READ_ONLY_PREAMBLE = (
    "You are running unattended as part of an automated read-only review.\n"
    "You have no write, edit, or shell tools — do not attempt to use them, and "
    "do not ask questions. Inspect the repository and report findings only.\n\n"
)


def _content(payload: dict) -> list[dict]:
    message = payload.get("message")
    if not isinstance(message, dict):
        return []
    blocks = message.get("content")
    if not isinstance(blocks, list):
        return []
    return [b for b in blocks if isinstance(b, dict)]


class ClaudeCodeAdapter:
    name = "claude_code"

    def __init__(self, binary: str = "claude"):
        self.binary = binary

    # ---- availability -------------------------------------------------

    def _which(self) -> str | None:
        return shutil.which(self.binary)

    def availability(self) -> Availability:
        path = self._which()
        if path is None:
            return Availability(
                ok=False,
                reason=f"`{self.binary}` is not on PATH — install Claude Code, see "
                f"https://claude.com/claude-code",
            )
        try:
            proc = subprocess.run(
                [self.binary, "--version"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return Availability(ok=False, reason=f"`{self.binary} --version` failed: {exc}")
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            first = detail[0] if detail else f"exit {proc.returncode}"
            return Availability(ok=False, reason=f"`{self.binary} --version` failed: {first}")
        return Availability(ok=True, reason=(proc.stdout or "").strip())

    def available(self) -> bool:
        return self.availability().ok

    # ---- idle detection -----------------------------------------------

    def _projects_dir(self) -> Path:
        return Path(os.path.expanduser(str(CLAUDE_PROJECTS_DIR)))

    def last_human_use(self) -> datetime | None:
        """Newest mtime under ``~/.claude/projects`` that was not ours.

        Returns ``None`` when the directory is absent — a fresh install has
        simply never been used, which reads as idle rather than as busy.

        Our own runs write transcripts here too, named for the session id the
        CLI reported, so those are skipped: counting them would make every run
        gate the next one and nightaudit would never run twice in a night.

        Only files are considered. A directory's mtime bumps whenever anything
        inside it is written — including our own transcript — so it cannot be
        attributed to a human once nightaudit shares the directory, and
        counting it would defeat the check above.
        """
        root = self._projects_dir()
        if not root.is_dir():
            return None
        mine = sessions.ours()
        newest: float | None = None
        try:
            for path in root.rglob("*"):
                if path.stem in mine:
                    continue
                try:
                    if not path.is_file():
                        continue
                    mtime = path.stat().st_mtime
                except OSError:
                    continue
                if newest is None or mtime > newest:
                    newest = mtime
        except OSError:
            return None
        if newest is None:
            return None
        return datetime.fromtimestamp(newest)

    # ---- running ------------------------------------------------------

    def command(self, prompt: str, stream: bool = False) -> list[str]:
        # stream-json is newline-delimited events rather than one envelope;
        # the CLI only emits it under --print when --verbose is also set.
        fmt = ["--output-format", "json"]
        if stream:
            fmt = ["--output-format", "stream-json", "--verbose"]
        return [
            self.binary,
            "--print",
            _READ_ONLY_PREAMBLE + prompt,
            *fmt,
            "--allowed-tools",
            *ALLOWED_TOOLS,
            "--disallowed-tools",
            *DISALLOWED_TOOLS,
        ]

    def run(
        self,
        prompt: str,
        project_dir: Path,
        timeout_s: int,
        on_event: OnEvent | None = None,
    ) -> RunResult:
        started = datetime.now()

        def finish(status: str, findings_md: str, detail: str = "") -> RunResult:
            return RunResult(
                provider=self.name,
                project=project_dir.name,
                task="",
                status=status,  # type: ignore[arg-type]
                findings_md=findings_md,
                started_at=started,
                duration_s=(datetime.now() - started).total_seconds(),
                detail=detail,
            )

        if not project_dir.is_dir():
            return finish("failed", "", f"project path does not exist: {project_dir}")

        if on_event is not None:
            return self._run_streaming(prompt, project_dir, timeout_s, on_event, finish)

        try:
            proc = subprocess.run(
                self.command(prompt),
                cwd=str(project_dir),
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except subprocess.TimeoutExpired:
            # This comment used to claim subprocess.run's kill takes the whole
            # process group with it. It does not: on timeout it calls
            # Popen.kill(), which is os.kill(pid) on the direct child alone —
            # start_new_session buys us nothing here. Any grandchild survives
            # as an orphan still holding provider quota.
            #
            # Nothing gates on this path today: the scheduler always passes an
            # event sink, so every real run streams. It stays for callers that
            # want no events, and it is honest about what it does not do.
            return finish("timeout", "", f"no output after {timeout_s}s")
        except FileNotFoundError:
            return finish("failed", "", f"`{self.binary}` is not on PATH")
        except OSError as exc:
            return finish("failed", "", f"could not start `{self.binary}`: {exc}")

        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()

        # Claim the session before anything can return: a transcript we do not
        # claim is one we will later mistake for a human's.
        self._claim_session(stdout)

        if proc.returncode != 0:
            detail = stderr.splitlines()[0] if stderr else f"exit {proc.returncode}"
            # A non-zero exit that still produced output is worth keeping.
            return finish("failed", stdout, detail)

        if not stdout:
            return finish("failed", "", "no output")

        return finish("ok", self._extract(stdout))

    # ---- streaming ----------------------------------------------------

    def _run_streaming(
        self,
        prompt: str,
        project_dir: Path,
        timeout_s: int,
        on_event: OnEvent,
        finish,
    ) -> RunResult:
        """Same run, reported as it happens.

        The buffered path above gets its timeout and its process-group kill
        from ``subprocess.run``; reading the stream ourselves means we have to
        reproduce both, which is what ``stream_ndjson`` is for — a timeout here
        still takes the whole tree with it rather than leaving orphans holding
        the quota.
        """
        state = {"result_text": "", "claimed": False}
        prose: list[str] = []

        def on_line(payload: dict) -> None:
            if not state["claimed"] and payload.get("session_id"):
                # Claim on sight rather than at the end: a run killed at the
                # deadline still wrote a transcript, and an unclaimed transcript
                # is one we later read as a human's.
                sessions.record(str(payload["session_id"]))
                state["claimed"] = True
            if payload.get("type") == "result" and not payload.get("is_error"):
                value = payload.get("result")
                if isinstance(value, str):
                    state["result_text"] = value.strip()
            for event in self._events_for(payload):
                if event.kind == "text":
                    prose.append(event.text)
                _emit(on_event, event)

        try:
            outcome = stream_ndjson(
                self.command(prompt, stream=True), project_dir, timeout_s, on_line
            )
        except FileNotFoundError:
            return finish("failed", "", f"`{self.binary}` is not on PATH")
        except OSError as exc:
            return finish("failed", "", f"could not start `{self.binary}`: {exc}")

        # Whatever the CLI managed to say before the deadline is still worth
        # keeping — the run was billed either way.
        findings = state["result_text"] or "\n\n".join(prose).strip()

        if outcome.timed_out:
            return finish("timeout", findings, f"no output after {timeout_s}s")

        if outcome.returncode != 0:
            return finish("failed", findings, outcome.stderr_head)

        if not findings:
            return finish("failed", "", "no output")

        return finish("ok", findings)

    @classmethod
    def _events_for(cls, payload: dict):
        """Translate one stream-json line into zero or more events."""
        kind = payload.get("type")

        if kind == "system" and payload.get("subtype") == "init":
            yield Event("start", text=str(payload.get("cwd") or ""))

        elif kind == "assistant":
            for block in _content(payload):
                btype = block.get("type")
                if btype == "text":
                    text = (block.get("text") or "").strip()
                    if text:
                        yield Event("text", text=text)
                elif btype == "tool_use":
                    yield Event(
                        "tool",
                        tool=str(block.get("name") or "?"),
                        detail=_format_input(block.get("input")),
                    )
                elif btype == "thinking":
                    yield Event("thinking")

        elif kind == "user":
            for block in _content(payload):
                if block.get("type") == "tool_result":
                    yield Event("tool_result", text=_summarize(block.get("content")))

        elif kind == "result":
            if payload.get("is_error"):
                detail = payload.get("result")
                yield Event("error", text=str(detail or "the run reported an error"))
            else:
                yield Event("result")

    @staticmethod
    def _claim_session(stdout: str) -> None:
        """Record the session id out of ``--output-format json``."""
        try:
            payload = json.loads(stdout)
        except (json.JSONDecodeError, TypeError):
            return
        if isinstance(payload, dict):
            sessions.record(str(payload.get("session_id") or ""))

    @staticmethod
    def _extract(stdout: str) -> str:
        """Pull the result text out of ``--output-format json``.

        Never discards a completed run: if the envelope isn't the shape we
        expect, the raw stdout *is* the findings. A run that cost quota must
        always leave something in the digest.
        """
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return stdout

        if isinstance(payload, dict):
            for key in ("result", "text", "content", "output"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            if payload.get("is_error") and isinstance(payload.get("error"), str):
                return payload["error"].strip()
        return stdout
