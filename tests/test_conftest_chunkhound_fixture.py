"""Regression tests for the session-autouse chunkhound PATH fixture.

The fixture must stay a plain function: a bare ``return`` inside a
yield-bearing (generator) fixture makes pytest abort the entire session with
"did not yield a value" on machines where the real ``chunkhound`` binary is
present on PATH -- precisely the installed/live acceptance environment the
suite is meant to validate (second external review finding B8a).
"""

from __future__ import annotations

import inspect
import os
from pathlib import Path
import shutil

from conftest import FAKE_CHUNKHOUND_ENV, _ensure_chunkhound_executable_on_path


# pytest wraps the decorated function; the underlying callable is what must
# behave like a plain function (no yield).
_FIXTURE_FN = _ensure_chunkhound_executable_on_path._fixture_function


def _request_mock() -> object:
    finalizers: list[object] = []

    class _Request:
        def addfinalizer(self, finalizer: object) -> None:
            finalizers.append(finalizer)

    return _Request()


def test_fixture_is_not_a_generator_function() -> None:
    """The fixture must never yield: a bare return must be a plain return."""
    assert not inspect.isgeneratorfunction(_FIXTURE_FN)


def test_fixture_is_noop_when_real_chunkhound_present(
    monkeypatch,
) -> None:
    fake_bin = Path("/usr/bin/chunkhound")
    monkeypatch.setattr(shutil, "which", lambda _name: str(fake_bin))
    before_path = os.environ.get("PATH", "")
    before_marker = os.environ.get(FAKE_CHUNKHOUND_ENV)

    _FIXTURE_FN(_request_mock())

    # The noop branch must not touch the environment at all.
    assert os.environ.get("PATH", "") == before_path
    assert os.environ.get(FAKE_CHUNKHOUND_ENV) == before_marker


def test_fixture_installs_fake_bin_and_restores_environment(
    monkeypatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    before_path = os.environ.get("PATH", "")
    finalizers: list[object] = []

    class _Request:
        def addfinalizer(self, finalizer: object) -> None:
            finalizers.append(finalizer)

    _FIXTURE_FN(_Request())

    fake_bin = os.environ.get(FAKE_CHUNKHOUND_ENV)
    assert fake_bin is not None
    assert Path(fake_bin).is_file()
    assert str(Path(fake_bin).parent) in os.environ.get("PATH", "")

    assert finalizers, "teardown must be registered via addfinalizer"
    finalizers[0]()  # type: ignore[operator]
    assert os.environ.get("PATH", "") == before_path
    assert os.environ.get(FAKE_CHUNKHOUND_ENV) is None
