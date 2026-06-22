from __future__ import annotations

from dataclasses import dataclass

import pytest

from cure_pr_context.fetcher import fetch_pr_discussion


@dataclass(frozen=True)
class PR:
    owner: str = "acme"
    repo: str = "rocket"
    number: int = 7


def test_fetch_pr_discussion_calls_three_list_endpoints_and_normalizes() -> None:
    seen: list[str] = []

    def gh_fetch(path: str) -> list[dict[str, object]]:
        seen.append(path)
        if path.endswith("/issues/7/comments"):
            return [{"id": 1, "user": {"login": "ana"}, "body": "issue", "created_at": "t1", "html_url": "u1"}]
        if path.endswith("/pulls/7/reviews"):
            return [{"id": 2, "user": {"login": "bob"}, "body": "review", "submitted_at": "t2", "state": "CHANGES_REQUESTED", "commit_id": "abc"}]
        return [{"id": 3, "user": {"login": "cy"}, "body": "inline", "created_at": "t3", "path": "x.py", "line": 4}]

    events = fetch_pr_discussion(pr=PR(), gh_fetch=gh_fetch)

    assert seen == [
        "repos/acme/rocket/issues/7/comments",
        "repos/acme/rocket/pulls/7/reviews",
        "repos/acme/rocket/pulls/7/comments",
    ]
    assert [event["kind"] for event in events] == ["issue_comment", "review", "review_comment"]
    assert events[1]["review_state"] == "CHANGES_REQUESTED"
    assert events[1]["reviewed_head"] == "abc"
    assert events[2]["path"] == "x.py"
    assert events[2]["line"] == 4


def test_fetch_pr_discussion_rejects_non_list_payload() -> None:
    with pytest.raises(TypeError, match="non-list"):
        fetch_pr_discussion(pr=PR(), gh_fetch=lambda path: {"items": []})  # type: ignore[return-value]
