from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

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
    hostile = finding(signal="issue\n\n## Forged Section")
    hostile.update(
        metric="cyclomatic_complexity\n- forged",
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


def test_budget_pressure_drops_summaries_before_findings(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n")
    outputs = [
        payload(*(finding(),) if index == 0 else (), summary={"hotspot_top_n": ["a.py:1"] * 100})
        for index in range(3)
    ]
    report = debt.build_code_debt_report(
        outputs, repo_dir=tmp_path, grounding_mode="strict", max_token_budget=130
    )
    assert len(report.findings) == 1
    assert report.truncated is True
    assert len(report.summary.get("worker_summaries", [])) < 3


def test_configured_metric_subset_is_enforced(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n")
    report = debt.build_code_debt_report(
        [payload(finding(metric="dependency_debt"))], repo_dir=tmp_path,
        grounding_mode="strict", max_token_budget=1000,
        enabled_metrics=("cyclomatic_complexity",),
    )
    assert report.findings == []


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
