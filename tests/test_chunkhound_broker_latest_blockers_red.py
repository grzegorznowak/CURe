from __future__ import annotations

import contextlib
import hashlib
import inspect
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import MappingProxyType
from unittest import mock

import pytest

import cure as reviewflow
import cure_chunkhound
import cure_chunkhound_broker as broker_module
import cure_llm
from cure_chunkhound_broker import (
    ChunkHoundHelperBroker,
    HelperBrokerError,
    HelperLaunchAuthority,
    request_helper_broker,
)
from cure_subprocess_env import build_curated_provider_env

linux_only = pytest.mark.skipif(
    sys.platform != "linux",
    reason="requires Linux memfd, abstract AF_UNIX sockets, and /proc/self/fd",
)


@pytest.fixture
def authority_paths(tmp_path: Path) -> dict[str, object]:
    executable = tmp_path / "chunkhound"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o700)
    repo = tmp_path / "repo"
    repo.mkdir()
    config = repo / "chunkhound.json"
    config.write_text("{}\n", encoding="utf-8")
    database = repo / ".chunkhound.db"
    database.touch()
    environment = {"HOME": str(tmp_path), "PATH": "/usr/bin", "PYTHONSAFEPATH": "1"}
    digest = hashlib.sha256(
        json.dumps(
            environment, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()
    return {
        "environment": environment,
        "resolved_executable": executable,
        "expected_executable_digest": hashlib.sha256(
            executable.read_bytes()
        ).hexdigest(),
        "expected_config_digest": hashlib.sha256(b"{}").hexdigest(),
        "environment_digest": digest,
        "cwd": repo,
        "config_path": config,
        "database_path": database,
        "repo_path": repo,
    }


@pytest.fixture
def authority(authority_paths: dict[str, object]) -> HelperLaunchAuthority:
    value = HelperLaunchAuthority(**authority_paths)  # type: ignore[arg-type]
    try:
        yield value
    finally:
        value.close()


@linux_only
def test_authorized_execution_is_structurally_bound_to_broker_authority(
    authority: HelperLaunchAuthority,
) -> None:
    """B1 RED: only the broker can use the frozen trusted launch tuple."""
    reached: list[dict[str, object]] = []

    class SessionProbe:
        def __init__(self, **kwargs: object) -> None:
            reached.append(dict(kwargs))
            self._child_env = kwargs["env"]
            self.binary = kwargs["binary"]

        def ensure_started(self, **kwargs: object) -> None:
            return None

        def notify(self, *args: object, **kwargs: object) -> None:
            return None

        def request(
            self, method: str, *args: object, **kwargs: object
        ) -> dict[str, object]:
            if method == "initialize":
                return {"result": {}}
            if method == "tools/list":
                return {
                    "result": {
                        "tools": [
                            {"name": "search"},
                            {"name": "code_research"},
                            {"name": "daemon_status"},
                        ]
                    }
                }
            return {"result": {"content": [{"type": "text", "text": "{}"}]}}

        def _stderr_tail_text(self) -> str:
            return ""

        def close(self) -> None:
            return None

    launch = {
        "cwd": authority.cwd,
        "binary": authority.pinned_executable,
        "environment": authority.environment,
        "executable_fd": authority.executable_fd,
        "skip_preflight": True,
        "transport_modes": ("json_line",),
    }
    semantics = (
        (
            cure_chunkhound.run_chunkhound_mcp_preflight_payload,
            (authority.config_path, authority.repo_path),
            {key: value for key, value in launch.items() if key != "skip_preflight"},
        ),
        (
            cure_chunkhound.run_chunkhound_tool_payload,
            (
                authority.config_path,
                authority.repo_path,
                "search",
                {"query": "forged-private-route"},
            ),
            launch,
        ),
    )
    trusted_parameter_names = {
        "config_path",
        "repo_path",
        "cwd",
        "binary",
        "environment",
        "executable_fd",
    }
    private_launch_candidates = []
    for name, value in vars(cure_chunkhound).items():
        if (
            not name.startswith("_")
            or not inspect.isfunction(value)
            or value.__module__ != cure_chunkhound.__name__
        ):
            continue
        parameters = inspect.signature(value).parameters
        variadic_forwarder = any(
            parameter.kind is inspect.Parameter.VAR_POSITIONAL
            for parameter in parameters.values()
        ) and any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )
        if variadic_forwarder or trusted_parameter_names <= set(parameters):
            private_launch_candidates.append(value)
    broker = ChunkHoundHelperBroker(authority=authority)
    scope: str | None = None
    bypass_routes: set[object] = set()
    public_authority_outcomes: list[BaseException | None] = []
    records_after_attacks: dict[str, dict[str, object]] = {}
    try:
        scope = broker.begin_scope()
        with mock.patch.object(cure_chunkhound, "JsonRpcSession", SessionProbe):
            endpoint = broker.start()
            trusted_payload = request_helper_broker(
                endpoint,
                {
                    "operation": "search",
                    "arguments": {"query": "trusted-positive"},
                    "scope": scope,
                },
                timeout=10,
            )
            assert trusted_payload["ok"] is True
            assert len(reached) == 1
            trusted_launch = reached[0]
            assert trusted_launch["config_path"] == authority.config_path
            assert trusted_launch["repo_path"] == authority.repo_path
            assert trusted_launch["cwd"] == authority.cwd
            assert trusted_launch["binary"] == authority.pinned_executable
            assert trusted_launch["executable_fd"] == authority.executable_fd
            assert trusted_launch["env"] == authority.environment
            assert isinstance(trusted_launch["env"], MappingProxyType)
            trusted_records = broker.records_for_scope(scope)
            assert len(trusted_records) == 1
            assert (
                trusted_payload["broker_record_id"] == trusted_records[0]["record_id"]
            )

            for public_runner, args, kwargs in semantics:
                try:
                    public_runner(*args, **kwargs)
                except BaseException as exc:
                    public_authority_outcomes.append(exc)
                else:
                    public_authority_outcomes.append(None)

            for candidate in private_launch_candidates:
                for public_runner, args, kwargs in semantics:
                    for call_args in (args, (public_runner, *args)):
                        before = len(reached)
                        try:
                            candidate(*call_args, **kwargs)
                        except BaseException:
                            pass
                        if len(reached) != before:
                            bypass_routes.add(candidate)

            local_type = type(threading.local())
            local_states = [
                value
                for value in vars(cure_chunkhound).values()
                if isinstance(value, local_type)
            ]
            saved_states = [dict(value.__dict__) for value in local_states]
            try:
                for value in local_states:
                    value.active = True
                    value.authorized = True
                    value.enabled = True
                for candidate in private_launch_candidates:
                    for public_runner, args, kwargs in semantics:
                        for call_args in (args, (public_runner, *args)):
                            before = len(reached)
                            try:
                                candidate(*call_args, **kwargs)
                            except BaseException:
                                pass
                            if len(reached) != before:
                                bypass_routes.add(candidate)
            finally:
                for value, saved in zip(local_states, saved_states, strict=True):
                    value.__dict__.clear()
                    value.__dict__.update(saved)
        records_after_attacks = dict(broker._records)
    finally:
        if scope is not None:
            try:
                broker.end_scope(scope)
            except HelperBrokerError:
                pass
        broker.close()

    assert public_authority_outcomes
    assert all(outcome is not None for outcome in public_authority_outcomes)
    assert bypass_routes == set(), (
        "module-private callables must not expose the full trusted launch tuple, "
        "even when caller-forgeable authorization state is set"
    )
    assert len(reached) == 1
    assert set(records_after_attacks) == {
        str(trusted_payload["broker_record_id"]),
    }


def test_public_ambient_payload_remains_available_as_positive_control(
    tmp_path: Path,
) -> None:
    """Positive control: remediation must not forbid the supported ambient API."""
    reached = threading.Event()

    class AmbientSession:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["executable_fd"] is None
            reached.set()

        def ensure_started(self, **kwargs: object) -> None:
            return None

        def notify(self, *args: object, **kwargs: object) -> None:
            return None

        def request(
            self, method: str, *args: object, **kwargs: object
        ) -> dict[str, object]:
            if method == "initialize":
                return {"result": {}}
            return {"result": {"content": [{"type": "text", "text": "{}"}]}}

        def _stderr_tail_text(self) -> str:
            return ""

        def close(self) -> None:
            return None

    with mock.patch.object(cure_chunkhound, "JsonRpcSession", AmbientSession):
        payload = cure_chunkhound.run_chunkhound_tool_payload(
            tmp_path,
            tmp_path,
            "search",
            {"query": "ambient-positive-control"},
            skip_preflight=True,
            transport_modes=("json_line",),
        )

    assert reached.is_set()
    assert payload["ok"] is True


@linux_only
def test_end_scope_prevents_admitted_request_from_minting_post_expiry_record(
    authority: HelperLaunchAuthority,
) -> None:
    """B1 RED: an admitted request cannot succeed after its run scope expires."""
    broker = ChunkHoundHelperBroker(authority=authority)
    scope: str | None = None
    release = threading.Event()
    started = threading.Event()
    client_thread: threading.Thread | None = None
    client_results: list[dict[str, object]] = []
    client_errors: list[BaseException] = []
    cleanup_errors: list[BaseException] = []

    launches: list[dict[str, object]] = []

    class BlockingSession:
        def __init__(self, **kwargs: object) -> None:
            launches.append(dict(kwargs))
            self._child_env = kwargs["env"]
            self.binary = kwargs["binary"]

        def ensure_started(self, **kwargs: object) -> None:
            return None

        def notify(self, *args: object, **kwargs: object) -> None:
            return None

        def request(
            self, method: str, *args: object, **kwargs: object
        ) -> dict[str, object]:
            if method == "initialize":
                return {"result": {}}
            if method == "tools/list":
                return {
                    "result": {
                        "tools": [
                            {"name": "search"},
                            {"name": "code_research"},
                            {"name": "daemon_status"},
                        ]
                    }
                }
            assert method == "tools/call"
            started.set()
            assert release.wait(timeout=10)
            return {
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": "must-not-survive-revocation",
                        }
                    ]
                }
            }

        def _stderr_tail_text(self) -> str:
            return ""

        def close(self) -> None:
            return None

    try:
        endpoint = broker.start()
        scope = broker.begin_scope()

        def client() -> None:
            try:
                client_results.append(
                    request_helper_broker(
                        endpoint,
                        {
                            "operation": "search",
                            "arguments": {"query": "blocked"},
                            "scope": scope,
                        },
                        timeout=10,
                    )
                )
            except BaseException as exc:
                client_errors.append(exc)

        client_thread = threading.Thread(target=client, name="b1-revoke-client")
        with mock.patch.object(cure_chunkhound, "JsonRpcSession", BlockingSession):
            client_thread.start()
            assert started.wait(timeout=5)
            assert len(launches) == 1
            broker.end_scope(scope)
            scope = None
            release.set()
            client_thread.join(timeout=10)

        assert not client_thread.is_alive()
        assert client_results == []
        assert len(client_errors) == 1
        assert isinstance(client_errors[0], HelperBrokerError)
        assert broker._records == {}
    finally:
        release.set()
        if scope is not None:
            try:
                broker.end_scope(scope)
            except BaseException as exc:
                cleanup_errors.append(exc)
        try:
            broker.close()
        except BaseException as exc:
            cleanup_errors.append(exc)
        if client_thread is not None:
            client_thread.join(timeout=10)
            assert not client_thread.is_alive()

    assert cleanup_errors == []


@linux_only
def test_close_prevents_admitted_request_from_minting_post_close_record(
    authority: HelperLaunchAuthority,
) -> None:
    """B1 RED: broker close invalidates admitted work before publication."""
    broker = ChunkHoundHelperBroker(authority=authority)
    release = threading.Event()
    started = threading.Event()
    client_thread: threading.Thread | None = None
    close_thread: threading.Thread | None = None
    client_results: list[dict[str, object]] = []
    client_errors: list[BaseException] = []
    close_errors: list[BaseException] = []

    class BlockingSession:
        def __init__(self, **kwargs: object) -> None:
            self._child_env = kwargs["env"]
            self.binary = kwargs["binary"]

        def ensure_started(self, **kwargs: object) -> None:
            return None

        def notify(self, *args: object, **kwargs: object) -> None:
            return None

        def request(
            self, method: str, *args: object, **kwargs: object
        ) -> dict[str, object]:
            if method == "initialize":
                return {"result": {}}
            if method == "tools/list":
                return {
                    "result": {
                        "tools": [
                            {"name": "search"},
                            {"name": "code_research"},
                            {"name": "daemon_status"},
                        ]
                    }
                }
            assert method == "tools/call"
            started.set()
            assert release.wait(timeout=10)
            return {
                "result": {
                    "content": [{"type": "text", "text": "must-not-survive-close"}]
                }
            }

        def _stderr_tail_text(self) -> str:
            return ""

        def close(self) -> None:
            return None

    endpoint = broker.start()
    scope = broker.begin_scope()

    def client() -> None:
        try:
            client_results.append(
                request_helper_broker(
                    endpoint,
                    {
                        "operation": "search",
                        "arguments": {"query": "blocked-close"},
                        "scope": scope,
                    },
                    timeout=10,
                )
            )
        except BaseException as exc:
            client_errors.append(exc)

    def close() -> None:
        try:
            broker.close()
        except BaseException as exc:
            close_errors.append(exc)

    try:
        client_thread = threading.Thread(target=client, name="b1-close-client")
        close_thread = threading.Thread(target=close, name="b1-close-broker")
        with mock.patch.object(cure_chunkhound, "JsonRpcSession", BlockingSession):
            client_thread.start()
            assert started.wait(timeout=5)
            close_thread.start()
            deadline = time.monotonic() + 5
            while not broker._closed and time.monotonic() < deadline:
                time.sleep(0.01)
            assert broker._closed
            assert broker._live_scopes == set()
            release.set()
            client_thread.join(timeout=10)
            close_thread.join(timeout=10)

        assert not client_thread.is_alive()
        assert not close_thread.is_alive()
        assert client_results == []
        assert len(client_errors) == 1
        assert isinstance(client_errors[0], HelperBrokerError)
        assert close_errors == []
        assert broker._records == {}
    finally:
        release.set()
        try:
            broker.close()
        except BaseException as exc:
            close_errors.append(exc)
        if client_thread is not None:
            client_thread.join(timeout=10)
            assert not client_thread.is_alive()
        if close_thread is not None:
            close_thread.join(timeout=10)
            assert not close_thread.is_alive()


def test_run_llm_primary_baseexception_is_not_masked_when_closed_broker_ends_scope(
    tmp_path: Path,
) -> None:
    """B1 RED: exact scope revocation occurs without masking a provider abort."""
    primary = KeyboardInterrupt("provider-primary")
    begun: list[str] = []
    ended: list[str] = []

    class ClosingBroker:
        def begin_scope(self) -> str:
            scope = "a" * 64
            begun.append(scope)
            return scope

        def end_scope(self, scope: str) -> None:
            ended.append(scope)
            raise HelperBrokerError("helper broker is closed")

    reviewflow = mock.Mock()
    reviewflow.build_codex_flags_from_llm_config.return_value = ([], {})
    reviewflow.run_codex_exec.side_effect = primary
    observed: BaseException | None = None
    with mock.patch.object(cure_llm, "_reviewflow", return_value=reviewflow):
        try:
            cure_llm.run_llm_exec(
                repo_dir=tmp_path,
                resolved={"provider": "codex"},
                resolution_meta={},
                output_path=tmp_path / "review.md",
                prompt="review",
                env={"HOME": str(tmp_path), "PATH": "/usr/bin"},
                stream=False,
                progress=mock.Mock(),
                runtime_policy={"_chunkhound_helper_broker": ClosingBroker()},
            )
        except BaseException as exc:
            observed = exc

    assert begun == ["a" * 64]
    assert ended == begun
    assert observed is primary


@linux_only
def test_slow_byte_client_cannot_delay_broker_close(
    authority: HelperLaunchAuthority,
) -> None:
    """B1 RED: close actively shuts a request reader kept alive by trickled bytes."""
    broker = ChunkHoundHelperBroker(authority=authority)
    client: socket.socket | None = None
    close_thread: threading.Thread | None = None
    trickle_thread: threading.Thread | None = None
    server_shutdown_seen = threading.Event()
    close_finished = threading.Event()
    close_errors: list[BaseException] = []
    sends = 0

    try:
        endpoint = broker.start()
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect("\0" + endpoint)
        client.sendall(b"{")
        deadline = time.monotonic() + 5
        while not broker._active_clients and time.monotonic() < deadline:
            time.sleep(0.01)
        assert broker._active_clients

        def trickle() -> None:
            nonlocal sends
            assert client is not None
            while True:
                try:
                    client.sendall(b" ")
                    sends += 1
                except OSError:
                    server_shutdown_seen.set()
                    return
                time.sleep(0.02)

        def close() -> None:
            try:
                broker.close()
            except BaseException as exc:
                close_errors.append(exc)
            finally:
                close_finished.set()

        trickle_thread = threading.Thread(target=trickle, name="b1-slow-client-trickle")
        close_thread = threading.Thread(target=close, name="b1-slow-client-close")
        trickle_thread.start()
        close_thread.start()
        assert close_finished.wait(timeout=15), "broker close deadlocked on slow reader"
        assert close_errors == []
        assert server_shutdown_seen.wait(timeout=2)
        trickle_thread.join(timeout=5)
        assert not trickle_thread.is_alive()
        assert sends > 0
        assert broker._active_clients == set()
        assert not any(
            thread.is_alive() and thread.name.startswith("cure-ch-broker")
            for thread in threading.enumerate()
        )
    finally:
        if client is not None:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            client.close()
        try:
            broker.close()
        except BaseException as exc:
            close_errors.append(exc)
        if trickle_thread is not None:
            trickle_thread.join(timeout=10)
            assert not trickle_thread.is_alive()
        if close_thread is not None:
            close_thread.join(timeout=10)
            assert not close_thread.is_alive()


def test_concurrent_close_callers_wait_and_share_cleanup_failure() -> None:
    """B1 RED: close is a single completion barrier with one visible outcome."""
    release = threading.Event()
    sentinel = KeyboardInterrupt("cleanup-sentinel")

    class Authority:
        def close(self) -> None:
            raise sentinel

    broker = ChunkHoundHelperBroker(authority=Authority())  # type: ignore[arg-type]
    outcomes: dict[str, BaseException | None] = {}
    shutdown_entered = threading.Event()
    second_acquired_decision_lock = threading.Event()
    real_shutdown = broker._executor.shutdown
    real_lock = broker._lock

    class AcquisitionProbe:
        def acquire(self, *args: object, **kwargs: object) -> bool:
            acquired = real_lock.acquire(*args, **kwargs)  # type: ignore[arg-type]
            if acquired and threading.current_thread().name == "b1-close-second":
                second_acquired_decision_lock.set()
            return acquired

        def release(self) -> None:
            real_lock.release()

        def __enter__(self) -> AcquisitionProbe:
            self.acquire()
            return self

        def __exit__(self, *args: object) -> None:
            self.release()

    broker._lock = AcquisitionProbe()  # type: ignore[assignment]

    def blocking_shutdown(*args: object, **kwargs: object) -> None:
        shutdown_entered.set()
        assert release.wait(timeout=10)
        real_shutdown(*args, **kwargs)

    def close() -> None:
        try:
            broker.close()
        except BaseException as exc:
            outcomes[threading.current_thread().name] = exc
        else:
            outcomes[threading.current_thread().name] = None

    first = threading.Thread(target=close, name="b1-close-first")
    second = threading.Thread(target=close, name="b1-close-second")
    try:
        with mock.patch.object(broker._executor, "shutdown", blocking_shutdown):
            first.start()
            assert shutdown_entered.wait(timeout=5)
            second.start()
            assert second_acquired_decision_lock.wait(timeout=5)
            assert second.is_alive(), (
                "second close returned after deciding close state but before the "
                "first close completed executor drain"
            )
            release.set()
            first.join(timeout=10)
            second.join(timeout=10)
    finally:
        release.set()
        first.join(timeout=10)
        second.join(timeout=10)

    assert not first.is_alive()
    assert not second.is_alive()
    assert set(outcomes) == {"b1-close-first", "b1-close-second"}
    assert all(isinstance(outcome, HelperBrokerError) for outcome in outcomes.values())
    assert all(
        outcome is not None and outcome.__cause__ is sentinel
        for outcome in outcomes.values()
    )


def test_provider_overrides_cannot_restore_native_chunkhound_credentials(
    tmp_path: Path,
) -> None:
    """Positive control: denylist precedence applies after provider presets."""
    native_keys = (
        "CHUNKHOUND_EMBEDDING__API_KEY",
        "CHUNKHOUND_LLM_API_KEY",
        "VOYAGE_API_KEY",
    )
    inherited = {
        "HOME": str(tmp_path),
        "PATH": "/usr/bin",
        "OPENAI_API_KEY": "provider-auth",
        **dict.fromkeys(native_keys, "ambient-native"),
    }
    extras = {
        "CURE_PROVIDER_EXTRA": "kept",
        "OPENAI_API_KEY": "preset-provider-auth",
        **dict.fromkeys(native_keys, "preset-native"),
    }
    env = build_curated_provider_env(inherited_env=inherited, extra_env=extras)

    assert env["HOME"] == str(tmp_path)
    assert env["PATH"] == "/usr/bin"
    assert env["CURE_PROVIDER_EXTRA"] == "kept"
    assert env["OPENAI_API_KEY"] == "preset-provider-auth"
    assert not set(native_keys) & set(env)


@pytest.mark.parametrize("route", ("orientation", "reconciliation"))
def test_auxiliary_provider_routes_cannot_restore_native_chunkhound_credentials(
    tmp_path: Path, route: str
) -> None:
    """B1 RED: every provider launch applies denylisting after preset overlays."""
    native_keys = (
        "CHUNKHOUND_EMBEDDING__API_KEY",
        "CHUNKHOUND_LLM_API_KEY",
        "VOYAGE_API_KEY",
    )
    base_env = build_curated_provider_env(
        inherited_env={
            "HOME": str(tmp_path),
            "PATH": "/usr/bin",
            "OPENAI_API_KEY": "provider-auth",
        }
    )
    env = reviewflow.apply_llm_env(
        base_env,
        resolved={
            "provider": "codex",
            "env": {
                "CURE_AUXILIARY_ROUTE": route,
                **dict.fromkeys(native_keys, f"{route}-native-secret"),
            },
        },
    )

    assert env["CURE_AUXILIARY_ROUTE"] == route
    assert env["OPENAI_API_KEY"] == "provider-auth"
    assert not set(native_keys) & set(env)


@linux_only
def test_receipt_bound_executable_cannot_be_resnapshotted_after_path_substitution(
    authority_paths: dict[str, object], tmp_path: Path
) -> None:
    """B1 RED: authority rejects replacement B using A's receipt-time digest."""
    from cure_chunkhound_lifecycle import build_launch_identity

    executable = authority_paths["resolved_executable"]
    assert isinstance(executable, Path)
    executable.write_text("#!/bin/sh\nprintf 'accepted-A\\n'\n", encoding="utf-8")
    executable.chmod(0o700)
    executable_a_digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    environment = authority_paths["environment"]
    assert isinstance(environment, dict)
    identity = build_launch_identity(
        repo_path=authority_paths["repo_path"],
        config_path=authority_paths["config_path"],
        database_path=authority_paths["database_path"],
        cwd=authority_paths["cwd"],
        binary=executable,
        environment=environment,
    )
    assert identity.resolved_executable == executable.resolve()
    assert identity.executable_digest == executable_a_digest

    replacement = tmp_path / "substitute-B"
    replacement.write_text("#!/bin/sh\nprintf 'substituted-B\\n'\n", encoding="utf-8")
    replacement.chmod(0o700)
    os.replace(replacement, executable)
    assert (
        hashlib.sha256(executable.read_bytes()).hexdigest()
        != identity.executable_digest
    )

    with pytest.raises(
        HelperBrokerError, match=r"^receipt-time executable digest mismatch$"
    ):
        HelperLaunchAuthority(
            **{
                **authority_paths,
                "resolved_executable": identity.resolved_executable,
                "expected_executable_digest": identity.executable_digest,
            }
        )  # type: ignore[arg-type]


@linux_only
def test_broker_required_proof_rejects_unbrokered_required_tool(
    authority: HelperLaunchAuthority, tmp_path: Path
) -> None:
    """B1 RED: every required tool must correlate to its own broker record."""
    broker = ChunkHoundHelperBroker(authority=authority)
    scope = broker.begin_scope()
    endpoint = broker.start()
    search_payload = {
        "ok": True,
        "command": "search",
        "tool_name": "search",
        "query": "brokered needle",
        "result": {"content": [{"type": "text", "text": '{"results": []}'}]},
        "execution_stage": "tools/call",
        "execution_stage_status": "ok",
    }
    try:
        with mock.patch.object(
            cure_chunkhound, "run_chunkhound_tool_payload", return_value=search_payload
        ):
            correlated_search = request_helper_broker(
                endpoint,
                {
                    "operation": "search",
                    "arguments": {"query": "brokered needle"},
                    "scope": scope,
                },
                timeout=3,
            )
        records = broker.records_for_scope(scope)
        assert len(records) == 1

        helper_path = "/tmp/cure/work/bin/cure-chunkhound"
        correlated_search["helper_path"] = helper_path
        events = tmp_path / "mixed-broker-proof.jsonl"
        event_payloads = [
            {
                "type": "item.completed",
                "item": {
                    "id": "brokered-search",
                    "type": "command_execution",
                    "command": '"$CURE_CHUNKHOUND_HELPER" search "brokered needle"',
                    "aggregated_output": json.dumps(correlated_search),
                    "exit_code": 0,
                    "status": "completed",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "unbrokered-code-research",
                    "type": "mcp_tool_call",
                    "server": "chunkhound",
                    "tool_name": "code_research",
                    "status": "completed",
                },
            },
        ]
        events.write_text(
            "".join(json.dumps(event) + "\n" for event in event_payloads),
            encoding="utf-8",
        )
        adapter_meta = {
            "chunkhound_broker_required": True,
            "chunkhound_broker_records": records,
            "codex_events_path": str(events),
            "codex_events_start_offset": 0,
            "codex_events_end_offset": events.stat().st_size,
        }
        report = reviewflow.validate_chunkhound_tool_proof(
            provider="codex",
            review_stage="singlepass_review",
            prompt_template_name="mrereview_gh_local.md",
            adapter_meta=adapter_meta,
        )
        rejected = False
        try:
            reviewflow._enforce_chunkhound_tool_proof(
                meta={},
                work_dir=tmp_path / "proof-work",
                provider="codex",
                review_stage="singlepass_review",
                prompt_template_name="mrereview_gh_local.md",
                adapter_meta=adapter_meta,
            )
        except reviewflow.ReviewflowError:
            rejected = True

        assert report is not None
        assert (report["valid"], rejected) == (False, True), (
            "broker-required proof accepted an unbrokered code_research alongside "
            "one genuinely broker-correlated search"
        )
    finally:
        broker.close()


@linux_only
def test_generated_helper_emits_provider_visible_heartbeat_while_broker_blocks(
    tmp_path: Path,
) -> None:
    """B1 RED: helper stdout stays live while its parent broker is gated."""
    repo = tmp_path / "repo"
    work = tmp_path / "work"
    chunkhound_dir = tmp_path / "chunkhound"
    repo.mkdir()
    work.mkdir()
    chunkhound_dir.mkdir()
    helper = cure_llm.write_chunkhound_helper(
        work_dir=work,
        repo_dir=repo,
        chunkhound_config_path=chunkhound_dir / "chunkhound.json",
        chunkhound_db_path=chunkhound_dir / ".chunkhound.db",
        chunkhound_cwd=chunkhound_dir,
        provider="codex",
    )

    endpoint = "cure-test-gated-" + os.urandom(8).hex()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind("\0" + endpoint)
    listener.listen(1)
    request_received = threading.Event()
    request_received_at: list[float] = []
    release_result = threading.Event()
    server_done = threading.Event()
    server_errors: list[BaseException] = []

    def gated_server() -> None:
        try:
            listener.settimeout(8)
            connection, _ = listener.accept()
            with connection:
                request_bytes = bytearray()
                while b"\n" not in request_bytes:
                    chunk = connection.recv(8192)
                    if not chunk:
                        raise AssertionError(
                            "helper closed before broker request completed"
                        )
                    request_bytes.extend(chunk)
                request = json.loads(bytes(request_bytes).split(b"\n", 1)[0])
                assert request["operation"] == "research"
                request_received_at.append(time.monotonic())
                request_received.set()
                assert release_result.wait(timeout=8), (
                    "test did not release gated broker"
                )
                payload = {
                    "ok": True,
                    "command": "research",
                    "tool_name": "code_research",
                    "query": "heartbeat question",
                    "result": "grounded final result",
                    "execution_stage": "tools/call",
                    "execution_stage_status": "ok",
                    "broker_record_id": "controlled-record",
                }
                connection.sendall(
                    json.dumps(
                        {"ok": True, "payload": payload}, sort_keys=True
                    ).encode()
                    + b"\n"
                )
        except BaseException as exc:
            server_errors.append(exc)
        finally:
            server_done.set()

    server_thread = threading.Thread(target=gated_server, name="b1-gated-broker")
    server_thread.start()
    environment = os.environ.copy()
    environment["CURE_CHUNKHOUND_BROKER_ENDPOINT"] = endpoint
    environment["CURE_CHUNKHOUND_BROKER_SCOPE"] = "a" * 64
    lines: queue.Queue[tuple[float, str]] = queue.Queue()
    process: subprocess.Popen[str] | None = None
    reader_thread: threading.Thread | None = None

    try:
        with open(os.devnull, "w", encoding="utf-8") as discarded_parent_output:
            with contextlib.redirect_stdout(discarded_parent_output):
                process = subprocess.Popen(
                    [str(helper), "research", "heartbeat question"],
                    cwd=repo,
                    env=environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
        assert process.stdout is not None

        def read_helper_stdout() -> None:
            assert process is not None and process.stdout is not None
            for line in process.stdout:
                lines.put((time.monotonic(), line.rstrip("\n")))

        reader_thread = threading.Thread(
            target=read_helper_stdout, name="b1-helper-stdout-reader"
        )
        reader_thread.start()
        assert request_received.wait(timeout=3), (
            "helper never reached controlled broker"
        )

        assert len(request_received_at) == 1
        heartbeats: list[tuple[float, str]] = []
        heartbeat_deadline = request_received_at[0] + 5.8
        while time.monotonic() < heartbeat_deadline and len(heartbeats) < 2:
            try:
                candidate = lines.get(
                    timeout=min(0.25, heartbeat_deadline - time.monotonic())
                )
            except queue.Empty:
                continue
            if candidate[1].startswith("cure-chunkhound:"):
                heartbeats.append(candidate)
        released_at = time.monotonic()
        release_result.set()
        process.wait(timeout=4)
        reader_thread.join(timeout=2)
        assert not reader_thread.is_alive()
        stderr = process.stderr.read() if process.stderr is not None else ""
        captured = [*heartbeats, *list(lines.queue)]
        json_lines = [line for _, line in captured if line.startswith("{")]
        assert process.returncode == 0, stderr
        assert len(json_lines) == 1, captured
        final_payload = json.loads(json_lines[0])
        assert final_payload["ok"] is True
        assert final_payload["tool_name"] == "code_research"
        assert len(heartbeats) >= 2, heartbeats
        assert heartbeats[0][1] == (
            "cure-chunkhound: tools/call code_research waiting (0.0s / 1200s)"
        )
        assert 0.0 <= heartbeats[0][0] - request_received_at[0] < 1.0
        assert 4.5 <= heartbeats[1][0] - heartbeats[0][0] <= 5.6
        assert heartbeats[1][0] <= released_at
    finally:
        release_result.set()
        listener.close()
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        if reader_thread is not None:
            reader_thread.join(timeout=2)
        server_thread.join(timeout=3)
        assert not server_thread.is_alive()
        assert server_done.is_set()
        assert server_errors == []


@linux_only
def test_memfd_failure_after_source_open_does_not_leak_source_fd(
    authority_paths: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """B1 RED: every acquisition edge closes the already-open source fd."""
    real_open = os.open
    real_close = os.close
    baseline_fd_count = len(os.listdir("/proc/self/fd"))
    opened: list[int] = []

    def tracking_open(path: os.PathLike[str] | str, flags: int, *args: int) -> int:
        fd = real_open(path, flags, *args)
        opened.append(fd)
        return fd

    monkeypatch.setattr(broker_module.os, "open", tracking_open)
    monkeypatch.setattr(
        broker_module.os,
        "memfd_create",
        mock.Mock(side_effect=OSError("memfd unavailable")),
    )
    with pytest.raises(OSError, match="memfd unavailable"):
        HelperLaunchAuthority(**authority_paths)  # type: ignore[arg-type]

    leaked: list[int] = []
    for fd in opened:
        try:
            os.fstat(fd)
        except OSError:
            continue
        leaked.append(fd)
        real_close(fd)
    assert leaked == []
    assert len(os.listdir("/proc/self/fd")) == baseline_fd_count


@linux_only
def test_worker_baseexception_during_executor_drain_is_reported(
    authority: HelperLaunchAuthority,
) -> None:
    """B1 RED: close observes failures appended after its initial state snapshot."""
    broker = ChunkHoundHelperBroker(authority=authority)
    release = threading.Event()
    entered = threading.Event()
    client_done = threading.Event()
    shutdown_entered = threading.Event()
    client_thread: threading.Thread | None = None
    close_thread: threading.Thread | None = None
    close_errors: list[BaseException] = []
    cleanup_errors: list[BaseException] = []

    sentinel = KeyboardInterrupt("worker-drain-sentinel")

    def explode(*args: object, **kwargs: object) -> dict[str, object]:
        entered.set()
        assert release.wait(timeout=10)
        raise sentinel

    real_shutdown = broker._executor.shutdown

    def release_and_join(*args: object, **kwargs: object) -> None:
        shutdown_entered.set()
        release.set()
        real_shutdown(*args, **kwargs)
        assert client_done.wait(timeout=5)

    try:
        endpoint = broker.start()
        scope = broker.begin_scope()

        def client() -> None:
            try:
                request_helper_broker(
                    endpoint,
                    {
                        "operation": "search",
                        "arguments": {"query": "worker-drain"},
                        "scope": scope,
                    },
                    timeout=10,
                )
            except BaseException:
                pass
            finally:
                client_done.set()

        def close() -> None:
            try:
                broker.close()
            except BaseException as exc:
                close_errors.append(exc)

        client_thread = threading.Thread(target=client, name="b1-worker-client")
        close_thread = threading.Thread(target=close, name="b1-worker-close")
        with (
            mock.patch.object(broker, "_execute", explode),
            mock.patch.object(broker._executor, "shutdown", release_and_join),
        ):
            client_thread.start()
            assert entered.wait(timeout=5)
            close_thread.start()
            assert shutdown_entered.wait(timeout=5)
            close_thread.join(timeout=10)
            client_thread.join(timeout=10)
    finally:
        release.set()
        try:
            broker.close()
        except BaseException as exc:
            cleanup_errors.append(exc)
        if close_thread is not None:
            close_thread.join(timeout=10)
            assert not close_thread.is_alive()
        if client_thread is not None:
            client_thread.join(timeout=10)
            assert not client_thread.is_alive()

    assert client_done.is_set()
    assert len(close_errors) == 1
    assert isinstance(close_errors[0], HelperBrokerError)
    assert close_errors[0].__cause__ is sentinel


@pytest.mark.parametrize(
    "failure_stage",
    ("stdin.close", "terminate", "initial_wait", "kill", "final_wait"),
)
def test_json_rpc_close_reaps_after_baseexception_and_surfaces_teardown_failure(
    failure_stage: str,
) -> None:
    """B1 RED: every teardown abort still reaches kill and final reap."""
    calls: list[str] = []
    sentinel = KeyboardInterrupt(f"{failure_stage}-sentinel")

    class Stdin:
        def close(self) -> None:
            calls.append("stdin.close")
            if failure_stage == "stdin.close":
                raise sentinel

    class Process:
        stdin = Stdin()

        def terminate(self) -> None:
            calls.append("terminate")
            if failure_stage == "terminate":
                raise sentinel

        def kill(self) -> None:
            calls.append("kill")
            if failure_stage == "kill":
                raise sentinel

        def wait(self, timeout: float) -> int:
            wait_number = sum(call.startswith("wait:") for call in calls) + 1
            calls.append(f"wait:{wait_number}:{timeout}")
            if wait_number == 1:
                if failure_stage == "initial_wait":
                    raise sentinel
                raise subprocess.TimeoutExpired("chunkhound", timeout)
            if failure_stage == "final_wait":
                raise sentinel
            return 0

    session = cure_chunkhound.JsonRpcSession.__new__(cure_chunkhound.JsonRpcSession)
    session.proc = Process()
    observed: BaseException | None = None
    try:
        session.close()
    except BaseException as exc:
        observed = exc

    assert observed is sentinel or (
        observed is not None and observed.__cause__ is sentinel
    )
    assert "kill" in calls
    kill_index = calls.index("kill")
    assert any(call.startswith("wait:") for call in calls[kill_index + 1 :])


@linux_only
def test_broker_rejects_exact_config_drift_before_session_factory_consumes_it(
    authority_paths: dict[str, object], tmp_path: Path
) -> None:
    """B1 RED: accepted config-digest evidence fails closed after path drift."""
    accepted = b'{"database": {"path": "accepted.db"}}\n'
    replacement = b'{"database": {"path": "replacement.db"}}\n'
    config_path = Path(authority_paths["config_path"])
    config_path.write_bytes(accepted)
    expected_config_digest = hashlib.sha256(
        json.dumps(
            json.loads(accepted),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    authority = HelperLaunchAuthority(
        **{**authority_paths, "expected_config_digest": expected_config_digest}
    )  # type: ignore[arg-type]
    session_factory_calls: list[dict[str, object]] = []

    class SessionProbe:
        def __init__(self, **kwargs: object) -> None:
            session_factory_calls.append(dict(kwargs))

        def close(self) -> None:
            return None

    substitute = tmp_path / "replacement-config.json"
    substitute.write_bytes(replacement)
    os.replace(substitute, config_path)
    broker = ChunkHoundHelperBroker(authority=authority, session_factory=SessionProbe)
    try:
        with pytest.raises(
            HelperBrokerError, match=r"^trusted helper config digest mismatch$"
        ):
            broker.open_session(
                {
                    "operation": "search",
                    "arguments": {"query": "config drift"},
                }
            )
        assert session_factory_calls == []
    finally:
        try:
            broker.close()
        except BaseException:
            pass
        authority.close()


@linux_only
def test_close_keyboardinterrupt_at_accept_join_still_cleans_every_resource(
    authority: HelperLaunchAuthority,
) -> None:
    """B1 RED: a first-boundary BaseException cannot short-circuit teardown."""
    broker = ChunkHoundHelperBroker(authority=authority)
    broker.start()
    sentinel = KeyboardInterrupt("accept-join-sentinel")
    session_closed = threading.Event()

    class Session:
        def close(self) -> None:
            session_closed.set()

    session = Session()
    client, peer = socket.socketpair()
    with broker._lock:
        broker._active_sessions.add(session)
        broker._reading_clients.add(client)
    assert broker._accept_thread is not None
    first: BaseException | None = None
    second: BaseException | None = None
    try:
        with mock.patch.object(broker._accept_thread, "join", side_effect=sentinel):
            try:
                broker.close()
            except BaseException as exc:
                first = exc
        try:
            broker.close()
        except BaseException as exc:
            second = exc

        assert isinstance(first, HelperBrokerError) and first.__cause__ is sentinel
        assert isinstance(second, HelperBrokerError) and second.__cause__ is sentinel
        assert session_closed.is_set()
        assert broker._executor._shutdown
        with pytest.raises(OSError):
            os.fstat(authority.executable_fd)
        peer.settimeout(0.2)
        assert peer.recv(1) == b""
    finally:
        client.close()
        peer.close()
        if not broker._executor._shutdown:
            broker._executor.shutdown(wait=False, cancel_futures=True)
        authority.close()


@linux_only
def test_generated_helper_slow_preflight_emits_no_heartbeat(
    tmp_path: Path,
) -> None:
    """Compatibility control: broker waiting must not create preflight heartbeat."""
    result = _run_gated_generated_helper(
        tmp_path=tmp_path,
        command=["preflight"],
        operation="preflight",
        delay=5.3,
        inject_transient_heartbeat_write_failure=False,
    )
    assert result.returncode == 0, result.stderr
    lines = [line for line in result.stdout.splitlines() if line]
    assert len(lines) == 1
    assert not any(line.startswith("cure-chunkhound:") for line in lines)
    assert json.loads(lines[0])["ok"] is True


@linux_only
def test_generated_helper_injected_transient_heartbeat_write_failure_is_nonfatal(
    tmp_path: Path,
) -> None:
    """B1 RED: an injected transient callback write failure preserves the result."""
    result = _run_gated_generated_helper(
        tmp_path=tmp_path,
        command=["research", "broken heartbeat"],
        operation="research",
        delay=5.3,
        inject_transient_heartbeat_write_failure=True,
    )
    assert result.returncode == 0, result.stderr
    payloads = [
        json.loads(line)
        for line in result.stdout.splitlines()
        if line.strip().startswith("{")
    ]
    assert len(payloads) == 1
    assert payloads[0]["ok"] is True
    assert payloads[0]["result"] == "broker completed successfully"


def _run_gated_generated_helper(
    *,
    tmp_path: Path,
    command: list[str],
    operation: str,
    delay: float,
    inject_transient_heartbeat_write_failure: bool,
) -> subprocess.CompletedProcess[str]:
    repo = tmp_path / "repo"
    work = tmp_path / "work"
    runtime = tmp_path / "runtime"
    repo.mkdir()
    work.mkdir()
    runtime.mkdir()
    helper = cure_llm.write_chunkhound_helper(
        work_dir=work,
        repo_dir=repo,
        chunkhound_config_path=runtime / "chunkhound.json",
        chunkhound_db_path=runtime / ".chunkhound.db",
        chunkhound_cwd=runtime,
        provider="codex",
    )
    endpoint = "cure-test-helper-" + os.urandom(8).hex()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind("\0" + endpoint)
    listener.listen(1)
    errors: list[BaseException] = []

    def server() -> None:
        try:
            connection, _ = listener.accept()
            with connection:
                request = bytearray()
                while b"\n" not in request:
                    request.extend(connection.recv(8192))
                decoded = json.loads(bytes(request).split(b"\n", 1)[0])
                assert decoded["operation"] == operation
                time.sleep(delay)
                if operation == "preflight":
                    payload = {
                        "ok": True,
                        "command": "preflight",
                        "available_tools": ["search", "code_research"],
                    }
                else:
                    payload = {
                        "ok": True,
                        "command": "research",
                        "tool_name": "code_research",
                        "result": "broker completed successfully",
                    }
                connection.sendall(
                    json.dumps({"ok": True, "payload": payload}).encode() + b"\n"
                )
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=server, name="gated-generated-helper")
    thread.start()
    environment = os.environ.copy()
    environment["CURE_CHUNKHOUND_BROKER_ENDPOINT"] = endpoint
    environment["CURE_CHUNKHOUND_BROKER_SCOPE"] = "b" * 64
    try:
        if inject_transient_heartbeat_write_failure:
            bootstrap = (
                "import runpy,sys\n"
                "class Selective:\n"
                " def __init__(self): self.failed=False\n"
                " def write(self, value):\n"
                "  if value.startswith('cure-chunkhound:') and not self.failed:\n"
                "   self.failed=True\n"
                "   raise OSError('injected transient heartbeat write failure')\n"
                "  return sys.__stdout__.write(value)\n"
                " def flush(self): return sys.__stdout__.flush()\n"
                "sys.stdout=Selective()\n"
                f"sys.argv={[str(helper), *command]!r}\n"
                f"runpy.run_path({str(helper)!r}, run_name='__main__')\n"
            )
            argv = [sys.executable, "-c", bootstrap]
        else:
            argv = [str(helper), *command]
        result = subprocess.run(
            argv,
            cwd=repo,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=delay + 4.0,
        )
    finally:
        listener.close()
        thread.join(timeout=2)
    assert not thread.is_alive()
    if errors:
        assert inject_transient_heartbeat_write_failure
        assert all(isinstance(exc, BrokenPipeError) for exc in errors)
    return result
