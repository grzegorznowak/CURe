from __future__ import annotations

from importlib import resources

from cure_flows import render_prompt

TEMPLATES = [
    "mrereview_gh_local.md",
    "mrereview_gh_local_big.md",
    "mrereview_gh_local_big_synth.md",
]

# Plan and step templates intentionally exclude $PRIOR_CONTEXT —
# they are independent review passes. Context is reconciled in synth.
NO_PRIOR_TEMPLATES = [
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


def test_prior_context_renders_with_brief_and_empty_string_without_raw_token() -> None:
    for name in TEMPLATES:
        text = resources.files("prompts").joinpath(name).read_text(encoding="utf-8")
        rendered = _render(text, "brief body")
        assert "brief body" in rendered, name
        assert "$PRIOR_CONTEXT" not in rendered, name
        empty_rendered = _render(text, "")
        assert "$PRIOR_CONTEXT" not in empty_rendered, name
