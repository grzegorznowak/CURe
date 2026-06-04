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


def _classify_fetch_error(exc: BaseException) -> str:
    stderr = str(getattr(exc, "stderr", "") or "")
    stdout = str(getattr(exc, "stdout", "") or "")
    text = f"{stderr}\n{stdout}".lower()
    if not text.strip() and not hasattr(exc, "cmd"):
        text = str(exc).lower()
    if "unknown flag" in text or "unknown option" in text or "invalid option" in text:
        return "cli_unsupported_flag"
    if "auth" in text or "login" in text or "token" in text:
        return "auth"
    if "api rate limit" in text or "rate limit" in text:
        return "api_rate_limit"
    if "http" in text or "status" in text:
        return "api_status"
    if "timed out" in text or "connection" in text or "network" in text:
        return "transport"
    return "fetch_error"


def _marker_from_exception(*, source: str, path: str, exc: BaseException) -> PaginationMarker:
    cmd = getattr(exc, "cmd", ()) or ()
    return PaginationMarker(
        source,
        False,
        status="discussion_unavailable",
        detail=str(exc),
        endpoint=path,
        fetch="gh_api_list",
        cause=_classify_fetch_error(exc),
        exit_code=getattr(exc, "exit_code", None),
        stderr=str(getattr(exc, "stderr", "") or "") or None,
        stdout=str(getattr(exc, "stdout", "") or "") or None,
        command=tuple(str(part) for part in cmd),
    )


def _user_login(payload: dict[str, Any]) -> str | None:
    raw_user = payload.get("user")
    user: dict[str, Any] = raw_user if isinstance(raw_user, dict) else {}
    login = str(user.get("login") or "").strip()
    return login or None


def _normalize_source_payload(source: str, path: str, payload: Any) -> tuple[list[dict[str, Any]], PaginationMarker, tuple[str, ...]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)], PaginationMarker(source, True, endpoint=path), ()
    if isinstance(payload, dict):
        raw_items = payload.get("items") if isinstance(payload.get("items"), list) else payload.get("data")
        items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []
        complete = bool(payload.get("complete", True))
        status = str(payload.get("status") or ("complete" if complete else "discussion_incomplete"))
        reasons: tuple[str, ...] = () if complete and status == "complete" else (status,)
        detail = str(payload.get("detail") or "") or None
        command = payload.get("command", ())
        command_parts = tuple(str(part) for part in command) if isinstance(command, list | tuple) else ()
        exit_code_raw = payload.get("exit_code")
        exit_code = exit_code_raw if isinstance(exit_code_raw, int) else None
        marker = PaginationMarker(
            source,
            complete,
            status=status,
            detail=detail,
            endpoint=str(payload.get("endpoint") or path),
            fetch=str(payload.get("fetch") or "gh_api_list"),
            cause=str(payload.get("cause") or "") or None,
            exit_code=exit_code,
            stderr=str(payload.get("stderr") or "") or None,
            stdout=str(payload.get("stdout") or "") or None,
            command=command_parts,
        )
        return items, marker, reasons
    return [], PaginationMarker(source, False, status="discussion_unavailable", endpoint=path), ("discussion_unavailable",)


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
            pagination.append(_marker_from_exception(source=source, path=path, exc=exc))
            if "discussion_unavailable" not in reasons:
                reasons.append("discussion_unavailable")
            continue
        items, marker, marker_reasons = _normalize_source_payload(source, path, payload)
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
