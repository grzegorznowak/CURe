from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import cure_github
from cure_errors import ReviewflowError
from run import ReviewflowSubprocessError


@dataclass
class _Result:
    stdout: str
    stderr: str = ""


def _error(*, stderr: str, cmd: list[str] | None = None) -> ReviewflowSubprocessError:
    return ReviewflowSubprocessError(
        cmd=cmd or ["gh", "api"],
        cwd=Path("/tmp"),
        exit_code=1,
        stdout="",
        stderr=stderr,
    )


@pytest.fixture(autouse=True)
def _reset_slurp_capability() -> None:
    cure_github._GH_API_SLURP_SUPPORTED = None
    yield
    cure_github._GH_API_SLURP_SUPPORTED = None


def test_gh_api_list_slurp_success_uses_exact_command(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []

    def run_cmd(cmd: list[str]) -> _Result:
        commands.append(cmd)
        return _Result('[{"id": 1}]')

    monkeypatch.setattr(cure_github, "run_cmd", run_cmd)

    assert cure_github.gh_api_list(host="github.com", path="repos/acme/repo/issues/1/comments") == [
        {"id": 1}
    ]
    assert commands == [
        [
            "gh",
            "api",
            "--hostname",
            "github.com",
            "repos/acme/repo/issues/1/comments",
            "--paginate",
            "--slurp",
        ]
    ]
    assert cure_github._GH_API_SLURP_SUPPORTED is True


def test_gh_api_list_retries_once_without_slurp_and_caches_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []
    outcomes: list[_Result | Exception] = [
        _error(stderr="unknown flag: --slurp"),
        _Result('[{"id": 1}]'),
        _Result('[{"id": 2}]'),
    ]

    def run_cmd(cmd: list[str]) -> _Result:
        commands.append(cmd)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(cure_github, "run_cmd", run_cmd)
    path = "repos/acme/repo/pulls/1/reviews"

    assert cure_github.gh_api_list(host="github.com", path=path) == [{"id": 1}]
    assert cure_github.gh_api_list(host="github.com", path=path) == [{"id": 2}]
    assert commands == [
        ["gh", "api", "--hostname", "github.com", path, "--paginate", "--slurp"],
        ["gh", "api", "--hostname", "github.com", path, "--paginate"],
        ["gh", "api", "--hostname", "github.com", path, "--paginate"],
    ]
    assert cure_github._GH_API_SLURP_SUPPORTED is False


@pytest.mark.parametrize("after_retry", [False, True])
def test_gh_api_list_routes_direct_or_post_retry_auth_failure_to_public_helper(
    monkeypatch: pytest.MonkeyPatch, after_retry: bool
) -> None:
    commands: list[list[str]] = []
    outcomes: list[Exception] = (
        [_error(stderr="unknown flag: --slurp"), _error(stderr="please run gh auth login")]
        if after_retry
        else [_error(stderr="not authenticated")]
    )
    public_calls: list[str] = []

    def run_cmd(cmd: list[str]) -> _Result:
        commands.append(cmd)
        raise outcomes.pop(0)

    def public_api(*, path: str) -> list[Any]:
        public_calls.append(path)
        return [{"source": "public"}]

    monkeypatch.setattr(cure_github, "run_cmd", run_cmd)
    monkeypatch.setattr(cure_github, "_github_public_api_list", public_api)
    path = "repos/acme/repo/pulls/1/comments"

    assert cure_github.gh_api_list(
        host="github.com", path=path, allow_public_fallback=True
    ) == [{"source": "public"}]
    assert public_calls == [path]
    assert commands == (
        [
            ["gh", "api", "--hostname", "github.com", path, "--paginate", "--slurp"],
            ["gh", "api", "--hostname", "github.com", path, "--paginate"],
        ]
        if after_retry
        else [["gh", "api", "--hostname", "github.com", path, "--paginate", "--slurp"]]
    )


@pytest.mark.parametrize(
    ("host", "allow_public_fallback", "stderr"),
    [
        ("github.com", False, "please run gh auth login"),
        ("github.example", True, "please run gh auth login"),
        ("github.com", True, "server exploded"),
    ],
)
def test_gh_api_list_does_not_public_fallback_when_route_is_ineligible(
    monkeypatch: pytest.MonkeyPatch,
    host: str,
    allow_public_fallback: bool,
    stderr: str,
) -> None:
    public_calls: list[str] = []
    error = _error(stderr=stderr)
    monkeypatch.setattr(cure_github, "run_cmd", lambda _cmd: (_ for _ in ()).throw(error))
    monkeypatch.setattr(
        cure_github,
        "_github_public_api_list",
        lambda *, path: public_calls.append(path) or [],
    )

    with pytest.raises(ReviewflowSubprocessError):
        cure_github.gh_api_list(
            host=host,
            path="repos/acme/repo/issues/1/comments",
            allow_public_fallback=allow_public_fallback,
        )

    assert public_calls == []


class _Response:
    def __init__(self, body: bytes, *, link: str = "") -> None:
        self._body = body
        self.headers = {"Link": link}

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def test_github_public_api_list_follows_link_pages_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    next_url = "https://api.github.com/repositories/1/issues/1/comments?page=2"
    responses = [
        _Response(b'[{"id": 1}]', link=f'<{next_url}>; rel="next", <ignored>; rel="last"'),
        _Response(b'[{"id": 2}, {"id": 3}]'),
    ]
    requested: list[str] = []

    def urlopen(request: Any) -> _Response:
        requested.append(request.full_url)
        return responses.pop(0)

    monkeypatch.setattr(cure_github.urllib.request, "urlopen", urlopen)

    assert cure_github._github_public_api_list(path="repos/acme/repo/issues/1/comments") == [
        {"id": 1},
        {"id": 2},
        {"id": 3},
    ]
    assert requested == [
        "https://api.github.com/repos/acme/repo/issues/1/comments",
        next_url,
    ]
    assert responses == []


@pytest.mark.parametrize("bad_body", [b"{not-json", b'{"id": 2}', b"42"])
def test_github_public_api_list_rejects_invalid_or_non_array_later_page(
    monkeypatch: pytest.MonkeyPatch, bad_body: bytes
) -> None:
    next_url = "https://api.github.com/page-2"
    responses = [
        _Response(b'[{"id": 1}]', link=f'<{next_url}>; rel="next"'),
        _Response(bad_body),
    ]
    requested: list[str] = []

    def urlopen(request: Any) -> _Response:
        requested.append(request.full_url)
        return responses.pop(0)

    monkeypatch.setattr(cure_github.urllib.request, "urlopen", urlopen)

    with pytest.raises(ReviewflowError, match="invalid JSON|unexpected list payload"):
        cure_github._github_public_api_list(path="repos/acme/repo/issues/1/comments")

    assert requested == ["https://api.github.com/repos/acme/repo/issues/1/comments", next_url]
