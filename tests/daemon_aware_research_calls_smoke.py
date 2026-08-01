#!/usr/bin/env python3
"""Checkout-isolated installed-wheel smoke for daemon-aware lifecycle primitives."""
from __future__ import annotations

import argparse
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, cast
from unittest import mock

import run as run_module
from cure_chunkhound_lifecycle import (
    ChunkHoundDaemonLease,
    DaemonGenerationIdentity,
    ExpectedSearchWitness,
    ExpectedSessionReceiptV1,
    LeaseState,
    build_launch_identity,
)


SOURCE_CHECKOUT = Path(__file__).resolve().parents[1]
_A25_SCENARIOS = (
    "success",
    "failure",
    "provider-ctrl-c-publication",
    "helper-ctrl-c-publication",
    "spawn-wins",
    "close-wins",
    "keeper-db-release",
)


def _write_fake_chunkhound(binary: Path) -> None:
    script = r'''#!/usr/bin/env python3
import fcntl
import json
import os
from pathlib import Path
import sys

if len(sys.argv) > 1 and sys.argv[1] == "-c":
    print(json.dumps({"daemon_pid": os.getpid(), "daemon_runtime_dir": "/fixture/runtime"}))
    raise SystemExit(0)
if len(sys.argv) < 2 or sys.argv[1] != "mcp":
    raise SystemExit(2)
runtime = Path(__file__).resolve().parent
(runtime / "keeper.pid").write_text(str(os.getpid()), encoding="utf-8")
with (runtime / "chunkhound.db").open("rb") as database:
    fcntl.flock(database.fileno(), fcntl.LOCK_EX)
    for raw in sys.stdin:
        message = json.loads(raw)
        if "id" not in message:
            continue
        method = message.get("method")
        params = message.get("params", {})
        if method == "initialize":
            result = {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "wheel-smoke", "version": "1"},
            }
        elif method == "tools/list":
            result = {"tools": [
                {"name": "search"},
                {"name": "code_research"},
                {"name": "daemon_status"},
            ]}
        elif method == "tools/call":
            tool = params.get("name")
            if tool == "daemon_status":
                text = json.dumps({
                    "status": "ready",
                    "server_version": "wheel-smoke-1",
                    "query_ready": True,
                    "scan_progress": {"query_ready_at": "wheel-smoke"},
                })
            else:
                text = "## `fixture.txt` L1\n\n```text\nfixture\n```\n\n---\nResults 1–1"
            result = {"content": [{"type": "text", "text": text}], "isError": False}
        else:
            result = {}
        print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)
'''
    binary.write_text(script, encoding="utf-8")
    binary.chmod(0o755)


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _assert_process_gone(pid: int, scenario: str) -> None:
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and _process_exists(pid):
        time.sleep(0.01)
    if _process_exists(pid):
        raise SystemExit(f"{scenario}: owned process {pid} survived")


def _assert_database_unlocked(database: Path) -> None:
    with database.open("rb") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit("keeper-db-release: database remained locked") from exc
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_owned_fixture(path: Path) -> None:
    path.write_text(
        "import os, pathlib, signal, subprocess, sys, time\n"
        "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()), encoding='utf-8')\n"
        "if sys.argv[2] == 'ignore':\n"
        " signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        " child = subprocess.Popen([sys.executable, '-c', "
        "'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)'])\n"
        " pathlib.Path(sys.argv[3]).write_text(str(child.pid), encoding='utf-8')\n"
        "if sys.argv[2] == 'exit': raise SystemExit(int(sys.argv[3]))\n"
        "while True: time.sleep(.01)\n",
        encoding="utf-8",
    )


def _read_pid(path: Path) -> int:
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        try:
            return int(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            time.sleep(0.01)
    raise SystemExit(f"owned fixture did not publish pid: {path}")


def _close_registry(registry: run_module.OwnedProcessRegistry) -> None:
    registry.terminate_and_drain(
        term_timeout_seconds=0.1,
        kill_timeout_seconds=0.2,
        drain_timeout_seconds=0.2,
    )
    if registry.state is not run_module.OwnedProcessRegistryState.CLOSED:
        raise SystemExit("owned registry did not close")


def _run_owned_residue_matrix(root: Path) -> None:
    if not sys.platform.startswith("linux"):
        return
    fixture = root / "owned_fixture.py"
    _write_owned_fixture(fixture)

    for scenario, role, exit_code in (
        ("success", "review-provider", 0),
        ("failure", "chunkhound-helper", 7),
    ):
        pid_path = root / f"{scenario}.pid"
        registry = run_module.OwnedProcessRegistry()
        process = registry.spawn(
            role=cast(run_module.OwnedProcessRole, role),
            cmd=[sys.executable, str(fixture), str(pid_path), "exit", str(exit_code)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        process.wait(timeout=2.0)
        _close_registry(registry)
        _assert_process_gone(_read_pid(pid_path), scenario)

    spawn_code = run_module.OwnedProcessRegistry.spawn.__code__
    for scenario, role in (
        ("provider-ctrl-c-publication", "review-provider"),
        ("helper-ctrl-c-publication", "chunkhound-helper"),
    ):
        pid_path = root / f"{scenario}.pid"
        registry = run_module.OwnedProcessRegistry()
        interrupted_pid: list[int] = []

        def trace(frame: Any, event: str, arg: Any) -> Any:
            del arg
            if frame.f_code is spawn_code and event == "line" and not interrupted_pid:
                for value in frame.f_locals.values():
                    if isinstance(value, subprocess.Popen):
                        interrupted_pid.append(value.pid)
                        raise KeyboardInterrupt(scenario)
            return trace

        sys.settrace(trace)
        try:
            try:
                registry.spawn(
                    role=cast(run_module.OwnedProcessRole, role),
                    cmd=[sys.executable, str(fixture), str(pid_path), "wait", "0"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except KeyboardInterrupt:
                pass
            else:
                raise SystemExit(f"{scenario}: publication interrupt was not raised")
        finally:
            sys.settrace(None)
        if len(interrupted_pid) != 1:
            raise SystemExit(f"{scenario}: child creation was not observed")
        _assert_process_gone(interrupted_pid[0], scenario)
        _close_registry(registry)

    registry = run_module.OwnedProcessRegistry()
    pid_path = root / "spawn-wins.pid"
    descendant_pid_path = root / "spawn-wins-descendant.pid"
    entered = threading.Event()
    release = threading.Event()
    failures: list[BaseException] = []
    spawned: list[subprocess.Popen[Any]] = []
    real_popen = run_module.subprocess.Popen

    def blocked_popen(*args: Any, **kwargs: Any) -> subprocess.Popen[Any]:
        process = real_popen(*args, **kwargs)
        spawned.append(process)
        entered.set()
        if not release.wait(2.0):
            process.kill()
            raise RuntimeError("spawn-wins barrier timed out")
        return process

    def spawn_first() -> None:
        try:
            registry.spawn(
                role="review-provider",
                cmd=[
                    sys.executable,
                    str(fixture),
                    str(pid_path),
                    "ignore",
                    str(descendant_pid_path),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except BaseException as exc:
            failures.append(exc)

    def close_after() -> None:
        try:
            _close_registry(registry)
        except BaseException as exc:
            failures.append(exc)

    with mock.patch.object(run_module.subprocess, "Popen", side_effect=blocked_popen):
        spawn_thread = threading.Thread(target=spawn_first)
        close_thread = threading.Thread(target=close_after)
        spawn_thread.start()
        if not entered.wait(2.0):
            raise SystemExit("spawn-wins: spawn did not reach barrier")
        close_thread.start()
        descendant_pid = _read_pid(descendant_pid_path)
        release.set()
        spawn_thread.join(3.0)
        close_thread.join(3.0)
    if failures or not spawned or spawn_thread.is_alive() or close_thread.is_alive():
        raise SystemExit(f"spawn-wins failed: {failures!r}")
    _assert_process_gone(spawned[0].pid, "spawn-wins")
    _assert_process_gone(descendant_pid, "spawn-wins-descendant")

    registry = run_module.OwnedProcessRegistry()
    _close_registry(registry)
    try:
        registry.spawn(role="review-provider", cmd=[sys.executable, "-c", "pass"])
    except run_module.OwnedProcessRegistryClosingError:
        pass
    else:
        raise SystemExit("close-wins: spawn was not rejected before Popen")


def _assert_checkout_isolated(cure_bin: Path) -> None:
    venv_root = cure_bin.resolve().parent.parent
    offenders: list[str] = []
    for name, module in sorted(sys.modules.items()):
        raw_origin = getattr(module, "__file__", None)
        if raw_origin is None:
            continue
        origin = Path(raw_origin).resolve()
        if origin.is_relative_to(SOURCE_CHECKOUT) and name != "__main__":
            offenders.append(f"{name}={origin}")
    if offenders:
        raise SystemExit("CURe modules loaded from source checkout: " + ", ".join(offenders))

    lifecycle_raw_origin = sys.modules["cure_chunkhound_lifecycle"].__file__
    if lifecycle_raw_origin is None:
        raise SystemExit("installed lifecycle module has no origin")
    lifecycle_origin = Path(lifecycle_raw_origin).resolve()
    if not lifecycle_origin.is_relative_to(venv_root):
        raise SystemExit(f"lifecycle module is outside smoke venv: {lifecycle_origin}")


def _run_lifecycle(cure_bin: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="cure-wheel-daemon-smoke-") as raw_root:
        root = Path(raw_root)
        repo = root / "repo"
        runtime = root / "runtime"
        repo.mkdir()
        runtime.mkdir()
        (repo / "fixture.txt").write_text("fixture\n", encoding="utf-8")
        config = runtime / "chunkhound.json"
        config.write_text("{}\n", encoding="utf-8")
        database = runtime / "chunkhound.db"
        database.write_bytes(b"wheel-smoke")
        binary = runtime / "chunkhound"
        _write_fake_chunkhound(binary)
        environment = {
            "PATH": f"{cure_bin.resolve().parent}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
            "PYTHONSAFEPATH": "1",
        }
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
            reviewed_head="1" * 40,
            resolved_config_path=identity.resolved_config_path,
            config_digest=identity.config_digest,
            resolved_database_path=identity.resolved_database_path,
            total_chunks=1,
            launch_identity_projection=identity,
        )
        lease = ChunkHoundDaemonLease(
            config_path=config,
            repo_path=repo,
            cwd=runtime,
            binary=str(binary),
            env=environment,
            launch_identity=identity,
            generation_probe=lambda: DaemonGenerationIdentity(pid=os.getpid(), process_started_at=1.0),
        )
        try:
            lease.open()
            lease.assert_alive()
            readiness = lease.adjudicate_expected_session(
                receipt,
                witness=ExpectedSearchWitness(relative_path="fixture.txt", literal="fixture"),
            )
            if readiness.launch_identity != identity:
                raise SystemExit("installed keeper launch identity changed")
        finally:
            lease.close()
        if lease.state is not LeaseState.CLOSED:
            raise SystemExit("installed keeper remained open after close")
        keeper_pid = int((runtime / "keeper.pid").read_text(encoding="utf-8"))
        _assert_process_gone(keeper_pid, "keeper-db-release")
        _assert_database_unlocked(database)
        _run_owned_residue_matrix(root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cure-bin", type=Path, required=True)
    args = parser.parse_args()
    cure_bin = args.cure_bin.resolve()
    if not cure_bin.is_file():
        raise SystemExit(f"installed cure executable is missing: {cure_bin}")
    subprocess.run([str(cure_bin), "--help"], check=True, stdout=subprocess.DEVNULL)
    _assert_checkout_isolated(cure_bin)
    _run_lifecycle(cure_bin)
    print("daemon-aware installed-wheel smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
