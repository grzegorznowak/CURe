from __future__ import annotations

from importlib import resources

import pytest

import cure
from cure_flows import render_prompt

# Only multipass synth template contains $PRIOR_CONTEXT.
# Singlepass templates (normal + big) intentionally exclude it —
# context arrives via a separate two-pass LLM call.
TEMPLATES = [
    "mrereview_gh_local_big_synth.md",
    "mrereview_gh_local_big_resume_synth.md",
]

# Plan and step templates intentionally exclude $PRIOR_CONTEXT —
# they are independent review passes.
NO_PRIOR_TEMPLATES = [
    "mrereview_gh_local.md",
    "mrereview_gh_local_big.md",
    "mrereview_gh_local_big_plan.md",
    "mrereview_gh_local_big_step.md",
]


def _render(template_text: str, prior_context: str) -> str:
    return render_prompt(
        template_text,
        base_ref_for_review="cure_base__main",
        pr_url="https://github.com/acme/rocket/pull/7",
        pr_number=7,
        gh_host="github.com",
        gh_owner="acme",
        gh_repo_name="rocket",
        gh_repo="acme/rocket",
        agent_desc="",
        head_ref="HEAD",
        extra_vars={
            "PRIOR_CONTEXT": prior_context,
            "REVIEW_INTELLIGENCE_GUIDANCE": "guidance",
            "PR_CONTEXT_PATH": "/tmp/pr_context.json",
            "VERBOSE_FINDING_MODE_GUIDANCE": "",
            "REVIEW_CITATION_CONTRACT": "citations",
            "STEP_CITATION_CONTRACT": "step citations",
            "SYNTH_CITATION_CONTRACT": "synth citations",
            "COD_HYPOTHESIS_LEDGER_PLAN_GUIDANCE": "",
            "COD_HYPOTHESIS_LEDGER_STEP_GUIDANCE": "",
            "COD_HYPOTHESIS_LEDGER_SYNTH_GUIDANCE": "",
            "MAX_STEPS": "3",
            "PLAN_JSON_PATH": "/tmp/plan.json",
            "STEP_ID": "01",
            "STEP_TITLE": "Step",
            "STEP_FOCUS": "Focus",
            "STEP_OUTPUT_PATHS": "- /tmp/step.md",
            "GROUNDING_SKIPPED_STEPS": "- None.",
        },
    )


def test_prior_context_token_is_in_all_builtin_review_templates() -> None:
    for name in TEMPLATES:
        text = resources.files("prompts").joinpath(name).read_text(encoding="utf-8")
        assert "$PRIOR_CONTEXT" in text, name


def test_delivery_prompts_label_orientation_as_selected_pr_remote_discussion() -> None:
    captured: list[str] = []
    cure._reconcile_prior_context(
        draft_review="draft",
        orientation_brief="brief",
        run_llm=lambda prompt: captured.append(prompt) or "review",
    )
    prompts = captured + [
        resources.files("prompts").joinpath(name).read_text(encoding="utf-8")
        for name in TEMPLATES
    ]

    for prompt in prompts:
        assert "selected pr remote discussion" in prompt.lower()
        assert "past cure reviews" not in prompt.lower()


def test_failure_capable_prior_context_is_inserted_opaquely() -> None:
    former_marker = "__CURE_OPAQUE_PRIOR_CONTEXT_7F3A9C__"
    sentinel = (
        "keep:$PRIOR_CONTEXT|$OTHER|${OTHER}|$PLAN_JSON_PATH|${PLAN_JSON_PATH}|"
        f"$AGENT_DESC|{former_marker}"
    )
    template = resources.files("prompts").joinpath("mrereview_gh_local_big_synth.md").read_text(encoding="utf-8")

    rendered = cure._render_synth_prompt_with_prior_context(
        template,
        prior_context=sentinel,
        base_ref_for_review="cure_base__main",
        pr_url="https://github.com/acme/rocket/pull/7",
        pr_number=7,
        gh_host="github.com",
        gh_owner="acme",
        gh_repo_name="rocket",
        gh_repo="acme/rocket",
        agent_desc=f"agent:{former_marker}",
        head_ref="HEAD",
        extra_vars={"PLAN_JSON_PATH": f"/tmp/{former_marker}/plan.json"},
    )

    assert sentinel in rendered
    assert rendered.count(sentinel) == 1
    assert f"/tmp/{former_marker}/plan.json" in rendered

    rendered_with_agent = cure._render_synth_prompt_with_prior_context(
        "$PRIOR_CONTEXT\nagent=$AGENT_DESC plan=$PLAN_JSON_PATH",
        prior_context=sentinel,
        base_ref_for_review="cure_base__main",
        pr_url="https://github.com/acme/rocket/pull/7",
        pr_number=7,
        gh_host="github.com",
        gh_owner="acme",
        gh_repo_name="rocket",
        gh_repo="acme/rocket",
        agent_desc=f"agent:{former_marker}",
        extra_vars={"PLAN_JSON_PATH": f"/tmp/{former_marker}/plan.json"},
    )
    assert f"agent:{former_marker}" in rendered_with_agent
    assert f"/tmp/{former_marker}/plan.json" in rendered_with_agent


@pytest.mark.parametrize("template", ["no owned token", "$PRIOR_CONTEXT and $PRIOR_CONTEXT"])
def test_synth_insertion_requires_exactly_one_owned_token(template: str) -> None:
    with pytest.raises(cure.ReviewflowError, match="exactly one"):
        cure._render_synth_prompt_with_prior_context(
            template,
            prior_context="brief",
            base_ref_for_review="cure_base__main",
            pr_url="https://github.com/acme/rocket/pull/7",
            pr_number=7,
            gh_host="github.com",
            gh_owner="acme",
            gh_repo_name="rocket",
            gh_repo="acme/rocket",
            agent_desc="AGENT",
        )


def test_prior_context_renders_with_brief_and_empty_string_without_raw_token() -> None:
    for name in TEMPLATES:
        text = resources.files("prompts").joinpath(name).read_text(encoding="utf-8")
        rendered = _render(text, "brief body")
        assert "brief body" in rendered, name
        assert "$PRIOR_CONTEXT" not in rendered, name
        empty_rendered = _render(text, "")
        assert "$PRIOR_CONTEXT" not in empty_rendered, name

    for name in NO_PRIOR_TEMPLATES:
        text = resources.files("prompts").joinpath(name).read_text(encoding="utf-8")
        assert "$PRIOR_CONTEXT" not in text, f"{name} should not contain $PRIOR_CONTEXT"
