from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

import cure
import cure_pr_context
from cure_pr_context.corpus import estimated_tokens
from cure_pr_context.orient import finalize_orientation_brief
from cure_pr_context.runtime import (
    apply_build_metadata,
    atomic_write_persisted_context,
    classify_fresh,
    metadata_for_resume,
    preserve_origin,
    read_persisted_context,
)
from cure_errors import ReviewflowError
from run import ReviewflowSubprocessError


def _subprocess_failure(message: str = "provider transport failed") -> ReviewflowSubprocessError:
    return ReviewflowSubprocessError(
        cmd=["provider"], cwd=None, exit_code=1, stdout="", stderr=message
    )


def _synth_stage_kwargs(
    *, progress: cure.SessionProgress, root: Path, prompt: str = "prompt"
) -> dict[str, object]:
    return {
        "progress": progress,
        "repo_dir": root / "repo",
        "work_dir": root / "work",
        "session_id": "session-boundary",
        "review_md_path": root / "review.md",
        "synth_prompt": prompt,
        "synth_llm": {
            "resolved": {"provider": "openai", "model": "gpt-5"},
            "resolution_meta": {"resolved": {}},
            "meta": {"provider": "openai"},
        },
        "synth_runtime_policy": {"codex_config_overrides": []},
        "synth_step_outputs": [],
        "grounding_mode": "strict",
        "env": {},
        "stream": False,
        "add_dirs": [],
        "codex_meta": None,
        "ui_enabled": False,
        "prompt_template_name": "mrereview_gh_local_big_synth.md",
        "run_kind": "synth",
        "review_stage": "multipass_synth",
        "stage_label": "multipass synth",
        "failure_message": "synth failed",
        "multipass_cfg": {},
    }


def _args(**overrides: object) -> argparse.Namespace:
    values = {"pr_context": None, "prompt": None, "prompt_file": None, "prompt_profile": "auto"}
    values.update(overrides)
    return argparse.Namespace(**values)


def test_parser_pr_context_is_paired_and_defaults_off() -> None:
    parser = cure.build_parser()
    base = ["pr", "https://github.com/acme/repo/pull/1"]
    assert parser.parse_args(base).pr_context is None
    assert parser.parse_args([*base, "--pr-context"]).pr_context is True
    assert parser.parse_args([*base, "--no-pr-context"]).pr_context is False
    with pytest.raises(SystemExit):
        parser.parse_args([*base, "--pr-context", "--no-pr-context"])


@pytest.mark.parametrize(
    ("args", "reason", "enabled", "eligible", "source"),
    [
        (_args(), "disabled_default", False, True, "default"),
        (_args(pr_context=False), "disabled_cli", False, True, "cli_explicit"),
        (_args(pr_context=True, prompt="custom"), "custom_prompt", True, False, "cli_explicit"),
        (_args(pr_context=True, prompt_file="custom.md"), "custom_prompt", True, False, "cli_explicit"),
        (_args(pr_context=True, prompt_profile="default"), "unsupported_profile", True, False, "cli_explicit"),
    ],
)
def test_pr_context_eligibility_pre_io_metadata(
    args: argparse.Namespace, reason: str, enabled: bool, eligible: bool, source: str
) -> None:
    meta = classify_fresh(args)
    assert (meta["reason"], meta["enabled"], meta["eligible"], meta["enablement_source"]) == (
        reason, enabled, eligible, source
    )
    assert meta["outcome"] == "bypassed" and meta["context_mode"] == "off"


def _valid_brief() -> str:
    return finalize_orientation_brief("## Problem areas\n- inspect")[0]


@pytest.mark.parametrize("outcome", [None, "bypassed", "degraded", "other"])
def test_resume_requires_used_origin(tmp_path: Path, outcome: str | None) -> None:
    work = tmp_path / "work"
    work.mkdir()
    (work / "pr_context_orientation.md").write_text(_valid_brief())
    origin = {} if outcome is None else {"outcome": outcome}
    assert read_persisted_context(work, origin) == ("", "resume_without_used_context")


def test_resume_pr_context_reuses_exact_used_valid_brief(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    brief = _valid_brief()
    atomic_write_persisted_context(work / "pr_context_orientation.md", brief)
    assert read_persisted_context(work, {"outcome": "used"}) == (brief, "context_delivered")


def test_resume_pr_context_reuses_exact_crlf_brief(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    brief = _valid_brief().replace("\n", "\r\n")
    atomic_write_persisted_context(work / "pr_context_orientation.md", brief)

    reused, reason = read_persisted_context(work, {"outcome": "used"})

    assert reason == "context_delivered"
    assert reused == brief
    assert (work / "pr_context_orientation.md").read_bytes() == brief.encode("utf-8")


@pytest.mark.parametrize("variant", ["missing", "empty", "invalid", "over_cap", "directory", "non_utf8"])
def test_resume_rejects_invalid_used_brief(tmp_path: Path, variant: str) -> None:
    work = tmp_path / "work"
    work.mkdir()
    path = work / "pr_context_orientation.md"
    if variant == "empty":
        path.write_text("")
    elif variant == "invalid":
        path.write_text("not finalized")
    elif variant == "over_cap":
        path.write_text(_valid_brief() + "x" * 8001)
    elif variant == "directory":
        path.mkdir()
    elif variant == "non_utf8":
        path.write_bytes(b"\xff")
    assert read_persisted_context(work, {"outcome": "used"}) == ("", "resume_invalid_context")


def test_opaque_insertion_preserves_context_bytes() -> None:
    sentinel = "keep:$PRIOR_CONTEXT|$OTHER|${OTHER}|$PLAN_JSON_PATH|$AGENT_DESC"
    rendered = cure._render_synth_prompt_with_prior_context(
        "before $PRIOR_CONTEXT after $AGENT_DESC",
        prior_context=sentinel,
        base_ref_for_review="base", pr_url="url", pr_number=1, gh_host="github.com",
        gh_owner="acme", gh_repo_name="repo", gh_repo="acme/repo", agent_desc="agent",
    )
    assert sentinel in rendered and rendered.count(sentinel) == 1
    assert "$PRIOR_CONTEXT" in rendered  # only the opaque context's own bytes remain


@pytest.mark.parametrize("reason", ["no_remote_context", "no_selected_context"])
def test_pr_context_no_remote_or_no_selected_metadata_is_context_free(reason: str) -> None:
    meta = classify_fresh(_args(pr_context=True))
    apply_build_metadata(meta, {"meta": {"reason": reason}}, "")
    assert (meta["outcome"], meta["reason"], meta["context_mode"]) == (
        "bypassed", reason, "off"
    )


def test_resume_no_delivery_pr_context_origin_copy_is_deep_equal_and_independent() -> None:
    origin = {
        "outcome": "used",
        "sentinel": {"nested": [1, {"unchanged": True}]},
        "provider_usage": {"delivery_input_tokens": None},
    }
    preserved = preserve_origin(origin)
    assert preserved == origin
    assert preserved is not origin
    assert preserved["sentinel"] is not origin["sentinel"]


@pytest.mark.parametrize(
    ("route", "actual", "expected"),
    [
        (
            "fresh",
            classify_fresh(_args(pr_context=True)),
            {
                "outcome": "used", "reason": "context_delivered", "enabled": True,
                "enablement_source": "cli_explicit", "eligible": True,
                "counts": {"fetched": 0, "normalized": 0, "selected": 0, "omitted": 0, "truncated_events": 0},
                "estimated_tokens": {"selected_events": 0, "orientation_prompt": 0, "orientation_output": 0, "injected": 0},
                "provider_usage": {"orientation_input_tokens": None, "orientation_output_tokens": None, "delivery_input_tokens": None, "delivery_output_tokens": None, "fallback_input_tokens": None, "fallback_output_tokens": None},
                "truncation": {"event_body": False, "event_count": False, "prompt_budget": False, "orientation_output": False, "injected_context": False},
                "latency_ms": {"fetch": 0, "selection": 0, "orientation": 0, "delivery": 0, "total_enrichment": 0},
                "persistence": {"discussion_artifact": "not_attempted", "orientation_artifact": "not_attempted", "meta_artifact": "not_attempted", "warning": None},
                "context_mode": "off",
            },
        ),
        (
            "resume",
            metadata_for_resume({}, brief="", reason="resume_without_used_context"),
            {
                "outcome": "bypassed", "reason": "resume_without_used_context", "enabled": False,
                "enablement_source": "default", "eligible": True,
                "counts": {"fetched": 0, "normalized": 0, "selected": 0, "omitted": 0, "truncated_events": 0},
                "estimated_tokens": {"selected_events": 0, "orientation_prompt": 0, "orientation_output": 0, "injected": 0},
                "provider_usage": {"orientation_input_tokens": None, "orientation_output_tokens": None, "delivery_input_tokens": None, "delivery_output_tokens": None, "fallback_input_tokens": None, "fallback_output_tokens": None},
                "truncation": {"event_body": False, "event_count": False, "prompt_budget": False, "orientation_output": False, "injected_context": False},
                "latency_ms": {"fetch": 0, "selection": 0, "orientation": 0, "delivery": 0, "total_enrichment": 0},
                "persistence": {"discussion_artifact": "not_attempted", "orientation_artifact": "not_attempted", "meta_artifact": "not_attempted", "warning": None},
                "context_mode": "off",
            },
        ),
    ],
)
def test_tap18_pr_context_meta_d14_d18_complete_route_dictionary(
    route: str, actual: dict[str, object], expected: dict[str, object]
) -> None:
    assert route in {"fresh", "resume"}
    assert actual == expected


def test_metadata_schema_has_no_finding_identity_primitives() -> None:
    meta = classify_fresh(_args())
    encoded = json.dumps(meta, sort_keys=True)
    assert "finding_id" not in encoded and "disposition" not in encoded


def test_resume_metadata_inherits_only_sanitized_used_acquisition() -> None:
    origin = classify_fresh(_args(pr_context=True))
    origin["counts"].update(fetched=3, normalized=2, selected=-1, omitted=True)
    origin["estimated_tokens"].update(selected_events=8, orientation_prompt="bad", injected=999)
    origin["provider_usage"].update(orientation_input_tokens=7, delivery_input_tokens=99)
    origin["latency_ms"].update(fetch=4, selection=-2, delivery=88, total_enrichment=77)
    origin["persistence"].update(discussion_artifact="written", orientation_artifact="bogus", meta_artifact="written")

    meta = metadata_for_resume(origin, brief=_valid_brief(), reason="context_delivered")

    assert meta["counts"] == {"fetched": 3, "normalized": 2, "selected": 0, "omitted": 0, "truncated_events": 0}
    assert meta["estimated_tokens"]["selected_events"] == 8
    assert meta["estimated_tokens"]["orientation_prompt"] == 0
    assert meta["estimated_tokens"]["injected"] > 0
    assert meta["provider_usage"]["orientation_input_tokens"] == 7
    assert meta["provider_usage"]["delivery_input_tokens"] is None
    assert meta["latency_ms"]["fetch"] == 4
    assert meta["latency_ms"]["selection"] == 0
    assert meta["latency_ms"]["delivery"] == 0
    assert meta["latency_ms"]["total_enrichment"] == 0
    assert meta["persistence"]["discussion_artifact"] == "written"
    assert meta["persistence"]["orientation_artifact"] == "not_attempted"
    assert meta["persistence"]["meta_artifact"] == "not_attempted"


@pytest.mark.parametrize(
    "failure",
    [ReviewflowError("configuration failed"), OSError("output write failed")],
)
def test_pr_context_does_not_swallow_multipass_synth_provider_adjacent_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: Exception
) -> None:
    progress = cure.SessionProgress(tmp_path / "meta.json", quiet=True)
    progress.init({"session_id": "session-boundary", "multipass": {"runs": []}})
    monkeypatch.setattr(
        cure, "run_llm_exec", lambda **_kwargs: (_ for _ in ()).throw(failure)
    )

    with pytest.raises(type(failure), match=str(failure)) as raised:
        cure._execute_multipass_synth_stage(**_synth_stage_kwargs(progress=progress, root=tmp_path))

    assert raised.value is failure


def test_pr_context_synthesis_fail_open_multipass_transport_is_only_translated_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    failure = _subprocess_failure()
    progress = cure.SessionProgress(tmp_path / "meta.json", quiet=True)
    progress.init({"session_id": "session-boundary", "multipass": {"runs": []}})
    monkeypatch.setattr(
        cure, "run_llm_exec", lambda **_kwargs: (_ for _ in ()).throw(failure)
    )

    with pytest.raises(cure._PrContextSynthesisExecutionFailure) as raised:
        cure._execute_multipass_synth_stage(**_synth_stage_kwargs(progress=progress, root=tmp_path))

    assert raised.value.cause is failure


def test_pr_context_synthesis_fail_open_clears_stale_usage_before_each_provider_attempt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stale_usage = {"input_tokens": 999, "output_tokens": 888}
    fallback_usage = {"input_tokens": 7, "output_tokens": 3}
    progress = cure.SessionProgress(tmp_path / "meta.json", quiet=True)
    progress.init(
        {
            "session_id": "session-boundary",
            "multipass": {"runs": [{"kind": "synth", "usage": stale_usage}]},
            "llm": {},
            "codex": {},
        }
    )
    attempts = 0

    def run_llm_exec(**kwargs: object) -> cure.LlmRunResult:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _subprocess_failure()
        Path(str(kwargs["output_path"])).write_text("fallback review", encoding="utf-8")
        return cure.LlmRunResult(adapter_meta={"usage": fallback_usage})

    monkeypatch.setattr(cure, "run_llm_exec", run_llm_exec)
    monkeypatch.setattr(cure, "_enforce_chunkhound_tool_proof", lambda **_kwargs: None)
    monkeypatch.setattr(
        cure,
        "_validate_or_reuse_synth_artifact",
        lambda **_kwargs: (True, {"valid": True, "errors": []}),
    )
    meta = classify_fresh(_args(pr_context=True))

    result = cure._execute_pr_context_synth_with_fallback(
        prior_context="context",
        context_meta=meta,
        render_synth=lambda context: f"prompt:{context}",
        execute_synth=lambda prompt: cure._execute_multipass_synth_stage(
            **_synth_stage_kwargs(progress=progress, root=tmp_path, prompt=prompt)
        ),
        retryable_failure=cure._PrContextSynthesisExecutionFailure,
        flush=progress.flush,
        warn=lambda _message: None,
        usage=lambda: cure._multipass_run_usage(progress.meta, kind="synth"),
        clock=iter([1.0, 1.1, 1.3]).__next__,
    )

    assert result is None
    assert attempts == 2
    assert meta["provider_usage"]["delivery_input_tokens"] is None
    assert meta["provider_usage"]["delivery_output_tokens"] is None
    assert meta["provider_usage"]["fallback_input_tokens"] == 7
    assert meta["provider_usage"]["fallback_output_tokens"] == 3
    assert progress.meta["multipass"]["runs"][0]["usage"] == {
        **fallback_usage,
        "total_tokens": 10,
    }


@pytest.mark.parametrize(
    "method_name",
    [
        "test_tap17_tap18_pr_context_pr_flow_multipass_fresh_success_has_exact_present_usage_and_route_latency",
        "test_tap17_tap18_pr_context_pr_flow_multipass_fresh_fallback_has_exact_absent_usage_and_route_latency",
        "test_tap17_tap18_pr_context_pr_flow_multipass_fresh_synthesis_fallback_fatal_captures_two_executor_calls",
    ],
)
def test_tap17_tap18_pr_context_synthesis_meta_fresh_multipass_canonical_routes(
    method_name: str,
) -> None:
    from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

    case = CodexToolProofFlowTests(methodName=method_name)
    getattr(case, method_name)()


@pytest.mark.parametrize(
    "method_name",
    [
        "test_tap14_tap18_pr_context_pr_flow_stage_failures_fail_open_with_exact_authority_and_final_mirror",
        "test_tap18_pr_context_pr_flow_final_mirror_failure_preserves_completed_route_without_rerun",
        "test_tap18_pr_context_pr_flow_no_selected_context_bypasses_orientation_and_completes_ordinary_route",
    ],
)
def test_tap18_pr_context_meta_no_selected_artifact_genuine_route_owners(
    method_name: str,
) -> None:
    from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

    case = CodexToolProofFlowTests(methodName=method_name)
    getattr(case, method_name)()


def test_tap14_pr_context_eligibility_no_remote_genuine_route_owners() -> None:
    from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

    method_name = "test_tap14_pr_context_eligibility_and_no_remote_genuine_pre_io_routes"
    case = CodexToolProofFlowTests(methodName=method_name)
    getattr(case, method_name)()


def test_pr_context_reconcile_fail_open_real_route_only_for_subprocess_transport() -> None:
    from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

    CodexToolProofFlowTests(
        methodName=(
            "test_pr_flow_singlepass_pr_context_reconcile_fail_open_retains_blind_draft_only_for_execution_failure"
        )
    ).test_pr_flow_singlepass_pr_context_reconcile_fail_open_retains_blind_draft_only_for_execution_failure()


def test_tap18_tap19_pr_context_meta_resume_no_delivery_same_head_genuine_route() -> None:
    from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

    method_name = (
        "test_tap18_tap19_resume_flow_from_synth_prior_context_same_head_d17_completed_latest_head_is_exact_no_delivery_state"
    )
    case = CodexToolProofFlowTests(methodName=method_name)
    getattr(case, method_name)()


def test_pr_context_does_not_swallow_reconcile_nontransport_failures_real_route() -> None:
    from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

    CodexToolProofFlowTests(
        methodName=(
            "test_pr_flow_singlepass_pr_context_does_not_swallow_reconcile_nontransport_failures"
        )
    ).test_pr_flow_singlepass_pr_context_does_not_swallow_reconcile_nontransport_failures()


def _run_tap22_genuine_route_owner(method_name: str) -> None:
    from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

    case = CodexToolProofFlowTests(methodName=method_name)
    getattr(case, method_name)()


def test_pr_context_does_not_swallow_build_or_orientation_file_faults_genuine_route() -> None:
    _run_tap22_genuine_route_owner(
        "test_pr_flow_pr_context_does_not_swallow_build_or_orientation_file_faults"
    )


def test_pr_context_does_not_swallow_checkout_failure_genuine_route() -> None:
    _run_tap22_genuine_route_owner("test_pr_flow_pr_context_does_not_swallow_checkout_failure")


def test_pr_context_does_not_swallow_config_failure_genuine_route() -> None:
    _run_tap22_genuine_route_owner("test_pr_flow_pr_context_does_not_swallow_config_failure")


def test_pr_context_does_not_swallow_keyboard_interrupt_cancellation_genuine_route() -> None:
    _run_tap22_genuine_route_owner("test_pr_flow_pr_context_does_not_swallow_keyboard_interrupt_cancellation")


def test_pr_context_does_not_swallow_singlepass_draft_failure_genuine_route() -> None:
    _run_tap22_genuine_route_owner("test_pr_flow_pr_context_does_not_swallow_singlepass_draft_failure")


def test_pr_context_does_not_swallow_multipass_plan_failure_genuine_route() -> None:
    _run_tap22_genuine_route_owner("test_pr_flow_pr_context_does_not_swallow_multipass_plan_failure")


def test_pr_context_does_not_swallow_multipass_step_failure_genuine_route() -> None:
    _run_tap22_genuine_route_owner("test_pr_flow_pr_context_does_not_swallow_multipass_step_failure")


def test_pr_context_does_not_swallow_acceptance_failure_genuine_route() -> None:
    _run_tap22_genuine_route_owner("test_pr_flow_pr_context_does_not_swallow_acceptance_failure")


def test_pr_context_does_not_swallow_final_session_flush_failure_genuine_route() -> None:
    _run_tap22_genuine_route_owner("test_pr_flow_pr_context_does_not_swallow_final_session_flush_failure")


def test_pr_context_does_not_swallow_posting_structurally_absent_genuine_route() -> None:
    _run_tap22_genuine_route_owner(
        "test_pr_flow_pr_context_does_not_swallow_posting_because_posting_is_structurally_absent"
    )


def test_pr_context_synthesis_fail_open_retries_once_and_flushes_before_retry() -> None:
    meta = classify_fresh(_args(pr_context=True))
    rendered: list[str] = []
    attempts: list[str] = []
    flush_states: list[tuple[str, str]] = []
    observed_usage = iter([
        {"input_tokens": 11},
        {"input_tokens": 7, "output_tokens": 3},
    ])

    def render(context: str) -> str:
        rendered.append(context)
        return f"prompt:{context}"

    def execute(prompt: str) -> str:
        attempts.append(prompt)
        if len(attempts) == 1:
            raise RuntimeError("context failed")
        return "resume-command"

    result = cure._execute_pr_context_synth_with_fallback(
        prior_context="brief",
        context_meta=meta,
        render_synth=render,
        execute_synth=execute,
        flush=lambda: flush_states.append((meta["reason"], meta["context_mode"])),
        warn=lambda _message: None,
        usage=observed_usage.__next__,
        clock=iter([1.0, 1.1, 1.3]).__next__,
    )

    assert result == "resume-command"
    assert rendered == ["brief", ""]
    assert attempts == ["prompt:brief", "prompt:"]
    assert flush_states[0] == ("context_synthesis_failed", "off")
    assert meta["outcome"] == "degraded"
    assert meta["reason"] == "context_synthesis_failed"
    assert meta["context_mode"] == "off"
    assert meta["latency_ms"]["delivery"] == 300
    assert meta["provider_usage"] == {
        "orientation_input_tokens": None,
        "orientation_output_tokens": None,
        "delivery_input_tokens": 11,
        "delivery_output_tokens": None,
        "fallback_input_tokens": 7,
        "fallback_output_tokens": 3,
    }


def test_tap18_pr_context_synthesis_retry_failure_flushes_available_fallback_telemetry() -> None:
    meta = classify_fresh(_args(pr_context=True))
    attempts: list[str] = []
    flushed: list[dict[str, object]] = []

    def execute(prompt: str) -> str:
        attempts.append(prompt)
        raise RuntimeError(prompt)

    observed_usage = iter([
        {"input_tokens": 13, "output_tokens": 2},
        {"input_tokens": 5},
    ])
    with pytest.raises(RuntimeError, match="prompt:"):
        cure._execute_pr_context_synth_with_fallback(
            prior_context="brief",
            context_meta=meta,
            render_synth=lambda context: f"prompt:{context}",
            execute_synth=execute,
            flush=lambda: flushed.append(json.loads(json.dumps(meta))),
            warn=lambda _message: None,
            usage=observed_usage.__next__,
            clock=iter([1.0, 1.1, 1.25]).__next__,
        )
    assert attempts == ["prompt:brief", "prompt:"]
    assert meta["reason"] == "context_synthesis_failed"
    assert meta["latency_ms"]["delivery"] == 250
    assert meta["provider_usage"]["delivery_input_tokens"] == 13
    assert meta["provider_usage"]["delivery_output_tokens"] == 2
    assert meta["provider_usage"]["fallback_input_tokens"] == 5
    assert meta["provider_usage"]["fallback_output_tokens"] is None
    assert flushed[-1] == meta
    assert flushed[-1]["provider_usage"]["fallback_input_tokens"] == 5  # type: ignore[index]


@pytest.mark.parametrize("path", ["regular_resume", "incremental_resume"])
def test_tap18_tap19_tap20_resume_pr_context_empty_delivery_records_validator_and_provider_telemetry(
    path: str,
) -> None:
    attempts: list[str] = []
    meta = metadata_for_resume({}, brief="", reason="resume_without_used_context")
    usage = {"input_tokens": 9, "output_tokens": 4}

    result = cure._execute_pr_context_synth_with_fallback(
        prior_context="",
        context_meta=meta,
        render_synth=lambda context: f"{path}:{context}",
        execute_synth=lambda prompt: attempts.append(prompt) or "ordinary-result",
        flush=lambda: None,
        warn=lambda _message: None,
        usage=lambda: usage,
        clock=iter([10.2, 10.6]).__next__,
        delivery_entered=True,
        total_started_at=10.0,
    )

    assert result == "ordinary-result"
    assert attempts == [f"{path}:"]
    assert (meta["outcome"], meta["reason"], meta["context_mode"]) == (
        "bypassed", "resume_without_used_context", "off"
    )
    assert meta["provider_usage"]["delivery_input_tokens"] == 9
    assert meta["provider_usage"]["delivery_output_tokens"] == 4
    assert meta["provider_usage"]["fallback_input_tokens"] is None
    assert meta["latency_ms"]["delivery"] == 400
    assert meta["latency_ms"]["total_enrichment"] == 599


def test_tap17_pr_context_initial_and_fallback_transport_failures_preserve_subprocess_semantics() -> None:
    initial = _subprocess_failure("initial ordinary synth failed")
    with pytest.raises(ReviewflowSubprocessError) as initial_raised:
        cure._execute_pr_context_synth_with_fallback(
            prior_context="",
            context_meta=classify_fresh(_args()),
            render_synth=lambda context: f"prompt:{context}",
            execute_synth=lambda _prompt: (_ for _ in ()).throw(
                cure._PrContextSynthesisExecutionFailure(initial)
            ),
            flush=lambda: None,
            warn=lambda _message: None,
        )
    assert initial_raised.value is initial

    fallback = _subprocess_failure("empty fallback synth failed")
    calls = 0

    def execute(_prompt: str) -> None:
        nonlocal calls
        calls += 1
        cause = _subprocess_failure("context synth failed") if calls == 1 else fallback
        raise cure._PrContextSynthesisExecutionFailure(cause)

    with pytest.raises(ReviewflowSubprocessError) as fallback_raised:
        cure._execute_pr_context_synth_with_fallback(
            prior_context="brief",
            context_meta=classify_fresh(_args(pr_context=True)),
            render_synth=lambda context: f"prompt:{context}",
            execute_synth=execute,
            flush=lambda: None,
            warn=lambda _message: None,
            retryable_failure=cure._PrContextSynthesisExecutionFailure,
            clock=iter([1.0, 1.1, 1.2]).__next__,
        )
    assert fallback_raised.value is fallback
    assert calls == 2


def test_tap18_empty_prior_context_synth_is_not_pr_context_delivery_telemetry() -> None:
    attempts: list[str] = []
    meta = classify_fresh(_args())
    before = json.loads(json.dumps(meta))

    def clock() -> float:
        raise AssertionError("PR-context clock must not run")

    result = cure._execute_pr_context_synth_with_fallback(
        prior_context="",
        context_meta=meta,
        render_synth=lambda context: f"prompt:{context}",
        execute_synth=lambda prompt: attempts.append(prompt) or "ordinary-result",
        flush=lambda: (_ for _ in ()).throw(AssertionError("metadata must not flush")),
        warn=lambda _message: None,
        usage=lambda: (_ for _ in ()).throw(AssertionError("usage must not be observed")),
        clock=clock,
    )

    assert result == "ordinary-result"
    assert attempts == ["prompt:"]
    assert meta == before


@pytest.mark.parametrize(
    "failure",
    [ReviewflowError("orientation control failed"), OSError("orientation output failed")],
)
def test_pr_context_does_not_swallow_orientation_control_or_output_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: Exception
) -> None:
    discussion = [{"kind": "issue_comment", "event_id": "1", "body": "inspect"}]
    monkeypatch.setattr(
        cure_pr_context,
        "select_orientation_events",
        lambda events, *, pr_stats: {
            "selected_discussion": events,
            "meta": {"selected": 1, "omitted": 0, "truncated_events": 0},
        },
    )

    with pytest.raises(type(failure), match=str(failure)) as raised:
        cure.build_pr_context(
            pr=argparse.Namespace(owner="acme", repo="repo", number=1),
            work_dir=tmp_path,
            pr_stats={},
            gh_fetch=lambda path: discussion if path.endswith("issues/1/comments") else [],
            run_llm=lambda _prompt: (_ for _ in ()).throw(failure),
        )

    assert raised.value is failure


def test_pr_context_does_not_swallow_template_render_failure() -> None:
    attempts: list[str] = []

    with pytest.raises(RuntimeError, match="template exploded"):
        cure._execute_pr_context_synth_with_fallback(
            prior_context="brief",
            context_meta=classify_fresh(_args(pr_context=True)),
            render_synth=lambda _context: (_ for _ in ()).throw(RuntimeError("template exploded")),
            execute_synth=lambda prompt: attempts.append(prompt),
            flush=lambda: None,
            warn=lambda _message: None,
            clock=iter([1.0]).__next__,
        )

    assert attempts == []


def test_pr_context_does_not_swallow_core_metadata_failure() -> None:
    class SynthesisExecutionFailure(RuntimeError):
        pass

    attempts: list[str] = []
    with pytest.raises(ValueError, match="metadata exploded"):
        cure._execute_pr_context_synth_with_fallback(
            prior_context="brief",
            context_meta=classify_fresh(_args(pr_context=True)),
            render_synth=lambda context: f"prompt:{context}",
            execute_synth=lambda prompt: attempts.append(prompt) or (_ for _ in ()).throw(
                ValueError("metadata exploded")
            ),
            retryable_failure=SynthesisExecutionFailure,
            flush=lambda: None,
            warn=lambda _message: None,
            clock=iter([1.0]).__next__,
        )

    assert attempts == ["prompt:brief"]


def test_pr_context_does_not_swallow_core_metadata_mirror_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    meta = classify_fresh(_args(pr_context=True))

    flushes = 0

    class Progress:
        def flush(self) -> None:
            nonlocal flushes
            flushes += 1

    monkeypatch.setattr(
        cure,
        "atomic_write_metadata",
        lambda _path, _payload: (_ for _ in ()).throw(ValueError("metadata exploded")),
    )

    with pytest.raises(ValueError, match="metadata exploded"):
        cure._mirror_pr_context_metadata(
            progress=Progress(),  # type: ignore[arg-type]
            work_dir=tmp_path,
            context_meta=meta,
            quiet=True,
        )
    assert flushes == 1


@pytest.mark.parametrize("mirror_fails", [False, True])
def test_tap18_canonical_metadata_flush_precedes_equal_final_mirror(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mirror_fails: bool
) -> None:
    meta = classify_fresh(_args(pr_context=True))
    meta.update(outcome="used", reason="context_delivered", context_mode="on")
    events: list[tuple[str, dict[str, object]]] = []

    class Progress:
        def flush(self) -> None:
            events.append(("canonical", json.loads(json.dumps(meta))))

    def write_mirror(_path: Path, payload: dict[str, object]) -> None:
        events.append(("mirror", json.loads(json.dumps(payload))))
        if mirror_fails:
            raise OSError("disk full")

    monkeypatch.setattr(cure, "atomic_write_metadata", write_mirror)

    cure._mirror_pr_context_metadata(
        progress=Progress(),  # type: ignore[arg-type]
        work_dir=tmp_path,
        context_meta=meta,
        quiet=True,
    )

    assert [kind for kind, _payload in events[:2]] == ["canonical", "mirror"]
    assert events[0][1] == events[1][1]
    if mirror_fails:
        assert [kind for kind, _payload in events] == ["canonical", "mirror", "canonical"]
        assert meta["persistence"]["meta_artifact"] == "failed"
        assert meta["persistence"]["warning"] == "meta_artifact_write_failed"
        assert events[-1][1] == meta
    else:
        assert len(events) == 2
        assert meta["persistence"]["meta_artifact"] == "written"
        assert meta["persistence"]["warning"] is None


def test_pr_context_does_not_swallow_process_control_flush_failure() -> None:
    attempts: list[str] = []

    def execute(prompt: str) -> None:
        attempts.append(prompt)
        raise RuntimeError("synthesis execution failed")

    with pytest.raises(RuntimeError, match="flush exploded"):
        cure._execute_pr_context_synth_with_fallback(
            prior_context="brief",
            context_meta=classify_fresh(_args(pr_context=True)),
            render_synth=lambda context: f"prompt:{context}",
            execute_synth=execute,
            flush=lambda: (_ for _ in ()).throw(RuntimeError("flush exploded")),
            warn=lambda _message: None,
            clock=iter([1.0, 1.1]).__next__,
        )

    assert attempts == ["prompt:brief"]


def test_pr_context_metadata_fresh_injection_finalization_fail_open_real_route() -> None:
    from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

    CodexToolProofFlowTests(
        methodName=(
            "test_pr_flow_singlepass_pr_context_fresh_injection_finalization_fail_open_real_route"
        )
    ).test_pr_flow_singlepass_pr_context_fresh_injection_finalization_fail_open_real_route()


def test_pr_context_metadata_fresh_injection_finalization_fail_open_is_orientation_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    meta = classify_fresh(_args(pr_context=True))
    built = {
        "orientation_brief": _valid_brief(),
        "meta": {
            "counts": {
                "fetched": 3,
                "normalized": 3,
                "selected": 2,
                "omitted": 1,
                "truncated_events": 0,
            },
            "selection": {"selected": 2, "omitted": 1, "truncated_events": 0},
            "orientation": {"estimated_tokens": 31, "truncated": False},
            "provider_usage": {"input_tokens": 17},
            "latency_ms": {
                "fetch": 11,
                "selection": 12,
                "orientation": 13,
                "total_enrichment": 36,
            },
        },
    }
    failure = ValueError("fresh injection finalizer failed")
    monkeypatch.setattr(
        cure,
        "finalize_injected_context",
        lambda _brief: (_ for _ in ()).throw(
            cure.InjectedContextFinalizationFailure(failure)
        ),
    )

    with pytest.raises(cure.PrContextStageError) as raised:
        cure._finalize_and_persist_fresh_pr_context(
            work_dir=tmp_path,
            context_meta=meta,
            built=built,
        )

    assert raised.value.stage == "orientation_failed"
    assert raised.value.meta == built["meta"]
    assert not (tmp_path / "pr_context_orientation.md").exists()


def test_fresh_pr_context_independently_finalizes_before_persist_and_delivery(
    tmp_path: Path,
) -> None:
    meta = classify_fresh(_args(pr_context=True))
    built = {
        "orientation_brief": "## Problem areas\n- " + ("x" * 9000),
        "meta": {
            "orientation": {"estimated_tokens": 2255, "truncated": False},
            "latency_ms": {},
        },
    }

    delivered = cure._finalize_and_persist_fresh_pr_context(
        work_dir=tmp_path,
        context_meta=meta,
        built=built,
    )

    assert estimated_tokens(delivered) <= 2000
    assert estimated_tokens(str(built["orientation_brief"])) > 2000
    assert (tmp_path / "pr_context_orientation.md").read_bytes() == delivered.encode("utf-8")
    assert meta["estimated_tokens"]["orientation_output"] == 2255
    assert meta["estimated_tokens"]["injected"] == estimated_tokens(delivered)
    assert meta["truncation"]["orientation_output"] is False
    assert meta["truncation"]["injected_context"] is True
    assert meta["persistence"] == {
        "discussion_artifact": "written",
        "orientation_artifact": "written",
        "meta_artifact": "not_attempted",
        "warning": None,
    }
