from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import threading
import time

import pytest

import cure
import cure_code_debt as debt
import cure_commands


def finding(path: str = "a.py", *, metric: str = "cyclomatic_complexity", signal: str = "branch") -> dict[str, object]:
    return {
        "signal": signal,
        "metric": metric,
        "path": path,
        "line": 1,
        "severity": "medium",
        "remediation_estimate": "30m",
        "evidence": f"{path}:1",
        "category": "maintainability",
        "fowler_quadrant": "inadvertent-prudent",
    }


def payload(*findings: dict[str, object], summary: dict[str, object] | None = None) -> str:
    return json.dumps({"findings": list(findings), "summary": summary or {}})


def test_prompt_forbids_executing_or_modifying_pr_code() -> None:
    text = (Path(__file__).parents[1] / "prompts" / "code_debt_analysis.md").read_text()
    for phrase in (
        "Do not execute", "test suites", "build scripts", "package hooks", "Do not modify",
        "read-only", "Do not send repository contents", "report the suspicion", "statically",
    ):
        assert phrase in text


def test_always_on_has_no_cli_or_config_switches() -> None:
    parser = cure.build_parser()
    args = parser.parse_args(["pr", "https://github.com/acme/repo/pull/1"])
    assert not hasattr(args, "code_debt")
    with pytest.raises(SystemExit):
        parser.parse_args(["pr", "https://github.com/acme/repo/pull/1", "--no-code-debt"])
    assert "enabled" not in debt.CodeDebtConfig.__dataclass_fields__
    assert "subagent_mode" not in debt.CodeDebtConfig.__dataclass_fields__
    assert debt.code_debt_stage_mode(multipass=True) == "multipass-stage"
    assert debt.code_debt_stage_mode(multipass=False) == "single-stage-subagent"


def test_removed_config_and_env_switches_are_ignored(tmp_path: Path) -> None:
    config = tmp_path / "cure.toml"
    config.write_text("[code_debt]\nenabled=false\nsubagent_mode='disabled'\n")
    cfg = debt.load_code_debt_config(
        config, env={"CURE_CODE_DEBT_ENABLED": "false", "CURE_CODE_DEBT_SUBAGENT_MODE": "disabled"}
    )
    assert not hasattr(cfg, "enabled")
    assert not hasattr(cfg, "subagent_mode")


def test_retry_attempt_caps_share_one_total_budget(tmp_path: Path) -> None:
    seen: list[int] = []
    def analyzer(request: debt.CodeDebtRequest) -> str:
        seen.append(request.token_budget)
        if len(seen) == 1:
            raise RuntimeError("retry")
        return payload()
    debt.run_code_debt_subagent(
        config=debt.CodeDebtConfig(max_token_budget=101), repo_dir=tmp_path, analyzer=analyzer
    )
    assert seen == [50, 51]
    assert sum(seen) == 101


def test_summary_is_grounded_and_unsupported_claims_are_removed(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n")
    output = payload(
        finding(),
        summary={
            "debt_ratio_estimate": "99% unsupported",
            "hotspot_top_n": ["a.py:1", "missing.py:9"],
            "business_claim": "customers hate this",
        },
    )
    report = debt.build_code_debt_report(
        [output], repo_dir=tmp_path, grounding_mode="strict", max_token_budget=1000
    )
    rendered = json.dumps(report.summary)
    assert "customers" not in rendered
    assert "99%" not in rendered
    assert "missing.py" not in rendered
    assert "a.py:1" in rendered


def test_markdown_renderer_neutralizes_hostile_fields(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n")
    hostile = finding(signal="issue\n\n## Forged Section ![audit](https://example.invalid/pixel)")
    hostile.update(
        metric="cyclomatic_complexity\n- forged",
        evidence="[deceptive](https://example.invalid)",
        remediation_estimate="1h\n# forged",
        fowler_quadrant="prudent\n> forged",
    )
    report = debt.build_code_debt_report(
        [payload(hostile)], repo_dir=tmp_path, grounding_mode="strict", max_token_budget=1000
    )
    markdown = report.to_markdown()
    assert "## Forged Section" not in markdown
    assert "\n- forged" not in markdown
    assert "\n# forged" not in markdown
    assert "\n> forged" not in markdown
    assert "![audit](" not in markdown
    assert "[deceptive](" not in markdown


def test_malformed_worker_output_is_reported_as_failure(tmp_path: Path) -> None:
    report = debt.build_code_debt_report(
        ['{"findings":'], repo_dir=tmp_path, grounding_mode="strict", max_token_budget=1000
    )
    markdown = report.to_markdown()
    assert report.worker_failures
    assert "failed" in markdown.lower()
    assert "completed successfully" not in markdown


def test_finding_without_evidence_or_fowler_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n")
    incomplete = finding()
    incomplete.pop("evidence")
    incomplete.pop("fowler_quadrant")
    report = debt.build_code_debt_report(
        [payload(incomplete)], repo_dir=tmp_path, grounding_mode="strict", max_token_budget=1000
    )
    assert report.findings == []


def test_documentation_finding_against_readme_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("prose\n")
    report = debt.build_code_debt_report(
        [payload(finding(path="README.md", metric="documentation_quality"))],
        repo_dir=tmp_path, grounding_mode="strict", max_token_budget=1000,
    )
    assert report.findings == []


def test_budget_pressure_drops_summaries_before_findings(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n" * 100)
    outputs = [
        payload(*(finding(),) if index == 0 else (), summary={"hotspot_top_n": [f"a.py:{line}" for line in range(1, 101)]})
        for index in range(3)
    ]
    report = debt.build_code_debt_report(
        outputs, repo_dir=tmp_path, grounding_mode="strict", max_token_budget=220
    )
    assert len(report.findings) == 1
    assert report.truncated is True
    assert len(report.summary.get("worker_summaries", [])) < 3


def test_config_validation_rejects_malformed_unbounded_or_noncanonical_values(tmp_path: Path) -> None:
    config = tmp_path / "cure.toml"
    config.write_text("[code_debt]\nmetrics=['cyclomatic_complexity', 'bad\\nmetric']\n")
    with pytest.raises(ValueError, match="code_debt.*metrics"):
        debt.load_code_debt_config(config, env={})
    config.write_text("[code_debt]\nmax_token_budget=1000001\n")
    with pytest.raises(ValueError, match="max_token_budget"):
        debt.load_code_debt_config(config, env={})
    with pytest.raises(ValueError, match="CURE_CODE_DEBT_TIMEOUT"):
        debt.load_code_debt_config(tmp_path / "missing.toml", env={"CURE_CODE_DEBT_TIMEOUT": "abc"})
    config.write_text("[code_debt]\ngrounding_mode='warn'\n")
    with pytest.raises(ValueError, match="grounding_mode.*strict"):
        debt.load_code_debt_config(config, env={})


def test_configured_metric_subset_is_enforced(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n")
    report = debt.build_code_debt_report(
        [payload(finding(metric="dependency_debt"))], repo_dir=tmp_path,
        grounding_mode="strict", max_token_budget=1000,
        enabled_metrics=("cyclomatic_complexity",),
    )
    assert report.findings == []


def test_deterministic_conflict_resolution_prefers_high_severity_and_ratio(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n")
    low = finding(signal="same")
    high = finding(signal="same")
    high.update(severity="high", evidence="more specific evidence at a.py:1")
    first = payload(low, summary={"debt_ratio_estimate": "2% of 100 changed NCLOC, SQALE A"})
    second = payload(high, summary={"debt_ratio_estimate": "8% of 100 changed NCLOC, SQALE B"})
    reports = [
        debt.build_code_debt_report(order, repo_dir=tmp_path, grounding_mode="strict", max_token_budget=1000)
        for order in ([first, second], [second, first])
    ]
    assert reports[0].findings == reports[1].findings
    assert reports[0].findings[0]["severity"] == "high"
    assert "Debt ratio estimate: **8% of 100 changed NCLOC, SQALE B**" in reports[0].to_markdown()
    assert reports[0].to_markdown() == reports[1].to_markdown()


def test_resume_synth_reattaches_persisted_code_debt_report(tmp_path: Path) -> None:
    report_path = tmp_path / "code-debt.md"
    report_path.write_text("debt")
    inputs = [str(tmp_path / "step-1.md")]
    cure._attach_code_debt_synth_input(inputs, session_dir=tmp_path)
    cure._attach_code_debt_synth_input(inputs, session_dir=tmp_path)
    assert inputs == [str(tmp_path / "step-1.md"), str(report_path)]


def test_setup_config_emits_documented_defaults(tmp_path: Path) -> None:
    runtime = SimpleNamespace(
        paths=SimpleNamespace(sandbox_root=tmp_path / "sandboxes", cache_root=tmp_path / "cache")
    )
    text = cure_commands._render_init_config(
        runtime=runtime, chunkhound_base_config_path=tmp_path / "chunkhound.json"
    )
    assert "[multipass]" in text
    assert 'grounding_mode = "strict"' in text
    assert "step_workers = 4" in text
    assert "[code_debt]" in text
    for expected in (
        'model_preset = "codex-cli"', 'model = "gpt-5.6-terra"',
        "max_token_budget = 4000", "timeout = 300", 'report_output = "file"',
    ):
        assert expected in text
    assert "enabled" not in text
    assert "subagent_mode" not in text


def write_fake_codex(binary: Path) -> None:
    binary.write_text("""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
Path(os.environ['ARGV']).write_text(json.dumps(sys.argv[1:]))
out = Path(sys.argv[sys.argv.index('--output-last-message') + 1])
out.write_text(json.dumps({'findings': [], 'summary': {}}))
print(json.dumps({'type':'thread.started','thread_id':'debt-test'}))
print(json.dumps({'type':'turn.started'}))
print(json.dumps({'type':'turn.completed','usage':{'output_tokens':1}}))
""")
    binary.chmod(0o755)


def test_execution_rebuilds_debt_model_and_generation_cap(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    session = tmp_path / "session"
    (session / "work").mkdir(parents=True)
    binary = tmp_path / "codex"
    write_fake_codex(binary)
    argv_path = tmp_path / "argv.json"
    env = {**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH','')}", "ARGV": str(argv_path)}
    logs = session / "work" / "logs"
    logs.mkdir()
    progress = cure.SessionProgress(session / "meta.json", quiet=True)
    progress.init({
        "session_id": "hardening", "status": "running",
        "paths": {"session_dir": str(session)},
        "logs": {"codex": str(logs / "codex.log")},
    })
    with mock.patch.object(
        cure, "resolve_llm_config",
        return_value=({"provider": "codex", "model": "gpt-5.6-terra"}, {}),
    ):
        cure._execute_code_debt_review_run(
            config=debt.CodeDebtConfig(max_token_budget=4000), multipass=False, plan=None,
            repo_dir=repo, session_dir=session, work_dir=session / "work", progress=progress,
            reviewflow_config_path=None, base_codex_config_path=tmp_path / "base.toml", env=env,
            add_dirs=None, runtime_policy={"codex_flags": ["-m", "gpt-primary"]},
            worker_count=1, owned_processes=None,
        )
    argv = json.loads(argv_path.read_text())
    assert argv[argv.index("-m") + 1] == "gpt-5.6-terra"
    assert "gpt-primary" not in argv
    assert "rollout_budget.limit_tokens=2000" in argv
    assert "--skip-git-repo-check" in argv
    assert "--add-dir" in argv


def test_rendered_report_is_narrative_complete_and_clean(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n")
    item = finding(signal="high-risk branch - hard to test")
    item.update(severity="high", evidence="a.py:1 contains an unchecked branch")
    report = debt.build_code_debt_report(
        [payload(item, summary={
            "debt_ratio_estimate": "4% of 100 changed NCLOC, SQALE A",
            "hotspot_top_n": ["a.py:1"],
            "severity_counts": {"high": 1},
        })],
        repo_dir=tmp_path,
        grounding_mode="strict",
        max_token_budget=1000,
    )
    markdown = report.to_markdown()
    assert "Overall assessment" in markdown
    assert "Debt ratio estimate: **4% of 100 changed NCLOC, SQALE A**" in markdown
    assert "High: 1" in markdown
    assert "a.py:1" in markdown and "high-risk branch" in markdown
    assert "### High" in markdown
    assert "Evidence: a.py:1 contains an unchecked branch" in markdown
    assert "Fowler quadrant: inadvertent-prudent" in markdown
    assert '"worker_summaries"' not in markdown
    assert "\\-" not in markdown


def test_rendered_exhausted_failure_is_not_clean_none() -> None:
    report = debt.CodeDebtReport(worker_count=1, worker_failures=("worker: boom",))
    markdown = report.to_markdown()
    assert "analysis failed" in markdown.lower()
    assert "worker: boom" in markdown
    assert "- None." not in markdown


def test_malformed_signal_does_not_discard_valid_findings(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n")
    malformed = finding(signal="branch")
    malformed["signal"] = ["branch"]
    report = debt.build_code_debt_report(
        [payload(malformed, finding(signal="valid branch"))],
        repo_dir=tmp_path,
        grounding_mode="strict",
        max_token_budget=1000,
    )
    assert any(item["signal"] == "valid branch" for item in report.findings)


def test_warn_grounding_is_visible_in_rendered_artifact(tmp_path: Path) -> None:
    report = debt.build_code_debt_report(
        [payload(finding(path="missing.py"))],
        repo_dir=tmp_path,
        grounding_mode="warn",
        max_token_budget=1000,
    )
    markdown = report.to_markdown()
    assert "unverified citation" in markdown.lower()
    assert "missing.py:1" in markdown


@pytest.mark.parametrize("budget", [1, 2])
def test_parallel_allocations_never_exceed_tiny_total_budget(tmp_path: Path, budget: int) -> None:
    seen: list[int] = []
    debt.run_code_debt_stage(
        config=debt.CodeDebtConfig(max_token_budget=budget),
        repo_dir=tmp_path,
        plan={},
        analyzer=lambda request: seen.append(request.token_budget) or payload(),
        worker_count=3,
    )
    assert sum(seen) <= budget
    assert len(seen) <= budget


def test_category_metric_alias_survives_but_unknown_metric_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n")
    report = debt.build_code_debt_report(
        [payload(finding(metric="security"), finding(metric="not_configured", signal="drop me"))],
        repo_dir=tmp_path,
        grounding_mode="strict",
        max_token_budget=1000,
    )
    assert [item["metric"] for item in report.findings] == ["severity_counts"]


def test_ensure_code_debt_artifact_runs_missing_and_persists_failure(tmp_path: Path) -> None:
    progress = SimpleNamespace(meta={})
    progress.mutate = lambda: mock.MagicMock(__enter__=lambda self: None, __exit__=lambda *args: None)
    calls: list[str] = []
    path = cure._ensure_code_debt_artifact(
        session_dir=tmp_path, progress=progress, mode="multipass-stage",
        execute=lambda: calls.append("run") or (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert calls == ["run"]
    assert path.is_file()
    assert "analysis failed" in path.read_text().lower()
    assert progress.meta["code_debt"]["status"] == "failed-open"
    calls.clear()
    assert cure._ensure_code_debt_artifact(
        session_dir=tmp_path, progress=progress, mode="multipass-stage",
        execute=lambda: calls.append("rerun") or path,
    ) == path
    assert calls == []


def test_plan_abort_debt_hook_runs_only_for_abort() -> None:
    calls: list[str] = []

    def execute() -> Path:
        calls.append("debt")
        return Path("code-debt.md")
    assert cure._execute_code_debt_on_plan_abort(plan={"abort": False}, execute=execute) is None
    assert calls == []
    assert cure._execute_code_debt_on_plan_abort(plan={"abort": True}, execute=execute) == Path("code-debt.md")
    assert calls == ["debt"]


def test_trust_directory_failures_cannot_double_generation_budget(tmp_path: Path) -> None:
    caps: list[int] = []

    def trust_failure(**kwargs: object) -> object:
        policy = kwargs["runtime_policy"]
        assert isinstance(policy, dict)
        assert policy["skip_git_repo_check"] is True
        flags = policy["codex_flags"]
        assert isinstance(flags, list)
        raw = next(str(item) for item in flags if str(item).startswith("rollout_budget.limit_tokens="))
        caps.append(int(raw.rsplit("=", 1)[1]))
        raise RuntimeError("trusted directory error after near-cap generation")

    progress = SimpleNamespace(meta={})
    progress.mutate = lambda: mock.MagicMock(__enter__=lambda self: None, __exit__=lambda *args: None)
    with mock.patch.object(
        cure, "resolve_llm_config",
        return_value=({"provider": "codex", "model": "gpt-5.6-terra"}, {}),
    ), mock.patch.object(cure, "run_llm_exec", side_effect=trust_failure):
        cure._execute_code_debt_review_run(
            config=debt.CodeDebtConfig(max_token_budget=101), multipass=False, plan=None,
            repo_dir=tmp_path, session_dir=tmp_path, work_dir=tmp_path, progress=progress,
            reviewflow_config_path=None, base_codex_config_path=tmp_path / "codex.toml", env={},
            add_dirs=[tmp_path], runtime_policy={}, worker_count=1, owned_processes=None,
        )
    assert caps == [50, 51]
    assert sum(caps) <= 101


def test_debt_runtime_matches_standard_step_worker_policy_with_budget(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_exec(**kwargs: object) -> object:
        captured.update(kwargs)
        Path(kwargs["output_path"]).write_text(payload())  # type: ignore[arg-type]
        return SimpleNamespace(adapter_meta={})

    progress = SimpleNamespace(meta={})
    progress.mutate = lambda: mock.MagicMock(__enter__=lambda self: None, __exit__=lambda *args: None)
    with mock.patch.object(cure, "resolve_llm_config", return_value=({"provider": "codex", "model": "gpt-5.6-terra"}, {})), mock.patch.object(cure, "run_llm_exec", side_effect=fake_exec):
        cure._execute_code_debt_review_run(
            config=debt.CodeDebtConfig(), multipass=False, plan=None,
            repo_dir=tmp_path, session_dir=tmp_path, work_dir=tmp_path, progress=progress,
            reviewflow_config_path=None, base_codex_config_path=tmp_path / "codex.toml", env={},
            add_dirs=None, runtime_policy={"dangerously_bypass_approvals_and_sandbox": True},
            worker_count=1, owned_processes=None,
        )
    policy = captured["runtime_policy"]
    assert isinstance(policy, dict)
    assert policy["dangerously_bypass_approvals_and_sandbox"] is True
    assert policy.get("sandbox_mode") != "read-only"
    assert policy.get("approval_policy") != "never"
    assert policy.get("add_dirs") == captured["add_dirs"]
    assert any(str(flag).startswith("rollout_budget.limit_tokens=") for flag in policy["codex_flags"])


def test_schema_grounding_rejections_are_disclosed_per_worker(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n")
    missing_estimate = finding()
    missing_estimate.pop("remediation_estimate")
    wrong_evidence = finding()
    wrong_evidence["evidence"] = "unrelated assertion"
    report = debt.build_code_debt_report(
        [payload(missing_estimate, wrong_evidence)], repo_dir=tmp_path,
        grounding_mode="strict", max_token_budget=1000,
    )
    assert report.findings == []
    assert any("rejected 2" in failure for failure in report.worker_failures)
    assert "completed successfully" not in report.to_markdown()


def test_ratio_requires_bounded_grounded_calculation(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n")
    reports = [
        debt.build_code_debt_report(
            [payload(finding(), summary={"debt_ratio_estimate": ratio})],
            repo_dir=tmp_path, grounding_mode="strict", max_token_budget=2000,
        )
        for ratio in ("999999%", "4%", "4% of 100 changed NCLOC, SQALE A")
    ]
    assert "999999%" not in reports[0].to_markdown()
    assert "Debt ratio estimate: **unknown**" in reports[1].to_markdown()
    assert "Debt ratio estimate: **4% of 100 changed NCLOC, SQALE A**" in reports[2].to_markdown()


def test_persist_budget_estimate_matches_rendered_markdown(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n")
    report = debt.build_code_debt_report(
        [payload(finding(signal="x" * 500))], repo_dir=tmp_path,
        grounding_mode="strict", max_token_budget=120,
    )
    assert report.estimated_tokens == debt._estimate_markdown_tokens(report.to_markdown())
    assert report.truncated


def test_legacy_debt_artifact_is_repaired_not_reused(tmp_path: Path) -> None:
    path = tmp_path / "code-debt.md"
    path.write_text("legacy report")
    progress = SimpleNamespace(meta={})
    progress.mutate = lambda: mock.MagicMock(__enter__=lambda self: None, __exit__=lambda *args: None)
    calls: list[str] = []
    result = cure._ensure_code_debt_artifact(
        session_dir=tmp_path, progress=progress, mode="multipass-stage",
        execute=lambda: calls.append("run") or (path.write_text(debt.CodeDebtReport().to_markdown()) and path),
    )
    assert result == path
    assert calls == ["run"]
    assert "Dedicated Code-Debt Analysis" in path.read_text()


def test_timeout_uses_dedicated_registry_and_leaves_shared_registry_open(tmp_path: Path) -> None:
    shared = cure.OwnedProcessRegistry()
    started = threading.Event()

    def blocked_exec(**kwargs: object) -> object:
        registry = kwargs["owned_processes"]
        assert registry is not shared
        started.set()
        deadline = time.monotonic() + 3
        while registry.state.name == "OPEN" and time.monotonic() < deadline:  # type: ignore[union-attr]
            time.sleep(0.01)
        raise TimeoutError("terminated")

    progress = SimpleNamespace(meta={})
    progress.mutate = lambda: mock.MagicMock(__enter__=lambda self: None, __exit__=lambda *args: None)
    with mock.patch.object(cure, "resolve_llm_config", return_value=({"provider": "codex", "model": "gpt-5.6-terra"}, {})), mock.patch.object(cure, "run_llm_exec", side_effect=blocked_exec):
        cure._execute_code_debt_review_run(
            config=debt.CodeDebtConfig(timeout_seconds=1), multipass=False, plan=None,
            repo_dir=tmp_path, session_dir=tmp_path, work_dir=tmp_path, progress=progress,
            reviewflow_config_path=None, base_codex_config_path=tmp_path / "codex.toml", env={},
            add_dirs=None, runtime_policy={}, worker_count=1, owned_processes=shared,
        )
    assert started.is_set()
    assert shared.state.name == "OPEN"
