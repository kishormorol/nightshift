from __future__ import annotations

from nightaudit.queue import Queue

PAIRS = [("a", "code_review"), ("a", "deps_audit"), ("b", "docs_drift")]


def test_first_pop_starts_at_the_top(tmp_path):
    assert Queue(tmp_path / "q.json").pop(PAIRS) == ("a", "code_review")


def test_pops_round_robin_and_wraps(tmp_path):
    q = Queue(tmp_path / "q.json")
    assert [q.pop(PAIRS) for _ in range(4)] == [
        ("a", "code_review"),
        ("a", "deps_audit"),
        ("b", "docs_drift"),
        ("a", "code_review"),  # wrapped
    ]


def test_position_survives_a_new_process(tmp_path):
    path = tmp_path / "q.json"
    Queue(path).pop(PAIRS)
    # Cron gives each run a fresh process; the rotation must not restart.
    assert Queue(path).pop(PAIRS) == ("a", "deps_audit")


def test_peek_does_not_advance(tmp_path):
    q = Queue(tmp_path / "q.json")
    assert q.peek(PAIRS) == ("a", "code_review")
    assert q.peek(PAIRS) == ("a", "code_review")
    assert q.pop(PAIRS) == ("a", "code_review")


def test_rotation_starts_where_peek_points_and_lists_everything_once(tmp_path):
    q = Queue(tmp_path / "q.json")
    assert q.rotation(PAIRS) == PAIRS
    q.pop(PAIRS)  # served ("a", "code_review"); next is ("a", "deps_audit")
    assert q.rotation(PAIRS) == [
        ("a", "deps_audit"),
        ("b", "docs_drift"),
        ("a", "code_review"),  # wrapped, still present exactly once
    ]


def test_rotation_of_nothing_is_empty(tmp_path):
    assert Queue(tmp_path / "q.json").rotation([]) == []


def test_take_can_serve_a_pair_out_of_turn(tmp_path):
    # What the scheduler does when the pair whose turn it is can't run: serve a
    # later one and record that, rather than hold the rotation still.
    q = Queue(tmp_path / "q.json")
    q.take(("b", "docs_drift"))
    assert q.last == ("b", "docs_drift")
    assert q.peek(PAIRS) == ("a", "code_review")  # rotation resumes after it


def test_take_survives_a_new_process(tmp_path):
    path = tmp_path / "q.json"
    Queue(path).take(("a", "deps_audit"))
    assert Queue(path).last == ("a", "deps_audit")


def test_empty_pairs_yields_nothing(tmp_path):
    q = Queue(tmp_path / "q.json")
    assert q.pop([]) is None
    assert q.peek([]) is None


def test_removed_last_pair_restarts_rather_than_wedging(tmp_path):
    path = tmp_path / "q.json"
    q = Queue(path)
    q.pop(PAIRS)
    q.pop(PAIRS)  # last = ("a", "deps_audit")

    # The user edits config and drops that pair entirely.
    shrunk = [("b", "docs_drift"), ("c", "code_review")]
    assert Queue(path).pop(shrunk) == ("b", "docs_drift")


def test_reordered_config_keeps_relative_position(tmp_path):
    path = tmp_path / "q.json"
    Queue(path).pop(PAIRS)  # last = ("a", "code_review")
    reordered = [("b", "docs_drift"), ("a", "code_review"), ("a", "deps_audit")]
    # Position is the *pair*, not an index, so we resume after it.
    assert Queue(path).pop(reordered) == ("a", "deps_audit")


def test_corrupt_queue_file_restarts_from_the_top(tmp_path):
    path = tmp_path / "q.json"
    path.write_text("]]not json", encoding="utf-8")
    assert Queue(path).pop(PAIRS) == ("a", "code_review")


def test_reset_clears_position(tmp_path):
    path = tmp_path / "q.json"
    q = Queue(path)
    q.pop(PAIRS)
    q.reset()
    assert Queue(path).pop(PAIRS) == ("a", "code_review")


def test_single_pair_repeats(tmp_path):
    path = tmp_path / "q.json"
    only = [("a", "code_review")]
    q = Queue(path)
    assert q.pop(only) == ("a", "code_review")
    assert q.pop(only) == ("a", "code_review")
