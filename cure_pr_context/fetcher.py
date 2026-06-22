"""Fetch and normalize GitHub PR discussion for CURe reviews."""

from __future__ import annotations

from typing import Any, Callable

GhFetch = Callable[..., list[Any]]

_DISCUSSION_KEYS = ("kind", "author", "body", "created_at", "url", "path", "line", "review_state")


def _user_login(payload: dict[str, Any]) -> str:
    raw_user = payload.get("user")
    user: dict[str, Any] = raw_user if isinstance(raw_user, dict) else {}
    return str(user.get("login") or "").strip()


def _event_id(payload: dict[str, Any]) -> str:
    return str(payload.get("id") or payload.get("node_id") or "").strip()


def _reviewed_head(payload: dict[str, Any]) -> str:
    for key in ("commit_id", "commitId", "head_sha", "headSha", "sha"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    raw_commit = payload.get("commit")
    commit: dict[str, Any] = raw_commit if isinstance(raw_commit, dict) else {}
    return str(commit.get("sha") or "").strip()


def _line(payload: dict[str, Any]) -> int | None:
    raw = payload.get("line") if payload.get("line") is not None else payload.get("original_line")
    if raw is None:
        return None
    try:
        return int(raw)
    except Exception:
        return None


def _normalize_item(kind: str, item: dict[str, Any]) -> dict[str, Any]:
    event: dict[str, Any] = {
        "kind": kind,
        "event_id": _event_id(item),
        "author": _user_login(item),
        "body": str(item.get("body") or ""),
        "created_at": str(item.get("submitted_at") or item.get("created_at") or ""),
        "url": str(item.get("html_url") or item.get("url") or ""),
        "path": "",
        "line": None,
        "review_state": "",
    }
    if kind == "review":
        event["review_state"] = str(item.get("state") or "")
        event["reviewed_head"] = _reviewed_head(item)
    elif kind == "review_comment":
        event["path"] = str(item.get("path") or "")
        event["line"] = _line(item)
        event["created_at"] = str(item.get("created_at") or "")
    return event


def _items_from_payload(payload: Any, *, path: str) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise TypeError(f"gh_fetch returned non-list payload for {path}")
    items: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise TypeError(f"gh_fetch returned non-object item for {path}")
        items.append(item)
    return items


def fetch_pr_discussion(*, pr: Any, gh_fetch: GhFetch) -> list[dict[str, Any]]:
    """Fetch issue comments, PR reviews, and inline review comments.

    ``gh_fetch`` must be a list-capable callable such as ``cure.gh_api_list``.
    It is called with the endpoint path as a positional argument so tests can
    use a compact ``lambda path: ...``; callers may bind host-specific keyword
    arguments around CURe's production helper.
    """

    endpoints = (
        ("issue_comment", f"repos/{pr.owner}/{pr.repo}/issues/{pr.number}/comments"),
        ("review", f"repos/{pr.owner}/{pr.repo}/pulls/{pr.number}/reviews"),
        ("review_comment", f"repos/{pr.owner}/{pr.repo}/pulls/{pr.number}/comments"),
    )
    events: list[dict[str, Any]] = []
    for kind, path in endpoints:
        payload = gh_fetch(path)
        for item in _items_from_payload(payload, path=path):
            event = _normalize_item(kind, item)
            for key in _DISCUSSION_KEYS:
                event.setdefault(key, None if key == "line" else "")
            events.append(event)
    return events
