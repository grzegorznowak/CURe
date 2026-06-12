"""Prior CURe review corpus construction."""

from __future__ import annotations

from typing import Any

from cure_subsequent_review.contracts import (
    DiscussionArtifact,
    ModuleStatus,
    PriorReviewCorpus,
    PriorReviewCorpusEntry,
)

_CURE_REVIEW_FOOTER_START = "<!-- CURE_REVIEW_FOOTER_START -->"
_CURE_REVIEW_FOOTER_END = "<!-- CURE_REVIEW_FOOTER_END -->"


def _has_official_cure_review_footer(body: str) -> bool:
    start = body.find(_CURE_REVIEW_FOOTER_START)
    end = body.find(_CURE_REVIEW_FOOTER_END)
    return start >= 0 and end > start


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
) -> PriorReviewCorpus:
    _ = pr
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
            provenance = {
                id_field: event.event_id,
                "url": event.url,
                "author": event.author,
                "created_at": event.created_at,
            }
            if event.kind == "review":
                provenance["state"] = event.review_state
                provenance["reviewed_head"] = event.reviewed_head
            if _looks_cure_authored(author=event.author, body=event.body):
                entries.append(
                    PriorReviewCorpusEntry(
                        entry_id=f"{source_type}:{event.event_id}",
                        source_type=source_type,
                        body=event.body,
                        reviewed_head=event.reviewed_head,
                        provenance=provenance,
                    )
                )
            else:
                ignored.append(
                    {
                        "source_type": source_type,
                        id_field: event.event_id,
                        "author": event.author,
                        "reason": "cure_authorship_not_established",
                    }
                )

    if not sessions and not entries:
        reasons.append("no_prior_reviews")

    status = ModuleStatus.SUCCESS if entries and not reasons else ModuleStatus.DEGRADED
    return PriorReviewCorpus(
        status=status,
        entries=tuple(entries),
        status_reasons=tuple(dict.fromkeys(reasons)),
        ignored_pr_comments=tuple(ignored),
    )
