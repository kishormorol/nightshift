"""Provider adapters.

Each adapter wraps one AI coding CLI the user already pays for. Adapters are
strictly read-only: they may inspect a project, never modify it.
"""

from __future__ import annotations

import inspect

from nightaudit.adapters.base import Adapter, AdapterError, RunResult, Status
from nightaudit.adapters.claude_code import ClaudeCodeAdapter
from nightaudit.adapters.codex import CodexAdapter
from nightaudit.adapters.copilot import CopilotAdapter

_REGISTRY: dict[str, type] = {
    "claude_code": ClaudeCodeAdapter,
    "codex": CodexAdapter,
    "copilot": CopilotAdapter,
}


def get(name: str, binary: str | None = None) -> Adapter:
    """Instantiate the adapter registered under ``name``.

    ``binary`` overrides where the adapter looks for its CLI. Left ``None``, the
    adapter keeps its own default and finds it on PATH as before.
    """
    try:
        cls = _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY))
        raise AdapterError(f"unknown provider {name!r} — known: {known}") from None
    if binary is None:
        return cls()  # type: ignore[return-value]
    # Asked by name rather than caught as a TypeError: `cls(binary=...)` raising
    # TypeError from somewhere deeper inside __init__ would look identical, and
    # we would report the wrong cause for it.
    if "binary" not in inspect.signature(cls).parameters:
        raise AdapterError(
            f"provider {name!r} does not take a custom binary path — it does not "
            f"run a CLI of its own. Remove `binary` from providers.{name}."
        )
    return cls(binary=binary)  # type: ignore[return-value]


def names() -> list[str]:
    return sorted(_REGISTRY)


__all__ = [
    "Adapter",
    "AdapterError",
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "CopilotAdapter",
    "RunResult",
    "Status",
    "get",
    "names",
]
