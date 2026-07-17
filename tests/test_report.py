from __future__ import annotations

from datetime import date, datetime

import pytest

from nightaudit.adapters.base import RunResult
from nightaudit.budget import Ledger
from nightaudit.report import (
    PLACEHOLDER,
    budget_bar,
    dedupe,
    format_duration,
    format_tokens,
    load_results,
    parse_finding_line,
    parse_findings,
    render_digest,
    store_result,
    tokens_by_project,
    write_digest,
)

ON = date(2026, 7, 14)
AT = datetime(2026, 7, 14, 3, 0)


def result(**kw) -> RunResult:
    base = dict(
        provider="claude_code",
        project="acme-api",
        task="code_review",
        status="ok",
        findings_md="",
        started_at=AT,
        duration_s=72.0,
    )
    base.update(kw)
    return RunResult(**base)


# ---- severity parsing -------------------------------------------------


def test_parses_the_documented_format():
    r = result(
        findings_md=(
            "- HIGH src/search/query.ts:88 — User input concatenated into SQL\n"
            "- MED api/routes/metrics.py:42 — Missing auth guard\n"
            "- LOW README.md:31 — Stale quickstart\n"
        )
    )
    findings = parse_findings(r)
    assert [f.severity for f in findings] == ["HIGH", "MED", "LOW"]
    assert findings[0].ref == "src/search/query.ts:88"
    assert "SQL" in findings[0].text


def test_leading_file_ref_is_not_repeated_in_the_text():
    # The documented format leads with the ref and we render it separately;
    # keeping it inline printed the path twice on every line.
    [f] = parse_findings(result(findings_md="- HIGH src/auth.py:142 — no expiry"))
    assert f.ref == "src/auth.py:142"
    assert f.text == "no expiry"
    assert "src/auth.py:142" not in f.text


def test_a_backticked_leading_ref_is_not_repeated_either():
    # What the model actually writes. The old check was `body.startswith(ref)`,
    # which a backtick defeats — so every digest line carried the path twice.
    [f] = parse_findings(result(findings_md="- HIGH `src/auth.py:142` — no expiry"))
    assert f.ref == "src/auth.py:142"
    assert f.text == "no expiry"


@pytest.mark.parametrize(
    "line",
    [
        "- HIGH **src/auth.py:142** — no expiry",
        "- HIGH `src/auth.py:142`: no expiry",
        "- HIGH `src/auth.py:142` no expiry",
    ],
)
def test_the_ref_is_stripped_through_whatever_markup_wraps_it(line):
    [f] = parse_findings(result(findings_md=line))
    assert f.text == "no expiry"


def test_ref_mentioned_mid_sentence_is_left_alone():
    [f] = parse_findings(result(findings_md="- HIGH Tokens set in auth.py:142 never expire"))
    assert f.ref == "auth.py:142"
    assert f.text == "Tokens set in auth.py:142 never expire"


def test_parse_finding_line_ignores_prose():
    # A live view classifies line by line, so non-list prose must not become
    # a finding just because it mentions a path.
    assert parse_finding_line("I'll start by reading src/auth.py:142 now.") is None
    assert parse_finding_line("") is None


def test_parse_finding_line_agrees_with_parse_findings():
    md = "- HIGH `src/auth.py:142` — no expiry"
    [batch] = parse_findings(result(findings_md=md))
    single = parse_finding_line(md)
    assert (single.severity, single.ref, single.text) == (
        batch.severity,
        batch.ref,
        batch.text,
    )


def test_a_finding_that_is_only_a_ref_still_survives():
    [f] = parse_findings(result(findings_md="- HIGH src/auth.py:142"))
    assert f.text == "src/auth.py:142"


def test_no_findings_yields_nothing():
    assert parse_findings(result(findings_md="No findings.")) == []
    assert parse_findings(result(findings_md="no findings")) == []
    assert parse_findings(result(findings_md="")) == []
    assert parse_findings(result(findings_md="   \n  ")) == []


def test_unlabelled_finding_defaults_to_low_rather_than_being_dropped():
    findings = parse_findings(result(findings_md="- something smells in a.py:3"))
    assert len(findings) == 1
    assert findings[0].severity == "LOW"


@pytest.mark.parametrize(
    "line,expected",
    [
        ("- **HIGH** a.py:1 — x", "HIGH"),
        ("- `HIGH` a.py:1 — x", "HIGH"),
        ("- [HIGH] a.py:1 — x", "HIGH"),
        ("- HIGH: a.py:1 — x", "HIGH"),
        ("- high a.py:1 — x", "HIGH"),
        ("- CRITICAL a.py:1 — x", "HIGH"),
        ("- Medium a.py:1 — x", "MED"),
        ("- WARNING a.py:1 — x", "MED"),
        ("- minor a.py:1 — x", "LOW"),
        ("- info a.py:1 — x", "LOW"),
        ("* HIGH a.py:1 — x", "HIGH"),
        ("+ HIGH a.py:1 — x", "HIGH"),
        ("1. HIGH a.py:1 — x", "HIGH"),
        ("  - HIGH a.py:1 — x", "HIGH"),
        ("- 🔴 HIGH a.py:1 — x", "HIGH"),
    ],
)
def test_severity_parsing_is_lenient(line, expected):
    findings = parse_findings(result(findings_md=line))
    assert len(findings) == 1, f"failed to parse: {line}"
    assert findings[0].severity == expected


def test_prose_lines_are_not_findings():
    r = result(
        findings_md=(
            "Here is what I found after reviewing the code:\n"
            "\n"
            "- HIGH a.py:1 — real finding\n"
            "\n"
            "That's all.\n"
        )
    )
    findings = parse_findings(r)
    assert len(findings) == 1
    assert findings[0].text == "real finding"
    assert findings[0].ref == "a.py:1"


def test_file_ref_is_optional():
    findings = parse_findings(result(findings_md="- HIGH the whole design is wrong"))
    assert len(findings) == 1
    assert findings[0].ref == ""


def test_a_word_that_merely_starts_a_line_is_not_a_severity():
    findings = parse_findings(result(findings_md="- Consider caching a.py:1"))
    assert findings[0].severity == "LOW"
    assert findings[0].text.startswith("Consider caching")


# ---- formatting -------------------------------------------------------


@pytest.mark.parametrize(
    "seconds,expected",
    [(0, "0s"), (22, "22s"), (59, "59s"), (60, "1m00s"), (72, "1m12s"), (300, "5m00s")],
)
def test_duration_formatting(seconds, expected):
    assert format_duration(result(duration_s=seconds)) == expected


def test_skipped_runs_have_no_duration():
    assert format_duration(result(status="skipped", duration_s=0)) == "—"


def test_budget_bar_matches_the_spec_example():
    assert budget_bar(3, 6) == "▓▓▓░░░"
    assert budget_bar(0, 6) == "░░░░░░"
    assert budget_bar(6, 6) == "▓▓▓▓▓▓"


def test_budget_bar_scales_when_the_cap_is_large():
    bar = budget_bar(50, 100)
    assert len(bar) == 12
    assert bar.count("▓") == 6


def test_budget_bar_never_shows_spent_budget_as_empty():
    # 1/100 rounds to zero cells; showing an empty bar would be a lie.
    assert budget_bar(1, 100).startswith("▓")


# ---- storage ----------------------------------------------------------


def test_store_writes_json_and_markdown(cfg):
    store_result(cfg, result())
    day = cfg.digest_dir / "2026-07-14"
    assert (day / "acme-api-code_review-030000.json").exists()
    assert (day / "acme-api-code_review-030000.md").exists()


def test_stored_result_round_trips(cfg):
    original = result(findings_md="- HIGH a.py:1 — x", detail="")
    store_result(cfg, original)
    [loaded] = load_results(cfg, ON)
    assert loaded.to_dict() == original.to_dict()


def test_two_runs_in_the_same_second_do_not_overwrite_each_other(cfg):
    # Filenames are second-granular. `nightaudit run --now` twice in a loop hits
    # this instantly, and a lost run contradicts the digest's own promise.
    store_result(cfg, result(findings_md="- HIGH a.py:1 — first"))
    store_result(cfg, result(findings_md="- HIGH b.py:2 — second"))

    loaded = load_results(cfg, ON)
    assert len(loaded) == 2
    assert {r.findings_md for r in loaded} == {
        "- HIGH a.py:1 — first",
        "- HIGH b.py:2 — second",
    }


def test_the_run_log_never_loses_a_run_the_ledger_counted(cfg):
    for i in range(3):
        store_result(cfg, result(findings_md=f"- LOW a.py:{i} — finding {i}"))
    # Three attempts spent quota, so three rows must appear.
    log = render(cfg, load_results(cfg, ON)).split("## Run log")[1]
    assert log.count("| gradagent |") + log.count("| acme-api |") == 3


def test_retries_do_not_overwrite_the_first_attempt(cfg):
    store_result(cfg, result(status="failed", attempt=1))
    store_result(cfg, result(status="ok", attempt=2))
    assert len(load_results(cfg, ON)) == 2


def test_results_come_back_in_time_order(cfg):
    store_result(cfg, result(started_at=datetime(2026, 7, 14, 5, 0), task="deps_audit"))
    store_result(cfg, result(started_at=datetime(2026, 7, 14, 1, 0), task="code_review"))
    assert [r.task for r in load_results(cfg, ON)] == ["code_review", "deps_audit"]


def test_a_corrupt_result_file_does_not_sink_the_digest(cfg):
    store_result(cfg, result())
    (cfg.digest_dir / "2026-07-14" / "broken.json").write_text("{{{", encoding="utf-8")
    assert len(load_results(cfg, ON)) == 1


def test_no_results_for_an_unknown_day(cfg):
    assert load_results(cfg, date(2020, 1, 1)) == []


def test_project_names_with_slashes_do_not_escape_the_day_dir(cfg):
    store_result(cfg, result(project="evil/../../etc"))
    files = list((cfg.digest_dir / "2026-07-14").glob("*.json"))
    assert len(files) == 1
    assert files[0].parent == cfg.digest_dir / "2026-07-14"


# ---- digest rendering -------------------------------------------------


def render(cfg, results, ledger=None):
    return render_digest(
        cfg,
        ON,
        ledger=ledger or Ledger(cfg.digest_dir.parent / "ledger.json"),
        results=results,
        generated_at=datetime(2026, 7, 14, 6, 0),
    )


def test_digest_has_every_required_section(cfg):
    text = render(cfg, [result(findings_md="- HIGH a.py:1 — boom")])
    assert "# Nightaudit · morning digest" in text
    assert "## Budget remaining" in text
    assert "## Highlights" in text
    assert "## By project" in text
    assert "## Run log" in text


def test_digest_header_counts_projects_and_runs(cfg):
    text = render(cfg, [result(), result(project="payments-web")])
    assert "2 projects · 2 runs" in text


def test_header_is_singular_for_one_run(cfg):
    assert "1 project · 1 run" in render(cfg, [result()])


def test_budget_bar_appears_with_both_caps(cfg, tmp_path):
    ledger = Ledger(tmp_path / "ledger.json")
    for _ in range(3):
        ledger.increment("claude_code", AT)
    text = render(cfg, [result()], ledger=ledger)
    assert "▓▓▓░░░ 3/6 today · 3/30 week" in text


def test_highlights_are_severity_ordered_across_projects(cfg):
    results = [
        result(project="a", findings_md="- LOW a.py:1 — low thing"),
        result(project="b", findings_md="- HIGH b.py:2 — high thing"),
        result(project="c", findings_md="- MED c.py:3 — med thing"),
    ]
    highlights = render(cfg, results).split("## Highlights")[1].split("## By project")[0]
    assert highlights.index("high thing") < highlights.index("med thing")
    assert highlights.index("med thing") < highlights.index("low thing")


def test_highlights_are_capped_at_five(cfg):
    md = "\n".join(f"- HIGH a.py:{i} — finding {i}" for i in range(12))
    highlights = (
        render(cfg, [result(findings_md=md)])
        .split("## Highlights")[1]
        .split("## By project")[0]
    )
    assert highlights.count("- 🔴") == 5


def test_findings_carry_severity_emoji(cfg):
    text = render(
        cfg,
        [
            result(
                findings_md=(
                    "- HIGH a.py:1 — h\n- MED b.py:2 — m\n- LOW c.py:3 — l\n"
                )
            )
        ],
    )
    assert "🔴" in text and "🟠" in text and "🟡" in text


def test_findings_only_come_from_successful_runs(cfg):
    # A failed run's stdout is not a finding list.
    text = render(cfg, [result(status="failed", findings_md="- HIGH a.py:1 — ignore me")])
    assert "ignore me" not in text
    assert "no run completed successfully" in text


def test_run_log_lists_every_run(cfg):
    text = render(cfg, [result(), result(task="deps_audit", status="failed")])
    log = text.split("## Run log")[1]
    assert "| acme-api | code_review | claude_code | ok | 1m12s | 03:00 |" in log
    assert "deps_audit" in log


def test_skipped_and_failed_runs_survive_into_the_run_log(cfg):
    results = [
        result(status="skipped", project="—", task="—", detail="budget · daily budget spent (6/6 today)", duration_s=0),
        result(status="timeout", task="deps_audit", detail="no output after 600s"),
    ]
    log = render(cfg, results).split("## Run log")[1]
    assert "skipped · budget · daily budget spent (6/6 today)" in log
    assert "timeout · no output after 600s" in log
    assert "nothing silently disappears" in render(cfg, results)


def test_repeated_runs_of_a_task_do_not_repeat_their_findings(cfg):
    # Cron runs code_review twice in a night; it finds the same thing twice.
    same = "- HIGH a.py:1 — boom"
    text = render(cfg, [result(findings_md=same), result(findings_md=same)])
    assert text.count("boom") == 2  # once in Highlights, once in By project


def test_the_same_file_flagged_by_two_tasks_is_kept_twice(cfg):
    # Different tasks are different observations — both are worth seeing.
    findings = dedupe(
        parse_findings(result(task="code_review", findings_md="- HIGH a.py:1 — boom"))
        + parse_findings(result(task="security_audit", findings_md="- HIGH a.py:1 — boom"))
    )
    assert len(findings) == 2


def test_a_budget_skip_is_not_counted_as_a_project(cfg):
    results = [
        result(),
        result(status="skipped", project=PLACEHOLDER, task=PLACEHOLDER, detail="budget"),
    ]
    text = render(cfg, results)
    assert "1 project · 2 runs" in text


def test_a_skip_is_stored_under_a_readable_filename(cfg):
    store_result(
        cfg,
        result(status="skipped", project=PLACEHOLDER, task=PLACEHOLDER, detail="budget"),
    )
    names = [p.name for p in (cfg.digest_dir / "2026-07-14").glob("*.json")]
    assert names == ["skipped-claude_code-030000.json"]


def test_empty_day_renders_without_crashing(cfg):
    text = render(cfg, [])
    assert "Nothing ran today" in text
    assert "0 runs" in text
    assert "## Budget remaining" in text


def test_all_failed_day_renders_without_crashing(cfg):
    text = render(cfg, [result(status="failed", findings_md=""), result(status="failed")])
    assert "no run completed successfully today" in text
    assert "## By project" not in text  # nothing to group
    assert "## Run log" in text


def test_clean_day_says_so(cfg):
    text = render(cfg, [result(findings_md="No findings.")])
    assert "every run came back clean" in text


def test_digest_ends_with_exactly_one_newline(cfg):
    text = render(cfg, [result()])
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def test_write_digest_puts_the_file_where_the_spec_says(cfg):
    store_result(cfg, result())
    path = write_digest(cfg, ON, ledger=Ledger(cfg.digest_dir.parent / "l.json"))
    assert path == cfg.digest_dir / "DIGEST-2026-07-14.md"
    assert path.read_text(encoding="utf-8").startswith("# Nightaudit")


# ---- token usage ------------------------------------------------------


def test_format_tokens_is_compact():
    assert format_tokens(0) == "0"
    assert format_tokens(482) == "482"
    assert format_tokens(48200) == "48.2k"
    assert format_tokens(1_250_000) == "1.2M"


def test_tokens_by_project_sums_across_runs_and_drops_zeros():
    results = [
        result(project="a", tokens=1000),
        result(project="a", tokens=500),
        result(project="b", tokens=2000),
        result(project="c", tokens=0),  # reported nothing — not a row of zeros
    ]
    assert tokens_by_project(results) == {"a": 1500, "b": 2000}


def test_tokens_by_project_counts_billed_failures_not_placeholders():
    results = [
        result(status="failed", tokens=700),
        result(project=PLACEHOLDER, tokens=999),  # a skipped slot, not a project
    ]
    assert tokens_by_project(results) == {"acme-api": 700}


def test_stored_result_keeps_its_token_count(cfg):
    store_result(cfg, result(tokens=12345))
    [loaded] = load_results(cfg, ON)
    assert loaded.tokens == 12345


def test_the_result_sidecar_shows_tokens(cfg):
    store_result(cfg, result(tokens=48200))
    md = (cfg.digest_dir / "2026-07-14" / "acme-api-code_review-030000.md").read_text(
        encoding="utf-8"
    )
    assert "- tokens: 48.2k" in md


def test_digest_reports_tokens_per_project_and_a_total(cfg):
    text = render(
        cfg,
        [
            result(project="acme-api", findings_md="- HIGH a.py:1 — x", tokens=48200),
            result(project="payments-web", findings_md="- LOW b.py:2 — y", tokens=31000),
        ],
    )
    assert "## Tokens" in text
    assert "- acme-api — 48.2k" in text
    assert "- payments-web — 31.0k" in text
    assert "**total — 79.2k**" in text
    # And the header carries the grand total.
    assert "· 79.2k tokens" in text


def test_digest_omits_the_tokens_section_when_nothing_was_reported(cfg):
    text = render(cfg, [result(findings_md="- HIGH a.py:1 — x", tokens=0)])
    assert "## Tokens" not in text
    assert "tokens" not in text.split("## Run log")[0].lower()
