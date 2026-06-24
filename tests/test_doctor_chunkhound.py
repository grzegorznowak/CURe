from __future__ import annotations

import argparse
import contextlib
import dataclasses
import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cure_commands  # noqa: E402
import cure_runtime  # noqa: E402
from cure_chunkhound import ChunkHoundPreflightError, ChunkHoundPreflightResult  # noqa: E402


def _recommended_chunkhound_config() -> dict[str, object]:
    return {
        "embedding": {
            "provider": "voyageai",
            "model": "voyage-3.5-lite",
            "rerank_model": "rerank-2.5",
            "api_key": "voyage-test-key",  # pragma: allowlist secret
        },
        "llm": {
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "synthesis_model": "deepseek-v4-flash",
            "utility_model": "deepseek-v4-flash",
            "api_key": "sk-test-key",  # pragma: allowlist secret
            "codex_reasoning_effort_synthesis": "high",
            "codex_reasoning_effort_utility": "high",
        },
    }


def _write_runtime_config(root: Path, base_config: dict[str, object] | None = None) -> cure_runtime.ReviewflowRuntime:
    root.mkdir(parents=True, exist_ok=True)
    (root / "sandboxes").mkdir(exist_ok=True)
    (root / "cache").mkdir(exist_ok=True)
    base_cfg = root / "chunkhound.json"
    if base_config is not None:
        base_cfg.write_text(json.dumps(base_config), encoding="utf-8")
    cfg = root / "cure.toml"
    cfg.write_text(
        "\n".join(
            [
                "[paths]",
                f'sandbox_root = "{root / "sandboxes"}"',
                f'cache_root = "{root / "cache"}"',
                "",
                "[chunkhound]",
                f'base_config_path = "{base_cfg}"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return cure_runtime.ReviewflowRuntime(
        config_path=cfg,
        config_source="cli",
        config_enabled=True,
        paths=cure_runtime.ReviewflowPaths(sandbox_root=root / "sandboxes", cache_root=root / "cache"),
        sandbox_root_source="config",
        cache_root_source="config",
        codex_base_config_path=root / "codex.toml",
        codex_base_config_source="default",
    )


def test_chunkhound_preflight_result_dataclass_defaults_and_serialization() -> None:
    result = ChunkHoundPreflightResult(
        stage="ok",
        available_tools=["search", "code_research"],
        missing_tools=[],
        mcp_transport="json_line",
        daemon_pid=123,
        daemon_socket="/tmp/chunkhound.sock",
        daemon_log="/tmp/daemon.log",
        daemon_runtime_dir="/tmp/chunkhound-runtime",
        time_ms=12.5,
    )

    assert dataclasses.is_dataclass(result)
    assert result.stage == "ok"
    assert result.available_tools == ["search", "code_research"]
    assert result.missing_tools == []
    assert result.daemon_pid == 123
    assert dataclasses.asdict(result) == {
        "stage": "ok",
        "available_tools": ["search", "code_research"],
        "missing_tools": [],
        "mcp_transport": "json_line",
        "daemon_pid": 123,
        "daemon_socket": "/tmp/chunkhound.sock",
        "daemon_log": "/tmp/daemon.log",
        "daemon_runtime_dir": "/tmp/chunkhound-runtime",
        "time_ms": 12.5,
    }


def test_chunkhound_preflight_result_allows_absent_daemon_metadata() -> None:
    result = ChunkHoundPreflightResult(
        stage="degraded",
        available_tools=["search"],
        missing_tools=["code_research"],
        mcp_transport="mcp_framed",
        daemon_pid=None,
        daemon_socket=None,
        daemon_log=None,
        daemon_runtime_dir=None,
        time_ms=0.0,
    )

    assert result.daemon_pid is None
    assert result.daemon_socket is None
    assert result.daemon_log is None
    assert result.daemon_runtime_dir is None


def test_chunkhound_preflight_error_exposes_stage_and_detail() -> None:
    exc = ChunkHoundPreflightError("initialize", "timed out")

    assert exc.stage == "initialize"
    assert exc.detail == "timed out"
    assert "initialize" in str(exc)
    assert "timed out" in str(exc)

    with pytest.raises(ChunkHoundPreflightError) as raised:
        raise exc
    assert raised.value.stage == "initialize"


@pytest.mark.parametrize(
    ("mutator", "expected_status", "expected_detail"),
    [
        (lambda cfg: cfg, "ok", "configuration matches CURe recommendation"),
        (lambda cfg: {k: v for k, v in cfg.items() if k != "embedding"}, "fail", "missing required section: embedding"),
        (lambda cfg: {k: v for k, v in cfg.items() if k != "llm"}, "fail", "missing required section: llm"),
        (lambda cfg: {**cfg, "embedding": {**cfg["embedding"], "provider": "openai"}}, "warn", "embedding.provider"),
        (lambda cfg: {**cfg, "embedding": {**cfg["embedding"], "model": "text-embedding-3-small"}}, "warn", "embedding.model"),
        (lambda cfg: {**cfg, "embedding": {**cfg["embedding"], "rerank_model": "other"}}, "warn", "embedding.rerank_model"),
        (lambda cfg: {**cfg, "embedding": {**cfg["embedding"], "api_key": ""}}, "warn", "embedding.api_key is empty"),
        (lambda cfg: {**cfg, "llm": {**cfg["llm"], "provider": "openai"}}, "warn", "llm.provider"),
        (lambda cfg: {**cfg, "llm": {**cfg["llm"], "base_url": "https://api.openai.com/v1"}}, "warn", "llm.base_url"),
        (lambda cfg: {**cfg, "llm": {**cfg["llm"], "synthesis_model": "other"}}, "warn", "llm.synthesis_model"),
        (lambda cfg: {**cfg, "llm": {**cfg["llm"], "utility_model": "other"}}, "warn", "llm.utility_model"),
        (lambda cfg: {**cfg, "llm": {**cfg["llm"], "api_key": "not-sk"}}, "warn", "llm.api_key does not start with sk-"),  # pragma: allowlist secret
        (
            lambda cfg: {**cfg, "llm": {**cfg["llm"], "codex_reasoning_effort_synthesis": "medium"}},
            "warn",
            "llm.codex_reasoning_effort_synthesis",
        ),
        (
            lambda cfg: {**cfg, "llm": {**cfg["llm"], "codex_reasoning_effort_utility": "medium"}},
            "warn",
            "llm.codex_reasoning_effort_utility",
        ),
    ],
)
def test_validate_chunkhound_config(mutator: object, expected_status: str, expected_detail: str) -> None:
    config = mutator(_recommended_chunkhound_config())  # type: ignore[operator]

    status, detail = cure_runtime._validate_chunkhound_config(config)

    assert status == expected_status
    assert expected_detail in detail


def test_validate_chunkhound_config_joins_multiple_warnings() -> None:
    config = _recommended_chunkhound_config()
    config["embedding"] = {**config["embedding"], "provider": "openai", "model": "text-embedding-3-small"}  # type: ignore[arg-type]

    status, detail = cure_runtime._validate_chunkhound_config(config)

    assert status == "warn"
    assert "embedding.provider" in detail
    assert "; " in detail
    assert "embedding.model" in detail


def test_index_fixture_for_health_check_copies_fixture_and_merges_config(tmp_path: Path) -> None:
    from _doctor_chunkhound_fixture import index_fixture_for_health_check

    completed = subprocess.CompletedProcess(args=["chunkhound"], returncode=0, stdout="", stderr="")
    with mock.patch("_doctor_chunkhound_fixture.subprocess.run", return_value=completed) as run_mock:
        with index_fixture_for_health_check("/usr/bin/chunkhound", _recommended_chunkhound_config(), timeout=12.0) as (
            config_path,
            repo_path,
            temp_dir,
        ):
            repo = Path(repo_path)
            merged_config = json.loads(Path(config_path).read_text(encoding="utf-8"))
            assert Path(temp_dir.name).exists()
            assert (repo / "main.py").read_text(encoding="utf-8").strip() == 'def saludar() -> str:\n    return "hola"'
            assert (repo / "utils.py").read_text(encoding="utf-8").strip() == "def sumar(a: int, b: int) -> int:\n    return a + b"
            assert "ChunkHound funciona correctamente" in (repo / "README.md").read_text(encoding="utf-8")
            assert merged_config["embedding"] == _recommended_chunkhound_config()["embedding"]
            assert merged_config["llm"] == _recommended_chunkhound_config()["llm"]
            assert merged_config["database"]["provider"] == "duckdb"
            assert str(Path(merged_config["database"]["path"]).parent) == str(Path(temp_dir.name))
            assert merged_config["indexing"] == {"include": ["*.py", "*.md"]}
            run_mock.assert_called_once_with(
                ["/usr/bin/chunkhound", "index", str(repo), "--config", str(Path(config_path))],
                check=True,
                capture_output=True,
                text=True,
                timeout=12.0,
            )
        assert not Path(temp_dir.name).exists()


def test_index_fixture_for_health_check_fixture_package_is_resource_backed() -> None:
    import importlib.resources
    import _doctor_chunkhound_fixture

    files = importlib.resources.files(_doctor_chunkhound_fixture)
    assert (files / "main.py").is_file()
    assert (files / "utils.py").is_file()
    assert (files / "README.md").is_file()


@contextlib.contextmanager
def _fake_indexed_fixture(config_path: Path, repo_path: Path):
    yield str(config_path), str(repo_path), mock.Mock(name=str(repo_path.parent))


def _preflight_result() -> ChunkHoundPreflightResult:
    return ChunkHoundPreflightResult(
        stage="complete",
        available_tools=["search", "code_research"],
        missing_tools=[],
        mcp_transport="json_line",
        daemon_pid=321,
        daemon_socket="/tmp/chunkhound.sock",
        daemon_log="/tmp/chunkhound.log",
        daemon_runtime_dir="/tmp/chunkhound-runtime",
        time_ms=42.0,
    )


def _health_runtime(tmp_path: Path) -> tuple[cure_runtime.ReviewflowRuntime, Path, Path]:
    runtime = _write_runtime_config(tmp_path, _recommended_chunkhound_config())
    fixture_repo = tmp_path / "fixture-repo"
    fixture_repo.mkdir()
    fixture_config = tmp_path / "fixture-chunkhound.json"
    fixture_config.write_text("{}", encoding="utf-8")
    return runtime, fixture_config, fixture_repo


def test_doctor_chunkhound_health_ok_when_all_stages_pass(tmp_path: Path) -> None:
    runtime, fixture_config, fixture_repo = _health_runtime(tmp_path)
    with mock.patch.object(cure_runtime.shutil, "which", return_value="/usr/bin/chunkhound"), \
        mock.patch.object(
            cure_runtime,
            "index_fixture_for_health_check",
            return_value=_fake_indexed_fixture(fixture_config, fixture_repo),
        ), \
        mock.patch.object(cure_runtime, "run_chunkhound_mcp_preflight", return_value=_preflight_result()), \
        mock.patch.object(
            cure_runtime,
            "run_chunkhound_tool",
            side_effect=[
                {"ok": True, "result": {"results": [{"file_path": str(fixture_repo / "main.py")}] }},
                {"ok": True, "result": "See [main.py](main.py) for saludar."},
            ],
        ):
        check, artifact = cure_runtime._doctor_chunkhound_health_check(runtime)

    assert check.status == "ok"
    assert check.name == "chunkhound-health"
    assert artifact == _preflight_result()


def test_doctor_chunkhound_health_fails_on_preflight_error(tmp_path: Path) -> None:
    runtime, fixture_config, fixture_repo = _health_runtime(tmp_path)
    with mock.patch.object(cure_runtime.shutil, "which", return_value="/usr/bin/chunkhound"), \
        mock.patch.object(cure_runtime, "index_fixture_for_health_check", return_value=_fake_indexed_fixture(fixture_config, fixture_repo)), \
        mock.patch.object(cure_runtime, "run_chunkhound_mcp_preflight", side_effect=ChunkHoundPreflightError("initialize", "boom")):
        check, artifact = cure_runtime._doctor_chunkhound_health_check(runtime)

    assert check.status == "fail"
    assert "initialize" in check.detail
    assert "boom" in check.detail
    assert isinstance(artifact, ChunkHoundPreflightError)


def test_doctor_chunkhound_health_fails_when_search_has_no_fixture_reference(tmp_path: Path) -> None:
    runtime, fixture_config, fixture_repo = _health_runtime(tmp_path)
    with mock.patch.object(cure_runtime.shutil, "which", return_value="/usr/bin/chunkhound"), \
        mock.patch.object(cure_runtime, "index_fixture_for_health_check", return_value=_fake_indexed_fixture(fixture_config, fixture_repo)), \
        mock.patch.object(cure_runtime, "run_chunkhound_mcp_preflight", return_value=_preflight_result()), \
        mock.patch.object(cure_runtime, "run_chunkhound_tool", return_value={"ok": True, "result": {"results": []}}):
        check, artifact = cure_runtime._doctor_chunkhound_health_check(runtime)

    assert check.status == "fail"
    assert "search returned no results for fixture" in check.detail
    assert artifact == _preflight_result()


def test_doctor_chunkhound_health_warns_when_research_times_out(tmp_path: Path) -> None:
    runtime, fixture_config, fixture_repo = _health_runtime(tmp_path)
    with mock.patch.object(cure_runtime.shutil, "which", return_value="/usr/bin/chunkhound"), \
        mock.patch.object(cure_runtime, "index_fixture_for_health_check", return_value=_fake_indexed_fixture(fixture_config, fixture_repo)), \
        mock.patch.object(cure_runtime, "run_chunkhound_mcp_preflight", return_value=_preflight_result()), \
        mock.patch.object(
            cure_runtime,
            "run_chunkhound_tool",
            side_effect=[
                {"ok": True, "result": {"results": [{"file_path": str(fixture_repo / "main.py")}] }},
                {"ok": False, "execution_stage_status": "timeout", "error": "timed out"},
            ],
        ):
        check, artifact = cure_runtime._doctor_chunkhound_health_check(runtime)

    assert check.status == "warn"
    assert "code_research timed out" in check.detail
    assert artifact == _preflight_result()


def test_doctor_chunkhound_health_warns_when_research_lacks_fixture_citation(tmp_path: Path) -> None:
    runtime, fixture_config, fixture_repo = _health_runtime(tmp_path)
    with mock.patch.object(cure_runtime.shutil, "which", return_value="/usr/bin/chunkhound"), \
        mock.patch.object(cure_runtime, "index_fixture_for_health_check", return_value=_fake_indexed_fixture(fixture_config, fixture_repo)), \
        mock.patch.object(cure_runtime, "run_chunkhound_mcp_preflight", return_value=_preflight_result()), \
        mock.patch.object(
            cure_runtime,
            "run_chunkhound_tool",
            side_effect=[
                {"ok": True, "result": {"results": [{"file_path": str(fixture_repo / "main.py")}] }},
                {"ok": True, "result": "No citations here."},
            ],
        ):
        check, artifact = cure_runtime._doctor_chunkhound_health_check(runtime)

    assert check.status == "warn"
    assert "code_research returned no fixture citation" in check.detail
    assert artifact == _preflight_result()


def test_doctor_chunkhound_health_warns_when_config_lacks_api_credentials(tmp_path: Path) -> None:
    config = _recommended_chunkhound_config()
    config["embedding"] = {**config["embedding"], "api_key": ""}  # type: ignore[index]
    config["llm"] = {**config["llm"], "api_key": ""}  # type: ignore[index]
    runtime = _write_runtime_config(tmp_path, config)
    with mock.patch.object(cure_runtime, "index_fixture_for_health_check") as index_mock:
        check, artifact = cure_runtime._doctor_chunkhound_health_check(runtime)

    assert check.status == "warn"
    assert "skipping runtime check: chunkhound config missing embedding/LLM api_key" in check.detail
    assert artifact is None
    index_mock.assert_not_called()


def test_doctor_runtime_checks_skip_health_when_chunkhound_binary_fails(tmp_path: Path) -> None:
    runtime = _write_runtime_config(tmp_path, _recommended_chunkhound_config())
    with mock.patch.object(cure_runtime.shutil, "which", side_effect=lambda name: None if name == "chunkhound" else f"/usr/bin/{name}"), \
        mock.patch.object(cure_runtime, "_doctor_chunkhound_health_check") as health_mock:
        checks = cure_runtime._doctor_runtime_checks(runtime)

    by_name = {item.name: item for item in checks}
    assert by_name["chunkhound-config-validate"].status == "ok"
    assert by_name["chunkhound"].status == "fail"
    assert "chunkhound-health" not in by_name
    health_mock.assert_not_called()


def test_doctor_runtime_checks_skip_health_when_config_validate_fails(tmp_path: Path) -> None:
    runtime = _write_runtime_config(tmp_path, {"llm": _recommended_chunkhound_config()["llm"]})
    with mock.patch.object(cure_runtime.shutil, "which", return_value="/usr/bin/tool"), \
        mock.patch.object(cure_runtime, "_doctor_chunkhound_health_check") as health_mock:
        checks = cure_runtime._doctor_runtime_checks(runtime)

    by_name = {item.name: item for item in checks}
    assert by_name["chunkhound-config"].status == "ok"
    assert by_name["chunkhound-config-validate"].status == "fail"
    assert "chunkhound-health" not in by_name
    health_mock.assert_not_called()


def test_doctor_runtime_checks_skip_validate_and_health_when_chunkhound_config_fails(tmp_path: Path) -> None:
    runtime = _write_runtime_config(tmp_path, None)
    with mock.patch.object(cure_runtime.shutil, "which", return_value="/usr/bin/tool"), \
        mock.patch.object(cure_runtime, "_doctor_chunkhound_health_check") as health_mock:
        checks = cure_runtime._doctor_runtime_checks(runtime)

    by_name = {item.name: item for item in checks}
    assert by_name["chunkhound-config"].status == "fail"
    assert "chunkhound-config-validate" not in by_name
    assert "chunkhound-health" not in by_name
    health_mock.assert_not_called()


def test_doctor_runtime_checks_run_health_when_config_validate_warns(tmp_path: Path) -> None:
    config = _recommended_chunkhound_config()
    config["embedding"] = {**config["embedding"], "provider": "openai"}  # type: ignore[arg-type]
    runtime = _write_runtime_config(tmp_path, config)
    expected = cure_runtime.DoctorCheck(name="chunkhound-health", status="warn", detail="skipping runtime check")
    with mock.patch.object(cure_runtime.shutil, "which", return_value="/usr/bin/tool"), \
        mock.patch.object(cure_runtime, "_doctor_chunkhound_health_check", return_value=(expected, None)) as health_mock:
        checks = cure_runtime._doctor_runtime_checks(runtime, artifacts={})

    by_name = {item.name: item for item in checks}
    assert by_name["chunkhound-config-validate"].status == "warn"
    assert by_name["chunkhound-health"] == expected
    health_mock.assert_called_once_with(runtime)


def test_doctor_runtime_payload_includes_chunkhound_health_artifact(tmp_path: Path) -> None:
    runtime = _write_runtime_config(tmp_path, _recommended_chunkhound_config())
    payload = cure_runtime._doctor_runtime_payload(runtime, artifacts={"chunkhound_health": _preflight_result()})

    assert payload["chunkhound_health"] == {
        "preflight_stage": "complete",
        "available_tools": ["search", "code_research"],
        "missing_tools": [],
        "mcp_transport": "json_line",
        "daemon_pid": 321,
        "daemon_socket": "/tmp/chunkhound.sock",
        "daemon_log": "/tmp/chunkhound.log",
        "daemon_runtime_dir": "/tmp/chunkhound-runtime",
        "time_ms": 42.0,
    }


def test_doctor_runtime_payload_omits_chunkhound_health_when_skipped(tmp_path: Path) -> None:
    runtime = _write_runtime_config(tmp_path, _recommended_chunkhound_config())
    payload = cure_runtime._doctor_runtime_payload(runtime, artifacts={})

    assert "chunkhound_health" not in payload


def test_doctor_flow_passes_shared_artifacts_to_checks_and_payload(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runtime = _write_runtime_config(tmp_path, _recommended_chunkhound_config())

    def fake_checks(*args: object, artifacts: dict[str, object] | None = None, **kwargs: object) -> list[cure_runtime.DoctorCheck]:
        assert artifacts is not None
        artifacts["chunkhound_health"] = _preflight_result()
        return [cure_runtime.DoctorCheck(name="chunkhound-health", status="ok", detail="ok")]

    def fake_payload(*args: object, artifacts: dict[str, object] | None = None, **kwargs: object) -> dict[str, object]:
        assert artifacts is not None
        assert artifacts["chunkhound_health"] == _preflight_result()
        return {"chunkhound_health": {"preflight_stage": "complete"}}

    with mock.patch.object(cure_commands, "_doctor_runtime_checks", side_effect=fake_checks), \
        mock.patch.object(cure_commands, "_doctor_runtime_payload", side_effect=fake_payload):
        rc = cure_commands.doctor_flow(argparse.Namespace(json_output=True, pr_url=None, agent_runtime_profile=None), runtime=runtime)

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["chunkhound_health"] == {"preflight_stage": "complete"}


def test_redact_secrets_strips_json_api_key() -> None:
    result = cure_runtime._redact_secrets('{"api_key": "sk-secret-123"}')
    assert "sk-secret-123" not in result
    assert "[REDACTED]" in result


def test_redact_secrets_strips_python_api_key() -> None:
    assert "[REDACTED]" in cure_runtime._redact_secrets("'api_key': 'sk-secret-123'")
    assert "sk-secret-123" not in cure_runtime._redact_secrets("'api_key': 'sk-secret-123'")


def test_redact_secrets_preserves_non_secret_text() -> None:
    result = cure_runtime._redact_secrets('{"name": "test", "value": 42}')
    assert '"name"' in result
    assert '42' in result


def test_search_result_references_fixture_matches_file_path() -> None:
    assert cure_runtime._search_result_references_fixture(
        {"results": [{"file_path": "/tmp/fixture/main.py"}]}
    )
    assert cure_runtime._search_result_references_fixture(
        {"results": [{"file_path": "/tmp/fixture/utils.py"}]}
    )


def test_search_result_references_fixture_rejects_non_matching() -> None:
    assert not cure_runtime._search_result_references_fixture(
        {"results": [{"file_path": "/tmp/other/demo.py"}]}
    )
    assert not cure_runtime._search_result_references_fixture({"results": []})
    assert not cure_runtime._search_result_references_fixture({})


def test_research_result_references_fixture_matches_bracketed() -> None:
    assert cure_runtime._research_result_references_fixture("See [main.py](main.py) for details.")
    assert cure_runtime._research_result_references_fixture("Reference [utils.py].")


def test_research_result_references_fixture_matches_backtick() -> None:
    assert cure_runtime._research_result_references_fixture("Use `README.md` for context.")


def test_research_result_references_fixture_rejects_bare_filename() -> None:
    assert not cure_runtime._research_result_references_fixture("Just main.py without brackets.")
    assert not cure_runtime._research_result_references_fixture("No references here.")
