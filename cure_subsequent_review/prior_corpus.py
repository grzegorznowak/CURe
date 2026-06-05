"""Prior CURe review corpus construction."""

from __future__ import annotations

import re
from typing import Any

from cure_subsequent_review.contracts import (
    DiscussionArtifact,
    ModuleStatus,
    PriorReviewCorpus,
    PriorReviewCorpusEntry,
)

_CURE_AUTHOR_RE = re.compile(r"\b(cure|cureview|reviewflow)(?:\b|-|_)", re.IGNORECASE)
_CURE_BODY_RE = re.compile(r"\b(CURe|CURE|Reviewflow)\s+(review|finding|findings)\b|<!--\s*cure", re.IGNORECASE)


def _looks_cure_authored(*, author: str | None, body: str) -> bool:
    """Return true only for trusted CURe-authored review markers.

    Body text alone is not enough: a human can mention ``CURe review`` in a
    generic GitHub discussion without that being evidence of a prior CURe run.
    """

    return bool(author and _CURE_AUTHOR_RE.search(author) and _CURE_BODY_RE.search(body))


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
        try:
            body = path.read_text(encoding="utf-8") if path is not None else ""
        except Exception as exc:  # noqa: BLE001 - malformed/missing artifact is degraded corpus input
            reasons.append("prior_review_artifact_unavailable")
            ignored.append({"source_type": "session", "session_id": str(getattr(session, "session_id", "")), "reason": str(exc)})
            continue
        session_id = str(getattr(session, "session_id", "") or getattr(path, "name", "review"))
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

    if not sessions:
        reasons.append("no_prior_reviews")

    remote_corpus_sources = {
        "issue_comment": ("pr_comment", "comment_id"),
        "review": ("pr_review", "review_id"),
    }
    if discussion is not None:
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
            if _looks_cure_authored(author=event.author, body=event.body):
                entries.append(
                    PriorReviewCorpusEntry(
                        entry_id=f"{source_type}:{event.event_id}",
                        source_type=source_type,
                        body=event.body,
                        reviewed_head=None,
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

    status = ModuleStatus.SUCCESS if entries and not reasons else ModuleStatus.DEGRADED
    if not entries and reasons == ["no_prior_reviews"]:
        status = ModuleStatus.DEGRADED
    return PriorReviewCorpus(
        status=status,
        entries=tuple(entries),
        status_reasons=tuple(dict.fromkeys(reasons)),
        ignored_pr_comments=tuple(ignored),
    )
