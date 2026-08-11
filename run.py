from __future__ import annotations

import codecs
import hashlib
import os
import signal
import subprocess
import sys
import tempfile
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from threading import Condition, Lock, Thread
from typing import Any, BinaryIO, Iterator, Literal, TextIO


class ReviewflowSubprocessError(RuntimeError):
    def __init__(
        self,
        *,
        cmd: list[str],
        cwd: Path | None,
        exit_code: int,
        stdout: str,
        stderr: str,
    ) -> None:
        super().__init__(f"Command failed ({exit_code}): {' '.join(cmd)}")
        self.cmd = cmd
        self.cwd = cwd
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


class ReviewflowCommandDrainError(ReviewflowSubprocessError):
    """Raised when a command exits but its stdout/stderr pipes stay open past the
    bounded post-exit drain deadline (a descendant inherited the write ends)."""

    def __init__(
        self,
        *,
        cmd: list[str],
        cwd: Path | None,
        stdout: str,
        stderr: str,
        deadline_seconds: float,
    ) -> None:
        self.cmd = cmd
        self.cwd = cwd
        # exit_code -1 is a sentinel: the process group was terminated, so no
        # ordinary exit status exists.
        self.exit_code = -1
        self.stdout = stdout
        self.stderr = stderr
        self.deadline_seconds = deadline_seconds
        RuntimeError.__init__(
            self,
            "Command stdout/stderr pipes did not reach EOF within "
            f"{deadline_seconds:g}s of exit (a descendant holds them open); "
            f"process group terminated: {' '.join(cmd)}",
        )


@dataclass(frozen=True)
class CommandResult:
    cmd: list[str]
    cwd: Path | None
    exit_code: int
    duration_seconds: float
    stdout: str
    stderr: str


OwnedProcessRole = Literal["review-provider", "chunkhound-helper"]
_ALLOWED_OWNED_PROCESS_ROLES = frozenset({"review-provider", "chunkhound-helper"})

# Bounded post-exit drain for stdout/stderr pipes: once the command itself has
# exited, readers wait at most this long for EOF. A descendant which inherited
# the pipe write ends keeps EOF from arriving; the process group is then
# terminated (SIGTERM then SIGKILL) and the run is reported as a failure.
_PIPE_EOF_DRAIN_SECONDS = 12.0


class OwnedProcessRegistryState(Enum):
    OPEN = auto()
    CLOSING = auto()
    CLOSED = auto()


class OwnedProcessRegistryClosingError(RuntimeError):
    """Raised when an owned process is requested after teardown has begun."""


class OwnedProcessRegistryCleanupError(RuntimeError):
    """Raised when an owned process group cannot be fully drained."""


class OwnedProcessPipeCoordinator:
    """Coordinates sole-reader pipe pumps with command-scoped teardown."""

    def __init__(self, *, manual_reader_reserved: bool = False) -> None:
        self._condition = Condition()
        self._pumps: tuple[Thread, Thread] | None = None
        self._complete = False
        self._manual_reader_mode = manual_reader_reserved
        self._manual_reader_active = manual_reader_reserved

    def attach_and_start(self, stdout_pump: Thread, stderr_pump: Thread) -> None:
        with self._condition:
            if self._pumps is not None:
                raise RuntimeError("owned process pipe pumps are already attached")
            self._pumps = (stdout_pump, stderr_pump)
            stdout_pump.start()
            stderr_pump.start()
            self._condition.notify_all()

    def complete(self, process: subprocess.Popen[Any]) -> None:
        with self._condition:
            pumps = self._pumps
            if process.poll() is None or pumps is None or any(
                pump.ident is None or pump.is_alive() for pump in pumps
            ):
                raise RuntimeError(
                    "owned process completion requires exit and both drained pumps"
                )
            self._complete = True
            self._condition.notify_all()

    def require_completed(self, process: subprocess.Popen[Any]) -> None:
        """Require normal process exit and sole-reader drain completion."""
        with self._condition:
            if process.poll() is None or not self._complete:
                raise RuntimeError(
                    "owned process unregister requires exit and drained pipes"
                )

    def release_manual_reader(self) -> None:
        """Transfer sole pipe ownership to bounded registry teardown."""
        with self._condition:
            if not self._manual_reader_mode:
                raise RuntimeError("manual reader ownership was not reserved")
            self._manual_reader_active = False
            self._condition.notify_all()

    def complete_manual_reader(self, process: subprocess.Popen[Any]) -> None:
        """Record normal exit after the manual reader drained and closed both pipes."""
        with self._condition:
            streams = (process.stdout, process.stderr)
            if (
                not self._manual_reader_mode
                or not self._manual_reader_active
                or process.poll() is None
                or any(stream is None or not stream.closed for stream in streams)
            ):
                raise RuntimeError(
                    "manual completion requires exit and both drained closed pipes"
                )
            self._manual_reader_active = False
            self._complete = True
            self._condition.notify_all()

    @staticmethod
    def _drain_stream(stream: Any) -> None:
        if stream is None:
            return
        try:
            while stream.read(8192):
                pass
        finally:
            stream.close()

    def drain(self, process: subprocess.Popen[Any], *, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            while self._manual_reader_active and not self._complete:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(timeout=remaining)
            if self._complete:
                return True
            if self._pumps is None:
                # If BaseException interrupted run_cmd before its pumps attached,
                # teardown atomically claims the pipes and becomes their drain owner.
                stdout_pump = Thread(
                    target=self._drain_stream,
                    args=(process.stdout,),
                    daemon=True,
                )
                stderr_pump = Thread(
                    target=self._drain_stream,
                    args=(process.stderr,),
                    daemon=True,
                )
                self._pumps = (stdout_pump, stderr_pump)
                stdout_pump.start()
                stderr_pump.start()
                self._condition.notify_all()
            pumps = self._pumps
            for pump in pumps:
                # BaseException can interrupt attach_and_start before either
                # start, or after only the first. Teardown retains the original
                # sole-reader threads and starts only those never launched.
                if pump.ident is None:
                    pump.start()
            self._condition.notify_all()
        assert pumps is not None
        try:
            process.wait(timeout=max(0.0, deadline - time.monotonic()))
        except (OSError, subprocess.TimeoutExpired):
            return False
        for pump in pumps:
            pump.join(max(0.0, deadline - time.monotonic()))
        if any(pump.is_alive() for pump in pumps):
            return False
        with self._condition:
            self._complete = True
            self._condition.notify_all()
        return True


@dataclass(frozen=True)
class OwnedProcessRecord:
    """Published owned leader and its optional sole-reader coordination seam."""

    process: subprocess.Popen[Any]
    pipe_coordinator: OwnedProcessPipeCoordinator | None


class OwnedProcessRegistry:
    """Synchronized ownership of narrowly tagged Linux process groups."""

    def __init__(self) -> None:
        self._condition = Condition()
        self._state = OwnedProcessRegistryState.OPEN
        self._processes: list[subprocess.Popen[Any]] = []
        self._records: dict[int, OwnedProcessRecord] = {}
        self._cleanup_error: BaseException | None = None

    @property
    def state(self) -> OwnedProcessRegistryState:
        # Enum reference reads are atomic; avoiding the lifecycle lock also makes
        # an in-progress spawn observably OPEN until publication completes.
        return self._state

    def spawn(
        self,
        *,
        role: OwnedProcessRole,
        cmd: list[str],
        pipe_coordinator: OwnedProcessPipeCoordinator | None = None,
        **popen_options: Any,
    ) -> subprocess.Popen[Any]:
        if role not in _ALLOWED_OWNED_PROCESS_ROLES:
            raise ValueError(f"unsupported owned process role: {role!r}")

        options = dict(popen_options)
        options["start_new_session"] = True
        with self._condition:
            if self._state is not OwnedProcessRegistryState.OPEN:
                raise OwnedProcessRegistryClosingError("owned process registry is closing")

            process: subprocess.Popen[Any] | None = None
            try:
                process = subprocess.Popen(cmd, **options)
                self._processes.append(process)
                self._records[id(process)] = OwnedProcessRecord(
                    process=process,
                    pipe_coordinator=pipe_coordinator,
                )
                return process
            except BaseException:
                if process is not None:
                    try:
                        self._processes.remove(process)
                    except ValueError:
                        pass
                    self._records.pop(id(process), None)
                    self._locally_terminate_and_drain(process)
                raise

    def unregister(self, process: subprocess.Popen[Any]) -> None:
        """Forget a normally completed process after its pipes have been drained."""
        with self._condition:
            if self._state is OwnedProcessRegistryState.OPEN:
                record = self._records.get(id(process))
                if record is not None:
                    if record.pipe_coordinator is None:
                        raise RuntimeError(
                            "owned process unregister requires pipe coordination"
                        )
                    record.pipe_coordinator.require_completed(process)
                    try:
                        self._processes.remove(process)
                    except ValueError:
                        pass
                    self._records.pop(id(process), None)
            self._condition.notify_all()

    def terminate_and_drain(
        self,
        *,
        term_timeout_seconds: float = 5.0,
        kill_timeout_seconds: float = 2.0,
        drain_timeout_seconds: float = 2.0,
    ) -> None:
        with self._condition:
            if self._state is OwnedProcessRegistryState.CLOSING:
                self._condition.wait_for(
                    lambda: self._state is OwnedProcessRegistryState.CLOSED
                )
                if self._cleanup_error is not None:
                    raise self._cleanup_error
                return
            if self._state is OwnedProcessRegistryState.CLOSED:
                if self._cleanup_error is not None:
                    raise self._cleanup_error
                return

            self._state = OwnedProcessRegistryState.CLOSING
            snapshot = tuple(self._processes)
            pipe_coordinators = {
                id(process): (
                    self._records[id(process)].pipe_coordinator
                    if id(process) in self._records
                    else None
                )
                for process in snapshot
            }

        cleanup_error: BaseException | None = None
        try:
            self._terminate_snapshot(
                snapshot,
                term_timeout_seconds=max(0.0, term_timeout_seconds),
                kill_timeout_seconds=max(0.0, kill_timeout_seconds),
                drain_timeout_seconds=max(0.0, drain_timeout_seconds),
                pipe_coordinators=pipe_coordinators,
            )
        except BaseException as exc:
            # Closing is idempotent for every cleanup failure category,
            # including interruption: repeat callers observe the same outcome.
            cleanup_error = exc
        finally:
            with self._condition:
                self._processes.clear()
                self._records.clear()
                self._cleanup_error = cleanup_error
                self._state = OwnedProcessRegistryState.CLOSED
                self._condition.notify_all()

        if cleanup_error is not None:
            raise cleanup_error

    @classmethod
    def _locally_terminate_and_drain(cls, process: subprocess.Popen[Any]) -> None:
        try:
            cls._terminate_snapshot(
                (process,),
                term_timeout_seconds=5.0,
                kill_timeout_seconds=2.0,
                drain_timeout_seconds=2.0,
            )
        except BaseException:
            # The exception which interrupted publication remains authoritative.
            pass

    @classmethod
    def _terminate_snapshot(
        cls,
        processes: tuple[subprocess.Popen[Any], ...],
        *,
        term_timeout_seconds: float,
        kill_timeout_seconds: float,
        drain_timeout_seconds: float,
        pipe_coordinators: dict[int, OwnedProcessPipeCoordinator | None] | None = None,
    ) -> None:
        groups = tuple(dict.fromkeys(process.pid for process in processes))
        for pgid in groups:
            cls._signal_group(pgid, signal.SIGTERM)

        cls._wait_for_groups(groups, term_timeout_seconds, processes)
        survivors = tuple(pgid for pgid in groups if cls._group_exists(pgid))
        for pgid in survivors:
            cls._signal_group(pgid, signal.SIGKILL)
        cls._wait_for_groups(survivors, kill_timeout_seconds, processes)

        drain_deadline = time.monotonic() + drain_timeout_seconds
        undrained: list[int] = []
        for process in processes:
            remaining = max(0.0, drain_deadline - time.monotonic())
            coordinator = (
                pipe_coordinators.get(id(process))
                if pipe_coordinators is not None
                else None
            )
            if coordinator is not None:
                if not coordinator.drain(process, timeout_seconds=remaining):
                    undrained.append(process.pid)
                continue
            try:
                process.communicate(timeout=remaining)
            except (OSError, ValueError):
                # A caller may already have closed a pipe; still require process exit.
                try:
                    process.wait(timeout=remaining)
                except (OSError, subprocess.TimeoutExpired):
                    undrained.append(process.pid)
            except subprocess.TimeoutExpired:
                undrained.append(process.pid)

        surviving_groups = [pgid for pgid in groups if cls._group_exists(pgid)]
        if surviving_groups or undrained:
            raise OwnedProcessRegistryCleanupError(
                "owned process cleanup did not finish within its bounded budgets"
            )

    @staticmethod
    def _signal_group(pgid: int, sig: signal.Signals) -> None:
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            pass

    @staticmethod
    def _group_exists(pgid: int) -> bool:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    @classmethod
    def _wait_for_groups(
        cls,
        groups: tuple[int, ...],
        timeout_seconds: float,
        processes: tuple[subprocess.Popen[Any], ...],
    ) -> None:
        deadline = time.monotonic() + timeout_seconds
        while any(cls._group_exists(pgid) for pgid in groups):
            # Reap group leaders promptly so exited groups are not mistaken for
            # survivors for the whole budget. Descendants remain visible by PGID.
            for process in processes:
                process.poll()
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                return
            time.sleep(min(0.01, remaining))


class LosslessCommandCaptureError(RuntimeError):
    """Base class for lossless command-capture failures."""


class LosslessCommandCaptureDisposedError(LosslessCommandCaptureError):
    """Raised when a disposed capture is accessed."""


class LosslessCommandCaptureNotSealedError(LosslessCommandCaptureError):
    """Raised when complete output is requested before sealing."""


class LosslessCommandCaptureIntegrityError(LosslessCommandCaptureError):
    """Raised when a capture cannot be written, sealed, or verified."""


class LosslessCommandCaptureState(Enum):
    OPEN = auto()
    SEALED = auto()
    DISPOSED = auto()


class LosslessCommandCapture:
    """Owner-managed, bounded-memory stdout/stderr spool capture."""

    _DEFAULT_CHUNK_CHARS = 64 * 1024

    def __init__(self, *, spool_dir: Path) -> None:
        self._lock = Lock()
        self._state = LosslessCommandCaptureState.OPEN
        self._stdout_path: Path | None = None
        self._stderr_path: Path | None = None
        self._stdout_file: BinaryIO | None = None
        self._stderr_file: BinaryIO | None = None
        self._digests = {
            "stdout": hashlib.sha256(),
            "stderr": hashlib.sha256(),
        }
        self._sealed_sizes: dict[str, int] = {}
        self._sealed_digests: dict[str, bytes] = {}

        try:
            spool_dir.mkdir(parents=True, exist_ok=True)
            self._stdout_path, self._stdout_file = self._new_spool(
                spool_dir, "stdout"
            )
            self._stderr_path, self._stderr_file = self._new_spool(
                spool_dir, "stderr"
            )
        except Exception as exc:
            self._close_and_unlink_constructor_artifacts()
            raise LosslessCommandCaptureIntegrityError(
                "failed to create private command-capture spools"
            ) from exc

    @staticmethod
    def _new_spool(spool_dir: Path, stream: str) -> tuple[Path, BinaryIO]:
        fd, raw_path = tempfile.mkstemp(
            prefix=f"cure-command-{stream}-", suffix=".spool", dir=spool_dir
        )
        try:
            os.fchmod(fd, 0o600)
            return Path(raw_path), os.fdopen(fd, "wb")
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            Path(raw_path).unlink(missing_ok=True)
            raise

    def _close_and_unlink_constructor_artifacts(self) -> None:
        for file_handle in (self._stdout_file, self._stderr_file):
            if file_handle is not None:
                try:
                    file_handle.close()
                except OSError:
                    pass
        for path in (self._stdout_path, self._stderr_path):
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass

    @property
    def state(self) -> LosslessCommandCaptureState:
        return self._state

    @property
    def sealed(self) -> bool:
        return self._state is LosslessCommandCaptureState.SEALED

    @property
    def stdout_path(self) -> Path:
        return self._path_for("stdout")

    @property
    def stderr_path(self) -> Path:
        return self._path_for("stderr")

    def _path_for(self, stream: str) -> Path:
        with self._lock:
            self._require_not_disposed()
            path = self._stdout_path if stream == "stdout" else self._stderr_path
            assert path is not None
            return path

    def _require_not_disposed(self) -> None:
        if self._state is LosslessCommandCaptureState.DISPOSED:
            raise LosslessCommandCaptureDisposedError(
                "lossless command capture has been disposed"
            )

    def write_stdout(self, text: str) -> None:
        self._write("stdout", text)

    def write_stderr(self, text: str) -> None:
        self._write("stderr", text)

    def _write(self, stream: str, text: str) -> None:
        data = text.encode("utf-8")
        with self._lock:
            self._require_not_disposed()
            if self._state is not LosslessCommandCaptureState.OPEN:
                raise LosslessCommandCaptureIntegrityError(
                    f"cannot write {stream} after capture has been sealed"
                )
            file_handle = (
                self._stdout_file if stream == "stdout" else self._stderr_file
            )
            assert file_handle is not None
            try:
                written = file_handle.write(data)
            except (OSError, ValueError) as exc:
                raise LosslessCommandCaptureIntegrityError(
                    f"failed to write lossless {stream} capture"
                ) from exc
            if written != len(data):
                raise LosslessCommandCaptureIntegrityError(
                    f"short write to lossless {stream} capture"
                )
            self._digests[stream].update(data)

    def seal(self) -> None:
        with self._lock:
            self._require_not_disposed()
            if self._state is LosslessCommandCaptureState.SEALED:
                raise LosslessCommandCaptureIntegrityError(
                    "lossless command capture is already sealed"
                )

            failures: list[BaseException] = []
            for stream, file_handle in (
                ("stdout", self._stdout_file),
                ("stderr", self._stderr_file),
            ):
                assert file_handle is not None
                try:
                    file_handle.flush()
                    os.fsync(file_handle.fileno())
                    self._sealed_sizes[stream] = file_handle.tell()
                except (OSError, ValueError) as exc:
                    failures.append(exc)
                finally:
                    try:
                        file_handle.close()
                    except OSError as exc:
                        failures.append(exc)
                self._sealed_digests[stream] = self._digests[stream].digest()

            if failures:
                raise LosslessCommandCaptureIntegrityError(
                    "failed to seal lossless command capture"
                ) from failures[0]
            self._state = LosslessCommandCaptureState.SEALED

    def iter_stdout_chunks(
        self, chunk_chars: int = _DEFAULT_CHUNK_CHARS
    ) -> Iterator[str]:
        return self._iter_chunks("stdout", chunk_chars)

    def iter_stderr_chunks(
        self, chunk_chars: int = _DEFAULT_CHUNK_CHARS
    ) -> Iterator[str]:
        return self._iter_chunks("stderr", chunk_chars)

    def _iter_chunks(self, stream: str, chunk_chars: int) -> Iterator[str]:
        if chunk_chars <= 0:
            raise ValueError("chunk_chars must be greater than zero")
        with self._lock:
            self._require_not_disposed()
            if self._state is not LosslessCommandCaptureState.SEALED:
                raise LosslessCommandCaptureNotSealedError(
                    "lossless command capture must be sealed before reading"
                )
            path = self._stdout_path if stream == "stdout" else self._stderr_path
            assert path is not None
            expected_size = self._sealed_sizes[stream]
            expected_digest = self._sealed_digests[stream]

        def chunks() -> Iterator[str]:
            digest = hashlib.sha256()
            size = 0
            decoder = codecs.getincrementaldecoder("utf-8")("strict")
            try:
                with path.open("rb") as file_handle:
                    while raw_chunk := file_handle.read(chunk_chars):
                        size += len(raw_chunk)
                        digest.update(raw_chunk)
                        decoded = decoder.decode(raw_chunk, final=False)
                        if decoded:
                            yield decoded
                    final_text = decoder.decode(b"", final=True)
                    if final_text:
                        yield final_text
            except (OSError, UnicodeError) as exc:
                raise LosslessCommandCaptureIntegrityError(
                    f"failed to read lossless {stream} capture"
                ) from exc
            if size != expected_size or digest.digest() != expected_digest:
                raise LosslessCommandCaptureIntegrityError(
                    f"lossless {stream} capture failed integrity verification"
                )

        return chunks()

    def dispose(self) -> None:
        with self._lock:
            if self._state is LosslessCommandCaptureState.DISPOSED:
                return
            self._state = LosslessCommandCaptureState.DISPOSED
            failures: list[BaseException] = []
            for file_handle in (self._stdout_file, self._stderr_file):
                if file_handle is not None and not file_handle.closed:
                    try:
                        file_handle.close()
                    except OSError as exc:
                        failures.append(exc)
            for path in (self._stdout_path, self._stderr_path):
                if path is not None:
                    try:
                        path.unlink(missing_ok=True)
                    except OSError as exc:
                        failures.append(exc)
            if failures:
                raise LosslessCommandCaptureIntegrityError(
                    "failed to dispose lossless command capture"
                ) from failures[0]


class _TailBuffer:
    def __init__(self, max_chars: int) -> None:
        self._max_chars = max(0, int(max_chars))
        self._chunks: deque[str] = deque()
        self._size = 0

    def append(self, text: str) -> None:
        if not text or self._max_chars == 0:
            return
        if len(text) >= self._max_chars:
            self._chunks.clear()
            self._chunks.append(text[-self._max_chars :])
            self._size = self._max_chars
            return
        self._chunks.append(text)
        self._size += len(text)
        while self._size > self._max_chars and self._chunks:
            overflow = self._size - self._max_chars
            first = self._chunks[0]
            if len(first) <= overflow:
                self._chunks.popleft()
                self._size -= len(first)
            else:
                self._chunks[0] = first[overflow:]
                self._size -= overflow

    def get(self) -> str:
        if not self._chunks:
            return ""
        return "".join(self._chunks)


def _terminate_pipe_holder_group(process: subprocess.Popen[Any]) -> None:
    """Terminate the process group keeping a command's pipes open (SIGTERM then SIGKILL).

    Spawns use start_new_session=True, so the direct child is its own group
    leader and any descendant which inherited the pipe write ends dies with it.
    """
    group = process.pid
    OwnedProcessRegistry._signal_group(group, signal.SIGTERM)
    OwnedProcessRegistry._wait_for_groups((group,), 5.0, (process,))
    if OwnedProcessRegistry._group_exists(group):
        OwnedProcessRegistry._signal_group(group, signal.SIGKILL)
        OwnedProcessRegistry._wait_for_groups((group,), 2.0, (process,))


def _drain_readers_bounded(
    readers: tuple[Thread, ...],
    *,
    deadline_seconds: float,
) -> bool:
    """Wait for pipe reader threads to reach EOF within one shared deadline."""
    deadline = time.monotonic() + max(0.0, float(deadline_seconds))
    for reader in readers:
        reader.join(max(0.0, deadline - time.monotonic()))
    return not any(reader.is_alive() for reader in readers)


def run_cmd(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
    stream: bool = False,
    stream_to: TextIO | None = None,
    stderr_stream: TextIO | None = None,
    stream_label: str | None = None,
    capture_tail_chars: int = 200_000,
    lossless_capture: LosslessCommandCapture | None = None,
    owned_processes: OwnedProcessRegistry | None = None,
    owned_role: OwnedProcessRole | None = None,
) -> CommandResult:
    """Run a command, optionally streaming stdout live.

    When ``stderr_stream`` is set, stderr bytes go there instead of into
    ``stream_to`` — required for JSON-streaming consumers (a codex stderr
    diagnostic landing between chunks of a large JSON event would otherwise
    corrupt the parse).
    """
    if (owned_processes is None) != (owned_role is None):
        raise ValueError("owned_processes and owned_role must be supplied together")
    tagged = owned_processes is not None
    started = time.perf_counter()
    if not tagged and not stream and lossless_capture is None:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=env,
            text=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        assert proc.stdout is not None
        assert proc.stderr is not None
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []

        def read_until_eof(stream: TextIO, chunks: list[str]) -> None:
            try:
                while chunk := stream.read(8192):
                    chunks.append(chunk)
            finally:
                try:
                    stream.close()
                except OSError:
                    pass

        readers: list[Thread] = []
        for pipe_stream, chunks in (
            (proc.stdout, stdout_chunks),
            (proc.stderr, stderr_chunks),
        ):
            reader = Thread(
                target=read_until_eof, args=(pipe_stream, chunks), daemon=True
            )
            reader.start()
            readers.append(reader)
        try:
            # Unbounded: a command which never exits keeps today's semantics
            # (callers already handle that case). Only the post-exit pipe drain
            # below is bounded.
            exit_code = int(proc.wait())
        except BaseException:
            # Best-effort group termination so interrupted children do not linger.
            _terminate_pipe_holder_group(proc)
            raise
        if not _drain_readers_bounded(
            tuple(readers), deadline_seconds=_PIPE_EOF_DRAIN_SECONDS
        ):
            _terminate_pipe_holder_group(proc)
            _drain_readers_bounded(tuple(readers), deadline_seconds=2.0)
            raise ReviewflowCommandDrainError(
                cmd=cmd,
                cwd=cwd,
                stdout="".join(stdout_chunks),
                stderr="".join(stderr_chunks),
                deadline_seconds=_PIPE_EOF_DRAIN_SECONDS,
            )
        duration = time.perf_counter() - started

        result = CommandResult(
            cmd=cmd,
            cwd=cwd,
            exit_code=exit_code,
            duration_seconds=float(duration),
            stdout="".join(stdout_chunks),
            stderr="".join(stderr_chunks),
        )
    else:
        out = stream_to or sys.stderr
        write_lock = Lock()
        failure_lock = Lock()
        pump_failures: list[tuple[str, BaseException]] = []

        stdout_tail = _TailBuffer(capture_tail_chars)
        stderr_tail = _TailBuffer(capture_tail_chars)

        prefix = f"[{stream_label}] " if stream_label else ""

        popen_options: dict[str, Any] = {
            "cwd": str(cwd) if cwd else None,
            "env": env,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "bufsize": 1,
        }
        if not tagged:
            # Untagged groups need a leader of their own so a pipe-holding
            # descendant can be terminated with the group (killpg machinery).
            popen_options["start_new_session"] = True
        pipe_coordinator = OwnedProcessPipeCoordinator() if tagged else None
        if tagged:
            assert owned_processes is not None
            assert owned_role is not None
            proc = owned_processes.spawn(
                role=owned_role,
                cmd=cmd,
                pipe_coordinator=pipe_coordinator,
                **popen_options,
            )
        else:
            proc = subprocess.Popen(cmd, **popen_options)

        assert proc.stdout is not None
        assert proc.stderr is not None

        def record_pump_failure(stream_name: str, exc: BaseException) -> None:
            with failure_lock:
                pump_failures.append((stream_name, exc))

        def write_live(chunk: str, *, at_line_start: bool, sink: TextIO) -> bool:
            if not prefix:
                sink.write(chunk)
                return chunk.endswith("\n")
            segments = chunk.splitlines(keepends=True)
            for segment in segments:
                if at_line_start:
                    sink.write(prefix)
                sink.write(segment)
                at_line_start = segment.endswith(("\n", "\r"))
            return at_line_start

        def pump(
            src: TextIO,
            *,
            stream_name: str,
            tail: _TailBuffer,
            capture_write: Any,
            sink: TextIO,
        ) -> None:
            at_line_start = True
            failed = False
            try:
                while chunk := src.read(8192):
                    if not failed:
                        try:
                            if capture_write is not None:
                                capture_write(chunk)
                            tail.append(chunk)
                            if stream:
                                with write_lock:
                                    at_line_start = write_live(
                                        chunk, at_line_start=at_line_start, sink=sink
                                    )
                                    sink.flush()
                        except BaseException as exc:
                            failed = True
                            record_pump_failure(stream_name, exc)
            except BaseException as exc:
                record_pump_failure(stream_name, exc)
            finally:
                try:
                    src.close()
                except BaseException as exc:
                    record_pump_failure(stream_name, exc)

        stdout_write = (
            lossless_capture.write_stdout if lossless_capture is not None else None
        )
        stderr_write = (
            lossless_capture.write_stderr if lossless_capture is not None else None
        )
        # JSON-streaming consumers (codex events) must never receive stderr:
        # a diagnostic landing between chunks of a large JSON event corrupts
        # the parse. Route it to its own stream when one is provided.
        stderr_sink = stderr_stream if (stderr_stream is not None and stream) else out
        t_out = Thread(
            target=pump,
            args=(proc.stdout,),
            kwargs={
                "stream_name": "stdout",
                "tail": stdout_tail,
                "capture_write": stdout_write,
                "sink": out,
            },
        )
        t_err = Thread(
            target=pump,
            args=(proc.stderr,),
            kwargs={
                "stream_name": "stderr",
                "tail": stderr_tail,
                "capture_write": stderr_write,
                "sink": stderr_sink,
            },
        )
        t_out.daemon = True
        t_err.daemon = True
        if pipe_coordinator is not None:
            pipe_coordinator.attach_and_start(t_out, t_err)
        else:
            t_out.start()
            t_err.start()

        try:
            # Unbounded wait: a command which never exits keeps today's semantics
            # (callers already handle that case). Only the post-exit pipe drain
            # below is bounded.
            exit_code = int(proc.wait())
            if not _drain_readers_bounded(
                (t_out, t_err), deadline_seconds=_PIPE_EOF_DRAIN_SECONDS
            ):
                # A descendant inherited stdout/stderr and keeps the pipes open
                # past the post-exit drain deadline: terminate the whole group
                # so EOF arrives, then report a failure instead of blocking.
                if pipe_coordinator is not None:
                    OwnedProcessRegistry._terminate_snapshot(
                        (proc,),
                        term_timeout_seconds=5.0,
                        kill_timeout_seconds=2.0,
                        drain_timeout_seconds=2.0,
                        pipe_coordinators={id(proc): pipe_coordinator},
                    )
                    pipe_coordinator.complete(proc)
                    assert owned_processes is not None
                    owned_processes.unregister(proc)
                else:
                    _terminate_pipe_holder_group(proc)
                    _drain_readers_bounded((t_out, t_err), deadline_seconds=2.0)
                raise ReviewflowCommandDrainError(
                    cmd=cmd,
                    cwd=cwd,
                    stdout=stdout_tail.get(),
                    stderr=stderr_tail.get(),
                    deadline_seconds=_PIPE_EOF_DRAIN_SECONDS,
                )
            if pipe_coordinator is not None:
                pipe_coordinator.complete(proc)
                assert owned_processes is not None
                owned_processes.unregister(proc)
        except BaseException:
            # Pumps remain the sole pipe readers. A tagged process stays registered,
            # transferring bounded reaping/drain ownership to command teardown.
            raise

        if pump_failures:
            stream_name, failure = pump_failures[0]
            if isinstance(failure, Exception):
                raise failure
            raise LosslessCommandCaptureIntegrityError(
                f"{stream_name} command-output pump failed"
            ) from failure
        if lossless_capture is not None:
            lossless_capture.seal()

        duration = time.perf_counter() - started

        result = CommandResult(
            cmd=cmd,
            cwd=cwd,
            exit_code=exit_code,
            duration_seconds=float(duration),
            stdout=stdout_tail.get(),
            stderr=stderr_tail.get(),
        )

    if check and result.exit_code != 0:
        raise ReviewflowSubprocessError(
            cmd=cmd,
            cwd=cwd,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    return result


def merged_env(extra: dict[str, str] | None) -> dict[str, str]:
    base = dict(os.environ)
    if extra:
        base.update(extra)
    return base
