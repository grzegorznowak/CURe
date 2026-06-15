"""Prior CURe review corpus construction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from cure_subsequent_review.contracts import (
    DiscussionArtifact,
    ModuleStatus,
    PriorReviewCorpus,
    PriorReviewCorpusEntry,
)

_CURE_REVIEW_FOOTER_START = "<!-- CURE_REVIEW_FOOTER_START -->"
_CURE_REVIEW_FOOTER_END = "<!-- CURE_REVIEW_FOOTER_END -->"
_FOOTER_SHA_RE = re.compile(r"(?:^|[·\s])sha\s+(?P<sha>[0-9a-fA-F]{3,40}|-)(?=$|[·_\s])")
_FOOTER_SESSION_RE = re.compile(r"(?:^|[·\s])session\s+(?P<session>[^·_\n\r]+)")
_SESSION_PR_RE = re.compile(r"(?:^|[-_/])pr(?P<number>\d+)(?:[-_/]|$)", re.IGNORECASE)


@dataclass(frozen=True)
class _RemoteFooterProvenance:
    has_official_footer: bool
    compatible: bool
    reason: str | None = None
    audit_reason: str | None = None
    footer_session_id: str | None = None
    footer_pr_number: int | None = None
    footer_reviewed_head: str | None = None
    event_reviewed_head: str | None = None


def _extract_official_cure_review_footer(body: str) -> str | None:
    start = body.find(_CURE_REVIEW_FOOTER_START)
    end = body.find(_CURE_REVIEW_FOOTER_END)
    if start < 0 or end <= start:
        return None
    return body[start + len(_CURE_REVIEW_FOOTER_START) : end].strip()


def _has_official_cure_review_footer(body: str) -> bool:
    return _extract_official_cure_review_footer(body) is not None


def _normalize_sha(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized if normalized and normalized != "-" else None


def _footer_session_pr_number(session_id: str | None) -> int | None:
    match = _SESSION_PR_RE.search(str(session_id or "").strip())
    if match is None:
        return None
    try:
        return int(match.group("number"))
    except ValueError:
        return None


def _parse_footer_metadata(body: str) -> dict[str, Any]:
    footer = _extract_official_cure_review_footer(body)
    if footer is None:
        return {}
    sha_match = _FOOTER_SHA_RE.search(footer)
    session_match = _FOOTER_SESSION_RE.search(footer)
    session_id = str(session_match.group("session")).strip() if session_match is not None else None
    reviewed_head = _normalize_sha(sha_match.group("sha") if sha_match is not None else None)
    return {
        "footer_text": footer,
        "session_id": session_id,
        "pr_number": _footer_session_pr_number(session_id),
        "reviewed_head": reviewed_head,
    }


def _head_matches_current(*, footer_head: str | None, current_head: str | None) -> bool:
    footer = _normalize_sha(footer_head)
    current = _normalize_sha(current_head)
    if footer is None or current is None:
        return False
    return current.startswith(footer) or footer.startswith(current)


def _remote_event_label(*, source_type: str, event_id: str) -> str:
    noun = "comment" if source_type == "pr_comment" else "review"
    return f"remote CURe {noun} {event_id}" if event_id else f"remote CURe {noun}"


def _foreign_footer_audit_reason(
    *,
    pr: Any,
    source_type: str,
    event_id: str,
    footer_session_id: str | None,
    footer_pr_number: int | None,
    footer_reviewed_head: str | None,
    event_reviewed_head: str | None,
    current_head: str | None,
) -> str:
    current_pr = f"PR{getattr(pr, 'number', '?')}"
    if footer_pr_number is not None and footer_session_id:
        owner = f"PR{footer_pr_number}/session {footer_session_id}"
    elif footer_session_id:
        owner = f"session {footer_session_id}"
    elif footer_pr_number is not None:
        owner = f"PR{footer_pr_number}"
    else:
        owner = "unknown PR/session provenance"
    if footer_reviewed_head:
        owner = f"{owner} at sha {footer_reviewed_head}"
    if event_reviewed_head:
        owner = f"{owner}; event reviewed_head {event_reviewed_head}"
    normalized_current_head = _normalize_sha(current_head)
    current_head_text = f" at sha {normalized_current_head[:7]}" if normalized_current_head else ""
    return (
        f"Ignored {_remote_event_label(source_type=source_type, event_id=event_id)}: official footer belongs to "
        f"{owner}, while this run is reviewing {current_pr}{current_head_text}, so it was not used as "
        f"{current_pr} prior-review provenance."
    )


def _assess_remote_cure_footer_provenance(
    *,
    pr: Any,
    source_type: str,
    event_id: str,
    body: str,
    current_head: str | None = None,
    event_reviewed_head: str | None = None,
) -> _RemoteFooterProvenance:
    metadata = _parse_footer_metadata(body)
    if not metadata:
        return _RemoteFooterProvenance(has_official_footer=False, compatible=False, reason="cure_authorship_not_established")

    footer_session_id = metadata.get("session_id") if isinstance(metadata.get("session_id"), str) else None
    footer_pr_number = metadata.get("pr_number") if isinstance(metadata.get("pr_number"), int) else None
    footer_reviewed_head = _normalize_sha(metadata.get("reviewed_head"))
    normalized_event_reviewed_head = _normalize_sha(event_reviewed_head)
    current_head_normalized = _normalize_sha(current_head)
    current_pr_number = getattr(pr, "number", None)

    foreign = False
    if footer_pr_number is not None and current_pr_number is not None and footer_pr_number != current_pr_number:
        foreign = True
    if current_head_normalized is not None:
        reviewed_head_signals = [signal for signal in (footer_reviewed_head, normalized_event_reviewed_head) if signal is not None]
        if not reviewed_head_signals:
            foreign = True
        elif any(not _head_matches_current(footer_head=signal, current_head=current_head_normalized) for signal in reviewed_head_signals):
            foreign = True

    if foreign:
        return _RemoteFooterProvenance(
            has_official_footer=True,
            compatible=False,
            reason="foreign_cure_footer_provenance",
            audit_reason=_foreign_footer_audit_reason(
                pr=pr,
                source_type=source_type,
                event_id=event_id,
                footer_session_id=footer_session_id,
                footer_pr_number=footer_pr_number,
                footer_reviewed_head=footer_reviewed_head,
                event_reviewed_head=normalized_event_reviewed_head,
                current_head=current_head_normalized,
            ),
            footer_session_id=footer_session_id,
            footer_pr_number=footer_pr_number,
            footer_reviewed_head=footer_reviewed_head,
            event_reviewed_head=normalized_event_reviewed_head,
        )

    return _RemoteFooterProvenance(
        has_official_footer=True,
        compatible=True,
        footer_session_id=footer_session_id,
        footer_pr_number=footer_pr_number,
        footer_reviewed_head=footer_reviewed_head,
        event_reviewed_head=normalized_event_reviewed_head,
    )


def _looks_cure_authored(*, author: str | None, body: str) -> bool:
    """Return true only for the official CURe review footer marker.

    Remote GitHub issue comments and pull review bodies may be authored by the
    operator or another non-bot account, so author/login is not a durable CURe
    provenance signal.  Generic body text alone is still insufficient: a human
    can mention ``CURe review`` or ``<!-- cure -->`` in discussion without that
    being evidence of a prior CURe run.
    """

    _ = author
    return _has_official_cure_review_footer(body)


def build_prior_review_corpus(
    *,
    pr: Any,
    sessions: list[Any] | tuple[Any, ...],
    discussion: DiscussionArtifact | None = None,
    current_head: str | None = None,
) -> PriorReviewCorpus:
    entries: list[PriorReviewCorpusEntry] = []
    reasons: list[str] = []
    ignored: list[dict[str, Any]] = []

    for session in sessions:
        path = getattr(session, "review_md_path", None)
        session_id = str(getattr(session, "session_id", "") or getattr(path, "name", "review"))
        artifact_status = str(getattr(session, "review_artifact_status", "available") or "available")
        if artifact_status != "available":
            reasons.append("prior_review_artifact_unavailable")
            ignored.append(
                {
                    "source_type": "session",
                    "session_id": session_id,
                    "reason": str(getattr(session, "review_artifact_reason", None) or artifact_status),
                    "review_md_path": str(getattr(session, "review_md_metadata_path", None) or path or ""),
                    "session_dir": str(getattr(session, "session_dir", "")),
                }
            )
            continue
        try:
            body = path.read_text(encoding="utf-8") if path is not None else ""
        except Exception as exc:  # noqa: BLE001 - malformed/missing artifact is degraded corpus input
            reasons.append("prior_review_artifact_unavailable")
            ignored.append(
                {
                    "source_type": "session",
                    "session_id": session_id,
                    "reason": str(exc),
                    "review_md_path": str(path or ""),
                    "session_dir": str(getattr(session, "session_dir", "")),
                }
            )
            continue
        entries.append(
            PriorReviewCorpusEntry(
                entry_id=f"session:{session_id}",
                source_type="session_review",
                artifact_path=path,
                body=body,
                reviewed_head=getattr(session, "review_head_sha", None),
                provenance={
                    "session_id": session_id,
                    "session_dir": str(getattr(session, "session_dir", "")),
                    "review_md_path": str(path),
                    "created_at": getattr(session, "created_at", None),
                    "completed_at": getattr(session, "completed_at", None),
                },
            )
        )

    remote_corpus_sources = {
        "issue_comment": ("pr_comment", "comment_id"),
        "review": ("pr_review", "review_id"),
    }
    if discussion is not None:
        if discussion.status is ModuleStatus.DEGRADED:
            reasons.extend(discussion.status_reasons)
        for event in discussion.events:
            remote_source = remote_corpus_sources.get(event.kind)
            if remote_source is None:
                continue
            source_type, id_field = remote_source
            provenance: dict[str, Any] = {
                id_field: event.event_id,
                "url": event.url,
                "author": event.author,
                "created_at": event.created_at,
            }
            if event.kind == "review":
                provenance["state"] = event.review_state
                provenance["reviewed_head"] = event.reviewed_head
            assessment = _assess_remote_cure_footer_provenance(
                pr=pr,
                source_type=source_type,
                event_id=event.event_id,
                body=event.body,
                current_head=current_head,
                event_reviewed_head=event.reviewed_head,
            )
            if assessment.compatible:
                if assessment.footer_session_id:
                    provenance["footer_session_id"] = assessment.footer_session_id
                if assessment.footer_pr_number is not None:
                    provenance["footer_pr_number"] = assessment.footer_pr_number
                if assessment.footer_reviewed_head:
                    provenance["footer_reviewed_head"] = assessment.footer_reviewed_head
                if assessment.event_reviewed_head:
                    provenance["event_reviewed_head"] = assessment.event_reviewed_head
                entries.append(
                    PriorReviewCorpusEntry(
                        entry_id=f"{source_type}:{event.event_id}",
                        source_type=source_type,
                        body=event.body,
                        reviewed_head=event.reviewed_head or assessment.footer_reviewed_head,
                        provenance=provenance,
                    )
                )
            else:
                ignored_item: dict[str, Any] = {
                    "source_type": source_type,
                    id_field: event.event_id,
                    "author": event.author,
                    "reason": assessment.reason or "cure_authorship_not_established",
                }
                if assessment.audit_reason:
                    ignored_item["audit_reason"] = assessment.audit_reason
                if assessment.footer_session_id:
                    ignored_item["footer_session_id"] = assessment.footer_session_id
                if assessment.footer_pr_number is not None:
                    ignored_item["footer_pr_number"] = assessment.footer_pr_number
                if assessment.footer_reviewed_head:
                    ignored_item["footer_reviewed_head"] = assessment.footer_reviewed_head
                if assessment.event_reviewed_head:
                    ignored_item["event_reviewed_head"] = assessment.event_reviewed_head
                ignored.append(ignored_item)

    if not sessions and not entries:
        reasons.append("no_prior_reviews")

    status = ModuleStatus.SUCCESS if entries and not reasons else ModuleStatus.DEGRADED
    return PriorReviewCorpus(
        status=status,
        entries=tuple(entries),
        status_reasons=tuple(dict.fromkeys(reasons)),
        ignored_pr_comments=tuple(ignored),
    )
