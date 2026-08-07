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
from typing import Any

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
)
from test_chunkhound_daemon_aware_source import (
    _A22_LIVE_RECEIPT_CASES,
    _assert_exact_a22_source_delta,
    _assert_exact_a22_watchman_source_delta,
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


def _register_tap05_ledger_persistence(
    request: pytest.FixtureRequest,
    classification_ledger_path: Path,
    event_ledger: list[dict[str, object]],
) -> Callable[[], None]:
    """Persist once on explicit success or any later pytest teardown path."""
    ledger_persisted = False

    def persist_classification_ledger() -> None:
        nonlocal ledger_persisted
        if ledger_persisted:
            return
        _write_private_json_exclusive(classification_ledger_path, event_ledger)
        ledger_persisted = True

    request.addfinalizer(persist_classification_ledger)
    return persist_classification_ledger


def _assert_tap05_classification_ledger(
    persisted_ledger: list[dict[str, object]],
) -> None:
    """Validate sanitized open-vocabulary Watchman ordering evidence."""
    degraded_indexes = [
        index
        for index, event in enumerate(persisted_ledger)
        if event.get("classification") == "fresh_instance_degraded"
    ]
    ready_indexes = [
        index
        for index, event in enumerate(persisted_ledger)
        if event.get("classification") == "ready"
    ]
    search_indexes = [
        index
        for index, event in enumerate(persisted_ledger)
        if event.get("event") == "search_request"
    ]
    assert degraded_indexes, persisted_ledger
    assert all(
        persisted_ledger[index].get("live_indexing_state") not in {"stalled", "missing"}
        for index in degraded_indexes
    ), persisted_ledger
    assert ready_indexes, persisted_ledger
    assert degraded_indexes[0] < ready_indexes[0], persisted_ledger
    assert all(index > ready_indexes[0] for index in search_indexes), persisted_ledger
    classifications = [
        event.get("classification")
        for event in persisted_ledger
        if event.get("event") == "daemon_status"
    ]
    first_ready = classifications.index("ready")
    assert "fresh_instance_degraded" in classifications[:first_ready]
    assert set(classifications[:first_ready]) <= {
        "fresh_instance_degraded",
        "initializing",
    }
    assert classifications[first_ready:] == ["ready"] * (
        len(classifications) - first_ready
    )
    assert all(
        set(event)
        <= {
            "event",
            "classification",
            "status",
            "query_ready",
            "scan_error_clear",
            "realtime_error_clear",
            "resync_error_clear",
            "service_state",
            "live_indexing_state",
            "needs_resync",
            "last_reason",
            "loss_of_sync_reason",
            "backend",
            "search_ordinal",
        }
        for event in persisted_ledger
    ), persisted_ledger


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


def _effective_realtime_filter_report(
    *,
    binary: str,
    repo: Path,
    config: Path,
    environment: dict[str, str],
    relative_paths: list[str],
) -> dict[str, object]:
    """Directly exercise the installed RealtimePathFilter for exact paths."""
    assert relative_paths and len(relative_paths) == len(set(relative_paths))
    for relative in relative_paths:
        path = Path(relative)
        assert (
            relative == path.as_posix()
            and not path.is_absolute()
            and ".." not in path.parts
        )

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
relative_paths = json.loads(sys.argv[3])
args = create_parser().parse_args(["mcp", "--config", str(config_path), str(repo)])
filter_ = RealtimePathFilter(config=Config(args), root_path=repo)
print(json.dumps({
    "ok": True,
    "excluded_paths": {
        relative: not filter_.should_index(repo / relative)
        for relative in relative_paths
    },
    "degraded": filter_.is_degraded,
}, sort_keys=True))
"""
    result = subprocess.run(
        [
            runtime_python,
            "-c",
            script,
            str(repo),
            str(config),
            json.dumps(relative_paths),
        ],
        cwd=repo,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    report = json.loads(result.stdout)
    assert type(report) is dict and set(report) == {
        "ok",
        "excluded_paths",
        "degraded",
    }, report
    assert report["ok"] is True and type(report["degraded"]) is bool
    assert report["excluded_paths"] == {relative: True for relative in relative_paths}
    return report


def _effective_daemon_log_filter_report(
    *, binary: str, repo: Path, config: Path, environment: dict[str, str]
) -> dict[str, bool]:
    report = _effective_realtime_filter_report(
        binary=binary,
        repo=repo,
        config=config,
        environment=environment,
        relative_paths=[".chunkhound/daemon.log"],
    )
    return {
        "ok": report["ok"] is True,
        "excluded": report["excluded_paths"] == {".chunkhound/daemon.log": True},
        "degraded": report["degraded"] is True,
    }


def _write_private_json_exclusive(path: Path, payload: object) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    assert path.stat().st_mode & 0o777 == 0o600


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
    if binary is None or os.environ.get("CURE_CHUNKHOUND_FAKE_BIN"):
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

        readiness = lease.adjudicate_expected_session(
            receipt,
            expected_generation=owned_generation,
            readiness_timeout_seconds=600.0,
        )
        assert readiness.launch_identity == identity
        if total_chunks:
            assert readiness.search_witness is not None
            assert readiness.search_witness.relative_path == "fixture.py"
            assert readiness.search_witness.literal in before_source.decode("utf-8")
            assert isinstance(readiness.expected_generation, ExpectedGenerationEvidence)
            client_witness: ExpectedSearchWitness | None = readiness.search_witness
        else:
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
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    *,
    existing_parent: bool,
    expected_chunks: int,
    exercise_clients: bool,
) -> None:
    artifact_root = os.environ.get("CURE_TAP05_ARTIFACT_ROOT")
    if artifact_root is None:
        tmp_path = tmp_path_factory.mktemp("ordinary")
    else:
        case_kind = "nonempty" if expected_chunks else "zero"
        parent_kind = "existing" if existing_parent else "absent"
        tmp_path = Path(artifact_root) / f"ordinary-{case_kind}-{parent_kind}"
        tmp_path.mkdir(mode=0o700, parents=False, exist_ok=False)
        tmp_path.chmod(0o700)
    _exercise_live_index(
        tmp_path,
        monkeypatch,
        include=["**/*.py"],
        expected_chunks=expected_chunks,
        exercise_clients=exercise_clients,
        existing_parent=existing_parent,
    )


@pytest.mark.skipif(
    os.environ.get("CURE_RUN_LIVE_CHUNKHOUND_WATCHMAN") != "1",
    reason=(
        "set CURE_RUN_LIVE_CHUNKHOUND_WATCHMAN=1 to run the dedicated "
        "Watchman readiness proof"
    ),
)
def test_tap05_watchman_fresh_instance_degraded_then_ready_live(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    """TAP-05: retain one fresh Watchman generation through benign resync."""
    artifact_root = os.environ.get("CURE_TAP05_ARTIFACT_ROOT")
    if artifact_root is None:
        tmp_path = tmp_path_factory.mktemp("w")
    else:
        artifact_parent = Path(artifact_root).expanduser().resolve(strict=False)
        assert artifact_parent.is_dir() and not artifact_parent.is_symlink()
        tmp_path = artifact_parent / "watchman-fresh-instance"
        tmp_path.mkdir(mode=0o700, parents=False, exist_ok=False)
        tmp_path.chmod(0o700)
    binary = shutil.which("chunkhound")
    if binary is None or os.environ.get("CURE_CHUNKHOUND_FAKE_BIN"):
        pytest.skip("installed chunkhound executable is unavailable")
    binary = str(Path(binary).resolve())

    repo = tmp_path / "repo"
    runtime = tmp_path / "runtime"
    home = tmp_path / "home"
    xdg_runtime = tmp_path / "xdg-runtime"
    temp_dir = tmp_path / "tmp"
    source = _write_repo(repo, source_matches_include=True)
    runtime.mkdir()
    home.mkdir()
    xdg_runtime.mkdir(mode=0o700)
    temp_dir.mkdir(mode=0o700)
    config = runtime / "chunkhound-watchman.json"
    database = runtime / "chunks.db"
    classification_ledger_path = tmp_path / "tap05-classification-ledger.json"
    event_ledger: list[dict[str, object]] = []

    # From this point onward every success or failure attempts a private, fsynced,
    # sanitized ledger.  The explicit success call below allows read-back auditing;
    # the finalizer covers every earlier setup/open/adjudication/cleanup failure.
    persist_classification_ledger = _register_tap05_ledger_persistence(
        request, classification_ledger_path, event_ledger
    )

    _prepare_a22_live_parent(repo, existing_parent=False)
    _write_a22_live_config(
        config_path=config,
        database_path=database,
        include=["**/*.py"],
    )
    materialized_config = json.loads(config.read_text(encoding="utf-8"))
    materialized_config["indexing"]["realtime_backend"] = "watchman"
    config.write_text(
        json.dumps(materialized_config, sort_keys=True) + "\n", encoding="utf-8"
    )
    assert materialized_config["indexing"] == {
        "exclude": ["**/.chunkhound/**"],
        "include": ["**/*.py"],
        "realtime_backend": "watchman",
    }

    environment = {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONSAFEPATH": "1",
        "TMPDIR": str(temp_dir),
        "XDG_RUNTIME_DIR": str(xdg_runtime),
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)

    daemon_parent = repo / ".chunkhound"
    daemon_log = daemon_parent / "daemon.log"
    assert not daemon_parent.exists() and not daemon_parent.is_symlink()
    before_source = source.read_bytes()
    before_manifest = _tree_manifest(repo)
    assert _effective_daemon_log_filter_report(
        binary=binary,
        repo=repo,
        config=config,
        environment=environment,
    ) == {"ok": True, "excluded": True, "degraded": False}
    total_chunks = _index(
        binary=binary,
        repo=repo,
        runtime=runtime,
        config=config,
        environment=environment,
    )
    assert total_chunks == 1
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
    receipt = ExpectedSessionReceiptV1(
        schema_version=1,
        canonical_root=identity.canonical_root,
        reviewed_head=_git(repo, "rev-parse", "HEAD").strip(),
        resolved_config_path=identity.resolved_config_path,
        config_digest=identity.config_digest,
        resolved_database_path=identity.resolved_database_path,
        total_chunks=total_chunks,
        launch_identity_projection=identity,
    )
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
    adjudication_error: BaseException | None = None
    readiness = None
    marker = f"CURE_TAP05_WATCHMAN_{secrets.token_hex(24)}"
    try:
        lease.open()
        assert pre_spawn_observations == [None]
        opened_generation = generation_probe()
        assert opened_generation is not None
        owned_generation = lease.owned_generation
        assert isinstance(owned_generation, ExpectedGenerationEvidence)
        assert daemon_log.is_file() and not daemon_log.is_symlink()

        # Test-only observation of the retained transport.  The single ledger
        # records only non-sensitive classification projections and call order.
        retained_session = getattr(lease, "_session", None)
        assert isinstance(retained_session, JsonRpcSession)
        original_request = retained_session.request

        def project_status(response: dict[str, Any]) -> dict[str, object]:
            projection: dict[str, object] = {
                "event": "daemon_status",
                "classification": "invalid",
            }
            result = response.get("result")
            if not isinstance(result, dict):
                return projection
            content = result.get("content")
            if not isinstance(content, list) or len(content) != 1:
                return projection
            item = content[0]
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                return projection
            try:
                sample = json.loads(item["text"])
            except (TypeError, json.JSONDecodeError):
                return projection
            if not isinstance(sample, dict):
                return projection

            scan = sample.get("scan_progress")
            realtime = scan.get("realtime") if isinstance(scan, dict) else None
            resync = realtime.get("resync") if isinstance(realtime, dict) else None
            details = resync.get("last_details") if isinstance(resync, dict) else None
            status = sample.get("status")
            query_ready = sample.get("query_ready")
            service_state = (
                realtime.get("service_state") if isinstance(realtime, dict) else None
            )
            live_indexing_state = (
                realtime.get("live_indexing_state")
                if isinstance(realtime, dict)
                else None
            )
            needs_resync = (
                resync.get("needs_resync") if isinstance(resync, dict) else None
            )
            last_reason = (
                resync.get("last_reason") if isinstance(resync, dict) else None
            )
            loss_reason = (
                details.get("loss_of_sync_reason")
                if isinstance(details, dict)
                else None
            )
            backend = details.get("backend") if isinstance(details, dict) else None
            projection.update(
                {
                    "status": status
                    if status in {"initializing", "ready", "degraded"}
                    else "other",
                    "query_ready": query_ready
                    if isinstance(query_ready, bool)
                    else None,
                    "scan_error_clear": isinstance(scan, dict)
                    and scan.get("scan_error") is None,
                    "realtime_error_clear": isinstance(realtime, dict)
                    and "last_error" in realtime
                    and realtime["last_error"] is None,
                    "resync_error_clear": isinstance(resync, dict)
                    and "last_error" in resync
                    and resync["last_error"] is None,
                    "service_state": "degraded"
                    if service_state == "degraded"
                    else "non_degraded"
                    if isinstance(service_state, str)
                    else "missing",
                    "live_indexing_state": live_indexing_state
                    if live_indexing_state in {"degraded", "stalled"}
                    else "not_stalled"
                    if isinstance(live_indexing_state, str)
                    else "missing",
                    "needs_resync": needs_resync
                    if isinstance(needs_resync, bool)
                    else None,
                    "last_reason": "realtime_loss_of_sync"
                    if last_reason == "realtime_loss_of_sync"
                    else "other",
                    "loss_of_sync_reason": "fresh_instance"
                    if loss_reason == "fresh_instance"
                    else "other",
                    "backend": "watchman" if backend == "watchman" else "other",
                }
            )
            exact_top = (
                set(sample)
                == {"status", "server_version", "query_ready", "scan_progress"}
                and isinstance(sample.get("server_version"), str)
                and isinstance(sample.get("query_ready"), bool)
                and isinstance(scan, dict)
            )
            if (
                exact_top
                and sample["status"] == "ready"
                and sample["query_ready"] is True
            ):
                projection["classification"] = "ready"
            elif (
                exact_top
                and sample["status"] == "initializing"
                and sample["query_ready"] is False
            ):
                projection["classification"] = "initializing"
            elif (
                sample.get("status") == "degraded"
                and isinstance(scan, dict)
                and isinstance(realtime, dict)
                and isinstance(resync, dict)
                and isinstance(details, dict)
                and projection["scan_error_clear"] is True
                and projection["realtime_error_clear"] is True
                and projection["resync_error_clear"] is True
                and projection["service_state"] == "non_degraded"
                and projection["live_indexing_state"] != "stalled"
                and projection["live_indexing_state"] != "missing"
                and projection["needs_resync"] is True
                and projection["last_reason"] == "realtime_loss_of_sync"
                and projection["loss_of_sync_reason"] == "fresh_instance"
                and projection["backend"] == "watchman"
            ):
                projection["classification"] = "fresh_instance_degraded"
            return projection

        def recording_request(
            method: str,
            params: dict[str, Any] | None = None,
            *,
            stage: str,
            timeout_seconds: float,
            heartbeat_enabled: bool = False,
            heartbeat_label: str | None = None,
        ) -> dict[str, Any]:
            if (
                method == "tools/call"
                and isinstance(params, dict)
                and params.get("name") == "search"
            ):
                event_ledger.append(
                    {"event": "search_request", "search_ordinal": len(event_ledger)}
                )
            response = original_request(
                method,
                params,
                stage=stage,
                timeout_seconds=timeout_seconds,
                heartbeat_enabled=heartbeat_enabled,
                heartbeat_label=heartbeat_label,
            )
            if method == "tools/call" and params == {
                "name": "daemon_status",
                "arguments": {},
            }:
                event_ledger.append(project_status(response))
            return response

        monkeypatch.setattr(retained_session, "request", recording_request)
        try:
            readiness = lease.adjudicate_expected_session(
                receipt,
                expected_generation=owned_generation,
                readiness_timeout_seconds=600.0,
            )
        except BaseException as exc:
            adjudication_error = exc

        if adjudication_error is None:
            assert readiness is not None
            assert readiness.launch_identity == identity
            assert readiness.search_witness is not None
            assert readiness.search_witness.relative_path == "fixture.py"
            assert readiness.search_witness.literal in before_source.decode("utf-8")
            assert isinstance(readiness.expected_generation, ExpectedGenerationEvidence)
            assert generation_probe() == opened_generation

            with daemon_log.open("a", encoding="utf-8") as handle:
                handle.write(marker + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            time.sleep(1.25)
            assert (
                _native_tool_text(
                    retained_session,
                    name="search",
                    arguments={
                        "type": "regex",
                        "query": re.escape(marker),
                        "path": ".chunkhound/daemon.log",
                    },
                    expect_error=False,
                )
                == "No results found."
            )
            assert generation_probe() == opened_generation
    finally:
        lease.close()

    _wait_for_release(generation_probe)
    assert generation_probe() is None
    assert lease.owned_generation is None
    assert source.read_bytes() == before_source
    assert _git(repo, "status", "--porcelain") == "?? .chunkhound/\n"
    persist_classification_ledger()
    persisted_ledger = json.loads(
        classification_ledger_path.read_text(encoding="utf-8")
    )
    assert persisted_ledger == event_ledger
    _assert_tap05_classification_ledger(persisted_ledger)
    if adjudication_error is not None:
        raise adjudication_error

    after_manifest = _tree_manifest(repo)
    _assert_exact_a22_watchman_source_delta(before_manifest, after_manifest)
    before_paths = {row[0] for row in before_manifest}
    materialized_watchman_paths = sorted(
        row[0]
        for row in after_manifest
        if row[0] not in before_paths
        and (
            row[0] == ".chunkhound/watchman"
            or row[0].startswith(".chunkhound/watchman/")
        )
    )
    materialized_watchman_files = sorted(
        row[0]
        for row in after_manifest
        if row[0] not in before_paths
        and row[1] == "file"
        and row[0].startswith(".chunkhound/watchman/")
    )
    assert materialized_watchman_paths
    assert materialized_watchman_files
    watchman_filter_report = _effective_realtime_filter_report(
        binary=binary,
        repo=repo,
        config=config,
        environment=environment,
        relative_paths=materialized_watchman_paths,
    )
    assert watchman_filter_report["degraded"] is False
    assert watchman_filter_report["excluded_paths"] == {
        relative: True for relative in materialized_watchman_paths
    }
    assert daemon_parent.is_dir() and not daemon_parent.is_symlink()
    assert daemon_log.is_file() and not daemon_log.is_symlink()
    assert database.is_file()
    assert _effective_daemon_log_filter_report(
        binary=binary,
        repo=repo,
        config=config,
        environment=environment,
    ) == {"ok": True, "excluded": True, "degraded": False}
    for path in database.parent.glob(database.name + "*"):
        if path.is_file():
            assert marker.encode("utf-8") not in path.read_bytes()
