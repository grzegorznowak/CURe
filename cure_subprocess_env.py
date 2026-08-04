from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

NATIVE_CHUNKHOUND_ENV_KEYS = (
    "CHUNKHOUND_EMBEDDING__API_KEY",
    "CHUNKHOUND_LLM_API_KEY",
    "VOYAGE_API_KEY",
)

CURATED_ENV_INHERIT_KEYS = (
    "CHUNKHOUND_EMBEDDING__API_KEY",
    "CHUNKHOUND_LLM_API_KEY",
    "COLORTERM",
    "FORCE_COLOR",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LOGNAME",
    "NO_COLOR",
    "OPENAI_API_KEY",
    "PATH",
    "SHELL",
    "SSH_AUTH_SOCK",
    "SYSTEMROOT",
    "TEMP",
    "TERM",
    "TMP",
    "TMPDIR",
    "USER",
    "VOYAGE_API_KEY",
)

SESSION_LAUNCH_CONTEXT_ENV = "CURE_CHUNKHOUND_SESSION_LAUNCH_FILE"
_SESSION_LAUNCH_SCHEMA_VERSION = 1
_SESSION_LAUNCH_MAX_BYTES = 1024 * 1024
_SESSION_LAUNCH_KEYS = {
    "schema_version",
    "environment",
    "resolved_executable",
    "environment_digest",
}


class SessionLaunchContextError(RuntimeError):
    """Sanitized failure at the private launch-context boundary."""


@dataclass(frozen=True)
class SessionLaunchContext:
    environment: Mapping[str, str]
    resolved_executable: Path
    environment_digest: str


@dataclass
class SessionLaunchContextPublication:
    """Retained authority for one published launch envelope."""

    path: Path
    _parent_fd: int
    _basename: str
    _file_identity: tuple[int, int]
    _closed: bool = False

    def _release(self) -> None:
        if not self._closed:
            self._closed = True
            os.close(self._parent_fd)

    def cleanup(self) -> None:
        """Remove only the publication owned by this retained parent capability."""
        if self._closed:
            return
        failed = False
        file_fd: int | None = None
        try:
            parent = os.fstat(self._parent_fd)
            if (
                not stat.S_ISDIR(parent.st_mode)
                or parent.st_uid != os.getuid()
                or stat.S_IMODE(parent.st_mode) != 0o700
            ):
                raise _fail("cleanup")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            flags |= getattr(os, "O_CLOEXEC", 0)
            try:
                file_fd = os.open(self._basename, flags, dir_fd=self._parent_fd)
            except FileNotFoundError:
                file_fd = None
            if file_fd is not None:
                metadata = os.fstat(file_fd)
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or (metadata.st_dev, metadata.st_ino) != self._file_identity
                ):
                    raise _fail("cleanup")
                os.unlink(self._basename, dir_fd=self._parent_fd)
        except BaseException:
            failed = True
        finally:
            if file_fd is not None:
                try:
                    os.close(file_fd)
                except BaseException:
                    failed = True
            try:
                self._release()
            except BaseException:
                failed = True
        if failed:
            raise _fail("cleanup")

    def close(self) -> None:
        self.cleanup()

    def __del__(self) -> None:
        try:
            self._release()
        except BaseException:
            pass


def build_curated_subprocess_env(
    *,
    inherited_env: Mapping[str, str] | None = None,
    extra_env: Mapping[str, str] | None = None,
    home_override: Path | None = None,
) -> dict[str, str]:
    source = inherited_env if inherited_env is not None else os.environ
    env: dict[str, str] = {}
    for key in CURATED_ENV_INHERIT_KEYS:
        value = str(source.get(key) or "").strip()
        if value:
            env[key] = value
    if home_override is not None:
        env["HOME"] = str(home_override)
    if extra_env:
        env.update(
            {str(key): str(value) for key, value in extra_env.items() if str(value)}
        )
    return env


def build_curated_provider_env(
    *,
    inherited_env: Mapping[str, str] | None = None,
    extra_env: Mapping[str, str] | None = None,
    home_override: Path | None = None,
) -> dict[str, str]:
    """Project provider-safe variables without native ChunkHound credentials."""
    env = build_curated_subprocess_env(
        inherited_env=inherited_env,
        extra_env=extra_env,
        home_override=home_override,
    )
    for key in NATIVE_CHUNKHOUND_ENV_KEYS:
        env.pop(key, None)
    return env


def build_curated_chunkhound_env(
    *,
    inherited_env: Mapping[str, str] | None = None,
    extra_env: Mapping[str, str] | None = None,
) -> Mapping[str, str]:
    """Build the immutable environment shared by receipt-bearing ChunkHound children."""
    source = inherited_env if inherited_env is not None else os.environ
    env = build_curated_subprocess_env(inherited_env=source)
    for key in NATIVE_CHUNKHOUND_ENV_KEYS:
        value = str(source.get(key) or "").strip()
        if value:
            env[key] = value
    if extra_env:
        env.update(
            {str(key): str(value) for key, value in extra_env.items() if str(value)}
        )
    voyage_key = env.get("VOYAGE_API_KEY")
    if voyage_key and not env.get("CHUNKHOUND_EMBEDDING__API_KEY"):
        env["CHUNKHOUND_EMBEDDING__API_KEY"] = voyage_key
    env["PYTHONSAFEPATH"] = "1"
    return MappingProxyType(env)


def _fail(category: str) -> SessionLaunchContextError:
    return SessionLaunchContextError(f"session launch context rejected ({category})")


def _environment_digest(environment: Mapping[str, str]) -> str:
    encoded = json.dumps(
        dict(environment), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validated_environment(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise _fail("environment")
    environment: dict[str, str] = {}
    for key, item in value.items():
        if (
            not isinstance(key, str)
            or not key
            or "=" in key
            or "\x00" in key
            or not isinstance(item, str)
            or "\x00" in item
        ):
            raise _fail("environment")
        environment[key] = item
    if environment.get("PYTHONSAFEPATH") != "1" or not environment.get("PATH"):
        raise _fail("environment")
    return environment


def _open_validated_parent(parent: Path, *, create: bool) -> int:
    """Return a stable, owner-private directory capability without following it."""
    if create:
        try:
            os.mkdir(parent, 0o700)
        except FileExistsError:
            pass
        except OSError:
            raise _fail("parent") from None
        else:
            # mkdir cannot return a directory capability. A same-UID peer may
            # replace its pathname before the next open, so never publish through
            # a parent first observed only after successful creation.
            raise _fail("parent")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(parent, flags)
    except OSError:
        raise _fail("parent") from None
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise _fail("parent")
    except BaseException:
        os.close(fd)
        raise
    return fd


def _target_parts(path: str | Path) -> tuple[Path, str]:
    target = Path(path)
    basename = target.name
    if not basename or basename in {".", ".."}:
        raise _fail("path")
    return target, basename


def _validated_executable(
    environment: Mapping[str, str], resolved_executable: object
) -> Path:
    if not isinstance(resolved_executable, (str, Path)):
        raise _fail("executable")
    raw = Path(resolved_executable)
    try:
        canonical = raw.resolve(strict=True)
        metadata = canonical.stat()
        selected = shutil.which("chunkhound", path=environment["PATH"])
        selected_canonical = Path(selected).resolve(strict=True) if selected else None
    except (OSError, RuntimeError):
        raise _fail("executable") from None
    if (
        raw != canonical
        or not stat.S_ISREG(metadata.st_mode)
        or not os.access(canonical, os.X_OK)
        or selected_canonical != canonical
    ):
        raise _fail("executable")
    return canonical


def _write_session_launch_context(
    path: str | Path,
    *,
    environment: Mapping[str, str],
    resolved_executable: str | Path,
    environment_digest: str,
) -> SessionLaunchContextPublication:
    """Publish an exclusive, owner-only launch envelope without exposing values."""
    target, basename = _target_parts(path)
    parent_fd = _open_validated_parent(target.parent, create=True)
    created = False
    file_identity: tuple[int, int] | None = None
    try:
        safe_environment = _validated_environment(dict(environment))
        digest = _environment_digest(safe_environment)
        if not isinstance(environment_digest, str) or environment_digest != digest:
            raise _fail("digest")
        executable = _validated_executable(safe_environment, resolved_executable)
        payload = json.dumps(
            {
                "schema_version": _SESSION_LAUNCH_SCHEMA_VERSION,
                "environment": safe_environment,
                "resolved_executable": str(executable),
                "environment_digest": digest,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        if len(payload) > _SESSION_LAUNCH_MAX_BYTES:
            raise _fail("size")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(basename, flags, 0o600, dir_fd=parent_fd)
        created = True
        try:
            metadata = os.fstat(fd)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                raise _fail("file")
            file_identity = (metadata.st_dev, metadata.st_ino)
            with os.fdopen(fd, "wb", closefd=False) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(fd)
    except BaseException as exc:
        if created:
            try:
                os.unlink(basename, dir_fd=parent_fd)
            except BaseException:
                pass
        try:
            os.close(parent_fd)
        except BaseException:
            pass
        if isinstance(exc, SessionLaunchContextError):
            raise
        raise _fail("write") from None
    if file_identity is None:
        try:
            os.close(parent_fd)
        except BaseException:
            pass
        raise _fail("write")
    return SessionLaunchContextPublication(
        path=target,
        _parent_fd=parent_fd,
        _basename=basename,
        _file_identity=file_identity,
    )


def write_session_launch_context(
    path: str | Path,
    *,
    environment: Mapping[str, str],
    resolved_executable: str | Path,
    environment_digest: str,
) -> SessionLaunchContextPublication:
    failed = False
    result: SessionLaunchContextPublication | None = None
    try:
        result = _write_session_launch_context(
            path,
            environment=environment,
            resolved_executable=resolved_executable,
            environment_digest=environment_digest,
        )
    except BaseException:
        failed = True
    if failed or result is None:
        raise _fail("write")
    return result


def _load_session_launch_context(
    path: str | Path,
    *,
    expected_resolved_executable: str | Path | None = None,
    expected_environment_digest: str | None = None,
) -> SessionLaunchContext:
    """Load and independently validate a private launch envelope, fail closed."""
    target, basename = _target_parts(path)
    parent_fd = _open_validated_parent(target.parent, create=False)
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_CLOEXEC", 0)
        fd = os.open(basename, flags, dir_fd=parent_fd)
        try:
            metadata = os.fstat(fd)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_size > _SESSION_LAUNCH_MAX_BYTES
            ):
                raise _fail("file")
            raw = bytearray()
            while len(raw) <= _SESSION_LAUNCH_MAX_BYTES:
                block = os.read(
                    fd, min(65536, _SESSION_LAUNCH_MAX_BYTES + 1 - len(raw))
                )
                if not block:
                    break
                raw.extend(block)
            if len(raw) > _SESSION_LAUNCH_MAX_BYTES:
                raise _fail("size")
        finally:
            os.close(fd)
        envelope = json.loads(bytes(raw).decode("utf-8"))
        if not isinstance(envelope, dict) or set(envelope) != _SESSION_LAUNCH_KEYS:
            raise _fail("schema")
        if envelope.get("schema_version") != _SESSION_LAUNCH_SCHEMA_VERSION:
            raise _fail("schema")
        environment = _validated_environment(envelope.get("environment"))
        digest = _environment_digest(environment)
        if envelope.get("environment_digest") != digest:
            raise _fail("digest")
        executable = _validated_executable(
            environment, envelope.get("resolved_executable")
        )
        if (
            expected_environment_digest is not None
            and digest != expected_environment_digest
        ):
            raise _fail("trusted-digest")
        if expected_resolved_executable is not None:
            try:
                expected = Path(expected_resolved_executable).resolve(strict=True)
            except (OSError, RuntimeError):
                raise _fail("trusted-executable") from None
            if executable != expected:
                raise _fail("trusted-executable")
        return SessionLaunchContext(
            environment=MappingProxyType(environment),
            resolved_executable=executable,
            environment_digest=digest,
        )
    except SessionLaunchContextError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        raise _fail("load") from None
    finally:
        os.close(parent_fd)


def load_session_launch_context(
    path: str | Path,
    *,
    expected_resolved_executable: str | Path | None = None,
    expected_environment_digest: str | None = None,
) -> SessionLaunchContext:
    failed = False
    result: SessionLaunchContext | None = None
    try:
        result = _load_session_launch_context(
            path,
            expected_resolved_executable=expected_resolved_executable,
            expected_environment_digest=expected_environment_digest,
        )
    except (
        SessionLaunchContextError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ):
        failed = True
    if failed or result is None:
        raise _fail("load")
    return result


def cleanup_session_launch_context(path: str | Path) -> None:
    """Unlink a basename through a stable, validated parent capability."""
    failed = False
    parent_fd: int | None = None
    try:
        target, basename = _target_parts(path)
        parent_fd = _open_validated_parent(target.parent, create=False)
        os.unlink(basename, dir_fd=parent_fd)
    except FileNotFoundError:
        return
    except (SessionLaunchContextError, OSError, TypeError, ValueError):
        failed = True
    finally:
        if parent_fd is not None:
            os.close(parent_fd)
    if failed:
        raise _fail("cleanup")
