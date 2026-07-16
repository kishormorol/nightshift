from __future__ import annotations

import pytest

from nightaudit import prompts


def test_the_five_documented_tasks_ship():
    available = prompts.available_tasks()
    for task in (
        "code_review",
        "security_audit",
        "deps_audit",
        "docs_drift",
        "dead_links",
    ):
        assert task in available


def test_every_shipped_prompt_demands_read_only_and_the_severity_format():
    for task in prompts.available_tasks():
        text = prompts.load(task).lower()
        assert "only read" in text or "may only read" in text, task
        assert "high" in text and "med" in text and "low" in text, task
        assert "file:line" in text or "line>" in text, task
        assert "no findings." in text, task


def test_user_prompts_dir_adds_a_task(isolated_home):
    (isolated_home / "prompts").mkdir()
    (isolated_home / "prompts" / "my_task.md").write_text("do a thing", encoding="utf-8")
    assert "my_task" in prompts.available_tasks()
    assert prompts.load("my_task") == "do a thing"


def test_user_prompt_overrides_a_shipped_one(isolated_home):
    (isolated_home / "prompts").mkdir()
    (isolated_home / "prompts" / "code_review.md").write_text("mine", encoding="utf-8")
    assert prompts.load("code_review") == "mine"


def test_missing_task_names_the_search_path_and_alternatives():
    with pytest.raises(prompts.PromptError) as exc:
        prompts.load("no_such_task")
    assert "no_such_task" in str(exc.value)
    assert "code_review" in str(exc.value)


def test_empty_template_is_an_error(isolated_home):
    (isolated_home / "prompts").mkdir()
    (isolated_home / "prompts" / "blank.md").write_text("   \n", encoding="utf-8")
    with pytest.raises(prompts.PromptError, match="empty"):
        prompts.load("blank")


def test_find_returns_none_for_unknown():
    assert prompts.find("no_such_task") is None


def test_available_tasks_is_sorted_and_deduplicated(isolated_home):
    (isolated_home / "prompts").mkdir()
    (isolated_home / "prompts" / "code_review.md").write_text("mine", encoding="utf-8")
    tasks = prompts.available_tasks()
    assert tasks == sorted(tasks)
    assert tasks.count("code_review") == 1
