#!/usr/bin/env python3
"""Create one preserved, non-reusable TAP-05 live-proof bundle."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from typing import IO, Any
from xml.etree import ElementTree


REPO_ROOT = Path(__file__).resolve().parents[1]
TAP05_NODE_IDS = (
    "tests/test_daemon_aware_chunkhound_live.py::test_installed_chunkhound_retains_owned_generation_without_llm[nonempty-absent]",
    "tests/test_daemon_aware_chunkhound_live.py::test_installed_chunkhound_retains_owned_generation_without_llm[nonempty-existing]",
    "tests/test_daemon_aware_chunkhound_live.py::test_installed_chunkhound_retains_owned_generation_without_llm[zero-absent]",
    "tests/test_daemon_aware_chunkhound_live.py::test_installed_chunkhound_retains_owned_generation_without_llm[zero-existing]",
    "tests/test_daemon_aware_chunkhound_live.py::test_tap05_watchman_fresh_instance_degraded_then_ready_live",
)
LIVE_CASE_ROOT_NAMES = (
    "ordinary-nonempty-absent",
    "ordinary-nonempty-existing",
    "ordinary-zero-absent",
    "ordinary-zero-existing",
    "watchman-fresh-instance",
)
PROOF_VALIDATION_EXIT = 86
SubprocessRunner = Callable[..., Any]


def _write_private(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _write_private_text(path: Path, text: str) -> None:
    _write_private(path, text.encode("utf-8"))


def _write_private_json(path: Path, payload: object) -> None:
    _write_private_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout


def _worktree_manifest() -> dict[str, dict[str, object]]:
    """Digest every tracked or nonignored untracked worktree path."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(REPO_ROOT),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    manifest: dict[str, dict[str, object]] = {}
    for raw_relative in sorted(filter(None, result.stdout.split(b"\0"))):
        relative = raw_relative.decode("utf-8", errors="surrogateescape")
        path = REPO_ROOT / relative
        if not path.exists() and not path.is_symlink():
            manifest[relative] = {"kind": "missing", "mode": None, "sha256": None}
            continue
        metadata = path.lstat()
        if path.is_symlink():
            kind = "symlink"
            payload = os.readlink(path).encode("utf-8", errors="surrogateescape")
        elif path.is_file():
            kind = "file"
            payload = path.read_bytes()
        else:
            # git paths should be blobs or links; retain an audible fail-closed row.
            kind = "other"
            payload = b""
        manifest[relative] = {
            "kind": kind,
            "mode": metadata.st_mode & 0o7777,
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    return manifest


def _path_manifest(root: Path) -> dict[str, dict[str, object]]:
    if not root.exists():
        return {}
    manifest: dict[str, dict[str, object]] = {}
    for path in sorted(
        root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()
    ):
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        row: dict[str, object] = {"mode": metadata.st_mode & 0o7777}
        if path.is_symlink():
            target = os.readlink(path)
            row.update(
                kind="symlink",
                sha256=hashlib.sha256(
                    target.encode("utf-8", errors="surrogateescape")
                ).hexdigest(),
            )
        elif path.is_dir():
            row.update(kind="directory", sha256=None)
        elif path.is_file():
            row.update(
                kind="file", sha256=hashlib.sha256(path.read_bytes()).hexdigest()
            )
        else:
            row.update(kind="other", sha256=None)
        manifest[relative] = row
    return manifest


def _capture_repository_state(proof_root: Path, phase: str) -> None:
    _write_private_text(proof_root / f"head-{phase}.txt", _git("rev-parse", "HEAD"))
    _write_private_text(
        proof_root / f"status-{phase}.porcelain",
        _git("status", "--porcelain=v1", "--untracked-files=all"),
    )
    _write_private_text(
        proof_root / f"diff-{phase}.patch",
        _git("diff", "--binary", "--no-ext-diff", "HEAD", "--"),
    )
    _write_private_json(
        proof_root / f"worktree-manifest-{phase}.json", _worktree_manifest()
    )


def _command_identity(command: str) -> dict[str, object]:
    located = shutil.which(command)
    row: dict[str, object] = {
        "requested_command": command,
        "resolved_path": None,
        "sha256": None,
        "version_output": None,
        "version_exit_code": None,
    }
    if located is None:
        return row
    resolved = Path(located).resolve()
    row["resolved_path"] = str(resolved)
    if resolved.is_file():
        row["sha256"] = hashlib.sha256(resolved.read_bytes()).hexdigest()
        try:
            first_line = (
                resolved.read_bytes().splitlines()[0].decode("utf-8", errors="replace")
            )
        except IndexError:
            first_line = ""
        row["launcher_first_line"] = first_line
    try:
        result = subprocess.run(
            [str(resolved), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        row["version_output"] = f"{type(exc).__name__}: {exc}"
    else:
        row["version_exit_code"] = result.returncode
        row["version_output"] = (result.stdout + result.stderr).strip()
    return row


def _installed_runtime_identity() -> dict[str, dict[str, object]]:
    return {
        "chunkhound": _command_identity("chunkhound"),
        "watchman": _command_identity("watchman"),
    }


def _open_private_text(path: Path) -> IO[str]:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    return os.fdopen(descriptor, "w", encoding="utf-8")


def _junit_node_id(case: ElementTree.Element) -> str:
    classname = case.attrib.get("classname", "")
    name = case.attrib.get("name", "")
    return f"{classname.replace('.', '/')}.py::{name}"


def _validate_proof(
    *,
    pytest_exit_code: int,
    junit_path: Path,
    stdout_path: Path,
    live_artifact_root: Path,
) -> tuple[int, dict[str, object]]:
    base: dict[str, object] = {
        "accepted": False,
        "expected_node_ids": list(TAP05_NODE_IDS),
        "passed_node_ids": [],
        "skipped_node_ids": [],
        "unexpected_node_ids": [],
    }
    if pytest_exit_code != 0:
        base["reason"] = f"pytest exited {pytest_exit_code}; proof not validated"
        return pytest_exit_code, base
    if not junit_path.is_file() or junit_path.is_symlink():
        base["reason"] = "pytest JUnit report is absent or not a regular file"
        return PROOF_VALIDATION_EXIT, base
    try:
        root = ElementTree.parse(junit_path).getroot()
    except (ElementTree.ParseError, OSError) as exc:
        base["reason"] = f"pytest JUnit report is invalid: {type(exc).__name__}: {exc}"
        return PROOF_VALIDATION_EXIT, base

    passed: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    for case in root.iter("testcase"):
        node_id = _junit_node_id(case)
        if case.find("skipped") is not None:
            skipped.append(node_id)
        elif case.find("failure") is not None or case.find("error") is not None:
            failed.append(node_id)
        else:
            passed.append(node_id)
    unexpected = sorted(
        (set(passed) | set(skipped) | set(failed)) - set(TAP05_NODE_IDS)
    )
    base.update(
        passed_node_ids=passed,
        skipped_node_ids=skipped,
        unexpected_node_ids=unexpected,
    )
    stdout = stdout_path.read_text(encoding="utf-8")
    stdout_passes = [
        node_id for node_id in TAP05_NODE_IDS if f"{node_id} PASSED" in stdout
    ]
    missing_case_roots = [
        name
        for name in LIVE_CASE_ROOT_NAMES
        if not (live_artifact_root / name).is_dir()
    ]
    if (
        len(passed) != 5
        or set(passed) != set(TAP05_NODE_IDS)
        or skipped
        or failed
        or unexpected
        or len(stdout_passes) != 5
        or missing_case_roots
    ):
        base["reason"] = (
            "expected exactly five passed TAP-05 nodes, zero skipped/failed/unexpected, "
            "five -vv PASSED node IDs, and five preserved case roots; "
            f"failed={failed!r}, missing_case_roots={missing_case_roots!r}"
        )
        return PROOF_VALIDATION_EXIT, base
    base["accepted"] = True
    base["reason"] = "exactly five expected TAP-05 nodes passed"
    return 0, base


def run_proof(
    proof_root: Path,
    *,
    subprocess_runner: SubprocessRunner = subprocess.run,
) -> int:
    """Run TAP-05 once in a caller-selected root that must not already exist."""
    proof_root = proof_root.expanduser().resolve(strict=False)
    if proof_root == REPO_ROOT or REPO_ROOT in proof_root.parents:
        raise ValueError("proof root must be outside the source checkout")
    proof_root.mkdir(mode=0o700, parents=False, exist_ok=False)
    proof_root.chmod(0o700)

    live_artifact_root = proof_root / "live-artifacts"
    live_artifact_root.mkdir(mode=0o700, exist_ok=False)
    junit_path = proof_root / "pytest-junit.xml"
    command = [
        "python",
        "-m",
        "pytest",
        "-vv",
        "--junitxml",
        str(junit_path),
        *TAP05_NODE_IDS,
    ]
    environment_overrides = {
        "CURE_RUN_LIVE_CHUNKHOUND": "1",
        "CURE_RUN_LIVE_CHUNKHOUND_WATCHMAN": "1",
        "CURE_TAP05_ARTIFACT_ROOT": str(live_artifact_root),
        "CURE_TAP05_PROOF_ROOT": str(proof_root),
        "PYTHONPATH": str(REPO_ROOT),
    }
    environment = os.environ.copy()
    environment.update(environment_overrides)
    rendered = " ".join(
        [
            "CURE_RUN_LIVE_CHUNKHOUND=1",
            "CURE_RUN_LIVE_CHUNKHOUND_WATCHMAN=1",
            f"CURE_TAP05_ARTIFACT_ROOT={shlex.quote(str(live_artifact_root))}",
            'PYTHONPATH="$PWD"',
            *(shlex.quote(part) for part in command),
        ]
    )
    _write_private_json(
        proof_root / "invocation.json",
        {
            "command": command,
            "cwd": str(REPO_ROOT),
            "environment": environment_overrides,
            "rendered_command": rendered,
        },
    )
    _write_private_json(
        proof_root / "installed-runtime-identity.json", _installed_runtime_identity()
    )
    _capture_repository_state(proof_root, "before")

    pytest_exit_code = 125
    proof_exit_code = 125
    validation: dict[str, object] = {
        "accepted": False,
        "reason": "pytest did not return",
        "expected_node_ids": list(TAP05_NODE_IDS),
        "passed_node_ids": [],
        "skipped_node_ids": [],
        "unexpected_node_ids": [],
    }
    stdout_path = proof_root / "stdout.txt"
    with (
        _open_private_text(stdout_path) as stdout,
        _open_private_text(proof_root / "stderr.txt") as stderr,
    ):
        try:
            result = subprocess_runner(
                command,
                cwd=REPO_ROOT,
                env=environment,
                stdout=stdout,
                stderr=stderr,
                check=False,
            )
            pytest_exit_code = int(result.returncode)
        except BaseException as exc:
            stderr.write(
                f"proof runner failed before pytest exit: {type(exc).__name__}: {exc}\n"
            )
            raise
        finally:
            stdout.flush()
            os.fsync(stdout.fileno())
            stderr.flush()
            os.fsync(stderr.fileno())
            _write_private_text(
                proof_root / "pytest-exit-code.txt", f"{pytest_exit_code}\n"
            )
            if junit_path.is_file() and not junit_path.is_symlink():
                junit_path.chmod(0o600)
            proof_exit_code, validation = _validate_proof(
                pytest_exit_code=pytest_exit_code,
                junit_path=junit_path,
                stdout_path=stdout_path,
                live_artifact_root=live_artifact_root,
            )
            _write_private_text(
                proof_root / "proof-exit-code.txt", f"{proof_exit_code}\n"
            )
            _write_private_json(proof_root / "proof-validation.json", validation)
            _capture_repository_state(proof_root, "after")
            _write_private_json(
                proof_root / "live-artifacts-manifest.json",
                _path_manifest(live_artifact_root),
            )
            _write_private_json(
                proof_root / "bundle-complete.json",
                {
                    "live_artifact_root": str(live_artifact_root),
                    "proof_exit_code": proof_exit_code,
                    "proof_validation_accepted": validation["accepted"],
                    "pytest_exit_code": pytest_exit_code,
                },
            )
    return proof_exit_code


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "proof_root",
        type=Path,
        help="new unique proof root; existing paths are rejected and never altered",
    )
    arguments = parser.parse_args(argv)
    return run_proof(arguments.proof_root)


if __name__ == "__main__":
    sys.exit(main())
