from __future__ import annotations

from collections.abc import Callable
import ast
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading

import pytest

from _reviewflow_unittest_daemon_aware_impl import _write_fake_chunkhound
from cure_chunkhound_lifecycle import (
    ChunkHoundDaemonLease,
    DaemonGenerationIdentity,
    ExpectedSearchWitness,
    ExpectedSessionReadinessError,
    ExpectedSessionReceiptV1,
    build_launch_identity,
)


def _tree_manifest(root: Path) -> tuple[tuple[str, str, int, str], ...]:
    """Capture path, type, mode, and byte/target digest without following links."""
    rows: list[tuple[str, str, int, str]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        mode = metadata.st_mode & 0o7777
        if path.is_symlink():
            kind = "symlink"
            payload = os.readlink(path).encode("utf-8", errors="surrogateescape")
        elif path.is_dir():
            kind = "directory"
            payload = b""
        elif path.is_file():
            kind = "file"
            payload = path.read_bytes()
        else:
            kind = "other"
            payload = b""
        rows.append((relative, kind, mode, hashlib.sha256(payload).hexdigest()))
    return tuple(rows)


def _assert_exact_a22_source_delta(
    before: tuple[tuple[str, str, int, str], ...],
    after: tuple[tuple[str, str, int, str], ...],
) -> None:
    """Allow only creation of the canonical native daemon log and its parent."""
    before_by_path = {row[0]: row for row in before}
    after_by_path = {row[0]: row for row in after}
    assert len(before_by_path) == len(before)
    assert len(after_by_path) == len(after)

    parent = ".chunkhound"
    daemon_log = ".chunkhound/daemon.log"
    if parent in before_by_path:
        assert before_by_path[parent][1] == "directory"
    if daemon_log in before_by_path:
        assert before_by_path[daemon_log][1] == "file"

    changed = {
        path
        for path in before_by_path.keys() | after_by_path.keys()
        if before_by_path.get(path) != after_by_path.get(path)
    }
    if not changed:
        return

    assert daemon_log not in before_by_path, (
        "a pre-existing canonical daemon.log must remain immutable"
    )
    expected = {daemon_log}
    if parent not in before_by_path:
        expected.add(parent)
    assert changed == expected
    assert parent in after_by_path and after_by_path[parent][1] == "directory"
    assert daemon_log in after_by_path and after_by_path[daemon_log][1] == "file"


_A22_LIVE_RECEIPT_CASES = ((1, True), (0, True))


def _prepare_a22_live_parent(repo: Path, *, existing_parent: bool) -> None:
    """Prepare the two native-daemon parent states used by the A22 canary."""
    parent = repo / ".chunkhound"
    daemon_log = parent / "daemon.log"
    if not existing_parent:
        assert not parent.exists() and not parent.is_symlink()
        return

    parent.mkdir(mode=0o750)
    parent.chmod(0o750)
    sibling = parent / "exclusion-sibling.py"
    sibling.write_bytes(b"daemon_log_exclusion_sibling_literal = True\n")
    sibling.chmod(0o640)
    assert not daemon_log.exists() and not daemon_log.is_symlink()


def _write_a22_live_config(
    *,
    config_path: Path,
    database_path: Path,
    include: list[str],
) -> None:
    """Write the exact installed-runtime config shared by A22 live cases."""
    config_path.write_text(
        json.dumps(
            {
                "database": {"provider": "duckdb", "path": str(database_path)},
                "embedding": {
                    "provider": "voyageai",
                    "api_key": "cure-canary-not-used",
                },
                "indexing": {
                    "include": include,
                    "exclude": ["**/.chunkhound/**"],
                },
                "llm": {
                    "provider": "openai",
                    "api_key": "cure-canary-not-used",
                    "model": "gpt-5-nano",
                    "base_url": "http://127.0.0.1:9/v1",
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_source_fixture(root: Path, *, witness: bool = False) -> None:
    root.mkdir(parents=True)
    source = root / ("fixture.txt" if witness else "source.py")
    source.write_text("fixture\n" if witness else "immutable_source = True\n", encoding="utf-8")
    source.chmod(0o640)
    executable = root / "tool.sh"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o751)
    nested = root / "nested"
    nested.mkdir()
    nested.chmod(0o750)
    (nested / "payload.bin").write_bytes(b"\x00\xffsource-boundary\n")
    (root / "source-link").symlink_to(source.name)


@pytest.mark.parametrize(
    "mutation",
    [
        "parent-only",
        "other-path",
        "other-content",
        "other-mode",
        "other-symlink-target",
        "daemon-log-symlink",
        "daemon-log-special",
        "preexisting-parent-mode",
        "preexisting-log-content",
        "preexisting-log-mode",
    ],
)
def test_exact_a22_manifest_rejects_every_unapproved_delta(mutation: str) -> None:
    with tempfile.TemporaryDirectory() as raw_root:
        root = Path(raw_root) / "reviewed"
        _write_source_fixture(root)
        parent = root / ".chunkhound"
        daemon_log = parent / "daemon.log"
        if mutation.startswith("preexisting-"):
            parent.mkdir()
        if mutation.startswith("preexisting-log-"):
            daemon_log.write_bytes(b"immutable pre-existing log\n")
        before = _tree_manifest(root)

        if mutation == "parent-only":
            parent.mkdir()
        elif mutation == "other-path":
            (root / "unexpected.lock").write_bytes(b"residue")
        elif mutation == "other-content":
            (root / "source.py").write_text("mutated\n", encoding="utf-8")
        elif mutation == "other-mode":
            (root / "source.py").chmod(0o600)
        elif mutation == "other-symlink-target":
            (root / "source-link").unlink()
            (root / "source-link").symlink_to("tool.sh")
        elif mutation == "daemon-log-symlink":
            parent.mkdir()
            daemon_log.symlink_to("../source.py")
        elif mutation == "daemon-log-special":
            parent.mkdir()
            os.mkfifo(daemon_log)
        elif mutation == "preexisting-parent-mode":
            parent.chmod(0o700)
        elif mutation == "preexisting-log-content":
            daemon_log.write_bytes(b"rewritten\n")
        elif mutation == "preexisting-log-mode":
            daemon_log.chmod(0o600)
        else:  # pragma: no cover - the parametrization is exhaustive
            raise AssertionError(mutation)

        with pytest.raises(AssertionError):
            _assert_exact_a22_source_delta(before, _tree_manifest(root))


def test_exact_a22_manifest_allows_only_creation_from_absent_state() -> None:
    with tempfile.TemporaryDirectory() as raw_root:
        root = Path(raw_root) / "reviewed"
        _write_source_fixture(root)
        before = _tree_manifest(root)
        parent = root / ".chunkhound"
        parent.mkdir()
        (parent / "daemon.log").write_bytes(b"native diagnostics\n")
        _assert_exact_a22_source_delta(before, _tree_manifest(root))


def test_exact_a22_manifest_keeps_preexisting_parent_and_log_immutable() -> None:
    with tempfile.TemporaryDirectory() as raw_root:
        root = Path(raw_root) / "reviewed"
        _write_source_fixture(root)
        parent = root / ".chunkhound"
        parent.mkdir(mode=0o750)
        before_parent = _tree_manifest(root)
        (parent / "daemon.log").write_bytes(b"new native diagnostics\n")
        _assert_exact_a22_source_delta(before_parent, _tree_manifest(root))
        immutable = _tree_manifest(root)
        _assert_exact_a22_source_delta(immutable, _tree_manifest(root))


def test_keeper_lifecycle_preserves_reviewed_and_operator_source_boundaries() -> None:
    """TAP-06 A22: keeper health/search/close cannot mutate either source tree."""
    with tempfile.TemporaryDirectory() as raw_root:
        root = Path(raw_root)
        reviewed = root / "reviewed-repository"
        operator_checkout = root / "operator-checkout"
        runtime = root / "cure-runtime"
        _write_source_fixture(reviewed, witness=True)
        _write_source_fixture(operator_checkout)
        runtime.mkdir()

        config = runtime / "chunkhound.json"
        config.write_text("{}\n", encoding="utf-8")
        database = runtime / "chunkhound.db"
        database.write_bytes(b"fixture-db")
        binary = runtime / "chunkhound"
        ledger = runtime / "chunkhound-ledger.jsonl"
        _write_fake_chunkhound(
            binary,
            ledger_path=ledger,
            tools_payload=[
                {"name": "search"},
                {"name": "code_research"},
                {"name": "daemon_status"},
            ],
        )
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONSAFEPATH": "1",
        }
        identity = build_launch_identity(
            repo_path=reviewed,
            config_path=config,
            database_path=database,
            cwd=runtime,
            binary=binary,
            environment=environment,
        )
        receipt = ExpectedSessionReceiptV1(
            schema_version=1,
            canonical_root=identity.canonical_root,
            reviewed_head="1" * 40,
            resolved_config_path=identity.resolved_config_path,
            config_digest=identity.config_digest,
            resolved_database_path=identity.resolved_database_path,
            total_chunks=1,
            launch_identity_projection=identity,
        )
        generation = DaemonGenerationIdentity(pid=os.getpid(), process_started_at=1.0)
        before = {
            reviewed: _tree_manifest(reviewed),
            operator_checkout: _tree_manifest(operator_checkout),
        }

        lease = ChunkHoundDaemonLease(
            config_path=config,
            repo_path=reviewed,
            cwd=runtime,
            binary=str(binary),
            env=environment,
            launch_identity=identity,
            generation_probe=lambda: generation,
        )
        try:
            lease.open()
            lease.assert_alive()
            readiness = lease.adjudicate_expected_session(
                receipt,
                witness=ExpectedSearchWitness(
                    relative_path="fixture.txt",
                    literal="fixture",
                ),
            )
            assert readiness.launch_identity == identity
        finally:
            lease.close()

        _assert_exact_a22_source_delta(before[reviewed], _tree_manifest(reviewed))
        assert _tree_manifest(operator_checkout) == before[operator_checkout]


def test_a22_live_parent_helper_leaves_absent_parent_for_native_creation() -> None:
    """A22 RED: the shared live fixture leaves the absent-parent route pristine."""
    prepare_parent = globals().get("_prepare_a22_live_parent")
    assert callable(prepare_parent), "_prepare_a22_live_parent helper is required"

    with tempfile.TemporaryDirectory() as raw_root:
        repo = Path(raw_root) / "repo"
        _write_source_fixture(repo)
        prepare_parent(repo, existing_parent=False)

        parent = repo / ".chunkhound"
        daemon_log = parent / "daemon.log"
        assert not parent.exists() and not parent.is_symlink()
        assert not daemon_log.exists() and not daemon_log.is_symlink()
        before = _tree_manifest(repo)

        parent.mkdir()
        daemon_log.write_bytes(b"native diagnostics\n")

        _assert_exact_a22_source_delta(before, _tree_manifest(repo))
        assert parent.is_dir() and not parent.is_symlink()
        assert daemon_log.is_file() and not daemon_log.is_symlink()


def test_a22_live_parent_helper_preserves_existing_real_parent_and_sibling() -> None:
    """A22 RED: the shared live fixture pins the existing-parent boundary."""
    prepare_parent = globals().get("_prepare_a22_live_parent")
    assert callable(prepare_parent), "_prepare_a22_live_parent helper is required"

    with tempfile.TemporaryDirectory() as raw_root:
        repo = Path(raw_root) / "repo"
        _write_source_fixture(repo)
        prepare_parent(repo, existing_parent=True)

        parent = repo / ".chunkhound"
        daemon_log = parent / "daemon.log"
        sibling = parent / "exclusion-sibling.py"
        assert parent.is_dir() and not parent.is_symlink()
        assert parent.lstat().st_mode & 0o7777 == 0o750
        assert not daemon_log.exists() and not daemon_log.is_symlink()
        assert sibling.is_file() and not sibling.is_symlink()
        assert sibling.read_bytes() == b"daemon_log_exclusion_sibling_literal = True\n"
        assert sibling.lstat().st_mode & 0o7777 == 0o640
        parent_mode = parent.lstat().st_mode & 0o7777
        sibling_state = (
            sibling.lstat().st_mode & 0o7777,
            sibling.read_bytes(),
        )
        before = _tree_manifest(repo)

        daemon_log.write_bytes(b"native diagnostics\n")

        _assert_exact_a22_source_delta(before, _tree_manifest(repo))
        assert parent.is_dir() and not parent.is_symlink()
        assert parent.lstat().st_mode & 0o7777 == parent_mode == 0o750
        assert daemon_log.is_file() and not daemon_log.is_symlink()
        assert sibling.is_file() and not sibling.is_symlink()
        assert (
            sibling.lstat().st_mode & 0o7777,
            sibling.read_bytes(),
        ) == sibling_state


def test_a22_live_config_helper_writes_exact_daemon_log_exclusion_once() -> None:
    """A22 RED: the shared live config excludes the native daemon tree exactly."""
    write_config = globals().get("_write_a22_live_config")
    assert callable(write_config), "_write_a22_live_config helper is required"

    with tempfile.TemporaryDirectory() as raw_root:
        root = Path(raw_root)
        config = root / "chunkhound.json"
        database = root / "chunks.db"
        write_config(
            config_path=config,
            database_path=database,
            include=["**/*.py"],
        )

        materialized = json.loads(config.read_text(encoding="utf-8"))
        exclude = materialized["indexing"]["exclude"]
        assert exclude == ["**/.chunkhound/**"]
        assert exclude.count("**/.chunkhound/**") == 1


def test_a22_live_receipt_cases_all_exercise_ordinary_client_concurrency() -> None:
    """A22 RED: every receipt branch runs the same real client workload."""
    cases = globals().get("_A22_LIVE_RECEIPT_CASES")
    assert cases == ((1, True), (0, True))

    live_path = Path(__file__).with_name("test_daemon_aware_chunkhound_live.py")
    module = ast.parse(live_path.read_text(encoding="utf-8"))
    exercise = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "_exercise_live_index"
    )
    receipt_branch_index = next(
        index
        for index, statement in enumerate(exercise.body)
        if isinstance(statement, ast.Try)
        for index, nested in enumerate(statement.body)
        if isinstance(nested, ast.If)
        and isinstance(nested.test, ast.Name)
        and nested.test.id == "total_chunks"
    )
    try_body = next(statement for statement in exercise.body if isinstance(statement, ast.Try)).body
    shared_calls = [
        statement.value
        for statement in try_body[receipt_branch_index + 1 :]
        if isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Name)
        and statement.value.func.id == "_run_a22_receipt_client_concurrency"
    ]
    assert len(shared_calls) == 1, (
        "the receipt-client route must be an unconditional direct statement after "
        "the nonempty/zero receipt split"
    )

    from test_daemon_aware_chunkhound_live import (
        _run_a22_receipt_client_concurrency,
    )

    for total_chunks, witness in (
        (1, ExpectedSearchWitness(relative_path="fixture.py", literal="fixture")),
        (0, None),
    ):
        lock = threading.Lock()
        worker_barrier = threading.Barrier(8, timeout=5)
        ordinals: list[int] = []
        worker_threads: set[int] = set()
        selected_witnesses: list[ExpectedSearchWitness | None] = []

        def client_call() -> None:
            with lock:
                ordinal = len(ordinals) + 1
                ordinals.append(ordinal)
                if ordinal > 2:
                    worker_threads.add(threading.get_ident())
            if ordinal > 2:
                worker_barrier.wait()

        def call_factory(
            selected_witness: ExpectedSearchWitness | None,
        ) -> Callable[[], None]:
            selected_witnesses.append(selected_witness)
            return client_call

        _run_a22_receipt_client_concurrency(
            total_chunks=total_chunks,
            exercise_clients=True,
            witness=witness,
            call_factory=call_factory,
        )
        assert selected_witnesses == [witness]
        assert ordinals == list(range(1, 11))
        assert len(worker_threads) == 8


def test_a22_nonempty_ordinary_client_rejects_literal_bearing_malformed_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A22 RED: ordinary clients use the strict native witness parser."""
    import test_daemon_aware_chunkhound_live as live

    closed: list[bool] = []

    class LiteralOnlySession:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def request(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            return {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "content": [{"type": "text", "text": "fixture literal"}],
                    "isError": False,
                },
            }

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(live, "JsonRpcSession", LiteralOnlySession)
    monkeypatch.setattr(
        live,
        "bootstrap_chunkhound_mcp_session",
        lambda *_args, **_kwargs: {"ok": True},
    )
    with pytest.raises(ExpectedSessionReadinessError):
        live._ordinary_client(
            binary="chunkhound",
            repo=Path("/repo"),
            runtime=Path("/runtime"),
            config=Path("/runtime/chunkhound.json"),
            environment={},
            witness=ExpectedSearchWitness(
                relative_path="fixture.py", literal="fixture literal"
            ),
        )
    assert closed == [True]
