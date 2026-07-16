"""Pinning a project to one provider.

A `provider:` on a project is a hard pin: that provider reviews it, or nobody
does. The pin must never leak into who reviews an *unpinned* project, and an
unrunnable pin must cost that project its turn rather than everyone else's.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from nightaudit import scheduler
from nightaudit.budget import Ledger
from nightaudit.config import ConfigError, parse
from nightaudit.queue import Queue
from tests.conftest import FakeAdapter

AT_NIGHT = datetime(2026, 7, 14, 3, 0)


def build(tmp_path, projects, providers=None):
    for entry in projects:
        d = tmp_path / entry["name"]
        d.mkdir(exist_ok=True)
        entry.setdefault("path", str(d))
        entry.setdefault("tasks", ["code_review"])
    return parse(
        {
            "providers": providers
            or {"claude_code": {"enabled": True}, "codex": {"enabled": True}},
            "projects": projects,
            "schedule": {"windows": ["00:00-23:59"], "idle_minutes": 0},
            "digest": {"dir": str(tmp_path / "reports")},
        }
    )


@pytest.fixture
def two_providers():
    """Both usable. Claude is first in config order, so it wins by default."""
    return {"claude_code": FakeAdapter(name="claude_code"), "codex": FakeAdapter(name="codex")}


def run(cfg, adapters, tmp_path, **kw):
    kw.setdefault("now", AT_NIGHT)
    kw.setdefault("ledger", Ledger(tmp_path / "ledger.json"))
    kw.setdefault("queue", Queue(tmp_path / "queue.json"))
    kw.setdefault("get_adapter", lambda n, binary=None: adapters[n])
    return scheduler.run_once(cfg, **kw)


# ---- config ------------------------------------------------------------


def test_a_pin_is_parsed(tmp_path):
    cfg = build(tmp_path, [{"name": "a", "provider": "codex"}])
    assert cfg.projects[0].provider == "codex"


def test_no_pin_means_none(tmp_path):
    assert build(tmp_path, [{"name": "a"}]).projects[0].provider is None


def test_a_pin_to_an_unknown_provider_names_the_known_ones(tmp_path):
    with pytest.raises(ConfigError, match="claude_code"):
        build(tmp_path, [{"name": "a", "provider": "claud"}])


def test_a_pin_to_a_disabled_provider_is_refused(tmp_path):
    # It could never run, on any machine, at any hour — the same contradiction
    # as a config with every provider disabled, which is already refused.
    with pytest.raises(ConfigError, match="pinned to provider 'codex', which is disabled"):
        build(
            tmp_path,
            [{"name": "a", "provider": "codex"}],
            providers={"claude_code": {"enabled": True}, "codex": {"enabled": False}},
        )


@pytest.mark.parametrize("value", ["", "   ", 3, True, ["codex"]])
def test_a_pin_must_look_like_a_provider_name(tmp_path, value):
    with pytest.raises(ConfigError, match=r"projects\[0\].provider"):
        build(tmp_path, [{"name": "a", "provider": value}])


# ---- routing -----------------------------------------------------------


def test_a_pin_beats_config_order(tmp_path, two_providers):
    # claude_code is first and perfectly usable; the pin must still win.
    cfg = build(tmp_path, [{"name": "a", "provider": "codex"}])
    outcome = run(cfg, two_providers, tmp_path)
    assert outcome.results[-1].provider == "codex"
    assert len(two_providers["claude_code"].calls) == 0


def test_without_a_pin_the_first_usable_provider_takes_it(tmp_path, two_providers):
    cfg = build(tmp_path, [{"name": "a"}])
    outcome = run(cfg, two_providers, tmp_path)
    assert outcome.results[-1].provider == "claude_code"


def test_a_pinned_project_is_never_handed_to_another_provider(tmp_path):
    # The whole point of the hard pin: codex is out, claude is free, and the
    # project waits anyway rather than being reviewed by the wrong one.
    adapters = {
        "claude_code": FakeAdapter(name="claude_code"),
        "codex": FakeAdapter(name="codex", is_available=False, unavailable_reason="not installed"),
    }
    cfg = build(tmp_path, [{"name": "a", "provider": "codex"}])
    outcome = run(cfg, adapters, tmp_path)
    assert outcome.ran is False
    assert "pinned to codex" in outcome.reason
    assert len(adapters["claude_code"].calls) == 0


def test_an_unrunnable_pin_costs_only_that_project_its_turn(tmp_path):
    # `a` is first in the rotation and pinned to an unavailable codex. `b` is
    # unpinned and must still be reviewed: one project's dead pin cannot freeze
    # the others, which is the starvation Queue.pop already refuses.
    adapters = {
        "claude_code": FakeAdapter(name="claude_code"),
        "codex": FakeAdapter(name="codex", is_available=False),
    }
    cfg = build(tmp_path, [{"name": "a", "provider": "codex"}, {"name": "b"}])
    outcome = run(cfg, adapters, tmp_path)
    assert outcome.ran is True
    assert outcome.results[-1].project == "b"
    assert outcome.results[-1].provider == "claude_code"


def test_a_passed_over_project_comes_round_again(tmp_path):
    # Skipping `a`'s turn must not drop it from the rotation for good: once
    # codex is back, `a` is reviewed on a later tick.
    codex = FakeAdapter(name="codex", is_available=False)
    adapters = {"claude_code": FakeAdapter(name="claude_code"), "codex": codex}
    cfg = build(tmp_path, [{"name": "a", "provider": "codex"}, {"name": "b"}])
    queue = Queue(tmp_path / "queue.json")

    first = run(cfg, adapters, tmp_path, queue=queue)
    assert first.results[-1].project == "b"

    codex.is_available = True
    second = run(cfg, adapters, tmp_path, queue=queue)
    assert second.results[-1].project == "a"
    assert second.results[-1].provider == "codex"


def test_when_nothing_can_run_the_rotation_is_untouched(tmp_path):
    # A run that reviews nothing must not spend a turn, or a provider that is
    # down for a day would silently eat every project's place in the queue.
    adapters = {
        "claude_code": FakeAdapter(name="claude_code", is_available=False),
        "codex": FakeAdapter(name="codex", is_available=False),
    }
    cfg = build(tmp_path, [{"name": "a"}, {"name": "b"}])
    queue = Queue(tmp_path / "queue.json")

    outcome = run(cfg, adapters, tmp_path, queue=queue)
    assert outcome.ran is False
    assert queue.last is None
    assert Queue(tmp_path / "queue.json").peek(cfg.pairs()) == ("a", "code_review")


def test_every_project_pinned_to_a_dead_provider_runs_nothing(tmp_path):
    adapters = {
        "claude_code": FakeAdapter(name="claude_code"),
        "codex": FakeAdapter(name="codex", is_available=False),
    }
    cfg = build(
        tmp_path, [{"name": "a", "provider": "codex"}, {"name": "b", "provider": "codex"}]
    )
    outcome = run(cfg, adapters, tmp_path)
    assert outcome.ran is False
    assert len(adapters["claude_code"].calls) == 0


# ---- choose_work on its own -------------------------------------------
#
# run_once returns before calling choose_work when nothing is usable, so these
# branches are unreachable through it. They are still the contract of a function
# that can be called directly, so they are pinned here rather than left to be
# discovered by the first caller who does.


def test_choose_work_with_no_usable_provider_chooses_nothing(tmp_path):
    cfg = build(tmp_path, [{"name": "a"}])
    choice = scheduler.choose_work(cfg, Queue(tmp_path / "q.json"), scheduler.Usable())
    assert choice.pair is None
    assert choice.provider is None


def test_choose_work_with_no_pairs_says_so(tmp_path, two_providers):
    cfg = build(tmp_path, [{"name": "a"}])
    object.__setattr__(cfg, "projects", ())
    choice = scheduler.choose_work(cfg, Queue(tmp_path / "q.json"), scheduler.Usable())
    assert choice.pair is None
    assert "no (project, task) pairs" in choice.reason


def test_the_provider_flag_and_a_pin_that_disagree_run_nothing(tmp_path, two_providers):
    # `--provider claude_code` restricts the run; `a` insists on codex. Neither
    # side gets to override the other, so nothing happens.
    cfg = build(tmp_path, [{"name": "a", "provider": "codex"}])
    outcome = run(cfg, two_providers, tmp_path, provider="claude_code")
    assert outcome.ran is False
    assert len(two_providers["claude_code"].calls) == 0
