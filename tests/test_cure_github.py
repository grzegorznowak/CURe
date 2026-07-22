from __future__ import annotations

import urllib.error
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
def _reset_slurp_capability(monkeypatch: pytest.MonkeyPatch) -> None:
    cure_github._GH_API_SLURP_SUPPORTED = None

    class DelegatingOpener:
        def open(self, request: Any, *, timeout: float | None = None) -> Any:
            return cure_github.urllib.request.urlopen(request, timeout=timeout)

    monkeypatch.setattr(
        cure_github.urllib.request,
        "build_opener",
        lambda *_handlers: DelegatingOpener(),
    )
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


def test_github_public_api_list_uses_bounded_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[tuple[str, float | None]] = []

    def urlopen(request: Any, *, timeout: float | None = None) -> _Response:
        captured.append((request.full_url, timeout))
        return _Response(b"[]")

    monkeypatch.setattr(cure_github.urllib.request, "urlopen", urlopen)

    assert cure_github._github_public_api_list(path="repos/acme/repo/issues/1/comments") == []
    assert captured == [("https://api.github.com/repos/acme/repo/issues/1/comments", 30.0)]


@pytest.mark.parametrize(
    "next_url",
    [
        "http://api.github.com/items",
        "https://user@api.github.com/items",
        "https://api.github.com/items#fragment",
        "https://api.github.com:444/items",
        "mailto:unsafe@example.com",
        "https://[invalid/items",
    ],
)
def test_github_public_api_list_rejects_every_unsafe_next_before_request(
    monkeypatch: pytest.MonkeyPatch, next_url: str
) -> None:
    requested: list[str] = []

    def urlopen(request: Any, *, timeout: float | None = None) -> _Response:
        requested.append(request.full_url)
        return _Response(b"[]", link=f'<{next_url}>; rel="next"')

    monkeypatch.setattr(cure_github.urllib.request, "urlopen", urlopen)
    with pytest.raises(ReviewflowError, match="unsafe|origin|malformed"):
        cure_github._github_public_api_list(path="repos/acme/repo/issues/1/comments")
    assert requested == ["https://api.github.com/repos/acme/repo/issues/1/comments"]


@pytest.mark.parametrize(
    "failure",
    [
        TimeoutError("timed out"),
        urllib.error.URLError("network down"),
        OSError("transport failed"),
    ],
)
def test_github_public_api_list_translates_transport_failures(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    calls: list[float | None] = []

    def urlopen(_request: Any, *, timeout: float | None = None) -> _Response:
        calls.append(timeout)
        raise failure

    monkeypatch.setattr(cure_github.urllib.request, "urlopen", urlopen)
    with pytest.raises(ReviewflowError, match="Public GitHub API request failed") as raised:
        cure_github._github_public_api_list(path="repos/acme/repo/issues/1/comments")
    assert raised.value.__cause__ is failure
    assert calls == [30.0]


def test_github_public_api_list_resolves_relative_next_against_current_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [
        _Response(b'[{"page":1}]', link='<?page=2>; rel="next"'),
        _Response(b'[{"page":2}]'),
    ]
    requested: list[str] = []

    def urlopen(request: Any, *, timeout: float | None = None) -> _Response:
        requested.append(request.full_url)
        return responses.pop(0)

    monkeypatch.setattr(cure_github.urllib.request, "urlopen", urlopen)
    assert cure_github._github_public_api_list(path="items?page=1") == [
        {"page": 1}, {"page": 2}
    ]
    assert requested == [
        "https://api.github.com/items?page=1",
        "https://api.github.com/items?page=2",
    ]


def test_github_public_api_list_rejects_cross_origin_next_before_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[str] = []

    def urlopen(request: Any, *, timeout: float | None = None) -> _Response:
        requested.append(request.full_url)
        return _Response(b"[]", link='<https://evil.example/items?page=2>; rel="next"')

    monkeypatch.setattr(cure_github.urllib.request, "urlopen", urlopen)

    with pytest.raises(ReviewflowError, match="unsafe|origin"):
        cure_github._github_public_api_list(path="repos/acme/repo/issues/1/comments")
    assert requested == ["https://api.github.com/repos/acme/repo/issues/1/comments"]


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_public_list_redirect_handler_rejects_before_followup(status: int) -> None:
    request = cure_github.urllib.request.Request("https://api.github.com/items")
    with pytest.raises(ReviewflowError, match="redirect rejected"):
        cure_github._RejectRedirects().redirect_request(
            request, None, status, "redirect", {}, "https://api.github.com/other"
        )


def test_github_public_api_list_rejects_equivalent_cycle_before_second_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[str] = []

    def urlopen(request: Any, *, timeout: float | None = None) -> _Response:
        requested.append(request.full_url)
        return _Response(
            b"[]",
            link='<https://API.GITHUB.COM:443/repos/acme/./repo/issues/1/comments>; rel="next"',
        )

    monkeypatch.setattr(cure_github.urllib.request, "urlopen", urlopen)
    with pytest.raises(ReviewflowError, match="cycle"):
        cure_github._github_public_api_list(path="repos/acme/repo/issues/1/comments")
    assert requested == ["https://api.github.com/repos/acme/repo/issues/1/comments"]


def test_github_public_api_list_terminal_page_100_succeeds_and_next_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def urlopen(request: Any, *, timeout: float | None = None) -> _Response:
        nonlocal calls
        calls += 1
        link = (
            f'<https://api.github.com/items?page={calls + 1}>; rel="next"'
            if calls < 100
            else ""
        )
        return _Response(f"[{{\"page\":{calls}}}]".encode(), link=link)

    monkeypatch.setattr(cure_github.urllib.request, "urlopen", urlopen)
    result = cure_github._github_public_api_list(path="items?page=1")
    assert calls == 100
    assert [result[0], result[-1]] == [{"page": 1}, {"page": 100}]

    calls = 0

    def overflowing(request: Any, *, timeout: float | None = None) -> _Response:
        nonlocal calls
        calls += 1
        return _Response(
            b"[]",
            link=f'<https://api.github.com/items?page={calls + 1}>; rel="next"',
        )

    monkeypatch.setattr(cure_github.urllib.request, "urlopen", overflowing)
    with pytest.raises(ReviewflowError, match="100 pages"):
        cure_github._github_public_api_list(path="items?page=1")
    assert calls == 100


def test_github_public_api_list_follows_link_pages_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    next_url = "https://api.github.com/repositories/1/issues/1/comments?page=2"
    responses = [
        _Response(b'[{"id": 1}]', link=f'<{next_url}>; rel="next", <ignored>; rel="last"'),
        _Response(b'[{"id": 2}, {"id": 3}]'),
    ]
    requested: list[str] = []

    def urlopen(request: Any, *, timeout: float | None = None) -> _Response:
        requested.append(request.full_url)
        assert timeout == 30.0
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

    def urlopen(request: Any, *, timeout: float | None = None) -> _Response:
        requested.append(request.full_url)
        assert timeout == 30.0
        return responses.pop(0)

    monkeypatch.setattr(cure_github.urllib.request, "urlopen", urlopen)

    with pytest.raises(ReviewflowError, match="invalid JSON|unexpected list payload"):
        cure_github._github_public_api_list(path="repos/acme/repo/issues/1/comments")

    assert requested == ["https://api.github.com/repos/acme/repo/issues/1/comments", next_url]
