from __future__ import annotations

import json
import os
import select
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_STDERR_TAIL_MAX = 16000
_DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 5.0
_DEFAULT_PREFLIGHT_STAGE_TIMEOUTS: dict[str, float] = {
    "spawn": 3.0,
    "initialize": 120.0,
    "notifications/initialized": 5.0,
    "tools/list": 10.0,
    "daemon_metadata": 5.0,
}
_DEFAULT_TOOL_CALL_TIMEOUTS: dict[str, float] = {
    "search": 60.0,
    "code_research": 1200.0,
}
_TRANSPORT_MODES = ("json_line", "mcp_framed")

DAEMON_METADATA_PROBE = "\n".join(
    [
        "import json",
        "import sys",
        "from pathlib import Path",
        "payload = dict(ok=False, daemon_lock_path='', daemon_log_path='', daemon_socket_path='', daemon_pid=None, daemon_runtime_dir='', daemon_registry_entry_path='', chunkhound_runtime_python=sys.executable, chunkhound_module_path='', daemon_metadata_error='')",
        "try:",
        "    import chunkhound",
        "    from chunkhound.daemon.discovery import DaemonDiscovery",
        "    repo_dir = Path(sys.argv[1]).resolve()",
        "    discovery = DaemonDiscovery(repo_dir)",
        "    payload['ok'] = True",
        "    payload['daemon_lock_path'] = str(discovery.get_lock_path())",
        "    payload['daemon_log_path'] = str(discovery.get_lock_path().with_name('daemon.log'))",
        "    payload['daemon_runtime_dir'] = str(discovery.get_runtime_dir())",
        "    payload['daemon_registry_entry_path'] = str(discovery.get_registry_entry_path())",
        "    payload['chunkhound_module_path'] = str(Path(chunkhound.__file__).resolve())",
        "    lock = discovery.read_lock() or dict()",
        "    payload['daemon_socket_path'] = str(lock.get('socket_path') or '')",
        "    payload['daemon_pid'] = lock.get('pid')",
        "except Exception as exc:",
        "    payload['daemon_metadata_error'] = str(exc)",
        "print(json.dumps(payload, sort_keys=True))",
    ]
)


@dataclass
class ChunkHoundPreflightResult:
    stage: str
    available_tools: list[str]
    missing_tools: list[str]
    mcp_transport: str
    daemon_pid: int | None
    daemon_socket: str | None
    daemon_log: str | None
    daemon_runtime_dir: str | None
    time_ms: float

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ChunkHoundPreflightResult":
        elapsed_seconds = payload.get("elapsed_seconds")
        time_ms = float(elapsed_seconds) * 1000.0 if isinstance(elapsed_seconds, (int, float)) else 0.0
        daemon_pid = payload.get("daemon_pid")
        if daemon_pid is not None:
            try:
                daemon_pid = int(daemon_pid)
            except (TypeError, ValueError):
                daemon_pid = None
        return cls(
            stage=str(payload.get("preflight_stage") or "unknown"),
            available_tools=[str(item) for item in payload.get("available_tools") or []],
            missing_tools=[str(item) for item in payload.get("missing_tools") or []],
            mcp_transport=str(payload.get("mcp_transport") or "unknown"),
            daemon_pid=daemon_pid,
            daemon_socket=_none_if_empty(payload.get("daemon_socket_path")),
            daemon_log=_none_if_empty(payload.get("daemon_log_path")),
            daemon_runtime_dir=_none_if_empty(payload.get("daemon_runtime_dir")),
            time_ms=round(time_ms, 3),
        )


class ChunkHoundPreflightError(Exception):
    """Raised when ChunkHound MCP preflight fails hard."""

    def __init__(self, stage: str, detail: str, *, payload: dict[str, Any] | None = None) -> None:
        self.stage = str(stage or "").strip() or "unknown"
        self.detail = str(detail or "").strip() or "ChunkHound preflight failed"
        self.payload = dict(payload or {})
        super().__init__(f"{self.stage}: {self.detail}")


class PreflightStageError(RuntimeError):
    def __init__(
        self,
        stage: str,
        detail: str,
        *,
        timeout: bool = False,
        stderr_tail: str = "",
    ) -> None:
        super().__init__(detail)
        self.stage = str(stage or "").strip() or "unknown"
        self.timeout = bool(timeout)
        self.stderr_tail = _trim_tail_text(stderr_tail)


def _none_if_empty(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _trim_tail_text(text: object, *, max_chars: int = 4000) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]


def _read_lock(path_text: str) -> dict[str, Any]:
    raw = str(path_text or "").strip()
    if not raw:
        return {}
    lock_path = Path(raw)
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _emit_stage(
    stage: str,
    status: str,
    *,
    detail: str | None = None,
    enabled: bool = True,
) -> None:
    if not enabled:
        return
    message = f"preflight stage={stage} status={status}"
    detail_text = " ".join(str(detail or "").split())
    if detail_text:
        detail_text = _trim_tail_text(detail_text, max_chars=240)
        message += f" detail={detail_text}"
    sys.stderr.write(message + "\n")
    sys.stderr.flush()


def _base_cmd(config_path: str | Path, repo_path: str | Path, *, binary: str = "chunkhound") -> list[str]:
    return [str(binary or "chunkhound"), "mcp", "--config", str(config_path), str(repo_path)]


def _chunkhound_runtime_cmd(binary: str = "chunkhound") -> list[str] | None:
    resolved = str(binary or "chunkhound")
    if resolved == "chunkhound":
        resolved = shutil.which("chunkhound") or "chunkhound"
    if resolved == "chunkhound":
        return None
    launcher = Path(resolved)
    try:
        first_line = launcher.read_text(encoding="utf-8").splitlines()[0].strip()
    except Exception:
        return None
    if not first_line.startswith("#!"):
        return None
    shebang = first_line[2:].strip()
    if not shebang:
        return None
    try:
        cmd = shlex.split(shebang)
    except ValueError:
        return None
    return cmd or None


def daemon_metadata_payload(
    repo_dir: str | Path,
    chunkhound_cwd: str | Path | None = None,
    binary: str = "chunkhound",
    timeout: float = 5.0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chunkhound_path": str(binary or "chunkhound"),
        "chunkhound_runtime_python": "",
        "chunkhound_module_path": "",
        "daemon_lock_path": "",
        "daemon_socket_path": "",
        "daemon_log_path": "",
        "daemon_pid": None,
        "daemon_runtime_dir": "",
        "daemon_registry_entry_path": "",
        "daemon_metadata_error": "",
    }
    runtime_cmd = _chunkhound_runtime_cmd(binary)
    if runtime_cmd is None:
        payload["daemon_metadata_error"] = "unable to resolve chunkhound runtime interpreter"
        return payload
    env = os.environ.copy()
    env["PYTHONSAFEPATH"] = "1"
    cwd = str(Path(chunkhound_cwd).resolve(strict=False) if chunkhound_cwd is not None else Path(repo_dir).resolve(strict=False))
    try:
        result = subprocess.run(
            runtime_cmd + ["-c", DAEMON_METADATA_PROBE, str(Path(repo_dir).resolve(strict=False))],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            env=env,
            timeout=float(timeout),
        )
    except subprocess.TimeoutExpired:
        payload["daemon_metadata_error"] = f"chunkhound runtime probe timed out after {float(timeout):.1f}s"
        return payload
    except Exception as exc:
        payload["daemon_metadata_error"] = str(exc)
        return payload
    stdout_text = str(result.stdout or "").strip()
    if not stdout_text:
        stderr_text = str(result.stderr or "").strip()
        payload["daemon_metadata_error"] = stderr_text or "chunkhound runtime probe returned no output"
        return payload
    try:
        parsed = json.loads(stdout_text)
    except Exception:
        payload["daemon_metadata_error"] = "chunkhound runtime probe returned malformed JSON"
        return payload
    if not isinstance(parsed, dict):
        payload["daemon_metadata_error"] = "chunkhound runtime probe returned a non-object payload"
        return payload
    for key in payload:
        if key in parsed:
            payload[key] = parsed.get(key)
    lock_payload = _read_lock(str(payload.get("daemon_lock_path") or ""))
    if not str(payload.get("daemon_socket_path") or "").strip():
        payload["daemon_socket_path"] = str(lock_payload.get("socket_path") or "")
    if payload.get("daemon_pid") is None:
        payload["daemon_pid"] = lock_payload.get("pid")
    if not str(payload.get("daemon_log_path") or "").strip() and str(payload.get("daemon_lock_path") or "").strip():
        payload["daemon_log_path"] = str(Path(str(payload["daemon_lock_path"])).with_name("daemon.log"))
    return payload


class JsonRpcSession:
    """Manage a ChunkHound MCP subprocess and JSON-RPC request/response framing."""

    def __init__(
        self,
        *,
        config_path: str | Path,
        repo_path: str | Path,
        cwd: str | Path | None = None,
        binary: str = "chunkhound",
        transport_mode: str = "json_line",
        heartbeat_provider: str = "claude",
        heartbeat_interval: float = _DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        self.config_path = Path(config_path)
        self.repo_path = Path(repo_path)
        self.cwd = Path(cwd).resolve(strict=False) if cwd is not None else self.repo_path.resolve(strict=False)
        self.binary = str(binary or "chunkhound")
        self._next_id = 1
        self._transport_mode = str(transport_mode or "").strip() or "json_line"
        if self._transport_mode not in _TRANSPORT_MODES:
            raise ValueError(f"unsupported transport mode: {self._transport_mode}")
        self._heartbeat_provider = str(heartbeat_provider or "").strip().lower() or "claude"
        self._heartbeat_interval = float(heartbeat_interval)
        env = os.environ.copy()
        env["PYTHONSAFEPATH"] = "1"
        self.proc = subprocess.Popen(
            _base_cmd(self.config_path, self.repo_path, binary=self.binary),
            cwd=str(self.cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            env=env,
        )
        if self.proc.stdin is None or self.proc.stdout is None or self.proc.stderr is None:
            raise RuntimeError("chunkhound mcp stdio pipes are unavailable")
        self._stdout_buffer = bytearray()
        self._stderr_buffer = bytearray()
        self._stdout_open = True
        self._stderr_open = True

    def close(self) -> None:
        try:
            if self.proc.stdin is not None:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.terminate()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass

    def _stderr_tail_text(self) -> str:
        if not self._stderr_buffer:
            return ""
        return _trim_tail_text(self._stderr_buffer.decode("utf-8", errors="replace"))

    def _append_stderr(self, data: bytes) -> None:
        if not data:
            return
        self._stderr_buffer.extend(data)
        if len(self._stderr_buffer) > _STDERR_TAIL_MAX:
            del self._stderr_buffer[:-_STDERR_TAIL_MAX]

    def _stage_error(self, stage: str, detail: str, *, timeout: bool = False) -> PreflightStageError:
        return PreflightStageError(stage, detail, timeout=timeout, stderr_tail=self._stderr_tail_text())

    def _drain_ready_io(self, *, timeout_seconds: float) -> bool:
        streams = [
            stream
            for stream, is_open in ((self.proc.stdout, self._stdout_open), (self.proc.stderr, self._stderr_open))
            if stream is not None and is_open
        ]
        if not streams:
            return False
        readable, _, _ = select.select(streams, [], [], max(0.0, float(timeout_seconds)))
        saw_data = False
        for stream in readable:
            try:
                chunk = os.read(stream.fileno(), 65536)
            except OSError:
                chunk = b""
            if stream is self.proc.stdout:
                if chunk:
                    self._stdout_buffer.extend(chunk)
                    saw_data = True
                else:
                    self._stdout_open = False
            else:
                if chunk:
                    self._append_stderr(chunk)
                    saw_data = True
                else:
                    self._stderr_open = False
        return saw_data

    def _try_extract_framed_message(self) -> dict[str, Any] | None:
        if not self._stdout_buffer:
            return None
        header_end = self._stdout_buffer.find(b"\r\n\r\n")
        delimiter_len = 4
        if header_end < 0:
            header_end = self._stdout_buffer.find(b"\n\n")
            delimiter_len = 2
        if header_end < 0:
            return None
        headers_blob = bytes(self._stdout_buffer[:header_end]).decode("utf-8", errors="replace")
        headers: dict[str, str] = {}
        for raw_line in headers_blob.splitlines():
            key, sep, value = raw_line.partition(":")
            if not sep:
                raise RuntimeError("invalid MCP header line")
            headers[key.strip().lower()] = value.strip()
        try:
            length = int(headers["content-length"])
        except Exception as exc:
            raise RuntimeError("invalid MCP content-length header") from exc
        body_start = header_end + delimiter_len
        body_end = body_start + length
        if len(self._stdout_buffer) < body_end:
            return None
        body = bytes(self._stdout_buffer[body_start:body_end])
        del self._stdout_buffer[:body_end]
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("unexpected MCP payload type")
        return payload

    def _try_extract_json_line_message(self) -> dict[str, Any] | None:
        if not self._stdout_buffer:
            return None
        newline_idx = self._stdout_buffer.find(b"\n")
        if newline_idx < 0:
            return None
        raw_line = bytes(self._stdout_buffer[: newline_idx + 1])
        del self._stdout_buffer[: newline_idx + 1]
        line = raw_line.strip()
        if not line:
            return None
        payload = json.loads(line.decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("unexpected JSON-RPC payload type")
        return payload

    def _try_extract_message(self) -> dict[str, Any] | None:
        while self._stdout_buffer[:1] in (b"\r", b"\n", b" ", b"\t"):
            del self._stdout_buffer[:1]
        if not self._stdout_buffer:
            return None
        if self._stdout_buffer.startswith(b"Content-Length:"):
            return self._try_extract_framed_message()
        if self._stdout_buffer[:1] in (b"{", b"["):
            return self._try_extract_json_line_message()
        if b"\r\n\r\n" in self._stdout_buffer or b"\n\n" in self._stdout_buffer:
            return self._try_extract_framed_message()
        newline_idx = self._stdout_buffer.find(b"\n")
        if newline_idx < 0:
            return None
        preview = bytes(self._stdout_buffer[: newline_idx + 1]).decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"unexpected chunkhound mcp stdout: {_trim_tail_text(preview, max_chars=240)}")

    def _closed_stream_detail(self, stage: str) -> str:
        detail = self._stderr_tail_text()
        exit_code = self.proc.poll()
        if exit_code is not None:
            if detail:
                return f"chunkhound mcp exited during {stage} with status {exit_code}: {detail}"
            return f"chunkhound mcp exited during {stage} with status {exit_code}"
        if detail:
            return f"chunkhound mcp closed stdout during {stage}: {detail}"
        return f"chunkhound mcp closed its stdio stream during {stage}"

    def _remaining_timeout(self, *, stage: str, timeout_seconds: float, deadline: float) -> float:
        remaining = float(deadline) - time.monotonic()
        if remaining <= 0:
            raise self._stage_error(
                stage,
                f"timed out after {float(timeout_seconds):.1f}s waiting for stage {stage}",
                timeout=True,
            )
        return remaining

    def _read_message(
        self,
        *,
        stage: str,
        timeout_seconds: float,
        deadline: float,
        heartbeat_enabled: bool = False,
    ) -> dict[str, Any]:
        last_heartbeat_at = time.monotonic() - self._heartbeat_interval
        while True:
            message = self._try_extract_message()
            if message is not None:
                return message
            if not self._stdout_open:
                raise self._stage_error(stage, self._closed_stream_detail(stage))
            if heartbeat_enabled:
                now = time.monotonic()
                if now - last_heartbeat_at >= self._heartbeat_interval:
                    elapsed = max(0.0, float(timeout_seconds) - max(0.0, float(deadline) - now))
                    try:
                        if self._heartbeat_provider == "codex":
                            sys.stdout.write(f"cure-chunkhound: tools/call waiting ({elapsed:.1f}s elapsed)\n")
                            sys.stdout.flush()
                        else:
                            sys.stderr.write(f"cure-chunkhound: tools/call waiting ({elapsed:.1f}s elapsed)\n")
                            sys.stderr.flush()
                    except Exception:
                        pass
                    last_heartbeat_at = now
            remaining = self._remaining_timeout(stage=stage, timeout_seconds=timeout_seconds, deadline=deadline)
            self._drain_ready_io(timeout_seconds=min(0.2, remaining))

    def _write_message(self, payload: dict[str, Any], *, stage: str) -> None:
        raw = json.dumps(payload).encode("utf-8")
        if self._transport_mode == "json_line":
            message = raw + b"\n"
        else:
            message = f"Content-Length: {len(raw)}\r\n\r\n".encode("utf-8") + raw
        try:
            self.proc.stdin.write(message)  # type: ignore[union-attr]
            self.proc.stdin.flush()  # type: ignore[union-attr]
        except Exception as exc:
            raise self._stage_error(stage, f"failed to write MCP request during {stage}: {exc}")

    def ensure_started(self, *, stage: str, timeout_seconds: float, deadline: float | None = None) -> None:
        active_deadline = float(deadline) if deadline is not None else (time.monotonic() + max(0.0, float(timeout_seconds)))
        if self.proc.poll() is not None:
            raise self._stage_error(stage, self._closed_stream_detail(stage))
        remaining = self._remaining_timeout(stage=stage, timeout_seconds=timeout_seconds, deadline=active_deadline)
        self._drain_ready_io(timeout_seconds=min(0.05, remaining))
        if self.proc.poll() is not None:
            raise self._stage_error(stage, self._closed_stream_detail(stage))

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        stage: str,
        timeout_seconds: float,
        heartbeat_enabled: bool = False,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + max(0.0, float(timeout_seconds))
        self.ensure_started(stage=stage, timeout_seconds=timeout_seconds, deadline=deadline)
        request_id = self._next_id
        self._next_id += 1
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._write_message(payload, stage=stage)
        while True:
            message = self._read_message(
                stage=stage,
                timeout_seconds=timeout_seconds,
                deadline=deadline,
                heartbeat_enabled=heartbeat_enabled,
            )
            if message.get("id") == request_id:
                return message

    def notify(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        stage: str,
        timeout_seconds: float,
    ) -> None:
        deadline = time.monotonic() + max(0.0, float(timeout_seconds))
        self.ensure_started(stage=stage, timeout_seconds=timeout_seconds, deadline=deadline)
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._write_message(payload, stage=stage)


def _extract_result_content(response: dict[str, Any]) -> Any:
    if "error" in response:
        error = response.get("error")
        raise RuntimeError(json.dumps(error, sort_keys=True))
    result = response.get("result")
    if not isinstance(result, dict):
        return result
    if bool(result.get("isError")):
        raise RuntimeError(json.dumps(result, sort_keys=True))
    content = result.get("content")
    if isinstance(content, list) and content:
        first = content[0] if isinstance(content[0], dict) else {}
        text = str(first.get("text") or "")
        stripped = text.strip()
        if stripped:
            try:
                return json.loads(stripped)
            except Exception:
                return stripped
    return result


def _stage_trace_entry(
    *,
    stage: str,
    status: str,
    started_at: float,
    timeout_seconds: float | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "stage": stage,
        "status": status,
        "elapsed_seconds": round(max(0.0, time.monotonic() - started_at), 3),
    }
    if timeout_seconds is not None:
        entry["timeout_seconds"] = float(timeout_seconds)
    detail_text = _trim_tail_text(detail or "")
    if detail_text:
        entry["detail"] = detail_text
    return entry


def _build_preflight_payload(
    *,
    ok: bool,
    config_path: str | Path,
    repo_path: str | Path,
    binary: str,
    helper_path: str | Path | None,
    error: str = "",
    available_tools: list[str] | None = None,
    missing_tools: list[str] | None = None,
    preflight_stage: str,
    preflight_stage_status: str,
    stage_trace: list[dict[str, Any]],
    started_at: float,
    daemon_meta: dict[str, Any] | None = None,
    stderr_tail: str = "",
) -> dict[str, Any]:
    daemon_meta = daemon_meta or {}
    payload = {
        "ok": bool(ok),
        "command": "preflight",
        "available_tools": sorted(str(tool).strip() for tool in (available_tools or []) if str(tool).strip()),
        "helper_path": str(helper_path or ""),
        "chunkhound_path": str(daemon_meta.get("chunkhound_path") or binary or ""),
        "chunkhound_runtime_python": str(daemon_meta.get("chunkhound_runtime_python") or ""),
        "chunkhound_module_path": str(daemon_meta.get("chunkhound_module_path") or ""),
        "daemon_lock_path": str(daemon_meta.get("daemon_lock_path") or ""),
        "daemon_socket_path": str(daemon_meta.get("daemon_socket_path") or ""),
        "daemon_log_path": str(daemon_meta.get("daemon_log_path") or ""),
        "daemon_pid": daemon_meta.get("daemon_pid"),
        "daemon_runtime_dir": str(daemon_meta.get("daemon_runtime_dir") or ""),
        "daemon_registry_entry_path": str(daemon_meta.get("daemon_registry_entry_path") or ""),
        "chunkhound_command": _base_cmd(config_path, repo_path, binary=binary),
        "preflight_stage": str(preflight_stage or "").strip() or "unknown",
        "preflight_stage_status": str(preflight_stage_status or "").strip() or "unknown",
        "stage_trace": list(stage_trace),
        "elapsed_seconds": round(max(0.0, time.monotonic() - started_at), 3),
    }
    error_text = _trim_tail_text(error)
    if error_text:
        payload["error"] = error_text
    missing = sorted(str(name).strip() for name in (missing_tools or []) if str(name).strip())
    if missing:
        payload["missing_tools"] = missing
    stderr_text = _trim_tail_text(stderr_tail)
    if stderr_text:
        payload["stderr_tail"] = stderr_text
    daemon_metadata_error = str(daemon_meta.get("daemon_metadata_error") or "").strip()
    if daemon_metadata_error:
        payload["daemon_metadata_error"] = daemon_metadata_error
    return payload


def _copy_stage_trace(trace: object) -> list[dict[str, Any]]:
    if not isinstance(trace, list):
        return []
    return [dict(item) for item in trace if isinstance(item, dict)]


def _tool_payload_base(
    *,
    command: str,
    query: str | None,
    path: str | None,
    preflight: dict[str, Any],
    transport_mode: str,
    tool_name: str,
    stage_trace: list[dict[str, Any]],
    helper_path: str | Path | None,
) -> dict[str, Any]:
    payload = {
        "command": command,
        "tool_name": tool_name,
        "query": query,
        "path": path,
        "helper_path": str(helper_path or ""),
        "chunkhound_path": str(preflight.get("chunkhound_path") or ""),
        "chunkhound_runtime_python": str(preflight.get("chunkhound_runtime_python") or ""),
        "chunkhound_module_path": str(preflight.get("chunkhound_module_path") or ""),
        "daemon_lock_path": preflight.get("daemon_lock_path"),
        "daemon_socket_path": preflight.get("daemon_socket_path"),
        "daemon_log_path": preflight.get("daemon_log_path"),
        "daemon_pid": preflight.get("daemon_pid"),
        "daemon_runtime_dir": preflight.get("daemon_runtime_dir"),
        "daemon_registry_entry_path": preflight.get("daemon_registry_entry_path"),
        "mcp_transport": transport_mode,
        "preflight_stage": str(preflight.get("preflight_stage") or ""),
        "preflight_stage_status": str(preflight.get("preflight_stage_status") or ""),
        "stage_trace": stage_trace,
    }
    preflight_elapsed = preflight.get("elapsed_seconds")
    if isinstance(preflight_elapsed, (int, float)):
        payload["preflight_elapsed_seconds"] = round(float(preflight_elapsed), 3)
    stderr_tail = _trim_tail_text(preflight.get("stderr_tail") or "")
    if stderr_tail:
        payload["stderr_tail"] = stderr_tail
    daemon_metadata_error = str(preflight.get("daemon_metadata_error") or "").strip()
    if daemon_metadata_error:
        payload["daemon_metadata_error"] = daemon_metadata_error
    return payload


def _run_preflight(
    session: JsonRpcSession,
    *,
    config_path: str | Path,
    repo_path: str | Path,
    cwd: str | Path | None,
    binary: str,
    helper_path: str | Path | None,
    stage_timeouts: dict[str, float],
    emit_stage_lines: bool = True,
) -> dict[str, Any]:
    started_at = time.monotonic()
    stage_trace: list[dict[str, Any]] = []

    def _metadata() -> dict[str, Any]:
        return daemon_metadata_payload(
            repo_path,
            chunkhound_cwd=cwd,
            binary=binary,
            timeout=stage_timeouts["daemon_metadata"],
        )

    def _run_stage(stage: str, timeout_seconds: float, func: Any) -> tuple[bool, Any]:
        stage_started = time.monotonic()
        _emit_stage(stage, "running", enabled=emit_stage_lines)
        try:
            result = func()
        except PreflightStageError as exc:
            status = "timeout" if exc.timeout else "error"
            detail = str(exc)
            _emit_stage(stage, status, detail=detail, enabled=emit_stage_lines)
            stage_trace.append(
                _stage_trace_entry(
                    stage=stage,
                    status=status,
                    started_at=stage_started,
                    timeout_seconds=timeout_seconds,
                    detail=detail,
                )
            )
            return (
                False,
                _build_preflight_payload(
                    ok=False,
                    config_path=config_path,
                    repo_path=repo_path,
                    binary=binary,
                    helper_path=helper_path,
                    error=detail,
                    preflight_stage=stage,
                    preflight_stage_status=status,
                    stage_trace=stage_trace,
                    started_at=started_at,
                    daemon_meta=_metadata(),
                    stderr_tail=exc.stderr_tail,
                ),
            )
        except Exception as exc:
            detail = str(exc)
            _emit_stage(stage, "error", detail=detail, enabled=emit_stage_lines)
            stage_trace.append(
                _stage_trace_entry(
                    stage=stage,
                    status="error",
                    started_at=stage_started,
                    timeout_seconds=timeout_seconds,
                    detail=detail,
                )
            )
            return (
                False,
                _build_preflight_payload(
                    ok=False,
                    config_path=config_path,
                    repo_path=repo_path,
                    binary=binary,
                    helper_path=helper_path,
                    error=detail,
                    preflight_stage=stage,
                    preflight_stage_status="error",
                    stage_trace=stage_trace,
                    started_at=started_at,
                    daemon_meta=_metadata(),
                    stderr_tail=session._stderr_tail_text(),
                ),
            )
        _emit_stage(stage, "ok", enabled=emit_stage_lines)
        stage_trace.append(
            _stage_trace_entry(
                stage=stage,
                status="ok",
                started_at=stage_started,
                timeout_seconds=timeout_seconds,
            )
        )
        return True, result

    ok, spawn_payload = _run_stage(
        "spawn",
        stage_timeouts["spawn"],
        lambda: session.ensure_started(stage="spawn", timeout_seconds=stage_timeouts["spawn"]),
    )
    if not ok:
        return spawn_payload

    ok, init_response = _run_stage(
        "initialize",
        stage_timeouts["initialize"],
        lambda: session.request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "cure-chunkhound-helper", "version": "1"},
            },
            stage="initialize",
            timeout_seconds=stage_timeouts["initialize"],
        ),
    )
    if not ok:
        return init_response
    if "error" in init_response:
        detail = json.dumps(init_response["error"], sort_keys=True)
        _emit_stage("initialize", "error", detail=detail, enabled=emit_stage_lines)
        stage_trace.append(
            _stage_trace_entry(
                stage="initialize",
                status="error",
                started_at=started_at,
                timeout_seconds=stage_timeouts["initialize"],
                detail=detail,
            )
        )
        return _build_preflight_payload(
            ok=False,
            config_path=config_path,
            repo_path=repo_path,
            binary=binary,
            helper_path=helper_path,
            error=detail,
            preflight_stage="initialize",
            preflight_stage_status="error",
            stage_trace=stage_trace,
            started_at=started_at,
            daemon_meta=_metadata(),
            stderr_tail=session._stderr_tail_text(),
        )

    ok, notify_result = _run_stage(
        "notifications/initialized",
        stage_timeouts["notifications/initialized"],
        lambda: session.notify(
            "notifications/initialized",
            {},
            stage="notifications/initialized",
            timeout_seconds=stage_timeouts["notifications/initialized"],
        ),
    )
    if not ok:
        return notify_result

    ok, tools_response = _run_stage(
        "tools/list",
        stage_timeouts["tools/list"],
        lambda: session.request("tools/list", {}, stage="tools/list", timeout_seconds=stage_timeouts["tools/list"]),
    )
    if not ok:
        return tools_response
    if "error" in tools_response:
        detail = json.dumps(tools_response["error"], sort_keys=True)
        _emit_stage("tools/list", "error", detail=detail, enabled=emit_stage_lines)
        stage_trace.append(
            _stage_trace_entry(
                stage="tools/list",
                status="error",
                started_at=started_at,
                timeout_seconds=stage_timeouts["tools/list"],
                detail=detail,
            )
        )
        return _build_preflight_payload(
            ok=False,
            config_path=config_path,
            repo_path=repo_path,
            binary=binary,
            helper_path=helper_path,
            error=detail,
            preflight_stage="tools/list",
            preflight_stage_status="error",
            stage_trace=stage_trace,
            started_at=started_at,
            daemon_meta=_metadata(),
            stderr_tail=session._stderr_tail_text(),
        )

    tools_payload = tools_response.get("result") if isinstance(tools_response.get("result"), dict) else {}
    raw_tools = tools_payload.get("tools") if isinstance(tools_payload, dict) else []
    tools = raw_tools if isinstance(raw_tools, list) else []
    available = sorted(
        str(tool.get("name") or "").strip()
        for tool in tools
        if isinstance(tool, dict) and str(tool.get("name") or "").strip()
    )
    missing_tools = [name for name in ("search", "code_research") if name not in available]
    stage_started = time.monotonic()
    _emit_stage("tool_validation", "running", enabled=emit_stage_lines)
    if missing_tools:
        detail = "required ChunkHound tools are unavailable: " + ", ".join(missing_tools)
        _emit_stage("tool_validation", "error", detail=detail, enabled=emit_stage_lines)
        stage_trace.append(_stage_trace_entry(stage="tool_validation", status="error", started_at=stage_started, detail=detail))
        return _build_preflight_payload(
            ok=False,
            config_path=config_path,
            repo_path=repo_path,
            binary=binary,
            helper_path=helper_path,
            error=detail,
            available_tools=available,
            missing_tools=missing_tools,
            preflight_stage="tool_validation",
            preflight_stage_status="error",
            stage_trace=stage_trace,
            started_at=started_at,
            daemon_meta=_metadata(),
            stderr_tail=session._stderr_tail_text(),
        )
    _emit_stage("tool_validation", "ok", enabled=emit_stage_lines)
    stage_trace.append(_stage_trace_entry(stage="tool_validation", status="ok", started_at=stage_started))

    stage_started = time.monotonic()
    _emit_stage("daemon_metadata", "running", enabled=emit_stage_lines)
    daemon_meta = _metadata()
    daemon_metadata_error = str(daemon_meta.get("daemon_metadata_error") or "").strip()
    if daemon_metadata_error:
        _emit_stage("daemon_metadata", "error", detail=daemon_metadata_error, enabled=emit_stage_lines)
        stage_trace.append(
            _stage_trace_entry(
                stage="daemon_metadata",
                status="error",
                started_at=stage_started,
                timeout_seconds=stage_timeouts["daemon_metadata"],
                detail=daemon_metadata_error,
            )
        )
    else:
        _emit_stage("daemon_metadata", "ok", enabled=emit_stage_lines)
        stage_trace.append(
            _stage_trace_entry(
                stage="daemon_metadata",
                status="ok",
                started_at=stage_started,
                timeout_seconds=stage_timeouts["daemon_metadata"],
            )
        )

    _emit_stage("complete", "ok", enabled=emit_stage_lines)
    return _build_preflight_payload(
        ok=True,
        config_path=config_path,
        repo_path=repo_path,
        binary=binary,
        helper_path=helper_path,
        available_tools=available,
        preflight_stage="complete",
        preflight_stage_status="ok",
        stage_trace=stage_trace,
        started_at=started_at,
        daemon_meta=daemon_meta,
        stderr_tail=session._stderr_tail_text(),
    )


def _should_retry_with_alternate_transport(payload: dict[str, Any]) -> bool:
    if bool(payload.get("ok")):
        return False
    stage = str(payload.get("preflight_stage") or "").strip()
    status = str(payload.get("preflight_stage_status") or "").strip()
    return stage in {"initialize", "notifications/initialized", "tools/list"} and status in {"error", "timeout"}


def _normalized_stage_timeouts(stage_timeouts: dict[str, float] | None, timeout: float | None) -> dict[str, float]:
    merged = dict(_DEFAULT_PREFLIGHT_STAGE_TIMEOUTS)
    if stage_timeouts:
        merged.update({str(key): float(value) for key, value in stage_timeouts.items()})
    if timeout is not None:
        merged["initialize"] = float(timeout)
    return merged


def _normalized_tool_timeouts(tool_timeouts: dict[str, float] | None, timeout: float | None) -> dict[str, float]:
    merged = dict(_DEFAULT_TOOL_CALL_TIMEOUTS)
    if tool_timeouts:
        merged.update({str(key): float(value) for key, value in tool_timeouts.items()})
    if timeout is not None:
        for key in merged:
            merged[key] = float(timeout)
    return merged


def run_chunkhound_mcp_preflight_payload(
    config_path: str | Path,
    repo_path: str | Path,
    *,
    timeout: float | None = None,
    cwd: str | Path | None = None,
    binary: str = "chunkhound",
    helper_path: str | Path | None = None,
    stage_timeouts: dict[str, float] | None = None,
    transport_modes: tuple[str, ...] | None = None,
    heartbeat_provider: str = "claude",
    heartbeat_interval: float = _DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
) -> dict[str, Any]:
    active_timeouts = _normalized_stage_timeouts(stage_timeouts, timeout)
    active_transport_modes = transport_modes or _TRANSPORT_MODES
    last_payload: dict[str, Any] | None = None
    for idx, transport_mode in enumerate(active_transport_modes):
        session = JsonRpcSession(
            config_path=config_path,
            repo_path=repo_path,
            cwd=cwd,
            binary=binary,
            transport_mode=transport_mode,
            heartbeat_provider=heartbeat_provider,
            heartbeat_interval=heartbeat_interval,
        )
        try:
            payload = _run_preflight(
                session,
                config_path=config_path,
                repo_path=repo_path,
                cwd=cwd,
                binary=binary,
                helper_path=helper_path,
                stage_timeouts=active_timeouts,
            )
        finally:
            session.close()
        payload["mcp_transport"] = transport_mode
        if payload.get("ok"):
            return payload
        last_payload = payload
        if idx + 1 >= len(active_transport_modes) or not _should_retry_with_alternate_transport(payload):
            return payload
    return last_payload or {"ok": False, "command": "preflight", "error": "no transport modes available"}


def run_chunkhound_mcp_preflight(
    config_path: str | Path,
    repo_path: str | Path,
    timeout: float = 30.0,
) -> ChunkHoundPreflightResult:
    payload = run_chunkhound_mcp_preflight_payload(config_path, repo_path, timeout=timeout)
    if not payload.get("ok"):
        raise ChunkHoundPreflightError(
            str(payload.get("preflight_stage") or "unknown"),
            str(payload.get("error") or "ChunkHound preflight failed"),
            payload=payload,
        )
    return ChunkHoundPreflightResult.from_payload(payload)


def run_chunkhound_tool_payload(
    config_path: str | Path,
    repo_path: str | Path,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    timeout: float | None = None,
    cwd: str | Path | None = None,
    binary: str = "chunkhound",
    helper_path: str | Path | None = None,
    stage_timeouts: dict[str, float] | None = None,
    tool_timeouts: dict[str, float] | None = None,
    transport_modes: tuple[str, ...] | None = None,
    heartbeat_provider: str = "claude",
    heartbeat_interval: float = _DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    skip_preflight: bool = False,
) -> dict[str, Any]:
    active_stage_timeouts = _normalized_stage_timeouts(stage_timeouts, None)
    active_tool_timeouts = _normalized_tool_timeouts(tool_timeouts, timeout)
    active_transport_modes = transport_modes or _TRANSPORT_MODES
    requested_tool_name = "code_research" if str(tool_name).strip() in {"research", "code_research"} else "search"
    command = "research" if requested_tool_name == "code_research" else "search"
    query = str(arguments.get("query") or "")
    path = str(arguments.get("path") or "").strip() or None
    last_payload: dict[str, Any] | None = None
    for idx, transport_mode in enumerate(active_transport_modes):
        session = JsonRpcSession(
            config_path=config_path,
            repo_path=repo_path,
            cwd=cwd,
            binary=binary,
            transport_mode=transport_mode,
            heartbeat_provider=heartbeat_provider,
            heartbeat_interval=heartbeat_interval,
        )
        try:
            if skip_preflight:
                try:
                    session.ensure_started(stage="spawn", timeout_seconds=active_stage_timeouts["spawn"])
                    session.request(
                        "initialize",
                        {
                            "protocolVersion": "2025-03-26",
                            "capabilities": {},
                            "clientInfo": {"name": "cure-chunkhound-helper", "version": "1"},
                        },
                        stage="initialize",
                        timeout_seconds=active_stage_timeouts["initialize"],
                    )
                    session.notify(
                        "notifications/initialized",
                        {},
                        stage="notifications/initialized",
                        timeout_seconds=active_stage_timeouts["notifications/initialized"],
                    )
                except PreflightStageError as exc:
                    preflight = {
                        "ok": False,
                        "preflight_stage": exc.stage,
                        "preflight_stage_status": "timeout" if exc.timeout else "error",
                        "error": str(exc),
                        "session": session,
                        "stage_trace": [],
                        "available_tools": [],
                    }
                except Exception as exc:
                    preflight = {
                        "ok": False,
                        "preflight_stage": "initialize",
                        "preflight_stage_status": "error",
                        "error": str(exc),
                        "session": session,
                        "stage_trace": [],
                        "available_tools": [],
                    }
                else:
                    preflight = {"ok": True, "session": session, "stage_trace": [], "available_tools": ["search", "code_research"]}
            else:
                preflight = _run_preflight(
                    session,
                    config_path=config_path,
                    repo_path=repo_path,
                    cwd=cwd,
                    binary=binary,
                    helper_path=helper_path,
                    stage_timeouts=active_stage_timeouts,
                    emit_stage_lines=False,
                )
            if not preflight.get("ok"):
                payload = {
                    **preflight,
                    "mcp_transport": transport_mode,
                    "command": command,
                    "tool_name": requested_tool_name,
                    "query": query,
                    "path": path,
                }
            else:
                call_arguments = dict(arguments)
                tool_timeout_seconds = float(active_tool_timeouts.get(requested_tool_name, active_tool_timeouts["search"]))
                stage_trace = _copy_stage_trace(preflight.get("stage_trace"))
                stage_started = time.monotonic()
                base_payload = _tool_payload_base(
                    command=command,
                    query=query,
                    path=path,
                    preflight=preflight,
                    transport_mode=transport_mode,
                    tool_name=requested_tool_name,
                    stage_trace=stage_trace,
                    helper_path=helper_path,
                )
                try:
                    response = session.request(
                        "tools/call",
                        {"name": requested_tool_name, "arguments": call_arguments},
                        stage="tools/call",
                        timeout_seconds=tool_timeout_seconds,
                        heartbeat_enabled=True,
                    )
                    result = _extract_result_content(response)
                except PreflightStageError as exc:
                    stage_status = "timeout" if exc.timeout else "error"
                    detail = str(exc)
                    stage_trace.append(
                        _stage_trace_entry(
                            stage="tools/call",
                            status=stage_status,
                            started_at=stage_started,
                            timeout_seconds=tool_timeout_seconds,
                            detail=detail,
                        )
                    )
                    payload = {
                        **base_payload,
                        "ok": False,
                        "error": detail,
                        "execution_stage": "tools/call",
                        "execution_stage_status": stage_status,
                        "execution_timeout_seconds": tool_timeout_seconds,
                    }
                    stderr_tail = _trim_tail_text(exc.stderr_tail)
                    if stderr_tail:
                        payload["stderr_tail"] = stderr_tail
                except Exception as exc:
                    detail = str(exc)
                    stage_trace.append(
                        _stage_trace_entry(
                            stage="tools/call",
                            status="error",
                            started_at=stage_started,
                            timeout_seconds=tool_timeout_seconds,
                            detail=detail,
                        )
                    )
                    payload = {
                        **base_payload,
                        "ok": False,
                        "error": detail,
                        "execution_stage": "tools/call",
                        "execution_stage_status": "error",
                        "execution_timeout_seconds": tool_timeout_seconds,
                    }
                    stderr_tail = _trim_tail_text(session._stderr_tail_text())
                    if stderr_tail:
                        payload["stderr_tail"] = stderr_tail
                else:
                    stage_trace.append(
                        _stage_trace_entry(
                            stage="tools/call",
                            status="ok",
                            started_at=stage_started,
                            timeout_seconds=tool_timeout_seconds,
                        )
                    )
                    payload = {
                        **base_payload,
                        "ok": True,
                        "result": result,
                        "execution_stage": "tools/call",
                        "execution_stage_status": "ok",
                        "execution_timeout_seconds": tool_timeout_seconds,
                    }
        finally:
            session.close()
        if payload.get("ok"):
            return payload
        last_payload = payload
        if idx + 1 >= len(active_transport_modes) or not _should_retry_with_alternate_transport(payload):
            return payload
    return last_payload or {
        "ok": False,
        "command": command,
        "tool_name": requested_tool_name,
        "query": query,
        "path": path,
        "error": "no transport modes available",
    }


def run_chunkhound_tool(
    config_path: str | Path,
    repo_path: str | Path,
    tool_name: str,
    arguments: dict[str, Any],
    timeout: float = 60.0,
    skip_preflight: bool = False,
) -> dict[str, Any]:
    return run_chunkhound_tool_payload(config_path, repo_path, tool_name, arguments, timeout=timeout, skip_preflight=skip_preflight)
