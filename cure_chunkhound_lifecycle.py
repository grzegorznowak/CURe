from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum, auto
import fnmatch
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import select
import shutil
import stat
import subprocess
import time
from types import MappingProxyType, TracebackType
from typing import Any, NoReturn

import cure_chunkhound
from cure_chunkhound import (
    ChunkHoundPreflightError,
    JsonRpcSession,
    bootstrap_chunkhound_mcp_session,
)
from run import LosslessCommandCapture


@dataclass(frozen=True)
class LaunchIdentity:
    """Canonical inputs shared by the final index and its retained daemon."""

    resolved_executable: Path
    executable_digest: str
    canonical_root: Path
    resolved_config_path: Path
    config_digest: str
    resolved_database_path: Path
    cwd: Path
    curated_environment_keys: tuple[str, ...]
    environment_equality_digest: str


@dataclass(frozen=True)
class ExpectedSessionReceiptV1:
    """Strict projection of one successful final index operation."""

    schema_version: int
    canonical_root: Path
    reviewed_head: str
    resolved_config_path: Path
    config_digest: str
    resolved_database_path: Path
    total_chunks: int
    launch_identity_projection: LaunchIdentity


class ExpectedSessionReceiptProjectionError(RuntimeError):
    """Raised when complete final-index output cannot authorize a receipt."""


@dataclass(frozen=True)
class ExpectedSearchWitness:
    """One exact repository-relative source witness for a nonempty index."""

    relative_path: str
    literal: str


@dataclass(frozen=True)
class DaemonGenerationIdentity:
    """Probe-backed identity of one native ChunkHound daemon generation."""

    pid: int
    process_started_at: float


_EVIDENCE_FACTORY_TOKEN = object()


class ExpectedGenerationEvidence:
    """Opaque lease-bound evidence for one adjudicated daemon generation."""

    __slots__ = ("__generation", "__lease_token")
    __generation: DaemonGenerationIdentity
    __lease_token: object

    def __init__(
        self,
        lease_token: object,
        generation: DaemonGenerationIdentity,
        *,
        _factory_token: object | None = None,
    ) -> None:
        if _factory_token is not _EVIDENCE_FACTORY_TOKEN:
            raise TypeError(
                "ExpectedGenerationEvidence is issued only by a daemon lease"
            )
        object.__setattr__(
            self, "_ExpectedGenerationEvidence__lease_token", lease_token
        )
        object.__setattr__(self, "_ExpectedGenerationEvidence__generation", generation)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("ExpectedGenerationEvidence is immutable")

    def _matches(
        self,
        lease_token: object,
        generation: DaemonGenerationIdentity,
    ) -> bool:
        return self.__lease_token is lease_token and self.__generation == generation


@dataclass(frozen=True)
class ExpectedSessionReadiness:
    """Proof that the held daemon can serve the expected final index."""

    launch_identity: LaunchIdentity
    search_witness: ExpectedSearchWitness | None
    expected_generation: ExpectedGenerationEvidence


class ExpectedSessionReadinessError(RuntimeError):
    """Raised when a held daemon cannot prove expected-session readiness."""

    poll_evidence: dict[str, Any] | None = None


class NativeStatusReadinessError(ExpectedSessionReadinessError):
    """Raised when native daemon status cannot prove readiness."""

    status_payload: str | None = None
    status: dict[str, Any] | None = None


class NativeSearchWitnessReadinessError(ExpectedSessionReadinessError):
    """Raised when native search cannot prove the selected source witness.

    ``witness`` and ``response`` carry the failed search's inputs and raw
    markdown response so the readiness evidence can persist a bounded,
    scrubbed excerpt for diagnosis (see the evidence collector in cure.py).
    """

    witness: ExpectedSearchWitness | None = None
    response: str | None = None


class ExpectedSessionReadinessTimeoutError(NativeStatusReadinessError):
    """Raised when an exact transient readiness state outlives its deadline."""


class PreNativeSpawnLeaseOpenError(RuntimeError):
    """Raised when lease opening fails before native spawn construction."""


class NativeDaemonReadinessSignal(Enum):
    """Typed result of strict native daemon-status adjudication."""

    READY = auto()
    INITIALIZING = auto()
    FRESH_INSTANCE_RESYNC = auto()


class LaunchIdentityConstructionError(RuntimeError):
    """Raised when canonical launch inputs cannot form an exact identity."""


class DaemonGenerationObservationError(RuntimeError):
    """Raised when native daemon generation identity cannot be proven."""


class SourceWitnessSelectionError(RuntimeError):
    """Raised when bounded tracked-source selection cannot produce a witness."""


def assert_daemon_log_startup_precondition(*, repo_path: str | Path) -> None:
    """Fail closed unless native startup can only create an absent regular log."""

    try:
        canonical_root = Path(repo_path).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ExpectedSessionReadinessError(
            "canonical daemon-log root cannot be resolved"
        ) from exc
    if not canonical_root.is_dir():
        raise ExpectedSessionReadinessError(
            "canonical daemon-log root is not a directory"
        )

    parent = canonical_root / ".chunkhound"
    try:
        parent_mode = parent.lstat().st_mode
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ExpectedSessionReadinessError(
            "daemon-log parent cannot be inspected safely"
        ) from exc
    if not stat.S_ISDIR(parent_mode):
        raise ExpectedSessionReadinessError(
            "daemon-log parent must be an existing real directory"
        )

    daemon_log = parent / "daemon.log"
    try:
        daemon_log.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ExpectedSessionReadinessError(
            "daemon log cannot be inspected safely"
        ) from exc
    raise ExpectedSessionReadinessError(
        "daemon log must be absent before native startup"
    )


_CANONICAL_JSON_SEPARATORS = (",", ":")
_SOURCE_TOKEN = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]{7,63}(?![A-Za-z0-9_])")
_DEFAULT_MAX_TRACKED_PATHS = 4096
_DEFAULT_MAX_LISTING_BYTES = 4 * 1024 * 1024
_DEFAULT_MAX_SOURCE_CANDIDATES = 128
_DEFAULT_MAX_SOURCE_FILE_BYTES = 256 * 1024
_DEFAULT_MAX_TOKENS_PER_FILE = 128

# Bounded daemon/DB-lock release verification after lease close().
_LEASE_RELEASE_VERIFY_SECONDS = 8.0
_LEASE_RELEASE_VERIFY_POLL_INTERVAL_SECONDS = 0.25


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=_CANONICAL_JSON_SEPARATORS,
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise LaunchIdentityConstructionError(
            "launch input is not canonical JSON"
        ) from exc


def _validated_environment(environment: Mapping[str, str]) -> dict[str, str]:
    try:
        copied = dict(environment)
    except Exception as exc:
        raise LaunchIdentityConstructionError(
            "curated environment cannot be copied"
        ) from exc
    if any(type(key) is not str or type(value) is not str for key, value in copied.items()):
        raise LaunchIdentityConstructionError(
            "curated environment must contain only string keys and values"
        )
    if any(
        not key or "=" in key or "\x00" in key or "\x00" in value
        for key, value in copied.items()
    ):
        raise LaunchIdentityConstructionError(
            "curated environment contains an invalid process environment entry"
        )
    return copied


def _resolve_executable(*, binary: str | Path, cwd: Path, environment: Mapping[str, str]) -> Path:
    requested = os.fspath(binary)
    if not requested or "\x00" in requested:
        raise LaunchIdentityConstructionError("ChunkHound executable is invalid")
    if os.path.dirname(requested):
        candidate = Path(requested)
        if not candidate.is_absolute():
            candidate = cwd / candidate
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise LaunchIdentityConstructionError(
                "ChunkHound executable cannot be resolved"
            ) from exc
    else:
        found = shutil.which(requested, path=environment.get("PATH", ""))
        if found is None:
            raise LaunchIdentityConstructionError(
                "ChunkHound executable is absent from the curated PATH"
            )
        try:
            resolved = Path(found).resolve(strict=True)
        except OSError as exc:
            raise LaunchIdentityConstructionError(
                "ChunkHound executable cannot be resolved"
            ) from exc
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise LaunchIdentityConstructionError(
            "resolved ChunkHound executable is not executable"
        )
    return resolved


def build_launch_identity(
    *,
    repo_path: str | Path,
    config_path: str | Path,
    database_path: str | Path,
    cwd: str | Path,
    binary: str | Path = "chunkhound",
    environment: Mapping[str, str],
) -> LaunchIdentity:
    """Build the secret-free exact identity shared by index and MCP launches."""

    curated = _validated_environment(environment)
    try:
        canonical_root = Path(repo_path).resolve(strict=True)
        resolved_config = Path(config_path).resolve(strict=True)
        resolved_database = Path(database_path).resolve(strict=True)
        resolved_cwd = Path(cwd).resolve(strict=True)
        config_value = json.loads(resolved_config.read_text(encoding="utf-8"))
    except (OSError, RuntimeError, UnicodeError, json.JSONDecodeError) as exc:
        raise LaunchIdentityConstructionError(
            "launch paths or ChunkHound config cannot be canonicalized"
        ) from exc
    if not isinstance(config_value, dict):
        raise LaunchIdentityConstructionError("ChunkHound config must be a JSON object")
    if not canonical_root.is_dir() or not resolved_cwd.is_dir():
        raise LaunchIdentityConstructionError("launch root and cwd must be directories")
    resolved_executable = _resolve_executable(
        binary=binary, cwd=resolved_cwd, environment=curated
    )
    try:
        executable_digest = hashlib.sha256(resolved_executable.read_bytes()).hexdigest()
    except OSError as exc:
        raise LaunchIdentityConstructionError(
            "resolved ChunkHound executable cannot be read"
        ) from exc
    config_digest = hashlib.sha256(_canonical_json_bytes(config_value)).hexdigest()
    environment_digest = hashlib.sha256(_canonical_json_bytes(curated)).hexdigest()
    return LaunchIdentity(
        resolved_executable=resolved_executable,
        executable_digest=executable_digest,
        canonical_root=canonical_root,
        resolved_config_path=resolved_config,
        config_digest=config_digest,
        resolved_database_path=resolved_database,
        cwd=resolved_cwd,
        curated_environment_keys=tuple(sorted(curated)),
        environment_equality_digest=environment_digest,
    )


@dataclass(frozen=True)
class _LinuxProcessIdentity:
    pid: int
    state: str
    parent_pid: int
    start_ticks: int


def _read_linux_process_identity(
    pid: int,
    *,
    proc_root: str | Path = "/proc",
) -> _LinuxProcessIdentity:
    stat_path = Path(proc_root) / str(pid) / "stat"
    try:
        proc_stat = stat_path.read_text(encoding="ascii")
    except (OSError, UnicodeError) as exc:
        raise DaemonGenerationObservationError(
            "native daemon /proc identity is unavailable"
        ) from exc

    stat_pid_text, separator, after_pid = proc_stat.partition(" (")
    closing_paren = after_pid.rfind(")")
    if not separator or closing_paren < 0:
        raise DaemonGenerationObservationError(
            "native daemon /proc identity is malformed"
        )
    fields_after_comm = after_pid[closing_paren + 1 :].strip().split()
    try:
        stat_pid = int(stat_pid_text, 10)
        process_state = fields_after_comm[0]
        parent_pid = int(fields_after_comm[1], 10)
        start_ticks = int(fields_after_comm[19], 10)
    except (IndexError, ValueError) as exc:
        raise DaemonGenerationObservationError(
            "native daemon /proc start identity is malformed"
        ) from exc
    if (
        stat_pid != pid
        or process_state in {"Z", "X", "x"}
        or parent_pid < 0
        or start_ticks < 0
    ):
        raise DaemonGenerationObservationError(
            "native daemon /proc start identity is invalid"
        )
    return _LinuxProcessIdentity(
        pid=stat_pid,
        state=process_state,
        parent_pid=parent_pid,
        start_ticks=start_ticks,
    )


def attest_native_daemon_generation_ownership(
    generation: DaemonGenerationIdentity,
    expected_parent_pid: int,
    *,
    proc_root: str | Path = "/proc",
) -> None:
    """Require a live generation to be the immediate child of one MCP proxy."""

    if (
        not isinstance(generation, DaemonGenerationIdentity)
        or type(generation.pid) is not int
        or generation.pid <= 0
        or not isinstance(generation.process_started_at, (int, float))
        or isinstance(generation.process_started_at, bool)
        or not math.isfinite(float(generation.process_started_at))
        or generation.process_started_at < 0
        or type(expected_parent_pid) is not int
        or expected_parent_pid <= 0
    ):
        raise ExpectedSessionReadinessError(
            "native daemon ownership attestation inputs are invalid"
        )
    try:
        identity = _read_linux_process_identity(
            generation.pid,
            proc_root=proc_root,
        )
    except DaemonGenerationObservationError as exc:
        raise ExpectedSessionReadinessError(
            "native daemon ownership identity cannot be read"
        ) from exc
    if (
        float(identity.start_ticks) != float(generation.process_started_at)
        or identity.parent_pid != expected_parent_pid
    ):
        raise ExpectedSessionReadinessError(
            "native daemon generation is not owned by the live MCP proxy"
        )


def observe_native_daemon_generation(
    *,
    repo_path: str | Path,
    cwd: str | Path,
    binary: str | Path,
    environment: Mapping[str, str],
    timeout: float = 5.0,
    proc_root: str | Path = "/proc",
) -> DaemonGenerationIdentity | None:
    """Observe a native daemon PID plus Linux PID-reuse-resistant start tick."""

    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not math.isfinite(float(timeout)) or timeout <= 0:
        raise DaemonGenerationObservationError("daemon metadata timeout is invalid")
    try:
        curated = _validated_environment(environment)
        repo = Path(repo_path).resolve(strict=True)
        resolved_cwd = Path(cwd).resolve(strict=True)
        resolved_binary = _resolve_executable(
            binary=binary, cwd=resolved_cwd, environment=curated
        )
    except (OSError, RuntimeError, LaunchIdentityConstructionError) as exc:
        raise DaemonGenerationObservationError(
            "native daemon launch inputs cannot be resolved"
        ) from exc
    try:
        payload = cure_chunkhound.daemon_metadata_payload(
            repo,
            chunkhound_cwd=resolved_cwd,
            binary=str(resolved_binary),
            timeout=float(timeout),
            env=MappingProxyType(curated),
        )
    except Exception as exc:
        raise DaemonGenerationObservationError(
            "native daemon metadata observation failed"
        ) from exc
    if not isinstance(payload, dict):
        raise DaemonGenerationObservationError(
            "native daemon metadata returned a non-object payload"
        )
    metadata_error = payload.get("daemon_metadata_error")
    pid = payload.get("daemon_pid")
    if metadata_error:
        raise DaemonGenerationObservationError(
            "native daemon metadata did not identify a live PID"
        )
    if pid is None:
        return None
    if type(pid) is not int or pid <= 0:
        raise DaemonGenerationObservationError(
            "native daemon metadata returned an invalid PID"
        )
    identity = _read_linux_process_identity(pid, proc_root=proc_root)
    # Keep the kernel start tick itself: conversion through wall-clock time loses
    # precision and weakens PID-reuse detection.
    return DaemonGenerationIdentity(
        pid=identity.pid,
        process_started_at=float(identity.start_ticks),
    )


def _load_indexing_patterns(
    config_path: Path,
) -> tuple[tuple[str, ...], tuple[str, ...], str | None]:
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SourceWitnessSelectionError(
            "ChunkHound config cannot be read for witness selection"
        ) from exc
    if not isinstance(payload, dict):
        raise SourceWitnessSelectionError("ChunkHound config must be an object")
    indexing = payload.get("indexing", {})
    if not isinstance(indexing, dict):
        raise SourceWitnessSelectionError("ChunkHound indexing config must be an object")

    def patterns(name: str) -> tuple[str, ...]:
        value = indexing.get(name, [])
        if not isinstance(value, list) or any(type(item) is not str or not item for item in value):
            raise SourceWitnessSelectionError(
                f"ChunkHound indexing {name} must be a list of nonempty strings"
            )
        return tuple(value)

    # exclude_mode mirrors the daemon's effective ignore source selection: the
    # materialized session config (materialize_chunkhound_env_config) converts
    # the ".gitignore" exclude sentinel into exclude_mode="gitignore_only",
    # which is the same field the daemon reads to index with gitignore rules
    # only (chunkhound core/config/indexing_config.py resolve_ignore_sources).
    exclude_mode = indexing.get("exclude_mode")
    if exclude_mode is not None and (type(exclude_mode) is not str or not exclude_mode):
        raise SourceWitnessSelectionError(
            "ChunkHound indexing exclude_mode must be a nonempty string"
        )
    include_name = "include" if "include" in indexing else "_include"
    return patterns(include_name), patterns("exclude"), exclude_mode


def _matches_index_pattern(relative_path: str, pattern: str) -> bool:
    # Match each glob component independently so wildcards never consume '/'.
    path_parts = PurePosixPath(relative_path).parts
    pattern_parts = PurePosixPath(pattern).parts
    matched_prefixes = [True, *([False] * len(path_parts))]
    for pattern_index, pattern_part in enumerate(pattern_parts):
        next_prefixes = [False] * (len(path_parts) + 1)
        if pattern_part == "**":
            # ChunkHound requires a terminal globstar to match a descendant,
            # while an internal globstar may match zero path components.
            if pattern_index != len(pattern_parts) - 1:
                next_prefixes[0] = matched_prefixes[0]
            for path_index in range(1, len(path_parts) + 1):
                next_prefixes[path_index] = (
                    matched_prefixes[path_index - 1]
                    or next_prefixes[path_index - 1]
                    or (
                        pattern_index != len(pattern_parts) - 1
                        and matched_prefixes[path_index]
                    )
                )
        else:
            for path_index, path_part in enumerate(path_parts, start=1):
                next_prefixes[path_index] = matched_prefixes[
                    path_index - 1
                ] and fnmatch.fnmatchcase(path_part, pattern_part)
        matched_prefixes = next_prefixes

    plain_directory = not any(character in pattern for character in "*?[")
    return matched_prefixes[-1] or (
        plain_directory and relative_path.startswith(pattern.rstrip("/") + "/")
    )


def _git_tracked_paths(
    repo: Path,
    *,
    max_tracked_paths: int,
    max_listing_bytes: int,
    timeout: float,
) -> tuple[str, ...]:
    if max_tracked_paths <= 0 or max_listing_bytes <= 0 or timeout <= 0:
        raise SourceWitnessSelectionError("tracked-source selection bounds are invalid")
    try:
        process = subprocess.Popen(
            ["git", "-C", str(repo), "ls-files", "-z", "--cached", "--"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise SourceWitnessSelectionError("git tracked-source listing failed") from exc
    assert process.stdout is not None
    listing = bytearray()
    listed_paths = 0
    try:
        deadline = time.monotonic() + float(timeout)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SourceWitnessSelectionError("git tracked-source listing timed out")
            readable, _, _ = select.select([process.stdout], [], [], remaining)
            if not readable:
                raise SourceWitnessSelectionError("git tracked-source listing timed out")
            chunk = os.read(process.stdout.fileno(), 64 * 1024)
            if not chunk:
                break
            listing.extend(chunk)
            listed_paths += chunk.count(b"\x00")
            if len(listing) > max_listing_bytes:
                raise SourceWitnessSelectionError("git tracked-source listing exceeded its byte bound")
            if listed_paths > max_tracked_paths:
                raise SourceWitnessSelectionError("git tracked-source listing exceeded its path bound")
        remaining = max(0.0, deadline - time.monotonic())
        return_code = process.wait(timeout=remaining)
        if return_code != 0:
            raise SourceWitnessSelectionError("git tracked-source listing failed")
    except (subprocess.TimeoutExpired, SourceWitnessSelectionError):
        process.kill()
        process.wait()
        raise
    finally:
        process.stdout.close()
    raw_paths = bytes(listing).split(b"\x00")
    if raw_paths and raw_paths[-1] == b"":
        raw_paths.pop()
    if len(raw_paths) > max_tracked_paths:
        raise SourceWitnessSelectionError("git tracked-source listing exceeded its path bound")
    try:
        decoded = tuple(raw.decode("utf-8") for raw in raw_paths)
    except UnicodeDecodeError as exc:
        raise SourceWitnessSelectionError("tracked source path is not UTF-8") from exc
    if decoded != tuple(sorted(decoded)) or len(set(decoded)) != len(decoded):
        raise SourceWitnessSelectionError("git tracked-source listing is not canonical")
    return decoded


def _git_ignored_paths(
    repo: Path,
    candidates: Sequence[str],
    *,
    max_tracked_paths: int,
    max_listing_bytes: int,
    timeout: float,
) -> frozenset[str]:
    """Return the candidates excluded by gitignore rules, tracked or not.

    ``git check-ignore --no-index`` evaluates the working tree's ignore rules
    WITHOUT the index's tracked-file exemption, which is exactly how the
    daemon's repo-aware ignore engine treats paths during indexing: a tracked
    file that matches .gitignore is skipped under exclude_mode=gitignore_only.
    Runs one batched subprocess for all candidates (NUL-separated stdin);
    never shells out per file. Bounds mirror ``_git_tracked_paths``.
    """
    if max_tracked_paths <= 0 or max_listing_bytes <= 0 or timeout <= 0:
        raise SourceWitnessSelectionError("tracked-source ignore bounds are invalid")
    try:
        payload = b"".join(path.encode("utf-8") + b"\x00" for path in candidates)
    except UnicodeEncodeError as exc:
        raise SourceWitnessSelectionError(
            "tracked source path is not UTF-8"
        ) from exc
    if len(payload) > max_listing_bytes:
        raise SourceWitnessSelectionError(
            "tracked-source ignore input exceeded its byte bound"
        )
    try:
        process = subprocess.Popen(
            ["git", "-C", str(repo), "check-ignore", "-z", "--no-index", "--stdin"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise SourceWitnessSelectionError("git ignore-check failed") from exc
    assert process.stdin is not None and process.stdout is not None
    listing = bytearray()
    listed_paths = 0
    input_view = memoryview(payload)
    input_offset = 0
    try:
        deadline = time.monotonic() + float(timeout)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SourceWitnessSelectionError("git ignore-check timed out")
            # Pump stdin and stdout together: with large candidate sets the
            # child can fill the stdout pipe while it still needs to read
            # stdin, so a write-then-read sequence could deadlock.
            readable, writable, _ = select.select(
                [process.stdout],
                [process.stdin] if input_offset < len(input_view) else [],
                [],
                remaining,
            )
            if not readable and not writable:
                raise SourceWitnessSelectionError("git ignore-check timed out")
            if process.stdout in readable:
                chunk = os.read(process.stdout.fileno(), 64 * 1024)
                if not chunk:
                    break
                listing.extend(chunk)
                listed_paths += chunk.count(b"\x00")
                if len(listing) > max_listing_bytes:
                    raise SourceWitnessSelectionError(
                        "git ignore-check listing exceeded its byte bound"
                    )
                if listed_paths > max_tracked_paths:
                    raise SourceWitnessSelectionError(
                        "git ignore-check listing exceeded its path bound"
                    )
            if input_offset < len(input_view) and process.stdin in writable:
                written = os.write(
                    process.stdin.fileno(),
                    input_view[input_offset : input_offset + 64 * 1024],
                )
                input_offset += written
                if input_offset >= len(input_view):
                    process.stdin.close()
        remaining = max(0.0, deadline - time.monotonic())
        return_code = process.wait(timeout=remaining)
        # 0 = at least one path ignored, 1 = none ignored; anything else is a
        # git failure and must not be interpreted as an empty ignore set.
        if return_code not in (0, 1):
            raise SourceWitnessSelectionError("git ignore-check failed")
    except (BrokenPipeError, OSError) as exc:
        raise SourceWitnessSelectionError("git ignore-check failed") from exc
    except (subprocess.TimeoutExpired, SourceWitnessSelectionError):
        process.kill()
        process.wait()
        raise
    finally:
        try:
            process.stdin.close()
        finally:
            process.stdout.close()
    raw_paths = bytes(listing).split(b"\x00")
    if raw_paths and raw_paths[-1] == b"":
        raw_paths.pop()
    if len(raw_paths) > max_tracked_paths:
        raise SourceWitnessSelectionError(
            "git ignore-check listing exceeded its path bound"
        )
    try:
        return frozenset(raw.decode("utf-8") for raw in raw_paths)
    except UnicodeDecodeError as exc:
        raise SourceWitnessSelectionError(
            "git ignore-check path is not UTF-8"
        ) from exc


def select_git_tracked_source_witness(
    *,
    repo_path: str | Path,
    config_path: str | Path,
    max_tracked_paths: int = _DEFAULT_MAX_TRACKED_PATHS,
    max_listing_bytes: int = _DEFAULT_MAX_LISTING_BYTES,
    max_candidates: int = _DEFAULT_MAX_SOURCE_CANDIDATES,
    max_file_bytes: int = _DEFAULT_MAX_SOURCE_FILE_BYTES,
    max_tokens_per_file: int = _DEFAULT_MAX_TOKENS_PER_FILE,
    git_timeout: float = 10.0,
) -> ExpectedSearchWitness:
    """Select the first bounded deterministic indexed Git-tracked text token.

    The witness mirrors the daemon's effective indexing ignore rules: config
    include/exclude globs are always applied, and when the indexing config
    selects ``exclude_mode == "gitignore_only"`` (the materialized form of the
    ".gitignore" exclude sentinel) tracked-but-ignored candidates are skipped,
    because the daemon's gitignore-only engine does not index them. In any
    other mode the daemon indexes tracked files regardless of gitignore, so
    they remain valid witnesses and behavior is unchanged. Note: chunkhound's
    ignore engine additionally overlays safe default excludes and the user's
    global gitignore (core.excludesFile); those are not mirrored here, and
    size/binary/token caps are enforced by the bounds below.
    """

    bounds = (max_candidates, max_file_bytes, max_tokens_per_file)
    if any(type(value) is not int or value <= 0 for value in bounds):
        raise SourceWitnessSelectionError("source witness bounds are invalid")
    try:
        repo = Path(repo_path).resolve(strict=True)
        config = Path(config_path).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise SourceWitnessSelectionError("source witness paths cannot be resolved") from exc
    if not repo.is_dir():
        raise SourceWitnessSelectionError("source witness repository is not a directory")
    includes, excludes, exclude_mode = _load_indexing_patterns(config)
    tracked = _git_tracked_paths(
        repo,
        max_tracked_paths=max_tracked_paths,
        max_listing_bytes=max_listing_bytes,
        timeout=git_timeout,
    )
    ignored: frozenset[str] = frozenset()
    if exclude_mode == "gitignore_only":
        # The daemon indexes with gitignore rules only, so a tracked-but-ignored
        # file is NOT indexed and cannot prove a search witness.
        ignored = _git_ignored_paths(
            repo,
            tracked,
            max_tracked_paths=max_tracked_paths,
            max_listing_bytes=max_listing_bytes,
            timeout=git_timeout,
        )
    candidate_count = 0
    skipped_ignored = 0
    for relative_path in tracked:
        placeholder = ExpectedSearchWitness(relative_path=relative_path, literal="x")
        try:
            _require_safe_witness(placeholder)
        except ExpectedSessionReadinessError as exc:
            raise SourceWitnessSelectionError("git returned an unsafe tracked path") from exc
        if relative_path in ignored:
            skipped_ignored += 1
            continue
        if includes and not any(_matches_index_pattern(relative_path, item) for item in includes):
            continue
        if any(_matches_index_pattern(relative_path, item) for item in excludes):
            continue
        source_path = repo / relative_path
        try:
            metadata = source_path.lstat()
        except OSError as exc:
            raise SourceWitnessSelectionError("tracked source metadata changed during selection") from exc
        if not stat.S_ISREG(metadata.st_mode):
            continue
        candidate_count += 1
        if candidate_count > max_candidates:
            break
        descriptor: int | None = None
        try:
            descriptor = os.open(
                source_path,
                os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
            )
            opened_metadata = os.fstat(descriptor)
            if not stat.S_ISREG(opened_metadata.st_mode):
                os.close(descriptor)
                descriptor = None
                continue
            with os.fdopen(descriptor, "rb") as source:
                descriptor = None
                raw = source.read(max_file_bytes + 1)
        except OSError as exc:
            if descriptor is not None:
                os.close(descriptor)
            raise SourceWitnessSelectionError("tracked source cannot be read") from exc
        if len(raw) > max_file_bytes or b"\x00" in raw:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        token_count = 0
        for match in _SOURCE_TOKEN.finditer(text):
            token_count += 1
            if token_count > max_tokens_per_file:
                break
            witness = ExpectedSearchWitness(relative_path=relative_path, literal=match.group(0))
            _require_safe_witness(witness)
            return witness
    if skipped_ignored:
        raise SourceWitnessSelectionError(
            "bounded tracked-source selection found no indexed text witness: "
            f"all {skipped_ignored} candidate(s) are gitignored under "
            "exclude_mode='gitignore_only' and are not indexed by the daemon"
        )
    raise SourceWitnessSelectionError(
        "bounded tracked-source selection found no indexed text witness"
    )


_TOTAL_CHUNKS_LINE = re.compile(r"Total chunks:[ \t]+([0-9]+)[ \t]*")
_ERRORS_LINE = re.compile(r"Errors:[ \t]+([0-9]+)[ \t]+files[ \t]*")
_RECOGNIZED_PREFIXES = ("Total chunks:", "Errors:")
_MAX_RECOGNIZED_LINE_CHARS = 256


def _iter_recognized_summary_lines(chunks: Iterator[str]) -> Iterator[str]:
    """Yield recognized lines while retaining only a small candidate prefix."""

    candidate = ""
    ignored = False
    previous_was_cr = False

    def finish_line() -> str | None:
        nonlocal candidate, ignored
        line = candidate if not ignored and candidate in _RECOGNIZED_PREFIXES else None
        if not ignored and any(
            candidate.startswith(prefix) for prefix in _RECOGNIZED_PREFIXES
        ):
            line = candidate
        candidate = ""
        ignored = False
        return line

    for chunk in chunks:
        if not isinstance(chunk, str):
            raise TypeError("lossless capture yielded a non-text chunk")
        for character in chunk:
            if character == "\n":
                if previous_was_cr:
                    previous_was_cr = False
                    continue
                line = finish_line()
                if line is not None:
                    yield line
                continue
            if character == "\r":
                line = finish_line()
                if line is not None:
                    yield line
                previous_was_cr = True
                continue
            previous_was_cr = False
            if ignored:
                continue
            if not candidate and character.isspace():
                continue
            candidate += character
            if len(candidate) > _MAX_RECOGNIZED_LINE_CHARS:
                if any(candidate.startswith(prefix) for prefix in _RECOGNIZED_PREFIXES):
                    raise ExpectedSessionReceiptProjectionError(
                        "recognized final-index summary line is too long"
                    )
                candidate = ""
                ignored = True
                continue
            if not any(
                prefix.startswith(candidate) or candidate.startswith(prefix)
                for prefix in _RECOGNIZED_PREFIXES
            ):
                candidate = ""
                ignored = True

    line = finish_line()
    if line is not None:
        yield line


def project_expected_session_receipt_v1(
    *,
    capture: LosslessCommandCapture,
    exit_code: int,
    reviewed_head: str,
    launch_identity_projection: LaunchIdentity,
) -> ExpectedSessionReceiptV1:
    """Project strict receipt fields from both sealed complete output streams."""

    if exit_code != 0:
        raise ExpectedSessionReceiptProjectionError(
            f"final index exited with status {exit_code}"
        )

    totals: int | None = None
    errors: int | None = None
    try:
        streams = (capture.iter_stdout_chunks(), capture.iter_stderr_chunks())
        for chunks in streams:
            for line in _iter_recognized_summary_lines(chunks):
                if line.startswith("Total chunks:"):
                    match = _TOTAL_CHUNKS_LINE.fullmatch(line)
                    if match is None:
                        raise ExpectedSessionReceiptProjectionError(
                            "malformed Total chunks: line in final-index output"
                        )
                    value = int(match.group(1))
                    if totals is not None and value != totals:
                        raise ExpectedSessionReceiptProjectionError(
                            "conflicting Total chunks: values in final-index output"
                        )
                    totals = value
                    continue

                match = _ERRORS_LINE.fullmatch(line)
                if match is None:
                    raise ExpectedSessionReceiptProjectionError(
                        "malformed Errors: line in final-index output"
                    )
                value = int(match.group(1))
                if errors is not None and value != errors:
                    raise ExpectedSessionReceiptProjectionError(
                        "conflicting Errors: values in final-index output"
                    )
                if value != 0:
                    raise ExpectedSessionReceiptProjectionError(
                        "final-index output reports nonzero errors"
                    )
                errors = value
    except ExpectedSessionReceiptProjectionError:
        raise
    except Exception as exc:
        raise ExpectedSessionReceiptProjectionError(
            "failed to read sealed final-index capture"
        ) from exc

    if totals is None:
        raise ExpectedSessionReceiptProjectionError(
            "final-index output is missing Total chunks:"
        )
    if errors is None:
        raise ExpectedSessionReceiptProjectionError(
            "final-index output is missing Errors:"
        )

    identity = launch_identity_projection
    return ExpectedSessionReceiptV1(
        schema_version=1,
        canonical_root=identity.canonical_root,
        reviewed_head=reviewed_head,
        resolved_config_path=identity.resolved_config_path,
        config_digest=identity.config_digest,
        resolved_database_path=identity.resolved_database_path,
        total_chunks=totals,
        launch_identity_projection=identity,
    )


_STATUS_KEYS = {"status", "server_version", "query_ready", "scan_progress"}
_NATIVE_HIT_HEADER = re.compile(
    r"## `(?P<path>[^`\r\n]+)`"
    r"(?: L[0-9]+(?:–L[0-9]+)?)?(?: — [^`\r\n]+)?"
)
_NATIVE_FENCE = re.compile(r"(?P<fence>`{3,})(?P<info>[A-Za-z0-9_+#.\-]*)")
_NATIVE_PAGE_FOOTER = re.compile(
    r"Page (?P<page>[1-9][0-9]*) of (?P<pages>[1-9][0-9]*) "
    r"\(results (?P<first>[1-9][0-9]*)–(?P<last>[1-9][0-9]*) "
    r"of (?P<total>[1-9][0-9]*)\)"
    r"(?: \| next_offset=(?P<next_offset>[1-9][0-9]*))?"
)
_NATIVE_RESULTS_FOOTER = re.compile(
    r"Results (?P<first>[1-9][0-9]*)–(?P<last>[1-9][0-9]*)"
    r"(?: \| next_offset=(?P<next_offset>[1-9][0-9]*))?"
)
# Per-call budget for one native daemon_status request. Must stay well above
# the daemon's fresh-instance resync directory scan, which blocks the daemon's
# event loop (observed 3.3s on a fast machine, 12.6s on a slower one for a
# 213-chunk repo). A 10s budget aborts a healthy daemon that is busy rescanning;
# the 600s total readiness deadline still bounds a genuinely hung daemon.
_READINESS_STATUS_TIMEOUT_SECONDS = 30.0
_READINESS_SEARCH_TIMEOUT_SECONDS = 60.0
_EXPECTED_SESSION_READINESS_TIMEOUT_SECONDS = 600.0
_EXPECTED_SESSION_READINESS_POLL_INTERVAL_SECONDS = 0.5


def _strict_tool_text(
    session: JsonRpcSession,
    *,
    tool: str,
    arguments: dict[str, Any],
    timeout_seconds: float,
) -> str:
    try:
        response = session.request(
            "tools/call",
            {"name": tool, "arguments": arguments},
            stage="tools/call",
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        raise ExpectedSessionReadinessError(
            f"native ChunkHound {tool} request failed"
        ) from exc

    if (
        set(response) != {"jsonrpc", "id", "result"}
        or response.get("jsonrpc") != "2.0"
        or type(response.get("id")) is not int
    ):
        raise ExpectedSessionReadinessError(
            f"native ChunkHound {tool} returned an invalid JSON-RPC envelope"
        )
    result = response.get("result")
    if (
        not isinstance(result, dict)
        or set(result) != {"content", "isError"}
        or result.get("isError") is not False
    ):
        raise ExpectedSessionReadinessError(
            f"native ChunkHound {tool} returned an invalid tool result"
        )
    content = result.get("content")
    if not isinstance(content, list) or len(content) != 1:
        raise ExpectedSessionReadinessError(
            f"native ChunkHound {tool} returned an invalid content envelope"
        )
    item = content[0]
    if (
        not isinstance(item, dict)
        or set(item) != {"type", "text"}
        or item.get("type") != "text"
        or not isinstance(item.get("text"), str)
    ):
        raise ExpectedSessionReadinessError(
            f"native ChunkHound {tool} did not return one text item"
        )
    return item["text"]


def _has_active_native_status_fault(scan_progress: dict[str, Any]) -> bool:
    """Recognize only named active markers that contradict ordinary readiness."""
    if scan_progress.get("scan_error") is not None:
        return True
    realtime = scan_progress.get("realtime")
    if not isinstance(realtime, dict):
        return False
    if (
        realtime.get("last_error") is not None
        or realtime.get("service_state") == "degraded"
        or realtime.get("live_indexing_state") == "stalled"
    ):
        return True
    resync = realtime.get("resync")
    if not isinstance(resync, dict):
        return False
    needs_resync = resync.get("needs_resync")
    return (
        "needs_resync" in resync
        and (type(needs_resync) is not bool or needs_resync is True)
    ) or resync.get("last_error") is not None


def _is_fresh_instance_resync(scan_progress: dict[str, Any]) -> bool:
    """Match the exact named evidence for benign fresh-instance reconciliation."""
    realtime = scan_progress.get("realtime")
    if not isinstance(realtime, dict):
        return False
    resync = realtime.get("resync")
    if not isinstance(resync, dict):
        return False
    details = resync.get("last_details")
    return (
        scan_progress.get("scan_error") is None
        and "last_error" in realtime
        and realtime["last_error"] is None
        and isinstance(realtime.get("service_state"), str)
        and realtime["service_state"] != "degraded"
        and isinstance(realtime.get("live_indexing_state"), str)
        and realtime["live_indexing_state"] != "stalled"
        and resync.get("needs_resync") is True
        and resync.get("last_reason") == "realtime_loss_of_sync"
        and "last_error" in resync
        and resync["last_error"] is None
        and isinstance(details, dict)
        and details.get("loss_of_sync_reason") == "fresh_instance"
        and details.get("backend") == "watchman"
    )


def _require_healthy_native_status(
    session: JsonRpcSession,
    *,
    timeout_seconds: float = _READINESS_STATUS_TIMEOUT_SECONDS,
    observations: list[dict[str, object]] | None = None,
) -> NativeDaemonReadinessSignal:
    text: str | None = None
    status: dict[str, Any] | None = None

    def fail(reason: str, *, cause: BaseException | None = None) -> NoReturn:
        error = NativeStatusReadinessError(reason)
        error.status_payload = text
        error.status = status
        if cause is None:
            raise error
        raise error from cause

    try:
        text = _strict_tool_text(
            session,
            tool="daemon_status",
            arguments={},
            timeout_seconds=timeout_seconds,
        )
    except ExpectedSessionReadinessError as exc:
        fail("native ChunkHound daemon_status request failed", cause=exc)
    try:
        status = json.loads(text)
    except (TypeError, ValueError) as exc:
        fail("native ChunkHound daemon_status returned malformed JSON", cause=exc)
    if not isinstance(status, dict) or set(status) != _STATUS_KEYS:
        fail("native ChunkHound daemon_status returned an invalid status object")
    if (
        not isinstance(status["status"], str)
        or not isinstance(status["server_version"], str)
        or type(status["query_ready"]) is not bool
        or not isinstance(status["scan_progress"], dict)
    ):
        fail("native ChunkHound daemon_status returned invalid field types")
    scan_progress = status["scan_progress"]
    # Installed ChunkHound derives the authoritative top-level state from
    # backend-specific scan_progress details. Keep that nested payload opaque
    # except for named active markers that contradict an ordinary top-level
    # readiness state.
    if status["status"] == "degraded" and _is_fresh_instance_resync(scan_progress):
        signal = NativeDaemonReadinessSignal.FRESH_INSTANCE_RESYNC
    elif not _has_active_native_status_fault(scan_progress):
        if status["status"] == "ready" and status["query_ready"] is True:
            signal = NativeDaemonReadinessSignal.READY
        elif status["status"] == "initializing" and status["query_ready"] is False:
            signal = NativeDaemonReadinessSignal.INITIALIZING
        else:
            fail("native ChunkHound daemon is not strictly query-ready")
    else:
        fail("native ChunkHound daemon is not strictly query-ready")
    if observations is not None:
        observations.append(
            {
                "signal": signal.name,
                "status": status["status"],
                "query_ready": status["query_ready"],
                "server_version": status["server_version"],
            }
        )
    return signal


def _require_safe_witness(witness: ExpectedSearchWitness) -> None:
    relative_path = witness.relative_path
    if (
        not isinstance(relative_path, str)
        or not relative_path
        or relative_path.startswith("/")
        or "\\" in relative_path
        or "`" in relative_path
        or any(character in relative_path for character in ("\r", "\n", "\x00"))
    ):
        raise ExpectedSessionReadinessError("search witness path is not safe")
    parsed = PurePosixPath(relative_path)
    if (
        str(parsed) != relative_path
        or parsed == PurePosixPath(".")
        or parsed.is_absolute()
        or any(part in {"", ".", ".."} for part in parsed.parts)
    ):
        raise ExpectedSessionReadinessError(
            "search witness path is not canonical repository-relative POSIX"
        )
    if not isinstance(witness.literal, str) or not witness.literal:
        raise ExpectedSessionReadinessError("search witness literal is empty")


def _longest_backtick_run(text: str) -> int:
    return max((len(match.group(0)) for match in re.finditer(r"`+", text)), default=0)


def _native_markdown_contains_witness(
    markdown: str,
    witness: ExpectedSearchWitness,
) -> bool:
    if not markdown.startswith("## `"):
        return False

    cursor = 0
    hit_count = 0
    found = False
    while True:
        header_end = markdown.find("\n", cursor)
        if header_end < 0:
            return False
        header_match = _NATIVE_HIT_HEADER.fullmatch(markdown[cursor:header_end])
        if header_match is None:
            return False
        cursor = header_end + 1
        if not markdown.startswith("\n", cursor):
            return False
        cursor += 1

        opening_end = markdown.find("\n", cursor)
        if opening_end < 0:
            return False
        fence_match = _NATIVE_FENCE.fullmatch(markdown[cursor:opening_end])
        if fence_match is None:
            return False
        fence = fence_match.group("fence")
        cursor = opening_end + 1
        payload_start = cursor

        payload: str | None = None
        while cursor < len(markdown):
            line_end = markdown.find("\n", cursor)
            if line_end < 0:
                return False
            if markdown[cursor:line_end] == fence:
                payload = markdown[payload_start:cursor]
                cursor = line_end + 1
                break
            cursor = line_end + 1
        if payload is None:
            return False
        if len(fence) != max(3, _longest_backtick_run(payload) + 1):
            return False

        hit_count += 1
        if (
            header_match.group("path") == witness.relative_path
            and witness.literal in payload
        ):
            found = True

        if not markdown.startswith("\n---\n", cursor):
            return False
        cursor += len("\n---\n")
        if markdown.startswith("\n## `", cursor):
            cursor += 1
            continue

        footer = markdown[cursor:]
        page_match = _NATIVE_PAGE_FOOTER.fullmatch(footer)
        results_match = _NATIVE_RESULTS_FOOTER.fullmatch(footer)
        footer_match = page_match or results_match
        if footer_match is None:
            return False
        first = int(footer_match.group("first"))
        last = int(footer_match.group("last"))
        if first != 1 or last < first or last - first + 1 != hit_count:
            return False
        next_offset = footer_match.group("next_offset")
        if next_offset is not None and int(next_offset) != last:
            return False
        if page_match is not None:
            page = int(page_match.group("page"))
            pages = int(page_match.group("pages"))
            total = int(page_match.group("total"))
            if page != 1 or page > pages or total < last:
                return False
        return found


def _require_native_search_witness(
    session: JsonRpcSession,
    witness: ExpectedSearchWitness,
) -> None:
    try:
        text = _strict_tool_text(
            session,
            tool="search",
            arguments={
                "type": "regex",
                "query": re.escape(witness.literal),
                "path": witness.relative_path,
            },
            timeout_seconds=_READINESS_SEARCH_TIMEOUT_SECONDS,
        )
    except ExpectedSessionReadinessError as exc:
        raise NativeSearchWitnessReadinessError(
            "native ChunkHound search request failed"
        ) from exc
    if not _native_markdown_contains_witness(text, witness):
        error = NativeSearchWitnessReadinessError(
            "native ChunkHound search did not prove the exact source witness"
        )
        error.witness = witness
        error.response = text
        raise error


def wait_for_daemon_generation_absence(
    probe: Callable[[], DaemonGenerationIdentity | None],
    *,
    timeout_seconds: float,
    poll_interval_seconds: float,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """Poll a generation probe until it reports no live daemon.

    Returns True once ``probe()`` returns None (no live daemon published),
    False when the deadline expires first. Probe exceptions count as "not yet
    released" and polling continues, so a transiently failing probe (e.g. a
    half-removed lock file mid-shutdown) cannot false-positive a release; a
    persistently failing probe yields False. Raises ValueError when the wait
    configuration is invalid. Never kills anything; it only observes.
    """
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(float(timeout_seconds))
        or timeout_seconds <= 0.0
        or isinstance(poll_interval_seconds, bool)
        or not isinstance(poll_interval_seconds, (int, float))
        or not math.isfinite(float(poll_interval_seconds))
        or poll_interval_seconds <= 0.0
        or not callable(probe)
        or not callable(clock)
        or not callable(sleep)
    ):
        raise ValueError("daemon release verification configuration is invalid")
    deadline = float(clock()) + float(timeout_seconds)
    while True:
        try:
            if probe() is None:
                return True
        except Exception:
            # An unusable probe right now must not count as "released".
            pass
        remaining = deadline - float(clock())
        if remaining <= 0.0:
            return False
        sleep(min(float(poll_interval_seconds), remaining))


class LeaseState(Enum):
    """Lifecycle states for one command-scoped ChunkHound daemon lease."""

    NEW = auto()
    HELD = auto()
    CLOSED = auto()


class ChunkHoundDaemonLease:
    """Retain one canonically bootstrapped MCP client as a daemon lease."""

    def __init__(
        self,
        *,
        config_path: str | Path,
        repo_path: str | Path,
        cwd: str | Path | None = None,
        binary: str = "chunkhound",
        env: Mapping[str, str] | None = None,
        transport_mode: str = "json_line",
        stage_timeouts: Mapping[str, float] | None = None,
        launch_identity: LaunchIdentity | None = None,
        generation_probe: Callable[[], DaemonGenerationIdentity | None] | None = None,
        generation_attestor: Callable[[DaemonGenerationIdentity, int], None]
        | None = None,
        pre_spawn_validation: Callable[[], None] | None = None,
    ) -> None:
        self._config_path = Path(config_path)
        self._repo_path = Path(repo_path)
        self._cwd = Path(cwd) if cwd is not None else None
        self._binary = str(binary or "chunkhound")
        self._env = dict(env) if env is not None else None
        self._transport_mode = transport_mode
        self._stage_timeouts = (
            dict(stage_timeouts) if stage_timeouts is not None else None
        )
        self._launch_identity = launch_identity
        self._generation_probe = generation_probe
        self._generation_attestor = (
            generation_attestor or attest_native_daemon_generation_ownership
        )
        self._pre_spawn_validation = pre_spawn_validation
        self._opened_generation: DaemonGenerationIdentity | None = None
        self._lease_token = object()
        self._owned_generation: ExpectedGenerationEvidence | None = None
        self._session: JsonRpcSession | None = None
        self.state = LeaseState.NEW

    @property
    def launch_identity(self) -> LaunchIdentity | None:
        return self._launch_identity

    @property
    def owned_generation(self) -> ExpectedGenerationEvidence | None:
        if self.state is not LeaseState.HELD:
            return None
        return self._owned_generation

    def _observe_generation(self) -> DaemonGenerationIdentity | None:
        probe = self._generation_probe
        if probe is None:
            return None
        try:
            generation = probe()
        except Exception as exc:
            raise ExpectedSessionReadinessError(
                "failed to probe native ChunkHound daemon generation"
            ) from exc
        if generation is None:
            return None
        if (
            not isinstance(generation, DaemonGenerationIdentity)
            or type(generation.pid) is not int
            or generation.pid <= 0
            or not isinstance(generation.process_started_at, (int, float))
            or isinstance(generation.process_started_at, bool)
            or not math.isfinite(float(generation.process_started_at))
            or generation.process_started_at < 0
        ):
            raise ExpectedSessionReadinessError(
                "native ChunkHound generation probe returned an invalid identity"
            )
        return generation

    def _evidence_for(
        self,
        generation: DaemonGenerationIdentity,
    ) -> ExpectedGenerationEvidence:
        return ExpectedGenerationEvidence(
            self._lease_token,
            generation,
            _factory_token=_EVIDENCE_FACTORY_TOKEN,
        )

    def _attest_owned_generation(
        self,
        session: JsonRpcSession,
        generation: DaemonGenerationIdentity,
    ) -> None:
        if session.proc.poll() is not None:
            raise ExpectedSessionReadinessError(
                "MCP proxy exited before daemon ownership attestation"
            )
        proxy_pid = session.proc.pid
        if type(proxy_pid) is not int or proxy_pid <= 0:
            raise ExpectedSessionReadinessError(
                "MCP proxy has no valid process identity"
            )
        try:
            self._generation_attestor(generation, proxy_pid)
        except Exception as exc:
            raise ExpectedSessionReadinessError(
                "native daemon ownership attestation failed"
            ) from exc
        if session.proc.poll() is not None:
            raise ExpectedSessionReadinessError(
                "MCP proxy exited during daemon ownership attestation"
            )

    def open(self) -> ChunkHoundDaemonLease:
        if self.state is LeaseState.HELD:
            self.assert_alive()
            return self
        if self.state is LeaseState.CLOSED:
            raise RuntimeError("a closed ChunkHound daemon lease cannot be reopened")

        session: JsonRpcSession | None = None
        try:
            try:
                generation_before = self._observe_generation()
                if generation_before is not None:
                    raise ExpectedSessionReadinessError(
                        "native ChunkHound daemon generation already exists"
                    )
                if self._pre_spawn_validation is not None:
                    self._pre_spawn_validation()
            except Exception as exc:
                raise PreNativeSpawnLeaseOpenError(
                    "ChunkHound lease failed before native spawn construction"
                ) from exc
            session = JsonRpcSession(
                config_path=self._config_path,
                repo_path=self._repo_path,
                cwd=self._cwd,
                binary=self._binary,
                env=self._env,
                transport_mode=self._transport_mode,
            )
            payload = bootstrap_chunkhound_mcp_session(
                session,
                config_path=self._config_path,
                repo_path=self._repo_path,
                cwd=self._cwd,
                binary=session.binary,
                stage_timeouts=self._stage_timeouts,
                emit_stage_lines=False,
            )
            if not payload.get("ok"):
                raise ChunkHoundPreflightError(
                    str(payload.get("preflight_stage") or "unknown"),
                    str(payload.get("error") or "ChunkHound keeper bootstrap failed"),
                    payload=payload,
                )
            generation_after = self._observe_generation()
            self._opened_generation = generation_after
            if generation_before is None and generation_after is not None:
                self._attest_owned_generation(session, generation_after)
                self._owned_generation = self._evidence_for(generation_after)
            self._session = session
            self.state = LeaseState.HELD
            return self
        except BaseException:
            if session is not None:
                session.close()
            self._session = None
            self.state = LeaseState.CLOSED
            raise

    def assert_alive(self) -> None:
        session = self._session
        if self.state is not LeaseState.HELD or session is None:
            raise RuntimeError("ChunkHound daemon lease is not held")
        exit_code = session.proc.poll()
        if exit_code is not None:
            raise RuntimeError(
                f"ChunkHound daemon lease process exited with status {exit_code}"
            )

    def _require_receipt_identity(
        self,
        receipt: ExpectedSessionReceiptV1,
    ) -> LaunchIdentity:
        identity = self._launch_identity
        if identity is None:
            raise ExpectedSessionReadinessError(
                "daemon lease has no canonical LaunchIdentity"
            )
        if not isinstance(receipt, ExpectedSessionReceiptV1):
            raise ExpectedSessionReadinessError(
                "expected-session receipt has the wrong type"
            )
        if (
            type(receipt.schema_version) is not int
            or receipt.schema_version != 1
            or not isinstance(receipt.reviewed_head, str)
            or not receipt.reviewed_head
            or type(receipt.total_chunks) is not int
            or receipt.total_chunks < 0
            or receipt.launch_identity_projection != identity
            or receipt.canonical_root != identity.canonical_root
            or receipt.resolved_config_path != identity.resolved_config_path
            or receipt.config_digest != identity.config_digest
            or receipt.resolved_database_path != identity.resolved_database_path
        ):
            raise ExpectedSessionReadinessError(
                "expected-session receipt does not exactly match the daemon lease"
            )
        return identity

    def _require_current_generation(self) -> DaemonGenerationIdentity:
        generation = self._observe_generation()
        if generation is None or generation != self._opened_generation:
            raise ExpectedSessionReadinessError(
                "native ChunkHound daemon generation is absent or changed"
            )
        return generation

    def adjudicate_expected_session(
        self,
        receipt: ExpectedSessionReceiptV1,
        *,
        witness: ExpectedSearchWitness | None = None,
        expected_generation: ExpectedGenerationEvidence | None = None,
        readiness_timeout_seconds: float = (
            _EXPECTED_SESSION_READINESS_TIMEOUT_SECONDS
        ),
        readiness_poll_interval_seconds: float = (
            _EXPECTED_SESSION_READINESS_POLL_INTERVAL_SECONDS
        ),
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> ExpectedSessionReadiness:
        if (
            isinstance(readiness_timeout_seconds, bool)
            or not isinstance(readiness_timeout_seconds, (int, float))
            or not math.isfinite(readiness_timeout_seconds)
            or readiness_timeout_seconds <= 0.0
            or isinstance(readiness_poll_interval_seconds, bool)
            or not isinstance(readiness_poll_interval_seconds, (int, float))
            or not math.isfinite(readiness_poll_interval_seconds)
            or readiness_poll_interval_seconds <= 0.0
            or not callable(clock)
            or not callable(sleep)
        ):
            raise ExpectedSessionReadinessError(
                "native readiness wait configuration is invalid"
            )

        def read_clock() -> float:
            value = clock()
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ExpectedSessionReadinessError(
                    "native readiness clock returned an invalid value"
                )
            return float(value)

        identity = self._require_receipt_identity(receipt)
        started = read_clock()
        deadline = started + float(readiness_timeout_seconds)
        polls = 0
        observations: list[dict[str, object]] = []

        def remaining_before_deadline() -> float:
            remaining = deadline - read_clock()
            if remaining <= 0.0:
                raise ExpectedSessionReadinessTimeoutError(
                    "native ChunkHound daemon readiness deadline expired"
                )
            return remaining

        while True:
            try:
                remaining_before_deadline()
                try:
                    self.assert_alive()
                except RuntimeError as exc:
                    raise ExpectedSessionReadinessError(
                        "ChunkHound daemon lease is not live"
                    ) from exc
                remaining_before_deadline()
                session = self._session
                assert session is not None
                generation_before = self._require_current_generation()
                remaining = remaining_before_deadline()
                signal = _require_healthy_native_status(
                    session,
                    timeout_seconds=min(
                        remaining,
                        _READINESS_STATUS_TIMEOUT_SECONDS,
                    ),
                    observations=observations,
                )
                polls += 1
                remaining = remaining_before_deadline()
                if signal is NativeDaemonReadinessSignal.READY:
                    break

                sleep(
                    min(
                        float(readiness_poll_interval_seconds),
                        round(remaining, 12),
                    )
                )
            except ExpectedSessionReadinessError as exc:
                try:
                    elapsed_seconds = read_clock() - started
                except ExpectedSessionReadinessError:
                    elapsed_seconds = None
                exc.poll_evidence = {
                    "polls": polls,
                    "observations": observations[-20:],
                    "timeout_seconds": float(readiness_timeout_seconds),
                    "elapsed_seconds": elapsed_seconds,
                }
                raise

        # READY must be returned strictly before the readiness deadline. Once it
        # is, witness validation keeps its independent request timeout while
        # generation continuity remains fail-closed.
        if receipt.total_chunks == 0:
            if witness is not None:
                raise ExpectedSessionReadinessError(
                    "a zero-chunk receipt cannot use a search witness"
                )
            generation_after = self._require_current_generation()
            if generation_after != generation_before:
                raise ExpectedSessionReadinessError(
                    "native ChunkHound daemon generation changed during readiness"
                )
            if type(expected_generation) is not ExpectedGenerationEvidence or not (
                expected_generation._matches(self._lease_token, generation_after)
            ):
                raise ExpectedSessionReadinessError(
                    "zero-chunk receipt lacks current lease-bound generation evidence"
                )
            return ExpectedSessionReadiness(identity, None, expected_generation)

        if not isinstance(witness, ExpectedSearchWitness):
            raise ExpectedSessionReadinessError(
                "a nonempty receipt requires an exact search witness"
            )
        _require_safe_witness(witness)
        _require_native_search_witness(session, witness)
        generation_after = self._require_current_generation()
        if generation_after != generation_before:
            raise ExpectedSessionReadinessError(
                "native ChunkHound daemon generation changed during readiness"
            )
        evidence = self._evidence_for(generation_after)
        return ExpectedSessionReadiness(identity, witness, evidence)

    def close(self) -> None:
        if self.state is LeaseState.CLOSED:
            return
        session, self._session = self._session, None
        try:
            if session is not None:
                session.close()
        finally:
            self.state = LeaseState.CLOSED

    def wait_for_daemon_release(
        self,
        timeout_seconds: float = _LEASE_RELEASE_VERIFY_SECONDS,
        *,
        poll_interval_seconds: float = _LEASE_RELEASE_VERIFY_POLL_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> bool:
        """Boundedly verify the native daemon released its lock after close().

        Call after ``close()`` (raises RuntimeError otherwise). The native
        daemon is a SEPARATE process from the MCP proxy that ``close()`` reaps:
        it writes its lock file when it publishes (chunkhound
        daemon/server.py ``write_lock``) and removes it only during graceful
        shutdown (``_graceful_shutdown`` → ``remove_lock``, guarded by the
        ``_lock_written`` flag). CURe daemons are per-session — open() rejects
        a pre-existing generation — and closing the proxy disconnects the
        daemon's only client, so the daemon shuts down and removes its lock.
        "Released" therefore means the generation probe reports no live
        daemon: the lock file is gone OR its recorded pid is no longer alive
        (stale locks count as released, matching the daemon's own lock
        validation in chunkhound daemon/discovery.py). This method never
        kills anything; it only verifies, so a reusable daemon is untouched.
        Returns True on verified release, False on deadline expiry.
        """
        if self.state is not LeaseState.CLOSED:
            raise RuntimeError(
                "ChunkHound daemon release verification requires close() first"
            )
        if self._generation_probe is None:
            raise RuntimeError(
                "ChunkHound daemon lease cannot verify release without a "
                "generation probe"
            )
        return wait_for_daemon_generation_absence(
            self._observe_generation,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            clock=clock,
            sleep=sleep,
        )

    def __enter__(self) -> ChunkHoundDaemonLease:
        return self.open()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
