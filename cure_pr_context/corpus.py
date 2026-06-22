"""Prior CURe review corpus and discussion deduplication."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from cure_sessions import scan_completed_sessions_for_pr

CURE_REVIEW_FOOTER_START = "<!-- CURE_REVIEW_FOOTER_START -->"
CURE_REVIEW_FOOTER_END = "<!-- CURE_REVIEW_FOOTER_END -->"
_FOOTER_SHA_RE = re.compile(r"(?:^|[·\s])sha\s+(?P<sha>[0-9a-fA-F]{3,40}|-)(?=$|[·_\s])")
_FOOTER_SESSION_RE = re.compile(r"(?:^|[·\s])session\s+(?P<session>[^·_\n\r]+)")
_SESSION_PR_RE = re.compile(r"(?:^|[-_/])pr(?P<number>\d+)(?:[-_/]|$)", re.IGNORECASE)


def _normalize_sha(value: object) -> str:
    text = str(value or "").strip().lower()
    return "" if not text or text == "-" else text


def _head_matches(*, candidate: object, head_sha: object) -> bool:
    candidate_sha = _normalize_sha(candidate)
    current_sha = _normalize_sha(head_sha)
    if not candidate_sha or not current_sha:
        return True
    return candidate_sha.startswith(current_sha) or current_sha.startswith(candidate_sha)


def extract_official_cure_review_footer(body: str) -> str | None:
    start = body.find(CURE_REVIEW_FOOTER_START)
    end = body.find(CURE_REVIEW_FOOTER_END)
    if start < 0 or end <= start:
        return None
    return body[start + len(CURE_REVIEW_FOOTER_START) : end].strip()


def _footer_pr_number(session_id: str | None) -> int | None:
    match = _SESSION_PR_RE.search(str(session_id or "").strip())
    if match is None:
        return None
    try:
        return int(match.group("number"))
    except ValueError:
        return None


def parse_footer_metadata(body: str) -> dict[str, Any]:
    footer = extract_official_cure_review_footer(body)
    if footer is None:
        return {}
    sha_match = _FOOTER_SHA_RE.search(footer)
    if sha_match is None:
        return {}
    session_match = _FOOTER_SESSION_RE.search(footer)
    session_id = str(session_match.group("session")).strip() if session_match else ""
    reviewed_head = _normalize_sha(sha_match.group("sha"))
    if not reviewed_head:
        return {}
    return {
        "footer_text": footer,
        "session_id": session_id,
        "pr_number": _footer_pr_number(session_id),
        "reviewed_head": reviewed_head,
    }


def _event_text(event: dict[str, Any]) -> str:
    return str(event.get("body") or "")


def _ngrams(text: str, *, n: int = 5) -> set[str]:
    normalized = " ".join(text.lower().split())
    if not normalized:
        return set()
    if len(normalized) <= n:
        return {normalized}
    return {normalized[idx : idx + n] for idx in range(0, len(normalized) - n + 1)}


def _jaccard(left: str, right: str) -> float:
    left_set = _ngrams(left)
    right_set = _ngrams(right)
    if not left_set and not right_set:
        return 1.0
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def _assert_local_session_meta_readable(*, sandbox_root: Path) -> None:
    if not sandbox_root.is_dir():
        return
    for entry in sandbox_root.iterdir():
        if not entry.is_dir():
            continue
        meta_path = entry / "meta.json"
        if not meta_path.exists():
            continue
        try:
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"failed to parse meta.json at {meta_path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"meta.json must contain a JSON object: {meta_path}")


def _local_session_reviews(*, sandbox_root: Path, pr: Any, head_sha: str) -> list[dict[str, Any]]:
    _assert_local_session_meta_readable(sandbox_root=sandbox_root)
    entries: list[dict[str, Any]] = []
    for session in scan_completed_sessions_for_pr(sandbox_root=sandbox_root, pr=pr):
        path = getattr(session, "review_md_path", None)
        if path is None:
            continue
        reviewed_head = _normalize_sha(getattr(session, "review_head_sha", ""))
        if reviewed_head and not _head_matches(candidate=reviewed_head, head_sha=head_sha):
            continue
        body = Path(path).read_text(encoding="utf-8")
        session_id = str(getattr(session, "session_id", "") or Path(path).parent.name)
        entries.append(
            {
                "source_type": "session_review",
                "entry_id": f"session:{session_id}",
                "body": body,
                "reviewed_head": reviewed_head,
                "provenance": {
                    "session_id": session_id,
                    "session_dir": str(getattr(session, "session_dir", "")),
                    "review_md_path": str(path),
                    "created_at": getattr(session, "created_at", None),
                    "completed_at": getattr(session, "completed_at", None),
                },
            }
        )
    return entries


def _remote_review_from_event(*, pr: Any, event: dict[str, Any], head_sha: str) -> dict[str, Any] | None:
    if event.get("kind") not in {"issue_comment", "review"}:
        return None
    body = _event_text(event)
    footer_meta = parse_footer_metadata(body)
    if not footer_meta:
        return None
    footer_pr = footer_meta.get("pr_number")
    if footer_pr is not None and int(footer_pr) != int(getattr(pr, "number", 0)):
        return None
    footer_head = _normalize_sha(footer_meta.get("reviewed_head"))
    event_head = _normalize_sha(event.get("reviewed_head"))
    for candidate in (footer_head, event_head):
        if candidate and not _head_matches(candidate=candidate, head_sha=head_sha):
            return None
    source_type = "pr_review" if event.get("kind") == "review" else "pr_comment"
    entry_id = f"{source_type}:{event.get('event_id') or event.get('url') or len(body)}"
    return {
        "source_type": source_type,
        "entry_id": entry_id,
        "body": body,
        "reviewed_head": event_head or footer_head,
        "provenance": {
            "event_id": event.get("event_id"),
            "url": event.get("url"),
            "author": event.get("author"),
            "created_at": event.get("created_at"),
            "footer_session_id": footer_meta.get("session_id"),
            "footer_reviewed_head": footer_head,
        },
    }


def deduplicate(
    *, discussion: list[dict[str, Any]], past_reviews: list[dict[str, Any]], threshold: float = 0.85
) -> tuple[list[dict[str, Any]], int]:
    """Prune discussion events that duplicate retained past reviews."""

    retained_discussion: list[dict[str, Any]] = []
    deduped = 0
    past_bodies = [str(item.get("body") or "") for item in past_reviews if str(item.get("body") or "")]
    for event in discussion:
        body = _event_text(event)
        if body and any(_jaccard(body, past_body) >= threshold for past_body in past_bodies):
            deduped += 1
            continue
        retained_discussion.append(event)
    return retained_discussion, deduped


def find_past_reviews(
    *, pr: Any, sandbox_root: Path, discussion: list[dict[str, Any]], head_sha: str
) -> dict[str, Any]:
    past_reviews = _local_session_reviews(sandbox_root=sandbox_root, pr=pr, head_sha=head_sha)
    for event in discussion:
        remote = _remote_review_from_event(pr=pr, event=event, head_sha=head_sha)
        if remote is not None:
            past_reviews.append(remote)
    pruned_discussion, n_deduped = deduplicate(discussion=discussion, past_reviews=past_reviews)
    return {
        "past_reviews": past_reviews,
        "discussion": pruned_discussion,
        "meta": {
            "n_past_reviews": len(past_reviews),
            "n_discussion": len(pruned_discussion),
            "n_deduped": n_deduped,
        },
    }
