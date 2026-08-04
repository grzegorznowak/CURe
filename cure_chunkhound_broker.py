from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
import socket
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import MappingProxyType
from typing import Any

_MAX_REQUEST_BYTES = 64 * 1024
_MAX_QUERY_CHARS = 32 * 1024
_MAX_PATH_CHARS = 4096
_EXECUTOR_DRAIN_SECONDS = 10.0
_ALLOWED_ARGUMENTS = {
    "preflight": frozenset(),
    "search": frozenset({"query", "type", "path", "page_size", "offset"}),
    "research": frozenset({"query", "path"}),
    "code_research": frozenset({"query", "path"}),
}


class HelperBrokerError(RuntimeError):
    """A sanitized helper-broker protocol or lifecycle failure."""


class HelperLaunchAuthority:
    """Coordinator-owned, immutable native ChunkHound launch authority."""

    __slots__ = (
        "environment",
        "resolved_executable",
        "expected_executable_digest",
        "expected_config_digest",
        "environment_digest",
        "cwd",
        "config_path",
        "database_path",
        "repo_path",
        "executable_fd",
        "_closed",
        "_initialized",
    )

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_initialized", False):
            raise AttributeError("helper launch authority is immutable")
        object.__setattr__(self, name, value)

    def __init__(
        self,
        *,
        environment: Mapping[str, str],
        resolved_executable: str | Path,
        expected_executable_digest: str,
        expected_config_digest: str,
        environment_digest: str,
        cwd: str | Path,
        config_path: str | Path,
        database_path: str | Path,
        repo_path: str | Path | None = None,
    ) -> None:
        frozen = {str(key): str(value) for key, value in environment.items()}
        digest = hashlib.sha256(
            json.dumps(
                frozen, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()
        if not secrets.compare_digest(digest, str(environment_digest)):
            raise HelperBrokerError("trusted launch environment digest mismatch")
        executable = Path(resolved_executable).resolve(strict=True)
        resolved_cwd = Path(cwd).resolve(strict=True)
        resolved_config = Path(config_path).resolve(strict=True)
        expected_config = str(expected_config_digest)
        self._validate_config_digest(resolved_config, expected_config)
        resolved_database = Path(database_path).resolve(strict=True)
        resolved_repo = Path(repo_path or resolved_cwd).resolve(strict=True)
        source_fd = os.open(executable, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
        try:
            executable_fd = os.memfd_create(
                "cure-chunkhound-snapshot",
                getattr(os, "MFD_CLOEXEC", 0)
                | getattr(os, "MFD_ALLOW_SEALING", 0),
            )
            try:
                executable_hasher = hashlib.sha256()
                while True:
                    chunk = os.read(source_fd, 1024 * 1024)
                    if not chunk:
                        break
                    executable_hasher.update(chunk)
                    view = memoryview(chunk)
                    while view:
                        written = os.write(executable_fd, view)
                        view = view[written:]
                if not secrets.compare_digest(
                    executable_hasher.hexdigest(), str(expected_executable_digest)
                ):
                    raise HelperBrokerError(
                        "receipt-time executable digest mismatch"
                    )
                os.fchmod(executable_fd, 0o500)
                os.lseek(executable_fd, 0, os.SEEK_SET)
                seals = (
                    fcntl.F_SEAL_SEAL
                    | fcntl.F_SEAL_SHRINK
                    | fcntl.F_SEAL_GROW
                    | fcntl.F_SEAL_WRITE
                )
                fcntl.fcntl(executable_fd, fcntl.F_ADD_SEALS, seals)
            except BaseException:
                os.close(executable_fd)
                raise
        finally:
            os.close(source_fd)
        self.environment = MappingProxyType(frozen)
        self.resolved_executable = executable
        self.expected_executable_digest = str(expected_executable_digest)
        self.expected_config_digest = expected_config
        self.environment_digest = str(environment_digest)
        self.cwd = resolved_cwd
        self.config_path = resolved_config
        self.database_path = resolved_database
        self.repo_path = resolved_repo
        self.executable_fd = executable_fd
        self._closed = False
        self._initialized = True

    @staticmethod
    def _validate_config_digest(config_path: Path, expected_digest: str) -> None:
        try:
            config_value = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(config_value, dict):
                raise ValueError("config is not a JSON object")
            canonical = json.dumps(
                config_value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
            actual_digest = hashlib.sha256(canonical).hexdigest()
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise HelperBrokerError("trusted helper config digest mismatch") from exc
        if not secrets.compare_digest(actual_digest, expected_digest):
            raise HelperBrokerError("trusted helper config digest mismatch")

    def validate_config(self) -> None:
        self._validate_config_digest(self.config_path, self.expected_config_digest)

    @property
    def pinned_executable(self) -> str:
        if self._closed:
            raise HelperBrokerError("helper launch authority is closed")
        return f"/proc/self/fd/{self.executable_fd}"

    def close(self) -> None:
        if self._closed:
            return
        object.__setattr__(self, "_closed", True)
        os.close(self.executable_fd)


class ChunkHoundHelperBroker:
    """Bounded coordinator IPC broker; only this object owns native launch inputs."""

    def __init__(
        self,
        *,
        authority: HelperLaunchAuthority,
        session_factory: Callable[..., object] | None = None,
        max_workers: int = 8,
    ) -> None:
        self.authority = authority
        self._session_factory = session_factory
        self._owner = secrets.token_hex(16)
        self._records: dict[str, dict[str, Any]] = {}
        self._consumed: set[str] = set()
        self._live_scopes: set[str] = set()
        self._revoked_scopes: set[str] = set()
        self._active_sessions: set[object] = set()
        self._active_clients: set[socket.socket] = set()
        self._reading_clients: set[socket.socket] = set()
        self._worker_failures: list[BaseException] = []
        self._lock = threading.Lock()
        self._listener: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._executor = ThreadPoolExecutor(
            max_workers=max(8, int(max_workers)), thread_name_prefix="cure-ch-broker"
        )
        self._closed = False
        self._close_done = threading.Event()
        self._close_failure: BaseException | None = None
        self.endpoint = "cure-chunkhound-" + secrets.token_hex(16)

    @staticmethod
    def _validate_request(
        request: Mapping[str, Any],
    ) -> tuple[str, dict[str, Any], str | None]:
        if not {"operation", "arguments"} <= set(request) or not set(request) <= {
            "operation",
            "arguments",
            "scope",
        }:
            raise HelperBrokerError("invalid helper broker request fields")
        operation = str(request.get("operation") or "").strip()
        if operation not in _ALLOWED_ARGUMENTS:
            raise HelperBrokerError("unsupported helper broker operation")
        raw_arguments = request.get("arguments")
        if (
            not isinstance(raw_arguments, dict)
            or not set(raw_arguments) <= _ALLOWED_ARGUMENTS[operation]
        ):
            raise HelperBrokerError("invalid helper broker arguments")
        arguments = dict(raw_arguments)
        query = arguments.get("query")
        if operation != "preflight" and (
            not isinstance(query, str) or not query or len(query) > _MAX_QUERY_CHARS
        ):
            raise HelperBrokerError("invalid helper broker query")
        path = arguments.get("path")
        if path is not None and (
            not isinstance(path, str) or len(path) > _MAX_PATH_CHARS
        ):
            raise HelperBrokerError("invalid helper broker path")
        if "type" in arguments and arguments["type"] not in {"regex", "semantic"}:
            raise HelperBrokerError("invalid helper broker search type")
        for key, low, high in (("page_size", 1, 100), ("offset", 0, 1_000_000)):
            if key in arguments and (
                type(arguments[key]) is not int or not low <= arguments[key] <= high
            ):
                raise HelperBrokerError(f"invalid helper broker {key}")
        raw_scope = request.get("scope")
        scope = str(raw_scope).strip() if raw_scope is not None else None
        if scope is not None and (not scope or len(scope) != 64):
            raise HelperBrokerError("invalid helper broker scope")
        return operation, arguments, scope

    def begin_scope(self) -> str:
        with self._lock:
            if self._closed:
                raise HelperBrokerError("helper broker is closed")
            while True:
                scope = secrets.token_hex(32)
                if scope not in self._live_scopes:
                    self._live_scopes.add(scope)
                    return scope

    def end_scope(self, scope: str) -> None:
        with self._lock:
            if scope not in self._live_scopes:
                raise HelperBrokerError(
                    "missing, foreign, or ended helper broker scope"
                )
            self._live_scopes.remove(scope)
            self._revoked_scopes.add(scope)

    def _require_live_scope(self, scope: str | None) -> str:
        with self._lock:
            if self._closed:
                raise HelperBrokerError("helper broker is closed")
            if scope is None or scope not in self._live_scopes:
                raise HelperBrokerError(
                    "missing, foreign, or ended helper broker scope"
                )
            return scope

    def records_for_scope(self, scope: str) -> list[dict[str, str]]:
        with self._lock:
            if scope not in self._live_scopes:
                raise HelperBrokerError(
                    "missing, foreign, or ended helper broker scope"
                )
            return [
                {
                    "record_id": record_id,
                    "operation": str(record["operation"]),
                    "result_digest": str(record["result_digest"]),
                }
                for record_id, record in self._records.items()
                if record.get("scope") == scope and record.get("result_digest")
            ]

    def open_session(self, request: Mapping[str, Any]) -> str:
        operation, arguments, scope = self._validate_request(request)
        if self._session_factory is None:
            scope = self._require_live_scope(scope)
        with self._lock:
            if self._closed:
                raise HelperBrokerError("helper broker is closed")
        if self._session_factory is None:
            from cure_chunkhound import JsonRpcSession

            factory: Callable[..., object] = JsonRpcSession
        else:
            factory = self._session_factory
        self.authority.validate_config()
        session = factory(
            config_path=self.authority.config_path,
            repo_path=self.authority.repo_path,
            cwd=self.authority.cwd,
            binary=(
                str(self.authority.resolved_executable)
                if self._session_factory is not None
                else self.authority.pinned_executable
            ),
            env=self.authority.environment,
            executable_fd=self.authority.executable_fd,
        )
        record_id = self._owner + secrets.token_hex(16)
        with self._lock:
            if self._closed:
                close = getattr(session, "close", None)
                if callable(close):
                    close()
                raise HelperBrokerError("helper broker is closed")
            self._records[record_id] = {
                "operation": operation,
                "arguments_digest": hashlib.sha256(
                    json.dumps(
                        arguments, sort_keys=True, separators=(",", ":")
                    ).encode()
                ).hexdigest(),
                "session": session,
                "result_digest": None,
                "scope": scope,
            }
        return record_id

    def accept_client_result(self, record_id: str, result: Mapping[str, Any]) -> None:
        if not isinstance(result, Mapping):
            raise HelperBrokerError("invalid helper broker result")
        with self._lock:
            record = self._records.get(str(record_id))
            if (
                record is None
                or record_id in self._consumed
                or not record_id.startswith(self._owner)
            ):
                raise HelperBrokerError(
                    "missing, foreign, or replayed helper broker record"
                )
            record["result_digest"] = hashlib.sha256(
                json.dumps(dict(result), sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            self._consumed.add(record_id)
            session = record.get("session")
            record["session"] = None
        close = getattr(session, "close", None)
        if callable(close):
            try:
                close()
            except BaseException as exc:
                raise HelperBrokerError(
                    "trusted helper session cleanup failed"
                ) from exc

    def start(self) -> str:
        with self._lock:
            if self._closed:
                raise HelperBrokerError("helper broker is closed")
            if self._listener is not None:
                return self.endpoint
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind("\0" + self.endpoint)
            listener.listen(64)
            listener.settimeout(0.25)
            self._listener = listener
            self._accept_thread = threading.Thread(
                target=self._accept_loop, name="cure-ch-broker-accept", daemon=True
            )
            self._accept_thread.start()
        return self.endpoint

    def _accept_loop(self) -> None:
        while True:
            listener = self._listener
            if listener is None:
                return
            try:
                client, _ = listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            self._executor.submit(self._serve_client, client)

    def _serve_client(self, client: socket.socket) -> None:
        with self._lock:
            if self._closed:
                client.close()
                return
            self._active_clients.add(client)
            self._reading_clients.add(client)
        try:
            with client:
                client.settimeout(2.0)
                data = bytearray()
                try:
                    while b"\n" not in data:
                        chunk = client.recv(
                            min(8192, _MAX_REQUEST_BYTES + 1 - len(data))
                        )
                        if not chunk:
                            raise HelperBrokerError("incomplete helper broker request")
                        data.extend(chunk)
                        if len(data) > _MAX_REQUEST_BYTES:
                            raise HelperBrokerError("helper broker request too large")
                    line, remainder = bytes(data).split(b"\n", 1)
                    if remainder:
                        raise HelperBrokerError(
                            "multiple helper broker requests are not allowed"
                        )
                    request = json.loads(line)
                    if not isinstance(request, dict):
                        raise HelperBrokerError("invalid helper broker request")
                    operation, arguments, scope = self._validate_request(request)
                    with self._lock:
                        self._reading_clients.discard(client)
                    payload = self._execute(operation, arguments, scope=scope)
                    response = {"ok": True, "payload": payload}
                except Exception as exc:
                    response = {"ok": False, "error": exc.__class__.__name__}
                except BaseException as exc:
                    with self._lock:
                        self._worker_failures.append(exc)
                    response = {"ok": False, "error": exc.__class__.__name__}
                try:
                    client.sendall(
                        json.dumps(response, sort_keys=True).encode() + b"\n"
                    )
                except OSError:
                    pass
        finally:
            with self._lock:
                self._active_clients.discard(client)
                self._reading_clients.discard(client)

    def _session_opened(self, session: object) -> None:
        with self._lock:
            if self._closed:
                close = getattr(session, "close", None)
                if callable(close):
                    close()
                raise HelperBrokerError("helper broker is closed")
            self._active_sessions.add(session)

    def _session_closed(self, session: object) -> None:
        with self._lock:
            self._active_sessions.discard(session)

    def _execute(
        self, operation: str, arguments: dict[str, Any], *, scope: str | None
    ) -> dict[str, Any]:
        scope = self._require_live_scope(scope)
        from cure_chunkhound import (
            JsonRpcSession,
            run_chunkhound_mcp_preflight_payload,
            run_chunkhound_tool_payload,
        )

        def session_factory(**requested: object) -> object:
            self.authority.validate_config()
            return JsonRpcSession(
                config_path=self.authority.config_path,
                repo_path=self.authority.repo_path,
                cwd=self.authority.cwd,
                binary=self.authority.pinned_executable,
                env=self.authority.environment,
                transport_mode=str(requested.get("transport_mode") or "json_line"),
                heartbeat_provider=str(
                    requested.get("heartbeat_provider") or "claude"
                ),
                heartbeat_interval=float(
                    str(requested.get("heartbeat_interval") or 5.0)
                ),
                executable_fd=self.authority.executable_fd,
            )

        self.authority.validate_config()
        if operation == "preflight":
            payload = run_chunkhound_mcp_preflight_payload(
                self.authority.config_path,
                self.authority.repo_path,
                _session_factory=session_factory,
                _session_opened=self._session_opened,
                _session_closed=self._session_closed,
            )
        else:
            payload = run_chunkhound_tool_payload(
                self.authority.config_path,
                self.authority.repo_path,
                operation,
                arguments,
                _session_factory=session_factory,
                _session_opened=self._session_opened,
                _session_closed=self._session_closed,
            )
        record_id = self._owner + secrets.token_hex(16)
        digest_payload = dict(payload)
        digest_payload.pop("helper_path", None)
        with self._lock:
            if self._closed:
                raise HelperBrokerError("helper broker closed during request")
            if scope not in self._live_scopes:
                raise HelperBrokerError("helper broker scope ended during request")
            self._records[record_id] = {
                "operation": operation,
                "arguments_digest": hashlib.sha256(
                    json.dumps(arguments, sort_keys=True).encode()
                ).hexdigest(),
                "result_digest": hashlib.sha256(
                    json.dumps(digest_payload, sort_keys=True, default=str).encode()
                ).hexdigest(),
                "session": None,
                "scope": scope,
            }
            self._consumed.add(record_id)
        result = dict(payload)
        result["broker_record_id"] = record_id
        return result

    def close(self) -> None:
        with self._lock:
            if self._closed:
                wait_for_close = True
            else:
                wait_for_close = False
                self._closed = True
                self._live_scopes.clear()
                listener, self._listener = self._listener, None
                records = list(self._records.values())
                sessions = list(self._active_sessions)
                clients = list(self._active_clients | self._reading_clients)
        if wait_for_close:
            self._close_done.wait()
            if self._close_failure is not None:
                raise HelperBrokerError(
                    "trusted helper broker cleanup failed"
                ) from self._close_failure
            return

        failures: list[BaseException] = []

        def attempt(cleanup: Callable[[], object]) -> None:
            try:
                cleanup()
            except BaseException as exc:
                failures.append(exc)

        if listener is not None:
            attempt(listener.close)
        accept_thread = self._accept_thread
        if accept_thread is not None:
            attempt(lambda: accept_thread.join(timeout=2.0))
        for client in clients:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            except BaseException as exc:
                failures.append(exc)
            attempt(client.close)
        for session in sessions + [record.get("session") for record in records]:
            close = getattr(session, "close", None)
            if callable(close):
                attempt(close)
        drain_failures: list[BaseException] = []

        def drain_executor() -> None:
            try:
                self._executor.shutdown(wait=True, cancel_futures=True)
            except BaseException as exc:
                drain_failures.append(exc)

        drain_thread = threading.Thread(
            target=drain_executor,
            name="cure-helper-broker-drain",
            daemon=True,
        )
        attempt(drain_thread.start)
        if drain_thread.ident is not None:
            attempt(lambda: drain_thread.join(timeout=_EXECUTOR_DRAIN_SECONDS))
            if drain_thread.is_alive():
                failures.append(TimeoutError("helper broker worker drain timed out"))
        failures.extend(drain_failures)
        with self._lock:
            failures.extend(self._worker_failures)
        attempt(self.authority.close)
        self._close_failure = failures[0] if failures else None
        self._close_done.set()
        if self._close_failure is not None:
            raise HelperBrokerError(
                "trusted helper broker cleanup failed"
            ) from self._close_failure


def request_helper_broker(
    endpoint: str,
    request: Mapping[str, Any],
    *,
    timeout: float = 1220.0,
    heartbeat_callback: Callable[[float], None] | None = None,
    heartbeat_interval: float = 5.0,
) -> dict[str, Any]:
    encoded = (
        json.dumps(dict(request), sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
    )
    if len(encoded) > _MAX_REQUEST_BYTES:
        raise HelperBrokerError("helper broker request too large")
    started_at = time.monotonic()
    deadline = started_at + timeout
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect("\0" + str(endpoint))
        client.sendall(encoded)
        data = bytearray()
        if heartbeat_callback is not None:
            # Yield once so the peer can admit the request before the provider-visible
            # waiting indication; this remains an immediate (0.0s) heartbeat.
            time.sleep(0.01)
            try:
                heartbeat_callback(0.0)
            except Exception:
                pass
        while b"\n" not in data:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("timed out waiting for helper broker response")
            receive_timeout = remaining
            if heartbeat_callback is not None:
                receive_timeout = min(receive_timeout, max(0.001, heartbeat_interval))
            client.settimeout(receive_timeout)
            try:
                chunk = client.recv(8192)
            except TimeoutError:
                if heartbeat_callback is None or time.monotonic() >= deadline:
                    raise
                try:
                    heartbeat_callback(time.monotonic() - started_at)
                except Exception:
                    pass
                continue
            if not chunk:
                raise HelperBrokerError("helper broker closed without a response")
            data.extend(chunk)
            if len(data) > _MAX_REQUEST_BYTES * 16:
                raise HelperBrokerError("helper broker response too large")
    response = json.loads(bytes(data).split(b"\n", 1)[0])
    if (
        not isinstance(response, dict)
        or not response.get("ok")
        or not isinstance(response.get("payload"), dict)
    ):
        raise HelperBrokerError("helper broker request failed")
    return dict(response["payload"])
