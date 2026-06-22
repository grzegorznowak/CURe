from __future__ import annotations

from cure_pr_context.orient import build_orientation_brief


def test_build_orientation_brief_empty_inputs_returns_empty_without_llm() -> None:
    called = False

    def run_llm(prompt: str) -> str:
        nonlocal called
        called = True
        return "unused"

    assert build_orientation_brief(discussion=[], past_reviews=[], pr_stats={}, run_llm=run_llm) == ""
    assert called is False


def test_build_orientation_brief_invokes_llm_and_ensures_sections() -> None:
    prompts: list[str] = []

    def run_llm(prompt: str) -> str:
        prompts.append(prompt)
        return "## Problem areas\n- Investigate API failures."

    brief = build_orientation_brief(
        discussion=[{"kind": "issue_comment", "body": "please check API failures"}],
        past_reviews=[],
        pr_stats={"changed_files": 2},
        run_llm=run_llm,
    )

    assert "Use this prior context as orientation only" in brief
    for header in ["Resolved areas", "Problem areas", "Pending issues", "Repeated patterns", "Decisions made"]:
        assert header in brief
    assert "please check API failures" in prompts[0]
