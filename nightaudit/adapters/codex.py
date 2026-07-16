"""The Codex adapter.

Read-only is enforced by Codex's own sandbox — Seatbelt on macOS, Landlock plus
seccomp on Linux, restricted tokens on Windows. That is a stronger guarantee
than the tool allowlist the Claude Code adapter relies on: an allowlist works
because the agent honours its own tool gating, whereas here the kernel refuses
the write. A bug in the model cannot touch the disk.

The flags below were read off the published `codex exec` reference rather than
assumed, and two of them are load-bearing in ways worth stating:

- ``--sandbox read-only`` is passed explicitly even though a fresh install
  already defaults to it, because the reference is explicit that ``--sandbox``
  "defaults to configuration settings". A user's ``~/.codex/config.toml``
  setting ``workspace-write`` would otherwise silently become nightaudit's
  default too. "It defaults to read-only" is a fact about a fresh machine, not
  a guarantee, and this product's whole claim rests on the difference.

- ``--ignore-user-config`` is belt-and-braces of the same kind as the Claude
  adapter's denylist — the explicit flags above should already settle it. It
  earns its place on a second count: MCP servers are configured in that same
  ``config.toml``, and an MCP tool is not a shell command, so it is not obvious
  that the filesystem sandbox constrains one at all. Refusing to load the file
  means there are no MCP servers to find out about. Authentication is
  unaffected — the reference states auth still resolves via ``CODEX_HOME``.

The cost of that second flag is real and worth knowing: a user's configured
model choice is ignored too, so runs use Codex's default model.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from nightaudit import sessions
from nightaudit.adapters._process import (
    clip,
    emit,
    stream_ndjson,
    summarize,
)
from nightaudit.adapters.base import Availability, Event, OnEvent, RunResult

#: The only sandbox nightaudit will ever ask for. Not a default — an assertion.
SANDBOX = "read-only"

#: Never pause for a human: there isn't one, and a run that could ask for
#: approval is a run that could be granted an escalation out of the sandbox.
APPROVAL = "never"

#: Where Codex records its sessions. ``CODEX_HOME`` relocates the whole tree.
CODEX_HOME = "~/.codex"

_READ_ONLY_PREAMBLE = (
    "You are running unattended as part of an automated read-only review.\n"
    "You are in a read-only sandbox: you cannot write, edit, or delete files, "
    "and nothing you do can change this repository. Do not attempt it, and do "
    "not ask questions. Inspect the repository and report findings only.\n\n"
)


def _first_token(command: str) -> tuple[str, str]:
    """Split a shell command into (program, rest) for display.

    ``rg -n foo src/`` reads better as ``rg(-n foo src/)`` than as
    ``Shell(rg -n foo src/)``, and lines up with how the Claude adapter names
    the tool it is running.
    """
    command = " ".join(str(command or "").split())
    if not command:
        return "shell", ""
    head, _, rest = command.partition(" ")
    return head, rest


class _Collector:
    """Turns Codex's NDJSON event stream into findings, events, and alarms.

    One of these per run. It is the ``on_line`` sink for ``stream_ndjson``, and
    it is deliberately the only place that knows Codex's event schema.
    """

    def __init__(self, project_dir: Path, on_event: OnEvent | None = None):
        self.project_dir = project_dir
        self.on_event = on_event
        #: Every ``agent_message`` seen, in order.
        self.messages: list[str] = []
        #: Paths Codex reported it *changed*. Must stay empty; see :meth:`_item`.
        self.wrote: list[str] = []
        #: A turn- or stream-level error message, preferred over raw stderr.
        self.error = ""
        self._claimed = False

    @property
    def findings(self) -> str:
        """The final assistant message.

        Codex's own ``--output-last-message`` treats the last one as *the*
        answer, so we do too. Joining every message instead would file the
        model's running narration into the digest alongside the findings.
        """
        return self.messages[-1] if self.messages else ""

    def _emit(self, event: Event) -> None:
        if self.on_event is not None:
            emit(self.on_event, event)

    def __call__(self, payload: dict) -> None:
        kind = payload.get("type")

        if kind == "thread.started":
            thread_id = str(payload.get("thread_id") or "")
            if thread_id and not self._claimed:
                # Claim on sight, not at the end: a run killed at the deadline
                # still left a session file behind, and an unclaimed session is
                # one last_human_use later mistakes for a human's.
                sessions.record(thread_id)
                self._claimed = True
            self._emit(Event("start", text=str(self.project_dir)))

        elif kind == "turn.failed":
            error = payload.get("error")
            message = error.get("message") if isinstance(error, dict) else None
            self.error = str(message or "the turn failed")
            self._emit(Event("error", text=self.error))

        elif kind == "error":
            self.error = str(payload.get("message") or "the run reported an error")
            self._emit(Event("error", text=self.error))

        elif kind in ("item.started", "item.completed"):
            item = payload.get("item")
            if isinstance(item, dict):
                self._item(kind, item)

    def _item(self, kind: str, item: dict) -> None:
        item_type = item.get("type")
        done = kind == "item.completed"

        if item_type == "agent_message" and done:
            text = str(item.get("text") or "").strip()
            if text:
                self.messages.append(text)
                self._emit(Event("text", text=text))

        elif item_type == "reasoning" and done:
            self._emit(Event("thinking"))

        elif item_type == "command_execution":
            if done:
                self._emit(Event("tool_result", text=summarize(item.get("aggregated_output"))))
            else:
                program, rest = _first_token(str(item.get("command") or ""))
                self._emit(Event("tool", tool=program, detail=clip(rest, 60)))

        elif item_type == "file_change" and done:
            # The tripwire. A read-only sandbox cannot let this happen, so if it
            # does, either the sandbox did not apply or it did not hold — and
            # every claim nightaudit makes about this provider is void for this
            # run. `status` matters: a *failed* file_change is the sandbox doing
            # its job and refusing a write, which is not an alarm.
            if str(item.get("status") or "") != "completed":
                return
            changes = item.get("changes")
            paths = [
                str(c.get("path"))
                for c in (changes if isinstance(changes, list) else [])
                if isinstance(c, dict) and c.get("path")
            ]
            self.wrote.extend(paths or ["<unnamed file>"])
            self._emit(Event("error", text=f"file changed: {', '.join(self.wrote)}"))

        elif item_type == "mcp_tool_call" and not done:
            # --ignore-user-config means no MCP servers are configured, so this
            # should never arrive. Render it rather than drop it: a tool we did
            # not expect is worth seeing in the live view.
            server = str(item.get("server") or "?")
            self._emit(Event("tool", tool=f"{server}:{item.get('tool') or '?'}"))

        elif item_type == "web_search" and done:
            self._emit(Event("tool", tool="web_search", detail=clip(item.get("query"), 60)))

        elif item_type == "error" and done:
            self._emit(Event("error", text=str(item.get("message") or "")))


class CodexAdapter:
    name = "codex"

    def __init__(self, binary: str = "codex"):
        self.binary = binary

    # ---- availability -------------------------------------------------

    def _which(self) -> str | None:
        return shutil.which(self.binary)

    def availability(self) -> Availability:
        path = self._which()
        if path is None:
            return Availability(
                ok=False,
                reason=f"`{self.binary}` is not on PATH — install Codex, see "
                f"https://developers.openai.com/codex",
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

    def _sessions_dir(self) -> Path:
        home = os.environ.get("CODEX_HOME") or CODEX_HOME
        return Path(os.path.expanduser(home)) / "sessions"

    def last_human_use(self) -> datetime | None:
        """Newest mtime under ``$CODEX_HOME/sessions`` that was not ours.

        ``None`` when the directory is absent: a Codex that has never run reads
        as idle, not as busy.

        Our own runs write session files here too, so they are skipped — count
        them and every run would gate the next one, and nightaudit would put
        itself to sleep. Codex names these ``rollout-<timestamp>-<thread_id>``
        rather than after the id alone, so this matches on *containment* where
        the Claude adapter can compare the stem outright.

        Only files count. A directory's mtime bumps when anything inside it is
        written, including our own session, so it cannot be attributed to a
        human once nightaudit shares the tree.
        """
        root = self._sessions_dir()
        if not root.is_dir():
            return None
        mine = sessions.ours()
        newest: float | None = None
        try:
            for path in root.rglob("*"):
                try:
                    if not path.is_file():
                        continue
                    if any(sid and sid in path.name for sid in mine):
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

    def command(self, prompt: str) -> list[str]:
        return [
            self.binary,
            "exec",
            "--sandbox",
            SANDBOX,
            "--ask-for-approval",
            APPROVAL,
            # nightaudit registers directories, not repositories; codex exec
            # refuses to run outside a git repo without this. The check exists
            # to protect uncommitted work from edits, which is not a risk we
            # have.
            "--skip-git-repo-check",
            "--ignore-user-config",
            # Project-local execpolicy rules cannot widen an OS sandbox, but
            # they can make one project behave unlike another. A review that
            # depends on a file in the repo being reviewed is not one we want.
            "--ignore-rules",
            "--json",
            _READ_ONLY_PREAMBLE + prompt,
        ]

    def run(
        self,
        prompt: str,
        project_dir: Path,
        timeout_s: int,
        on_event: OnEvent | None = None,
    ) -> RunResult:
        """One read-only review.

        Unlike the Claude adapter there is no separate buffered path: NDJSON is
        the only output format worth parsing, and ``stream_ndjson`` is the only
        implementation that reliably kills the process tree at the deadline.
        An unattended run is the same run with nobody listening.
        """
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

        collector = _Collector(project_dir, on_event)
        try:
            outcome = stream_ndjson(self.command(prompt), project_dir, timeout_s, collector)
        except FileNotFoundError:
            return finish("failed", "", f"`{self.binary}` is not on PATH")
        except OSError as exc:
            return finish("failed", "", f"could not start `{self.binary}`: {exc}")

        findings = collector.findings

        if collector.wrote:
            # Before anything else, including the exit code: a run that changed
            # files broke the promise the provider is here to keep, and "it also
            # exited 0" is not the headline. Fail loudly and keep the output, so
            # the digest carries the evidence.
            return finish(
                "failed",
                findings,
                f"sandbox breach — codex reported changing {', '.join(collector.wrote)}; "
                "refusing to treat this run as read-only",
            )

        if outcome.timed_out:
            return finish("timeout", findings, f"no output after {timeout_s}s")

        if outcome.returncode != 0:
            return finish("failed", findings, collector.error or outcome.stderr_head)

        if not findings:
            return finish("failed", "", collector.error or "no output")

        return finish("ok", findings)
