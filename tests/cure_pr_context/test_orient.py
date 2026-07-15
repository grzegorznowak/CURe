from __future__ import annotations

import re

from cure_pr_context.orient import build_orientation_brief


def test_build_orientation_brief_empty_inputs_returns_empty_without_llm() -> None:
    called = False

    def run_llm(prompt: str) -> str:
        nonlocal called
        called = True
        return "unused"

    assert build_orientation_brief(discussion=[], past_reviews=[], pr_stats={}, run_llm=run_llm) == ""
    assert called is False


def test_build_orientation_brief_invokes_llm_with_bounded_normalized_payload() -> None:
    prompts: list[str] = []

    def run_llm(prompt: str) -> str:
        prompts.append(prompt)
        return "## Problem areas\n- Investigate API failures."

    brief = build_orientation_brief(
        discussion=[
            {
                "kind": "issue_comment",
                "author": "reviewer",
                "body": "please check API failures",
            }
        ],
        past_reviews=[
            {
                "source": "local",
                "body": "The retry issue was addressed.",
                "reviewed_head": "abc1234",
            }
        ],
        pr_stats={"changed_files": 2, "changed_lines": 17},
        run_llm=run_llm,
    )

    assert "Use this prior context as orientation only" in brief
    for header in ["Resolved areas", "Problem areas", "Pending issues", "Repeated patterns", "Decisions made"]:
        assert header in brief

    assert len(prompts) == 1
    prompt = prompts[0]
    assert '"kind": "issue_comment"' in prompt
    assert '"body": "please check API failures"' in prompt
    assert '"reviewed_head": "abc1234"' in prompt
    assert '"changed_lines": 17' in prompt
    assert "Resolved areas only when supplied discussion or past-review text" in prompt
    assert "not authoritative GitHub review-thread resolution state" in prompt


def test_build_orientation_brief_adds_headings_when_llm_only_mentions_section_names() -> None:
    usage_only = """This brief is orientation only.

- "Resolved areas": do not re-evaluate them
- "Problem areas": prioritize them
- "Pending issues": verify them
- "Repeated patterns": mention them if present
- "Decisions made": accept them as context
"""

    brief = build_orientation_brief(
        discussion=[{"kind": "issue_comment", "body": "context"}],
        past_reviews=[],
        pr_stats={},
        run_llm=lambda _prompt: usage_only,
    )

    for header in ["Resolved areas", "Problem areas", "Pending issues", "Repeated patterns", "Decisions made"]:
        assert re.search(rf"^## {re.escape(header)}$", brief, flags=re.MULTILINE)
