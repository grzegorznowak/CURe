from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import threading
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cure  # noqa: E402
import cure_code_debt as debt  # noqa: E402


def _payload(*findings: dict[str, object]) -> str:
    return json.dumps({"findings": list(findings), "summary": {"debt_ratio_estimate": "4%"}})


def _finding(path: str = "src/a.py", line: int = 1, *, signal: str = "complex branch") -> dict[str, object]:
    return {
        "signal": signal,
        "metric": "cyclomatic_complexity",
        "path": path,
        "line": line,
        "severity": "medium",
        "remediation_estimate": "30m",
        "evidence": f"{path}:{line}",
        "category": "maintainability",
        "fowler_quadrant": "inadvertent-prudent",
    }


def test_prompt_contract_contains_tiered_metrics_and_hotspots() -> None:
    text = (Path(__file__).parents[1] / "prompts" / "code_debt_analysis.md").read_text()
    for phrase in (
        "technical-debt ratio",
        "severity counts",
        "cyclomatic complexity",
        "duplication density",
        "TODO/FIXME/HACK/XXX",
        "test gap",
        "dependency debt",
        "design/architecture debt",
        "semantic smells",
        "documentation quality",
        "test quality",
        "Fowler quadrant",
        "churn × complexity",
    ):
        assert phrase in text


def test_code_debt_has_no_activation_override() -> None:
    parser = cure.build_parser()
    inherited = parser.parse_args(["pr", "https://github.com/acme/repo/pull/1"])
    assert not hasattr(inherited, "code_debt")


def test_config_defaults_and_named_codex_model_resolution(tmp_path: Path) -> None:
    cfg = debt.load_code_debt_config(tmp_path / "missing.toml", env={})
    assert cfg.model_preset == "codex-cli"
    assert cfg.model == "gpt-5.6-terra"
    assert cfg.max_token_budget > 0

    path = tmp_path / "cure.toml"
    path.write_text(
        "[code_debt]\nenabled=true\nmodel_preset='terra-custom'\nmodel='gpt-custom'\n"
        "max_token_budget=900\nmetrics=['cyclomatic_complexity']\n"
    )
    cfg = debt.load_code_debt_config(
        path,
        env={"CURE_CODE_DEBT_MODEL": "gpt-env", "CURE_CODE_DEBT_TIMEOUT": "17"},
    )
    assert cfg.model_preset == "terra-custom"
    assert cfg.model == "gpt-env"
    assert cfg.timeout_seconds == 17


def test_budget_cap_truncates_gracefully(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    cfg = debt.CodeDebtConfig(max_token_budget=90)
    raw = _payload(*[_finding("a.py", 1, signal="x" * 180) for _ in range(5)])
    report = debt.run_code_debt_stage(
        config=cfg,
        repo_dir=tmp_path,
        plan={"steps": []},
        analyzer=lambda request: raw,
        worker_count=4,
    )
    assert report.estimated_tokens <= cfg.max_token_budget
    assert report.truncated is True
    assert "token budget" in report.notice.lower()


def test_grounding_drops_or_flags_invalid_findings(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("one\ntwo\n")
    good = _finding("ok.py", 2)
    bad = _finding("missing.py", 10)
    strict = debt.validate_code_debt_findings([good, bad], repo_dir=tmp_path, mode="strict")
    assert strict == [good]
    warn = debt.validate_code_debt_findings([good, bad], repo_dir=tmp_path, mode="warn")
    assert len(warn) == 2
    assert warn[1]["grounding"] == "warning"


def test_non_code_findings_are_filtered(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n")
    code = _finding("a.py", 1)
    business = {**_finding("a.py", 1), "category": "product", "signal": "pricing unclear"}
    report = debt.build_code_debt_report(
        [_payload(code, business)], repo_dir=tmp_path, grounding_mode="strict", max_token_budget=1000
    )
    assert [item["signal"] for item in report.findings] == ["complex branch"]


def test_single_stage_subagent_is_isolated_and_code_only(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n")
    seen: list[debt.CodeDebtRequest] = []

    def analyzer(request: debt.CodeDebtRequest) -> str:
        seen.append(request)
        return _payload(_finding("a.py", 1), {**_finding("a.py", 1), "category": "business"})

    report = debt.run_code_debt_subagent(
        config=debt.CodeDebtConfig(),
        repo_dir=tmp_path,
        analyzer=analyzer,
    )
    assert len(seen) == 1
    assert seen[0].isolated is True
    assert seen[0].stage == "single-stage-subagent"
    assert len(report.findings) == 1


def _progress(session_dir: Path) -> cure.SessionProgress:
    logs_dir = session_dir / "work" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    progress = cure.SessionProgress(session_dir / "meta.json", quiet=True)
    progress.init(
        {
            "session_id": "code-debt-test",
            "status": "running",
            "paths": {"session_dir": str(session_dir)},
            "logs": {"codex": str(logs_dir / "codex.log")},
        }
    )
    return progress


def _write_fake_codex(binary: Path) -> None:
    binary.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

Path(os.environ["FAKE_CODEX_ARGV"]).write_text(json.dumps(sys.argv[1:]), encoding="utf-8")
if os.environ.get("FAKE_CODEX_EXIT"):
    print("fake codex rejected request", file=sys.stderr)
    raise SystemExit(int(os.environ["FAKE_CODEX_EXIT"]))
output = Path(sys.argv[sys.argv.index("--output-last-message") + 1])
output.write_text(json.dumps({"findings": [], "summary": {"status": "ok"}}), encoding="utf-8")
for event in (
    {"type": "thread.started", "thread_id": "fake-code-debt"},
    {"type": "turn.started"},
    {"type": "turn.completed", "usage": {"output_tokens": 7}},
):
    print(json.dumps(event), flush=True)
""",
        encoding="utf-8",
    )
    binary.chmod(0o755)


def test_fake_codex_smoke_propagates_configured_model_and_handles_failure(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    session_dir = tmp_path / "session"
    work_dir = session_dir / "work"
    bin_dir = tmp_path / "bin"
    repo_dir.mkdir()
    work_dir.mkdir(parents=True)
    bin_dir.mkdir()
    _write_fake_codex(bin_dir / "codex")
    argv_path = tmp_path / "codex-argv.json"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "CODEX_HOME": str(tmp_path / "codex-home"),
        "FAKE_CODEX_ARGV": str(argv_path),
    }
    cfg = debt.load_code_debt_config(tmp_path / "missing.toml", env={})

    with mock.patch.object(
        cure,
        "resolve_llm_config",
        return_value=({"provider": "codex", "model": cfg.model, "preset": cfg.model_preset}, {}),
    ):
        report_path = cure._execute_code_debt_review_run(
            config=cfg,
            multipass=False,
            plan=None,
            repo_dir=repo_dir,
            session_dir=session_dir,
            work_dir=work_dir,
            progress=_progress(session_dir),
            reviewflow_config_path=None,
            base_codex_config_path=tmp_path / "codex.toml",
            env=env,
            add_dirs=None,
            runtime_policy={},
            worker_count=1,
            owned_processes=None,
        )
    argv = json.loads(argv_path.read_text(encoding="utf-8"))
    assert argv[argv.index("-m") + 1] == "gpt-5.6-terra"
    assert report_path == session_dir / "code-debt.md"
    assert report_path.is_file()

    failed_session = tmp_path / "failed-session"
    failed_work = failed_session / "work"
    failed_work.mkdir(parents=True)
    failing_env = {**env, "FAKE_CODEX_EXIT": "23"}
    with mock.patch.object(
        cure,
        "resolve_llm_config",
        return_value=({"provider": "codex", "model": cfg.model, "preset": cfg.model_preset}, {}),
    ):
        failed_progress = _progress(failed_session)
        failed_report = cure._execute_code_debt_review_run(
            config=cfg,
            multipass=False,
            plan=None,
            repo_dir=repo_dir,
            session_dir=failed_session,
            work_dir=failed_work,
            progress=failed_progress,
            reviewflow_config_path=None,
            base_codex_config_path=tmp_path / "codex.toml",
            env=failing_env,
            add_dirs=None,
            runtime_policy={},
            worker_count=1,
            owned_processes=None,
        )
    assert failed_report == failed_session / "code-debt.md"
    assert failed_report.is_file()
    failures = failed_progress.meta["code_debt"]["worker_failures"]
    assert failures
    assert "Command failed (23)" in failures[0]


def test_report_output_file_mode_persists_without_printing(tmp_path: Path) -> None:
    report_path = tmp_path / "code-debt.md"
    report_path.write_text("## Dedicated Code-Debt Analysis\n\n### Summary\n- ok\n")
    stdout = io.StringIO()
    stderr = io.StringIO()
    cure._emit_code_debt_report_output(
        config=debt.CodeDebtConfig(report_output="file"),
        report_path=report_path,
        machine_readable=False,
        stdout=stdout,
        stderr=stderr,
    )
    assert report_path.is_file()
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == ""


def test_report_output_stdout_appends_human_summary_and_keeps_file(tmp_path: Path) -> None:
    report_path = tmp_path / "code-debt.md"
    report_path.write_text("## Dedicated Code-Debt Analysis\n\n### Summary\n- debt ratio: 4%\n")
    stdout = io.StringIO()
    cure._emit_code_debt_report_output(
        config=debt.CodeDebtConfig(report_output="stdout"),
        report_path=report_path,
        machine_readable=False,
        stdout=stdout,
        stderr=io.StringIO(),
    )
    assert report_path.is_file()
    assert "Dedicated Code-Debt Analysis" in stdout.getvalue()
    assert "debt ratio: 4%" in stdout.getvalue()


def test_report_output_stdout_degrades_in_machine_path_with_stderr_notice(tmp_path: Path) -> None:
    report_path = tmp_path / "code-debt.md"
    report_path.write_text("## Dedicated Code-Debt Analysis\n")
    stdout = io.StringIO()
    stderr = io.StringIO()
    cure._emit_code_debt_report_output(
        config=debt.CodeDebtConfig(report_output="stdout"),
        report_path=report_path,
        machine_readable=True,
        stdout=stdout,
        stderr=stderr,
    )
    assert report_path.is_file()
    assert stdout.getvalue() == ""
    assert "code-debt.md" in stderr.getvalue()
    assert "reserved" in stderr.getvalue().lower()


def test_integrated_timeout_terminates_isolated_run_without_hanging(tmp_path: Path) -> None:
    class Progress:
        def __init__(self) -> None:
            self.meta: dict[str, object] = {}

        @contextlib.contextmanager
        def mutate(self):
            yield

    progress = Progress()

    def blocked_exec(**kwargs: object) -> object:
        registry = kwargs["owned_processes"]
        deadline = time.monotonic() + 4
        while registry.state.name == "OPEN" and time.monotonic() < deadline:  # type: ignore[union-attr]
            time.sleep(0.01)
        raise TimeoutError("terminated")

    started = time.monotonic()
    with mock.patch.object(
        cure,
        "resolve_llm_config",
        return_value=({"provider": "codex", "model": "gpt-5.6-terra"}, {}),
    ), mock.patch.object(cure, "run_llm_exec", side_effect=blocked_exec):
        report_path = cure._execute_code_debt_review_run(
            config=debt.CodeDebtConfig(timeout_seconds=1),
            multipass=False,
            plan=None,
            repo_dir=tmp_path,
            session_dir=tmp_path,
            work_dir=tmp_path,
            progress=progress,  # type: ignore[arg-type]
            reviewflow_config_path=None,
            base_codex_config_path=tmp_path / "codex.toml",
            env={},
            add_dirs=None,
            runtime_policy={},
            worker_count=1,
            owned_processes=None,
        )
    assert time.monotonic() - started < 2.5
    assert report_path == tmp_path / "code-debt.md"
    assert "configured timeout reached" in progress.meta["code_debt"]["worker_failures"]  # type: ignore[index]


def test_multistage_activation_and_parallel_workers(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n")
    cfg = debt.CodeDebtConfig()
    assert debt.code_debt_stage_mode(multipass=True) == "multipass-stage"
    assert debt.code_debt_stage_mode(multipass=False) == "single-stage-subagent"

    barrier = threading.Barrier(len(debt.METRIC_CLUSTERS))
    thread_ids: set[int] = set()

    def analyzer(request: debt.CodeDebtRequest) -> str:
        thread_ids.add(threading.get_ident())
        barrier.wait(timeout=2)
        time.sleep(0.01)
        return _payload(_finding("a.py", 1, signal=request.metric_cluster))

    report = debt.run_code_debt_stage(
        config=cfg,
        repo_dir=tmp_path,
        plan={"steps": []},
        analyzer=analyzer,
        worker_count=len(debt.METRIC_CLUSTERS),
    )
    assert len(thread_ids) > 1
    assert report.worker_count == len(debt.METRIC_CLUSTERS)
