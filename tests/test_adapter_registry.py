"""The registry seam: turning a provider name into an adapter instance.

The `binary` path lives in config and is honoured by the adapters, but until
recently the registry instantiated with a bare ``cls()`` and dropped it on the
floor — so a configured path was accepted, ignored, and the provider reported
itself missing. These tests pin the wiring, not the adapters.
"""

from __future__ import annotations

import pytest

from nightaudit import adapters
from nightaudit.adapters import AdapterError


def test_unknown_provider_names_the_known_ones():
    with pytest.raises(AdapterError, match="claude_code"):
        adapters.get("nope")


def test_without_an_override_the_adapter_keeps_its_default_binary():
    assert adapters.get("claude_code").binary == "claude"
    assert adapters.get("codex").binary == "codex"


def test_an_override_reaches_the_adapter():
    path = "/Applications/ChatGPT.app/Contents/Resources/codex"
    assert adapters.get("codex", path).binary == path


def test_a_stub_provider_says_so_rather_than_raising_a_typeerror():
    # CopilotAdapter runs no CLI, so it takes no binary. The registry asks the
    # signature instead of catching TypeError, which would also swallow a
    # TypeError raised from inside a real __init__ and blame the wrong thing.
    with pytest.raises(AdapterError, match="does not take a custom binary path"):
        adapters.get("copilot", "/somewhere/copilot")


def test_a_stub_provider_is_still_constructible_without_one():
    assert adapters.get("copilot").name == "copilot"
