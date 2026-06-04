"""GitHub PR discussion collection for subsequent-review intake."""

from __future__ import annotations

from typing import Any, Callable

from cure_subsequent_review.contracts import (
    DiscussionArtifact,
    DiscussionEvent,
    ModuleStatus,
    PaginationMarker,
)

JsonFetcher = Callable[[str], Any]


def _user_login(payload: dict[str, Any]) -> str | None:
    raw_user = payload.get("user")
    user: dict[str, Any] = raw_user if isinstance(raw_user, dict) else {}
    login = str(user.get("login") or "").strip()
    return login or None


def _normalize_source_payload(source: str, payload: Any) -> tuple[list[dict[str, Any]], PaginationMarker, tuple[str, ...]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)], PaginationMarker(source, True), ()
    if isinstance(payload, dict):
        raw_items = payload.get("items") if isinstance(payload.get("items"), list) else payload.get("data")
        items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []
        complete = bool(payload.get("complete", True))
        status = str(payload.get("status") or ("complete" if complete else "discussion_incomplete"))
        reasons: tuple[str, ...] = () if complete and status == "complete" else (status,)
        detail = str(payload.get("detail") or "") or None
        return items, PaginationMarker(source, complete, status=status, detail=detail), reasons
    return [], PaginationMarker(source, False, status="discussion_unavailable"), ("discussion_unavailable",)


def _thread_state(payload: dict[str, Any]) -> tuple[str, str | None]:
    raw = payload.get("thread_state") or payload.get("threadState")
    if raw is None and isinstance(payload.get("thread"), dict):
        raw = payload["thread"].get("state")
    if raw is None and "resolved" in payload:
        return ("resolved" if bool(payload.get("resolved")) else "unresolved"), None
    normalized = str(raw or "").strip().lower()
    if normalized in {"resolved", "unresolved", "unknown"}:
        return normalized, None
    return "unknown", "thread_state_unavailable"


def collect_pr_discussion(*, pr: Any, fetch_json: JsonFetcher) -> DiscussionArtifact:
    """Fetch and normalize PR discussion.

    Missing API data is recorded as degraded rather than being normalized to an
    empty successful discussion.  Thread state remains metadata only.
    """

    endpoints = (
        ("issue_comments", f"repos/{pr.owner}/{pr.repo}/issues/{pr.number}/comments"),
        ("reviews", f"repos/{pr.owner}/{pr.repo}/pulls/{pr.number}/reviews"),
        ("review_comments", f"repos/{pr.owner}/{pr.repo}/pulls/{pr.number}/comments"),
    )
    events: list[DiscussionEvent] = []
    pagination: list[PaginationMarker] = []
    reasons: list[str] = []

    for source, path in endpoints:
        try:
            payload = fetch_json(path)
        except Exception as exc:  # noqa: BLE001 - external service failure is a degraded status
            pagination.append(PaginationMarker(source, False, status="discussion_unavailable", detail=str(exc)))
            if "discussion_unavailable" not in reasons:
                reasons.append("discussion_unavailable")
            continue
        items, marker, marker_reasons = _normalize_source_payload(source, payload)
        pagination.append(marker)
        for reason in marker_reasons:
            if reason not in reasons:
                reasons.append(reason)
        for item in items:
            if source == "issue_comments":
                events.append(
                    DiscussionEvent(
                        kind="issue_comment",
                        event_id=str(item.get("id") or item.get("node_id") or ""),
                        author=_user_login(item),
                        body=str(item.get("body") or ""),
                        url=str(item.get("html_url") or item.get("url") or "") or None,
                        created_at=str(item.get("created_at") or "") or None,
                    )
                )
            elif source == "reviews":
                events.append(
                    DiscussionEvent(
                        kind="review",
                        event_id=str(item.get("id") or item.get("node_id") or ""),
                        author=_user_login(item),
                        body=str(item.get("body") or ""),
                        url=str(item.get("html_url") or item.get("url") or "") or None,
                        created_at=str(item.get("submitted_at") or item.get("created_at") or "") or None,
                        review_state=str(item.get("state") or "") or None,
                    )
                )
            else:
                state, state_reason = _thread_state(item)
                if state_reason and state_reason not in reasons:
                    reasons.append(state_reason)
                line_value = item.get("line") or item.get("original_line")
                try:
                    line = int(line_value) if line_value is not None else None
                except Exception:
                    line = None
                events.append(
                    DiscussionEvent(
                        kind="review_comment",
                        event_id=str(item.get("id") or item.get("node_id") or ""),
                        author=_user_login(item),
                        body=str(item.get("body") or ""),
                        url=str(item.get("html_url") or item.get("url") or "") or None,
                        created_at=str(item.get("created_at") or "") or None,
                        path=str(item.get("path") or "") or None,
                        line=line,
                        thread_state=state,
                    )
                )

    status = ModuleStatus.DEGRADED if reasons else ModuleStatus.SUCCESS
    return DiscussionArtifact(status=status, events=tuple(events), pagination=tuple(pagination), status_reasons=tuple(reasons))
