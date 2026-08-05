# ruff: noqa: F403, F405
from _reviewflow_unittest_shared import *  # noqa: F401, F403

import ast
import copy
import importlib
import inspect
import io
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
import venv
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any
from unittest import mock

import cure_chunkhound
import cure_llm
import cure_output
import run as run_module


_REQUIRED_KEEPER_TOOLS = ("search", "code_research", "daemon_status")


def _fresh_instance_resync_status() -> dict[str, object]:
    """Return the installed Watchman fresh-instance degraded status shape."""
    return {
        "status": "degraded",
        "server_version": "fixture-1",
        "query_ready": False,
        "scan_progress": {
            "query_ready_at": None,
            "unknown_scan_sibling": {"future": True},
            "realtime": {
                "service_state": "running",
                "live_indexing_state": "degraded",
                "last_error": None,
                "unknown_realtime_sibling": ["opaque"],
                "resync": {
                    "needs_resync": True,
                    "last_reason": "realtime_loss_of_sync",
                    "last_error": None,
                    "last_details": {
                        "loss_of_sync_reason": "fresh_instance",
                        "backend": "watchman",
                        "subscription": "chunkhound-fixture",
                        "unknown_detail_sibling": {"opaque": 1},
                    },
                    "unknown_resync_sibling": "opaque",
                },
            },
        },
    }


def _write_fake_chunkhound(
    binary: Path,
    *,
    ledger_path: Path,
    tools_payload: object,
    marker: str = "curated",
    daemon_status: object | None = None,
    daemon_status_sequence: tuple[object, ...] | None = None,
    search_text: str = "## `fixture.txt` L1\n\n```text\nfixture\n```\n\n---\nResults 1–1",
    tool_overrides: dict[str, object] | None = None,
    create_daemon_log: bool = False,
    daemon_status_no_response: bool = False,
) -> None:
    """Write an executable, line-framed stdio JSON-RPC ChunkHound fixture."""
    script = f"""#!/usr/bin/python3
import json
import os
import signal
import sys

LEDGER = {str(ledger_path)!r}
TOOLS = {tools_payload!r}
MARKER = {marker!r}
DAEMON_STATUS = {daemon_status if daemon_status is not None else {"status": "ready", "server_version": "fixture-1", "query_ready": True, "scan_progress": {"query_ready_at": "fixture"}}!r}
DAEMON_STATUS_SEQUENCE = {daemon_status_sequence or ()!r}
SEARCH_TEXT = {search_text!r}
TOOL_OVERRIDES = {tool_overrides or {}!r}
CREATE_DAEMON_LOG = {create_daemon_log!r}
DAEMON_STATUS_NO_RESPONSE = {daemon_status_no_response!r}
daemon_status_index = 0


def record(event, **fields):
    with open(LEDGER, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({{"event": event, **fields}}, sort_keys=True) + "\\n")
        handle.flush()


def stop(signum, frame):
    record("signal", signal=signum, pid=os.getpid())
    raise SystemExit(0)


signal.signal(signal.SIGTERM, stop)
if len(sys.argv) > 1 and sys.argv[1] == "-c":
    print(json.dumps({{"daemon_pid": os.getpid(), "daemon_runtime_dir": "/fixture/runtime"}}))
    raise SystemExit(0)
if len(sys.argv) < 2 or sys.argv[1] != "mcp":
    record("wrong-command", argv=sys.argv)
    raise SystemExit(2)

record(
    "launch",
    marker=MARKER,
    pid=os.getpid(),
    path=os.environ.get("PATH"),
    ambient_secret=os.environ.get("CURE_AMBIENT_SECRET"),
    child_token=os.environ.get("CURE_CHILD_TOKEN"),
)
if CREATE_DAEMON_LOG:
    daemon_root = sys.argv[-1]
    daemon_parent = os.path.join(daemon_root, ".chunkhound")
    os.makedirs(daemon_parent, exist_ok=True)
    with open(os.path.join(daemon_parent, "daemon.log"), "a", encoding="utf-8") as handle:
        handle.write("fake native startup diagnostics\\n")
try:
    for raw in sys.stdin:
        message = json.loads(raw)
        method = message.get("method")
        params = message.get("params", {{}})
        record(
            "request",
            method=method,
            pid=os.getpid(),
            tool=params.get("name") if isinstance(params, dict) else None,
            arguments=params.get("arguments") if isinstance(params, dict) else None,
        )
        if "id" not in message:
            continue
        if method == "initialize":
            result = {{
                "protocolVersion": "2025-03-26",
                "capabilities": {{"tools": {{}}}},
                "serverInfo": {{
                    "name": "fake-chunkhound",
                    "version": "1",
                    "marker": MARKER,
                    "path": os.environ.get("PATH"),
                    "ambient_secret": os.environ.get("CURE_AMBIENT_SECRET"),
                    "child_token": os.environ.get("CURE_CHILD_TOKEN"),
                }},
            }}
        elif method == "tools/list":
            result = {{"tools": TOOLS}}
        elif method == "tools/call":
            tool = params.get("name") if isinstance(params, dict) else None
            if tool == "daemon_status" and DAEMON_STATUS_NO_RESPONSE:
                record("tool-no-response", tool=tool)
                continue
            override = TOOL_OVERRIDES.get(tool)
            if override is not None:
                response = {{"jsonrpc": "2.0", "id": message["id"], **override}}
                sys.stdout.write(json.dumps(response) + "\\n")
                sys.stdout.flush()
                continue
            if tool == "daemon_status":
                status = DAEMON_STATUS
                if DAEMON_STATUS_SEQUENCE:
                    status = DAEMON_STATUS_SEQUENCE[
                        min(daemon_status_index, len(DAEMON_STATUS_SEQUENCE) - 1)
                    ]
                    daemon_status_index += 1
                record("tool-response", tool=tool, status=status)
                text = json.dumps(status, sort_keys=True)
            else:
                text = SEARCH_TEXT
            result = {{
                "content": [{{"type": "text", "text": text}}],
                "isError": False,
            }}
        else:
            result = {{}}
        sys.stdout.write(json.dumps({{"jsonrpc": "2.0", "id": message["id"], "result": result}}) + "\\n")
        sys.stdout.flush()
finally:
    record("closed", pid=os.getpid())
"""
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text(script, encoding="utf-8")
    binary.chmod(0o755)


def _append_ledger(path: Path, event: str, **fields: object) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event": event, **fields}, sort_keys=True) + "\n")
        handle.flush()


def _read_ledger(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _wait_until(predicate: Any, *, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return bool(predicate())


def _state_name(value: object) -> str:
    return str(getattr(value, "name", value)).rsplit(".", 1)[-1].upper()


def _write_owned_process_fixture(path: Path) -> None:
    script = """#!/usr/bin/python3
import json
import os
import signal
import subprocess
import sys
import time

ledger = sys.argv[1]
mode = sys.argv[2]


def record(event, **fields):
    with open(ledger, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event": event, "mode": mode, "pid": os.getpid(), **fields}) + "\\n")
        handle.flush()


def on_term(signum, frame):
    record("term", signal=signum)
    if mode in {"cooperative", "sentinel"}:
        raise SystemExit(0)


signal.signal(signal.SIGTERM, on_term)
record("launch", pgid=os.getpgrp())
if mode == "descendant-parent":
    subprocess.Popen(
        [sys.executable, __file__, ledger, "descendant-child"],
        stdin=subprocess.DEVNULL,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
while True:
    time.sleep(0.05)
"""
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)


def _process_is_gone(pid: int) -> bool:
    stat_path = Path(f"/proc/{pid}/stat")
    try:
        fields = stat_path.read_text(encoding="utf-8").split()
    except FileNotFoundError:
        return True
    return len(fields) > 2 and fields[2] == "Z"


class LosslessCommandCaptureTransportTests(unittest.TestCase):
    """RED contract for final-index-only lossless command capture transport."""

    def _capture_api(self) -> tuple[Any, Any, Any]:
        capture_type = getattr(run_module, "LosslessCommandCapture", None)
        disposed_error = getattr(
            run_module, "LosslessCommandCaptureDisposedError", None
        )
        not_sealed_error = getattr(
            run_module, "LosslessCommandCaptureNotSealedError", None
        )
        self.assertIsNotNone(
            capture_type, "run.LosslessCommandCapture production API is required"
        )
        self.assertIsNotNone(
            disposed_error,
            "run.LosslessCommandCaptureDisposedError production API is required",
        )
        self.assertIsNotNone(
            not_sealed_error,
            "run.LosslessCommandCaptureNotSealedError production API is required",
        )
        return capture_type, disposed_error, not_sealed_error

    @staticmethod
    def _emitter_command(stdout: str, stderr: str) -> list[str]:
        code = (
            "import sys\n"
            f"sys.stdout.write({stdout!r})\n"
            "sys.stdout.flush()\n"
            f"sys.stderr.write({stderr!r})\n"
            "sys.stderr.flush()\n"
        )
        return [sys.executable, "-c", code]

    def test_silent_capture_forces_popen_and_keeps_complete_separate_streams(
        self,
    ) -> None:
        capture_type, _, _ = self._capture_api()
        stdout = "".join(f"out-{index:03d}-café\\n" for index in range(40))
        stderr = "".join(f"err-{index:03d}-Δ\\n" for index in range(40))
        with tempfile.TemporaryDirectory() as raw_root:
            capture = capture_type(spool_dir=Path(raw_root))
            live_sink = io.StringIO()
            try:
                with mock.patch.object(
                    run_module.subprocess,
                    "run",
                    side_effect=AssertionError("capture must not use subprocess.run"),
                ) as subprocess_run:
                    result = run_module.run_cmd(
                        self._emitter_command(stdout, stderr),
                        stream=False,
                        stream_to=live_sink,
                        capture_tail_chars=24,
                        lossless_capture=capture,
                    )
                subprocess_run.assert_not_called()

                self.assertEqual(live_sink.getvalue(), "")
                self.assertTrue(capture.sealed)
                self.assertEqual(
                    capture.stdout_path.read_bytes(), stdout.encode("utf-8")
                )
                self.assertEqual(
                    capture.stderr_path.read_bytes(), stderr.encode("utf-8")
                )
                self.assertEqual(capture.stdout_path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(capture.stderr_path.stat().st_mode & 0o777, 0o600)
                self.assertNotEqual(result.stdout, stdout)
                self.assertNotEqual(result.stderr, stderr)
                self.assertLessEqual(len(result.stdout), 24)
                self.assertLessEqual(len(result.stderr), 24)

                stdout_chunks = tuple(capture.iter_stdout_chunks(chunk_chars=11))
                stderr_chunks = tuple(capture.iter_stderr_chunks(chunk_chars=11))
                self.assertTrue(stdout_chunks)
                self.assertTrue(stderr_chunks)
                self.assertTrue(all(len(chunk) <= 11 for chunk in stdout_chunks))
                self.assertTrue(all(len(chunk) <= 11 for chunk in stderr_chunks))
                self.assertEqual("".join(stdout_chunks), stdout)
                self.assertEqual("".join(stderr_chunks), stderr)
            finally:
                capture.dispose()

    def test_streaming_capture_retains_live_output_behavior(self) -> None:
        capture_type, _, _ = self._capture_api()
        stdout = "stdout-visible-é\n"
        stderr = "stderr-visible-λ\n"
        with tempfile.TemporaryDirectory() as raw_root:
            capture = capture_type(spool_dir=Path(raw_root))
            live_sink = io.StringIO()
            try:
                run_module.run_cmd(
                    self._emitter_command(stdout, stderr),
                    stream=True,
                    stream_to=live_sink,
                    capture_tail_chars=8,
                    lossless_capture=capture,
                )
                self.assertCountEqual(
                    live_sink.getvalue().splitlines(keepends=True),
                    [stdout, stderr],
                )
                self.assertEqual(
                    capture.stdout_path.read_bytes(), stdout.encode("utf-8")
                )
                self.assertEqual(
                    capture.stderr_path.read_bytes(), stderr.encode("utf-8")
                )
            finally:
                capture.dispose()

    def test_capture_seals_only_after_process_exit_and_both_pumps_join(self) -> None:
        capture_type, _, not_sealed_error = self._capture_api()
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            ready = root / "ready"
            release = root / "release"
            capture = capture_type(spool_dir=root)
            code = (
                "import pathlib, sys, time\n"
                "ready, release = map(pathlib.Path, sys.argv[1:])\n"
                "sys.stdout.write('stdout-before-exit\\n'); sys.stdout.flush()\n"
                "sys.stderr.write('stderr-before-exit\\n'); sys.stderr.flush()\n"
                "ready.write_text('ready', encoding='utf-8')\n"
                "while not release.exists(): time.sleep(0.01)\n"
            )
            failures: list[BaseException] = []

            def execute() -> None:
                try:
                    run_module.run_cmd(
                        [sys.executable, "-c", code, str(ready), str(release)],
                        stream=False,
                        capture_tail_chars=8,
                        lossless_capture=capture,
                    )
                except BaseException as exc:
                    failures.append(exc)

            thread = threading.Thread(target=execute)
            thread.start()
            try:
                self.assertTrue(
                    _wait_until(ready.exists), "emitter did not reach barrier"
                )
                self.assertTrue(thread.is_alive())
                self.assertFalse(capture.sealed)
                with self.assertRaises(not_sealed_error):
                    next(iter(capture.iter_stdout_chunks(chunk_chars=4)))

                release.touch()
                thread.join(2.0)
                self.assertFalse(thread.is_alive())
                self.assertEqual(failures, [])
                self.assertTrue(capture.sealed)
                self.assertEqual(
                    "".join(capture.iter_stdout_chunks(chunk_chars=4)),
                    "stdout-before-exit\n",
                )
                self.assertEqual(
                    "".join(capture.iter_stderr_chunks(chunk_chars=4)),
                    "stderr-before-exit\n",
                )
            finally:
                release.touch(exist_ok=True)
                thread.join(2.0)
                capture.dispose()

    def test_disposal_is_idempotent_and_all_post_dispose_access_fails_explicitly(
        self,
    ) -> None:
        capture_type, disposed_error, _ = self._capture_api()
        with tempfile.TemporaryDirectory() as raw_root:
            capture = capture_type(spool_dir=Path(raw_root))
            capture.write_stdout("complete stdout")
            capture.write_stderr("complete stderr")
            capture.seal()
            stdout_path = capture.stdout_path
            stderr_path = capture.stderr_path
            self.assertEqual(
                "".join(capture.iter_stdout_chunks(chunk_chars=3)),
                "complete stdout",
            )
            capture.dispose()
            capture.dispose()
            self.assertFalse(stdout_path.exists())
            self.assertFalse(stderr_path.exists())

            actions = (
                lambda: capture.write_stdout("late"),
                lambda: capture.write_stderr("late"),
                capture.seal,
                lambda: next(iter(capture.iter_stdout_chunks(chunk_chars=3))),
                lambda: next(iter(capture.iter_stderr_chunks(chunk_chars=3))),
            )
            for action in actions:
                with self.subTest(action=action):
                    with self.assertRaises(disposed_error):
                        action()

    def test_reviewflow_output_forwards_and_replays_silent_capture_in_chunks(
        self,
    ) -> None:
        output = object.__new__(cure_output.ReviewflowOutput)
        output.ui_enabled = False
        sink = mock.Mock()
        output.stream_sink = mock.Mock(return_value=sink)
        callback = mock.Mock()
        capture = mock.Mock()
        capture.iter_stdout_chunks.return_value = iter(("full-out-1", "full-out-2"))
        capture.iter_stderr_chunks.return_value = iter(("full-err-1", "full-err-2"))
        expected = run_module.CommandResult(
            cmd=["fixture"],
            cwd=None,
            exit_code=0,
            duration_seconds=0.01,
            stdout="tail-out",
            stderr="tail-err",
        )
        with mock.patch.object(
            cure_output, "run_cmd", return_value=expected
        ) as run_cmd:
            result = output.run_logged_cmd(
                ["fixture"],
                kind="chunkhound",
                cwd=None,
                env=None,
                check=True,
                stream_requested=False,
                stream_text_callback=callback,
                lossless_capture=capture,
            )

        self.assertIs(result, expected)
        run_cmd.assert_called_once_with(
            ["fixture"],
            cwd=None,
            env=None,
            check=True,
            stream=False,
            lossless_capture=capture,
            owned_processes=None,
            owned_role=None,
        )
        capture.iter_stdout_chunks.assert_called_once_with()
        capture.iter_stderr_chunks.assert_called_once_with()
        replay_chunks = ("full-out-1", "full-out-2", "full-err-1", "full-err-2")
        self.assertEqual(
            sink.write.call_args_list, [mock.call(chunk) for chunk in replay_chunks]
        )
        self.assertEqual(
            callback.call_args_list, [mock.call(chunk) for chunk in replay_chunks]
        )


class A13TransportOwnershipTests(unittest.TestCase):
    """A13 transport ownership and single-reader coordination contract."""

    def test_cure_reexports_only_canonical_owned_codex_executor(self) -> None:
        self.assertIs(rf.run_codex_exec, cure_llm.run_codex_exec)
        self.assertIn(
            "owned_processes", inspect.signature(cure_llm.run_codex_exec).parameters
        )

        cure_tree = ast.parse((ROOT / "cure.py").read_text(encoding="utf-8"))
        local_definitions = {
            node.name
            for node in cure_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertNotIn("run_codex_exec", local_definitions)
        self.assertTrue(
            any(
                isinstance(node, ast.ImportFrom)
                and node.module == "cure_llm"
                and any(alias.name == "run_codex_exec" for alias in node.names)
                for node in cure_tree.body
            )
        )

    def test_run_cmd_requires_pair_and_uses_registry_only_for_tagged_launches(self) -> None:
        registry = mock.Mock(spec=run_module.OwnedProcessRegistry)
        with self.assertRaises(ValueError), mock.patch.object(
            run_module.subprocess, "Popen"
        ) as popen:
            run_module.run_cmd(["fixture"], owned_processes=registry)
        popen.assert_not_called()

        process = mock.Mock()
        process.stdout = io.StringIO("out")
        process.stderr = io.StringIO("err")
        process.wait.return_value = 0
        with mock.patch.object(
            run_module.subprocess, "Popen", return_value=process
        ) as popen:
            result = run_module.run_cmd(["fixture"], check=False)
        self.assertEqual((result.stdout, result.stderr), ("out", "err"))
        self.assertEqual(result.exit_code, 0)
        popen.assert_called_once()
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        registry.spawn.assert_not_called()

        process = mock.Mock()
        process.stdout = io.StringIO("owned-out")
        process.stderr = io.StringIO("owned-err")
        process.wait.return_value = 0
        process.poll.return_value = 0
        registry.spawn.return_value = process
        run_module.run_cmd(
            ["owned"],
            check=False,
            owned_processes=registry,
            owned_role="review-provider",
        )
        spawn_kwargs = registry.spawn.call_args.kwargs
        self.assertEqual(spawn_kwargs["role"], "review-provider")
        self.assertNotIn("start_new_session", spawn_kwargs)

    def test_run_cmd_untagged_hung_pipe_returns_bounded_and_reaps_descendant(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            pid_path = Path(raw_root) / "pid"
            code = (
                "import subprocess, sys\n"
                "child = subprocess.Popen("
                "[sys.executable, '-c', 'import time; time.sleep(60)'],"
                " stdout=sys.stdout.fileno())\n"
                f"open({str(pid_path)!r}, 'w').write(str(child.pid))\n"
                "sys.stdout.write('parent-done\\n'); sys.stdout.flush()\n"
            )
            started = time.monotonic()
            with mock.patch.object(
                run_module, "_PIPE_EOF_DRAIN_SECONDS", 0.5
            ), self.assertRaises(
                run_module.ReviewflowCommandDrainError
            ) as raised:
                run_module.run_cmd([sys.executable, "-c", code], check=False)
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 10.0)
            self.assertEqual(raised.exception.exit_code, -1)
            self.assertIn("parent-done", raised.exception.stdout)
            child_pid = int(pid_path.read_text(encoding="utf-8"))
            self.assertTrue(
                _wait_until(lambda: _process_is_gone(child_pid)),
                f"pipe-holding descendant {child_pid} was not reaped",
            )

    def test_run_cmd_tagged_hung_pipe_is_terminated_and_reported(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            pid_path = Path(raw_root) / "pid"
            code = (
                "import subprocess, sys\n"
                "child = subprocess.Popen("
                "[sys.executable, '-c', 'import time; time.sleep(60)'],"
                " stdout=sys.stdout.fileno())\n"
                f"open({str(pid_path)!r}, 'w').write(str(child.pid))\n"
                "sys.stdout.write('parent-done\\n'); sys.stdout.flush()\n"
            )
            registry = run_module.OwnedProcessRegistry()
            started = time.monotonic()
            with mock.patch.object(
                run_module, "_PIPE_EOF_DRAIN_SECONDS", 0.5
            ), self.assertRaises(
                run_module.ReviewflowCommandDrainError
            ) as raised:
                run_module.run_cmd(
                    [sys.executable, "-c", code],
                    check=False,
                    owned_processes=registry,
                    owned_role="review-provider",
                )
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 10.0)
            self.assertIn("parent-done", raised.exception.stdout)
            child_pid = int(pid_path.read_text(encoding="utf-8"))
            self.assertTrue(
                _wait_until(lambda: _process_is_gone(child_pid)),
                f"pipe-holding descendant {child_pid} was not reaped",
            )
            # The killed process was unregistered, so registry teardown is empty.
            registry.terminate_and_drain(
                term_timeout_seconds=1.0,
                kill_timeout_seconds=1.0,
                drain_timeout_seconds=1.0,
            )
            self.assertIs(registry.state, run_module.OwnedProcessRegistryState.CLOSED)
            self.assertEqual(registry._processes, [])

    def _assert_attach_start_interrupt_cleanup(self, *, interrupted_start: int) -> None:
        registry = run_module.OwnedProcessRegistry()
        expected = KeyboardInterrupt(f"pump start {interrupted_start} interrupted")
        original_start = threading.Thread.start
        start_calls = 0
        process: subprocess.Popen[Any] | None = None

        def start_or_interrupt(thread: threading.Thread) -> None:
            nonlocal start_calls
            start_calls += 1
            if start_calls == interrupted_start:
                raise expected
            original_start(thread)

        try:
            with mock.patch.object(
                run_module.Thread,
                "start",
                new=start_or_interrupt,
            ), self.assertRaises(KeyboardInterrupt) as raised:
                run_module.run_cmd(
                    [sys.executable, "-c", "import time; time.sleep(30)"],
                    check=False,
                    stream=True,
                    stream_to=io.StringIO(),
                    owned_processes=registry,
                    owned_role="review-provider",
                )

            self.assertIs(raised.exception, expected)
            self.assertEqual(start_calls, interrupted_start)
            self.assertEqual(len(registry._processes), 1)
            process = registry._processes[0]

            registry.terminate_and_drain(
                term_timeout_seconds=0.5,
                kill_timeout_seconds=0.5,
                drain_timeout_seconds=0.5,
            )
            self.assertIs(registry.state, run_module.OwnedProcessRegistryState.CLOSED)
            self.assertIsNotNone(process.poll())
            self.assertTrue(process.stdout is not None and process.stdout.closed)
            self.assertTrue(process.stderr is not None and process.stderr.closed)

            registry.terminate_and_drain(
                term_timeout_seconds=0.01,
                kill_timeout_seconds=0.01,
                drain_timeout_seconds=0.01,
            )
        finally:
            if process is None and registry._processes:
                process = registry._processes[0]
            if process is not None:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=2.0)
                for stream in (process.stdout, process.stderr):
                    if stream is not None and not stream.closed:
                        stream.close()

    @unittest.skipUnless(sys.platform.startswith("linux"), "process groups require Linux")
    def test_attach_interrupt_before_first_pump_start_is_cleanup_safe(self) -> None:
        self._assert_attach_start_interrupt_cleanup(interrupted_start=1)

    @unittest.skipUnless(sys.platform.startswith("linux"), "process groups require Linux")
    def test_attach_interrupt_between_pump_starts_is_cleanup_safe(self) -> None:
        self._assert_attach_start_interrupt_cleanup(interrupted_start=2)

    @unittest.skipUnless(sys.platform.startswith("linux"), "process groups require Linux")
    def test_registry_persists_every_cleanup_failure_category_idempotently(self) -> None:
        for failure in (
            RuntimeError("pipe drain cleanup failed"),
            KeyboardInterrupt("pipe drain cleanup interrupted"),
        ):
            with self.subTest(category=type(failure).__name__):
                registry = run_module.OwnedProcessRegistry()
                coordinator = run_module.OwnedProcessPipeCoordinator()
                process = registry.spawn(
                    role="review-provider",
                    cmd=[sys.executable, "-c", "import time; time.sleep(30)"],
                    pipe_coordinator=coordinator,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                try:
                    with mock.patch.object(
                        coordinator,
                        "drain",
                        side_effect=failure,
                    ), self.assertRaises(BaseException) as first_close:
                        registry.terminate_and_drain(
                            term_timeout_seconds=0.5,
                            kill_timeout_seconds=0.5,
                            drain_timeout_seconds=0.5,
                        )
                    self.assertIs(first_close.exception, failure)
                    self.assertIs(
                        registry.state,
                        run_module.OwnedProcessRegistryState.CLOSED,
                    )

                    with self.assertRaises(BaseException) as repeated_close:
                        registry.terminate_and_drain(
                            term_timeout_seconds=0.01,
                            kill_timeout_seconds=0.01,
                            drain_timeout_seconds=0.01,
                        )
                    self.assertIs(repeated_close.exception, failure)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=2.0)
                    for stream in (process.stdout, process.stderr):
                        if stream is not None and not stream.closed:
                            stream.close()

    def test_registry_unregister_refuses_live_owned_process_and_retains_record(self) -> None:
        registry = run_module.OwnedProcessRegistry()
        coordinator = run_module.OwnedProcessPipeCoordinator()
        process = registry.spawn(
            role="review-provider",
            cmd=[sys.executable, "-c", "import time; time.sleep(30)"],
            pipe_coordinator=coordinator,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            with self.assertRaisesRegex(RuntimeError, "exit and drained pipes"):
                registry.unregister(process)
            self.assertIn(process, registry._processes)
            self.assertIn(id(process), registry._records)
        finally:
            registry.terminate_and_drain(
                term_timeout_seconds=0.5,
                kill_timeout_seconds=0.5,
                drain_timeout_seconds=0.5,
            )

    def test_registry_unregister_refuses_exited_process_until_pumps_complete(self) -> None:
        registry = run_module.OwnedProcessRegistry()
        coordinator = run_module.OwnedProcessPipeCoordinator()
        process = registry.spawn(
            role="review-provider",
            cmd=[sys.executable, "-c", "print('done')"],
            pipe_coordinator=coordinator,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        release_pumps = threading.Event()

        def pump(stream: Any) -> None:
            try:
                stream.read()
                release_pumps.wait(2.0)
            finally:
                stream.close()

        assert process.stdout is not None
        assert process.stderr is not None
        stdout_pump = threading.Thread(target=pump, args=(process.stdout,))
        stderr_pump = threading.Thread(target=pump, args=(process.stderr,))
        coordinator.attach_and_start(stdout_pump, stderr_pump)
        try:
            process.wait(timeout=2.0)
            self.assertTrue(
                _wait_until(lambda: stdout_pump.is_alive() and stderr_pump.is_alive())
            )
            with self.assertRaisesRegex(RuntimeError, "exit and drained pipes"):
                registry.unregister(process)
            self.assertIn(process, registry._processes)
            self.assertIn(id(process), registry._records)

            release_pumps.set()
            stdout_pump.join(2.0)
            stderr_pump.join(2.0)
            coordinator.complete(process)
            registry.unregister(process)
            self.assertNotIn(process, registry._processes)
            self.assertNotIn(id(process), registry._records)
        finally:
            release_pumps.set()
            if process in registry._processes:
                registry.terminate_and_drain(
                    term_timeout_seconds=0.5,
                    kill_timeout_seconds=0.5,
                    drain_timeout_seconds=0.5,
                )

    def test_registry_unregister_refuses_manual_reader_before_completion(self) -> None:
        registry = run_module.OwnedProcessRegistry()
        coordinator = run_module.OwnedProcessPipeCoordinator(
            manual_reader_reserved=True
        )
        process = registry.spawn(
            role="chunkhound-helper",
            cmd=[sys.executable, "-c", "print('done')"],
            pipe_coordinator=coordinator,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            process.wait(timeout=2.0)
            with self.assertRaisesRegex(RuntimeError, "exit and drained pipes"):
                registry.unregister(process)
            self.assertIn(process, registry._processes)
            self.assertIn(id(process), registry._records)

            assert process.stdout is not None
            assert process.stderr is not None
            process.stdout.read()
            process.stderr.read()
            process.stdout.close()
            process.stderr.close()
            coordinator.complete_manual_reader(process)
            registry.unregister(process)
            self.assertNotIn(process, registry._processes)
            self.assertNotIn(id(process), registry._records)
        finally:
            if process in registry._processes:
                coordinator.release_manual_reader()
                registry.terminate_and_drain(
                    term_timeout_seconds=0.5,
                    kill_timeout_seconds=0.5,
                    drain_timeout_seconds=0.5,
                )

    def test_reviewflow_output_forwards_pair_through_every_transport_branch(self) -> None:
        output = object.__new__(cure_output.ReviewflowOutput)
        output.ui_enabled = False
        output.no_stream = False
        output.verbosity = cure_output.Verbosity.normal
        output.stderr = io.StringIO()
        output.stream_label = mock.Mock(return_value=None)
        output.stream_sink = mock.Mock(return_value=io.StringIO())
        registry = mock.Mock(spec=run_module.OwnedProcessRegistry)
        result = run_module.CommandResult(["fixture"], None, 0, 0.0, "", "")

        for name, stream_requested, capture in (
            ("streamed", True, None),
            ("silent-lossless", False, mock.Mock()),
            ("ordinary", False, None),
        ):
            with self.subTest(name=name), mock.patch.object(
                cure_output, "run_cmd", return_value=result
            ) as run_cmd:
                if capture is not None:
                    capture.iter_stdout_chunks.return_value = iter(())
                    capture.iter_stderr_chunks.return_value = iter(())
                output.run_logged_cmd(
                    ["fixture"],
                    kind="chunkhound",
                    cwd=None,
                    env=None,
                    check=False,
                    stream_requested=stream_requested,
                    lossless_capture=capture,
                    owned_processes=registry,
                    owned_role="chunkhound-helper",
                )
                self.assertIs(run_cmd.call_args.kwargs["owned_processes"], registry)
                self.assertEqual(
                    run_cmd.call_args.kwargs["owned_role"], "chunkhound-helper"
                )

    def test_codex_threads_review_provider_ownership_and_http_stays_untagged(self) -> None:
        registry = mock.Mock(spec=run_module.OwnedProcessRegistry)
        progress = mock.Mock()
        codex_result = cure_llm.CodexRunResult(resume=None)
        reviewflow = mock.Mock()
        reviewflow.build_codex_flags_from_llm_config.return_value = ([], {})
        reviewflow.run_codex_exec.return_value = codex_result
        with mock.patch.object(
            cure_llm, "_reviewflow", return_value=reviewflow
        ), mock.patch.object(
            cure_llm, "_extract_codex_usage_from_event_slice", return_value={}
        ):
            cure_llm.run_llm_exec(
                repo_dir=Path("/repo"),
                resolved={"provider": "codex"},
                resolution_meta={},
                output_path=Path("/out.md"),
                prompt="review",
                env={},
                stream=False,
                progress=progress,
                owned_processes=registry,
            )
        self.assertIs(
            reviewflow.run_codex_exec.call_args.kwargs["owned_processes"], registry
        )

        reviewflow.run_http_response_exec.return_value = cure_llm.LlmRunResult(
            resume=None
        )
        with mock.patch.object(cure_llm, "_reviewflow", return_value=reviewflow):
            cure_llm.run_llm_exec(
                repo_dir=Path("/repo"),
                resolved={"provider": "openai"},
                resolution_meta={},
                output_path=Path("/out.md"),
                prompt="review",
                env={},
                stream=False,
                progress=progress,
                owned_processes=registry,
            )
        self.assertNotIn(
            "owned_processes", reviewflow.run_http_response_exec.call_args.kwargs
        )

    def test_helper_preflight_uses_helper_role_and_unregisters_only_after_drain(self) -> None:
        registry = mock.Mock(spec=run_module.OwnedProcessRegistry)
        processes: list[subprocess.Popen[Any]] = []

        def spawn(**kwargs: Any) -> subprocess.Popen[Any]:
            process = subprocess.Popen(
                kwargs["cmd"],
                cwd=kwargs.get("cwd"),
                env=kwargs.get("env"),
                stdin=kwargs.get("stdin"),
                stdout=kwargs.get("stdout"),
                stderr=kwargs.get("stderr"),
                text=kwargs.get("text", False),
                start_new_session=True,
            )
            processes.append(process)
            return process

        registry.spawn.side_effect = spawn
        command = [
            sys.executable,
            "-c",
            "import json,sys; print(json.dumps({'ok': True})); "
            "print('Running initialize...', file=sys.stderr)",
        ]
        payload = rf._run_chunkhound_helper_preflight(
            cmd=command,
            repo_dir=Path.cwd(),
            env=dict(os.environ),
            runtime_policy={},
            meta={},
            progress=None,
            owned_processes=registry,
            owned_role="chunkhound-helper",
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(registry.spawn.call_args.kwargs["role"], "chunkhound-helper")
        coordinator = registry.spawn.call_args.kwargs.get("pipe_coordinator")
        self.assertIsInstance(coordinator, run_module.OwnedProcessPipeCoordinator)
        registry.unregister.assert_called_once_with(processes[0])
        self.assertIsNotNone(processes[0].poll())
        self.assertTrue(processes[0].stdout.closed)
        self.assertTrue(processes[0].stderr.closed)

    def test_unowned_helper_preflight_cleans_up_early_eof_sleeping_process(self) -> None:
        real_popen = subprocess.Popen
        processes: list[subprocess.Popen[Any]] = []

        def spawn(*args: Any, **kwargs: Any) -> subprocess.Popen[Any]:
            process = real_popen(*args, **kwargs)
            processes.append(process)
            return process

        with tempfile.TemporaryDirectory() as temp_dir:
            pid_path = Path(temp_dir) / "pid"
            command = [
                sys.executable,
                "-c",
                (
                    "import os,time; "
                    f"open({str(pid_path)!r}, 'w').write(str(os.getpid())); "
                    "os.close(1); os.close(2); time.sleep(30)"
                ),
            ]
            with mock.patch.object(
                rf, "_CHUNKHOUND_HELPER_PREFLIGHT_TIMEOUT_SECONDS", 0.05
            ), mock.patch.object(rf.subprocess, "Popen", side_effect=spawn):
                payload = rf._run_chunkhound_helper_preflight(
                    cmd=command,
                    repo_dir=Path.cwd(),
                    env=dict(os.environ),
                    runtime_policy={},
                    meta={},
                    progress=None,
                )

            self.assertFalse(payload["ok"])
            self.assertEqual(len(processes), 1)
            process = processes[0]
            try:
                pid = int(pid_path.read_text(encoding="utf-8"))
                self.assertEqual(process.pid, pid)
                self.assertTrue(
                    _wait_until(lambda: _process_is_gone(pid)),
                    f"early-EOF helper process {pid} was not reaped",
                )
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=2)
                if process.stdout is not None:
                    process.stdout.close()
                if process.stderr is not None:
                    process.stderr.close()

    def test_unowned_helper_preflight_preserves_keyboard_interrupt_and_cleans_up(self) -> None:
        real_popen = subprocess.Popen
        processes: list[subprocess.Popen[Any]] = []
        expected = KeyboardInterrupt("select interrupted")

        def spawn(*args: Any, **kwargs: Any) -> subprocess.Popen[Any]:
            process = real_popen(*args, **kwargs)
            processes.append(process)
            return process

        with mock.patch.object(rf.subprocess, "Popen", side_effect=spawn) as popen, mock.patch.object(
            rf.select, "select", side_effect=expected
        ):
            with self.assertRaises(KeyboardInterrupt) as raised:
                rf._run_chunkhound_helper_preflight(
                    cmd=[sys.executable, "-c", "import time; time.sleep(30)"],
                    repo_dir=Path.cwd(),
                    env=dict(os.environ),
                    runtime_policy={},
                    meta={},
                    progress=None,
                )

        self.assertIs(raised.exception, expected)
        self.assertEqual(len(processes), 1)
        process = processes[0]
        try:
            self.assertTrue(popen.call_args.kwargs["start_new_session"])
            self.assertTrue(
                _wait_until(lambda: _process_is_gone(process.pid)),
                f"interrupted helper process {process.pid} was not reaped",
            )
            self.assertIsNotNone(process.stdout)
            self.assertIsNotNone(process.stderr)
            assert process.stdout is not None
            assert process.stderr is not None
            self.assertTrue(process.stdout.closed)
            self.assertTrue(process.stderr.closed)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=2)
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()

    def test_unowned_helper_preflight_cleans_up_interruption_immediately_after_spawn(self) -> None:
        real_popen = subprocess.Popen
        processes: list[subprocess.Popen[Any]] = []
        expected = KeyboardInterrupt("post-spawn setup interrupted")

        def spawn(*args: Any, **kwargs: Any) -> subprocess.Popen[Any]:
            process = real_popen(*args, **kwargs)
            assert process.stdout is not None
            process.stdout = mock.Mock(wraps=process.stdout)
            process.stdout.fileno.side_effect = expected
            processes.append(process)
            return process

        with mock.patch.object(rf.subprocess, "Popen", side_effect=spawn):
            with self.assertRaises(KeyboardInterrupt) as raised:
                rf._run_chunkhound_helper_preflight(
                    cmd=[sys.executable, "-c", "import time; time.sleep(30)"],
                    repo_dir=Path.cwd(),
                    env=dict(os.environ),
                    runtime_policy={},
                    meta={},
                    progress=None,
                )

        self.assertIs(raised.exception, expected)
        self.assertEqual(len(processes), 1)
        process = processes[0]
        try:
            self.assertTrue(
                _wait_until(lambda: _process_is_gone(process.pid)),
                f"post-spawn interrupted helper process {process.pid} was not reaped",
            )
            assert process.stdout is not None
            assert process.stderr is not None
            self.assertTrue(process.stdout.closed)
            self.assertTrue(process.stderr.closed)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=2)
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()

    def test_unowned_helper_preflight_select_timeout_kills_inherited_pipe_descendant(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fixture = root / "owned-process-fixture.py"
            ledger = root / "ledger.jsonl"
            _write_owned_process_fixture(fixture)
            command = [str(fixture), str(ledger), "descendant-parent"]
            with mock.patch.object(
                rf, "_CHUNKHOUND_HELPER_PREFLIGHT_TIMEOUT_SECONDS", 0.2
            ):
                payload = rf._run_chunkhound_helper_preflight(
                    cmd=command,
                    repo_dir=Path.cwd(),
                    env=dict(os.environ),
                    runtime_policy={},
                    meta={},
                    progress=None,
                )

            self.assertFalse(payload["ok"])
            launches = [
                event for event in _read_ledger(ledger) if event["event"] == "launch"
            ]
            self.assertEqual(
                {event["mode"] for event in launches},
                {"descendant-parent", "descendant-child"},
            )
            try:
                for event in launches:
                    pid = int(str(event["pid"]))
                    self.assertTrue(
                        _wait_until(lambda pid=pid: _process_is_gone(pid)),
                        f"inherited-pipe process {pid} was not terminated",
                    )
            finally:
                for event in launches:
                    pid = int(str(event["pid"]))
                    if not _process_is_gone(pid):
                        try:
                            os.kill(pid, 9)
                        except ProcessLookupError:
                            pass

    def test_helper_preflight_timeout_transfers_reader_ownership_to_registry(self) -> None:
        registry = run_module.OwnedProcessRegistry()
        command = [
            sys.executable,
            "-c",
            "import time; time.sleep(30)",
        ]
        with mock.patch.object(
            rf, "_CHUNKHOUND_HELPER_PREFLIGHT_TIMEOUT_SECONDS", 0.05
        ):
            payload = rf._run_chunkhound_helper_preflight(
                cmd=command,
                repo_dir=Path.cwd(),
                env=dict(os.environ),
                runtime_policy={},
                meta={},
                progress=None,
                owned_processes=registry,
                owned_role="chunkhound-helper",
            )
        self.assertFalse(payload["ok"])
        self.assertIs(registry.state, run_module.OwnedProcessRegistryState.OPEN)
        registry.terminate_and_drain(
            term_timeout_seconds=0.2,
            kill_timeout_seconds=0.2,
            drain_timeout_seconds=0.2,
        )
        self.assertIs(registry.state, run_module.OwnedProcessRegistryState.CLOSED)

    @unittest.skipUnless(
        sys.platform.startswith("linux"), "process groups require Linux"
    )
    def test_owned_helper_post_publication_interrupt_releases_reader_reservation(
        self,
    ) -> None:
        registry = run_module.OwnedProcessRegistry()
        expected = KeyboardInterrupt("owned helper interrupted after publication")
        processes: list[subprocess.Popen[Any]] = []
        real_spawn = registry.spawn
        helper_code = rf._run_chunkhound_helper_preflight.__code__
        source_lines, source_start = inspect.getsourcelines(
            rf._run_chunkhound_helper_preflight
        )
        target_line = next(
            source_start + offset
            for offset, line in enumerate(source_lines)
            if line.strip() == "open_fds: dict[int, str] = {}"
        )

        def observed_spawn(**kwargs: Any) -> subprocess.Popen[Any]:
            process = real_spawn(**kwargs)
            processes.append(process)
            return process

        def interrupt_after_publication(frame: Any, event: str, arg: Any) -> Any:
            if (
                frame.f_code is helper_code
                and event == "line"
                and frame.f_lineno == target_line
                and registry._processes
            ):
                raise expected
            return interrupt_after_publication

        try:
            with mock.patch.object(registry, "spawn", side_effect=observed_spawn):
                sys.settrace(interrupt_after_publication)
                try:
                    with self.assertRaises(KeyboardInterrupt) as raised:
                        rf._run_chunkhound_helper_preflight(
                            cmd=[sys.executable, "-c", "import time; time.sleep(30)"],
                            repo_dir=Path.cwd(),
                            env=dict(os.environ),
                            runtime_policy={},
                            meta={},
                            progress=None,
                            owned_processes=registry,
                            owned_role="chunkhound-helper",
                        )
                finally:
                    sys.settrace(None)

            self.assertIs(raised.exception, expected)
            self.assertEqual(len(processes), 1)
            process = processes[0]
            registry.terminate_and_drain(
                term_timeout_seconds=0.5,
                kill_timeout_seconds=0.5,
                drain_timeout_seconds=0.5,
            )
            self.assertTrue(
                _wait_until(lambda: _process_is_gone(process.pid)),
                f"post-publication interrupted helper {process.pid} was not reaped",
            )
            assert process.stdout is not None
            assert process.stderr is not None
            self.assertTrue(process.stdout.closed)
            self.assertTrue(process.stderr.closed)
            self.assertIs(registry.state, run_module.OwnedProcessRegistryState.CLOSED)
        finally:
            sys.settrace(None)
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=2)
                if process.stdout is not None:
                    process.stdout.close()
                if process.stderr is not None:
                    process.stderr.close()

    @unittest.skipUnless(sys.platform.startswith("linux"), "process groups require Linux")
    def test_helper_preflight_concurrent_teardown_waits_for_manual_reader(self) -> None:
        registry = run_module.OwnedProcessRegistry()
        helper_failures: list[BaseException] = []
        teardown_failures: list[BaseException] = []
        reader_entered = threading.Event()
        release_reader = threading.Event()
        helper_done = threading.Event()
        signal_sent = threading.Event()
        maximum_concurrent_reads = 0
        active_reads = 0
        reads_lock = threading.Lock()
        real_read = os.read

        with tempfile.TemporaryDirectory():
            code = (
                "import signal,time\n"
                "def stop(*_): raise SystemExit(0)\n"
                "signal.signal(signal.SIGTERM, stop)\n"
                "print('reader-ready', flush=True)\n"
                "while True: time.sleep(.01)\n"
            )

            def blocking_read(fd: int, size: int) -> bytes:
                nonlocal active_reads, maximum_concurrent_reads
                # Popen itself uses os.read before registry publication; only
                # reserve the helper's post-publication manual pipe read.
                if not registry._processes:
                    return real_read(fd, size)
                with reads_lock:
                    active_reads += 1
                    maximum_concurrent_reads = max(maximum_concurrent_reads, active_reads)
                reader_entered.set()
                try:
                    if not release_reader.wait(2.0):
                        raise AssertionError("manual reader was not released")
                    return real_read(fd, size)
                finally:
                    with reads_lock:
                        active_reads -= 1

            def run_helper() -> None:
                try:
                    rf._run_chunkhound_helper_preflight(
                        cmd=[sys.executable, "-c", code],
                        repo_dir=Path.cwd(),
                        env=dict(os.environ),
                        runtime_policy={},
                        meta={},
                        progress=None,
                        owned_processes=registry,
                        owned_role="chunkhound-helper",
                    )
                except BaseException as exc:
                    helper_failures.append(exc)
                finally:
                    helper_done.set()

            def teardown() -> None:
                try:
                    registry.terminate_and_drain(
                        term_timeout_seconds=0.5,
                        kill_timeout_seconds=0.5,
                        drain_timeout_seconds=1.0,
                    )
                except BaseException as exc:
                    teardown_failures.append(exc)

            def forbidden_communicate(process: Any, *args: Any, **kwargs: Any) -> Any:
                raise AssertionError(
                    f"communicate double-read attempted for helper pid {process.pid}"
                )

            real_signal_group = registry._signal_group

            def observed_signal_group(pgid: int, sig: signal.Signals) -> None:
                signal_sent.set()
                real_signal_group(pgid, sig)

            helper_thread = threading.Thread(target=run_helper)
            teardown_thread = threading.Thread(target=teardown)
            with mock.patch.object(rf.os, "read", side_effect=blocking_read), mock.patch.object(
                subprocess.Popen, "communicate", forbidden_communicate
            ), mock.patch.object(
                run_module.OwnedProcessRegistry,
                "_signal_group",
                side_effect=observed_signal_group,
            ):
                helper_thread.start()
                self.assertTrue(reader_entered.wait(2.0), "manual read did not start")
                teardown_thread.start()
                self.assertTrue(
                    signal_sent.wait(1.0),
                    f"teardown did not signal helper: {teardown_failures!r}, {registry.state!r}",
                )
                self.assertTrue(teardown_thread.is_alive(), "teardown did not wait for reader")
                release_reader.set()
                helper_thread.join(2.0)
                teardown_thread.join(2.0)

        self.assertTrue(helper_done.is_set())
        self.assertFalse(helper_thread.is_alive())
        self.assertFalse(teardown_thread.is_alive())
        self.assertEqual(helper_failures, [])
        self.assertEqual(teardown_failures, [])
        self.assertEqual(maximum_concurrent_reads, 1)
        self.assertIs(registry.state, run_module.OwnedProcessRegistryState.CLOSED)

    @unittest.skipUnless(sys.platform.startswith("linux"), "process groups require Linux")
    def test_owned_helper_manual_read_interrupt_releases_exact_exception(self) -> None:
        registry = run_module.OwnedProcessRegistry()
        expected = KeyboardInterrupt("owned helper read interrupted")
        read_entered = threading.Event()
        real_read = os.read

        def interrupted_read(fd: int, size: int) -> bytes:
            if not registry._processes:
                return real_read(fd, size)
            read_entered.set()
            raise expected

        def forbidden_communicate(process: Any, *args: Any, **kwargs: Any) -> Any:
            raise AssertionError(
                f"communicate double-read attempted for helper pid {process.pid}"
            )

        with mock.patch.object(
            rf.os, "read", side_effect=interrupted_read
        ), mock.patch.object(subprocess.Popen, "communicate", forbidden_communicate):
            with self.assertRaises(KeyboardInterrupt) as raised:
                rf._run_chunkhound_helper_preflight(
                    cmd=[
                        sys.executable,
                        "-c",
                        "import time; print('ready', flush=True); time.sleep(30)",
                    ],
                    repo_dir=Path.cwd(),
                    env=dict(os.environ),
                    runtime_policy={},
                    meta={},
                    progress=None,
                    owned_processes=registry,
                    owned_role="chunkhound-helper",
                )

            self.assertTrue(read_entered.is_set())
            self.assertIs(raised.exception, expected)
            registry.terminate_and_drain(
                term_timeout_seconds=0.5,
                kill_timeout_seconds=0.5,
                drain_timeout_seconds=0.5,
            )
        self.assertIs(registry.state, run_module.OwnedProcessRegistryState.CLOSED)

    def test_fresh_and_retry_callsites_explicitly_forward_owned_processes(self) -> None:
        """A13 exclusion-safe structural proof: no ambient ownership lookup."""

        def calls_named(function: Any, name: str) -> list[ast.Call]:
            tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
            return [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == name
            ]

        fresh_calls = calls_named(rf._pr_flow_impl, "run_llm_exec")
        self.assertEqual(len(fresh_calls), 4)  # orientation, plan, single, reconcile
        self.assertTrue(
            all(
                "owned_processes" in {keyword.arg for keyword in call.keywords}
                for call in fresh_calls
            )
        )

        step_calls = calls_named(
            rf._execute_multipass_step_stage, "_run_multipass_step_llm"
        )
        self.assertEqual(len(step_calls), 2)  # UI retry + automatic retry
        self.assertTrue(
            all(
                "owned_processes" in {keyword.arg for keyword in call.keywords}
                for call in step_calls
            )
        )
        step_tree = ast.parse(
            textwrap.dedent(inspect.getsource(rf._execute_multipass_step_stage))
        )
        worker_submits = [
            node
            for node in ast.walk(step_tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "submit"
            and node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "_run_multipass_step_llm"
        ]
        self.assertEqual(len(worker_submits), 1)
        self.assertIn(
            "owned_processes",
            {keyword.arg for keyword in worker_submits[0].keywords},
        )
        synth_calls = calls_named(rf._execute_multipass_synth_stage, "run_llm_exec")
        self.assertEqual(len(synth_calls), 1)  # loop body covers synth retries
        self.assertIn(
            "owned_processes",
            {keyword.arg for keyword in synth_calls[0].keywords},
        )

    def test_direct_codex_trust_retry_keeps_review_provider_ownership(self) -> None:
        registry = mock.Mock(spec=run_module.OwnedProcessRegistry)
        progress = mock.Mock()
        trust_failure = run_module.ReviewflowSubprocessError(
            cmd=["codex"],
            cwd=Path("/repo"),
            exit_code=1,
            stdout="",
            stderr="not a trusted directory",
        )
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            with mock.patch.object(cure_llm, "active_output", return_value=None), mock.patch.object(
                cure_llm,
                "_resolve_codex_events_log_path",
                return_value=root / "events.jsonl",
            ), mock.patch.object(
                cure_llm,
                "_resolve_codex_display_log_path",
                return_value=root / "display.log",
            ), mock.patch.object(
                cure_llm, "_ensure_codex_live_progress"
            ), mock.patch.object(
                cure_llm, "_record_codex_live_event"
            ), mock.patch.object(
                cure_llm, "_finalize_codex_live_progress"
            ), mock.patch.object(
                cure_llm, "normalize_markdown_artifact"
            ), mock.patch.object(
                cure_llm, "find_codex_resume_info", return_value=None
            ), mock.patch.object(
                cure_llm,
                "run_cmd",
                side_effect=[
                    trust_failure,
                    run_module.CommandResult([], None, 0, 0.0, "", ""),
                ],
            ) as run_cmd:
                cure_llm.run_codex_exec(
                    repo_dir=root,
                    codex_flags=[],
                    codex_config_overrides=None,
                    output_path=root / "review.md",
                    prompt="review",
                    env={},
                    stream=False,
                    progress=progress,
                    owned_processes=registry,
                )

        self.assertEqual(run_cmd.call_count, 2)
        self.assertTrue(run_cmd.call_args_list[1].args[0])
        for call in run_cmd.call_args_list:
            self.assertIs(call.kwargs["owned_processes"], registry)
            self.assertEqual(call.kwargs["owned_role"], "review-provider")

    @unittest.skipUnless(sys.platform.startswith("linux"), "process groups require Linux")
    def test_teardown_during_stream_never_double_reads_and_closes_after_pumps(self) -> None:
        registry = run_module.OwnedProcessRegistry()
        failures: list[BaseException] = []
        result: list[run_module.CommandResult] = []
        with tempfile.TemporaryDirectory() as raw_root:
            ready = Path(raw_root) / "ready"
            code = (
                "import pathlib, signal, sys, time\n"
                "ready = pathlib.Path(sys.argv[1])\n"
                "def stop(*_):\n"
                " sys.stdout.write('term-out\\n'); sys.stdout.flush()\n"
                " sys.stderr.write('term-err\\n'); sys.stderr.flush()\n"
                " raise SystemExit(0)\n"
                "signal.signal(signal.SIGTERM, stop)\n"
                "sys.stdout.write('start-out\\n'); sys.stdout.flush()\n"
                "sys.stderr.write('start-err\\n'); sys.stderr.flush()\n"
                "ready.touch()\n"
                "while True: time.sleep(.01)\n"
            )

            def execute() -> None:
                try:
                    result.append(
                        run_module.run_cmd(
                            [sys.executable, "-c", code, str(ready)],
                            check=False,
                            stream=True,
                            stream_to=io.StringIO(),
                            owned_processes=registry,
                            owned_role="review-provider",
                        )
                    )
                except BaseException as exc:
                    failures.append(exc)

            original_communicate = subprocess.Popen.communicate

            def forbidden_communicate(process: Any, *args: Any, **kwargs: Any) -> Any:
                raise AssertionError(
                    f"communicate double-read attempted for owned streamed pid {process.pid}"
                )

            thread = threading.Thread(target=execute)
            with mock.patch.object(
                subprocess.Popen, "communicate", forbidden_communicate
            ):
                thread.start()
                self.assertTrue(_wait_until(ready.exists), "stream did not start")
                registry.terminate_and_drain(
                    term_timeout_seconds=1.0,
                    kill_timeout_seconds=1.0,
                    drain_timeout_seconds=1.0,
                )
                thread.join(2.0)
            self.assertIsNotNone(original_communicate)
            self.assertFalse(thread.is_alive())
            self.assertEqual(failures, [])
            self.assertEqual(_state_name(registry.state), "CLOSED")
            self.assertEqual(len(result), 1)
            self.assertIn("term-out", result[0].stdout)
            self.assertIn("term-err", result[0].stderr)


class JsonRpcSessionReadCapTests(unittest.TestCase):
    """RED contract for bounded MCP stdout framing (read-time caps)."""

    @staticmethod
    def _bare_session() -> Any:
        session = cure_chunkhound.JsonRpcSession.__new__(
            cure_chunkhound.JsonRpcSession
        )
        session._stdout_buffer = bytearray()
        return session

    def test_framed_header_cap_rejects_terminatorless_headers(self) -> None:
        session = self._bare_session()
        session._stdout_buffer.extend(b"X" * (16 * 1024 + 1))
        with self.assertRaises(RuntimeError) as raised:
            session._try_extract_framed_message()
        self.assertIn("headers exceeded", str(raised.exception))

    def test_framed_content_length_cap_rejects_huge_declared_bodies(self) -> None:
        session = self._bare_session()
        session._stdout_buffer.extend(b"Content-Length: 999999999\r\n\r\n")
        with self.assertRaises(RuntimeError) as raised:
            session._try_extract_framed_message()
        self.assertIn("content-length exceeds", str(raised.exception))

    def test_framed_negative_content_length_is_rejected(self) -> None:
        session = self._bare_session()
        session._stdout_buffer.extend(b"Content-Length: -5\r\n\r\n")
        with self.assertRaises(RuntimeError):
            session._try_extract_framed_message()

    def test_json_line_cap_rejects_newline_less_gigantic_line(self) -> None:
        session = self._bare_session()
        session._stdout_buffer.extend(b"{" + b"x" * (8 * 1024 * 1024))
        with self.assertRaises(RuntimeError) as raised:
            session._try_extract_json_line_message()
        self.assertIn("JSON line exceeded", str(raised.exception))

    def test_stdout_buffer_cap_terminates_on_unbounded_growth(self) -> None:
        read_fd, write_fd = os.pipe()
        stream = os.fdopen(read_fd, "rb", buffering=0)
        try:
            proc = mock.Mock()
            proc.stdout = stream
            proc.stderr = None
            session = self._bare_session()
            session.proc = proc
            session._stdout_open = True
            session._stderr_open = False
            os.write(write_fd, b"y" * 8192)
            with mock.patch.object(
                cure_chunkhound, "_MAX_MCP_STDOUT_BUFFER_BYTES", 4096
            ), self.assertRaises(RuntimeError) as raised:
                session._drain_ready_io(timeout_seconds=1.0)
            self.assertIn("maximum buffered byte cap", str(raised.exception))
        finally:
            os.close(write_fd)
            stream.close()

    def test_well_formed_framed_message_still_parses_within_caps(self) -> None:
        session = self._bare_session()
        body = b'{"jsonrpc":"2.0","id":1,"result":{"ok":true}}'
        session._stdout_buffer.extend(
            f"Content-Length: {len(body)}\r\n\r\n".encode() + body
        )
        payload = session._try_extract_framed_message()
        self.assertEqual(payload, {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
        self.assertEqual(session._stdout_buffer, bytearray())


class ExpectedSessionReceiptProjectionTests(unittest.TestCase):
    """RED public contract for strict final-index receipt projection."""

    def _receipt_api(self) -> tuple[Any, Any, Any, Any]:
        try:
            lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        except ModuleNotFoundError as exc:
            self.fail(f"receipt lifecycle production module is required: {exc}")
        launch_identity_type = getattr(lifecycle, "LaunchIdentity", None)
        receipt_type = getattr(lifecycle, "ExpectedSessionReceiptV1", None)
        projector = getattr(lifecycle, "project_expected_session_receipt_v1", None)
        projection_error = getattr(
            lifecycle, "ExpectedSessionReceiptProjectionError", None
        )
        self.assertIsNotNone(
            launch_identity_type, "cure_chunkhound_lifecycle.LaunchIdentity is required"
        )
        self.assertIsNotNone(
            receipt_type,
            "cure_chunkhound_lifecycle.ExpectedSessionReceiptV1 is required",
        )
        self.assertIsNotNone(
            projector,
            "cure_chunkhound_lifecycle.project_expected_session_receipt_v1 is required",
        )
        self.assertIsNotNone(
            projection_error,
            "cure_chunkhound_lifecycle.ExpectedSessionReceiptProjectionError is required",
        )
        return launch_identity_type, receipt_type, projector, projection_error

    @staticmethod
    def _identity(launch_identity_type: Any, root: Path) -> Any:
        return launch_identity_type(
            resolved_executable=root / "bin" / "chunkhound",
            canonical_root=root / "repo",
            resolved_config_path=root / "chunkhound.json",
            config_digest="a" * 64,
            resolved_database_path=root / "index.duckdb",
            cwd=root / "repo",
            curated_environment_keys=("PATH", "PYTHONSAFEPATH"),
            environment_equality_digest="b" * 64,
        )

    @staticmethod
    def _summary_command(stdout: str, stderr: str) -> list[str]:
        code = (
            "import sys\n"
            f"sys.stdout.write({stdout!r}); sys.stdout.flush()\n"
            f"sys.stderr.write({stderr!r}); sys.stderr.flush()\n"
        )
        return [sys.executable, "-c", code]

    def _capture_summary(
        self, root: Path, *, stdout: str, stderr: str
    ) -> tuple[Any, Any]:
        capture = run_module.LosslessCommandCapture(spool_dir=root)
        result = run_module.run_cmd(
            self._summary_command(stdout, stderr),
            stream=False,
            capture_tail_chars=32,
            lossless_capture=capture,
        )
        return capture, result

    def test_expected_session_receipt_v1_is_frozen_with_exact_launch_projection(
        self,
    ) -> None:
        launch_identity_type, receipt_type, _, _ = self._receipt_api()
        self.assertEqual(
            tuple(field.name for field in fields(launch_identity_type)),
            (
                "resolved_executable",
                "canonical_root",
                "resolved_config_path",
                "config_digest",
                "resolved_database_path",
                "cwd",
                "curated_environment_keys",
                "environment_equality_digest",
            ),
        )
        self.assertEqual(
            tuple(field.name for field in fields(receipt_type)),
            (
                "schema_version",
                "canonical_root",
                "reviewed_head",
                "resolved_config_path",
                "config_digest",
                "resolved_database_path",
                "total_chunks",
                "launch_identity_projection",
            ),
        )
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            identity = self._identity(launch_identity_type, root)
            receipt = receipt_type(
                schema_version=1,
                canonical_root=identity.canonical_root,
                reviewed_head="1" * 40,
                resolved_config_path=identity.resolved_config_path,
                config_digest=identity.config_digest,
                resolved_database_path=identity.resolved_database_path,
                total_chunks=7,
                launch_identity_projection=identity,
            )
            self.assertEqual(receipt.schema_version, 1)
            self.assertIs(receipt.launch_identity_projection, identity)
            with self.assertRaises(FrozenInstanceError):
                receipt.total_chunks = 8

            mismatched_identity = launch_identity_type(
                **{
                    field.name: (
                        "c" * 64
                        if field.name == "environment_equality_digest"
                        else getattr(identity, field.name)
                    )
                    for field in fields(launch_identity_type)
                }
            )
            self.assertNotEqual(receipt.launch_identity_projection, mismatched_identity)

    def test_lossless_projection_accepts_valid_fields_beyond_display_tail(self) -> None:
        launch_identity_type, _, projector, _ = self._receipt_api()
        filler = "display-only filler " * 20
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            identity = self._identity(launch_identity_type, root)
            capture, result = self._capture_summary(
                root,
                stdout=f"Total chunks: 7\n{filler}\n",
                stderr=f"Errors: 0 files\nTotal chunks: 7\n{filler}\n",
            )
            try:
                self.assertNotIn("Total chunks", result.stdout)
                self.assertNotIn("Errors:", result.stderr)
                receipt = projector(
                    capture=capture,
                    exit_code=result.exit_code,
                    reviewed_head="1" * 40,
                    launch_identity_projection=identity,
                )
                self.assertEqual(receipt.schema_version, 1)
                self.assertEqual(receipt.total_chunks, 7)
                self.assertEqual(receipt.canonical_root, identity.canonical_root)
                self.assertEqual(receipt.launch_identity_projection, identity)
            finally:
                capture.dispose()

    def test_lossless_projection_rejects_every_early_invalid_recognized_occurrence(
        self,
    ) -> None:
        launch_identity_type, _, projector, projection_error = self._receipt_api()
        filler = "tail-displacing filler " * 20
        cases = {
            "conflicting-total": (
                "Total chunks: 6\n",
                "Errors: 0 files\n",
            ),
            "malformed-total": (
                "Total chunks: seven\n",
                "Errors: 0 files\n",
            ),
            "malformed-errors": (
                "Errors: none files\n",
                "Total chunks: 7\n",
            ),
            "nonzero-errors": (
                "Errors: 2 files\n",
                "Total chunks: 7\n",
            ),
        }
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            identity = self._identity(launch_identity_type, root)
            for name, (early_stdout, early_stderr) in cases.items():
                with self.subTest(name=name):
                    capture, result = self._capture_summary(
                        root,
                        stdout=f"{early_stdout}{filler}\nTotal chunks: 7\n",
                        stderr=f"{early_stderr}{filler}\nErrors: 0 files\n",
                    )
                    try:
                        self.assertNotIn(early_stdout.strip(), result.stdout)
                        if early_stderr.strip() != "Errors: 0 files":
                            self.assertNotIn(early_stderr.strip(), result.stderr)
                        with self.assertRaises(projection_error):
                            projector(
                                capture=capture,
                                exit_code=result.exit_code,
                                reviewed_head="1" * 40,
                                launch_identity_projection=identity,
                            )
                    finally:
                        capture.dispose()


class ChunkHoundKeeperRuntimeTests(unittest.TestCase):
    def test_json_rpc_session_uses_immutable_explicit_env_and_curated_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            repo = root / "repo"
            repo.mkdir()
            config = root / "chunkhound.json"
            config.write_text("{}", encoding="utf-8")
            curated_ledger = root / "curated.jsonl"
            ambient_ledger = root / "ambient.jsonl"
            curated_binary = root / "curated-bin" / "chunkhound"
            ambient_binary = root / "ambient-bin" / "chunkhound"
            tools = [{"name": name} for name in _REQUIRED_KEEPER_TOOLS]
            _write_fake_chunkhound(
                curated_binary, ledger_path=curated_ledger, tools_payload=tools
            )
            _write_fake_chunkhound(
                ambient_binary,
                ledger_path=ambient_ledger,
                tools_payload=tools,
                marker="ambient",
            )

            backing_env = {
                "PATH": str(curated_binary.parent),
                "PYTHONSAFEPATH": "1",
                "CURE_CHILD_TOKEN": "original",
            }
            explicit_env = MappingProxyType(backing_env)
            with mock.patch.dict(
                os.environ,
                {
                    "PATH": str(ambient_binary.parent),
                    "CURE_AMBIENT_SECRET": "must-not-be-inherited",  # pragma: allowlist secret
                },
                clear=False,
            ):
                session = cure_chunkhound.JsonRpcSession(
                    config_path=config,
                    repo_path=repo,
                    cwd=repo,
                    binary="chunkhound",
                    env=explicit_env,
                )
                try:
                    backing_env["PATH"] = str(ambient_binary.parent)
                    backing_env["CURE_CHILD_TOKEN"] = "mutated-after-construction"
                    response = session.request(
                        "initialize",
                        {},
                        stage="initialize",
                        timeout_seconds=2.0,
                    )
                finally:
                    session.close()

            server = response["result"]["serverInfo"]
            self.assertEqual(server["marker"], "curated")
            self.assertEqual(server["path"], str(curated_binary.parent))
            self.assertEqual(server["child_token"], "original")
            self.assertIsNone(server["ambient_secret"])
            self.assertEqual(
                len(
                    [
                        row
                        for row in _read_ledger(curated_ledger)
                        if row["event"] == "launch"
                    ]
                ),
                1,
            )
            self.assertEqual(_read_ledger(ambient_ledger), [])

    def test_retained_preflight_metadata_uses_immutable_explicit_session_env(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            repo = root / "repo"
            repo.mkdir()
            config = root / "chunkhound.json"
            config.write_text("{}", encoding="utf-8")
            curated_binary = root / "curated-bin" / "chunkhound"
            ambient_binary = root / "ambient-bin" / "chunkhound"
            _write_fake_chunkhound(
                curated_binary,
                ledger_path=root / "curated.jsonl",
                tools_payload=[{"name": name} for name in _REQUIRED_KEEPER_TOOLS],
            )
            _write_fake_chunkhound(
                ambient_binary,
                ledger_path=root / "ambient.jsonl",
                tools_payload=[{"name": name} for name in _REQUIRED_KEEPER_TOOLS],
                marker="ambient",
            )
            backing_env = {
                "PATH": str(curated_binary.parent),
                "PYTHONSAFEPATH": "1",
                "CURE_RUNTIME_MARKER": "/explicit/runtime",
                "CURE_REGISTRY_MARKER": "/explicit/registry.json",
                "CURE_CHILD_TOKEN": "must-not-be-in-payload",
            }
            explicit_env = MappingProxyType(backing_env)
            captured_envs: list[object] = []

            def metadata_payload(*args: object, env: object = None, **kwargs: object) -> dict[str, object]:
                del args, kwargs
                captured_envs.append(env)
                effective_env = os.environ if env is None else env
                return {
                    "chunkhound_path": str(Path(effective_env["PATH"]) / "chunkhound"),
                    "daemon_runtime_dir": effective_env["CURE_RUNTIME_MARKER"],
                    "daemon_registry_entry_path": effective_env["CURE_REGISTRY_MARKER"],
                    "daemon_metadata_error": "",
                }

            with mock.patch.dict(
                os.environ,
                {
                    "PATH": str(ambient_binary.parent),
                    "CURE_RUNTIME_MARKER": "/ambient/runtime",
                    "CURE_REGISTRY_MARKER": "/ambient/registry.json",
                    "CURE_AMBIENT_SECRET": "must-not-be-inherited",  # pragma: allowlist secret
                },
                clear=False,
            ), mock.patch.object(
                cure_chunkhound,
                "daemon_metadata_payload",
                side_effect=metadata_payload,
            ):
                session = cure_chunkhound.JsonRpcSession(
                    config_path=config,
                    repo_path=repo,
                    cwd=repo,
                    binary="chunkhound",
                    env=explicit_env,
                )
                try:
                    backing_env["PATH"] = str(ambient_binary.parent)
                    backing_env["CURE_RUNTIME_MARKER"] = "/mutated/runtime"
                    backing_env["CURE_REGISTRY_MARKER"] = "/mutated/registry.json"
                    payload = cure_chunkhound.bootstrap_chunkhound_mcp_session(
                        session,
                        config_path=config,
                        repo_path=repo,
                        cwd=repo,
                        binary=session.binary,
                        emit_stage_lines=False,
                    )
                finally:
                    session.close()

            self.assertTrue(payload["ok"], payload)
            self.assertEqual(payload["chunkhound_path"], str(curated_binary))
            self.assertEqual(payload["daemon_runtime_dir"], "/explicit/runtime")
            self.assertEqual(
                payload["daemon_registry_entry_path"],
                "/explicit/registry.json",
            )
            self.assertEqual(len(captured_envs), 1)
            self.assertIsInstance(captured_envs[0], MappingProxyType)
            self.assertIsNot(captured_envs[0], explicit_env)
            self.assertNotIn("must-not-be-in-payload", json.dumps(payload, sort_keys=True))
            self.assertNotIn("must-not-be-inherited", json.dumps(payload, sort_keys=True))

    def test_canonical_bootstrap_requires_three_well_formed_tools(self) -> None:
        variants = {
            "valid": ([{"name": name} for name in _REQUIRED_KEEPER_TOOLS], True),
            "missing-search": (
                [{"name": "code_research"}, {"name": "daemon_status"}],
                False,
            ),
            "missing-code-research": (
                [{"name": "search"}, {"name": "daemon_status"}],
                False,
            ),
            "missing-daemon-status": (
                [{"name": "search"}, {"name": "code_research"}],
                False,
            ),
            "tools-not-list": ({"name": "search"}, False),
            "malformed-entry": (
                [{"name": name} for name in _REQUIRED_KEEPER_TOOLS] + [{"name": 17}],
                False,
            ),
            "missing-name": (
                [{"name": name} for name in _REQUIRED_KEEPER_TOOLS]
                + [{"description": "invalid"}],
                False,
            ),
        }
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            repo = root / "repo"
            repo.mkdir()
            config = root / "chunkhound.json"
            config.write_text("{}", encoding="utf-8")
            for name, (tools_payload, expected_ok) in variants.items():
                with self.subTest(name=name):
                    ledger = root / f"{name}.jsonl"
                    binary = root / name / "chunkhound"
                    _write_fake_chunkhound(
                        binary, ledger_path=ledger, tools_payload=tools_payload
                    )
                    with mock.patch.object(
                        cure_chunkhound,
                        "daemon_metadata_payload",
                        return_value={"daemon_metadata_error": ""},
                    ):
                        payload = cure_chunkhound.run_chunkhound_mcp_preflight_payload(
                            config,
                            repo,
                            cwd=repo,
                            binary=str(binary),
                            transport_modes=("json_line",),
                            stage_timeouts={
                                "spawn": 1.0,
                                "initialize": 2.0,
                                "notifications/initialized": 1.0,
                                "tools/list": 2.0,
                                "daemon_metadata": 1.0,
                            },
                        )
                    self.assertEqual(bool(payload["ok"]), expected_ok, payload)
                    methods = [
                        row.get("method")
                        for row in _read_ledger(ledger)
                        if row["event"] == "request"
                    ]
                    self.assertEqual(
                        methods[:3],
                        ["initialize", "notifications/initialized", "tools/list"],
                    )


class DaemonLogEffectiveFilterAdapterTests(unittest.TestCase):
    """RED contract for the installed-runtime daemon.log exclusion adapter."""

    _EXPECTED_PROBE = textwrap.dedent(
        """
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
    ).strip()

    def _adapter(self) -> Any:
        adapter = getattr(cure_chunkhound, "probe_effective_daemon_log_exclusion", None)
        self.assertTrue(
            callable(adapter),
            "A22 RED: cure_chunkhound.probe_effective_daemon_log_exclusion is required",
        )
        return adapter

    def _invoke(
        self,
        *,
        completed: subprocess.CompletedProcess[str] | None = None,
        side_effect: BaseException | None = None,
    ) -> tuple[dict[str, bool], mock.Mock, Path, Path, Path, dict[str, str]]:
        adapter = self._adapter()
        root = Path("/reviewed/repo")
        config = Path("/reviewed/runtime/chunkhound.json")
        cwd = Path("/reviewed/runtime")
        env = {"PATH": "/runtime/bin", "PYTHONSAFEPATH": "1"}
        runtime_cmd = ["/runtime/python", "-I"]
        run_result = completed or subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"degraded": false, "excluded": true, "ok": true}\n',
            stderr="",
        )
        with mock.patch.object(
            cure_chunkhound, "_chunkhound_runtime_cmd", return_value=runtime_cmd
        ) as runtime, mock.patch.object(
            cure_chunkhound.subprocess,
            "run",
            return_value=run_result,
            side_effect=side_effect,
        ) as run:
            report = adapter(
                repo_path=root,
                config_path=config,
                cwd=cwd,
                binary="/runtime/bin/chunkhound",
                env=MappingProxyType(env),
                timeout=7.5,
            )
        runtime.assert_called_once_with("/runtime/bin/chunkhound")
        run.assert_called_once_with(
            runtime_cmd
            + ["-c", self._EXPECTED_PROBE, str(root.resolve()), str(config.resolve())],
            cwd=str(cwd.resolve()),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            env=env,
            timeout=7.5,
        )
        return report, run, root, config, cwd, env

    def test_probe_uses_exact_runtime_interpreter_argv_and_curated_process_context(
        self,
    ) -> None:
        report, *_unused = self._invoke()
        self.assertEqual(
            report,
            {"ok": True, "excluded": True, "degraded": False},
        )

    def test_runtime_command_uses_the_installed_launchers_isolated_interpreter(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            environment = root / "chunkhound-venv"
            venv.EnvBuilder(with_pip=False, symlinks=True).create(environment)
            interpreter = environment / "bin" / "python"
            self.assertNotEqual(interpreter, interpreter.resolve(strict=True))

            purelib = Path(
                subprocess.check_output(
                    [
                        str(interpreter),
                        "-I",
                        "-c",
                        "import sysconfig; print(sysconfig.get_path('purelib'))",
                    ],
                    text=True,
                ).strip()
            )
            sentinel = purelib / "cure_chunkhound_venv_sentinel.py"
            sentinel.write_text("IDENTITY = 'venv-preserved'\n", encoding="utf-8")

            launcher = root / "chunkhound"
            launcher.write_text(f"#!{interpreter}\n", encoding="utf-8")
            launcher.chmod(0o755)

            runtime_cmd = cure_chunkhound._chunkhound_runtime_cmd(str(launcher))
            self.assertEqual(runtime_cmd, [str(interpreter), "-I"])
            self.assertEqual(
                subprocess.check_output(
                    runtime_cmd
                    + [
                        "-c",
                        "import cure_chunkhound_venv_sentinel as value; "
                        "print(value.IDENTITY)",
                    ],
                    text=True,
                ).strip(),
                "venv-preserved",
            )

    def test_runtime_command_rejects_relative_shebang_interpreter(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            interpreter = root / "relative-python"
            interpreter.write_bytes(Path(sys.executable).read_bytes())
            interpreter.chmod(0o755)
            launcher = root / "chunkhound"
            launcher.write_text("#!relative-python\n", encoding="utf-8")
            launcher.chmod(0o755)

            previous_cwd = Path.cwd()
            try:
                os.chdir(root)
                self.assertIsNone(
                    cure_chunkhound._chunkhound_runtime_cmd(str(launcher))
                )
            finally:
                os.chdir(previous_cwd)

    def test_probe_rejects_every_non_exact_or_failed_runtime_result(self) -> None:
        adapter = self._adapter()
        invalid_results: tuple[tuple[str, object], ...] = (
            (
                "nonzero",
                subprocess.CompletedProcess(
                    args=[],
                    returncode=9,
                    stdout='{"ok":true,"excluded":true,"degraded":false}',
                    stderr="probe failed",
                ),
            ),
            (
                "malformed-json",
                subprocess.CompletedProcess(args=[], returncode=0, stdout="not-json", stderr=""),
            ),
            (
                "extra-fields",
                subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout='{"ok":true,"excluded":true,"degraded":false,"extra":1}',
                    stderr="",
                ),
            ),
            (
                "ok-false",
                subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout='{"ok":false,"excluded":true,"degraded":false}',
                    stderr="",
                ),
            ),
            (
                "excluded-false",
                subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout='{"ok":true,"excluded":false,"degraded":false}',
                    stderr="",
                ),
            ),
            (
                "degraded-true",
                subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout='{"ok":true,"excluded":true,"degraded":true}',
                    stderr="",
                ),
            ),
        )
        for name, completed in invalid_results:
            with self.subTest(name=name), mock.patch.object(
                cure_chunkhound, "_chunkhound_runtime_cmd", return_value=["/runtime/python"]
            ), mock.patch.object(
                cure_chunkhound.subprocess, "run", return_value=completed
            ):
                with self.assertRaises(RuntimeError):
                    adapter(
                        repo_path=Path("/reviewed/repo"),
                        config_path=Path("/reviewed/runtime/chunkhound.json"),
                        cwd=Path("/reviewed/runtime"),
                        binary="/runtime/bin/chunkhound",
                        env={"PATH": "/runtime/bin", "PYTHONSAFEPATH": "1"},
                        timeout=7.5,
                    )

        timeout = subprocess.TimeoutExpired(cmd=["/runtime/python"], timeout=7.5)
        with mock.patch.object(
            cure_chunkhound, "_chunkhound_runtime_cmd", return_value=["/runtime/python"]
        ), mock.patch.object(cure_chunkhound.subprocess, "run", side_effect=timeout):
            with self.assertRaises(RuntimeError):
                adapter(
                    repo_path=Path("/reviewed/repo"),
                    config_path=Path("/reviewed/runtime/chunkhound.json"),
                    cwd=Path("/reviewed/runtime"),
                    binary="/runtime/bin/chunkhound",
                    env={"PATH": "/runtime/bin", "PYTHONSAFEPATH": "1"},
                    timeout=7.5,
                )


class DaemonAwareResearchCallFlowTests(unittest.TestCase):
    """RED ownership contract for supported fresh provider/helper subprocesses."""

    def _registry_api(self) -> tuple[Any, Any]:
        registry_type = getattr(run_module, "OwnedProcessRegistry", None)
        closing_error = getattr(run_module, "OwnedProcessRegistryClosingError", None)
        self.assertIsNotNone(
            registry_type, "run.OwnedProcessRegistry production API is required"
        )
        self.assertIsNotNone(
            closing_error,
            "run.OwnedProcessRegistryClosingError production API is required",
        )
        return registry_type, closing_error

    def test_daemon_route_classifier_separates_supported_rejected_and_bypass_routes(
        self,
    ) -> None:
        """TAP-03 A8/A9: only the fresh Linux indexed helper route owns a keeper."""
        classify = getattr(rf, "_classify_chunkhound_daemon_route", None)
        self.assertIsNotNone(classify, "an explicit production route classifier is required")
        cases = (
            (
                "supported-linux-helper",
                {
                    "provider": "codex",
                    "access_mode": "cli_helper_daemon",
                    "no_index": False,
                    "no_review": False,
                    "platform": "linux",
                },
                "supported",
            ),
            (
                "rejected-non-linux-helper",
                {
                    "provider": "codex",
                    "access_mode": "cli_helper_daemon",
                    "no_index": False,
                    "no_review": False,
                    "platform": "darwin",
                },
                "unsupported",
            ),
            (
                "bypass-http-non-helper",
                {
                    "provider": "openai",
                    "access_mode": "",
                    "no_index": False,
                    "no_review": False,
                    "platform": "linux",
                },
                "bypass",
            ),
            (
                "bypass-no-index",
                {
                    "provider": "codex",
                    "access_mode": "cli_helper_daemon",
                    "no_index": True,
                    "no_review": False,
                    "platform": "linux",
                },
                "bypass",
            ),
            (
                "bypass-no-review-before-platform-rejection",
                {
                    "provider": "codex",
                    "access_mode": "cli_helper_daemon",
                    "no_index": False,
                    "no_review": True,
                    "platform": "darwin",
                },
                "bypass",
            ),
        )
        for name, kwargs, expected in cases:
            with self.subTest(name=name):
                route = classify(**kwargs)
                self.assertEqual(route.value, expected)

    def test_non_linux_indexed_helper_route_fails_before_helper_or_model(self) -> None:
        """TAP-03 A8: helper-bearing indexed routes reject unsupported platforms."""
        from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

        events: list[str] = []

        def forbidden_helper(**_kwargs: Any) -> None:
            events.append("helper")
            raise AssertionError("helper must not run on an unsupported daemon route")

        def forbidden_model(*_args: Any) -> Any:
            events.append("model")
            raise AssertionError("model must not run on an unsupported daemon route")

        with tempfile.TemporaryDirectory() as raw_root, mock.patch.object(
            rf.sys, "platform", "darwin"
        ):
            _, calls = CodexToolProofFlowTests()._run_pr_flow_for_tool_proof(
                root=Path(raw_root) / "unsupported-route",
                profile_resolved="normal",
                multipass_enabled=False,
                llm_side_effect=forbidden_model,
                helper_preflight_side_effect=forbidden_helper,
                expect_error="requires Linux",
            )

        self.assertEqual(events, [])
        self.assertEqual(calls, [])

    def test_http_non_helper_and_no_index_routes_remain_keeper_free(self) -> None:
        """TAP-03 A9: bypass routes retain model behavior without keeper authority."""
        from _reviewflow_unittest_grounding_impl import (
            CodexToolProofFlowTests,
            _sectioned_review_markdown,
        )

        def complete_review(output_path: Path, _work_dir: Path) -> Any:
            output_path.write_text(
                _sectioned_review_markdown(business="APPROVE", technical="APPROVE"),
                encoding="utf-8",
            )
            return rf.LlmRunResult(resume=None, adapter_meta={})

        def forbidden_keeper(*_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("bypass route must not open or adjudicate a keeper")

        def bypass_helper_dispatch(**_kwargs: Any) -> None:
            return None

        non_helper_policy = {
            "env": {},
            "metadata": {
                "provider": "openai",
                "transport": "http",
                "chunkhound_access_mode": None,
            },
            "staged_paths": {},
            "add_dirs": [],
            "codex_config_overrides": [],
            "codex_flags": [],
            "dangerously_bypass_approvals_and_sandbox": False,
        }
        no_index_policy = {
            "env": {},
            "metadata": {
                "provider": "codex",
                "transport": "cli",
                "chunkhound_access_mode": None,
            },
            "staged_paths": {},
            "add_dirs": [],
            "codex_config_overrides": [],
            "codex_flags": [],
            "dangerously_bypass_approvals_and_sandbox": True,
        }

        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            for name, resolved, policy, extra_args in (
                (
                    "http-non-helper",
                    {"provider": "openai", "preset": "test-http", "transport": "http"},
                    non_helper_policy,
                    [],
                ),
                (
                    "no-index",
                    {"provider": "codex", "preset": "test-codex", "transport": "cli"},
                    no_index_policy,
                    ["--no-index", "--prompt", "Custom review without ChunkHound"],
                ),
            ):
                with self.subTest(name=name):
                    expects_index = name == "http-non-helper"

                    def flow_patch(
                        stack: Any, *, expects_index: bool = expects_index
                    ) -> None:
                        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")

                        def bypass_index(**kwargs: Any) -> None:
                            if not expects_index:
                                raise AssertionError("--no-index route attempted top-up indexing")
                            self.assertIsNone(
                                kwargs.get("reviewed_head"),
                                "non-helper route requested keeper receipt authority",
                            )
                            return None

                        stack.enter_context(
                            mock.patch.object(
                                rf,
                                "_run_session_chunkhound_index_with_rebuild_fallback",
                                side_effect=bypass_index,
                            )
                        )
                        stack.enter_context(
                            mock.patch.object(
                                lifecycle.ChunkHoundDaemonLease,
                                "open",
                                autospec=True,
                                side_effect=forbidden_keeper,
                            )
                        )
                        stack.enter_context(
                            mock.patch.object(
                                lifecycle.ChunkHoundDaemonLease,
                                "adjudicate_expected_session",
                                autospec=True,
                                side_effect=forbidden_keeper,
                            )
                        )

                    _, calls = CodexToolProofFlowTests()._run_pr_flow_for_tool_proof(
                        root=root / name,
                        profile_resolved="normal",
                        multipass_enabled=False,
                        llm_side_effect=complete_review,
                        helper_preflight_side_effect=bypass_helper_dispatch,
                        llm_resolved_override=resolved,
                        runtime_policy_override=policy,
                        extra_cli_args=extra_args,
                        flow_patch=flow_patch,
                    )
                    self.assertEqual(calls, ["review.md"])

    def test_supported_fresh_route_threads_one_registry_and_closes_it_before_keeper(self) -> None:
        """A13: helper and every fresh provider launch share command ownership."""
        from _reviewflow_unittest_grounding_impl import (
            CodexToolProofFlowTests,
            _sectioned_review_markdown,
        )

        proof = CodexToolProofFlowTests()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        events: list[str] = []
        registries: list[Any] = []

        class RecordingRegistry:
            def __init__(self) -> None:
                self.state = run_module.OwnedProcessRegistryState.OPEN
                registries.append(self)

            def terminate_and_drain(self) -> None:
                events.append("registry-close")
                self.state = run_module.OwnedProcessRegistryState.CLOSED

        def helper_preflight(**kwargs: Any) -> None:
            self.assertIs(kwargs.get("owned_processes"), registries[0])
            events.append("helper")

        def complete_review(output_path: Path, work_dir: Path, kwargs: Any) -> Any:
            self.assertIs(kwargs.get("owned_processes"), registries[0])
            events.append("provider")
            output_path.write_text(
                _sectioned_review_markdown(business="APPROVE", technical="APPROVE"),
                encoding="utf-8",
            )
            return rf.LlmRunResult(
                resume=None,
                adapter_meta=proof._write_helper_command_events(
                    work_dir=work_dir,
                    commands=["search", "research"],
                ),
            )

        def keeper_close(_lease: Any) -> None:
            self.assertIs(
                registries[0].state,
                run_module.OwnedProcessRegistryState.CLOSED,
            )
            events.append("keeper-close")

        def flow_patch(stack: Any) -> None:
            stack.enter_context(
                mock.patch.object(rf, "OwnedProcessRegistry", RecordingRegistry)
            )
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "close",
                    autospec=True,
                    side_effect=keeper_close,
                )
            )

        with tempfile.TemporaryDirectory() as raw_root:
            proof._run_pr_flow_for_tool_proof(
                root=Path(raw_root) / "owned-route",
                profile_resolved="normal",
                multipass_enabled=False,
                llm_side_effect=complete_review,
                helper_preflight_side_effect=helper_preflight,
                flow_patch=flow_patch,
            )

        self.assertEqual(len(registries), 1)
        self.assertEqual(
            events,
            ["helper", "provider", "registry-close", "keeper-close"],
        )

    def test_supported_fresh_multipass_threads_registry_to_plan_steps_and_synth(self) -> None:
        """A13: concurrent stage workers and synthesis share the fresh scope."""
        from _reviewflow_unittest_grounding_impl import (
            CodexToolProofFlowTests,
            _sectioned_review_markdown,
        )

        proof = CodexToolProofFlowTests()
        registries: list[Any] = []
        seen: list[tuple[str, Any]] = []

        class RecordingRegistry:
            def __init__(self) -> None:
                self.state = run_module.OwnedProcessRegistryState.OPEN
                registries.append(self)

            def terminate_and_drain(self) -> None:
                self.state = run_module.OwnedProcessRegistryState.CLOSED

        def llm(output_path: Path, work_dir: Path, kwargs: Any) -> Any:
            seen.append((output_path.name, kwargs.get("owned_processes")))
            if output_path.name == "review.plan.md":
                output_path.write_text(
                    "```json\n"
                    + json.dumps(
                        {
                            "abort": False,
                            "abort_reason": None,
                            "jira_keys": [],
                            "steps": [
                                {"id": "01", "title": "Ownership", "focus": "registry"}
                            ],
                        }
                    )
                    + "\n```\n",
                    encoding="utf-8",
                )
            elif output_path.name == "review.md":
                output_path.write_text(
                    _sectioned_review_markdown(
                        business="APPROVE", technical="APPROVE"
                    ),
                    encoding="utf-8",
                )
            else:
                output_path.write_text("# Step\n\nOwnership evidence.\n", encoding="utf-8")
            return rf.LlmRunResult(
                resume=None,
                adapter_meta=proof._write_helper_command_events(
                    work_dir=work_dir,
                    commands=["search", "research"],
                ),
            )

        def helper(**kwargs: Any) -> None:
            seen.append(("helper", kwargs.get("owned_processes")))

        def flow_patch(stack: Any) -> None:
            stack.enter_context(
                mock.patch.object(rf, "OwnedProcessRegistry", RecordingRegistry)
            )

        with tempfile.TemporaryDirectory() as raw_root:
            proof._run_pr_flow_for_tool_proof(
                root=Path(raw_root) / "owned-multipass",
                profile_resolved="big",
                multipass_enabled=True,
                step_workers=2,
                llm_side_effect=llm,
                helper_preflight_side_effect=helper,
                flow_patch=flow_patch,
            )

        self.assertEqual(len(registries), 1)
        self.assertEqual(
            [name for name, _ in seen],
            ["helper", "review.plan.md", "review.step-01.md", "review.md"],
        )
        self.assertTrue(all(registry is registries[0] for _, registry in seen))

    def test_standard_big_and_multipass_retain_exactly_one_keeper_through_model_work(
        self,
    ) -> None:
        """A2/A3: every supported fresh review shape holds one command lease."""
        from _reviewflow_unittest_grounding_impl import (
            CodexToolProofFlowTests,
            _sectioned_review_markdown,
        )

        proof = CodexToolProofFlowTests()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        cases = (
            ("standard", "normal", False),
            ("big", "big", False),
            ("multipass", "big", True),
        )
        for label, profile, multipass_enabled in cases:
            with self.subTest(route=label):
                keeper_active = False
                open_calls = 0
                close_calls = 0
                model_calls: list[str] = []

                def llm(output_path: Path, work_dir: Path, _kwargs: Any) -> Any:
                    self.assertTrue(keeper_active, f"{label} model ran without keeper")
                    model_calls.append(output_path.name)
                    if output_path.name == "review.plan.md":
                        output_path.write_text(
                            "```json\n"
                            + json.dumps(
                                {
                                    "abort": False,
                                    "abort_reason": None,
                                    "jira_keys": [],
                                    "steps": [
                                        {
                                            "id": "01",
                                            "title": "Retention",
                                            "focus": "one keeper",
                                        }
                                    ],
                                }
                            )
                            + "\n```\n",
                            encoding="utf-8",
                        )
                    elif output_path.name == "review.md":
                        output_path.write_text(
                            _sectioned_review_markdown(
                                business="APPROVE", technical="APPROVE"
                            ),
                            encoding="utf-8",
                        )
                    else:
                        output_path.write_text(
                            "# Step\n\nRetained keeper evidence.\n", encoding="utf-8"
                        )
                    return rf.LlmRunResult(
                        resume=None,
                        adapter_meta=proof._write_helper_command_events(
                            work_dir=work_dir,
                            commands=["search", "research"],
                        ),
                    )

                def open_keeper(lease: Any) -> Any:
                    nonlocal keeper_active, open_calls
                    self.assertFalse(keeper_active)
                    keeper_active = True
                    open_calls += 1
                    return lease

                def adjudicate(_lease: Any, _receipt: Any, **_kwargs: Any) -> object:
                    self.assertTrue(keeper_active)
                    return object()

                def assert_alive(_lease: Any) -> None:
                    self.assertTrue(keeper_active)

                def close_keeper(_lease: Any) -> None:
                    nonlocal keeper_active, close_calls
                    self.assertTrue(keeper_active)
                    keeper_active = False
                    close_calls += 1

                def helper(**_kwargs: Any) -> None:
                    self.assertTrue(keeper_active)

                def flow_patch(stack: Any) -> None:
                    for method, side_effect in (
                        ("open", open_keeper),
                        ("adjudicate_expected_session", adjudicate),
                        ("assert_alive", assert_alive),
                        ("close", close_keeper),
                    ):
                        stack.enter_context(
                            mock.patch.object(
                                lifecycle.ChunkHoundDaemonLease,
                                method,
                                autospec=True,
                                side_effect=side_effect,
                            )
                        )

                with tempfile.TemporaryDirectory() as raw_root:
                    proof._run_pr_flow_for_tool_proof(
                        root=Path(raw_root) / label,
                        profile_resolved=profile,
                        multipass_enabled=multipass_enabled,
                        llm_side_effect=llm,
                        helper_preflight_side_effect=helper,
                        flow_patch=flow_patch,
                    )

                self.assertEqual(open_calls, 1)
                self.assertEqual(close_calls, 1)
                self.assertFalse(keeper_active)
                self.assertEqual(
                    model_calls,
                    (
                        ["review.plan.md", "review.step-01.md", "review.md"]
                        if multipass_enabled
                        else ["review.md"]
                    ),
                )

    def test_eight_multipass_helper_clients_overlap_while_one_keeper_is_held(
        self,
    ) -> None:
        """TAP-03 A4: eight independent clients overlap without CURe serialization."""
        from _reviewflow_unittest_grounding_impl import (
            CodexToolProofFlowTests,
            _sectioned_review_markdown,
        )

        proof = CodexToolProofFlowTests()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        client_count = 8
        overlap_barrier = threading.Barrier(client_count, timeout=5.0)
        state_lock = threading.Lock()
        event_log_lock = threading.Lock()
        keeper_active = False
        active_clients = 0
        maximum_overlap = 0
        client_threads: set[int] = set()
        observed_generations: list[str] = []
        close_calls = 0

        def record_tool_proof(work_dir: Path) -> dict[str, object]:
            with event_log_lock:
                return proof._write_helper_command_events(
                    work_dir=work_dir,
                    commands=["search", "research"],
                )

        def llm(output_path: Path, work_dir: Path, _kwargs: Any) -> Any:
            nonlocal active_clients, maximum_overlap
            if output_path.name == "review.plan.md":
                output_path.write_text(
                    "```json\n"
                    + json.dumps(
                        {
                            "abort": False,
                            "abort_reason": None,
                            "jira_keys": [],
                            "steps": [
                                {
                                    "id": f"{index:02d}",
                                    "title": f"Client {index}",
                                    "focus": "independent helper overlap",
                                }
                                for index in range(1, client_count + 1)
                            ],
                        }
                    )
                    + "\n```\n",
                    encoding="utf-8",
                )
            elif output_path.name.startswith("review.step-"):
                with state_lock:
                    self.assertTrue(keeper_active, "step client started without keeper")
                    active_clients += 1
                    maximum_overlap = max(maximum_overlap, active_clients)
                    client_threads.add(threading.get_ident())
                    observed_generations.append("expected-generation")
                try:
                    overlap_barrier.wait()
                    with state_lock:
                        self.assertTrue(
                            keeper_active,
                            "keeper closed while helper clients overlapped",
                        )
                    output_path.write_text(
                        "# Step\n\nIndependent helper evidence.\n",
                        encoding="utf-8",
                    )
                finally:
                    with state_lock:
                        active_clients -= 1
            elif output_path.name == "review.md":
                with state_lock:
                    self.assertTrue(keeper_active, "keeper closed before synthesis")
                    self.assertEqual(active_clients, 0)
                output_path.write_text(
                    _sectioned_review_markdown(
                        business="APPROVE", technical="APPROVE"
                    ),
                    encoding="utf-8",
                )
            else:
                raise AssertionError(f"unexpected output path: {output_path}")
            return rf.LlmRunResult(
                resume=None,
                adapter_meta=record_tool_proof(work_dir),
            )

        def open_keeper(lease: Any) -> Any:
            nonlocal keeper_active
            with state_lock:
                self.assertFalse(keeper_active)
                keeper_active = True
            return lease

        def adjudicate(_lease: Any, _receipt: Any, **_kwargs: Any) -> object:
            with state_lock:
                self.assertTrue(keeper_active)
            return object()

        def close_keeper(_lease: Any) -> None:
            nonlocal close_calls, keeper_active
            with state_lock:
                self.assertTrue(keeper_active)
                self.assertEqual(active_clients, 0)
                keeper_active = False
                close_calls += 1

        def flow_patch(stack: Any) -> None:
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "open",
                    autospec=True,
                    side_effect=open_keeper,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "adjudicate_expected_session",
                    autospec=True,
                    side_effect=adjudicate,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "close",
                    autospec=True,
                    side_effect=close_keeper,
                )
            )

        with tempfile.TemporaryDirectory() as raw_root:
            root, calls = proof._run_pr_flow_for_tool_proof(
                root=Path(raw_root) / "eight-client-overlap",
                profile_resolved="big",
                multipass_enabled=True,
                step_workers=client_count,
                llm_side_effect=llm,
                flow_patch=flow_patch,
            )
            session_dir = next((root / "sandboxes").iterdir())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))

        self.assertEqual(maximum_overlap, client_count)
        self.assertEqual(len(client_threads), client_count)
        self.assertEqual(observed_generations, ["expected-generation"] * client_count)
        self.assertEqual(close_calls, 1)
        self.assertFalse(keeper_active)
        self.assertEqual(meta["multipass"]["effective_step_workers"], client_count)
        self.assertEqual(
            sorted(name for name in calls if name.startswith("review.step-")),
            [f"review.step-{index:02d}.md" for index in range(1, client_count + 1)],
        )

    def test_multipass_keeper_loss_after_plan_stops_steps_without_replay(self) -> None:
        """TAP-03 A12: post-dispatch keeper loss cannot replay or dispatch steps."""
        from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

        proof = CodexToolProofFlowTests()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        seeded_secret = "daemon-continuity-secret-SHOULD-NOT-PERSIST"  # pragma: allowlist secret
        continuity_failure = RuntimeError(
            f"keeper continuity lost after plan dispatch: {seeded_secret}"
        )
        continuity_checks: list[str] = []

        def planner(output_path: Path, work_dir: Path) -> Any:
            self.assertEqual(output_path.name, "review.plan.md")
            output_path.write_text(
                "```json\n"
                + json.dumps(
                    {
                        "abort": False,
                        "abort_reason": None,
                        "jira_keys": [],
                        "steps": [
                            {"id": "01", "title": "Must not dispatch", "focus": "loss"}
                        ],
                    }
                )
                + "\n```\n",
                encoding="utf-8",
            )
            return rf.LlmRunResult(
                resume=None,
                adapter_meta=proof._write_helper_command_events(
                    work_dir=work_dir,
                    commands=["search", "research"],
                ),
            )

        def assert_lost(_lease: Any) -> None:
            boundaries = (
                "before-helper",
                "after-helper",
                "before-plan",
                "after-plan",
                "before-step",
            )
            boundary = boundaries[len(continuity_checks)]
            continuity_checks.append(boundary)
            if boundary == "before-step":
                raise continuity_failure

        def forbidden_synth(**_kwargs: Any) -> None:
            raise AssertionError("synthesis dispatched after keeper continuity loss")

        def flow_patch(stack: Any) -> None:
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "assert_alive",
                    autospec=True,
                    side_effect=assert_lost,
                )
            )

        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root) / "post-plan-keeper-loss"
            _, calls = proof._run_pr_flow_for_tool_proof(
                root=root,
                profile_resolved="big",
                multipass_enabled=True,
                step_workers=1,
                llm_side_effect=planner,
                synth_stage_side_effect=forbidden_synth,
                flow_patch=flow_patch,
                expect_error=(
                    r"ChunkHound daemon continuity failed \(RuntimeError\); "
                    r"dispatched model work was not replayed\."
                ),
            )
            session_dir = next((root / "sandboxes").iterdir())
            persisted_meta = (session_dir / "meta.json").read_text(encoding="utf-8")

        self.assertNotIn(seeded_secret, persisted_meta)
        self.assertEqual(calls, ["review.plan.md"])
        self.assertEqual(
            continuity_checks,
            [
                "before-helper",
                "after-helper",
                "before-plan",
                "after-plan",
                "before-step",
            ],
        )

    def test_multipass_keeper_loss_after_steps_stops_synth_without_replay(self) -> None:
        """TAP-03 A12: post-step loss stops synthesis without replaying work."""
        from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

        proof = CodexToolProofFlowTests()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        continuity_failure = RuntimeError("keeper continuity lost before synthesis")
        continuity_checks: list[str] = []

        def llm(output_path: Path, work_dir: Path) -> Any:
            if output_path.name == "review.plan.md":
                output_path.write_text(
                    "```json\n"
                    + json.dumps(
                        {
                            "abort": False,
                            "abort_reason": None,
                            "jira_keys": [],
                            "steps": [
                                {"id": "01", "title": "Completed once", "focus": "loss"}
                            ],
                        }
                    )
                    + "\n```\n",
                    encoding="utf-8",
                )
            elif output_path.name == "review.step-01.md":
                output_path.write_text("# Step\n\nCompleted evidence.\n", encoding="utf-8")
            else:
                raise AssertionError(f"model work replayed or synthesis dispatched: {output_path.name}")
            return rf.LlmRunResult(
                resume=None,
                adapter_meta=proof._write_helper_command_events(
                    work_dir=work_dir,
                    commands=["search", "research"],
                ),
            )

        def assert_continuity(_lease: Any) -> None:
            boundaries = (
                "before-helper",
                "after-helper",
                "before-plan",
                "after-plan",
                "before-step",
                "after-step",
                "before-synth",
            )
            boundary = boundaries[len(continuity_checks)]
            continuity_checks.append(boundary)
            if boundary == "before-synth":
                raise continuity_failure

        def flow_patch(stack: Any) -> None:
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "assert_alive",
                    autospec=True,
                    side_effect=assert_continuity,
                )
            )

        with tempfile.TemporaryDirectory() as raw_root:
            _, calls = proof._run_pr_flow_for_tool_proof(
                root=Path(raw_root) / "post-step-keeper-loss",
                profile_resolved="big",
                multipass_enabled=True,
                step_workers=1,
                llm_side_effect=llm,
                flow_patch=flow_patch,
                expect_error=(
                    r"ChunkHound daemon continuity failed \(RuntimeError\); "
                    r"dispatched model work was not replayed\."
                ),
            )

        self.assertEqual(calls, ["review.plan.md", "review.step-01.md"])
        self.assertEqual(
            continuity_checks,
            [
                "before-helper",
                "after-helper",
                "before-plan",
                "after-plan",
                "before-step",
                "after-step",
                "before-synth",
            ],
        )

    def test_multipass_keeper_loss_after_step_llm_aborts_acceptance_without_replay(
        self,
    ) -> None:
        """TAP-03 A12: a daemon dying mid-step is detected post-LLM; the step
        result is never accepted and synthesis is never dispatched."""
        from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

        proof = CodexToolProofFlowTests()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        continuity_failure = RuntimeError("keeper continuity lost during step LLM call")
        continuity_checks: list[str] = []

        def llm(output_path: Path, work_dir: Path) -> Any:
            if output_path.name == "review.plan.md":
                output_path.write_text(
                    "```json\n"
                    + json.dumps(
                        {
                            "abort": False,
                            "abort_reason": None,
                            "jira_keys": [],
                            "steps": [
                                {"id": "01", "title": "Completed once", "focus": "loss"}
                            ],
                        }
                    )
                    + "\n```\n",
                    encoding="utf-8",
                )
            elif output_path.name == "review.step-01.md":
                output_path.write_text(
                    "# Step\n\nCompleted evidence.\n", encoding="utf-8"
                )
            else:
                raise AssertionError(
                    f"model work replayed or synthesis dispatched: {output_path.name}"
                )
            return rf.LlmRunResult(
                resume=None,
                adapter_meta=proof._write_helper_command_events(
                    work_dir=work_dir,
                    commands=["search", "research"],
                ),
            )

        def assert_continuity(_lease: Any) -> None:
            boundaries = (
                "before-helper",
                "after-helper",
                "before-plan",
                "after-plan",
                "before-step",
                "after-step",
            )
            boundary = boundaries[len(continuity_checks)]
            continuity_checks.append(boundary)
            if boundary == "after-step":
                raise continuity_failure

        def forbidden_synth(**_kwargs: Any) -> None:
            raise AssertionError("synthesis dispatched after mid-step keeper loss")

        def flow_patch(stack: Any) -> None:
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "assert_alive",
                    autospec=True,
                    side_effect=assert_continuity,
                )
            )

        with tempfile.TemporaryDirectory() as raw_root:
            _, calls = proof._run_pr_flow_for_tool_proof(
                root=Path(raw_root) / "mid-step-keeper-loss",
                profile_resolved="big",
                multipass_enabled=True,
                step_workers=1,
                llm_side_effect=llm,
                synth_stage_side_effect=forbidden_synth,
                flow_patch=flow_patch,
                expect_error=(
                    r"ChunkHound daemon continuity failed \(RuntimeError\); "
                    r"dispatched model work was not replayed\."
                ),
            )

        self.assertEqual(calls, ["review.plan.md", "review.step-01.md"])
        self.assertEqual(
            continuity_checks,
            [
                "before-helper",
                "after-helper",
                "before-plan",
                "after-plan",
                "before-step",
                "after-step",
            ],
        )

    def test_singlepass_keeper_loss_after_draft_aborts_before_reconcile(self) -> None:
        """TAP-03 A12: a daemon dying during the singlepass draft is detected
        post-LLM; the draft is not accepted and reconcile is never dispatched."""
        from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

        proof = CodexToolProofFlowTests()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        continuity_failure = RuntimeError("keeper continuity lost during draft LLM call")
        continuity_checks: list[str] = []

        def draft(output_path: Path, work_dir: Path) -> Any:
            self.assertEqual(output_path.name, "pr_context_draft.md")
            output_path.write_text("blind draft\n", encoding="utf-8")
            return rf.LlmRunResult(
                resume=None,
                adapter_meta=proof._write_helper_command_events(
                    work_dir=work_dir,
                    commands=["search", "research"],
                ),
            )

        def assert_continuity(_lease: Any) -> None:
            boundaries = (
                "before-helper",
                "after-helper",
                "before-draft",
                "after-draft",
            )
            boundary = boundaries[len(continuity_checks)]
            continuity_checks.append(boundary)
            if boundary == "after-draft":
                raise continuity_failure

        def flow_patch(stack: Any) -> None:
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "assert_alive",
                    autospec=True,
                    side_effect=assert_continuity,
                )
            )

        with tempfile.TemporaryDirectory() as raw_root:
            _, calls = proof._run_pr_flow_for_tool_proof(
                root=Path(raw_root) / "mid-draft-keeper-loss",
                profile_resolved="normal",
                multipass_enabled=False,
                llm_side_effect=draft,
                extra_cli_args=["--pr-context"],
                pr_context_result_override={
                    "orientation_brief": "singlepass context",
                    "meta": {},
                },
                flow_patch=flow_patch,
                expect_error=(
                    r"ChunkHound daemon continuity failed \(RuntimeError\); "
                    r"dispatched model work was not replayed\."
                ),
            )

        self.assertEqual(calls, ["pr_context_draft.md"])
        self.assertEqual(
            continuity_checks,
            ["before-helper", "after-helper", "before-draft", "after-draft"],
        )

    def test_singlepass_keeper_loss_before_reconcile_does_not_replay_draft(self) -> None:
        """TAP-03 A12: a completed draft is not replayed after keeper loss."""
        from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

        proof = CodexToolProofFlowTests()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        continuity_failure = RuntimeError("keeper continuity lost before reconcile")
        continuity_checks: list[str] = []

        def draft(output_path: Path, work_dir: Path) -> Any:
            self.assertEqual(output_path.name, "pr_context_draft.md")
            output_path.write_text("blind draft\n", encoding="utf-8")
            return rf.LlmRunResult(
                resume=None,
                adapter_meta=proof._write_helper_command_events(
                    work_dir=work_dir,
                    commands=["search", "research"],
                ),
            )

        def assert_continuity(_lease: Any) -> None:
            boundaries = (
                "before-helper",
                "after-helper",
                "before-draft",
                "after-draft",
                "before-reconcile",
            )
            boundary = boundaries[len(continuity_checks)]
            continuity_checks.append(boundary)
            if boundary == "before-reconcile":
                raise continuity_failure

        def flow_patch(stack: Any) -> None:
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "assert_alive",
                    autospec=True,
                    side_effect=assert_continuity,
                )
            )

        with tempfile.TemporaryDirectory() as raw_root:
            _, calls = proof._run_pr_flow_for_tool_proof(
                root=Path(raw_root) / "singlepass-reconcile-loss",
                profile_resolved="normal",
                multipass_enabled=False,
                llm_side_effect=draft,
                extra_cli_args=["--pr-context"],
                pr_context_result_override={
                    "orientation_brief": "singlepass context",
                    "meta": {},
                },
                flow_patch=flow_patch,
                expect_error=(
                    r"ChunkHound daemon continuity failed \(RuntimeError\); "
                    r"dispatched model work was not replayed\."
                ),
            )

        self.assertEqual(calls, ["pr_context_draft.md"])
        self.assertEqual(
            continuity_checks,
            [
                "before-helper",
                "after-helper",
                "before-draft",
                "after-draft",
                "before-reconcile",
            ],
        )

    def test_teardown_reports_unverified_daemon_release(self) -> None:
        """FIX 5: an otherwise-successful run whose daemon lease closed but was
        not verified released within the bounded deadline surfaces as a
        teardown failure."""
        from _reviewflow_unittest_grounding_impl import (
            CodexToolProofFlowTests,
            _sectioned_review_markdown,
        )

        proof = CodexToolProofFlowTests()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")

        def model(output_path: Path, work_dir: Path) -> Any:
            output_path.write_text(
                _sectioned_review_markdown(business="APPROVE", technical="APPROVE"),
                encoding="utf-8",
            )
            return rf.LlmRunResult(
                resume=None,
                adapter_meta=proof._write_helper_command_events(
                    work_dir=work_dir,
                    commands=["search", "research"],
                ),
            )

        def flow_patch(stack: Any) -> None:
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "wait_for_daemon_release",
                    autospec=True,
                    return_value=False,
                )
            )

        with tempfile.TemporaryDirectory() as raw_root:
            _, calls = proof._run_pr_flow_for_tool_proof(
                root=Path(raw_root) / "unverified-daemon-release",
                profile_resolved="normal",
                multipass_enabled=False,
                llm_side_effect=model,
                flow_patch=flow_patch,
                expect_error_type=RuntimeError,
                expect_error=(
                    r"ChunkHound daemon release was not verified within the "
                    r"bounded deadline after lease close"
                ),
            )

        self.assertEqual(calls, ["review.md"])

    def test_teardown_reports_daemon_release_verification_error(self) -> None:
        """FIX 5: a RuntimeError from the release verification itself (e.g. a
        lease without a generation probe) is recorded as a teardown failure."""
        from _reviewflow_unittest_grounding_impl import (
            CodexToolProofFlowTests,
            _sectioned_review_markdown,
        )

        proof = CodexToolProofFlowTests()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")

        def model(output_path: Path, work_dir: Path) -> Any:
            output_path.write_text(
                _sectioned_review_markdown(business="APPROVE", technical="APPROVE"),
                encoding="utf-8",
            )
            return rf.LlmRunResult(
                resume=None,
                adapter_meta=proof._write_helper_command_events(
                    work_dir=work_dir,
                    commands=["search", "research"],
                ),
            )

        def flow_patch(stack: Any) -> None:
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "wait_for_daemon_release",
                    autospec=True,
                    side_effect=RuntimeError("no generation probe attached"),
                )
            )

        with tempfile.TemporaryDirectory() as raw_root:
            _, calls = proof._run_pr_flow_for_tool_proof(
                root=Path(raw_root) / "daemon-release-verify-error",
                profile_resolved="normal",
                multipass_enabled=False,
                llm_side_effect=model,
                flow_patch=flow_patch,
                expect_error_type=RuntimeError,
                expect_error=r"no generation probe attached",
            )

        self.assertEqual(calls, ["review.md"])

    def test_fresh_multipass_interrupt_tears_down_workers_before_executor_join(self) -> None:
        """A15: terminal interruption releases owned workers before pool shutdown."""
        from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

        proof = CodexToolProofFlowTests()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        expected = KeyboardInterrupt("multipass collection interrupted")
        events: list[str] = []
        release_worker = threading.Event()
        worker_started = threading.Event()
        watchdog_released = threading.Event()
        registry_close_calls: list[str] = []
        keeper_close_calls: list[str] = []
        real_executor = rf.ThreadPoolExecutor

        class RecordingExecutor(real_executor):
            def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> bool:
                result = super().__exit__(exc_type, exc_value, traceback)
                events.append("executor-joined")
                return result

        class RecordingRegistry:
            def __init__(self) -> None:
                self.state = run_module.OwnedProcessRegistryState.OPEN

            def terminate_and_drain(self) -> None:
                registry_close_calls.append("close")
                events.append("registry-close")
                self.state = run_module.OwnedProcessRegistryState.CLOSED
                release_worker.set()

        def planner(output_path: Path, work_dir: Path) -> Any:
            self.assertEqual(output_path.name, "review.plan.md")
            output_path.write_text(
                "```json\n"
                + json.dumps(
                    {
                        "abort": False,
                        "abort_reason": None,
                        "jira_keys": [],
                        "steps": [
                            {"id": "01", "title": "Worker one", "focus": "blocking"},
                            {"id": "02", "title": "Worker two", "focus": "blocking"},
                        ],
                    }
                )
                + "\n```\n",
                encoding="utf-8",
            )
            return rf.LlmRunResult(
                resume=None,
                adapter_meta=proof._write_helper_command_events(
                    work_dir=work_dir,
                    commands=["search", "research"],
                ),
            )

        def blocking_worker(**_kwargs: Any) -> Any:
            events.append("worker-started")
            worker_started.set()
            self.assertTrue(release_worker.wait(3.0), "bounded worker release timed out")
            events.append("worker-released")
            return mock.Mock()

        def interrupt_collection(_futures: Any) -> Any:
            self.assertTrue(worker_started.wait(1.0), "worker did not start before collection")
            events.append("collection-interrupt")
            raise expected

        def keeper_close(_lease: Any) -> None:
            keeper_close_calls.append("close")
            events.append("keeper-close")

        def forbidden_synth(**_kwargs: Any) -> None:
            raise AssertionError("synth must not run after multipass interruption")

        def flow_patch(stack: Any) -> None:
            stack.enter_context(mock.patch.object(rf, "OwnedProcessRegistry", RecordingRegistry))
            stack.enter_context(mock.patch.object(rf, "ThreadPoolExecutor", RecordingExecutor))
            stack.enter_context(mock.patch.object(rf, "as_completed", side_effect=interrupt_collection))
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "_run_multipass_step_llm",
                    side_effect=blocking_worker,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "close",
                    autospec=True,
                    side_effect=keeper_close,
                )
            )

        def watchdog() -> None:
            if not release_worker.wait(1.0):
                watchdog_released.set()
                events.append("watchdog-release")
                release_worker.set()

        watchdog_thread = threading.Thread(target=watchdog, name="multipass-abort-watchdog")
        watchdog_thread.start()
        try:
            with tempfile.TemporaryDirectory() as raw_root:
                _, calls = proof._run_pr_flow_for_tool_proof(
                    root=Path(raw_root) / "interrupted-multipass",
                    profile_resolved="big",
                    multipass_enabled=True,
                    step_workers=2,
                    llm_side_effect=planner,
                    synth_stage_side_effect=forbidden_synth,
                    flow_patch=flow_patch,
                    expected_exception=expected,
                )
        finally:
            release_worker.set()
            watchdog_thread.join(3.0)

        self.assertFalse(watchdog_thread.is_alive())
        self.assertFalse(
            watchdog_released.is_set(),
            "watchdog, not owner teardown, released the blocked worker",
        )
        self.assertEqual(calls, ["review.plan.md"])
        self.assertEqual(registry_close_calls, ["close"])
        self.assertEqual(keeper_close_calls, ["close"])
        self.assertLess(events.index("collection-interrupt"), events.index("registry-close"))
        self.assertLess(events.index("registry-close"), events.index("worker-released"))
        self.assertLess(events.index("worker-released"), events.index("executor-joined"))
        self.assertLess(events.index("executor-joined"), events.index("keeper-close"))

    def test_bypass_route_does_not_construct_owned_process_registry(self) -> None:
        """A13 exclusion: no-index fresh review has no command ownership scope."""
        from _reviewflow_unittest_grounding_impl import (
            CodexToolProofFlowTests,
            _sectioned_review_markdown,
        )

        def complete_review(output_path: Path, _work_dir: Path, kwargs: Any) -> Any:
            self.assertIsNone(kwargs.get("owned_processes"))
            output_path.write_text(
                _sectioned_review_markdown(business="APPROVE", technical="APPROVE"),
                encoding="utf-8",
            )
            return rf.LlmRunResult(resume=None, adapter_meta={})

        def forbidden_registry() -> None:
            raise AssertionError("bypass route constructed OwnedProcessRegistry")

        def flow_patch(stack: Any) -> None:
            stack.enter_context(
                mock.patch.object(rf, "OwnedProcessRegistry", side_effect=forbidden_registry)
            )

        with tempfile.TemporaryDirectory() as raw_root:
            _, calls = CodexToolProofFlowTests()._run_pr_flow_for_tool_proof(
                root=Path(raw_root) / "no-index-owned-route",
                profile_resolved="normal",
                multipass_enabled=False,
                llm_side_effect=complete_review,
                extra_cli_args=["--no-index", "--prompt", "custom"],
                flow_patch=flow_patch,
            )
        self.assertEqual(calls, ["review.md"])

    def test_keeper_close_failure_runs_all_cleanup_and_remains_visible(self) -> None:
        """TAP-03 A14: close failure cannot skip sensitive or output cleanup."""
        from _reviewflow_unittest_grounding_impl import (
            CodexToolProofFlowTests,
            _sectioned_review_markdown,
        )

        proof = CodexToolProofFlowTests()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        close_failure = RuntimeError("keeper close failed")
        events: list[str] = []
        original_sensitive_cleanup = rf.cleanup_sensitive_staged_paths
        original_clear_output = rf.clear_active_output
        original_stop = rf.ReviewflowOutput.stop

        def complete_review(output_path: Path, work_dir: Path) -> Any:
            output_path.write_text(
                _sectioned_review_markdown(business="APPROVE", technical="APPROVE"),
                encoding="utf-8",
            )
            return rf.LlmRunResult(
                resume=None,
                adapter_meta=proof._write_helper_command_events(
                    work_dir=work_dir,
                    commands=["search", "research"],
                ),
            )

        def fail_close(_lease: Any) -> None:
            events.append("keeper-close")
            raise close_failure

        def sensitive_cleanup(staged_paths: Any, **_kwargs: Any) -> None:
            events.append("sensitive-cleanup")
            original_sensitive_cleanup(staged_paths)

        def clear_output(output: Any) -> None:
            events.append("clear-output")
            original_clear_output(output)

        def stop_output(output: Any) -> None:
            events.append("output-stop")
            original_stop(output)

        def flow_patch(stack: Any) -> None:
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "close",
                    autospec=True,
                    side_effect=fail_close,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "cleanup_sensitive_staged_paths",
                    side_effect=sensitive_cleanup,
                )
            )
            stack.enter_context(
                mock.patch.object(rf, "clear_active_output", side_effect=clear_output)
            )
            stack.enter_context(
                mock.patch.object(
                    rf.ReviewflowOutput,
                    "stop",
                    autospec=True,
                    side_effect=stop_output,
                )
            )

        with tempfile.TemporaryDirectory() as raw_root:
            proof._run_pr_flow_for_tool_proof(
                root=Path(raw_root) / "close-failure",
                profile_resolved="normal",
                multipass_enabled=False,
                llm_side_effect=complete_review,
                flow_patch=flow_patch,
                expected_exception=close_failure,
            )

        self.assertEqual(
            events,
            ["keeper-close", "sensitive-cleanup", "clear-output", "output-stop"],
        )

    def test_primary_failure_survives_close_failure_with_teardown_reported(self) -> None:
        """TAP-03 A14: primary and teardown outcomes both remain reportable."""
        from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

        proof = CodexToolProofFlowTests()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        primary_failure = RuntimeError("primary model failure")
        close_failure = RuntimeError("keeper close failure after primary")
        close_calls: list[str] = []

        def fail_model(*_args: Any) -> Any:
            raise primary_failure

        def fail_close(_lease: Any) -> None:
            close_calls.append("close")
            raise close_failure

        def flow_patch(stack: Any) -> None:
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "close",
                    autospec=True,
                    side_effect=fail_close,
                )
            )

        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root) / "primary-and-close-failure"
            proof._run_pr_flow_for_tool_proof(
                root=root,
                profile_resolved="normal",
                multipass_enabled=False,
                llm_side_effect=fail_model,
                flow_patch=flow_patch,
                expected_exception=primary_failure,
            )
            session_dir = next((root / "sandboxes").iterdir())
            meta = json.loads(
                (session_dir / "meta.json").read_text(encoding="utf-8")
            )

        self.assertEqual(close_calls, ["close"])
        self.assertEqual(meta["teardown"]["status"], "failed")
        self.assertEqual(meta["teardown"]["category"], "RuntimeError")

    def test_all_teardown_failure_categories_are_persisted_in_cleanup_order(self) -> None:
        from _reviewflow_unittest_grounding_impl import (
            CodexToolProofFlowTests,
            _sectioned_review_markdown,
        )

        proof = CodexToolProofFlowTests()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        owned_failure = OSError("owned process cleanup failed")
        keeper_failure = RuntimeError("keeper cleanup failed")
        events: list[str] = []
        original_sensitive_cleanup = rf.cleanup_sensitive_staged_paths

        class FailingRegistry:
            def __init__(self) -> None:
                self.state = run_module.OwnedProcessRegistryState.OPEN

            def terminate_and_drain(self) -> None:
                events.append("owned-processes")
                self.state = run_module.OwnedProcessRegistryState.CLOSED
                raise owned_failure

        def complete_review(output_path: Path, work_dir: Path) -> Any:
            output_path.write_text(
                _sectioned_review_markdown(business="APPROVE", technical="APPROVE"),
                encoding="utf-8",
            )
            return rf.LlmRunResult(
                resume=None,
                adapter_meta=proof._write_helper_command_events(
                    work_dir=work_dir,
                    commands=["search", "research"],
                ),
            )

        def fail_keeper_close(_lease: Any) -> None:
            events.append("keeper-close")
            raise keeper_failure

        def sensitive_cleanup(staged_paths: Any, **_kwargs: Any) -> None:
            events.append("sensitive-cleanup")
            original_sensitive_cleanup(staged_paths)

        def flow_patch(stack: Any) -> None:
            stack.enter_context(mock.patch.object(rf, "OwnedProcessRegistry", FailingRegistry))
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "close",
                    autospec=True,
                    side_effect=fail_keeper_close,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "cleanup_sensitive_staged_paths",
                    side_effect=sensitive_cleanup,
                )
            )

        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root) / "all-teardown-failures"
            proof._run_pr_flow_for_tool_proof(
                root=root,
                profile_resolved="normal",
                multipass_enabled=False,
                llm_side_effect=complete_review,
                flow_patch=flow_patch,
                expected_exception=owned_failure,
            )
            session_dir = next((root / "sandboxes").iterdir())
            meta = json.loads(
                (session_dir / "meta.json").read_text(encoding="utf-8")
            )

        self.assertEqual(
            events,
            ["owned-processes", "keeper-close", "sensitive-cleanup"],
        )
        self.assertEqual(
            meta["teardown"]["failures"],
            [
                {"stage": "owned_processes", "category": "OSError"},
                {"stage": "keeper_close", "category": "RuntimeError"},
            ],
        )

    def test_fresh_indexed_codex_helper_route_is_ready_before_orientation(
        self,
    ) -> None:
        """TAP-03 A1/A11: orientation is model work and must be last here."""
        from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        events: list[str] = []
        receipt_boundary: list[Any] = []
        stop_at_orientation = RuntimeError("stop at optional orientation")
        expected = [
            "final-index/receipt-ready",
            "keeper-native-health/expected-session-ready",
            "helper-preflight",
            "orientation",
        ]

        def final_index_receipt_boundary(**kwargs: Any) -> Any:
            identity = lifecycle.LaunchIdentity(
                resolved_executable=Path("/usr/bin/chunkhound"),
                canonical_root=Path(kwargs["repo_dir"]).resolve(),
                resolved_config_path=Path(kwargs["chunkhound_cfg_path"]).resolve(),
                config_digest="a" * 64,
                resolved_database_path=Path(kwargs["chunkhound_db_path"]).resolve(),
                cwd=Path(kwargs["chunkhound_work_dir"]).resolve(),
                curated_environment_keys=("PATH", "PYTHONSAFEPATH"),
                environment_equality_digest="b" * 64,
            )
            receipt = lifecycle.ExpectedSessionReceiptV1(
                schema_version=1,
                canonical_root=identity.canonical_root,
                reviewed_head="1" * 40,
                resolved_config_path=identity.resolved_config_path,
                config_digest=identity.config_digest,
                resolved_database_path=identity.resolved_database_path,
                total_chunks=1,
                launch_identity_projection=identity,
            )
            self.assertIs(receipt.launch_identity_projection, identity)
            with self.assertRaises(FrozenInstanceError):
                receipt.total_chunks = 2
            receipt_boundary.append(receipt)
            events.append("final-index/receipt-ready")
            return receipt

        def keeper_readiness(lease: Any, receipt: Any, **kwargs: Any) -> object:
            del kwargs
            self.assertEqual(len(receipt_boundary), 1)
            self.assertIs(receipt, receipt_boundary[0])
            self.assertEqual(lease.launch_identity, receipt.launch_identity_projection)
            events.append("keeper-native-health/expected-session-ready")
            return object()

        def helper_preflight(**kwargs: Any) -> None:
            del kwargs
            events.append("helper-preflight")

        def orientation_model(*_args: Any) -> Any:
            events.append("orientation")
            raise stop_at_orientation

        def gh_list(
            *, host: str, path: str, allow_public_fallback: bool = False
        ) -> list[dict[str, object]]:
            self.assertEqual(host, "github.com")
            self.assertTrue(allow_public_fallback)
            if path.endswith("/comments") and "/issues/" in path:
                return [
                    {
                        "id": 1,
                        "body": "orientation-worthy discussion",
                        "created_at": "2026-07-30T00:00:00Z",
                    }
                ]
            return []

        def flow_patch(stack: Any) -> None:
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "_run_session_chunkhound_index_with_rebuild_fallback",
                    side_effect=final_index_receipt_boundary,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "select_git_tracked_source_witness",
                    return_value=lifecycle.ExpectedSearchWitness(
                        relative_path="source.py",
                        literal="orientation_witness",
                    ),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "open",
                    autospec=True,
                    side_effect=lambda lease: lease,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "adjudicate_expected_session",
                    autospec=True,
                    side_effect=keeper_readiness,
                )
            )

        with tempfile.TemporaryDirectory() as raw_root:
            CodexToolProofFlowTests()._run_pr_flow_for_tool_proof(
                root=Path(raw_root) / "route",
                profile_resolved="normal",
                multipass_enabled=False,
                llm_side_effect=orientation_model,
                helper_preflight_side_effect=helper_preflight,
                extra_cli_args=["--pr-context"],
                gh_api_list_side_effect=gh_list,
                flow_patch=flow_patch,
                expected_exception=stop_at_orientation,
            )

        self.assertEqual(
            events,
            expected,
            "optional orientation dispatched before final-index receipt, exact-identity "
            "keeper readiness, and helper preflight",
        )

    def test_keeper_readiness_failure_prevents_helper_and_all_model_work(self) -> None:
        """TAP-03: failed native readiness is terminal before helper/model work."""
        from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        events: list[str] = []
        seeded_secret = "daemon-auth-token-SHOULD-NOT-PERSIST"  # pragma: allowlist secret
        readiness_failure = lifecycle.ExpectedSessionReadinessError(
            f"expected session is not ready: {seeded_secret}"
        )

        def final_index_receipt_boundary(**kwargs: Any) -> Any:
            identity = lifecycle.LaunchIdentity(
                resolved_executable=Path("/usr/bin/chunkhound"),
                canonical_root=Path(kwargs["repo_dir"]).resolve(),
                resolved_config_path=Path(kwargs["chunkhound_cfg_path"]).resolve(),
                config_digest="a" * 64,
                resolved_database_path=Path(kwargs["chunkhound_db_path"]).resolve(),
                cwd=Path(kwargs["chunkhound_work_dir"]).resolve(),
                curated_environment_keys=("PATH", "PYTHONSAFEPATH"),
                environment_equality_digest="b" * 64,
            )
            events.append("final-index/receipt-ready")
            return lifecycle.ExpectedSessionReceiptV1(
                schema_version=1,
                canonical_root=identity.canonical_root,
                reviewed_head="1" * 40,
                resolved_config_path=identity.resolved_config_path,
                config_digest=identity.config_digest,
                resolved_database_path=identity.resolved_database_path,
                total_chunks=1,
                launch_identity_projection=identity,
            )

        def fail_readiness(*_args: Any, **_kwargs: Any) -> None:
            events.append("keeper-readiness-failed")
            raise readiness_failure

        real_close = lifecycle.ChunkHoundDaemonLease.close

        def close_keeper(lease: Any) -> None:
            events.append("keeper-close")
            real_close(lease)

        def forbidden_helper(**_kwargs: Any) -> None:
            events.append("helper-preflight")
            raise AssertionError("helper ran after failed keeper readiness")

        def forbidden_model(*_args: Any) -> Any:
            events.append("model")
            raise AssertionError("model ran after failed keeper readiness")

        def flow_patch(stack: Any) -> None:
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "_run_session_chunkhound_index_with_rebuild_fallback",
                    side_effect=final_index_receipt_boundary,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "select_git_tracked_source_witness",
                    return_value=lifecycle.ExpectedSearchWitness(
                        relative_path="source.py",
                        literal="readiness_witness",
                    ),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "open",
                    autospec=True,
                    side_effect=lambda lease: lease,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "adjudicate_expected_session",
                    autospec=True,
                    side_effect=fail_readiness,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "close",
                    autospec=True,
                    side_effect=close_keeper,
                )
            )

        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root) / "route"
            CodexToolProofFlowTests()._run_pr_flow_for_tool_proof(
                root=root,
                profile_resolved="normal",
                multipass_enabled=False,
                llm_side_effect=forbidden_model,
                helper_preflight_side_effect=forbidden_helper,
                flow_patch=flow_patch,
                expect_error=(
                    r"ChunkHound daemon startup/readiness failed "
                    r"\(stage=expected_session; category=expected_session\)\."
                ),
            )
            session_dir = next((root / "sandboxes").iterdir())
            persisted_meta = (session_dir / "meta.json").read_text(encoding="utf-8")

        self.assertNotIn(
            seeded_secret,
            persisted_meta,
            "native lifecycle diagnostics persisted secret-bearing exception text",
        )
        self.assertEqual(
            json.loads(persisted_meta)["chunkhound_readiness_failure"],
            {"stage": "expected_session", "category": "expected_session"},
        )
        self.assertEqual(
            events,
            [
                "final-index/receipt-ready",
                "keeper-readiness-failed",
                "keeper-close",
            ],
            "terminal readiness must close exactly once without retrying",
        )

    def test_fresh_route_probes_immediately_before_lease_helper_and_model(self) -> None:
        """A22 RED: every daemon/helper/model boundary gets fresh generation proof."""
        from _reviewflow_unittest_grounding_impl import (
            CodexToolProofFlowTests,
            _sectioned_review_markdown,
        )

        proof = CodexToolProofFlowTests()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        generation = lifecycle.DaemonGenerationIdentity(pid=4242, process_started_at=1.0)
        events: list[str] = []
        probe_calls = 0

        def probe(**_kwargs: Any) -> Any:
            nonlocal probe_calls
            probe_calls += 1
            events.append("probe")
            return None if probe_calls == 1 else generation

        def open_keeper(lease: Any) -> Any:
            events.append("open")
            return lease

        def helper(**_kwargs: Any) -> None:
            events.append("helper")

        def model(output_path: Path, work_dir: Path) -> Any:
            events.append("model")
            output_path.write_text(
                _sectioned_review_markdown(business="APPROVE", technical="APPROVE"),
                encoding="utf-8",
            )
            return rf.LlmRunResult(
                resume=None,
                adapter_meta=proof._write_helper_command_events(
                    work_dir=work_dir, commands=["search", "research"]
                ),
            )

        def flow_patch(stack: Any) -> None:
            stack.enter_context(
                mock.patch.object(rf, "observe_native_daemon_generation", side_effect=probe)
            )
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "probe_effective_daemon_log_exclusion",
                    return_value={"ok": True, "excluded": True, "degraded": False},
                    create=True,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "open",
                    autospec=True,
                    side_effect=open_keeper,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "owned_generation",
                    new_callable=mock.PropertyMock,
                    return_value=object(),
                )
            )

        with tempfile.TemporaryDirectory() as raw_root:
            _, calls = proof._run_pr_flow_for_tool_proof(
                root=Path(raw_root) / "generation-boundaries",
                profile_resolved="normal",
                multipass_enabled=False,
                llm_side_effect=model,
                helper_preflight_side_effect=helper,
                flow_patch=flow_patch,
            )

        self.assertEqual(calls, ["review.md"])
        self.assertEqual(events.count("open"), 1)
        self.assertEqual(events.count("helper"), 1)
        self.assertEqual(events.count("model"), 1)
        for boundary in ("open", "helper", "model"):
            position = events.index(boundary)
            self.assertGreater(position, 0, events)
            self.assertEqual(events[position - 1], "probe", events)
        self.assertGreaterEqual(events.count("probe"), 4, events)

    def test_startup_retry_probes_again_before_second_lease_open(self) -> None:
        """A22 RED: a retry gets a second pre-open generation observation."""
        from _reviewflow_unittest_grounding_impl import (
            CodexToolProofFlowTests,
            _sectioned_review_markdown,
        )

        proof = CodexToolProofFlowTests()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        generation = lifecycle.DaemonGenerationIdentity(pid=4292, process_started_at=1.5)
        first_failure = lifecycle.PreNativeSpawnLeaseOpenError("first open failed")
        events: list[str] = []
        probe_count = 0

        def probe(**_kwargs: Any) -> Any:
            nonlocal probe_count
            probe_count += 1
            events.append("probe")
            return None if probe_count <= 2 else generation

        def open_keeper(lease: Any) -> Any:
            events.append("open")
            if events.count("open") == 1:
                raise first_failure
            return lease

        def helper(**_kwargs: Any) -> None:
            events.append("helper")

        def model(output_path: Path, work_dir: Path) -> Any:
            events.append("model")
            output_path.write_text(
                _sectioned_review_markdown(business="APPROVE", technical="APPROVE"),
                encoding="utf-8",
            )
            return rf.LlmRunResult(
                resume=None,
                adapter_meta=proof._write_helper_command_events(
                    work_dir=work_dir, commands=["search", "research"]
                ),
            )

        def flow_patch(stack: Any) -> None:
            stack.enter_context(
                mock.patch.object(rf, "observe_native_daemon_generation", side_effect=probe)
            )
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "probe_effective_daemon_log_exclusion",
                    return_value={"ok": True, "excluded": True, "degraded": False},
                    create=True,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "open",
                    autospec=True,
                    side_effect=open_keeper,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "owned_generation",
                    new_callable=mock.PropertyMock,
                    return_value=object(),
                )
            )

        with tempfile.TemporaryDirectory() as raw_root:
            _, calls = proof._run_pr_flow_for_tool_proof(
                root=Path(raw_root) / "startup-reprobe",
                profile_resolved="normal",
                multipass_enabled=False,
                llm_side_effect=model,
                helper_preflight_side_effect=helper,
                flow_patch=flow_patch,
            )

        self.assertEqual(calls, ["review.md"])
        open_positions = [index for index, event in enumerate(events) if event == "open"]
        self.assertEqual(len(open_positions), 2, events)
        for position in open_positions:
            self.assertGreater(position, 0, events)
            self.assertEqual(events[position - 1], "probe", events)
        self.assertGreaterEqual(events.count("probe"), 2, events)

    def test_startup_retry_rejects_log_created_by_failed_first_open(
        self,
    ) -> None:
        """A22 RED: retry cannot truncate the regular log created by attempt one."""
        from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        first_failure = lifecycle.ExpectedSessionReadinessError("first open failed")
        events: list[str] = []
        created_log: Path | None = None

        def open_keeper(lease: Any) -> Any:
            nonlocal created_log
            events.append("open")
            if events.count("open") > 1:
                raise AssertionError("pre-existing first-attempt log reached a second open")
            parent = Path(lease._repo_path) / ".chunkhound"
            parent.mkdir()
            created_log = parent / "daemon.log"
            created_log.write_bytes(b"first-attempt diagnostics\n")
            raise first_failure

        def forbidden_work(*_args: Any, **_kwargs: Any) -> Any:
            events.append("work")
            raise AssertionError("unsafe retry reached helper/model work")

        def flow_patch(stack: Any) -> None:
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "probe_effective_daemon_log_exclusion",
                    return_value={"ok": True, "excluded": True, "degraded": False},
                    create=True,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "observe_native_daemon_generation",
                    return_value=None,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "open",
                    autospec=True,
                    side_effect=open_keeper,
                )
            )

        with tempfile.TemporaryDirectory() as raw_root:
            CodexToolProofFlowTests()._run_pr_flow_for_tool_proof(
                root=Path(raw_root) / "created-log-retry",
                profile_resolved="normal",
                multipass_enabled=False,
                llm_side_effect=forbidden_work,
                helper_preflight_side_effect=forbidden_work,
                flow_patch=flow_patch,
                expect_error="",
            )
            self.assertIsNotNone(created_log)
            self.assertEqual(created_log.read_bytes(), b"first-attempt diagnostics\n")

        self.assertEqual(events, ["open"])

    def test_route_synthetic_untyped_open_failure_without_log_is_not_retried(
        self,
    ) -> None:
        """Synthetic orchestration gating: log absence cannot retry an untyped fault."""
        from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        open_calls: list[Any] = []

        def fail_open(lease: Any) -> None:
            open_calls.append(lease)
            raise lifecycle.ExpectedSessionReadinessError(
                "post-session bootstrap failed before log publication"
            )

        def forbidden_work(*_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError("generic open failure reached helper/model work")

        def flow_patch(stack: Any) -> None:
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "probe_effective_daemon_log_exclusion",
                    return_value={"ok": True, "excluded": True, "degraded": False},
                    create=True,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    rf, "observe_native_daemon_generation", return_value=None
                )
            )
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "open",
                    autospec=True,
                    side_effect=fail_open,
                )
            )

        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root) / "generic-open-terminal"
            CodexToolProofFlowTests()._run_pr_flow_for_tool_proof(
                root=root,
                profile_resolved="normal",
                multipass_enabled=False,
                llm_side_effect=forbidden_work,
                helper_preflight_side_effect=forbidden_work,
                flow_patch=flow_patch,
                expect_error=(
                    r"ChunkHound daemon startup/readiness failed "
                    r"\(stage=lease_open; category=lease_open\)\."
                ),
            )
        self.assertEqual(len(open_calls), 1)
        self.assertFalse(
            (Path(open_calls[0]._repo_path) / ".chunkhound" / "daemon.log").exists()
        )

    def test_startup_retry_reprobes_and_reused_generation_fails_before_second_open(
        self,
    ) -> None:
        """A22 RED: an attempt cannot reuse a generation left by its predecessor."""
        from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        generation = lifecycle.DaemonGenerationIdentity(pid=4343, process_started_at=2.0)
        first_failure = lifecycle.PreNativeSpawnLeaseOpenError("first startup failed")
        events: list[str] = []
        probes = iter((None, generation))

        def probe(**_kwargs: Any) -> Any:
            events.append("probe")
            return next(probes)

        def open_keeper(lease: Any) -> Any:
            events.append("open")
            if events.count("open") == 1:
                raise first_failure
            raise AssertionError("reused generation reached a second lease open")

        def forbidden_helper(**_kwargs: Any) -> None:
            events.append("helper")
            raise AssertionError("helper ran after reused-generation detection")

        def forbidden_model(*_args: Any) -> Any:
            events.append("model")
            raise AssertionError("model ran after reused-generation detection")

        def flow_patch(stack: Any) -> None:
            stack.enter_context(
                mock.patch.object(rf, "observe_native_daemon_generation", side_effect=probe)
            )
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "probe_effective_daemon_log_exclusion",
                    return_value={"ok": True, "excluded": True, "degraded": False},
                    create=True,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "open",
                    autospec=True,
                    side_effect=open_keeper,
                )
            )

        with tempfile.TemporaryDirectory() as raw_root:
            CodexToolProofFlowTests()._run_pr_flow_for_tool_proof(
                root=Path(raw_root) / "reused-generation",
                profile_resolved="normal",
                multipass_enabled=False,
                llm_side_effect=forbidden_model,
                helper_preflight_side_effect=forbidden_helper,
                flow_patch=flow_patch,
                expect_error="",
            )

        self.assertEqual(events, ["probe", "open", "probe"])

    def test_preexisting_generation_fails_before_first_lease_open(self) -> None:
        """A22 RED: a fresh flow cannot attach to an already-running generation."""
        from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        generation = lifecycle.DaemonGenerationIdentity(pid=4444, process_started_at=3.0)
        events: list[str] = []

        def probe(**_kwargs: Any) -> Any:
            events.append("probe")
            return generation

        def forbidden_open(_lease: Any) -> None:
            events.append("open")
            raise AssertionError("pre-existing generation reached lease.open")

        def forbidden_work(*_args: Any, **_kwargs: Any) -> Any:
            events.append("work")
            raise AssertionError("pre-existing generation reached helper/model work")

        def flow_patch(stack: Any) -> None:
            stack.enter_context(
                mock.patch.object(rf, "observe_native_daemon_generation", side_effect=probe)
            )
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "probe_effective_daemon_log_exclusion",
                    return_value={"ok": True, "excluded": True, "degraded": False},
                    create=True,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "open",
                    autospec=True,
                    side_effect=forbidden_open,
                )
            )

        with tempfile.TemporaryDirectory() as raw_root:
            CodexToolProofFlowTests()._run_pr_flow_for_tool_proof(
                root=Path(raw_root) / "preexisting-generation",
                profile_resolved="normal",
                multipass_enabled=False,
                llm_side_effect=forbidden_work,
                helper_preflight_side_effect=forbidden_work,
                flow_patch=flow_patch,
                expect_error="",
            )

        self.assertEqual(events, ["probe"])

    def test_non_owned_post_open_generation_fails_before_helper_or_model(self) -> None:
        """A22 RED: post-open generation proof must be bound to this lease."""
        from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        generation = lifecycle.DaemonGenerationIdentity(pid=4545, process_started_at=4.0)
        events: list[str] = []
        probes = iter((None, generation))

        def probe(**_kwargs: Any) -> Any:
            events.append("probe")
            return next(probes)

        def open_keeper(lease: Any) -> Any:
            events.append("open")
            return lease

        def forbidden_work(*_args: Any, **_kwargs: Any) -> Any:
            events.append("work")
            raise rf.ReviewflowError(
                "non-owned post-open generation reached helper/model work"
            )

        def flow_patch(stack: Any) -> None:
            stack.enter_context(
                mock.patch.object(rf, "observe_native_daemon_generation", side_effect=probe)
            )
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "probe_effective_daemon_log_exclusion",
                    return_value={"ok": True, "excluded": True, "degraded": False},
                    create=True,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "open",
                    autospec=True,
                    side_effect=open_keeper,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "owned_generation",
                    new_callable=mock.PropertyMock,
                    return_value=None,
                )
            )

        with tempfile.TemporaryDirectory() as raw_root:
            CodexToolProofFlowTests()._run_pr_flow_for_tool_proof(
                root=Path(raw_root) / "non-owned-generation",
                profile_resolved="normal",
                multipass_enabled=False,
                llm_side_effect=forbidden_work,
                helper_preflight_side_effect=forbidden_work,
                flow_patch=flow_patch,
                expect_error="",
            )

        self.assertEqual(events, ["probe", "open", "probe"])

    def test_config_identity_is_rehashed_after_probe_before_startup(
        self,
    ) -> None:
        """A22 RED: post-probe config mutation aborts before lease.open."""
        from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        events: list[str] = []
        rehash_count = 0

        def rehash(**kwargs: Any) -> Any:
            nonlocal rehash_count
            rehash_count += 1
            events.append("rehash")
            return lifecycle.LaunchIdentity(
                resolved_executable=Path(str(kwargs["binary"])).resolve(),
                canonical_root=Path(str(kwargs["repo_path"])).resolve(),
                resolved_config_path=Path(str(kwargs["config_path"])).resolve(),
                config_digest=("a" if rehash_count == 1 else "c") * 64,
                resolved_database_path=Path(str(kwargs["database_path"])).resolve(),
                cwd=Path(str(kwargs["cwd"])).resolve(),
                curated_environment_keys=("PATH", "PYTHONSAFEPATH"),
                environment_equality_digest="b" * 64,
            )

        def probe(**_kwargs: Any) -> dict[str, bool]:
            events.append("probe")
            return {"ok": True, "excluded": True, "degraded": False}

        def forbidden_open(_lease: Any) -> None:
            events.append("open")
            raise AssertionError("post-probe config mutation reached lease.open")

        def forbidden_work(*_args: Any, **_kwargs: Any) -> Any:
            events.append("work")
            raise AssertionError("post-probe config mutation reached helper/model work")

        def flow_patch(stack: Any) -> None:
            stack.enter_context(mock.patch.object(rf, "build_launch_identity", side_effect=rehash))
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "probe_effective_daemon_log_exclusion",
                    side_effect=probe,
                    create=True,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "open",
                    autospec=True,
                    side_effect=forbidden_open,
                )
            )

        with tempfile.TemporaryDirectory() as raw_root:
            CodexToolProofFlowTests()._run_pr_flow_for_tool_proof(
                root=Path(raw_root) / "post-probe-config-rehash",
                profile_resolved="normal",
                multipass_enabled=False,
                llm_side_effect=forbidden_work,
                helper_preflight_side_effect=forbidden_work,
                flow_patch=flow_patch,
                expect_error="",
            )

        self.assertEqual(events, ["rehash", "probe", "rehash"])

    def test_lease_internal_validation_rechecks_identity_and_log_before_spawn(
        self,
    ) -> None:
        """Blocker 2: outer-valid inputs mutated at the lease barrier fail closed."""
        from _reviewflow_unittest_grounding_impl import CodexToolProofFlowTests

        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        original_open = lifecycle.ChunkHoundDaemonLease.open

        for mutation in ("config", "launcher", "source", "explicit-env", "daemon-log"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as raw_root:
                events: list[str] = []
                inside_open = False
                barrier_crossed = False
                created_log: Path | None = None

                def build_identity(**kwargs: Any) -> Any:
                    identity = lifecycle.LaunchIdentity(
                        resolved_executable=Path(str(kwargs["binary"])).resolve(),
                        canonical_root=Path(str(kwargs["repo_path"])).resolve(),
                        resolved_config_path=Path(str(kwargs["config_path"])).resolve(),
                        config_digest="a" * 64,
                        resolved_database_path=Path(
                            str(kwargs["database_path"])
                        ).resolve(),
                        cwd=Path(str(kwargs["cwd"])).resolve(),
                        curated_environment_keys=("PATH", "PYTHONSAFEPATH"),
                        environment_equality_digest="b" * 64,
                    )
                    if not barrier_crossed or mutation == "daemon-log":
                        return identity
                    changed = {
                        "config": {"config_digest": "c" * 64},
                        "launcher": {
                            "resolved_executable": identity.resolved_executable.with_name(
                                "replaced-chunkhound"
                            )
                        },
                        "source": {
                            "canonical_root": identity.canonical_root / "replaced-source"
                        },
                        "explicit-env": {"environment_equality_digest": "d" * 64},
                    }[mutation]
                    return replace(identity, **changed)

                def generation_probe(**kwargs: Any) -> None:
                    nonlocal barrier_crossed, created_log
                    events.append("internal-probe" if inside_open else "outer-probe")
                    if inside_open:
                        barrier_crossed = True
                        if mutation == "daemon-log":
                            parent = Path(str(kwargs["repo_path"])) / ".chunkhound"
                            parent.mkdir(exist_ok=True)
                            created_log = parent / "daemon.log"
                            created_log.write_bytes(b"barrier mutation\n")
                    return None

                def forbidden_spawn(**_kwargs: Any) -> Any:
                    events.append("spawn")
                    raise AssertionError("lease validation mutation reached session construction")

                def open_keeper(lease: Any) -> Any:
                    nonlocal inside_open, barrier_crossed
                    events.append("open")
                    inside_open = True
                    try:
                        return original_open(lease)
                    finally:
                        inside_open = False
                        barrier_crossed = False
                        if created_log is not None:
                            created_log.unlink(missing_ok=True)

                def forbidden_work(*_args: Any, **_kwargs: Any) -> Any:
                    events.append("work")
                    raise AssertionError("lease validation mutation reached helper/model work")

                def flow_patch(stack: Any) -> None:
                    stack.enter_context(
                        mock.patch.object(rf, "build_launch_identity", side_effect=build_identity)
                    )
                    stack.enter_context(
                        mock.patch.object(
                            rf,
                            "observe_native_daemon_generation",
                            side_effect=generation_probe,
                        )
                    )
                    stack.enter_context(
                        mock.patch.object(
                            lifecycle, "JsonRpcSession", side_effect=forbidden_spawn
                        )
                    )
                    stack.enter_context(
                        mock.patch.object(
                            lifecycle.ChunkHoundDaemonLease,
                            "open",
                            autospec=True,
                            side_effect=open_keeper,
                        )
                    )

                CodexToolProofFlowTests()._run_pr_flow_for_tool_proof(
                    root=Path(raw_root) / mutation,
                    profile_resolved="normal",
                    multipass_enabled=False,
                    llm_side_effect=forbidden_work,
                    helper_preflight_side_effect=forbidden_work,
                    flow_patch=flow_patch,
                    expect_error=(
                        r"ChunkHound daemon startup/readiness failed "
                        r"\(stage=lease_open; category=lease_open\)\."
                    ),
                )

                self.assertEqual(events.count("open"), 2, events)
                self.assertEqual(events.count("internal-probe"), 2, events)
                self.assertNotIn("spawn", events)
                self.assertNotIn("work", events)

    def _run_real_readiness_route(
        self,
        *,
        root: Path,
        statuses: tuple[dict[str, object], ...],
        expect_error: str | None = None,
        adjudication_kwargs: dict[str, object] | None = None,
        search_text: str | None = None,
        expect_search_on_error: bool = False,
    ) -> dict[str, object]:
        """Run `_pr_flow_impl` through one real retained lease lifecycle."""
        from _reviewflow_unittest_grounding_impl import (
            CodexToolProofFlowTests,
            _sectioned_review_markdown,
        )

        proof = CodexToolProofFlowTests()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        binary = root.parent / "bin" / f"{root.name}-chunkhound"
        ledger = root.parent / f"{root.name}.jsonl"
        _write_fake_chunkhound(
            binary,
            ledger_path=ledger,
            tools_payload=[{"name": tool} for tool in _REQUIRED_KEEPER_TOOLS],
            daemon_status_sequence=statuses,
            search_text=(
                search_text
                if search_text is not None
                else (
                    "## `source.py` L1 — witness\n\n```text\n"
                    "tool_proof_witness\n```\n\n---\nResults 1–1"
                )
            ),
            create_daemon_log=True,
        )
        generation = lifecycle.DaemonGenerationIdentity(
            pid=4242, process_started_at=1234.5
        )
        open_calls: list[Any] = []
        close_calls: list[Any] = []
        validation_calls: list[Path] = []
        precondition_log_states: list[bool] = []
        dispatches: list[str] = []
        ownership_attestations: list[tuple[Any, int]] = []
        released = False
        adjudicating = False
        captured_lease: Any | None = None
        original_open = lifecycle.ChunkHoundDaemonLease.open
        original_close = lifecycle.ChunkHoundDaemonLease.close
        original_assert_alive = lifecycle.ChunkHoundDaemonLease.assert_alive
        original_adjudicate = lifecycle.ChunkHoundDaemonLease.adjudicate_expected_session
        original_classifier = lifecycle._require_healthy_native_status
        original_precondition = rf.assert_daemon_log_startup_precondition
        real_owned_generation = inspect.getattr_static(
            lifecycle.ChunkHoundDaemonLease, "owned_generation"
        )

        class LeaseBoundOwnedGeneration(mock.PropertyMock):
            def __get__(self, obj: Any, obj_type: Any = None) -> Any:
                if obj is None:
                    return self
                return real_owned_generation.__get__(obj, obj_type)

        def identity_for(**kwargs: object) -> Any:
            return lifecycle.LaunchIdentity(
                resolved_executable=binary.resolve(),
                canonical_root=Path(str(kwargs["repo_path"])).resolve(),
                resolved_config_path=Path(str(kwargs["config_path"])).resolve(),
                config_digest="a" * 64,
                resolved_database_path=Path(str(kwargs["database_path"])).resolve(),
                cwd=Path(str(kwargs["cwd"])).resolve(),
                curated_environment_keys=("PATH", "PYTHONSAFEPATH"),
                environment_equality_digest="b" * 64,
            )

        def final_index_receipt(**kwargs: object) -> Any:
            identity = identity_for(
                repo_path=kwargs["repo_dir"],
                config_path=kwargs["chunkhound_cfg_path"],
                database_path=kwargs["chunkhound_db_path"],
                cwd=kwargs["chunkhound_work_dir"],
            )
            return lifecycle.ExpectedSessionReceiptV1(
                schema_version=1,
                canonical_root=identity.canonical_root,
                reviewed_head="1" * 40,
                resolved_config_path=identity.resolved_config_path,
                config_digest=identity.config_digest,
                resolved_database_path=identity.resolved_database_path,
                total_chunks=1,
                launch_identity_projection=identity,
            )

        def generation_probe(*_args: object, **_kwargs: object) -> Any:
            if released:
                return None
            observed = (
                generation
                if any(row.get("event") == "launch" for row in _read_ledger(ledger))
                else None
            )
            if adjudicating:
                _append_ledger(
                    ledger, "generation-check", matches=observed == generation
                )
            return observed

        def track_precondition(**kwargs: object) -> None:
            repo = Path(str(kwargs["repo_path"]))
            precondition_log_states.append(
                (repo / ".chunkhound" / "daemon.log").exists()
            )
            original_precondition(repo_path=repo)

        def open_real(lease: Any) -> Any:
            nonlocal captured_lease
            captured_lease = lease
            open_calls.append(lease)
            validation = lease._pre_spawn_validation
            self.assertTrue(callable(validation))

            def tracked_validation() -> None:
                validation_calls.append(Path(lease._repo_path))
                assert validation is not None
                validation()

            lease._pre_spawn_validation = tracked_validation
            opened = original_open(lease)
            evidence = lease.owned_generation
            self.assertIsInstance(evidence, lifecycle.ExpectedGenerationEvidence)
            self.assertTrue(evidence._matches(lease._lease_token, generation))
            return opened

        def close_real(lease: Any) -> None:
            nonlocal released
            close_calls.append(lease)
            original_close(lease)
            released = True

        def adjudicate_real(lease: Any, receipt: Any, **kwargs: Any) -> Any:
            nonlocal adjudicating
            adjudicating = True
            try:
                return original_adjudicate(
                    lease,
                    receipt,
                    **{**kwargs, **(adjudication_kwargs or {})},
                )
            finally:
                adjudicating = False

        def attest_ownership(observed: Any, proxy_pid: int) -> None:
            ownership_attestations.append((observed, proxy_pid))

        def classify_status(*args: Any, **kwargs: Any) -> object:
            signal = original_classifier(*args, **kwargs)
            _append_ledger(ledger, "status-classification", signal=signal.name)
            return signal

        def helper(**_kwargs: Any) -> None:
            _append_ledger(ledger, "helper")
            dispatches.append("helper")
            if expect_error is not None:
                raise AssertionError("terminal readiness reached helper work")

        def model(output_path: Path, work_dir: Path) -> Any:
            _append_ledger(ledger, "model")
            dispatches.append("model")
            if expect_error is not None:
                raise AssertionError("terminal readiness reached model work")
            output_path.write_text(
                _sectioned_review_markdown(business="APPROVE", technical="APPROVE"),
                encoding="utf-8",
            )
            return rf.LlmRunResult(
                resume=None,
                adapter_meta=proof._write_helper_command_events(
                    work_dir=work_dir, commands=["search", "research"]
                ),
            )

        def flow_patch(stack: Any) -> None:
            patches = (
                mock.patch.object(
                    rf,
                    "_run_session_chunkhound_index_with_rebuild_fallback",
                    side_effect=final_index_receipt,
                ),
                mock.patch.object(rf, "build_launch_identity", side_effect=identity_for),
                mock.patch.object(
                    rf,
                    "probe_effective_daemon_log_exclusion",
                    return_value={"ok": True, "excluded": True, "degraded": False},
                ),
                mock.patch.object(
                    rf,
                    "observe_native_daemon_generation",
                    side_effect=generation_probe,
                ),
                mock.patch.object(
                    rf,
                    "assert_daemon_log_startup_precondition",
                    side_effect=track_precondition,
                ),
                mock.patch.object(
                    rf,
                    "select_git_tracked_source_witness",
                    return_value=lifecycle.ExpectedSearchWitness(
                        relative_path="source.py", literal="tool_proof_witness"
                    ),
                ),
                mock.patch.object(
                    lifecycle,
                    "attest_native_daemon_generation_ownership",
                    side_effect=attest_ownership,
                ),
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "owned_generation",
                    new=LeaseBoundOwnedGeneration(),
                ),
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "open",
                    autospec=True,
                    side_effect=open_real,
                ),
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "close",
                    autospec=True,
                    side_effect=close_real,
                ),
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "assert_alive",
                    autospec=True,
                    side_effect=original_assert_alive,
                ),
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "adjudicate_expected_session",
                    autospec=True,
                    side_effect=adjudicate_real,
                ),
                mock.patch.object(
                    lifecycle,
                    "_require_healthy_native_status",
                    side_effect=classify_status,
                ),
            )
            for patch in patches:
                stack.enter_context(patch)

        result = proof._run_pr_flow_for_tool_proof(
            root=root,
            profile_resolved="normal",
            multipass_enabled=False,
            llm_side_effect=model,
            helper_preflight_side_effect=helper,
            flow_patch=flow_patch,
            expect_error=expect_error,
        )

        rows = _read_ledger(ledger)
        tools = [
            row.get("tool") for row in rows if row.get("method") == "tools/call"
        ]
        self.assertEqual(len(open_calls), 1)
        self.assertEqual(len(close_calls), 1)
        self.assertEqual(len(validation_calls), 1)
        self.assertTrue(precondition_log_states)
        self.assertNotIn(
            True,
            precondition_log_states,
            "creation-only precondition reran after native startup",
        )
        self.assertEqual(
            len([row for row in rows if row.get("event") == "launch"]), 1
        )
        self.assertEqual(len(ownership_attestations), 1)
        self.assertEqual(ownership_attestations[0][0], generation)
        generation_checks = [
            row for row in rows if row.get("event") == "generation-check"
        ]
        self.assertTrue(generation_checks)
        self.assertTrue(all(row.get("matches") is True for row in generation_checks))
        self.assertIsNotNone(captured_lease)
        assert captured_lease is not None
        self.assertEqual(_state_name(captured_lease.state), "CLOSED")
        self.assertIsNone(captured_lease.owned_generation)
        self.assertIsNone(generation_probe())
        self.assertTrue(
            _wait_until(
                lambda: any(
                    row.get("event") in {"closed", "signal"}
                    for row in _read_ledger(ledger)
                )
            ),
            _read_ledger(ledger),
        )
        if expect_error is None:
            self.assertEqual(dispatches, ["helper", "model"])
            self.assertEqual(result[1], ["review.md"])
            self.assertEqual(tools, ["daemon_status"] * len(statuses) + ["search"])
        else:
            self.assertEqual(dispatches, [])
            if expect_search_on_error:
                self.assertEqual(tools, ["daemon_status"] * len(statuses) + ["search"])
            else:
                self.assertNotIn("search", tools)
        session_dir = next((root / "sandboxes").iterdir())
        persisted_meta = json.loads(
            (session_dir / "meta.json").read_text(encoding="utf-8")
        )
        return {
            "tools": tools,
            "rows": rows,
            "generation": generation,
            "meta": persisted_meta,
        }

    def test_pr_flow_retains_first_real_lease_while_native_status_becomes_ready(
        self,
    ) -> None:
        """The real route waits on one generation without rerunning startup gates."""
        initializing = {
            "status": "initializing",
            "server_version": "fixture-1",
            "query_ready": False,
            "scan_progress": {"query_ready_at": None},
        }
        ready = {
            "status": "ready",
            "server_version": "fixture-1",
            "query_ready": True,
            "scan_progress": {"query_ready_at": "fixture"},
        }
        with tempfile.TemporaryDirectory() as raw_root:
            self._run_real_readiness_route(
                root=Path(raw_root) / "retained-readiness-route",
                statuses=(initializing, initializing, ready),
            )

    def test_pr_flow_fresh_instance_resync_retains_real_lease_until_ready(
        self,
    ) -> None:
        """TAP-03: fresh Watchman reconciliation stays on the original route."""
        fresh_resync = _fresh_instance_resync_status()
        fresh_resync_query_ready = copy.deepcopy(fresh_resync)
        fresh_resync_query_ready["query_ready"] = True
        scan_progress = fresh_resync_query_ready["scan_progress"]
        assert isinstance(scan_progress, dict)
        scan_progress["query_ready_at"] = "fixture"
        ready = {
            "status": "ready",
            "server_version": "fixture-1",
            "query_ready": True,
            "scan_progress": {"query_ready_at": "fixture"},
        }
        now = 40.0
        sleeps: list[float] = []

        def clock() -> float:
            return now

        def sleep(delay: float) -> None:
            nonlocal now
            sleeps.append(delay)
            if len(sleeps) > 2:
                raise AssertionError("fresh-resync route exceeded its finite retry guard")
            now += delay

        with tempfile.TemporaryDirectory() as raw_root:
            result = self._run_real_readiness_route(
                root=Path(raw_root) / "fresh-resync-readiness-route",
                statuses=(fresh_resync, fresh_resync_query_ready, ready),
                adjudication_kwargs={
                    "readiness_timeout_seconds": 1.0,
                    "readiness_poll_interval_seconds": 0.25,
                    "clock": clock,
                    "sleep": sleep,
                },
            )
        self.assertEqual(
            result["tools"],
            ["daemon_status", "daemon_status", "daemon_status", "search"],
        )
        self.assertEqual(sleeps, [0.25, 0.25])
        rows = result["rows"]
        assert isinstance(rows, list)
        ordered = [
            (
                f"status-response:{row['status']['status']}:"
                f"{row['status']['query_ready']}"
                if row.get("event") == "tool-response"
                and row.get("tool") == "daemon_status"
                else f"status-classification:{row.get('signal')}"
                if row.get("event") == "status-classification"
                else "search"
                if row.get("event") == "request" and row.get("tool") == "search"
                else str(row.get("event"))
            )
            for row in rows
            if (
                row.get("event") in {"status-classification", "helper", "model"}
                or (
                    row.get("event") == "tool-response"
                    and row.get("tool") == "daemon_status"
                )
                or (row.get("event") == "request" and row.get("tool") == "search")
            )
        ]
        self.assertEqual(
            ordered,
            [
                "status-response:degraded:False",
                "status-classification:FRESH_INSTANCE_RESYNC",
                "status-response:degraded:True",
                "status-classification:FRESH_INSTANCE_RESYNC",
                "status-response:ready:True",
                "status-classification:READY",
                "search",
                "helper",
                "model",
            ],
        )
        first_ready = ordered.index("status-classification:READY")
        for event in ("search", "helper", "model"):
            self.assertGreater(ordered.index(event), first_ready)

    def test_readiness_stage_routing_persists_only_fixed_public_diagnostics(
        self,
    ) -> None:
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        raw_detail = "private-native-detail-/secret/repo/token-value"
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            for stage in (
                "launch_validation",
                "generation_attestation",
                "witness_selection",
            ):
                with self.subTest(stage=stage):
                    meta_path = root / f"{stage}.json"
                    progress = rf.SessionProgress(meta_path, quiet=True)
                    with self.assertRaises(rf.ReviewflowError) as caught:
                        rf._raise_chunkhound_readiness_failure(
                            progress=progress,
                            stage=stage,
                            exc=lifecycle.ExpectedSessionReadinessError(raw_detail),
                        )
                    public_text = (
                        "ChunkHound daemon startup/readiness failed "
                        f"(stage={stage}; category={stage}). "
                        "Evidence written to "
                        f"{meta_path.with_name('chunkhound_readiness_failure.json')}"
                    )
                    self.assertEqual(str(caught.exception), public_text)
                    persisted = json.loads(meta_path.read_text(encoding="utf-8"))
                    self.assertEqual(
                        persisted["chunkhound_readiness_failure"],
                        {"stage": stage, "category": stage},
                    )
                    self.assertNotIn(raw_detail, str(caught.exception))
                    self.assertNotIn(raw_detail, json.dumps(persisted))
                    evidence_path = meta_path.with_name(
                        "chunkhound_readiness_failure.json"
                    )
                    self.assertTrue(evidence_path.is_file())
                    evidence_text = evidence_path.read_text(encoding="utf-8")
                    self.assertNotIn(raw_detail, evidence_text)
                    evidence = json.loads(evidence_text)
                    self.assertEqual(
                        evidence["exception"],
                        {
                            "type": "ExpectedSessionReadinessError",
                            "message_chars": len(raw_detail),
                            "message": "<not persisted: not fixed public text>",
                        },
                    )

    def test_pr_flow_witness_no_hit_reports_safe_distinct_category(self) -> None:
        """A real exact-witness no-hit is attributable without leaking payload data."""
        ready = {
            "status": "ready",
            "server_version": "fixture-1",
            "query_ready": True,
            "scan_progress": {"query_ready_at": "fixture"},
        }
        with tempfile.TemporaryDirectory() as raw_root:
            result = self._run_real_readiness_route(
                root=Path(raw_root) / "witness-no-hit-route",
                statuses=(ready,),
                search_text="No results found: /secret/repo/token-value",
                expect_error=(
                    r"ChunkHound daemon startup/readiness failed "
                    r"\(stage=expected_session; category=witness_search\)\."
                ),
                expect_search_on_error=True,
            )

        self.assertEqual(
            result["meta"]["chunkhound_readiness_failure"],
            {"stage": "expected_session", "category": "witness_search"},
        )
        serialized = json.dumps(result["meta"])
        self.assertNotIn("/secret/repo/token-value", serialized)
        self.assertNotIn("No results found", serialized)

    def test_pr_flow_non_fresh_degraded_resync_is_terminal_without_dispatch(
        self,
    ) -> None:
        """TAP-03: a non-benign degraded route closes instead of retrying work."""
        non_benign = _fresh_instance_resync_status()
        scan_progress = non_benign["scan_progress"]
        assert isinstance(scan_progress, dict)
        realtime = scan_progress["realtime"]
        assert isinstance(realtime, dict)
        resync = realtime["resync"]
        assert isinstance(resync, dict)
        details = resync["last_details"]
        assert isinstance(details, dict)
        details["loss_of_sync_reason"] = "recrawl"
        sleeps: list[float] = []

        def reject_sleep(delay: float) -> None:
            sleeps.append(delay)
            raise AssertionError("terminal degraded route retried")

        with tempfile.TemporaryDirectory() as raw_root:
            result = self._run_real_readiness_route(
                root=Path(raw_root) / "recrawl-readiness-route",
                statuses=(non_benign,),
                expect_error=(
                    r"ChunkHound daemon startup/readiness failed "
                    r"\(stage=expected_session; category=native_status\)\."
                ),
                adjudication_kwargs={
                    "readiness_timeout_seconds": 0.5,
                    "readiness_poll_interval_seconds": 0.25,
                    "clock": lambda: 40.0,
                    "sleep": reject_sleep,
                },
            )
        self.assertEqual(result["tools"], ["daemon_status"])
        self.assertEqual(
            result["meta"]["chunkhound_readiness_failure"],
            {"stage": "expected_session", "category": "native_status"},
        )
        self.assertEqual(sleeps, [])


    def test_pr_flow_initializing_timeout_uses_production_cleanup_once(
        self,
    ) -> None:
        """A bounded real adjudication timeout is terminal and leaves no residue."""
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        initializing = {
            "status": "initializing",
            "server_version": "fixture-1",
            "query_ready": False,
            "scan_progress": {"query_ready_at": None},
        }
        now = 70.0
        sleeps: list[float] = []

        def clock() -> float:
            return now

        def sleep(delay: float) -> None:
            nonlocal now
            sleeps.append(delay)
            now += delay

        with tempfile.TemporaryDirectory() as raw_root:
            result = self._run_real_readiness_route(
                root=Path(raw_root) / "timeout-readiness-route",
                statuses=(initializing,),
                expect_error=(
                    r"ChunkHound daemon startup/readiness failed "
                    r"\(stage=expected_session; category=native_status_timeout\)\."
                ),
                adjudication_kwargs={
                    "readiness_timeout_seconds": 0.5,
                    "readiness_poll_interval_seconds": 0.2,
                    "clock": clock,
                    "sleep": sleep,
                },
            )
        self.assertEqual(result["tools"], ["daemon_status"] * 3)
        self.assertEqual(
            result["meta"]["chunkhound_readiness_failure"],
            {"stage": "expected_session", "category": "native_status_timeout"},
        )
        self.assertEqual(sleeps, [0.2, 0.2, 0.1])
        self.assertEqual(now, 70.5)
        self.assertTrue(
            issubclass(
                lifecycle.ExpectedSessionReadinessTimeoutError,
                lifecycle.ExpectedSessionReadinessError,
            )
        )

    def test_keeper_readiness_failure_writes_evidence_file_without_secrets(
        self,
    ) -> None:
        """Terminal native readiness failures persist actionable evidence locally."""
        degraded = {
            "status": "degraded",
            "server_version": "fixture-1",
            "query_ready": False,
            "scan_progress": {
                "backend": "watchman",
                "api_key": "evidence-secret-TOKEN-value",  # pragma: allowlist secret
            },
        }
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root) / "degraded-evidence-route"
            result = self._run_real_readiness_route(
                root=root,
                statuses=(degraded,),
                expect_error=(
                    r"ChunkHound daemon startup/readiness failed "
                    r"\(stage=expected_session; category=native_status\)\. "
                    r"Evidence written to .*chunkhound_readiness_failure\.json"
                ),
            )
            session_dir = next((root / "sandboxes").iterdir())
            evidence_path = session_dir / "chunkhound_readiness_failure.json"
            self.assertTrue(evidence_path.is_file())
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence_text = evidence_path.read_text(encoding="utf-8")

        self.assertEqual(evidence["schema_version"], 2)
        self.assertEqual(evidence["stage"], "expected_session")
        self.assertEqual(evidence["category"], "native_status")
        self.assertEqual(
            evidence["exception"],
            {
                "type": "NativeStatusReadinessError",
                "message": "native ChunkHound daemon is not strictly query-ready",
            },
        )
        self.assertEqual(evidence["causes"], [])
        # Strict allowlist: the evidence FILE persists no raw status payloads
        # (no parsed last_status, no raw status_payload), no daemon server
        # version value, and no sandbox paths.
        self.assertEqual(
            set(evidence),
            {

                "schema_version",
                "raised_at",
                "stage",
                "category",
                "exception",
                "causes",
                "native_status",
                "identity",
                "receipt",
                "environment",
                "expected_status_schema",
            },
        )
        native_status = evidence["native_status"]
        self.assertNotIn("last_status", native_status)
        self.assertNotIn("last_status_payload", native_status)
        poll = native_status["poll"]
        self.assertEqual(poll["polls"], 0)
        self.assertEqual(poll["observations"], [])
        self.assertEqual(poll["timeout_seconds"], 600.0)
        self.assertIsInstance(poll["elapsed_seconds"], float)
        identity = evidence["identity"]
        # Path-bearing fields must not persist; only presence booleans.
        self.assertIs(identity["resolved_executable_found"], True)
        self.assertIs(identity["canonical_root_present"], True)
        self.assertNotIn("resolved_executable", identity)
        self.assertNotIn("canonical_root", identity)
        self.assertNotIn("cwd", identity)
        self.assertEqual(
            set(evidence["receipt"]),
            {"schema_version", "config_digest", "total_chunks"},
        )
        self.assertIsInstance(evidence["receipt"]["config_digest"], str)
        self.assertEqual(
            evidence["expected_status_schema"],
            sorted({"status", "server_version", "query_ready", "scan_progress"}),
        )
        environment = evidence["environment"]
        self.assertIs(environment["chunkhound"]["resolved_executable_found"], True)
        self.assertNotIn("binary", environment["chunkhound"])
        self.assertIn("env_keys", environment)
        self.assertIn("tmp_writable", environment)
        self.assertIn("sandbox_disk_free_bytes", environment)
        self.assertEqual(
            result["meta"]["chunkhound_readiness_failure"],
            {"stage": "expected_session", "category": "native_status"},
        )
        self.assertNotIn("evidence-secret-TOKEN-value", evidence_text)
        self.assertNotIn("evidence-secret-TOKEN-value", json.dumps(result["meta"]))
        # No status payload, no daemon server version value, no absolute
        # sandbox paths anywhere in the evidence file text.
        self.assertNotIn("status_payload", evidence_text)
        self.assertNotIn("fixture-1", evidence_text)
        for needle in (str(root), str(root.parent / "bin" / "chunkhound")):
            self.assertNotIn(needle, evidence_text)

    def _broker_proof_events_file(
        self, events_path: Path, payloads: list[dict[str, object]]
    ) -> None:
        lines = []
        for payload in payloads:
            lines.append(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "command_execution",
                            "command": (
                                "/bin/bash -lc '\"$CURE_CHUNKHOUND_HELPER\" "
                                f"{payload.get('command')} probe'"
                            ),
                            "aggregated_output": json.dumps(
                                payload, sort_keys=True
                            ),
                        },
                    },
                    sort_keys=True,
                )
            )
        events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _broker_search_payload(
        self, *, record_id: str, query: str
    ) -> dict[str, object]:
        return {
            "broker_record_id": record_id,
            "helper_path": "/work/bin/cure-chunkhound",
            "chunkhound_path": "/usr/local/bin/chunkhound",
            "command": "search",
            "tool_name": "search",
            "ok": True,
            "query": query,
            "path": None,
            "result": {
                "results": [{"path": "src/fixture.py", "snippet": query}],
                "pagination": {"offset": 0, "page_size": 10, "total_results": 1},
            },
            "execution_stage": "tools/call",
            "execution_stage_status": "ok",
        }

    def _broker_payload_digest(self, payload: dict[str, object]) -> str:
        bound = dict(payload)
        bound.pop("broker_record_id", None)
        bound.pop("helper_path", None)
        return hashlib.sha256(
            json.dumps(bound, sort_keys=True, default=str).encode()
        ).hexdigest()

    def test_broker_proof_falls_back_to_whole_file_when_slice_misses_payload(
        self,
    ) -> None:
        """Parallel workers share one events log; a step slice can miss its own
        helper payload. A strict whole-file scan must still prove the record."""
        own_id = "owner-1111" + "0" * 44
        foreign_id = "owner-2222" + "0" * 44
        own = self._broker_search_payload(record_id=own_id, query="own")
        foreign = self._broker_search_payload(record_id=foreign_id, query="foreign")
        own_digest = self._broker_payload_digest(own)
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            work_dir = root / "work"
            work_dir.mkdir()
            events_path = root / "codex.events.jsonl"
            self._broker_proof_events_file(events_path, [own, foreign])
            own_line_len = len(
                events_path.read_text(encoding="utf-8").splitlines()[0]
            ) + 1
            adapter_meta = {
                "transport": "cli-codex",
                "codex_events_path": str(events_path),
                "codex_events_start_offset": own_line_len,
                "codex_events_end_offset": events_path.stat().st_size,
                "chunkhound_broker_required": True,
                "chunkhound_broker_records": [
                    {
                        "record_id": own_id,
                        "operation": "search",
                        "result_digest": own_digest,
                    }
                ],
            }
            report = rf._enforce_chunkhound_tool_proof(
                meta={},
                work_dir=work_dir,
                provider="codex",
                review_stage="multipass_step",
                prompt_template_name="mrereview_gh_local_big_step.md",
                adapter_meta=adapter_meta,
            )
        self.assertIsNotNone(report)
        assert report is not None
        self.assertTrue(report["valid"])
        self.assertIsNone(report["failure_reason"])
        self.assertIn("search", report["observed_successful_calls"])

    def test_broker_proof_per_run_events_file_rejects_post_end_events(
        self,
    ) -> None:
        """Per-run events files (codex.events.<32-hex>.jsonl) are sealed: a
        matching payload beyond the run-end offset must NOT be accepted via
        the whole-file fallback (which only rescues legacy shared files)."""
        own_id = "owner-1111" + "0" * 44
        foreign_id = "owner-2222" + "0" * 44
        own = self._broker_search_payload(record_id=own_id, query="own")
        foreign = self._broker_search_payload(record_id=foreign_id, query="foreign")
        own_digest = self._broker_payload_digest(own)
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            work_dir = root / "work"
            work_dir.mkdir()
            events_path = root / f"codex.events.{'a' * 32}.jsonl"
            self._broker_proof_events_file(events_path, [foreign, own])
            foreign_line_len = len(
                events_path.read_text(encoding="utf-8").splitlines()[0]
            ) + 1
            adapter_meta = {
                "transport": "cli-codex",
                "codex_events_path": str(events_path),
                "codex_events_start_offset": 0,
                "codex_events_end_offset": foreign_line_len,
                "chunkhound_broker_required": True,
                "chunkhound_broker_records": [
                    {
                        "record_id": own_id,
                        "operation": "search",
                        "result_digest": own_digest,
                    }
                ],
            }
            with self.assertRaises(rf.ReviewflowError) as caught:
                rf._enforce_chunkhound_tool_proof(
                    meta={},
                    work_dir=work_dir,
                    provider="codex",
                    review_stage="multipass_step",
                    prompt_template_name="mrereview_gh_local_big_step.md",
                    adapter_meta=adapter_meta,
                )
            diagnostics_path = work_dir / "chunkhound_proof_failure.json"
            self.assertTrue(diagnostics_path.is_file())
            diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
            self.assertEqual(diagnostics["whole_file_payloads"], [])
        self.assertIn(
            "helper output lacked a matching coordinator broker result record",
            str(caught.exception),
        )

    def test_broker_proof_failure_writes_diagnostics_file(self) -> None:
        """A real no-match abort persists expected records vs observed payloads."""
        own_id = "owner-1111" + "0" * 44
        foreign_id = "owner-2222" + "0" * 44
        own = self._broker_search_payload(record_id=own_id, query="own")
        foreign = self._broker_search_payload(record_id=foreign_id, query="foreign")
        own_digest = self._broker_payload_digest(own)
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            work_dir = root / "work"
            work_dir.mkdir()
            events_path = root / "codex.events.jsonl"
            self._broker_proof_events_file(events_path, [foreign])
            adapter_meta = {
                "transport": "cli-codex",
                "codex_events_path": str(events_path),
                "codex_events_start_offset": 0,
                "codex_events_end_offset": events_path.stat().st_size,
                "chunkhound_broker_required": True,
                "chunkhound_broker_records": [
                    {
                        "record_id": own_id,
                        "operation": "search",
                        "result_digest": own_digest,
                    }
                ],
            }
            with self.assertRaises(rf.ReviewflowError) as caught:
                rf._enforce_chunkhound_tool_proof(
                    meta={},
                    work_dir=work_dir,
                    provider="codex",
                    review_stage="multipass_step",
                    prompt_template_name="mrereview_gh_local_big_step.md",
                    adapter_meta=adapter_meta,
                )
            diagnostics_path = work_dir / "chunkhound_proof_failure.json"
            self.assertTrue(diagnostics_path.is_file())
            diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
            self.assertEqual(
                diagnostics["broker_records"],
                [
                    {
                        "record_id": own_id,
                        "operation": "search",
                        "result_digest": own_digest,
                    }
                ],
            )
            self.assertEqual(diagnostics["slice"]["start_offset"], 0)
            self.assertIn(
                "helper output lacked a matching coordinator broker result record",
                str(caught.exception),
            )
            self.assertIn("Diagnostics written to", str(caught.exception))

    def test_route_synthetic_typed_open_failure_retries_once_before_model_work(
        self,
    ) -> None:
        """Synthetic orchestration gating retries only the explicit typed fault."""
        from _reviewflow_unittest_grounding_impl import (
            CodexToolProofFlowTests,
            _sectioned_review_markdown,
        )

        proof = CodexToolProofFlowTests()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        transient_failure = lifecycle.PreNativeSpawnLeaseOpenError(
            "typed pre-native-spawn failure"
        )
        open_attempts: list[Any] = []
        first_attempt_observation: list[tuple[bool, bool]] = []
        readiness_attempts: list[str] = []

        def open_keeper(lease: Any) -> Any:
            open_attempts.append(lease)
            if len(open_attempts) == 1:
                first_attempt_observation.append(
                    (
                        lease._session is None,
                        not (
                            Path(lease._repo_path) / ".chunkhound" / "daemon.log"
                        ).exists(),
                    )
                )
                raise transient_failure
            return lease

        def adjudicate(_lease: Any, _receipt: Any, **_kwargs: Any) -> object:
            readiness_attempts.append("attempt")
            return object()

        def model(output_path: Path, work_dir: Path) -> Any:
            self.assertEqual(len(open_attempts), 2)
            self.assertEqual(readiness_attempts, ["attempt"])
            output_path.write_text(
                _sectioned_review_markdown(
                    business="APPROVE",
                    technical="APPROVE",
                ),
                encoding="utf-8",
            )
            return rf.LlmRunResult(
                resume=None,
                adapter_meta=proof._write_helper_command_events(
                    work_dir=work_dir,
                    commands=["search", "research"],
                ),
            )

        def flow_patch(stack: Any) -> None:
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "open",
                    autospec=True,
                    side_effect=open_keeper,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "adjudicate_expected_session",
                    autospec=True,
                    side_effect=adjudicate,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    lifecycle.ChunkHoundDaemonLease,
                    "owned_generation",
                    new_callable=mock.PropertyMock,
                    return_value=object(),
                )
            )

        with tempfile.TemporaryDirectory() as raw_root:
            _, calls = proof._run_pr_flow_for_tool_proof(
                root=Path(raw_root) / "startup-retry",
                profile_resolved="normal",
                multipass_enabled=False,
                llm_side_effect=model,
                flow_patch=flow_patch,
            )

        self.assertEqual(len(open_attempts), 2)
        self.assertEqual(first_attempt_observation, [(True, True)])
        self.assertEqual(readiness_attempts, ["attempt"])
        self.assertEqual(calls, ["review.md"])

    @unittest.skipUnless(
        sys.platform.startswith("linux"), "Linux process-group contract"
    )
    def test_registry_owns_only_tagged_groups_and_preserves_untagged_sentinel(
        self,
    ) -> None:
        registry_type, _ = self._registry_api()
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            fixture = root / "owned_fixture.py"
            ledger = root / "ledger.jsonl"
            _write_owned_process_fixture(fixture)
            sentinel = subprocess.Popen(
                [sys.executable, str(fixture), str(ledger), "sentinel"],
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            registry = registry_type()
            try:
                self.assertEqual(_state_name(registry.state), "OPEN")
                provider = registry.spawn(
                    role="review-provider",
                    cmd=[sys.executable, str(fixture), str(ledger), "cooperative"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                helper = registry.spawn(
                    role="chunkhound-helper",
                    cmd=[sys.executable, str(fixture), str(ledger), "cooperative"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                self.assertTrue(
                    _wait_until(
                        lambda: (
                            len(
                                [
                                    row
                                    for row in _read_ledger(ledger)
                                    if row["event"] == "launch"
                                ]
                            )
                            == 3
                        )
                    ),
                    _read_ledger(ledger),
                )
                self.assertEqual(os.getpgid(provider.pid), provider.pid)
                self.assertEqual(os.getpgid(helper.pid), helper.pid)
                with mock.patch.object(
                    run_module.subprocess, "Popen", wraps=subprocess.Popen
                ) as popen:
                    with self.assertRaises((TypeError, ValueError)):
                        registry.spawn(
                            role="indexer",
                            cmd=[
                                sys.executable,
                                str(fixture),
                                str(ledger),
                                "cooperative",
                            ],
                        )
                    popen.assert_not_called()

                registry.terminate_and_drain(
                    term_timeout_seconds=0.2,
                    kill_timeout_seconds=0.2,
                    drain_timeout_seconds=0.2,
                )
                self.assertEqual(_state_name(registry.state), "CLOSED")
                self.assertIsNone(
                    sentinel.poll(), "untagged generic subprocess was signalled"
                )
                self.assertTrue(_process_is_gone(provider.pid))
                self.assertTrue(_process_is_gone(helper.pid))
            finally:
                if sentinel.poll() is None:
                    sentinel.terminate()
                sentinel.communicate(timeout=2.0)

    @unittest.skipUnless(
        sys.platform.startswith("linux"), "Linux process-group contract"
    )
    def test_close_first_rejects_before_popen(self) -> None:
        registry_type, closing_error = self._registry_api()
        defaults = inspect.signature(registry_type.terminate_and_drain).parameters
        self.assertEqual(defaults["term_timeout_seconds"].default, 5.0)
        self.assertEqual(defaults["kill_timeout_seconds"].default, 2.0)
        self.assertEqual(defaults["drain_timeout_seconds"].default, 2.0)
        registry = registry_type()
        registry.terminate_and_drain(
            term_timeout_seconds=0.05,
            kill_timeout_seconds=0.05,
            drain_timeout_seconds=0.05,
        )
        self.assertEqual(_state_name(registry.state), "CLOSED")
        with mock.patch.object(
            run_module.subprocess, "Popen", wraps=subprocess.Popen
        ) as popen:
            with self.assertRaises(closing_error):
                registry.spawn(
                    role="review-provider", cmd=[sys.executable, "-c", "pass"]
                )
            popen.assert_not_called()

    @unittest.skipUnless(
        sys.platform.startswith("linux"), "Linux process-group contract"
    )
    def test_spawn_first_is_in_snapshot_and_concurrent_close_is_idempotent(
        self,
    ) -> None:
        registry_type, _ = self._registry_api()
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            fixture = root / "owned_fixture.py"
            ledger = root / "ledger.jsonl"
            _write_owned_process_fixture(fixture)
            registry = registry_type()
            popen_entered = threading.Event()
            allow_popen_return = threading.Event()
            real_popen = subprocess.Popen
            spawned: list[Any] = []
            failures: list[BaseException] = []

            def blocked_popen(*args: Any, **kwargs: Any) -> Any:
                proc = real_popen(*args, **kwargs)
                spawned.append(proc)
                popen_entered.set()
                if not allow_popen_return.wait(2.0):
                    proc.kill()
                    raise AssertionError("test barrier timed out")
                return proc

            def spawn() -> None:
                try:
                    registry.spawn(
                        role="review-provider",
                        cmd=[sys.executable, str(fixture), str(ledger), "cooperative"],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                except BaseException as exc:
                    failures.append(exc)

            def close() -> None:
                try:
                    registry.terminate_and_drain(
                        term_timeout_seconds=0.2,
                        kill_timeout_seconds=0.2,
                        drain_timeout_seconds=0.2,
                    )
                except BaseException as exc:
                    failures.append(exc)

            with mock.patch.object(
                run_module.subprocess, "Popen", side_effect=blocked_popen
            ):
                spawn_thread = threading.Thread(target=spawn)
                spawn_thread.start()
                self.assertTrue(
                    popen_entered.wait(2.0), "spawn never reached Popen barrier"
                )
                self.assertTrue(
                    _wait_until(
                        lambda: any(
                            row["event"] == "launch" for row in _read_ledger(ledger)
                        )
                    ),
                    "spawned fixture never reached its signal-ready launch barrier",
                )
                first_close = threading.Thread(target=close)
                second_close = threading.Thread(target=close)
                first_close.start()
                second_close.start()
                time.sleep(0.05)
                self.assertEqual(_state_name(registry.state), "OPEN")
                self.assertTrue(first_close.is_alive() or second_close.is_alive())
                allow_popen_return.set()
                spawn_thread.join(2.0)
                first_close.join(2.0)
                second_close.join(2.0)

            self.assertFalse(spawn_thread.is_alive())
            self.assertFalse(first_close.is_alive())
            self.assertFalse(second_close.is_alive())
            self.assertEqual(failures, [])
            self.assertEqual(_state_name(registry.state), "CLOSED")
            self.assertEqual(len(spawned), 1)
            pid = spawned[0].pid
            self.assertTrue(
                _wait_until(lambda: _process_is_gone(pid)), _read_ledger(ledger)
            )
            terms = [
                row
                for row in _read_ledger(ledger)
                if row["event"] == "term" and int(str(row["pid"])) == pid
            ]
            self.assertEqual(len(terms), 1, _read_ledger(ledger))

    @unittest.skipUnless(
        sys.platform.startswith("linux"), "Linux process-group contract"
    )
    def test_term_then_kill_drains_pipe_holding_descendant_group(self) -> None:
        registry_type, _ = self._registry_api()
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            fixture = root / "owned_fixture.py"
            ledger = root / "ledger.jsonl"
            _write_owned_process_fixture(fixture)
            registry = registry_type()
            parent = registry.spawn(
                role="chunkhound-helper",
                cmd=[sys.executable, str(fixture), str(ledger), "descendant-parent"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertTrue(
                _wait_until(
                    lambda: (
                        len(
                            [
                                row
                                for row in _read_ledger(ledger)
                                if row["event"] == "launch"
                            ]
                        )
                        == 2
                    )
                ),
                _read_ledger(ledger),
            )
            launches = [row for row in _read_ledger(ledger) if row["event"] == "launch"]
            child_pid = next(
                int(str(row["pid"]))
                for row in launches
                if row["mode"] == "descendant-child"
            )
            self.assertEqual(os.getpgid(parent.pid), parent.pid)
            self.assertEqual(os.getpgid(child_pid), parent.pid)

            close_failures: list[BaseException] = []

            def close() -> None:
                try:
                    registry.terminate_and_drain(
                        term_timeout_seconds=0.3,
                        kill_timeout_seconds=0.2,
                        drain_timeout_seconds=0.2,
                    )
                except BaseException as exc:
                    close_failures.append(exc)

            started = time.monotonic()
            close_thread = threading.Thread(target=close)
            close_thread.start()
            self.assertTrue(
                _wait_until(
                    lambda: _state_name(registry.state) == "CLOSING", timeout=0.2
                ),
                _state_name(registry.state),
            )
            close_thread.join(2.0)
            elapsed = time.monotonic() - started

            self.assertFalse(close_thread.is_alive())
            self.assertEqual(close_failures, [])
            self.assertEqual(_state_name(registry.state), "CLOSED")
            self.assertLess(elapsed, 1.5)
            self.assertTrue(_process_is_gone(parent.pid))
            self.assertTrue(_wait_until(lambda: _process_is_gone(child_pid)))
            term_pids = {
                int(str(row["pid"]))
                for row in _read_ledger(ledger)
                if row["event"] == "term"
            }
            self.assertEqual(term_pids, {parent.pid, child_pid}, _read_ledger(ledger))

    @unittest.skipUnless(
        sys.platform.startswith("linux"), "Linux process-group contract"
    )
    def test_keyboard_interrupt_after_popen_before_publication_is_locally_drained(
        self,
    ) -> None:
        registry_type, _ = self._registry_api()
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            fixture = root / "owned_fixture.py"
            ledger = root / "ledger.jsonl"
            _write_owned_process_fixture(fixture)
            registry = registry_type()
            spawn_code = registry_type.spawn.__code__
            interrupted_pid: list[int] = []
            caught: list[BaseException] = []

            def trace(frame: Any, event: str, arg: Any) -> Any:
                if (
                    frame.f_code is spawn_code
                    and event == "line"
                    and not interrupted_pid
                ):
                    for value in frame.f_locals.values():
                        if isinstance(value, subprocess.Popen):
                            interrupted_pid.append(value.pid)
                            raise KeyboardInterrupt("fixture interrupt after Popen")
                return trace

            def interrupted_spawn() -> None:
                sys.settrace(trace)
                try:
                    registry.spawn(
                        role="chunkhound-helper",
                        cmd=[sys.executable, str(fixture), str(ledger), "cooperative"],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                except BaseException as exc:
                    caught.append(exc)
                finally:
                    sys.settrace(None)

            thread = threading.Thread(target=interrupted_spawn)
            thread.start()
            thread.join(3.0)
            self.assertFalse(
                thread.is_alive(), "interrupted spawn failed to drain locally"
            )
            self.assertEqual(len(caught), 1)
            self.assertIsInstance(caught[0], KeyboardInterrupt)
            self.assertEqual(str(caught[0]), "fixture interrupt after Popen")
            self.assertEqual(len(interrupted_pid), 1, _read_ledger(ledger))
            self.assertTrue(
                _wait_until(lambda: _process_is_gone(interrupted_pid[0])),
                _read_ledger(ledger),
            )
            self.assertEqual(_state_name(registry.state), "OPEN")
            registry.terminate_and_drain(
                term_timeout_seconds=0.05,
                kill_timeout_seconds=0.05,
                drain_timeout_seconds=0.05,
            )
            self.assertEqual(_state_name(registry.state), "CLOSED")


class ChunkHoundDaemonLeaseTests(unittest.TestCase):
    def test_lease_retains_one_bootstrapped_mcp_session_and_closes_idempotently(
        self,
    ) -> None:
        try:
            lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        except ModuleNotFoundError as exc:
            self.fail(f"daemon lease production module is required: {exc}")
        lease_type = getattr(lifecycle, "ChunkHoundDaemonLease", None)
        self.assertIsNotNone(
            lease_type, "ChunkHoundDaemonLease production API is required"
        )
        assert lease_type is not None

        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            repo = root / "repo"
            repo.mkdir()
            config = root / "chunkhound.json"
            config.write_text("{}", encoding="utf-8")
            ledger = root / "lease.jsonl"
            binary = root / "bin" / "chunkhound"
            _write_fake_chunkhound(
                binary,
                ledger_path=ledger,
                tools_payload=[{"name": name} for name in _REQUIRED_KEEPER_TOOLS],
            )
            child_env = MappingProxyType(
                {"PATH": str(binary.parent), "PYTHONSAFEPATH": "1"}
            )
            lease = lease_type(
                config_path=config,
                repo_path=repo,
                cwd=repo,
                binary="chunkhound",
                env=child_env,
            )
            self.assertEqual(_state_name(lease.state), "NEW")
            lease.open()
            self.assertEqual(_state_name(lease.state), "HELD")
            lease.assert_alive()

            rows = _read_ledger(ledger)
            launches = [row for row in rows if row["event"] == "launch"]
            self.assertEqual(len(launches), 1, rows)
            self.assertEqual(
                [row.get("method") for row in rows if row["event"] == "request"][:3],
                ["initialize", "notifications/initialized", "tools/list"],
            )
            pid = int(str(launches[0]["pid"]))
            os.kill(pid, 0)

            lease.close()
            self.assertEqual(_state_name(lease.state), "CLOSED")
            self.assertTrue(
                _wait_until(
                    lambda: any(
                        row["event"] in {"closed", "signal"}
                        for row in _read_ledger(ledger)
                    )
                ),
                _read_ledger(ledger),
            )
            lease.close()
            self.assertEqual(_state_name(lease.state), "CLOSED")
            self.assertEqual(
                len([row for row in _read_ledger(ledger) if row["event"] == "launch"]),
                1,
            )

    def test_open_validates_after_generation_observation_immediately_before_session(
        self,
    ) -> None:
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        events: list[str] = []
        session = mock.Mock(binary="chunkhound")

        def observe_generation() -> None:
            events.append("generation")

        def validate() -> None:
            events.append("validation")

        def construct_session(**_kwargs: Any) -> Any:
            events.append("session")
            return session

        with (
            tempfile.TemporaryDirectory() as raw_root,
            mock.patch.object(
                lifecycle, "JsonRpcSession", side_effect=construct_session
            ),
            mock.patch.object(
                lifecycle,
                "bootstrap_chunkhound_mcp_session",
                return_value={"ok": True},
            ),
        ):
            root = Path(raw_root)
            lease = lifecycle.ChunkHoundDaemonLease(
                config_path=root / "chunkhound.json",
                repo_path=root,
                pre_spawn_validation=validate,
                generation_probe=observe_generation,
            )
            lease.open()
            self.assertEqual(
                events,
                ["generation", "validation", "session", "generation"],
            )
            lease.close()

        events.clear()

        def reject() -> None:
            events.append("validation")
            raise lifecycle.ExpectedSessionReadinessError("stale launch inputs")

        with mock.patch.object(
            lifecycle,
            "JsonRpcSession",
            side_effect=AssertionError("validation failure reached session construction"),
        ) as session_constructor:
            lease = lifecycle.ChunkHoundDaemonLease(
                config_path="chunkhound.json",
                repo_path=".",
                pre_spawn_validation=reject,
                generation_probe=observe_generation,
            )
            with self.assertRaises(lifecycle.PreNativeSpawnLeaseOpenError):
                lease.open()

        self.assertEqual(events, ["generation", "validation"])
        session_constructor.assert_not_called()
        self.assertEqual(_state_name(lease.state), "CLOSED")

    def test_owned_generation_requires_live_proxy_and_parent_attestation(self) -> None:
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        generation = lifecycle.DaemonGenerationIdentity(
            pid=321, process_started_at=98765.0
        )

        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            proc_root = root / "proc"

            def write_stat(*, state: str, parent_pid: int, ticks: int) -> None:
                stat_path = proc_root / "321" / "stat"
                stat_path.parent.mkdir(parents=True, exist_ok=True)
                fields_after_comm = (
                    [state, str(parent_pid)] + ["0"] * 17 + [str(ticks)]
                )
                stat_path.write_text(
                    "321 (daemon with ) and spaces) "
                    + " ".join(fields_after_comm)
                    + "\n",
                    encoding="ascii",
                )

            cases = (
                ("owned", "S", 700, 98765, True),
                ("foreign-parent", "S", 701, 98765, False),
                ("changed-tick", "S", 700, 98766, False),
                ("zombie", "Z", 700, 98765, False),
            )
            for name, state, parent_pid, ticks, succeeds in cases:
                with self.subTest(name=name):
                    write_stat(state=state, parent_pid=parent_pid, ticks=ticks)
                    session = mock.Mock(binary="chunkhound")
                    session.proc.pid = 700
                    session.proc.poll.return_value = None
                    lease = lifecycle.ChunkHoundDaemonLease(
                        config_path=root / "chunkhound.json",
                        repo_path=root,
                        generation_probe=mock.Mock(side_effect=[None, generation]),
                        generation_attestor=lambda observed, proxy_pid: (
                            lifecycle.attest_native_daemon_generation_ownership(
                                generation=observed,
                                expected_parent_pid=proxy_pid,
                                proc_root=proc_root,
                            )
                        ),
                    )
                    with (
                        mock.patch.object(
                            lifecycle, "JsonRpcSession", return_value=session
                        ),
                        mock.patch.object(
                            lifecycle,
                            "bootstrap_chunkhound_mcp_session",
                            return_value={"ok": True},
                        ),
                    ):
                        if succeeds:
                            lease.open()
                            self.assertIsNotNone(lease.owned_generation)
                            self.assertEqual(_state_name(lease.state), "HELD")
                            lease.close()
                        else:
                            with self.assertRaises(
                                lifecycle.ExpectedSessionReadinessError
                            ):
                                lease.open()
                            self.assertIsNone(lease.owned_generation)
                            self.assertEqual(_state_name(lease.state), "CLOSED")
                    session.close.assert_called_once()

            (proc_root / "321" / "stat").unlink()
            session = mock.Mock(binary="chunkhound")
            session.proc.pid = 700
            session.proc.poll.return_value = None
            lease = lifecycle.ChunkHoundDaemonLease(
                config_path=root / "chunkhound.json",
                repo_path=root,
                generation_probe=mock.Mock(side_effect=[None, generation]),
                generation_attestor=lambda observed, proxy_pid: (
                    lifecycle.attest_native_daemon_generation_ownership(
                        generation=observed,
                        expected_parent_pid=proxy_pid,
                        proc_root=proc_root,
                    )
                ),
            )
            with (
                mock.patch.object(lifecycle, "JsonRpcSession", return_value=session),
                mock.patch.object(
                    lifecycle,
                    "bootstrap_chunkhound_mcp_session",
                    return_value={"ok": True},
                ),
                self.assertRaises(lifecycle.ExpectedSessionReadinessError),
            ):
                lease.open()
            session.close.assert_called_once()
            self.assertEqual(_state_name(lease.state), "CLOSED")

    def test_dead_proxy_cannot_issue_owned_generation(self) -> None:
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        generation = lifecycle.DaemonGenerationIdentity(
            pid=321, process_started_at=98765.0
        )
        session = mock.Mock(binary="chunkhound")
        session.proc.pid = 700
        session.proc.poll.return_value = 9
        attestor = mock.Mock()
        lease = lifecycle.ChunkHoundDaemonLease(
            config_path="chunkhound.json",
            repo_path=".",
            generation_probe=mock.Mock(side_effect=[None, generation]),
            generation_attestor=attestor,
        )
        with (
            mock.patch.object(lifecycle, "JsonRpcSession", return_value=session),
            mock.patch.object(
                lifecycle,
                "bootstrap_chunkhound_mcp_session",
                return_value={"ok": True},
            ),
            self.assertRaises(lifecycle.ExpectedSessionReadinessError),
        ):
            lease.open()
        attestor.assert_not_called()
        session.close.assert_called_once()
        self.assertIsNone(lease.owned_generation)
        self.assertEqual(_state_name(lease.state), "CLOSED")



    def test_open_rejects_preexisting_generation_before_it_can_mint_evidence(
        self,
    ) -> None:
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        generation = lifecycle.DaemonGenerationIdentity(
            pid=321, process_started_at=98765.0
        )
        session = mock.Mock(binary="chunkhound")
        session.proc.pid = 700
        session.proc.poll.return_value = None
        attestor = mock.Mock()
        lease = lifecycle.ChunkHoundDaemonLease(
            config_path="chunkhound.json",
            repo_path=".",
            generation_probe=mock.Mock(return_value=generation),
            generation_attestor=attestor,
        )

        self.addCleanup(lease.close)
        caught: BaseException | None = None
        with (
            mock.patch.object(
                lifecycle, "JsonRpcSession", return_value=session
            ) as session_constructor,
            mock.patch.object(
                lifecycle,
                "bootstrap_chunkhound_mcp_session",
                return_value={"ok": True},
            ),
        ):
            try:
                lease.open()
            except (
                lifecycle.PreNativeSpawnLeaseOpenError,
                lifecycle.ExpectedSessionReadinessError,
            ) as exc:
                caught = exc

        self.assertEqual(_state_name(lease.state), "CLOSED")
        self.assertIsNone(lease.owned_generation)
        attestor.assert_not_called()
        if session_constructor.called:
            session_constructor.assert_called_once()
            session.close.assert_called_once()
        else:
            session.close.assert_not_called()
        self.assertIsNotNone(caught)

    def test_wait_for_daemon_release_requires_close_before_verification(
        self,
    ) -> None:
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        lease = lifecycle.ChunkHoundDaemonLease(
            config_path="chunkhound.json",
            repo_path=".",
            generation_probe=lambda: None,
        )
        with self.assertRaises(RuntimeError):
            lease.wait_for_daemon_release(timeout_seconds=1.0)

    def test_wait_for_daemon_release_requires_a_generation_probe(self) -> None:
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        lease = lifecycle.ChunkHoundDaemonLease(
            config_path="chunkhound.json",
            repo_path=".",
        )
        lease.close()
        with self.assertRaises(RuntimeError):
            lease.wait_for_daemon_release(timeout_seconds=1.0)

    def test_wait_for_daemon_release_polls_until_generation_is_absent(
        self,
    ) -> None:
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        identity = lifecycle.DaemonGenerationIdentity(
            pid=123, process_started_at=98765.0
        )
        calls: list[int] = []

        def probe() -> lifecycle.DaemonGenerationIdentity | None:
            calls.append(len(calls))
            return identity if len(calls) < 3 else None

        lease = lifecycle.ChunkHoundDaemonLease(
            config_path="chunkhound.json",
            repo_path=".",
            generation_probe=probe,
        )
        lease.close()
        clock_state = {"now": 0.0}
        slept: list[float] = []

        def clock() -> float:
            return clock_state["now"]

        def fake_sleep(seconds: float) -> None:
            slept.append(seconds)
            clock_state["now"] += seconds

        self.assertTrue(
            lease.wait_for_daemon_release(
                timeout_seconds=5.0,
                poll_interval_seconds=0.25,
                clock=clock,
                sleep=fake_sleep,
            )
        )
        self.assertEqual(calls, [0, 1, 2])
        self.assertEqual(len(slept), 2)

    def test_wait_for_daemon_release_times_out_when_daemon_never_releases(
        self,
    ) -> None:
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        identity = lifecycle.DaemonGenerationIdentity(
            pid=123, process_started_at=98765.0
        )
        lease = lifecycle.ChunkHoundDaemonLease(
            config_path="chunkhound.json",
            repo_path=".",
            generation_probe=lambda: identity,
        )
        lease.close()
        clock_state = {"now": 0.0}

        def clock() -> float:
            return clock_state["now"]

        def fake_sleep(seconds: float) -> None:
            clock_state["now"] += seconds

        self.assertFalse(
            lease.wait_for_daemon_release(
                timeout_seconds=1.0,
                poll_interval_seconds=0.25,
                clock=clock,
                sleep=fake_sleep,
            )
        )
        self.assertEqual(clock_state["now"], 1.0)

    def test_wait_for_daemon_generation_absence_treats_probe_errors_as_unreleased(
        self,
    ) -> None:
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        attempts = {"n": 0}

        def probe() -> lifecycle.DaemonGenerationIdentity | None:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise lifecycle.ExpectedSessionReadinessError(
                    "transient probe failure"
                )
            return None

        clock_state = {"now": 0.0}

        def clock() -> float:
            return clock_state["now"]

        def fake_sleep(seconds: float) -> None:
            clock_state["now"] += seconds

        self.assertTrue(
            lifecycle.wait_for_daemon_generation_absence(
                probe,
                timeout_seconds=5.0,
                poll_interval_seconds=0.25,
                clock=clock,
                sleep=fake_sleep,
            )
        )
        self.assertEqual(attempts["n"], 3)

        with self.assertRaises(ValueError):
            lifecycle.wait_for_daemon_generation_absence(
                probe,
                timeout_seconds=0.0,
                poll_interval_seconds=0.25,
                clock=clock,
                sleep=fake_sleep,
            )

class ExpectedSessionReadinessTests(unittest.TestCase):
    """Native status and expected-index adjudication contract."""

    def _api(self) -> tuple[Any, Any, Any, Any, Any, Any, Any, Any]:
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        names = (
            "LaunchIdentity",
            "ExpectedSessionReceiptV1",
            "ChunkHoundDaemonLease",
            "ExpectedSearchWitness",
            "DaemonGenerationIdentity",
            "ExpectedGenerationEvidence",
            "ExpectedSessionReadiness",
            "ExpectedSessionReadinessError",
        )
        values = tuple(getattr(lifecycle, name, None) for name in names)
        for name, value in zip(names, values, strict=True):
            self.assertIsNotNone(value, f"cure_chunkhound_lifecycle.{name} is required")
        return values  # type: ignore[return-value]

    def _identity(self, identity_type: Any, root: Path, binary: Path) -> Any:
        repo = root / "repo"
        config = root / "chunkhound.json"
        database = root / "chunkhound.db"
        return identity_type(
            resolved_executable=binary.resolve(),
            canonical_root=repo.resolve(),
            resolved_config_path=config.resolve(),
            config_digest="config-digest",
            resolved_database_path=database.resolve(),
            cwd=repo.resolve(),
            curated_environment_keys=("PATH", "PYTHONSAFEPATH"),
            environment_equality_digest="environment-digest",
        )

    def _receipt(self, receipt_type: Any, identity: Any, *, total_chunks: int) -> Any:
        return receipt_type(
            schema_version=1,
            canonical_root=identity.canonical_root,
            reviewed_head="a" * 40,
            resolved_config_path=identity.resolved_config_path,
            config_digest=identity.config_digest,
            resolved_database_path=identity.resolved_database_path,
            total_chunks=total_chunks,
            launch_identity_projection=identity,
        )

    def _open_lease(
        self,
        root: Path,
        lease_type: Any,
        identity_type: Any,
        *,
        name: str,
        daemon_status: object | None = None,
        daemon_status_sequence: tuple[object, ...] | None = None,
        search_text: str = "## `src/fixture.py` L1–L2 — witness\n\n````python\nneedle[1]\n```\n````\n\n---\nPage 1 of 1 (results 1–1 of 1)",
        tool_overrides: dict[str, object] | None = None,
        generation_probe: Any | None = None,
        daemon_status_no_response: bool = False,
    ) -> tuple[Any, Any, Path]:
        repo = root / "repo"
        repo.mkdir(exist_ok=True)
        config = root / "chunkhound.json"
        config.write_text("{}", encoding="utf-8")
        ledger = root / f"{name}.jsonl"
        binary = root / name / "chunkhound"
        _write_fake_chunkhound(
            binary,
            ledger_path=ledger,
            tools_payload=[{"name": tool} for tool in _REQUIRED_KEEPER_TOOLS],
            daemon_status=daemon_status,
            daemon_status_sequence=daemon_status_sequence,
            search_text=search_text,
            tool_overrides=tool_overrides,
            daemon_status_no_response=daemon_status_no_response,
        )
        identity = self._identity(identity_type, root, binary)
        generation_type = getattr(
            importlib.import_module("cure_chunkhound_lifecycle"),
            "DaemonGenerationIdentity",
        )
        fixed_generation = generation_type(pid=4242, process_started_at=1234.5)
        if generation_probe is None:

            def default_generation_probe() -> object | None:
                return (
                    fixed_generation
                    if any(row.get("event") == "launch" for row in _read_ledger(ledger))
                    else None
                )

            generation_probe = default_generation_probe
        lease = lease_type(
            config_path=config,
            repo_path=repo,
            cwd=repo,
            binary=str(binary),
            env=MappingProxyType({"PATH": str(binary.parent), "PYTHONSAFEPATH": "1"}),
            launch_identity=identity,
            generation_probe=generation_probe,
            generation_attestor=lambda _generation, _proxy_pid: None,
        )
        lease.open()
        self.assertEqual(
            lease.launch_identity, identity, "lease exposes its exact LaunchIdentity"
        )
        return lease, identity, ledger

    def test_exact_identity_and_native_markdown_witness_use_public_lease_api(
        self,
    ) -> None:
        (
            identity_type,
            receipt_type,
            lease_type,
            witness_type,
            daemon_generation_type,
            evidence_type,
            readiness_type,
            readiness_error,
        ) = self._api()
        self.assertEqual(
            tuple(field.name for field in fields(witness_type)),
            ("relative_path", "literal"),
        )
        self.assertEqual(
            tuple(field.name for field in fields(daemon_generation_type)),
            ("pid", "process_started_at"),
        )
        generation = daemon_generation_type(pid=4242, process_started_at=1234.5)
        with self.assertRaises(FrozenInstanceError):
            generation.pid = 7
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            lease, identity, ledger = self._open_lease(
                root, lease_type, identity_type, name="valid"
            )
            try:
                witness = witness_type(
                    relative_path="src/fixture.py", literal="needle[1]"
                )
                receipt = self._receipt(receipt_type, identity, total_chunks=2)
                readiness = lease.adjudicate_expected_session(receipt, witness=witness)
                self.assertIsInstance(readiness, readiness_type)
                self.assertEqual(readiness.launch_identity, identity)
                self.assertEqual(readiness.search_witness, witness)
                self.assertIsInstance(readiness.expected_generation, evidence_type)
                with self.assertRaises(FrozenInstanceError):
                    readiness.search_witness = None

                calls = [
                    row
                    for row in _read_ledger(ledger)
                    if row.get("method") == "tools/call"
                ]
                self.assertEqual(calls[0].get("tool"), "daemon_status")
                self.assertEqual(calls[0].get("arguments"), {})
                self.assertEqual(calls[1].get("tool"), "search")
                self.assertEqual(
                    calls[1].get("arguments"),
                    {
                        "type": "regex",
                        "query": re.escape("needle[1]"),
                        "path": "src/fixture.py",
                    },
                )

                mismatched = replace(
                    receipt,
                    launch_identity_projection=replace(
                        identity, config_digest="foreign-config"
                    ),
                )
                with self.assertRaises(readiness_error):
                    lease.adjudicate_expected_session(mismatched, witness=witness)
            finally:
                lease.close()

    def test_pre_native_spawn_open_failure_is_typed_without_launch_or_log(self) -> None:
        """Only generation/pre-validation failures expose the retryable open type."""
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        identity_type, _, lease_type, *_ = self._api()
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            repo = root / "repo"
            repo.mkdir()
            config = root / "chunkhound.json"
            config.write_text("{}", encoding="utf-8")
            binary = root / "bin" / "chunkhound"
            binary.parent.mkdir()
            binary.write_text("unused", encoding="utf-8")
            identity = self._identity(identity_type, root, binary)
            validation_calls: list[str] = []

            def fail_validation() -> None:
                validation_calls.append("validation")
                raise OSError("pre-spawn validation unavailable")

            lease = lease_type(
                config_path=config,
                repo_path=repo,
                cwd=repo,
                binary=str(binary),
                env=MappingProxyType({"PATH": str(binary.parent)}),
                launch_identity=identity,
                generation_probe=lambda: None,
                pre_spawn_validation=fail_validation,
            )
            with mock.patch.object(lifecycle, "JsonRpcSession") as session_type:
                with self.assertRaises(lifecycle.PreNativeSpawnLeaseOpenError):
                    lease.open()
            session_type.assert_not_called()
            self.assertEqual(validation_calls, ["validation"])
            self.assertFalse((repo / ".chunkhound" / "daemon.log").exists())
            self.assertEqual(_state_name(lease.state), "CLOSED")
            self.assertIsNone(lease.owned_generation)

    def test_post_session_attestation_failure_is_generic_and_closes_session(
        self,
    ) -> None:
        """A real bootstrapped session fault is terminal, untyped, and cleaned up."""
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        identity_type, _, lease_type, *_ = self._api()
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            repo = root / "repo"
            repo.mkdir()
            config = root / "chunkhound.json"
            config.write_text("{}", encoding="utf-8")
            ledger = root / "post-session-attestation.jsonl"
            binary = root / "bin" / "chunkhound"
            _write_fake_chunkhound(
                binary,
                ledger_path=ledger,
                tools_payload=[{"name": tool} for tool in _REQUIRED_KEEPER_TOOLS],
            )
            identity = self._identity(identity_type, root, binary)
            generation = lifecycle.DaemonGenerationIdentity(
                pid=4242, process_started_at=1234.5
            )

            def generation_probe() -> object | None:
                return (
                    generation
                    if any(
                        row.get("event") == "launch" for row in _read_ledger(ledger)
                    )
                    else None
                )

            def fail_attestation(_generation: Any, _proxy_pid: int) -> None:
                raise OSError("ownership attestation unavailable")

            lease = lease_type(
                config_path=config,
                repo_path=repo,
                cwd=repo,
                binary=str(binary),
                env=MappingProxyType({"PATH": str(binary.parent)}),
                launch_identity=identity,
                generation_probe=generation_probe,
                generation_attestor=fail_attestation,
            )
            with self.assertRaises(lifecycle.ExpectedSessionReadinessError) as caught:
                lease.open()
            self.assertNotIsInstance(
                caught.exception, lifecycle.PreNativeSpawnLeaseOpenError
            )
            self.assertEqual(
                len(
                    [
                        row
                        for row in _read_ledger(ledger)
                        if row.get("event") == "launch"
                    ]
                ),
                1,
            )
            self.assertTrue(
                _wait_until(
                    lambda: any(
                        row.get("event") in {"closed", "signal"}
                        for row in _read_ledger(ledger)
                    )
                ),
                _read_ledger(ledger),
            )
            self.assertEqual(_state_name(lease.state), "CLOSED")
            self.assertIsNone(lease.owned_generation)

    def test_ready_status_accepts_backend_specific_scan_progress_shape(self) -> None:
        """Top-level installed status is authoritative over opaque backend details."""
        identity_type, receipt_type, lease_type, witness_type, *_ = self._api()
        backend_specific = {
            "status": "ready",
            "server_version": "fixture-1",
            "query_ready": True,
            "scan_progress": {
                "service_state": "backend-specific-value",
                "nested": [None, {"future_field": "opaque"}],
            },
        }
        with tempfile.TemporaryDirectory() as raw_root:
            lease, identity, _ = self._open_lease(
                Path(raw_root),
                lease_type,
                identity_type,
                name="opaque-scan-progress",
                daemon_status=backend_specific,
            )
            try:
                readiness = lease.adjudicate_expected_session(
                    self._receipt(receipt_type, identity, total_chunks=1),
                    witness=witness_type(
                        relative_path="src/fixture.py", literal="needle[1]"
                    ),
                )
                self.assertIsNotNone(readiness)
            finally:
                lease.close()

    def test_initializing_then_ready_waits_on_one_held_lease_and_generation(
        self,
    ) -> None:
        """Exact initializing/false waits without closing or searching."""
        (
            identity_type,
            receipt_type,
            lease_type,
            witness_type,
            daemon_generation_type,
            _,
            readiness_type,
            _,
        ) = self._api()
        initializing = {
            "status": "initializing",
            "server_version": "fixture-1",
            "query_ready": False,
            "scan_progress": {"query_ready_at": None},
        }
        ready = {
            "status": "ready",
            "server_version": "fixture-1",
            "query_ready": True,
            "scan_progress": {"query_ready_at": "fixture"},
        }
        now = 10.0
        sleeps: list[float] = []

        def clock() -> float:
            return now

        def sleep(delay: float) -> None:
            nonlocal now
            self.assertGreater(delay, 0.0)
            sleeps.append(delay)
            now += delay

        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            ledger = root / "initializing-ready.jsonl"
            generation = daemon_generation_type(pid=4242, process_started_at=1234.5)
            generation_observations: list[object | None] = []
            track_readiness = False

            def generation_probe() -> object | None:
                observed = (
                    generation
                    if any(row.get("event") == "launch" for row in _read_ledger(ledger))
                    else None
                )
                generation_observations.append(observed)
                if track_readiness:
                    _append_ledger(ledger, "generation", matches=observed == generation)
                return observed

            lease, identity, ledger = self._open_lease(
                root,
                lease_type,
                identity_type,
                name="initializing-ready",
                daemon_status_sequence=(initializing, initializing, ready),
                generation_probe=generation_probe,
            )
            track_readiness = True
            receipt = self._receipt(receipt_type, identity, total_chunks=1)
            witness = witness_type(relative_path="src/fixture.py", literal="needle[1]")

            def record_alive() -> None:
                _append_ledger(ledger, "liveness")
                lease_type.assert_alive(lease)

            try:
                with mock.patch.object(
                    lease, "assert_alive", side_effect=record_alive
                ) as assert_alive:
                    readiness = lease.adjudicate_expected_session(
                        receipt,
                        witness=witness,
                        readiness_timeout_seconds=1.0,
                        readiness_poll_interval_seconds=0.25,
                        clock=clock,
                        sleep=sleep,
                    )
                self.assertIsInstance(readiness, readiness_type)
                self.assertEqual(assert_alive.call_count, 3)
                self.assertEqual(sleeps, [0.25, 0.25])
                rows = _read_ledger(ledger)
                tools = [
                    row.get("tool") for row in rows if row.get("method") == "tools/call"
                ]
                self.assertEqual(
                    tools,
                    ["daemon_status", "daemon_status", "daemon_status", "search"],
                )
                self.assertEqual(
                    [
                        row.get("status")
                        for row in rows
                        if row.get("event") == "tool-response"
                    ],
                    [initializing, initializing, ready],
                )
                continuity = [
                    row.get("event")
                    for row in rows
                    if row.get("event") in {"liveness", "generation", "tool-response"}
                ]
                self.assertEqual(
                    continuity[:9],
                    [
                        "liveness",
                        "generation",
                        "tool-response",
                        "liveness",
                        "generation",
                        "tool-response",
                        "liveness",
                        "generation",
                        "tool-response",
                    ],
                    continuity,
                )
                self.assertTrue(
                    all(
                        row.get("matches") is True
                        for row in rows
                        if row.get("event") == "generation"
                    )
                )
                self.assertEqual(
                    len([row for row in rows if row.get("event") == "launch"]), 1
                )
                self.assertFalse(
                    any(row.get("event") in {"closed", "signal"} for row in rows),
                    "the held lease must not close/reopen while native readiness advances",
                )
                self.assertEqual(_state_name(lease.state), "HELD")
                self.assertEqual(generation_observations[0], None)
                self.assertGreaterEqual(len(generation_observations), 5)
                self.assertTrue(
                    all(
                        observed == generation
                        for observed in generation_observations[1:]
                    ),
                    generation_observations,
                )
            finally:
                lease.close()
            self.assertTrue(
                _wait_until(
                    lambda: any(
                        row.get("event") in {"closed", "signal"}
                        for row in _read_ledger(ledger)
                    )
                ),
                _read_ledger(ledger),
            )
            self.assertEqual(
                len(
                    [
                        row
                        for row in _read_ledger(ledger)
                        if row.get("event") == "launch"
                    ]
                ),
                1,
            )

    def test_fresh_instance_resync_then_ready_uses_typed_retained_polling(
        self,
    ) -> None:
        """TAP-02: exact fresh resync is typed and polled on one generation."""
        (
            identity_type,
            receipt_type,
            lease_type,
            witness_type,
            daemon_generation_type,
            _,
            readiness_type,
            _,
        ) = self._api()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        fresh_signal = getattr(
            lifecycle.NativeDaemonReadinessSignal, "FRESH_INSTANCE_RESYNC", None
        )
        self.assertIsNotNone(
            fresh_signal,
            "fresh Watchman reconciliation requires a distinct typed readiness signal",
        )
        fresh_resync = _fresh_instance_resync_status()
        fresh_resync_query_ready = copy.deepcopy(fresh_resync)
        fresh_resync_query_ready["query_ready"] = True
        fresh_scan = fresh_resync_query_ready["scan_progress"]
        assert isinstance(fresh_scan, dict)
        fresh_scan["query_ready_at"] = "fixture"
        initializing = {
            "status": "initializing",
            "server_version": "fixture-1",
            "query_ready": False,
            "scan_progress": {"query_ready_at": None},
        }
        ready = {
            "status": "ready",
            "server_version": "fixture-1",
            "query_ready": True,
            "scan_progress": {"query_ready_at": "fixture"},
        }
        now = 20.0
        sleeps: list[float] = []

        def clock() -> float:
            return now

        def sleep(delay: float) -> None:
            nonlocal now
            sleeps.append(delay)
            now += delay

        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            ledger = root / "fresh-resync-ready.jsonl"
            generation = daemon_generation_type(pid=4242, process_started_at=1234.5)
            track_readiness = False

            def generation_probe() -> object | None:
                observed = (
                    generation
                    if any(row.get("event") == "launch" for row in _read_ledger(ledger))
                    else None
                )
                if track_readiness:
                    _append_ledger(ledger, "generation", matches=observed == generation)
                return observed

            lease, identity, ledger = self._open_lease(
                root,
                lease_type,
                identity_type,
                name="fresh-resync-ready",
                daemon_status_sequence=(
                    fresh_resync,
                    fresh_resync_query_ready,
                    initializing,
                    ready,
                ),
                generation_probe=generation_probe,
            )
            track_readiness = True
            classified: list[object] = []
            original_classifier = lifecycle._require_healthy_native_status

            def classify(*args: Any, **kwargs: Any) -> object:
                signal = original_classifier(*args, **kwargs)
                classified.append(signal)
                return signal

            def record_alive() -> None:
                _append_ledger(ledger, "liveness")
                lease_type.assert_alive(lease)

            try:
                with (
                    mock.patch.object(
                        lease, "assert_alive", side_effect=record_alive
                    ) as alive,
                    mock.patch.object(
                        lifecycle,
                        "_require_healthy_native_status",
                        side_effect=classify,
                    ),
                ):
                    readiness = lease.adjudicate_expected_session(
                        self._receipt(receipt_type, identity, total_chunks=1),
                        witness=witness_type(
                            relative_path="src/fixture.py", literal="needle[1]"
                        ),
                        readiness_timeout_seconds=2.0,
                        readiness_poll_interval_seconds=0.25,
                        clock=clock,
                        sleep=sleep,
                    )
                self.assertIsInstance(readiness, readiness_type)
                self.assertEqual(
                    classified,
                    [
                        fresh_signal,
                        fresh_signal,
                        lifecycle.NativeDaemonReadinessSignal.INITIALIZING,
                        lifecycle.NativeDaemonReadinessSignal.READY,
                    ],
                )
                self.assertEqual(alive.call_count, 4)
                self.assertEqual(sleeps, [0.25, 0.25, 0.25])
                rows = _read_ledger(ledger)
                tools = [
                    row.get("tool") for row in rows if row.get("method") == "tools/call"
                ]
                self.assertEqual(
                    tools,
                    ["daemon_status"] * 4 + ["search"],
                )
                continuity = [
                    row.get("event")
                    for row in rows
                    if row.get("event") in {"liveness", "generation", "tool-response"}
                ]
                self.assertEqual(
                    continuity[:12],
                    ["liveness", "generation", "tool-response"] * 4,
                )
                self.assertTrue(
                    all(
                        row.get("matches") is True
                        for row in rows
                        if row.get("event") == "generation"
                    )
                )
                self.assertEqual(
                    len([row for row in rows if row.get("event") == "launch"]), 1
                )
                self.assertFalse(
                    any(row.get("event") in {"closed", "signal"} for row in rows)
                )
                self.assertEqual(_state_name(lease.state), "HELD")
            finally:
                lease.close()
            self.assertEqual(_state_name(lease.state), "CLOSED")


    def test_status_semantic_consistency_matrix_rejects_only_active_faults(
        self,
    ) -> None:
        """TAP-02: nested active faults contradict ordinary top-level states."""
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        classify = lifecycle._require_healthy_native_status
        signal = lifecycle.NativeDaemonReadinessSignal
        readiness_error = lifecycle.ExpectedSessionReadinessError

        def classify_payload(payload: dict[str, object]) -> object:
            response = {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(payload)}],
                    "isError": False,
                },
            }
            session = mock.Mock()
            session.request.return_value = response
            return classify(session)

        ordinary_pairs = (
            ("ready", True, signal.READY),
            ("initializing", False, signal.INITIALIZING),
        )
        active_faults: tuple[tuple[str, tuple[str, ...], object], ...] = (
            ("needs-resync", ("realtime", "resync", "needs_resync"), True),
            ("needs-resync-int", ("realtime", "resync", "needs_resync"), 1),
            (
                "needs-resync-string",
                ("realtime", "resync", "needs_resync"),
                "true",
            ),
            (
                "needs-resync-container",
                ("realtime", "resync", "needs_resync"),
                {},
            ),
            ("scan-error", ("scan_error",), "scan failed"),
            ("realtime-error", ("realtime", "last_error"), "observer failed"),
            (
                "resync-error",
                ("realtime", "resync", "last_error"),
                "resync failed",
            ),
            ("service-degraded", ("realtime", "service_state"), "degraded"),
            ("live-indexing-stalled", ("realtime", "live_indexing_state"), "stalled"),
        )

        historical = _fresh_instance_resync_status()
        historical_scan = historical["scan_progress"]
        assert isinstance(historical_scan, dict)
        historical_realtime = historical_scan["realtime"]
        assert isinstance(historical_realtime, dict)
        historical_resync = historical_realtime["resync"]
        assert isinstance(historical_resync, dict)
        historical_resync["needs_resync"] = False
        historical_realtime["service_state"] = "running"
        historical_realtime["live_indexing_state"] = "idle"

        for top_status, query_ready, expected in ordinary_pairs:
            with self.subTest(kind="inactive-history", status=top_status):
                payload = copy.deepcopy(historical)
                payload["status"] = top_status
                payload["query_ready"] = query_ready
                self.assertIs(classify_payload(payload), expected)

            with self.subTest(kind="open-vocabulary-states", status=top_status):
                payload = copy.deepcopy(historical)
                payload["status"] = top_status
                payload["query_ready"] = query_ready
                scan = payload["scan_progress"]
                assert isinstance(scan, dict)
                realtime = scan["realtime"]
                assert isinstance(realtime, dict)
                realtime["service_state"] = "future-service-state"
                realtime["live_indexing_state"] = "future-live-indexing-state"
                self.assertIs(classify_payload(payload), expected)

            for fault_name, path, value in active_faults:
                with self.subTest(kind="active-fault", status=top_status, fault=fault_name):
                    payload = copy.deepcopy(historical)
                    payload["status"] = top_status
                    payload["query_ready"] = query_ready
                    target = payload["scan_progress"]
                    assert isinstance(target, dict)
                    for key in path[:-1]:
                        target = target[key]
                        assert isinstance(target, dict)
                    target[path[-1]] = value
                    with self.assertRaises(readiness_error):
                        classify_payload(payload)

        fresh_open_vocabulary = _fresh_instance_resync_status()
        fresh_scan = fresh_open_vocabulary["scan_progress"]
        assert isinstance(fresh_scan, dict)
        fresh_realtime = fresh_scan["realtime"]
        assert isinstance(fresh_realtime, dict)
        fresh_realtime["service_state"] = "future-service-state"
        fresh_realtime["live_indexing_state"] = "future-live-indexing-state"
        self.assertIs(
            classify_payload(fresh_open_vocabulary), signal.FRESH_INSTANCE_RESYNC
        )

    def test_fresh_instance_resync_terminal_near_neighbors_fail_closed(
        self,
    ) -> None:
        """TAP-02: only the exact benign degraded discriminator may be polled."""
        (
            identity_type,
            receipt_type,
            lease_type,
            witness_type,
            _,
            _,
            _,
            readiness_error,
        ) = self._api()
        delete = object()
        cases: tuple[tuple[str, tuple[str, ...], object], ...] = (
            ("missing-needs-resync", ("realtime", "resync", "needs_resync"), delete),
            ("needs-resync-false", ("realtime", "resync", "needs_resync"), False),
            ("needs-resync-wrong-type", ("realtime", "resync", "needs_resync"), 1),
            ("missing-realtime", ("realtime",), delete),
            ("non-dict-realtime", ("realtime",), []),
            ("missing-resync", ("realtime", "resync"), delete),
            ("non-dict-resync", ("realtime", "resync"), []),
            ("missing-details", ("realtime", "resync", "last_details"), delete),
            ("non-dict-details", ("realtime", "resync", "last_details"), []),
            (
                "missing-backend",
                ("realtime", "resync", "last_details", "backend"),
                delete,
            ),
            (
                "wrong-backend",
                ("realtime", "resync", "last_details", "backend"),
                "sdk",
            ),
            (
                "wrong-type-backend",
                ("realtime", "resync", "last_details", "backend"),
                None,
            ),
            ("missing-last-reason", ("realtime", "resync", "last_reason"), delete),
            ("wrong-last-reason", ("realtime", "resync", "last_reason"), "manual"),
            ("wrong-type-last-reason", ("realtime", "resync", "last_reason"), None),
            (
                "missing-loss-reason",
                ("realtime", "resync", "last_details", "loss_of_sync_reason"),
                delete,
            ),
            (
                "wrong-type-loss-reason",
                ("realtime", "resync", "last_details", "loss_of_sync_reason"),
                None,
            ),
            (
                "recrawl",
                ("realtime", "resync", "last_details", "loss_of_sync_reason"),
                "recrawl",
            ),
            (
                "disconnect",
                ("realtime", "resync", "last_details", "loss_of_sync_reason"),
                "disconnect",
            ),
            (
                "overflow",
                ("realtime", "resync", "last_details", "loss_of_sync_reason"),
                "overflow",
            ),
            ("scan-error", ("scan_error",), "scan failed"),
            ("wrong-type-scan-error", ("scan_error",), 0),
            ("missing-realtime-error", ("realtime", "last_error"), delete),
            ("realtime-error", ("realtime", "last_error"), "observer failed"),
            ("wrong-type-realtime-error", ("realtime", "last_error"), False),
            ("missing-resync-error", ("realtime", "resync", "last_error"), delete),
            ("resync-error", ("realtime", "resync", "last_error"), "resync failed"),
            ("wrong-type-resync-error", ("realtime", "resync", "last_error"), 0),
            ("missing-service-state", ("realtime", "service_state"), delete),
            ("service-degraded", ("realtime", "service_state"), "degraded"),
            ("wrong-type-service-state", ("realtime", "service_state"), None),
            ("missing-live-indexing-state", ("realtime", "live_indexing_state"), delete),
            ("live-indexing-stalled", ("realtime", "live_indexing_state"), "stalled"),
            ("wrong-type-live-indexing-state", ("realtime", "live_indexing_state"), 1),
        )

        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            for index, (name, path, value) in enumerate(cases):
                with self.subTest(name=name):
                    status = _fresh_instance_resync_status()
                    target = status["scan_progress"]
                    assert isinstance(target, dict)
                    for key in path[:-1]:
                        target = target[key]
                        assert isinstance(target, dict)
                    if value is delete:
                        del target[path[-1]]
                    else:
                        target[path[-1]] = value
                    sleeps: list[float] = []

                    def reject_sleep(delay: float) -> None:
                        sleeps.append(delay)
                        raise AssertionError(
                            f"terminal fresh-resync neighbor slept for {delay}"
                        )

                    lease, identity, ledger = self._open_lease(
                        root,
                        lease_type,
                        identity_type,
                        name=f"fresh-resync-neighbor-{index}",
                        daemon_status=status,
                    )
                    try:
                        with self.assertRaises(readiness_error):
                            lease.adjudicate_expected_session(
                                self._receipt(receipt_type, identity, total_chunks=1),
                                witness=witness_type(
                                    relative_path="src/fixture.py", literal="needle[1]"
                                ),
                                readiness_timeout_seconds=1.0,
                                readiness_poll_interval_seconds=0.25,
                                clock=lambda: 30.0,
                                sleep=reject_sleep,
                            )
                        self.assertEqual(sleeps, [])
                        tools = [
                            row.get("tool")
                            for row in _read_ledger(ledger)
                            if row.get("method") == "tools/call"
                        ]
                        self.assertEqual(tools, ["daemon_status"])
                        self.assertNotIn("search", tools)
                        self.assertEqual(_state_name(lease.state), "HELD")
                    finally:
                        lease.close()
                    self.assertTrue(
                        _wait_until(
                            lambda: any(
                                row.get("event") in {"closed", "signal"}
                                for row in _read_ledger(ledger)
                            )
                        )
                    )
                    self.assertEqual(_state_name(lease.state), "CLOSED")


    def test_initializing_only_times_out_with_deterministic_budget_and_no_search(
        self,
    ) -> None:
        """Deadline exhaustion has a typed, singular lifecycle result."""
        (
            identity_type,
            receipt_type,
            lease_type,
            witness_type,
            daemon_generation_type,
            _,
            _,
            readiness_error,
        ) = self._api()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        timeout_error = getattr(lifecycle, "ExpectedSessionReadinessTimeoutError", None)
        self.assertIsNotNone(
            timeout_error,
            "readiness deadline exhaustion requires ExpectedSessionReadinessTimeoutError",
        )
        assert isinstance(timeout_error, type)
        self.assertTrue(issubclass(timeout_error, readiness_error))
        initializing = {
            "status": "initializing",
            "server_version": "fixture-1",
            "query_ready": False,
            "scan_progress": {"query_ready_at": None},
        }
        now = 20.0
        sleeps: list[float] = []

        def clock() -> float:
            return now

        def sleep(delay: float) -> None:
            nonlocal now
            sleeps.append(delay)
            now += delay

        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            ledger = root / "initializing-timeout.jsonl"
            generation = daemon_generation_type(pid=4242, process_started_at=1234.5)
            generation_observations: list[object | None] = []

            def generation_probe() -> object | None:
                observed = (
                    generation
                    if any(row.get("event") == "launch" for row in _read_ledger(ledger))
                    else None
                )
                generation_observations.append(observed)
                return observed

            lease, identity, ledger = self._open_lease(
                root,
                lease_type,
                identity_type,
                name="initializing-timeout",
                daemon_status_sequence=(initializing,),
                generation_probe=generation_probe,
            )
            with mock.patch.object(lease, "close", wraps=lease.close) as close:
                with self.assertRaises(timeout_error):
                    lease.adjudicate_expected_session(
                        self._receipt(receipt_type, identity, total_chunks=1),
                        witness=witness_type(
                            relative_path="src/fixture.py", literal="needle[1]"
                        ),
                        readiness_timeout_seconds=0.5,
                        readiness_poll_interval_seconds=0.2,
                        clock=clock,
                        sleep=sleep,
                    )
                close.assert_not_called()
                self.assertEqual(_state_name(lease.state), "HELD")
                lease.close()
                close.assert_called_once_with()
            self.assertEqual(sleeps, [0.2, 0.2, 0.1])
            self.assertEqual(now, 20.5)
            rows = _read_ledger(ledger)
            tools = [
                row.get("tool") for row in rows if row.get("method") == "tools/call"
            ]
            self.assertEqual(tools, ["daemon_status"] * 3)
            self.assertNotIn("search", tools)
            self.assertEqual(
                len([row for row in rows if row.get("event") == "launch"]), 1
            )
            self.assertEqual(generation_observations[0], None)
            self.assertTrue(
                all(item == generation for item in generation_observations[1:]),
                generation_observations,
            )
            self.assertTrue(
                _wait_until(
                    lambda: any(
                        row.get("event") in {"closed", "signal"}
                        for row in _read_ledger(ledger)
                    )
                ),
                _read_ledger(ledger),
            )
            self.assertEqual(_state_name(lease.state), "CLOSED")

    def test_ready_response_completing_at_deadline_is_timeout(self) -> None:
        """A ready result is not accepted when its request consumes the budget."""
        (
            identity_type,
            receipt_type,
            lease_type,
            witness_type,
            _,
            _,
            _,
            _,
        ) = self._api()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        ready = {
            "status": "ready",
            "server_version": "fixture-1",
            "query_ready": True,
            "scan_progress": {"query_ready_at": "fixture"},
        }
        now = 40.0
        request_timeouts: list[float] = []

        def clock() -> float:
            return now

        def slow_ready(
            _session: Any,
            *,
            tool: str,
            arguments: dict[str, Any],
            timeout_seconds: float,
        ) -> str:
            nonlocal now
            self.assertEqual(tool, "daemon_status")
            self.assertEqual(arguments, {})
            request_timeouts.append(timeout_seconds)
            now += timeout_seconds
            return json.dumps(ready)

        with tempfile.TemporaryDirectory() as raw_root:
            lease, identity, ledger = self._open_lease(
                Path(raw_root), lease_type, identity_type, name="slow-ready"
            )
            try:
                with mock.patch.object(
                    lifecycle, "_strict_tool_text", side_effect=slow_ready
                ):
                    with self.assertRaises(
                        lifecycle.ExpectedSessionReadinessTimeoutError
                    ):
                        lease.adjudicate_expected_session(
                            self._receipt(receipt_type, identity, total_chunks=1),
                            witness=witness_type(
                                relative_path="src/fixture.py", literal="needle[1]"
                            ),
                            readiness_timeout_seconds=0.5,
                            readiness_poll_interval_seconds=0.1,
                            clock=clock,
                            sleep=lambda _delay: self.fail("deadline path slept"),
                        )
                self.assertEqual(request_timeouts, [0.5])
                self.assertNotIn(
                    "search",
                    [
                        row.get("tool")
                        for row in _read_ledger(ledger)
                        if row.get("method") == "tools/call"
                    ],
                )
            finally:
                lease.close()

    def test_ready_before_deadline_keeps_independent_search_timeout(self) -> None:
        """The readiness budget ends when READY completes before its deadline."""
        (
            identity_type,
            receipt_type,
            lease_type,
            witness_type,
            _,
            _,
            readiness_type,
            _,
        ) = self._api()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        ready = {
            "status": "ready",
            "server_version": "fixture-1",
            "query_ready": True,
            "scan_progress": {"query_ready_at": "fixture"},
        }
        now = 50.0
        request_timeouts: list[tuple[str, float]] = []
        strict_tool_text = lifecycle._strict_tool_text

        def clock() -> float:
            return now

        def timed_tool(
            session: Any,
            *,
            tool: str,
            arguments: dict[str, Any],
            timeout_seconds: float,
        ) -> str:
            nonlocal now
            request_timeouts.append((tool, timeout_seconds))
            if tool == "daemon_status":
                now = 50.49
                return json.dumps(ready)
            self.assertEqual(tool, "search")
            self.assertEqual(timeout_seconds, 60.0)
            now = 75.0
            return strict_tool_text(
                session,
                tool=tool,
                arguments=arguments,
                timeout_seconds=timeout_seconds,
            )

        with tempfile.TemporaryDirectory() as raw_root:
            lease, identity, _ = self._open_lease(
                Path(raw_root), lease_type, identity_type, name="ready-before-deadline"
            )
            try:
                with mock.patch.object(
                    lifecycle, "_strict_tool_text", side_effect=timed_tool
                ):
                    result = lease.adjudicate_expected_session(
                        self._receipt(receipt_type, identity, total_chunks=1),
                        witness=witness_type(
                            relative_path="src/fixture.py", literal="needle[1]"
                        ),
                        readiness_timeout_seconds=0.5,
                        readiness_poll_interval_seconds=0.1,
                        clock=clock,
                        sleep=lambda _delay: self.fail("ready path slept"),
                    )
                self.assertIsInstance(result, readiness_type)
                self.assertEqual(request_timeouts, [("daemon_status", 0.5), ("search", 60.0)])
                self.assertGreater(now, 50.5)
            finally:
                lease.close()

    def test_process_loss_while_initializing_is_terminal_without_more_work(
        self,
    ) -> None:
        """A real held proxy exit is detected before another status request."""
        identity_type, receipt_type, lease_type, witness_type, *_, readiness_error = (
            self._api()
        )
        initializing = {
            "status": "initializing",
            "server_version": "fixture-1",
            "query_ready": False,
            "scan_progress": {"query_ready_at": None},
        }
        sleeps: list[float] = []
        now = 60.0
        with tempfile.TemporaryDirectory() as raw_root:
            lease, identity, ledger = self._open_lease(
                Path(raw_root),
                lease_type,
                identity_type,
                name="process-loss",
                daemon_status_sequence=(initializing,),
            )
            session = lease._session
            self.assertIsNotNone(session)

            def clock() -> float:
                return now

            def lose_process(delay: float) -> None:
                nonlocal now
                sleeps.append(delay)
                now += delay
                assert session is not None
                session.proc.terminate()
                session.proc.wait(timeout=2.0)

            try:
                with self.assertRaises(readiness_error):
                    lease.adjudicate_expected_session(
                        self._receipt(receipt_type, identity, total_chunks=1),
                        witness=witness_type(
                            relative_path="src/fixture.py", literal="needle[1]"
                        ),
                        readiness_timeout_seconds=1.0,
                        readiness_poll_interval_seconds=0.1,
                        clock=clock,
                        sleep=lose_process,
                    )
                self.assertEqual(sleeps, [0.1])
                tools = [
                    row.get("tool")
                    for row in _read_ledger(ledger)
                    if row.get("method") == "tools/call"
                ]
                self.assertEqual(tools, ["daemon_status"])
                self.assertNotIn("search", tools)
                self.assertEqual(_state_name(lease.state), "HELD")
            finally:
                lease.close()
            self.assertEqual(_state_name(lease.state), "CLOSED")

    def test_status_transport_timeout_is_terminal_without_sleep_or_search(
        self,
    ) -> None:
        """A real unanswered JSON-RPC status request fails at its request budget."""
        identity_type, receipt_type, lease_type, witness_type, *_, readiness_error = (
            self._api()
        )
        sleeps: list[float] = []
        with tempfile.TemporaryDirectory() as raw_root:
            lease, identity, ledger = self._open_lease(
                Path(raw_root),
                lease_type,
                identity_type,
                name="status-timeout",
                daemon_status_no_response=True,
            )
            try:
                with self.assertRaises(readiness_error):
                    lease.adjudicate_expected_session(
                        self._receipt(receipt_type, identity, total_chunks=1),
                        witness=witness_type(
                            relative_path="src/fixture.py", literal="needle[1]"
                        ),
                        readiness_timeout_seconds=0.2,
                        readiness_poll_interval_seconds=0.01,
                        sleep=sleeps.append,
                    )
                self.assertEqual(sleeps, [])
                tools = [
                    row.get("tool")
                    for row in _read_ledger(ledger)
                    if row.get("method") == "tools/call"
                ]
                self.assertEqual(tools, ["daemon_status"])
                self.assertNotIn("search", tools)
                self.assertEqual(_state_name(lease.state), "HELD")
            finally:
                lease.close()
            self.assertEqual(_state_name(lease.state), "CLOSED")

    def test_contradictory_status_pairs_are_immediate_terminal_without_sleep(
        self,
    ) -> None:
        """Only exact initializing/false is transient; contradictory pairs abort."""
        (
            identity_type,
            receipt_type,
            lease_type,
            witness_type,
            _,
            _,
            _,
            readiness_error,
        ) = self._api()
        cases = {
            "initializing-true": {
                "status": "initializing",
                "server_version": "fixture-1",
                "query_ready": True,
                "scan_progress": {"query_ready_at": None},
            },
            "ready-false": {
                "status": "ready",
                "server_version": "fixture-1",
                "query_ready": False,
                "scan_progress": {"query_ready_at": None},
            },
        }
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            for index, (name, status) in enumerate(cases.items()):
                with self.subTest(name=name):
                    sleeps: list[float] = []
                    lease, identity, ledger = self._open_lease(
                        root,
                        lease_type,
                        identity_type,
                        name=f"contradictory-{index}",
                        daemon_status=status,
                    )
                    try:
                        with self.assertRaises(readiness_error):
                            lease.adjudicate_expected_session(
                                self._receipt(receipt_type, identity, total_chunks=1),
                                witness=witness_type(
                                    relative_path="src/fixture.py", literal="needle[1]"
                                ),
                                readiness_timeout_seconds=1.0,
                                readiness_poll_interval_seconds=0.2,
                                clock=lambda: 10.0,
                                sleep=sleeps.append,
                            )
                        self.assertEqual(sleeps, [])
                        tools = [
                            row.get("tool")
                            for row in _read_ledger(ledger)
                            if row.get("method") == "tools/call"
                        ]
                        self.assertEqual(tools, ["daemon_status"])
                        self.assertNotIn("search", tools)
                        self.assertEqual(_state_name(lease.state), "HELD")
                    finally:
                        lease.close()

    def test_generation_loss_during_initializing_is_terminal_before_second_probe(
        self,
    ) -> None:
        """Each retry re-proves liveness and generation before native status."""
        (
            identity_type,
            receipt_type,
            lease_type,
            witness_type,
            daemon_generation_type,
            _,
            _,
            readiness_error,
        ) = self._api()
        initializing = {
            "status": "initializing",
            "server_version": "fixture-1",
            "query_ready": False,
            "scan_progress": {"query_ready_at": None},
        }
        sleeps: list[float] = []
        now = 30.0

        def clock() -> float:
            return now

        def sleep(delay: float) -> None:
            nonlocal now
            sleeps.append(delay)
            now += delay

        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            ledger = root / "generation-loss.jsonl"
            generation = daemon_generation_type(pid=4242, process_started_at=1234.5)
            track_readiness = False

            def generation_probe() -> object | None:
                launched = any(
                    row.get("event") == "launch" for row in _read_ledger(ledger)
                )
                status_samples = sum(
                    row.get("event") == "tool-response" for row in _read_ledger(ledger)
                )
                observed = generation if launched and status_samples == 0 else None
                if track_readiness:
                    _append_ledger(
                        ledger,
                        "generation" if observed is not None else "generation-loss",
                    )
                return observed

            lease, identity, ledger = self._open_lease(
                root,
                lease_type,
                identity_type,
                name="generation-loss",
                daemon_status_sequence=(initializing,),
                generation_probe=generation_probe,
            )
            track_readiness = True

            def record_alive() -> None:
                _append_ledger(ledger, "liveness")
                lease_type.assert_alive(lease)

            try:
                with mock.patch.object(lease, "assert_alive", side_effect=record_alive):
                    with self.assertRaises(readiness_error):
                        lease.adjudicate_expected_session(
                            self._receipt(receipt_type, identity, total_chunks=1),
                            witness=witness_type(
                                relative_path="src/fixture.py", literal="needle[1]"
                            ),
                            readiness_timeout_seconds=1.0,
                            readiness_poll_interval_seconds=0.1,
                            clock=clock,
                            sleep=sleep,
                        )
                self.assertEqual(sleeps, [0.1])
                rows = _read_ledger(ledger)
                tools = [
                    row.get("tool") for row in rows if row.get("method") == "tools/call"
                ]
                self.assertEqual(tools, ["daemon_status"])
                self.assertNotIn("search", tools)
                continuity = [
                    row.get("event")
                    for row in rows
                    if row.get("event")
                    in {"liveness", "generation", "tool-response", "generation-loss"}
                ]
                self.assertEqual(
                    continuity,
                    [
                        "liveness",
                        "generation",
                        "tool-response",
                        "liveness",
                        "generation-loss",
                    ],
                )
                self.assertEqual(_state_name(lease.state), "HELD")
            finally:
                lease.close()

    def test_native_response_failures_use_typed_errors_and_fixed_public_text(
        self,
    ) -> None:
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        witness = lifecycle.ExpectedSearchWitness(
            relative_path="src/fixture.py", literal="needle[1]"
        )
        raw_detail = "private-native-detail-/secret/repo/token-value"

        def text_response(text: str) -> dict[str, object]:
            return {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "content": [{"type": "text", "text": text}],
                    "isError": False,
                },
            }

        transport_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32000, "message": raw_detail},
        }
        cases = (
            (
                "status-malformed",
                lifecycle._require_healthy_native_status,
                text_response("{" + raw_detail),
                lifecycle.NativeStatusReadinessError,
                "native ChunkHound daemon_status returned malformed JSON",
            ),
            (
                "status-transport",
                lifecycle._require_healthy_native_status,
                transport_response,
                lifecycle.NativeStatusReadinessError,
                "native ChunkHound daemon_status request failed",
            ),
            (
                "search-malformed",
                lambda session: lifecycle._require_native_search_witness(
                    session, witness
                ),
                text_response(raw_detail),
                lifecycle.NativeSearchWitnessReadinessError,
                "native ChunkHound search did not prove the exact source witness",
            ),
            (
                "search-transport",
                lambda session: lifecycle._require_native_search_witness(
                    session, witness
                ),
                transport_response,
                lifecycle.NativeSearchWitnessReadinessError,
                "native ChunkHound search request failed",
            ),
        )
        for name, invoke, response, error_type, public_text in cases:
            with self.subTest(name=name):
                session = mock.Mock()
                session.request.return_value = response
                with self.assertRaises(error_type) as caught:
                    invoke(session)
                self.assertEqual(str(caught.exception), public_text)
                self.assertNotIn(raw_detail, str(caught.exception))
                self.assertTrue(
                    issubclass(error_type, lifecycle.ExpectedSessionReadinessError)
                )

    def test_readiness_status_timeout_tolerates_fresh_instance_resync_scan(
        self,
    ) -> None:
        """The per-call status budget must exceed real fresh-instance resync scans.

        A fresh-instance reconciliation blocks the daemon's event loop on a
        directory scan (observed 3.3s on a fast machine vs 12.6s on a slower
        one for a 213-chunk repo). The per-call daemon_status timeout must
        stay above that floor so readiness adjudication does not abort a
        healthy daemon that is busy rescanning.
        """
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        self.assertGreaterEqual(
            lifecycle._READINESS_STATUS_TIMEOUT_SECONDS,
            30.0,
        )

    def test_native_status_failure_carries_raw_payload_and_last_status(self) -> None:
        """Failure evidence rides on the typed error: payload text + parsed status."""
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")

        def text_response(text: str) -> dict[str, object]:
            return {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "content": [{"type": "text", "text": text}],
                    "isError": False,
                },
            }

        malformed = "{" + "not-json"
        wrong_keys = {"status": "ready", "server_version": "fixture-1"}
        degraded = {
            "status": "degraded",
            "server_version": "fixture-1",
            "query_ready": False,
            "scan_progress": {"backend": "watchman"},
        }
        cases = (
            ("malformed", text_response(malformed), malformed, None),
            (
                "wrong-keys",
                text_response(json.dumps(wrong_keys)),
                json.dumps(wrong_keys),
                wrong_keys,
            ),
            (
                "degraded",
                text_response(json.dumps(degraded)),
                json.dumps(degraded),
                degraded,
            ),
        )
        for name, response, payload, status in cases:
            with self.subTest(name=name):
                session = mock.Mock()
                session.request.return_value = response
                with self.assertRaises(
                    lifecycle.NativeStatusReadinessError
                ) as caught:
                    lifecycle._require_healthy_native_status(session)
                self.assertEqual(caught.exception.status_payload, payload)
                self.assertEqual(caught.exception.status, status)

        transport = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32000, "message": "transport"},
        }
        session = mock.Mock()
        session.request.return_value = transport
        with self.assertRaises(lifecycle.NativeStatusReadinessError) as caught:
            lifecycle._require_healthy_native_status(session)
        self.assertIsNone(caught.exception.status_payload)
        self.assertIsNone(caught.exception.status)

        ready = {
            "status": "ready",
            "server_version": "fixture-1",
            "query_ready": True,
            "scan_progress": {"query_ready_at": "fixture"},
        }
        observations: list[dict[str, object]] = []
        session = mock.Mock()
        session.request.return_value = text_response(json.dumps(ready))
        signal = lifecycle._require_healthy_native_status(
            session, observations=observations
        )
        self.assertIs(signal, lifecycle.NativeDaemonReadinessSignal.READY)
        self.assertEqual(
            observations,
            [
                {
                    "signal": "READY",
                    "status": "ready",
                    "query_ready": True,
                    "server_version": "fixture-1",
                }
            ],
        )

    def test_readiness_timeout_attaches_poll_evidence(self) -> None:
        """Deadline exhaustion carries the full observation timeline on the error."""
        (
            identity_type,
            receipt_type,
            lease_type,
            witness_type,
            _,
            _,
            _,
            _,
        ) = self._api()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        initializing = {
            "status": "initializing",
            "server_version": "fixture-1",
            "query_ready": False,
            "scan_progress": {"query_ready_at": None},
        }
        now = 20.0
        sleeps: list[float] = []

        def clock() -> float:
            return now

        def sleep(delay: float) -> None:
            nonlocal now
            sleeps.append(delay)
            now += delay

        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            lease, identity, _ = self._open_lease(
                root,
                lease_type,
                identity_type,
                name="poll-evidence-timeout",
                daemon_status_sequence=(initializing,),
            )
            try:
                with self.assertRaises(
                    lifecycle.ExpectedSessionReadinessTimeoutError
                ) as caught:
                    lease.adjudicate_expected_session(
                        self._receipt(receipt_type, identity, total_chunks=1),
                        witness=witness_type(
                            relative_path="src/fixture.py", literal="needle[1]"
                        ),
                        readiness_timeout_seconds=0.5,
                        readiness_poll_interval_seconds=0.2,
                        clock=clock,
                        sleep=sleep,
                    )
                self.assertEqual(
                    caught.exception.poll_evidence,
                    {
                        "polls": 3,
                        "observations": [
                            {
                                "signal": "INITIALIZING",
                                "status": "initializing",
                                "query_ready": False,
                                "server_version": "fixture-1",
                            }
                        ]
                        * 3,
                        "timeout_seconds": 0.5,
                        "elapsed_seconds": 0.5,
                    },
                )
            finally:
                lease.close()

    def test_terminal_status_failure_attaches_payload_and_poll_evidence(self) -> None:
        """An immediate non-transient status failure keeps its raw payload."""
        (
            identity_type,
            receipt_type,
            lease_type,
            witness_type,
            _,
            _,
            _,
            _,
        ) = self._api()
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        contradictory = {
            "status": "ready",
            "server_version": "fixture-1",
            "query_ready": False,
            "scan_progress": {"query_ready_at": None},
        }
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            lease, identity, _ = self._open_lease(
                root,
                lease_type,
                identity_type,
                name="terminal-payload-evidence",
                daemon_status=contradictory,
            )
            try:
                with self.assertRaises(
                    lifecycle.NativeStatusReadinessError
                ) as caught:
                    lease.adjudicate_expected_session(
                        self._receipt(receipt_type, identity, total_chunks=1),
                        witness=witness_type(
                            relative_path="src/fixture.py", literal="needle[1]"
                        ),
                        readiness_timeout_seconds=1.0,
                        readiness_poll_interval_seconds=0.2,
                        clock=lambda: 10.0,
                        sleep=lambda delay: None,
                    )
                self.assertEqual(caught.exception.status, contradictory)
                self.assertEqual(
                    json.loads(caught.exception.status_payload or "{}"),
                    contradictory,
                )
                self.assertEqual(
                    caught.exception.poll_evidence,
                    {
                        "polls": 0,
                        "observations": [],
                        "timeout_seconds": 1.0,
                        "elapsed_seconds": 0.0,
                    },
                )
            finally:
                lease.close()

    def test_strict_status_envelope_and_health_fail_closed_before_search(self) -> None:
        (
            identity_type,
            receipt_type,
            lease_type,
            witness_type,
            _,
            _,
            _,
            readiness_error,
        ) = self._api()
        healthy = {
            "status": "ready",
            "server_version": "fixture-1",
            "query_ready": True,
            "scan_progress": {"query_ready_at": "fixture"},
        }
        variants: dict[str, tuple[object | None, dict[str, object] | None]] = {
            "rpc-error": (
                healthy,
                {"daemon_status": {"error": {"code": -32000, "message": "boom"}}},
            ),
            "tool-is-error": (
                healthy,
                {
                    "daemon_status": {
                        "result": {
                            "content": [{"type": "text", "text": json.dumps(healthy)}],
                            "isError": True,
                        }
                    }
                },
            ),
            "missing-is-error": (
                healthy,
                {
                    "daemon_status": {
                        "result": {
                            "content": [{"type": "text", "text": json.dumps(healthy)}]
                        }
                    }
                },
            ),
            "non-object": ([], None),
            "malformed-json": (
                healthy,
                {
                    "daemon_status": {
                        "result": {
                            "content": [{"type": "text", "text": "{"}],
                            "isError": False,
                        }
                    }
                },
            ),
            "missing-field": (
                {
                    key: value
                    for key, value in healthy.items()
                    if key != "server_version"
                },
                None,
            ),
            "wrong-type": ({**healthy, "query_ready": 1}, None),
            "wrong-scan-progress": ({**healthy, "scan_progress": []}, None),
            "invented-generation": ({**healthy, "generation": "not-native"}, None),
            "degraded": ({**healthy, "status": "degraded"}, None),
        }
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            for index, (name, (status, overrides)) in enumerate(variants.items()):
                with self.subTest(name=name):
                    lease, identity, ledger = self._open_lease(
                        root,
                        lease_type,
                        identity_type,
                        name=f"status-{index}",
                        daemon_status=status,
                        tool_overrides=overrides,
                    )
                    try:
                        receipt = self._receipt(receipt_type, identity, total_chunks=1)
                        witness = witness_type(
                            relative_path="src/fixture.py", literal="needle[1]"
                        )
                        with self.assertRaises(readiness_error):
                            lease.adjudicate_expected_session(receipt, witness=witness)
                        tools = [
                            row.get("tool")
                            for row in _read_ledger(ledger)
                            if row.get("method") == "tools/call"
                        ]
                        self.assertEqual(tools, ["daemon_status"])
                    finally:
                        lease.close()
                    self.assertTrue(
                        _wait_until(
                            lambda: any(
                                row.get("event") in {"closed", "signal"}
                                for row in _read_ledger(ledger)
                            )
                        ),
                        _read_ledger(ledger),
                    )
                    self.assertEqual(_state_name(lease.state), "CLOSED")

    def test_nonempty_receipt_requires_exact_safe_path_and_fenced_literal(self) -> None:
        (
            identity_type,
            receipt_type,
            lease_type,
            witness_type,
            _,
            _,
            _,
            readiness_error,
        ) = self._api()
        literal = "needle[1]"
        cases: dict[str, tuple[str, dict[str, object] | None]] = {
            "no-results": ("No results found.", None),
            "wrong-path": (
                f"## `src/other.py` L1\n\n```text\n{literal}\n```\n\n---\nResults 1–1",
                None,
            ),
            "warning-only": (f"> **Warning:** {literal}\n\nNo results found.", None),
            "other-hit": (
                "## `src/fixture.py` L1\n\n```text\nno witness\n```\n\n---\n\n"
                f"## `src/other.py` L1\n\n```text\n{literal}\n```\n\n---\nResults 1–2",
                None,
            ),
            "malformed-markdown": (
                f"## `src/fixture.py` L1\n\n```text\n{literal}\n",
                None,
            ),
            "non-first-page": (
                f"## `src/fixture.py` L2\n\n```text\n{literal}\n```\n\n---\n"
                "Page 2 of 2 (results 2–2 of 2)",
                None,
            ),
            "non-first-results": (
                f"## `src/fixture.py` L2\n\n```text\n{literal}\n```\n\n---\nResults 2–2",
                None,
            ),
            "rpc-error": (
                "unused",
                {"search": {"error": {"code": -32000, "message": "boom"}}},
            ),
            "tool-is-error": (
                "unused",
                {
                    "search": {
                        "result": {
                            "content": [{"type": "text", "text": "boom"}],
                            "isError": True,
                        }
                    }
                },
            ),
            "non-text-content": (
                "unused",
                {
                    "search": {
                        "result": {
                            "content": [{"type": "image", "data": "x"}],
                            "isError": False,
                        }
                    }
                },
            ),
        }
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            for index, (name, (markdown, overrides)) in enumerate(cases.items()):
                with self.subTest(name=name):
                    lease, identity, _ = self._open_lease(
                        root,
                        lease_type,
                        identity_type,
                        name=f"search-{index}",
                        search_text=markdown,
                        tool_overrides=overrides,
                    )
                    try:
                        with self.assertRaises(readiness_error):
                            lease.adjudicate_expected_session(
                                self._receipt(receipt_type, identity, total_chunks=1),
                                witness=witness_type(
                                    relative_path="src/fixture.py", literal=literal
                                ),
                            )
                    finally:
                        lease.close()

            for index, unsafe_path in enumerate(
                ("/src/fixture.py", "src/../fixture.py", "src\\fixture.py")
            ):
                with self.subTest(unsafe_path=unsafe_path):
                    lease, identity, ledger = self._open_lease(
                        root, lease_type, identity_type, name=f"unsafe-{index}"
                    )
                    try:
                        with self.assertRaises(readiness_error):
                            lease.adjudicate_expected_session(
                                self._receipt(receipt_type, identity, total_chunks=1),
                                witness=witness_type(
                                    relative_path=unsafe_path, literal=literal
                                ),
                            )
                        tools = [
                            row.get("tool")
                            for row in _read_ledger(ledger)
                            if row.get("method") == "tools/call"
                        ]
                        self.assertEqual(tools, ["daemon_status"])
                    finally:
                        lease.close()

    def test_zero_receipt_never_searches_and_requires_current_owned_evidence(
        self,
    ) -> None:
        (
            identity_type,
            receipt_type,
            lease_type,
            witness_type,
            daemon_generation_type,
            evidence_type,
            readiness_type,
            readiness_error,
        ) = self._api()
        generation = daemon_generation_type(pid=4242, process_started_at=1234.5)
        foreign_generation = daemon_generation_type(pid=4343, process_started_at=1234.5)
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            owned_observations: list[object | None] = []
            owned_ledger = root / "owned.jsonl"

            def owned_probe() -> object | None:
                observed = (
                    generation
                    if any(
                        row.get("event") == "launch"
                        for row in _read_ledger(owned_ledger)
                    )
                    else None
                )
                owned_observations.append(observed)
                return observed

            owned_lease, owned_identity, owned_ledger = self._open_lease(
                root,
                lease_type,
                identity_type,
                name="owned",
                generation_probe=owned_probe,
            )
            owned = owned_lease.owned_generation
            self.assertEqual(owned_observations[:2], [None, generation])
            self.assertIsInstance(owned, evidence_type)

            stale_lease, _, _ = self._open_lease(
                root, lease_type, identity_type, name="stale"
            )
            stale = stale_lease.owned_generation
            self.assertIsInstance(stale, evidence_type)
            stale_lease.close()

            foreign_lease, _, _ = self._open_lease(
                root,
                lease_type,
                identity_type,
                name="foreign",
                generation_probe=lambda: foreign_generation,
            )
            self.assertIsNone(
                foreign_lease.owned_generation,
                "a preexisting daemon generation is not owned by a newly opened MCP proxy",
            )

            preexisting_observations: list[object | None] = []

            def preexisting_probe() -> object:
                preexisting_observations.append(generation)
                return generation

            preexisting_lease, identity, ledger = self._open_lease(
                root,
                lease_type,
                identity_type,
                name="preexisting",
                generation_probe=preexisting_probe,
            )
            try:
                self.assertEqual(preexisting_observations[:2], [generation, generation])
                self.assertIsNone(
                    preexisting_lease.owned_generation,
                    "unchanged preexisting generation must await content adjudication",
                )
                zero_receipt = self._receipt(receipt_type, identity, total_chunks=0)
                with self.assertRaises(readiness_error):
                    preexisting_lease.adjudicate_expected_session(zero_receipt)

                class ForgedEvidence(evidence_type):
                    def __new__(cls) -> object:
                        return object.__new__(cls)

                    def __init__(self) -> None:
                        pass

                    def _matches(self, lease_token: object, generation: object) -> bool:
                        return True

                with self.assertRaises(readiness_error):
                    preexisting_lease.adjudicate_expected_session(
                        zero_receipt,
                        expected_generation=ForgedEvidence(),
                    )

                for name, evidence in (
                    ("foreign", owned),
                    ("stale", stale),
                ):
                    with self.subTest(name=name):
                        with self.assertRaises(readiness_error):
                            preexisting_lease.adjudicate_expected_session(
                                zero_receipt, expected_generation=evidence
                            )

                owned_readiness = owned_lease.adjudicate_expected_session(
                    self._receipt(receipt_type, owned_identity, total_chunks=0),
                    expected_generation=owned,
                )
                self.assertIsInstance(owned_readiness, readiness_type)
                self.assertIsInstance(
                    owned_readiness.expected_generation, evidence_type
                )
                self.assertNotIn(
                    "search",
                    [
                        row.get("tool")
                        for row in _read_ledger(owned_ledger)
                        if row.get("method") == "tools/call"
                    ],
                    "owned zero receipt must never issue search",
                )
                self.assertNotIn(
                    "search",
                    [
                        row.get("tool")
                        for row in _read_ledger(ledger)
                        if row.get("method") == "tools/call"
                    ],
                    "unexplained preexisting zero receipts must never issue search",
                )

                nonempty = preexisting_lease.adjudicate_expected_session(
                    self._receipt(receipt_type, identity, total_chunks=1),
                    witness=witness_type(
                        relative_path="src/fixture.py", literal="needle[1]"
                    ),
                )
                adjudicated = nonempty.expected_generation
                self.assertIsInstance(adjudicated, evidence_type)
                search_count = len(
                    [
                        row
                        for row in _read_ledger(ledger)
                        if row.get("method") == "tools/call"
                        and row.get("tool") == "search"
                    ]
                )
                preexisting_lease.adjudicate_expected_session(
                    zero_receipt, expected_generation=adjudicated
                )
                final_tools = [
                    row.get("tool")
                    for row in _read_ledger(ledger)
                    if row.get("method") == "tools/call"
                ]
                self.assertEqual(
                    final_tools.count("search"),
                    search_count,
                    "adjudicated preexisting evidence authorizes zero without another search",
                )
                self.assertGreaterEqual(final_tools.count("daemon_status"), 1)
            finally:
                preexisting_lease.close()
                foreign_lease.close()
                owned_lease.close()


class DaemonLifecycleProductionUtilityTests(unittest.TestCase):
    def test_daemon_log_startup_precondition_accepts_only_creation_safe_states(
        self,
    ) -> None:
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        precondition = getattr(
            lifecycle,
            "assert_daemon_log_startup_precondition",
            None,
        )
        self.assertTrue(
            callable(precondition),
            "A22 RED: a production daemon-log creation precondition is required",
        )

        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            absent_parent = root / "absent-parent"
            absent_parent.mkdir()
            precondition(repo_path=absent_parent)
            self.assertFalse((absent_parent / ".chunkhound").exists())

            existing_parent = root / "existing-parent"
            existing_parent.mkdir()
            chunkhound_parent = existing_parent / ".chunkhound"
            chunkhound_parent.mkdir(mode=0o750)
            sibling = chunkhound_parent / "operator-note"
            sibling.write_bytes(b"preserve exactly\n")
            before_mode = chunkhound_parent.stat().st_mode
            before_sibling = sibling.read_bytes()
            precondition(repo_path=existing_parent)
            self.assertEqual(chunkhound_parent.stat().st_mode, before_mode)
            self.assertEqual(sibling.read_bytes(), before_sibling)
            self.assertFalse((chunkhound_parent / "daemon.log").exists())

    def test_daemon_log_startup_precondition_rejects_parent_and_log_hazards_unchanged(
        self,
    ) -> None:
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        precondition = getattr(
            lifecycle,
            "assert_daemon_log_startup_precondition",
            None,
        )
        self.assertTrue(callable(precondition))

        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            for case in (
                "parent-file",
                "parent-symlink",
                "regular-log",
                "log-symlink",
            ):
                with self.subTest(case=case):
                    repo = root / case
                    repo.mkdir()
                    parent = repo / ".chunkhound"
                    external = root / f"{case}-external"
                    if case == "parent-file":
                        parent.write_bytes(b"immutable parent\n")
                    elif case == "parent-symlink":
                        external.mkdir()
                        parent.symlink_to(external, target_is_directory=True)
                    else:
                        parent.mkdir()
                        log = parent / "daemon.log"
                        if case == "regular-log":
                            log.write_bytes(b"immutable diagnostics\n")
                        else:
                            external.write_bytes(b"immutable target\n")
                            log.symlink_to(external)
                    before = {
                        path.relative_to(repo).as_posix(): (
                            path.lstat().st_mode,
                            path.read_bytes() if path.is_file() and not path.is_symlink() else None,
                            os.readlink(path) if path.is_symlink() else None,
                        )
                        for path in sorted(repo.rglob("*"))
                    }

                    with self.assertRaises(lifecycle.ExpectedSessionReadinessError):
                        precondition(repo_path=repo)

                    after = {
                        path.relative_to(repo).as_posix(): (
                            path.lstat().st_mode,
                            path.read_bytes() if path.is_file() and not path.is_symlink() else None,
                            os.readlink(path) if path.is_symlink() else None,
                        )
                        for path in sorted(repo.rglob("*"))
                    }
                    self.assertEqual(after, before)
                    if case == "log-symlink":
                        self.assertEqual(external.read_bytes(), b"immutable target\n")

    def test_build_launch_identity_is_exact_deterministic_and_secret_free(self) -> None:
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            bindir = root / "bin"
            repo.mkdir()
            bindir.mkdir()
            executable = bindir / "chunkhound"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
            config = root / "config.json"
            config.write_text('{"z": 1, "indexing": {"include": ["**/*.py"]}}\n', encoding="utf-8")
            database = root / "index.db"
            database.touch()
            environment = MappingProxyType(
                {"PATH": str(bindir), "TOKEN": "never-store-this-value"}
            )

            identity = lifecycle.build_launch_identity(
                repo_path=repo,
                config_path=config,
                database_path=database,
                cwd=repo,
                binary="chunkhound",
                environment=environment,
            )
            config.write_text(
                '{\n  "indexing": {"include": ["**/*.py"]},\n  "z": 1\n}\n',
                encoding="utf-8",
            )
            equivalent = lifecycle.build_launch_identity(
                repo_path=repo,
                config_path=config,
                database_path=database,
                cwd=repo,
                binary="chunkhound",
                environment=dict(environment),
            )

            self.assertEqual(identity, equivalent)
            self.assertEqual(identity.resolved_executable, executable.resolve())
            self.assertEqual(identity.curated_environment_keys, ("PATH", "TOKEN"))
            self.assertNotIn("never-store-this-value", repr(identity))
            with mock.patch.dict(os.environ, {"PATH": "/ambient-must-not-win"}):
                self.assertEqual(
                    lifecycle.build_launch_identity(
                        repo_path=repo,
                        config_path=config,
                        database_path=database,
                        cwd=repo,
                        binary="chunkhound",
                        environment=environment,
                    ),
                    equivalent,
                )

    def test_final_index_returns_strict_receipt_from_lossless_capture(self) -> None:
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            work = root / "work"
            bindir = root / "bin"
            repo.mkdir()
            work.mkdir()
            bindir.mkdir()
            executable = bindir / "chunkhound"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
            config = work / "chunkhound.json"
            database = work / ".chunkhound.db"
            base_config = root / "base.json"
            config.write_text("{}\n", encoding="utf-8")
            base_config.write_text("{}\n", encoding="utf-8")
            environment = {"PATH": str(bindir), "PYTHONSAFEPATH": "1"}
            observed_capture: list[Any] = []

            class ChunkHoundConfig:
                base_config_path = base_config

            def successful_index(
                cmd: list[str], **kwargs: Any
            ) -> run_module.CommandResult:
                capture = kwargs["lossless_capture"]
                observed_capture.append(capture)
                database.write_bytes(b"indexed")
                capture.write_stdout("progress\nTotal chunks: 7\n")
                capture.write_stderr("Errors: 0 files\n")
                capture.seal()
                return run_module.CommandResult(
                    cmd=cmd,
                    cwd=kwargs["cwd"],
                    exit_code=0,
                    duration_seconds=0.1,
                    stdout="progress\nTotal chunks: 7\n",
                    stderr="Errors: 0 files\n",
                )

            progress = mock.MagicMock()
            progress.meta = {}
            reporter = mock.MagicMock()
            with mock.patch.object(rf, "active_output", return_value=None), mock.patch.object(
                rf, "run_cmd", side_effect=successful_index
            ), mock.patch.object(
                rf, "ChunkhoundLiveProgressReporter", return_value=reporter
            ):
                receipt = rf._run_session_chunkhound_index_with_rebuild_fallback(
                    progress=progress,
                    scope="topup",
                    quiet=True,
                    stream=False,
                    chunkhound_cfg=ChunkHoundConfig(),
                    chunkhound_cfg_path=config,
                    chunkhound_db_path=database,
                    chunkhound_work_dir=work,
                    repo_dir=repo,
                    reuse_source_kind="test",
                    reviewed_head="1" * 40,
                    env=environment,
                )

            self.assertIsInstance(receipt, lifecycle.ExpectedSessionReceiptV1)
            assert receipt is not None
            self.assertEqual(receipt.reviewed_head, "1" * 40)
            self.assertEqual(receipt.total_chunks, 7)
            self.assertEqual(
                receipt.launch_identity_projection.resolved_executable,
                executable.resolve(),
            )
            self.assertEqual(len(observed_capture), 1)
            self.assertEqual(observed_capture[0].state.name, "DISPOSED")
            self.assertEqual(list(work.glob("cure-command-*.spool")), [])
            reporter.finish.assert_called_once_with(status="done")

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux /proc contract")
    def test_observe_native_generation_uses_exact_launch_inputs_and_proc_start(self) -> None:
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc_root = root / "proc"
            (proc_root / "321").mkdir(parents=True)
            fields = ["S"] + [str(value) for value in range(4, 22)] + ["98765"]
            (proc_root / "321" / "stat").write_text(
                "321 (daemon with ) parens) " + " ".join(fields) + "\n",
                encoding="ascii",
            )
            executable = root / "chunkhound"
            executable.write_text("#!/usr/bin/python3\n", encoding="utf-8")
            executable.chmod(0o755)
            env = MappingProxyType({"PATH": "/curated", "MARKER": "exact"})
            with mock.patch.object(
                cure_chunkhound,
                "daemon_metadata_payload",
                return_value={"daemon_pid": 321, "daemon_metadata_error": ""},
            ) as metadata:
                generation = lifecycle.observe_native_daemon_generation(
                    repo_path=root,
                    cwd=root,
                    binary=executable,
                    environment=env,
                    timeout=2.5,
                    proc_root=proc_root,
                )
            self.assertEqual(
                generation,
                lifecycle.DaemonGenerationIdentity(
                    pid=321, process_started_at=98765.0
                ),
            )
            metadata.assert_called_once_with(
                root,
                chunkhound_cwd=root,
                binary=str(executable.resolve()),
                timeout=2.5,
                env=env,
            )

    def test_matches_index_pattern_honors_recursive_root_subtree_globs(self) -> None:
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        cases = (
            (".claude/skills/cure_release/SKILL.md", "**/.claude/**", True),
            (".claude/SKILL.md", "**/.claude/**", True),
            ("pkg/.claude/skills/review/SKILL.md", "**/.claude/**", True),
            ("openspec/initiatives/example/story.md", "**/openspec/**", True),
            ("src/__pycache__/nested/module.pyc", "**/__pycache__/**", True),
            (".claude2/skills/SKILL.md", "**/.claude/**", False),
            ("src/.claude2/SKILL.md", "**/.claude/**", False),
            ("foo/x/bar/file.py", "**/foo*bar/**", False),
            ("foo-bar/nested/file.py", "**/foo*bar/**", True),
            ("src/selected.py", "**/.claude/**", False),
            ("src/selected.py", "**/*.py", True),
            ("foo", "foo/**", False),
            ("foo/child.py", "foo/**", True),
            ("foo/nested/child.py", "foo/**", True),
        )
        for relative_path, pattern, expected in cases:
            with self.subTest(relative_path=relative_path, pattern=pattern):
                self.assertIs(
                    lifecycle._matches_index_pattern(relative_path, pattern),
                    expected,
                )

    def test_matches_index_pattern_handles_deep_components_without_recursion(
        self,
    ) -> None:
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        relative_path = "/".join(["component"] * 1100 + ["leaf.py"])
        self.assertTrue(
            lifecycle._matches_index_pattern(relative_path, "**/leaf.py")
        )
        self.assertFalse(
            lifecycle._matches_index_pattern(relative_path, "**/other.py")
        )

    def test_selector_does_not_treat_terminal_globstar_as_prefix_file(self) -> None:
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "foo").write_text("prefix_file_witness\n", encoding="utf-8")
            (repo / "z.py").write_text("selected_witness = 1\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(repo), "add", "foo", "z.py"], check=True
            )
            config = repo / "chunkhound.json"
            config.write_text(
                json.dumps(
                    {"indexing": {"include": ["foo/**", "**/*.py"]}}
                ),
                encoding="utf-8",
            )

            witness = lifecycle.select_git_tracked_source_witness(
                repo_path=repo,
                config_path=config,
                max_tracked_paths=8,
                max_candidates=4,
                max_file_bytes=1024,
                max_tokens_per_file=8,
            )

        self.assertEqual(witness.relative_path, "z.py")
        self.assertEqual(witness.literal, "selected_witness")

    def test_selector_skips_lexically_first_excluded_recursive_root_subtree(
        self,
    ) -> None:
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            excluded = repo / ".claude" / "skills" / "cure_release" / "SKILL.md"
            excluded.parent.mkdir(parents=True)
            excluded.write_text("excluded_witness\n", encoding="utf-8")
            selected = repo / "src" / "selected.py"
            selected.parent.mkdir()
            selected.write_text("selected_witness = 1\n", encoding="utf-8")
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "add",
                    ".claude/skills/cure_release/SKILL.md",
                    "src/selected.py",
                ],
                check=True,
            )
            config = repo / "chunkhound.json"
            config.write_text(
                json.dumps(
                    {
                        "indexing": {
                            "include": ["**/*.md", "**/*.py"],
                            "exclude": ["**/.claude/**"],
                        }
                    }
                ),
                encoding="utf-8",
            )

            witness = lifecycle.select_git_tracked_source_witness(
                repo_path=repo,
                config_path=config,
                max_tracked_paths=8,
                max_candidates=4,
                max_file_bytes=1024,
                max_tokens_per_file=8,
            )

        self.assertEqual(witness.relative_path, "src/selected.py")
        self.assertEqual(witness.literal, "selected_witness")

    def test_select_git_tracked_source_witness_is_bounded_and_honors_policy(self) -> None:
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "src").mkdir()
            (repo / "docs").mkdir()
            (repo / "src" / "a.py").write_text(
                "excluded_identifier = 1\n", encoding="utf-8"
            )
            (repo / "src" / "b.py").write_text(
                "selected_identifier = 2\n", encoding="utf-8"
            )
            (repo / "docs" / "guide.md").write_text(
                "documentation_identifier\n", encoding="utf-8"
            )
            (repo / "untracked.py").write_text(
                "untracked_identifier = 3\n", encoding="utf-8"
            )
            subprocess.run(
                ["git", "-C", str(repo), "add", "src/a.py", "src/b.py", "docs/guide.md"],
                check=True,
            )
            config = repo / "chunkhound.json"
            config.write_text(
                json.dumps(
                    {
                        "indexing": {
                            "include": ["**/*.py"],
                            "exclude": ["src/a.py"],
                        }
                    }
                ),
                encoding="utf-8",
            )

            witness = lifecycle.select_git_tracked_source_witness(
                repo_path=repo,
                config_path=config,
                max_tracked_paths=16,
                max_candidates=4,
                max_file_bytes=1024,
                max_tokens_per_file=8,
            )
            self.assertEqual(witness.relative_path, "src/b.py")
            self.assertEqual(witness.literal, "selected_identifier")

            with self.assertRaises(lifecycle.SourceWitnessSelectionError):
                lifecycle.select_git_tracked_source_witness(
                    repo_path=repo,
                    config_path=config,
                    max_tracked_paths=1,
                    max_candidates=4,
                    max_file_bytes=1024,
                    max_tokens_per_file=8,
                )

    def test_select_git_tracked_source_witness_honors_gitignore_only_exclude_mode(
        self,
    ) -> None:
        lifecycle = importlib.import_module("cure_chunkhound_lifecycle")
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            # a_ignored.txt sorts first, is tracked, and is matched by an
            # UNTRACKED working-tree .gitignore (gitignore rules apply to the
            # working tree whether or not the .gitignore itself is tracked;
            # leaving it untracked keeps it out of the candidate listing).
            (repo / "a_ignored.txt").write_text(
                "ignored_witness = 1\n", encoding="utf-8"
            )
            (repo / "kept.py").write_text(
                "selected_witness = 2\n", encoding="utf-8"
            )
            subprocess.run(
                ["git", "-C", str(repo), "add", "a_ignored.txt", "kept.py"],
                check=True,
            )
            # Ignore rules written AFTER tracking: tracked files stay in the
            # index even when .gitignore later matches them (the exact
            # production failure mode). The .gitignore itself stays untracked
            # to keep it out of the candidate listing.
            (repo / ".gitignore").write_text(
                "a_ignored.txt\n", encoding="utf-8"
            )

            def select(exclude_mode: str | None) -> "object":
                config = repo / "chunkhound.json"
                indexing: dict[str, object] = {
                    "include": ["**/*.txt", "**/*.py"],
                }
                if exclude_mode is not None:
                    indexing["exclude_mode"] = exclude_mode
                config.write_text(
                    json.dumps({"indexing": indexing}), encoding="utf-8"
                )
                return lifecycle.select_git_tracked_source_witness(
                    repo_path=repo,
                    config_path=config,
                    max_tracked_paths=16,
                    max_candidates=4,
                    max_file_bytes=1024,
                    max_tokens_per_file=8,
                )

            # (a) gitignore_only: the tracked-but-ignored candidate is skipped.
            witness = select("gitignore_only")
            self.assertEqual(witness.relative_path, "kept.py")
            self.assertEqual(witness.literal, "selected_witness")

            # (b) default mode: the ignored candidate remains selectable,
            # because the daemon indexes tracked files regardless of gitignore.
            witness = select(None)
            self.assertEqual(witness.relative_path, "a_ignored.txt")
            self.assertEqual(witness.literal, "ignored_witness")

            # (c) all candidates gitignored -> clear selection failure.
            (repo / ".gitignore").write_text("*\n", encoding="utf-8")
            with self.assertRaises(lifecycle.SourceWitnessSelectionError):
                select("gitignore_only")
