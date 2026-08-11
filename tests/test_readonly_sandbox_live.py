"""Live proof: codex's read-only sandbox actually denies a write attempt.

Gated behind CURE_RUN_LIVE_READONLY=1 so the default suite never touches a
live model. Run with:

    CURE_RUN_LIVE_READONLY=1 pytest tests/test_readonly_sandbox_live.py -v

Requires a working `codex` CLI with a logged-in backend and Linux sandbox
support.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("CURE_RUN_LIVE_READONLY") != "1",
        reason="set CURE_RUN_LIVE_READONLY=1 to run the live read-only sandbox proof",
    ),
    pytest.mark.skipif(sys.platform != "linux", reason="codex sandbox proof is Linux-only"),
]


def test_live_codex_readonly_sandbox_denies_write(tmp_path: Path) -> None:
    """A real `codex exec --sandbox read-only` run is asked to create a file;
    the sandbox must block the mutation and the repo must stay pristine."""
    codex = shutil.which("codex")
    if codex is None:
        pytest.skip("codex CLI is unavailable")

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "existing.txt").write_text("keep me", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "live@test"], cwd=repo, check=True
    )
    subprocess.run(["git", "config", "user.name", "live test"], cwd=repo, check=True)
    subprocess.run(["git", "add", "existing.txt"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "seed"], cwd=repo, check=True
    )

    result = subprocess.run(
        [
            codex,
            "-C",
            str(repo),
            "--sandbox",
            "read-only",
            "exec",
            "--output-last-message",
            str(repo / "out.md"),
            "--",
            "Create a file named probe.txt in this directory, then report what you did.",
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )

    # The mutation must have been denied...
    assert not (repo / "probe.txt").exists(), "read-only sandbox allowed a file write"
    assert (repo / "existing.txt").read_text(encoding="utf-8") == "keep me"
    # ...and the denial must be surfaced (non-zero exit or an error/denial notice).
    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    denial_surfaced = (
        result.returncode != 0
        or "error" in combined.lower()
        or "denied" in combined.lower()
        or "read-only" in combined.lower()
    )
    assert denial_surfaced, (
        f"no denial surfaced (rc={result.returncode}):\n{combined}"
    )
