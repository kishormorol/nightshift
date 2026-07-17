"""The process helpers shared by the streaming adapters.

For now this covers only :func:`tokens_from_usage` — the one piece of shared
parsing that both the Claude and Codex adapters lean on to answer "how many
tokens did this run take". It is telemetry riding the same stream as the
findings, so its first duty is to never turn a billed run into an exception.
"""

from __future__ import annotations

from nightaudit.adapters._process import tokens_from_usage


def test_sums_input_and_output():
    assert tokens_from_usage({"input_tokens": 10, "output_tokens": 5}) == 15


def test_counts_claude_cache_tokens_as_real_tokens():
    usage = {
        "input_tokens": 1000,
        "output_tokens": 200,
        "cache_creation_input_tokens": 300,
        "cache_read_input_tokens": 5000,
    }
    assert tokens_from_usage(usage) == 6500


def test_a_missing_counter_contributes_zero():
    assert tokens_from_usage({"output_tokens": 5}) == 5


def test_unknown_keys_are_ignored():
    assert tokens_from_usage({"input_tokens": 3, "service_tier": "standard"}) == 3


def test_non_numeric_values_do_not_raise():
    assert tokens_from_usage({"input_tokens": "lots", "output_tokens": None}) == 0


def test_booleans_are_not_counted_as_tokens():
    # bool is an int subclass; True must not read as one token.
    assert tokens_from_usage({"input_tokens": True, "output_tokens": 4}) == 4


def test_a_non_dict_usage_is_zero():
    assert tokens_from_usage(None) == 0
    assert tokens_from_usage("48000") == 0
    assert tokens_from_usage(42) == 0
