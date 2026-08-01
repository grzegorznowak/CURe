from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import time

import pytest

import cure_chunkhound
from cure_chunkhound import JsonRpcSession, bootstrap_chunkhound_mcp_session
from cure_chunkhound_lifecycle import (
    ChunkHoundDaemonLease,
    ExpectedGenerationEvidence,
    ExpectedSearchWitness,
    ExpectedSessionReceiptV1,
    NativeDaemonReadinessSignal,
    _require_healthy_native_status,
    _require_native_search_witness,
    build_launch_identity,
    observe_native_daemon_generation,
    select_git_tracked_source_witness,
)
from test_chunkhound_daemon_aware_source import (
    _A22_LIVE_RECEIPT_CASES,
    _assert_exact_a22_source_delta,
    _prepare_a22_live_parent,
    _tree_manifest,
    _write_a22_live_config,
)


pytestmark = [
    pytest.mark.skipif(
        os.environ.get("CURE_RUN_LIVE_CHUNKHOUND") != "1",
        reason="set CURE_RUN_LIVE_CHUNKHOUND=1 to run the installed-ChunkHound canary",
    ),
    pytest.mark.skipif(
        sys.platform != "linux", reason="native daemon canary is Linux-only"
    ),
]


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return result.stdout


def _write_repo(repo: Path, *, source_matches_include: bool) -> Path:
    repo.mkdir()
    source = repo / ("fixture.py" if source_matches_include else "fixture.txt")
    source.write_text("daemon_keeper_canary_literal = True\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", source.name)
    _git(
        repo,
        "-c",
        "user.name=CURe canary",
        "-c",
        "user.email=cure-canary@example.invalid",
        "commit",
        "-qm",
        "canary fixture",
    )
    return source


def _index(
    *,
    binary: str,
    repo: Path,
    runtime: Path,
    config: Path,
    environment: dict[str, str],
) -> int:
    result = subprocess.run(
        [binary, "index", str(repo), "--config", str(config), "--no-embeddings"],
        cwd=runtime,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    matches = re.findall(r"(?im)^Total chunks:\s*(\d+)\s*$", result.stdout)
    assert len(matches) == 1, result.stdout[-4000:]
    assert re.findall(r"(?im)^Errors:\s*(\d+)\s+files\s*$", result.stdout) == ["0"]
    return int(matches[0])


def _native_tool_text(
    session: JsonRpcSession,
    *,
    name: str,
    arguments: dict[str, object],
    expect_error: bool,
) -> str:
    response = session.request(
        "tools/call",
        {"name": name, "arguments": arguments},
        stage=f"tools/call:{name}",
        timeout_seconds=60,
    )
    assert "error" not in response, response
    result = response.get("result")
    assert isinstance(result, dict), response
    assert result.get("isError") is expect_error, result
    assert set(result) == {"content", "isError"}, result
    content = result.get("content")
    assert isinstance(content, list) and len(content) == 1, result
    item = content[0]
    assert isinstance(item, dict) and set(item) == {"type", "text"}, item
    assert item.get("type") == "text" and isinstance(item.get("text"), str), item
    return item["text"]


def _effective_daemon_log_filter_report(
    *, binary: str, repo: Path, config: Path, environment: dict[str, str]
) -> dict[str, bool]:
    launcher = Path(binary)
    shebang = launcher.read_text(encoding="utf-8").splitlines()[0]
    assert shebang.startswith("#!") and shebang[2:]
    runtime_python = shebang[2:]
    script = """
import json
import sys
from pathlib import Path
from chunkhound.api.cli.main import create_parser
from chunkhound.core.config.config import Config
from chunkhound.services.realtime_path_filter import RealtimePathFilter

repo = Path(sys.argv[1]).resolve()
config_path = Path(sys.argv[2]).resolve()
args = create_parser().parse_args(["mcp", "--config", str(config_path), str(repo)])
filter_ = RealtimePathFilter(config=Config(args), root_path=repo)
print(json.dumps({
    "ok": True,
    "excluded": not filter_.should_index(repo / ".chunkhound" / "daemon.log"),
    "degraded": filter_.is_degraded,
}, sort_keys=True))
"""
    result = subprocess.run(
        [runtime_python, "-c", script, str(repo), str(config)],
        cwd=repo,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    report = json.loads(result.stdout)
    assert type(report) is dict and set(report) == {"ok", "excluded", "degraded"}, (
        report
    )
    assert report["ok"] is True
    assert type(report["excluded"]) is bool and type(report["degraded"]) is bool
    return report


def _ordinary_client(
    *,
    binary: str,
    repo: Path,
    runtime: Path,
    config: Path,
    environment: dict[str, str],
    witness: ExpectedSearchWitness | None,
) -> None:
    session = JsonRpcSession(
        config_path=config,
        repo_path=repo,
        cwd=runtime,
        binary=binary,
        env=environment,
    )
    try:
        payload = bootstrap_chunkhound_mcp_session(
            session,
            config_path=config,
            repo_path=repo,
            cwd=runtime,
            binary=binary,
            emit_stage_lines=False,
        )
        assert payload.get("ok") is True, payload
        if witness is None:
            assert (
                _require_healthy_native_status(session)
                is NativeDaemonReadinessSignal.READY
            )
        else:
            _require_native_search_witness(session, witness)
    finally:
        session.close()


def _run_a22_receipt_client_concurrency(
    *,
    total_chunks: int,
    exercise_clients: bool,
    witness: ExpectedSearchWitness | None,
    call_factory: Callable[[ExpectedSearchWitness | None], Callable[[], None]],
) -> None:
    assert total_chunks >= 0
    assert (witness is None) is (total_chunks == 0)
    if not exercise_clients:
        return

    call = call_factory(witness)
    call()
    time.sleep(0.25)
    call()
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(call) for _ in range(8)]
        for future in futures:
            future.result(timeout=120)


def _wait_for_release(
    probe: Callable[[], object | None], *, timeout: float = 20.0
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if probe() is None:
            return
        time.sleep(0.1)
    pytest.fail("installed ChunkHound daemon generation did not release")


def _exercise_live_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    include: list[str],
    expected_chunks: int,
    exercise_clients: bool,
    existing_parent: bool,
) -> None:
    binary = shutil.which("chunkhound")
    if binary is None:
        pytest.skip("installed chunkhound executable is unavailable")
    binary = str(Path(binary).resolve())

    repo = tmp_path / "repo"
    runtime = tmp_path / "runtime"
    home = tmp_path / "home"
    xdg_runtime = tmp_path / "xdg-runtime"
    source = _write_repo(repo, source_matches_include=expected_chunks > 0)
    runtime.mkdir()
    home.mkdir()
    xdg_runtime.mkdir(mode=0o700)
    config = runtime / "chunkhound.json"
    database = runtime / "chunks.db"
    _prepare_a22_live_parent(repo, existing_parent=existing_parent)
    _write_a22_live_config(
        config_path=config,
        database_path=database,
        include=include,
    )
    materialized_config = json.loads(config.read_text(encoding="utf-8"))
    assert materialized_config["indexing"]["exclude"] == ["**/.chunkhound/**"]
    assert materialized_config["indexing"]["exclude"].count("**/.chunkhound/**") == 1
    environment = {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONSAFEPATH": "1",
        "XDG_RUNTIME_DIR": str(xdg_runtime),
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)

    daemon_parent = repo / ".chunkhound"
    daemon_log = daemon_parent / "daemon.log"
    sibling = daemon_parent / "exclusion-sibling.py"
    if existing_parent:
        assert daemon_parent.is_dir() and not daemon_parent.is_symlink()
        assert daemon_parent.lstat().st_mode & 0o7777 == 0o750
        assert sibling.is_file() and not sibling.is_symlink()
        assert sibling.read_bytes() == b"daemon_log_exclusion_sibling_literal = True\n"
        assert sibling.lstat().st_mode & 0o7777 == 0o640
    else:
        assert not daemon_parent.exists() and not daemon_parent.is_symlink()
    assert not daemon_log.exists() and not daemon_log.is_symlink()
    before_source = source.read_bytes()
    before_manifest = _tree_manifest(repo)
    filter_report = _effective_daemon_log_filter_report(
        binary=binary,
        repo=repo,
        config=config,
        environment=environment,
    )
    assert filter_report == {"ok": True, "excluded": True, "degraded": False}
    total_chunks = _index(
        binary=binary,
        repo=repo,
        runtime=runtime,
        config=config,
        environment=environment,
    )
    assert total_chunks == expected_chunks
    assert database.is_file()
    assert not daemon_log.exists() and not daemon_log.is_symlink()

    identity = build_launch_identity(
        repo_path=repo,
        config_path=config,
        database_path=database,
        cwd=runtime,
        binary=binary,
        environment=environment,
    )
    reviewed_head = _git(repo, "rev-parse", "HEAD").strip()
    receipt = ExpectedSessionReceiptV1(
        schema_version=1,
        canonical_root=identity.canonical_root,
        reviewed_head=reviewed_head,
        resolved_config_path=identity.resolved_config_path,
        config_digest=identity.config_digest,
        resolved_database_path=identity.resolved_database_path,
        total_chunks=total_chunks,
        launch_identity_projection=identity,
    )
    assert receipt.canonical_root == repo.resolve()
    assert receipt.resolved_config_path == config.resolve()
    assert receipt.resolved_database_path == database.resolve()
    assert receipt.launch_identity_projection == identity
    generation_probe = partial(
        observe_native_daemon_generation,
        repo_path=repo,
        cwd=runtime,
        binary=binary,
        environment=environment,
    )
    pre_spawn_observations: list[object | None] = []

    def validate_immediate_pre_spawn() -> None:
        observed = generation_probe()
        pre_spawn_observations.append(observed)
        assert observed is None
        assert not daemon_log.exists() and not daemon_log.is_symlink()

    assert generation_probe() is None
    lease = ChunkHoundDaemonLease(
        config_path=config,
        repo_path=repo,
        cwd=runtime,
        binary=binary,
        env=environment,
        launch_identity=identity,
        generation_probe=generation_probe,
        pre_spawn_validation=validate_immediate_pre_spawn,
    )
    try:
        assert not daemon_log.exists() and not daemon_log.is_symlink()
        lease.open()
        assert pre_spawn_observations == [None]
        opened_generation = generation_probe()
        assert opened_generation is not None
        owned_generation = lease.owned_generation
        assert isinstance(owned_generation, ExpectedGenerationEvidence)

        def assert_owned_generation_continuity(checkpoint: str) -> None:
            assert generation_probe() == opened_generation, checkpoint
            assert lease.owned_generation is owned_generation, checkpoint

        assert_owned_generation_continuity("opened")
        assert daemon_log.is_file() and not daemon_log.is_symlink()

        if total_chunks:
            witness = select_git_tracked_source_witness(
                repo_path=repo, config_path=config
            )
            assert witness.relative_path == "fixture.py"
            assert witness.literal in before_source.decode("utf-8")
            readiness = lease.adjudicate_expected_session(
                receipt,
                witness=witness,
                expected_generation=owned_generation,
                readiness_timeout_seconds=600.0,
            )
            assert readiness.launch_identity == identity
            assert readiness.search_witness == witness
            assert isinstance(readiness.expected_generation, ExpectedGenerationEvidence)
            client_witness: ExpectedSearchWitness | None = witness
        else:
            readiness = lease.adjudicate_expected_session(
                receipt,
                expected_generation=owned_generation,
                readiness_timeout_seconds=600.0,
            )
            assert readiness.launch_identity == identity
            assert readiness.search_witness is None
            assert readiness.expected_generation is owned_generation
            client_witness = None
        assert_owned_generation_continuity("readiness")

        marker = f"CURE_A22_DAEMON_LOG_{secrets.token_hex(24)}"
        if client_witness is not None:
            assert marker not in client_witness.literal
        with daemon_log.open("a", encoding="utf-8") as handle:
            handle.write(marker + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        time.sleep(1.25)
        assert_owned_generation_continuity("marker")
        assert _effective_daemon_log_filter_report(
            binary=binary,
            repo=repo,
            config=config,
            environment=environment,
        ) == {"ok": True, "excluded": True, "degraded": False}

        native_session = JsonRpcSession(
            config_path=config,
            repo_path=repo,
            cwd=runtime,
            binary=binary,
            env=environment,
        )
        try:
            payload = bootstrap_chunkhound_mcp_session(
                native_session,
                config_path=config,
                repo_path=repo,
                cwd=runtime,
                binary=binary,
                emit_stage_lines=False,
            )
            assert payload.get("ok") is True, payload
            search_output = _native_tool_text(
                native_session,
                name="search",
                arguments={
                    "type": "regex",
                    "query": re.escape(marker),
                    "path": ".chunkhound/daemon.log",
                },
                expect_error=False,
            )
            assert search_output == "No results found."
            research_output = _native_tool_text(
                native_session,
                name="code_research",
                arguments={
                    "query": "What indexed files are under the .chunkhound directory?",
                    "path": ".chunkhound",
                },
                expect_error=False,
            )
            assert marker not in research_output
            assert ".chunkhound/daemon.log" not in research_output
            if existing_parent:
                sibling_output = _native_tool_text(
                    native_session,
                    name="search",
                    arguments={
                        "type": "regex",
                        "query": "daemon_log_exclusion_sibling_literal",
                        "path": ".chunkhound/exclusion-sibling.py",
                    },
                    expect_error=False,
                )
                assert sibling_output == "No results found."
            assert_owned_generation_continuity("native-session")
        finally:
            native_session.close()

        forbidden_sidecar_bytes = (
            marker.encode("utf-8"),
            b".chunkhound/daemon.log",
            b"daemon_log_exclusion_sibling_literal",
        )
        for path in database.parent.glob(database.name + "*"):
            if path.is_file():
                sidecar = path.read_bytes()
                assert all(value not in sidecar for value in forbidden_sidecar_bytes)

        def call_factory(
            selected_witness: ExpectedSearchWitness | None,
        ) -> Callable[[], None]:
            return partial(
                _ordinary_client,
                binary=binary,
                repo=repo,
                runtime=runtime,
                config=config,
                environment=environment,
                witness=selected_witness,
            )

        assert_owned_generation_continuity("pre-client-concurrency")
        _run_a22_receipt_client_concurrency(
            total_chunks=total_chunks,
            exercise_clients=exercise_clients,
            witness=client_witness,
            call_factory=call_factory,
        )
        assert_owned_generation_continuity("post-client-concurrency")

        proof_objects = (
            receipt,
            identity,
            owned_generation,
            readiness,
            readiness.search_witness,
            readiness.expected_generation,
        )
        for proof in proof_objects:
            representation = repr(proof)
            assert marker not in representation
            assert ".chunkhound/daemon.log" not in representation

        assert_owned_generation_continuity("pre-close")
    finally:
        lease.close()

    _wait_for_release(generation_probe)
    assert generation_probe() is None
    assert lease.owned_generation is None
    assert source.read_bytes() == before_source
    assert _git(repo, "status", "--porcelain") == "?? .chunkhound/\n"
    _assert_exact_a22_source_delta(before_manifest, _tree_manifest(repo))
    if existing_parent:
        assert daemon_parent.is_dir() and not daemon_parent.is_symlink()
        assert daemon_parent.lstat().st_mode & 0o7777 == 0o750
        assert sibling.is_file() and not sibling.is_symlink()
        assert sibling.read_bytes() == b"daemon_log_exclusion_sibling_literal = True\n"
        assert sibling.lstat().st_mode & 0o7777 == 0o640
    assert database.is_file()

    safeguard = getattr(cure_chunkhound, "probe_effective_daemon_log_exclusion", None)
    assert callable(safeguard), (
        "A22 RED: CURe lacks the production fail-closed installed-runtime "
        "daemon.log exclusion safeguard"
    )
    assert safeguard(
        repo_path=repo,
        config_path=config,
        cwd=runtime,
        binary=binary,
        env=environment,
    ) == {"ok": True, "excluded": True, "degraded": False}


@pytest.mark.parametrize("existing_parent", [False, True], ids=["absent", "existing"])
@pytest.mark.parametrize(
    ("expected_chunks", "exercise_clients"),
    _A22_LIVE_RECEIPT_CASES,
    ids=["nonempty", "zero"],
)
def test_installed_chunkhound_retains_owned_generation_without_llm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    existing_parent: bool,
    expected_chunks: int,
    exercise_clients: bool,
) -> None:
    _exercise_live_index(
        tmp_path,
        monkeypatch,
        include=["**/*.py"],
        expected_chunks=expected_chunks,
        exercise_clients=exercise_clients,
        existing_parent=existing_parent,
    )
