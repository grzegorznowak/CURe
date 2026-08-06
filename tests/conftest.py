"""Suite-level pytest fixtures.

Unit tests throughout the suite resolve the ChunkHound daemon launch identity,
which requires an executable named ``chunkhound`` on the environment PATH.
Developer machines have the real installed binary; CI runners do not, which
previously made those tests fail with LaunchIdentityConstructionError instead
of running. This fixture provides a minimal executable placeholder on PATH for
the whole session when no real ``chunkhound`` is present, and records the
substitution via ``CURE_CHUNKHOUND_FAKE_BIN`` so live daemon tests can skip
instead of attempting to run against the placeholder.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

FAKE_CHUNKHOUND_ENV = "CURE_CHUNKHOUND_FAKE_BIN"


@pytest.fixture(scope="session", autouse=True)
def _ensure_chunkhound_executable_on_path(
    request: pytest.FixtureRequest,
) -> None:
    if shutil.which("chunkhound") is not None:
        # Real installed binary present (developer machine): nothing to do.
        return
    bin_dir = Path(tempfile.mkdtemp(prefix="cure-fake-bin-"))
    binary = bin_dir / "chunkhound"
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)
    original_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{original_path}"
    os.environ[FAKE_CHUNKHOUND_ENV] = str(binary)

    def _restore_environment() -> None:
        os.environ["PATH"] = original_path
        os.environ.pop(FAKE_CHUNKHOUND_ENV, None)

    # NOT a generator fixture: a bare ``return`` in a yield-bearing fixture
    # makes pytest abort the whole session with "did not yield a value" on
    # machines where the real chunkhound binary is present -- exactly the
    # environment the installed/live acceptance proof must run in.
    request.addfinalizer(_restore_environment)
