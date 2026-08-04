from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import threading
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

import pytest

import cure_subprocess_env as subprocess_env

pytestmark = pytest.mark.skipif(
    os.name != "posix",
    reason="secure launch-context ownership, modes, and symlinks are POSIX contracts",
)


@dataclass(frozen=True)
class LaunchFixture:
    parent: Path
    path: Path
    executable: Path
    environment: dict[str, str]
    digest: str


def _api(name: str) -> Callable[..., object]:
    """Resolve proposed APIs in test bodies so every RED node still collects."""
    candidate = getattr(subprocess_env, name)
    assert callable(candidate)
    return candidate


def _environment_digest(environment: dict[str, str]) -> str:
    """Compute the envelope digest independently of production helpers."""
    payload = json.dumps(
        environment,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@pytest.fixture
def launch_fixture(tmp_path: Path) -> LaunchFixture:
    parent = tmp_path / "session-owned"
    parent.mkdir(mode=0o700)
    parent.chmod(0o700)

    executable_dir = tmp_path / "fixture-bin"
    executable_dir.mkdir(mode=0o700)
    executable = executable_dir / "chunkhound"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o700)
    executable = executable.resolve()

    environment = dict(
        subprocess_env.build_curated_chunkhound_env(
            inherited_env={
                "HOME": str(tmp_path),
                "PATH": str(executable_dir),
            },
        )
    )
    assert environment["PYTHONSAFEPATH"] == "1"
    assert shutil.which("chunkhound", path=environment["PATH"]) == str(executable)

    return LaunchFixture(
        parent=parent,
        path=parent / "chunkhound-launch-context",
        executable=executable,
        environment=environment,
        digest=_environment_digest(environment),
    )


def _write(fixture: LaunchFixture, *, path: Path | None = None) -> object:
    write = _api("write_session_launch_context")
    return write(
        path or fixture.path,
        environment=fixture.environment,
        resolved_executable=fixture.executable,
        environment_digest=_environment_digest(fixture.environment),
    )


def _load(fixture: LaunchFixture, *, path: Path | None = None) -> object:
    load = _api("load_session_launch_context")
    return load(
        path or fixture.path,
        expected_resolved_executable=fixture.executable,
        expected_environment_digest=fixture.digest,
    )


def _assert_secret_safe(
    exc_info: pytest.ExceptionInfo[BaseException], *secrets: str
) -> None:
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc_info.value
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__

    rendered = [
        str(exc_info.value),
        repr(exc_info.value),
        repr(exc_info.value.args),
        "".join(
            traceback.format_exception(
                type(exc_info.value), exc_info.value, exc_info.value.__traceback__
            )
        ),
    ]
    for error in chain:
        rendered.extend((str(error), repr(error), repr(error.args)))

    for secret in secrets:
        assert secret
        for text in rendered:
            assert secret not in text


def test_roundtrips_exact_immutable_curated_environment_privately(
    launch_fixture: LaunchFixture,
) -> None:
    expected_environment = dict(launch_fixture.environment)
    _write(launch_fixture)
    launch_fixture.environment["HOME"] = "mutated-after-publication"

    metadata = launch_fixture.path.lstat()
    assert stat.S_ISREG(metadata.st_mode)
    assert not launch_fixture.path.is_symlink()
    assert stat.S_IMODE(metadata.st_mode) == 0o600
    assert stat.S_IMODE(launch_fixture.parent.stat().st_mode) == 0o700
    assert list(launch_fixture.parent.iterdir()) == [launch_fixture.path]

    loaded = _load(launch_fixture)
    assert dict(loaded.environment) == expected_environment  # type: ignore[attr-defined]
    assert loaded.resolved_executable == launch_fixture.executable  # type: ignore[attr-defined]
    assert loaded.environment_digest == launch_fixture.digest  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        loaded.environment["HOME"] = "changed"  # type: ignore[attr-defined,index]


@pytest.mark.parametrize(
    "parent_mode", [0o750, 0o755], ids=["group-accessible", "world-accessible"]
)
def test_writer_rejects_accessible_parent_without_disclosing_environment(
    launch_fixture: LaunchFixture,
    parent_mode: int,
) -> None:
    secret = "writer-parent-secret"
    launch_fixture.environment["OPENAI_API_KEY"] = secret
    launch_fixture.parent.chmod(parent_mode)
    _api("write_session_launch_context")

    with pytest.raises(Exception) as raised:
        _write(launch_fixture)

    _assert_secret_safe(raised, secret)
    assert not launch_fixture.path.exists()


def test_writer_fails_closed_when_fresh_parent_is_swapped_after_real_mkdir(
    launch_fixture: LaunchFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A1: successful fresh-parent creation must stay bound through acquisition."""
    secret = "post-mkdir-parent-swap-secret"
    launch_fixture.environment["OPENAI_API_KEY"] = secret
    fresh_parent = tmp_path / "fresh-session-owned"
    fixture = LaunchFixture(
        parent=fresh_parent,
        path=fresh_parent / launch_fixture.path.name,
        executable=launch_fixture.executable,
        environment=launch_fixture.environment,
        digest=_environment_digest(launch_fixture.environment),
    )
    original_parent = tmp_path / "created-original-parent"
    replacement_staging = tmp_path / "replacement-parent-staging"
    replacement_staging.mkdir(mode=0o700)
    replacement_staging.chmod(0o700)
    real_mkdir = os.mkdir
    swapped = False

    def swap_immediately_after_target_mkdir(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> None:
        nonlocal swapped
        real_mkdir(path, mode, dir_fd=dir_fd)
        candidate = Path(os.fsdecode(path))
        if dir_fd is None:
            targets_fixture = candidate == fixture.parent
        else:
            target_parent = os.fstat(dir_fd)
            expected_parent = fixture.parent.parent.stat()
            targets_fixture = (
                candidate == Path(fixture.parent.name)
                and target_parent.st_dev == expected_parent.st_dev
                and target_parent.st_ino == expected_parent.st_ino
            )
        if not swapped and targets_fixture:
            swapped = True
            fixture.parent.rename(original_parent)
            replacement_staging.rename(fixture.parent)

    monkeypatch.setattr(os, "mkdir", swap_immediately_after_target_mkdir)
    rejected: BaseException | None = None
    try:
        _write(fixture)
    except BaseException as exc:  # inspect all fail-closed properties below
        rejected = exc

    assert swapped, "test must swap immediately after the successful target mkdir"
    original_context = original_parent / fixture.path.name
    replacement_context = fixture.parent / fixture.path.name
    original_body = (
        original_context.read_text(encoding="utf-8")
        if original_context.is_file()
        else ""
    )
    replacement_body = (
        replacement_context.read_text(encoding="utf-8")
        if replacement_context.is_file()
        else ""
    )
    assert secret not in original_body
    assert secret not in replacement_body, (
        "the pathname replacement received the launch secret after fresh mkdir"
    )
    assert rejected is not None, "fresh-parent identity replacement must fail closed"
    _assert_secret_safe(pytest.ExceptionInfo.from_exception(rejected), secret)


def test_writer_remains_anchored_when_parent_is_swapped_at_final_open(
    launch_fixture: LaunchFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The validated parent capability, not its replaceable pathname, owns output."""
    secret = "writer-parent-swap-secret"
    launch_fixture.environment["OPENAI_API_KEY"] = secret
    fixture = LaunchFixture(
        parent=launch_fixture.parent,
        path=launch_fixture.path,
        executable=launch_fixture.executable,
        environment=launch_fixture.environment,
        digest=_environment_digest(launch_fixture.environment),
    )
    validated_parent = tmp_path / "originally-validated-parent"
    attacker_parent = tmp_path / "attacker-replacement-parent"
    attacker_parent.mkdir(mode=0o700)
    attacker_parent.chmod(0o700)
    real_open = os.open
    swapped = False

    def swap_parent_then_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        candidate = Path(os.fsdecode(path))
        if not swapped and flags & os.O_CREAT and candidate.name == fixture.path.name:
            swapped = True
            fixture.parent.rename(validated_parent)
            attacker_parent.rename(fixture.parent)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", swap_parent_then_open)
    published = _api("write_session_launch_context")(
        fixture.path,
        environment=fixture.environment,
        resolved_executable=fixture.executable,
        environment_digest=fixture.digest,
    )

    assert swapped, "test must swap the parent exactly at final-component creation"
    published_path = getattr(published, "path", published)
    assert Path(published_path) == fixture.path
    anchored_context = validated_parent / fixture.path.name
    attacker_context = fixture.parent / fixture.path.name
    assert anchored_context.is_file()
    assert secret in anchored_context.read_text(encoding="utf-8")
    assert not attacker_context.exists() and not attacker_context.is_symlink()


def test_writer_rejects_symlink_parent_without_following_it(
    launch_fixture: LaunchFixture,
    tmp_path: Path,
) -> None:
    secret = "writer-symlink-parent-secret"
    launch_fixture.environment["OPENAI_API_KEY"] = secret
    linked_parent = tmp_path / "linked-session"
    linked_parent.symlink_to(launch_fixture.parent, target_is_directory=True)
    linked_path = linked_parent / launch_fixture.path.name
    _api("write_session_launch_context")

    with pytest.raises(Exception) as raised:
        _write(launch_fixture, path=linked_path)

    _assert_secret_safe(raised, secret)
    assert not launch_fixture.path.exists()


@pytest.mark.parametrize("destination_kind", ["regular", "symlink"])
def test_writer_never_overwrites_preexisting_destination(
    launch_fixture: LaunchFixture,
    tmp_path: Path,
    destination_kind: str,
) -> None:
    environment_secret = "preexisting-writer-environment-secret"
    sentinel = "preexisting-destination-must-remain-byte-exact"
    launch_fixture.environment["OPENAI_API_KEY"] = environment_secret
    external = tmp_path / "external-target"
    if destination_kind == "regular":
        launch_fixture.path.write_text(sentinel, encoding="utf-8")
        launch_fixture.path.chmod(0o600)
    else:
        external.write_text(sentinel, encoding="utf-8")
        launch_fixture.path.symlink_to(external)
    _api("write_session_launch_context")

    with pytest.raises(Exception) as raised:
        _write(launch_fixture)

    _assert_secret_safe(raised, environment_secret, sentinel)
    if destination_kind == "regular":
        assert launch_fixture.path.read_text(encoding="utf-8") == sentinel
        assert not launch_fixture.path.is_symlink()
    else:
        assert launch_fixture.path.is_symlink()
        assert external.read_text(encoding="utf-8") == sentinel


@pytest.mark.parametrize("payload_kind", ["malformed", "oversized"])
def test_loader_fails_closed_without_disclosing_payload_or_exception_chain(
    launch_fixture: LaunchFixture,
    payload_kind: str,
) -> None:
    secret = "malformed-loader-payload-secret"
    if payload_kind == "malformed":
        launch_fixture.path.write_text("not-json:" + secret, encoding="utf-8")
    else:
        launch_fixture.path.write_bytes((secret.encode("utf-8") + b"x") * 70_000)
    launch_fixture.path.chmod(0o600)
    _api("load_session_launch_context")

    with pytest.raises(Exception) as raised:
        _load(launch_fixture)

    _assert_secret_safe(raised, secret)


@pytest.mark.parametrize(
    "unsafe_metadata",
    ["file-mode", "file-symlink", "parent-group", "parent-changed-after-write"],
)
def test_loader_rejects_unsafe_file_and_parent_metadata(
    launch_fixture: LaunchFixture,
    tmp_path: Path,
    unsafe_metadata: str,
) -> None:
    secret = "loader-metadata-environment-secret"
    launch_fixture.environment["OPENAI_API_KEY"] = secret
    fixture = LaunchFixture(
        parent=launch_fixture.parent,
        path=launch_fixture.path,
        executable=launch_fixture.executable,
        environment=launch_fixture.environment,
        digest=_environment_digest(launch_fixture.environment),
    )
    _write(fixture)

    load_path = fixture.path
    if unsafe_metadata == "file-mode":
        fixture.path.chmod(0o640)
    elif unsafe_metadata == "file-symlink":
        regular = fixture.parent / "regular-context"
        fixture.path.rename(regular)
        load_path = fixture.path
        load_path.symlink_to(regular.name)
    elif unsafe_metadata == "parent-group":
        fixture.parent.chmod(0o750)
    else:
        # This is deliberately post-publication: the loader must revalidate ownership.
        fixture.parent.chmod(0o755)
    _api("load_session_launch_context")

    with pytest.raises(Exception) as raised:
        _load(fixture, path=load_path)

    _assert_secret_safe(raised, secret)


def test_loader_recomputes_environment_digest_and_rejects_tampered_envelope(
    launch_fixture: LaunchFixture,
) -> None:
    original_secret = "digest-original-secret-AA"
    tampered_secret = "digest-tampered-secret-BB"
    assert len(original_secret) == len(tampered_secret)
    launch_fixture.environment["OPENAI_API_KEY"] = original_secret
    fixture = LaunchFixture(
        parent=launch_fixture.parent,
        path=launch_fixture.path,
        executable=launch_fixture.executable,
        environment=launch_fixture.environment,
        digest=_environment_digest(launch_fixture.environment),
    )
    _write(fixture)

    # The JSON envelope is approved contract; preserve its stored digest while
    # replacing a same-length value so metadata-only validation cannot pass.
    envelope = json.loads(fixture.path.read_text(encoding="utf-8"))
    assert envelope["environment_digest"] == fixture.digest
    envelope["environment"]["OPENAI_API_KEY"] = tampered_secret
    fixture.path.write_text(
        json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )
    fixture.path.chmod(0o600)
    _api("load_session_launch_context")

    with pytest.raises(Exception) as raised:
        _load(fixture)

    _assert_secret_safe(raised, original_secret, tampered_secret)


def test_loader_rejects_wrong_trusted_digest_and_executable(
    launch_fixture: LaunchFixture,
    tmp_path: Path,
) -> None:
    secret = "trusted-binding-loader-secret"
    launch_fixture.environment["OPENAI_API_KEY"] = secret
    fixture = LaunchFixture(
        parent=launch_fixture.parent,
        path=launch_fixture.path,
        executable=launch_fixture.executable,
        environment=launch_fixture.environment,
        digest=_environment_digest(launch_fixture.environment),
    )
    _write(fixture)
    other_executable = tmp_path / "fixture-bin" / "other-chunkhound"
    other_executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    other_executable.chmod(0o700)

    load = _api("load_session_launch_context")
    for expected_executable, expected_digest in (
        (other_executable.resolve(), fixture.digest),
        (fixture.executable, "f" * 64),
    ):
        with pytest.raises(Exception) as raised:
            load(
                fixture.path,
                expected_resolved_executable=expected_executable,
                expected_environment_digest=expected_digest,
            )
        _assert_secret_safe(raised, secret)

    bad_path = fixture.parent / "bad-digest-context"
    write = _api("write_session_launch_context")
    with pytest.raises(Exception) as raised:
        write(
            bad_path,
            environment=fixture.environment,
            resolved_executable=fixture.executable,
            environment_digest="a" * 64,
        )
    _assert_secret_safe(raised, secret)
    assert not bad_path.exists()


def test_publication_capability_cleans_original_inode_after_parent_rename(
    launch_fixture: LaunchFixture,
    tmp_path: Path,
) -> None:
    """A2: use publication-time cleanup authority; path fallback only exposes RED."""
    secret = "cleanup-original-parent-inode-secret"
    replacement_sentinel = "replacement-basename-must-survive-byte-exact"
    launch_fixture.environment["OPENAI_API_KEY"] = secret
    fixture = LaunchFixture(
        parent=launch_fixture.parent,
        path=launch_fixture.path,
        executable=launch_fixture.executable,
        environment=launch_fixture.environment,
        digest=_environment_digest(launch_fixture.environment),
    )
    publication = _write(fixture)
    original_parent = tmp_path / "published-original-parent"
    fixture.parent.rename(original_parent)
    fixture.parent.mkdir(mode=0o700)
    fixture.parent.chmod(0o700)
    replacement_context = fixture.parent / fixture.path.name
    replacement_context.write_text(replacement_sentinel, encoding="utf-8")
    replacement_context.chmod(0o600)
    original_context = original_parent / fixture.path.name
    assert secret in original_context.read_text(encoding="utf-8")

    publication_path = getattr(publication, "path", publication)
    assert Path(publication_path) == fixture.path
    capability_cleanup = getattr(publication, "cleanup", None)
    if not callable(capability_cleanup):
        capability_cleanup = getattr(publication, "close", None)
    if callable(capability_cleanup):
        capability_cleanup()
        capability_cleanup()  # cleanup capability is an idempotent lease
    else:
        # Current path-only API has no publication authority; invoke it solely to
        # demonstrate the moved-inode residue/false-success vulnerability.
        _api("cleanup_session_launch_context")(fixture.path)

    assert not original_context.exists(), (
        "cleanup returned successfully but secret residue survived on the original "
        "published parent inode"
    )
    assert replacement_context.is_file(), (
        "cleanup falsely acted on a same-basename replacement instead of its lease"
    )
    assert replacement_context.read_text(encoding="utf-8") == replacement_sentinel


def test_cleanup_is_idempotent_and_does_not_follow_final_symlink(
    launch_fixture: LaunchFixture,
    tmp_path: Path,
) -> None:
    cleanup = _api("cleanup_session_launch_context")
    _write(launch_fixture)

    cleanup(launch_fixture.path)
    cleanup(launch_fixture.path)
    assert not launch_fixture.path.exists() and not launch_fixture.path.is_symlink()

    external = tmp_path / "external-secret"
    external.write_text("must remain", encoding="utf-8")
    launch_fixture.path.symlink_to(external)
    cleanup(launch_fixture.path)
    cleanup(launch_fixture.path)

    assert not launch_fixture.path.exists() and not launch_fixture.path.is_symlink()
    assert external.read_text(encoding="utf-8") == "must remain"


def test_coordinator_broker_owns_launch_authority_against_substituted_client(
    launch_fixture: LaunchFixture,
    tmp_path: Path,
) -> None:
    """B: an untrusted client may request work, never provide launch authority."""
    import cure_chunkhound

    foreign_secret = "self-consistent-foreign-broker-secret"
    trusted_repo = tmp_path / "trusted-repo"
    trusted_repo.mkdir()
    trusted_config = trusted_repo / "chunkhound.json"
    trusted_database = trusted_repo / ".chunkhound.db"
    trusted_config.write_text("{}\n", encoding="utf-8")
    trusted_database.touch()

    foreign_bin = tmp_path / "foreign-bin"
    foreign_bin.mkdir(mode=0o700)
    foreign_executable = foreign_bin / "chunkhound"
    foreign_executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    foreign_executable.chmod(0o700)
    foreign_executable = foreign_executable.resolve()
    foreign_environment = dict(launch_fixture.environment)
    foreign_environment.update(
        {"PATH": str(foreign_bin), "OPENAI_API_KEY": foreign_secret}
    )
    foreign_digest = _environment_digest(foreign_environment)
    foreign_parent = tmp_path / "foreign-envelope-parent"
    foreign_parent.mkdir(mode=0o700)
    foreign_parent.chmod(0o700)
    foreign_path = foreign_parent / "context.json"
    _api("write_session_launch_context")(
        foreign_path,
        environment=foreign_environment,
        resolved_executable=foreign_executable,
        environment_digest=foreign_digest,
    )
    foreign_context = _api("load_session_launch_context")(
        foreign_path,
        expected_resolved_executable=foreign_executable,
        expected_environment_digest=foreign_digest,
    )
    assert dict(foreign_context.environment) == foreign_environment  # type: ignore[attr-defined]

    foreign_repo = tmp_path / "foreign-repo"
    foreign_repo.mkdir()
    foreign_config = foreign_repo / "chunkhound.json"
    foreign_database = foreign_repo / ".chunkhound.db"
    foreign_config.write_text("{}\n", encoding="utf-8")
    foreign_database.touch()
    forged_request = {
        "operation": "search",
        "arguments": {"query": "security-red"},
        "environment": foreign_environment,
        "resolved_executable": str(foreign_executable),
        "environment_digest": foreign_digest,
        "cwd": str(foreign_repo),
        "config_path": str(foreign_config),
        "database_path": str(foreign_database),
        "launch_context": str(foreign_path),
    }
    constructed: list[dict[str, object]] = []

    def observe_session(**kwargs: object) -> object:
        constructed.append(dict(kwargs))
        return object()

    broker_type = getattr(cure_chunkhound, "ChunkHoundHelperBroker", None)
    authority_type = getattr(cure_chunkhound, "HelperLaunchAuthority", None)
    if callable(broker_type) and callable(authority_type):
        authority = None
        foreign_authority = None
        broker = None
        foreign_broker = None
        try:
            authority = authority_type(
                environment=launch_fixture.environment,
                resolved_executable=launch_fixture.executable,
                expected_executable_digest=hashlib.sha256(
                    launch_fixture.executable.read_bytes()
                ).hexdigest(),
                expected_config_digest=hashlib.sha256(b"{}").hexdigest(),
                environment_digest=launch_fixture.digest,
                cwd=trusted_repo,
                config_path=trusted_config,
                database_path=trusted_database,
            )
            broker = broker_type(authority=authority, session_factory=observe_session)
            with pytest.raises(Exception) as rejected:
                broker.open_session(forged_request)
            _assert_secret_safe(rejected, foreign_secret)
            assert constructed == [], (
                "forged launch fields reached trusted construction"
            )

            # A fake helper result without a coordinator record is not authority.
            with pytest.raises(Exception):
                broker.accept_client_result(
                    "missing-broker-record", {"ok": True, "results": []}
                )
            assert constructed == []

            record_id = broker.open_session(
                {"operation": "search", "arguments": {"query": "positive-control"}}
            )
            assert isinstance(record_id, str) and record_id.strip(), (
                "trusted session open must publish a nonempty opaque broker record id"
            )
            assert record_id not in {"search", "positive-control"}
            assert len(constructed) == 1
            trusted = constructed[0]
            assert dict(trusted["env"]) == launch_fixture.environment
            assert Path(str(trusted["binary"])).resolve() == launch_fixture.executable
            assert Path(str(trusted["cwd"])).resolve() == trusted_repo.resolve()
            assert (
                Path(str(trusted["config_path"])).resolve() == trusted_config.resolve()
            )
            assert Path(str(trusted["repo_path"])).resolve() == trusted_repo.resolve()

            authentic_result = {"ok": True, "results": [{"file_path": "trusted.py"}]}
            broker.accept_client_result(record_id, authentic_result)
            with pytest.raises(Exception):
                broker.accept_client_result(record_id, authentic_result)

            foreign_constructed: list[dict[str, object]] = []

            def observe_foreign_session(**kwargs: object) -> object:
                foreign_constructed.append(dict(kwargs))
                return object()

            foreign_authority = authority_type(
                environment=launch_fixture.environment,
                resolved_executable=launch_fixture.executable,
                expected_executable_digest=hashlib.sha256(
                    launch_fixture.executable.read_bytes()
                ).hexdigest(),
                expected_config_digest=hashlib.sha256(b"{}").hexdigest(),
                environment_digest=launch_fixture.digest,
                cwd=trusted_repo,
                config_path=trusted_config,
                database_path=trusted_database,
            )
            foreign_broker = broker_type(
                authority=foreign_authority,
                session_factory=observe_foreign_session,
            )
            foreign_record_id = foreign_broker.open_session(
                {"operation": "search", "arguments": {"query": "foreign-record"}}
            )
            assert isinstance(foreign_record_id, str) and foreign_record_id.strip()
            assert foreign_record_id != record_id
            assert len(foreign_constructed) == 1
            with pytest.raises(Exception):
                broker.accept_client_result(foreign_record_id, authentic_result)
        finally:
            if foreign_broker is not None:
                foreign_broker.close()
            if broker is not None:
                broker.close()
            if foreign_authority is not None:
                foreign_authority.close()
            if authority is not None:
                authority.close()

    # Always exercise the real ambient route after any standalone broker contract
    # checks. Merely defining unintegrated broker classes must not bypass this proof.
    class ReachedTrustedConstruction(RuntimeError):
        pass

    direct_constructed: list[dict[str, object]] = []

    def observe_direct_session(**kwargs: object) -> object:
        direct_constructed.append(dict(kwargs))
        raise ReachedTrustedConstruction

    # A completely substituted client simultaneously presents its own envelope,
    # matching verifier values, and every launch field. The public route must be
    # disabled or reject that authority before JsonRpcSession construction.
    pointer = {subprocess_env.SESSION_LAUNCH_CONTEXT_ENV: str(foreign_path)}
    with (
        mock.patch.dict(os.environ, pointer, clear=True),
        mock.patch.object(
            cure_chunkhound, "JsonRpcSession", side_effect=observe_direct_session
        ),
        pytest.raises(Exception) as rejected,
    ):
        cure_chunkhound.run_chunkhound_tool_payload(
            foreign_config,
            foreign_repo,
            "search",
            {"query": "security-red"},
            cwd=foreign_repo,
            binary=str(foreign_executable),
            expected_environment_digest=foreign_digest,
            expected_resolved_executable=foreign_executable,
        )

    _assert_secret_safe(rejected, foreign_secret)
    assert direct_constructed == [], (
        "simultaneous foreign envelope, verifier, and launch fields reached "
        "JsonRpcSession; the ambient direct route must be disabled or reject them "
        "before construction without exposing the foreign secret"
    )


def test_broker_ipc_is_bounded_concurrent_and_closes_endpoint(
    launch_fixture: LaunchFixture,
    tmp_path: Path,
) -> None:
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import cure_chunkhound
    from cure_chunkhound_broker import request_helper_broker

    repo = tmp_path / "repo"
    repo.mkdir()
    config = repo / "chunkhound.json"
    database = repo / ".chunkhound.db"
    config.write_text("{}\n", encoding="utf-8")
    database.touch()
    authority = cure_chunkhound.HelperLaunchAuthority(
        environment=launch_fixture.environment,
        resolved_executable=launch_fixture.executable,
        expected_executable_digest=hashlib.sha256(
            launch_fixture.executable.read_bytes()
        ).hexdigest(),
        expected_config_digest=hashlib.sha256(b"{}").hexdigest(),
        environment_digest=launch_fixture.digest,
        cwd=repo,
        config_path=config,
        database_path=database,
    )
    broker = cure_chunkhound.ChunkHoundHelperBroker(authority=authority)
    endpoint = broker.start()
    barrier = threading.Barrier(8)

    def fake_payload(*args: object, **kwargs: object) -> dict[str, object]:
        barrier.wait(timeout=5)
        return {"ok": True, "result": {"results": []}}

    scope = broker.begin_scope()
    try:
        with (
            mock.patch.object(
                cure_chunkhound,
                "run_chunkhound_tool_payload",
                side_effect=fake_payload,
            ),
            ThreadPoolExecutor(max_workers=8) as clients,
        ):
            futures = [
                clients.submit(
                    request_helper_broker,
                    endpoint,
                    {
                        "operation": "search",
                        "arguments": {"query": f"q-{index}"},
                        "scope": scope,
                    },
                )
                for index in range(8)
            ]
            payloads = [future.result(timeout=10) for future in futures]

        assert all(payload["ok"] for payload in payloads)
        assert len({str(payload["broker_record_id"]) for payload in payloads}) == 8
        assert len(broker.records_for_scope(scope)) == 8
    finally:
        broker.close()
    with pytest.raises(Exception):
        request_helper_broker(
            endpoint,
            {"operation": "search", "arguments": {"query": "after-close"}},
            timeout=0.1,
        )


def test_isolated_wheel_imports_chunkhound_broker(tmp_path: Path) -> None:
    """B1 RED: the installed artifact must contain the broker dependency."""
    project = Path(__file__).resolve().parents[1]
    wheel_dir = tmp_path / "wheelhouse"
    wheel_dir.mkdir()
    built = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            str(project),
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheel_dir),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert built.returncode == 0, built.stderr[-2000:]
    wheels = list(wheel_dir.glob("*.whl"))
    assert len(wheels) == 1
    isolated = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            (
                "import sys; sys.path.insert(0, sys.argv[1]); "
                "import cure_chunkhound_broker, cure_chunkhound; "
                "assert cure_chunkhound.ChunkHoundHelperBroker"
            ),
            str(wheels[0]),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert isolated.returncode == 0, isolated.stderr


@pytest.mark.parametrize("forgery_route", ["stdout", "events"])
def test_forged_provider_output_cannot_substitute_for_parent_broker_record(
    launch_fixture: LaunchFixture,
    tmp_path: Path,
    forgery_route: str,
) -> None:
    """B1 RED: only a real parent record correlated by the real validator proves use."""
    import cure
    import cure_chunkhound
    from cure_chunkhound_broker import request_helper_broker

    repo = tmp_path / "proof-repo"
    repo.mkdir()
    config = repo / "chunkhound.json"
    database = repo / ".chunkhound.db"
    config.write_text("{}\n", encoding="utf-8")
    database.touch()
    authority = cure_chunkhound.HelperLaunchAuthority(
        environment=launch_fixture.environment,
        resolved_executable=launch_fixture.executable,
        expected_executable_digest=hashlib.sha256(
            launch_fixture.executable.read_bytes()
        ).hexdigest(),
        expected_config_digest=hashlib.sha256(b"{}").hexdigest(),
        environment_digest=launch_fixture.digest,
        cwd=repo,
        config_path=config,
        database_path=database,
    )
    broker = cure_chunkhound.ChunkHoundHelperBroker(authority=authority)
    endpoint = broker.start()
    scope = broker.begin_scope()
    helper_path = "/tmp/cure/work/bin/cure-chunkhound"
    genuine_payload = {
        "ok": True,
        "command": "search",
        "tool_name": "search",
        "query": "needle",
        "helper_path": helper_path,
        "result": {
            "content": [{"type": "text", "text": '{"results": []}'}],
            "isError": False,
        },
    }

    def write_event(
        path: Path,
        payload: dict[str, object] | None,
        *,
        output_prefix: str = "",
    ) -> None:
        item: dict[str, object] = {
            "id": "helper-search",
            "type": "command_execution",
            "command": '"$CURE_CHUNKHOUND_HELPER" search "needle"',
            "aggregated_output": output_prefix + json.dumps(payload)
            if payload is not None
            else "clean",
            "exit_code": 0,
            "status": "completed",
        }
        path.write_text(
            json.dumps({"type": "item.completed", "item": item}) + "\n",
            encoding="utf-8",
        )

    try:
        with mock.patch.object(
            cure_chunkhound,
            "run_chunkhound_tool_payload",
            return_value=genuine_payload,
        ):
            genuine_result = request_helper_broker(
                endpoint,
                {
                    "operation": "search",
                    "arguments": {"query": "needle"},
                    "scope": scope,
                },
            )
        genuine_records = broker.records_for_scope(scope)
        assert len(genuine_records) == 1
        genuine_record_id = genuine_records[0]["record_id"]
        assert genuine_result["broker_record_id"] == genuine_record_id

        forged_record_id = "f" * len(genuine_record_id)
        forged_events = tmp_path / f"forged-{forgery_route}.jsonl"
        forged_event_payload = (
            {**genuine_payload, "broker_record_id": forged_record_id}
            if forgery_route == "events"
            else None
        )
        write_event(forged_events, forged_event_payload)
        (tmp_path / "agent-output.md").write_text(
            forged_record_id if forgery_route == "stdout" else "clean",
            encoding="utf-8",
        )
        forged_meta = {
            "chunkhound_broker_required": True,
            "chunkhound_broker_records": genuine_records,
            "codex_events_path": str(forged_events),
            "codex_events_start_offset": 0,
            "codex_events_end_offset": forged_events.stat().st_size,
        }
        with pytest.raises(cure.ReviewflowError, match="ChunkHound tool proof"):
            cure._enforce_chunkhound_tool_proof(
                meta={},
                work_dir=tmp_path,
                provider="codex",
                review_stage="multipass_plan",
                prompt_template_name="mrereview_gh_local_big_plan.md",
                adapter_meta=forged_meta,
            )

        correlated_forgeries = {
            "tampered-result-digest": (
                {
                    **genuine_result,
                    "result": {
                        "content": [
                            {"type": "text", "text": '{"results": ["tampered"]}'}
                        ],
                        "isError": False,
                    },
                },
                genuine_records,
            ),
            "operation-mismatch": (
                dict(genuine_result),
                [{**genuine_records[0], "operation": "code_research"}],
            ),
        }
        for forgery_name, (
            forged_payload,
            correlated_records,
        ) in correlated_forgeries.items():
            assert forged_payload["broker_record_id"] == genuine_record_id
            correlated_events = tmp_path / f"{forgery_name}.jsonl"
            write_event(correlated_events, forged_payload)
            correlated_meta = {
                **forged_meta,
                "chunkhound_broker_records": correlated_records,
                "codex_events_path": str(correlated_events),
                "codex_events_end_offset": correlated_events.stat().st_size,
            }
            with pytest.raises(cure.ReviewflowError, match="ChunkHound tool proof"):
                cure._enforce_chunkhound_tool_proof(
                    meta={},
                    work_dir=tmp_path,
                    provider="codex",
                    review_stage="multipass_plan",
                    prompt_template_name="mrereview_gh_local_big_plan.md",
                    adapter_meta=correlated_meta,
                )

        honest_events = tmp_path / "honest.jsonl"
        write_event(
            honest_events,
            dict(genuine_result),
            output_prefix=(
                "cure-chunkhound: tools/call search waiting (0.0s / 60s)\n"
            ),
        )
        honest_meta = {
            **forged_meta,
            "codex_events_path": str(honest_events),
            "codex_events_end_offset": honest_events.stat().st_size,
        }
        honest_report = cure._enforce_chunkhound_tool_proof(
            meta={},
            work_dir=tmp_path,
            provider="codex",
            review_stage="multipass_plan",
            prompt_template_name="mrereview_gh_local_big_plan.md",
            adapter_meta=honest_meta,
        )
        assert honest_report is not None and honest_report["valid"] is True
    finally:
        broker.close()


@pytest.mark.skipif(
    not sys.platform.startswith("linux") or not Path("/proc/self/fd").is_dir(),
    reason="sealed executable snapshots use Linux fd execution",
)
def test_authority_executes_immutable_bytes_after_same_inode_overwrite(
    launch_fixture: LaunchFixture,
    tmp_path: Path,
) -> None:
    """B1 RED: an fd pins an inode, not the executable bytes in that inode."""
    from cure_chunkhound_broker import HelperLaunchAuthority

    repo = tmp_path / "snapshot-repo"
    repo.mkdir()
    config = repo / "chunkhound.json"
    database = repo / ".chunkhound.db"
    config.write_text("{}\n", encoding="utf-8")
    database.touch()
    executable = tmp_path / "snapshot-bin" / "chunkhound"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\nprintf 'trusted-snapshot\\n'\n", encoding="utf-8")
    executable.chmod(0o700)
    environment = {"HOME": str(tmp_path), "PATH": str(executable.parent)}
    authority = HelperLaunchAuthority(
        environment=environment,
        resolved_executable=executable,
        expected_executable_digest=hashlib.sha256(executable.read_bytes()).hexdigest(),
        expected_config_digest=hashlib.sha256(b"{}").hexdigest(),
        environment_digest=_environment_digest(environment),
        cwd=repo,
        config_path=config,
        database_path=database,
    )
    attacker_marker = tmp_path / "same-inode-attacker-ran"
    try:
        positive = subprocess.run(
            [authority.pinned_executable],
            pass_fds=(authority.executable_fd,),
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        assert positive.stdout == "trusted-snapshot\n"

        before = executable.stat()
        executable.write_text(
            f"#!/bin/sh\ntouch {attacker_marker}\nprintf 'attacker-bytes\\n'\n",
            encoding="utf-8",
        )
        executable.chmod(0o700)
        after = executable.stat()
        assert (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
        executed = subprocess.run(
            [authority.pinned_executable],
            pass_fds=(authority.executable_fd,),
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        assert executed.stdout == "trusted-snapshot\n"
        assert not attacker_marker.exists()
    finally:
        authority.close()


@pytest.mark.skipif(
    not sys.platform.startswith("linux") or not Path("/proc/self/fd").is_dir(),
    reason="fd-leak assertion uses Linux /proc",
)
def test_broker_close_causally_cancels_owned_session_and_reaps_resources(
    launch_fixture: LaunchFixture,
    tmp_path: Path,
) -> None:
    """B1 RED: close cancels owned work without publishing an expired result."""
    import cure_chunkhound
    from cure_chunkhound_broker import HelperBrokerError, request_helper_broker

    baseline_fds = len(os.listdir("/proc/self/fd"))
    repo = tmp_path / "cooperative-close-repo"
    repo.mkdir()
    config = repo / "chunkhound.json"
    database = repo / ".chunkhound.db"
    config.write_text("{}\n", encoding="utf-8")
    database.touch()
    authority = cure_chunkhound.HelperLaunchAuthority(
        environment=launch_fixture.environment,
        resolved_executable=launch_fixture.executable,
        expected_executable_digest=hashlib.sha256(
            launch_fixture.executable.read_bytes()
        ).hexdigest(),
        expected_config_digest=hashlib.sha256(b"{}").hexdigest(),
        environment_digest=launch_fixture.digest,
        cwd=repo,
        config_path=config,
        database_path=database,
    )
    broker = cure_chunkhound.ChunkHoundHelperBroker(authority=authority)
    endpoint = broker.start()
    scope = broker.begin_scope()
    worker_started = threading.Event()
    session_close_called = threading.Event()
    emergency_release = threading.Event()
    close_finished = threading.Event()
    close_errors: list[BaseException] = []
    client_errors: list[BaseException] = []
    client_results: list[dict[str, object]] = []

    class CooperativelyBlockingSession:
        def __init__(self, **kwargs: object) -> None:
            self._child_env = kwargs["env"]

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
            worker_started.set()
            assert emergency_release.wait(timeout=10), (
                "controlled session was not closed"
            )
            return {"result": {"content": [{"type": "text", "text": "{}"}]}}

        def _stderr_tail_text(self) -> str:
            return ""

        def close(self) -> None:
            session_close_called.set()
            emergency_release.set()

    def client() -> None:
        try:
            client_results.append(
                request_helper_broker(
                    endpoint,
                    {
                        "operation": "search",
                        "arguments": {"query": "cooperative-worker"},
                        "scope": scope,
                    },
                    timeout=12,
                )
            )
        except BaseException as exc:
            client_errors.append(exc)

    def close() -> None:
        try:
            broker.close()
        except BaseException as exc:
            close_errors.append(exc)
        finally:
            close_finished.set()

    client_thread = threading.Thread(target=client, name="b1-red-client")
    close_thread = threading.Thread(target=close, name="b1-red-close")
    try:
        with (
            mock.patch.object(
                cure_chunkhound, "JsonRpcSession", CooperativelyBlockingSession
            ),
            mock.patch.object(
                cure_chunkhound,
                "daemon_metadata_payload",
                return_value={},
            ),
        ):
            client_thread.start()
            assert worker_started.wait(timeout=5)
            close_thread.start()
            assert session_close_called.wait(timeout=2), (
                "broker.close did not causally close its owned active JsonRpcSession"
            )
            assert close_finished.wait(timeout=5), "broker close deadlocked"
            close_thread.join(timeout=2)
            client_thread.join(timeout=2)

        assert not close_errors
        assert client_results == []
        assert len(client_errors) == 1
        assert isinstance(client_errors[0], HelperBrokerError)
        assert broker._records == {}
        assert not close_thread.is_alive() and not client_thread.is_alive()
        assert len(os.listdir("/proc/self/fd")) <= baseline_fds
        assert not any(
            thread.is_alive() and thread.name.startswith("cure-ch-broker")
            for thread in threading.enumerate()
        )
        with pytest.raises(Exception):
            request_helper_broker(
                endpoint,
                {
                    "operation": "search",
                    "arguments": {"query": "closed"},
                    "scope": scope,
                },
                timeout=0.1,
            )
    finally:
        emergency_release.set()
        if close_thread.ident is None:
            broker.close()
        elif close_thread.is_alive():
            close_thread.join(timeout=5)
        if client_thread.ident is not None:
            client_thread.join(timeout=5)


def test_broker_cleanup_failure_is_visible_and_baseexception_safe(
    launch_fixture: LaunchFixture,
    tmp_path: Path,
) -> None:
    """B1 RED: coordinator cleanup failures cannot be swallowed."""
    import cure_chunkhound

    repo = tmp_path / "cleanup-visible-repo"
    repo.mkdir()
    config = repo / "chunkhound.json"
    database = repo / ".chunkhound.db"
    config.write_text("{}\n", encoding="utf-8")
    database.touch()

    class ExplodingSession:
        def close(self) -> None:
            raise KeyboardInterrupt("cleanup sentinel")

    authority = cure_chunkhound.HelperLaunchAuthority(
        environment=launch_fixture.environment,
        resolved_executable=launch_fixture.executable,
        expected_executable_digest=hashlib.sha256(
            launch_fixture.executable.read_bytes()
        ).hexdigest(),
        expected_config_digest=hashlib.sha256(b"{}").hexdigest(),
        environment_digest=launch_fixture.digest,
        cwd=repo,
        config_path=config,
        database_path=database,
    )
    broker = cure_chunkhound.ChunkHoundHelperBroker(
        authority=authority, session_factory=lambda **kwargs: ExplodingSession()
    )
    try:
        broker.open_session(
            {"operation": "search", "arguments": {"query": "cleanup-visible"}}
        )
        with pytest.raises(Exception, match="cleanup"):
            broker.close()
        with pytest.raises(Exception):
            _ = authority.pinned_executable
    finally:
        try:
            broker.close()
        except Exception:
            pass


def test_codex_provider_env_preserves_provider_auth_and_strips_only_native_secrets(
    tmp_path: Path,
) -> None:
    """B1 RED: native ChunkHound credentials never enter the provider process."""
    ambient = {
        "HOME": str(tmp_path),
        "PATH": "/usr/bin",
        "OPENAI_API_KEY": "codex-provider-auth",
        "CHUNKHOUND_EMBEDDING__API_KEY": "embedding-secret",
        "CHUNKHOUND_LLM_API_KEY": "llm-secret",
        "VOYAGE_API_KEY": "voyage-native-secret",
    }
    provider_extras = {
        "CODEX_HOME": str(tmp_path / "codex-home"),
        "CURE_PROVIDER_TRACE": "provider-extra",
        "CHUNKHOUND_EMBEDDING__API_KEY": "preset-embedding-secret",
        "CHUNKHOUND_LLM_API_KEY": "preset-llm-secret",
        "VOYAGE_API_KEY": "preset-voyage-secret",
    }
    import cure_llm

    repo = tmp_path / "provider-repo"
    session_dir = tmp_path / "provider-session"
    work_dir = session_dir / "work"
    repo.mkdir()
    work_dir.mkdir(parents=True)
    with (
        mock.patch.dict(os.environ, ambient, clear=True),
        mock.patch.object(shutil, "which", return_value="/usr/bin/codex"),
        mock.patch.object(
            cure_llm,
            "_stage_review_auth_support",
            side_effect=lambda *, work_dir, repo_dir, env: (dict(env), {}),
        ),
    ):
        runtime = cure_llm.prepare_review_agent_runtime(
            args=argparse.Namespace(
                agent_runtime_profile="permissive", dry_run_chunkhound=False
            ),
            resolved={
                "provider": "codex",
                "transport": "cli",
                "command": "codex",
                "env": provider_extras,
            },
            resolution_meta={},
            reviewflow_config_path=tmp_path / "reviewflow.toml",
            config_enabled=False,
            repo_dir=repo,
            session_dir=session_dir,
            work_dir=work_dir,
            base_env=ambient,
            chunkhound_config_path=None,
            chunkhound_db_path=None,
            chunkhound_cwd=None,
            enable_mcp=False,
            interactive=False,
            paths=mock.Mock(),
        )
    provider = runtime["env"]
    native = subprocess_env.build_curated_chunkhound_env(inherited_env=ambient)

    assert provider["HOME"] == ambient["HOME"]
    assert provider["PATH"] == ambient["PATH"]
    assert provider["OPENAI_API_KEY"] == ambient["OPENAI_API_KEY"]
    assert provider["CODEX_HOME"] == provider_extras["CODEX_HOME"]
    assert provider["CURE_PROVIDER_TRACE"] == provider_extras["CURE_PROVIDER_TRACE"]
    for key in (
        "CHUNKHOUND_EMBEDDING__API_KEY",
        "CHUNKHOUND_LLM_API_KEY",
        "VOYAGE_API_KEY",
    ):
        assert key not in provider  # type: ignore[operator]
        assert native[key] == ambient[key]


class _ScopeLifecycleProbe:
    def __init__(self) -> None:
        self.scope = "a" * 32
        self.live: set[str] = set()
        self.events: list[tuple[str, str]] = []

    def begin_scope(self) -> str:
        self.live.add(self.scope)
        self.events.append(("begin", self.scope))
        return self.scope

    def records_for_scope(self, scope: str) -> list[dict[str, str]]:
        assert scope in self.live, "records were collected after scope revocation"
        self.events.append(("records", scope))
        return []

    def end_scope(self, scope: str) -> None:
        assert scope in self.live
        self.live.remove(scope)
        self.events.append(("end", scope))


def _run_llm_exec_with_scope_probe(
    *,
    tmp_path: Path,
    broker: _ScopeLifecycleProbe,
    provider_effect: object,
) -> object:
    import cure_llm

    reviewflow = mock.Mock()
    reviewflow.build_codex_flags_from_llm_config.return_value = ([], {})
    if isinstance(provider_effect, BaseException):
        reviewflow.run_codex_exec.side_effect = provider_effect
    else:
        reviewflow.run_codex_exec.return_value = provider_effect
    with mock.patch.object(cure_llm, "_reviewflow", return_value=reviewflow):
        return cure_llm.run_llm_exec(
            repo_dir=tmp_path,
            resolved={"provider": "codex"},
            resolution_meta={},
            output_path=tmp_path / "review.md",
            prompt="review",
            env={"HOME": str(tmp_path), "PATH": "/usr/bin"},
            stream=False,
            progress=mock.Mock(),
            runtime_policy={"_chunkhound_helper_broker": broker},
        )


def test_run_llm_exec_revokes_broker_scope_after_success(tmp_path: Path) -> None:
    """B1 RED: production composition ends the per-provider scope after capture."""
    import cure_llm

    broker = _ScopeLifecycleProbe()
    result = _run_llm_exec_with_scope_probe(
        tmp_path=tmp_path,
        broker=broker,
        provider_effect=cure_llm.CodexRunResult(),
    )

    assert isinstance(result, cure_llm.LlmRunResult)
    assert broker.live == set()
    assert broker.events == [
        ("begin", broker.scope),
        ("records", broker.scope),
        ("end", broker.scope),
    ]


@pytest.mark.parametrize(
    "provider_failure",
    [KeyboardInterrupt("provider interrupted"), TimeoutError("provider timed out")],
    ids=["baseexception", "timeout"],
)
def test_run_llm_exec_revokes_broker_scope_after_provider_failure(
    tmp_path: Path,
    provider_failure: BaseException,
) -> None:
    """B1 RED: interruption and timeout cannot leave a reusable live scope."""
    broker = _ScopeLifecycleProbe()

    with pytest.raises(type(provider_failure), match="provider"):
        _run_llm_exec_with_scope_probe(
            tmp_path=tmp_path,
            broker=broker,
            provider_effect=provider_failure,
        )

    assert broker.live == set()
    assert broker.events == [("begin", broker.scope), ("end", broker.scope)]


def test_cleanup_propagates_non_enoent_as_sanitized_failure(
    launch_fixture: LaunchFixture,
) -> None:
    cleanup = _api("cleanup_session_launch_context")
    secret = "cleanup-directory-name-secret"
    non_unlinkable = launch_fixture.parent / secret
    non_unlinkable.mkdir(mode=0o700)

    with pytest.raises(Exception) as raised:
        cleanup(non_unlinkable)

    _assert_secret_safe(raised, secret)
    assert non_unlinkable.is_dir()
