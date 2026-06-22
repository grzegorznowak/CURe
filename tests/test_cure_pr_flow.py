from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import cure
import cure_github


def _run_singlepass_pr_flow_with_orientation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    orientation_brief: str,
) -> tuple[list[str], list[str], dict[str, object]]:
    sandbox_root = tmp_path / "sandboxes"
    cache_root = tmp_path / "cache"
    seed = tmp_path / "seed"
    base_cfg = tmp_path / "chunkhound-base.json"
    base_db = tmp_path / "base.chunkhound.db"
    config_path = tmp_path / "reviewflow.toml"
    seed.mkdir(parents=True)
    sandbox_root.mkdir(parents=True)
    cache_root.mkdir(parents=True)
    base_cfg.write_text("{}", encoding="utf-8")
    base_db.write_text("db", encoding="utf-8")
    config_path.write_text("[chunkhound]\n", encoding="utf-8")
    paths = cure.ReviewflowPaths(sandbox_root=sandbox_root, cache_root=cache_root)
    args = cure.build_parser().parse_args(
        [
            "pr",
            "https://github.com/acme/rocket/pull/7",
            "--if-reviewed",
            "new",
            "--ui",
            "off",
            "--quiet",
            "--no-stream",
        ]
    )

    class _Result:
        def __init__(self, stdout: str = "") -> None:
            self.stdout = stdout
            self.stderr = ""
            self.duration_seconds = 0.0

    calls: list[str] = []
    llm_prompts: list[str] = []
    build_kwargs: dict[str, object] = {}

    def fake_run_cmd(cmd: list[str], **kwargs: object) -> _Result:
        if cmd[:2] == ["git", "clone"]:
            Path(str(cmd[-1])).mkdir(parents=True, exist_ok=True)
            return _Result()
        if cmd and cmd[0] == "rsync":
            Path(str(cmd[-1])).mkdir(parents=True, exist_ok=True)
            return _Result()
        if cmd[:3] == ["git", "-C", str(seed)]:
            return _Result("true\n")
        if cmd[:2] == ["git", "-C"] and cmd[-2:] == ["rev-parse", "HEAD"]:
            return _Result("2222222222222222222222222222222222222222\n")
        if cmd and cmd[0] == "git":
            return _Result()
        raise AssertionError(f"unexpected command: {cmd}")

    def fake_materialize_chunkhound_env_config(
        *,
        resolved_config: dict[str, object],
        output_config_path: Path,
        database_provider: str,
        database_path: Path,
    ) -> None:
        output_config_path.parent.mkdir(parents=True, exist_ok=True)
        output_config_path.write_text("{}", encoding="utf-8")
        database_path.parent.mkdir(parents=True, exist_ok=True)

    def fake_build_pr_context(**kwargs: object) -> dict[str, object]:
        calls.append("context")
        build_kwargs.update(kwargs)
        assert calls == ["stats", "context"]
        assert kwargs["head_sha"] == "2222222222222222222222222222222222222222"
        assert kwargs["pr_stats"] == {"changed_files": 1}
        return {"orientation_brief": orientation_brief, "meta": {"n_discussion": 0}}

    def fake_run_llm_exec(**kwargs: object) -> cure.LlmRunResult:
        prompt = str(kwargs["prompt"])
        output_path = kwargs["output_path"]
        assert isinstance(output_path, Path)
        llm_prompts.append(prompt)
        if len(llm_prompts) == 1:
            output_path.write_text("draft review from pass 1\n", encoding="utf-8")
        elif len(llm_prompts) == 2:
            output_path.write_text("final reconciled review\n", encoding="utf-8")
        else:  # pragma: no cover - defensive assertion for this focused harness
            raise AssertionError(f"unexpected LLM call count: {len(llm_prompts)}")
        return cure.LlmRunResult()

    monkeypatch.setattr(cure, "ensure_review_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        cure,
        "gh_api_json",
        lambda **kwargs: {
            "base": {"ref": "main"},
            "head": {"sha": "1111111111111111111111111111111111111111"},
            "title": "PR",
        },
    )
    monkeypatch.setattr(cure, "scan_completed_sessions_for_pr", lambda **kwargs: [])
    monkeypatch.setattr(
        cure,
        "load_chunkhound_runtime_config",
        lambda **kwargs: (
            cure.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
            {"chunkhound": {"base_config_path": str(base_cfg)}},
            {"indexing": {"exclude": []}},
        ),
    )
    monkeypatch.setattr(cure, "materialize_chunkhound_env_config", fake_materialize_chunkhound_env_config)
    monkeypatch.setattr(
        cure,
        "write_pr_context_file",
        lambda *, work_dir, pr, pr_meta: (work_dir / "pr-context.md"),
    )
    monkeypatch.setattr(cure, "ensure_base_cache", lambda **kwargs: {"db_path": str(base_db)})
    monkeypatch.setattr(
        cure,
        "resolve_pr_review_chunkhound_seed_source",
        lambda **kwargs: (base_db, {"source_kind": "test_base"}),
    )
    monkeypatch.setattr(cure, "_run_session_chunkhound_index_with_rebuild_fallback", lambda **kwargs: None)
    monkeypatch.setattr(cure, "seed_dir", lambda *args, **kwargs: seed)
    monkeypatch.setattr(cure, "ensure_clean_git_worktree", lambda *args, **kwargs: None)
    monkeypatch.setattr(cure, "same_device", lambda *args, **kwargs: True)
    monkeypatch.setattr(cure, "checkout_pr_in_repo", lambda **kwargs: None)
    monkeypatch.setattr(cure, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(
        cure,
        "resolve_llm_config_from_args",
        lambda *args, **kwargs: ({"provider": "openai", "preset": "test"}, {}),
    )
    monkeypatch.setattr(
        cure,
        "prepare_review_agent_runtime",
        lambda **kwargs: {"env": {}, "metadata": {}, "staged_paths": {}, "add_dirs": []},
    )
    monkeypatch.setattr(cure, "compute_pr_stats", lambda **kwargs: calls.append("stats") or {"changed_files": 1})
    monkeypatch.setattr(cure, "build_pr_context", fake_build_pr_context)
    monkeypatch.setattr(
        cure,
        "load_review_intelligence_config",
        lambda **kwargs: (None, {"review_intelligence": {"sources": [], "capabilities": {}}}),
    )
    monkeypatch.setattr(
        cure,
        "load_reviewflow_multipass_defaults",
        lambda **kwargs: ({"enabled": False, "max_steps": 20}, {"enabled": False, "max_steps": 20}),
    )
    monkeypatch.setattr(cure, "resolve_prompt_profile", lambda **kwargs: ("normal", "forced:test"))
    monkeypatch.setattr(cure, "_review_intelligence_runtime_capabilities", lambda *args, **kwargs: {})
    monkeypatch.setattr(cure, "_run_review_intelligence_preflight", lambda *args, **kwargs: None)
    monkeypatch.setattr(cure, "review_intelligence_prompt_vars", lambda *args, **kwargs: {})
    monkeypatch.setattr(cure, "require_builtin_review_intelligence", lambda *args, **kwargs: None)
    monkeypatch.setattr(cure, "load_builtin_prompt_text", lambda name: "draft prompt without prior context")
    monkeypatch.setattr(cure, "run_llm_exec", fake_run_llm_exec)

    rc = cure.pr_flow(
        args,
        paths=paths,
        config_path=config_path,
        codex_base_config_path=tmp_path / "codex.toml",
    )

    assert rc == 0
    assert calls == ["stats", "context"]
    return calls, llm_prompts, build_kwargs


def test_pr_flow_singlepass_with_prior_context_runs_draft_then_reconcile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, llm_prompts, build_kwargs = _run_singlepass_pr_flow_with_orientation(
        monkeypatch,
        tmp_path,
        orientation_brief="runtime brief",
    )

    assert build_kwargs["head_sha"] == "2222222222222222222222222222222222222222"
    assert build_kwargs["pr_stats"] == {"changed_files": 1}
    assert len(llm_prompts) == 2
    assert llm_prompts[0] == "draft prompt without prior context"
    assert "runtime brief" not in llm_prompts[0]
    assert "runtime brief" in llm_prompts[1]
    assert "draft review from pass 1" in llm_prompts[1]
    assert "Reconciliation rules (Option B)" in llm_prompts[1]


def test_pr_flow_singlepass_without_prior_context_runs_one_review_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, llm_prompts, _ = _run_singlepass_pr_flow_with_orientation(
        monkeypatch,
        tmp_path,
        orientation_brief="",
    )

    assert llm_prompts == ["draft prompt without prior context"]


def test_pr_flow_builds_simple_pr_context_after_pr_stats_with_effective_head() -> None:
    source = inspect.getsource(cure._pr_flow_impl)
    stats_idx = source.index('with phase("detect_pr_size"')
    context_idx = source.index('with phase("build_pr_context"')
    routing_idx = source.index('with phase("select_prompt_profile"')

    assert stats_idx < context_idx < routing_idx
    assert "head_sha=review_head_sha or head_sha" in source
    assert "gh_fetch=lambda path: gh_api_list(" in source
    assert "progress.meta[\"pr_context\"]" in source


def test_pr_flow_supplies_prior_context_only_to_multipass_synth_render() -> None:
    flow_source = inspect.getsource(cure._pr_flow_impl)

    assert 'prompt_extra_vars["PRIOR_CONTEXT"] = prior_context' not in flow_source
    assert flow_source.count('"PRIOR_CONTEXT": prior_context') == 1  # multipass synth only


def test_build_multipass_step_entries_no_prior_context(monkeypatch) -> None:
    """Step entries should NOT receive prior context — steps are independent review passes."""
    monkeypatch.setattr(cure, "load_builtin_prompt_text", lambda name: "prior=$PRIOR_CONTEXT step=$STEP_ID")
    monkeypatch.setattr(cure, "review_intelligence_prompt_vars", lambda *args, **kwargs: {})
    monkeypatch.setattr(cure, "cod_hypothesis_ledger_prompt_vars", lambda *args, **kwargs: {})

    entries = cure._build_multipass_step_entries(
        steps=[{"id": "api", "title": "API", "focus": "Boundaries"}],
        session_dir=cure.Path("/tmp/session"),
        plan_json_path=cure.Path("/tmp/plan.json"),
        templates={"step": "ignored.md"},
        base_ref_for_review="cure_base__main",
        pr_url="https://github.com/acme/rocket/pull/7",
        pr_number=7,
        pr=cure.PullRequestRef(host="github.com", owner="acme", repo="rocket", number=7),
        agent_desc="",
        review_intelligence_cfg=None,  # type: ignore[arg-type]
        review_intelligence_capabilities=None,
    )

    assert entries[0].prompt == "prior=$PRIOR_CONTEXT step=api"


def test_two_pass_singlepass_reconcile_prompt_has_option_b_rules() -> None:
    """The reconcile prompt must contain Option B reconciliation rules."""
    flow_source = inspect.getsource(cure._pr_flow_impl)
    reconcile_source = inspect.getsource(cure._reconcile_prior_context)
    assert "reconcile_prior_context" in flow_source
    assert 'inspect that specific file/path BEFORE adding' in reconcile_source
    assert 'Code evidence wins over context claims' in reconcile_source
    assert 'Do NOT re-review files the draft already covered well' in reconcile_source
    assert 'if (not use_multipass) and review_md_path.is_file() and prior_context' in flow_source


def test_github_api_helpers_are_reexported_from_cure_github_module() -> None:
    assert cure.gh_api_json is cure_github.gh_api_json
    assert cure.gh_api_list is cure_github.gh_api_list
    assert cure._decode_gh_api_list_stdout is cure_github._decode_gh_api_list_stdout


def test_gh_api_list_decodes_slurped_and_unslurped_pages() -> None:
    assert cure._decode_gh_api_list_stdout(stdout='[[{"id": 1}], [{"id": 2}]]', path="p") == [
        {"id": 1},
        {"id": 2},
    ]
    assert cure._decode_gh_api_list_stdout(stdout='[{"id": 1}]\n[{"id": 2}]', path="p") == [
        {"id": 1},
        {"id": 2},
    ]
