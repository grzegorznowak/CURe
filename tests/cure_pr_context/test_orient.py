from __future__ import annotations

import re

import pytest

import cure_pr_context.orient as orient
from cure_pr_context.corpus import estimated_tokens
from cure_pr_context.orient import (
    ORIENTATION_INSTRUCTIONS,
    USAGE_INSTRUCTIONS,
    build_orientation_brief,
    finalize_injected_context,
    finalize_orientation_brief,
    is_valid_injected_context,
    is_valid_orientation_brief,
)

HEADINGS = ("Resolved areas", "Problem areas", "Pending issues", "Repeated patterns", "Decisions made")


def _valid_brief_at_estimate(target: int) -> str:
    suffix = "\n\n".join(
        [*(f"## {heading}\n- None identified." for heading in HEADINGS), USAGE_INSTRUCTIONS]
    )
    fence_overhead = len("```text\n\n```\n\n")
    body_length = target * 4 - len(suffix) - fence_overhead
    assert body_length > 0
    brief = "```text\n" + "x" * body_length + "\n```\n\n" + suffix
    assert estimated_tokens(brief) == target
    return brief


def test_orientation_uses_canonical_prompt_and_is_structurally_bounded() -> None:
    prompts: list[str] = []

    def run_llm(prompt: str) -> str:
        prompts.append(prompt)
        return "```text\n" + "x" * 9000

    result = build_orientation_brief(
        discussion=[{"kind": "issue_comment", "body": "context"}],
        pr_stats={"changed": 1},
        run_llm=run_llm,
    )
    assert prompts[0].startswith(ORIENTATION_INSTRUCTIONS + "\n--- PR_STATS_JSON ---\n")
    assert prompts[0].endswith("\n--- END_ORIENTATION_INPUT ---")
    assert estimated_tokens(result["brief"]) <= 2000
    assert result["meta"]["truncated"] is True
    assert is_valid_orientation_brief(result["brief"])
    assert "```" in result["brief"]
    for heading in HEADINGS:
        assert re.search(rf"^## {re.escape(heading)}$", result["brief"], re.MULTILINE)


def test_internal_orientation_output_finalization_failure_is_typed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = ValueError("orientation output finalizer failed")
    monkeypatch.setattr(
        orient,
        "_finalize_to_cap",
        lambda _raw, _cap: (_ for _ in ()).throw(failure),
    )

    with pytest.raises(orient.OrientationOutputFinalizationFailure) as raised:
        finalize_orientation_brief("scanner output")

    assert raised.value.cause is failure


def test_internal_fresh_injection_finalization_failure_is_typed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = ValueError("fresh injection finalizer failed")
    monkeypatch.setattr(
        orient,
        "_finalize_to_cap",
        lambda _raw, _cap: (_ for _ in ()).throw(failure),
    )

    with pytest.raises(orient.InjectedContextFinalizationFailure) as raised:
        finalize_injected_context("orientation brief")

    assert raised.value.cause is failure


def test_finalizer_ignores_fenced_pseudo_headings_and_emits_instructions_once() -> None:
    raw = "```md\n## Resolved areas\n```\n## Problem areas\n- real"
    result = build_orientation_brief(
        discussion=[{"body": "context"}], pr_stats={}, run_llm=lambda _prompt: raw
    )
    brief = result["brief"]
    assert brief.count("INSTRUCTIONS FOR USING PRIOR_CONTEXT:") == 1
    assert brief.count("## Resolved areas") == 2
    assert is_valid_orientation_brief(brief)


def test_orientation_output_cap_minus_one_is_preserved_exactly() -> None:
    original = _valid_brief_at_estimate(1999)

    brief, truncated = finalize_orientation_brief(original)

    assert (brief, estimated_tokens(brief), truncated) == (original, 1999, False)
    assert is_valid_orientation_brief(brief)


def test_orientation_output_at_cap_is_preserved_exactly() -> None:
    original = _valid_brief_at_estimate(2000)

    brief, truncated = finalize_orientation_brief(original)

    assert (brief, estimated_tokens(brief), truncated) == (original, 2000, False)
    assert is_valid_orientation_brief(brief)


def test_orientation_output_cap_plus_one_is_truncated_to_exact_cap() -> None:
    original = _valid_brief_at_estimate(2001)

    brief, truncated = finalize_orientation_brief(original)

    assert estimated_tokens(brief) == 2000
    assert truncated is True
    assert brief != original
    assert is_valid_orientation_brief(brief)


def test_validation_rejects_fence_would_be_closer_with_trailing_content() -> None:
    malformed = "\n".join(
        [
            "```text",
            "```not-a-closer",
            *(f"## {heading}" for heading in HEADINGS),
            USAGE_INSTRUCTIONS,
        ]
    )

    assert not is_valid_orientation_brief(malformed)


@pytest.mark.parametrize("indent", ["", " ", "  ", "   "])
def test_shared_markdown_grammar_accepts_structural_indentation(indent: str) -> None:
    brief = "\n".join(
        [
            f"{indent}````python",
            "## fenced pseudo-heading",
            f"{indent}`````",
            *(f"{indent}## {heading}" for heading in HEADINGS),
            USAGE_INSTRUCTIONS,
        ]
    )
    assert is_valid_orientation_brief(brief)


def test_shared_markdown_grammar_treats_four_space_constructs_as_code() -> None:
    brief = "\n".join(
        [
            *(f"    ## {heading}" for heading in HEADINGS),
            USAGE_INSTRUCTIONS,
        ]
    )
    assert not is_valid_orientation_brief(brief)


@pytest.mark.parametrize("closer", ["~~~", "```"])
def test_shared_markdown_grammar_rejects_wrong_or_short_fence_closer(closer: str) -> None:
    brief = "\n".join(
        [
            "````python",
            "inside",
            closer,
            *(f"## {heading}" for heading in HEADINGS),
            USAGE_INSTRUCTIONS,
        ]
    )
    assert not is_valid_orientation_brief(brief)


def test_fresh_injected_context_cap_minus_one_is_preserved_with_exact_metadata() -> None:
    original = _valid_brief_at_estimate(1999)

    result = finalize_injected_context(original)

    assert result == {"brief": original, "estimated_tokens": 1999, "truncated": False}
    assert is_valid_injected_context(result["brief"])


def test_fresh_injected_context_at_cap_is_preserved_with_exact_metadata() -> None:
    original = _valid_brief_at_estimate(2000)

    result = finalize_injected_context(original)

    assert result == {"brief": original, "estimated_tokens": 2000, "truncated": False}
    assert is_valid_injected_context(result["brief"])


def test_fresh_injected_context_cap_plus_one_is_independently_truncated() -> None:
    original = _valid_brief_at_estimate(2001)

    result = finalize_injected_context(original)

    assert result["estimated_tokens"] == estimated_tokens(result["brief"]) == 2000
    assert result["truncated"] is True
    assert result["brief"] != original
    assert is_valid_injected_context(result["brief"])
