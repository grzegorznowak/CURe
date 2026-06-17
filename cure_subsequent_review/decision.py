"""Decision service for automatic subsequent-review command mode.

Story 02 keeps command mode separate from Story 01 evidence policy.  This
module decides whether Story 01 intake should run for a new sandbox and writes
an explicit decision artifact even when intake is disabled.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from meta import write_json

from cure_subsequent_review.contracts import DiscussionArtifact, EvidencePolicy, ModuleStatus
from cure_subsequent_review.github_history import JsonFetcher, collect_pr_discussion
from cure_subsequent_review.prior_corpus import _assess_remote_cure_footer_provenance


class SubsequentReviewCommandMode(str, Enum):
    AUTO = "auto"
    DISABLED = "disabled"


@dataclass(frozen=True)
class SubsequentReviewDecision:
    mode: SubsequentReviewCommandMode
    enabled: bool
    evidence_policy: EvidencePolicy
    reasons: tuple[str, ...]
    signal_counts: dict[str, int]
    degraded_reasons: tuple[str, ...] = ()
    rejected_remote_cure_markers: tuple[dict[str, Any], ...] = ()

    def to_json(self, *, pr: Any | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": 1,
            "mode": self.mode.value,
            "enabled": self.enabled,
            "evidence_policy": self.evidence_policy.value,
            "reasons": list(self.reasons),
            "signal_counts": dict(self.signal_counts),
            "degraded_reasons": list(self.degraded_reasons),
        }
        if self.rejected_remote_cure_markers:
            payload["rejected_remote_cure_markers"] = [dict(item) for item in self.rejected_remote_cure_markers]
        if pr is not None:
            payload["pr"] = {"host": pr.host, "owner": pr.owner, "repo": pr.repo, "number": pr.number}
        return payload


def normalize_command_mode(value: str | SubsequentReviewCommandMode | None) -> SubsequentReviewCommandMode:
    if isinstance(value, SubsequentReviewCommandMode):
        return value
    normalized = str(value or SubsequentReviewCommandMode.AUTO.value).strip().lower()
    if normalized == SubsequentReviewCommandMode.AUTO.value:
        return SubsequentReviewCommandMode.AUTO
    if normalized == SubsequentReviewCommandMode.DISABLED.value:
        return SubsequentReviewCommandMode.DISABLED
    raise ValueError("subsequent-review command mode must be one of: auto, disabled")


def _session_has_subsequent_artifacts(session: Any) -> bool:
    session_dir = getattr(session, "session_dir", None)
    if session_dir is None:
        return False
    try:
        root = Path(session_dir)
    except TypeError:
        return False
    candidates = (
        root / "work" / "subsequent" / "run_manifest.json",
        root / "work" / "subsequent" / "decision.json",
        root / "work" / "subsequent" / "prior_review_corpus.json",
    )
    return any(path.is_file() for path in candidates)


def _ordered_unique(items: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item for item in items if item))


def _remote_source_type(event: Any) -> str | None:
    if event.kind == "issue_comment":
        return "pr_comment"
    if event.kind == "review":
        return "pr_review"
    return None


def _remote_footer_assessment(*, pr: Any, event: Any, current_head: str | None) -> Any | None:
    source_type = _remote_source_type(event)
    if source_type is None:
        return None
    return _assess_remote_cure_footer_provenance(
        pr=pr,
        source_type=source_type,
        event_id=str(event.event_id or ""),
        body=str(event.body or ""),
        current_head=current_head,
        event_reviewed_head=getattr(event, "reviewed_head", None),
    )


def _rejected_remote_marker_metadata(*, pr: Any, event: Any, assessment: Any, current_head: str | None) -> dict[str, Any]:
    source_type = _remote_source_type(event) or "remote"
    id_field = "review_id" if source_type == "pr_review" else "comment_id"
    event_timestamp = getattr(event, "created_at", None)
    item: dict[str, Any] = {
        "source_type": source_type,
        id_field: str(getattr(event, "event_id", "") or ""),
        "url": getattr(event, "url", None),
        "author": getattr(event, "author", None),
        "created_at": event_timestamp,
        "reason": str(getattr(assessment, "reason", None) or "foreign_cure_footer_provenance"),
        "audit_reason": getattr(assessment, "audit_reason", None),
        "current_pr_number": getattr(pr, "number", None),
        "current_head": str(current_head or "").strip() or None,
        "footer_pr_number": getattr(assessment, "footer_pr_number", None),
        "footer_session_id": getattr(assessment, "footer_session_id", None),
        "footer_reviewed_head": getattr(assessment, "footer_reviewed_head", None),
        "event_reviewed_head": getattr(assessment, "event_reviewed_head", None),
    }
    if source_type == "pr_review" and event_timestamp:
        item["submitted_at"] = event_timestamp
    return {key: value for key, value in item.items() if value not in (None, "")}


_NON_ENABLING_REMOTE_METADATA_REASONS = {"discussion_incomplete", "thread_state_unavailable"}


def _degraded_remote_probe_requires_intake(degraded_reasons: tuple[str, ...]) -> bool:
    return not degraded_reasons or any(reason not in _NON_ENABLING_REMOTE_METADATA_REASONS for reason in degraded_reasons)


def decide_subsequent_review(
    *,
    pr: Any,
    completed_sessions: list[Any] | tuple[Any, ...],
    mode: SubsequentReviewCommandMode | str,
    evidence_policy: EvidencePolicy,
    fetch_json: JsonFetcher | None = None,
    discussion: DiscussionArtifact | None = None,
    current_head: str | None = None,
) -> tuple[SubsequentReviewDecision, DiscussionArtifact | None]:
    """Return the command-mode decision plus the discussion artifact used to decide."""

    command_mode = normalize_command_mode(mode)
    completed_count = len(completed_sessions)
    sessions_with_subsequent_artifacts = sum(1 for session in completed_sessions if _session_has_subsequent_artifacts(session))
    signal_counts = {
        "completed_sessions": completed_count,
        "sessions_with_subsequent_artifacts": sessions_with_subsequent_artifacts,
        "remote_events": 0,
        "remote_cure_markers": 0,
        "accepted_remote_cure_markers": 0,
        "foreign_remote_cure_markers": 0,
    }

    if command_mode is SubsequentReviewCommandMode.DISABLED:
        return (
            SubsequentReviewDecision(
                mode=command_mode,
                enabled=False,
                evidence_policy=evidence_policy,
                reasons=("operator_disabled",),
                signal_counts=signal_counts,
            ),
            None,
        )

    reasons: list[str] = []
    if completed_count > 0:
        reasons.append("completed_sessions_found")
    if sessions_with_subsequent_artifacts > 0:
        reasons.append("prior_subsequent_artifacts_found")
    if discussion is None and not reasons and fetch_json is not None:
        discussion = collect_pr_discussion(pr=pr, fetch_json=fetch_json)

    if discussion is None:
        if reasons:
            return (
                SubsequentReviewDecision(
                    mode=command_mode,
                    enabled=True,
                    evidence_policy=evidence_policy,
                    reasons=_ordered_unique(reasons),
                    signal_counts=signal_counts,
                ),
                None,
            )
        return (
            SubsequentReviewDecision(
                mode=command_mode,
                enabled=True,
                evidence_policy=evidence_policy,
                reasons=("remote_probe_degraded",),
                signal_counts=signal_counts,
                degraded_reasons=("remote_probe_unavailable",),
            ),
            None,
        )

    signal_counts["remote_events"] = len(discussion.events)
    remote_assessments: list[Any] = []
    rejected_remote_cure_markers: list[dict[str, Any]] = []
    for event in discussion.events:
        assessment = _remote_footer_assessment(pr=pr, event=event, current_head=current_head)
        if assessment is None:
            continue
        remote_assessments.append(assessment)
        if assessment.has_official_footer and assessment.reason == "foreign_cure_footer_provenance":
            rejected_remote_cure_markers.append(
                _rejected_remote_marker_metadata(pr=pr, event=event, assessment=assessment, current_head=current_head)
            )
    remote_cure_markers = sum(1 for assessment in remote_assessments if assessment.has_official_footer)
    accepted_remote_cure_markers = sum(1 for assessment in remote_assessments if assessment.compatible)
    foreign_remote_cure_markers = sum(
        1 for assessment in remote_assessments if assessment.has_official_footer and assessment.reason == "foreign_cure_footer_provenance"
    )
    signal_counts["remote_cure_markers"] = remote_cure_markers
    signal_counts["accepted_remote_cure_markers"] = accepted_remote_cure_markers
    signal_counts["foreign_remote_cure_markers"] = foreign_remote_cure_markers
    disabled_rejected_remote_cure_markers = (
        tuple(rejected_remote_cure_markers)
        if remote_cure_markers > 0 and accepted_remote_cure_markers == 0 and foreign_remote_cure_markers == remote_cure_markers
        else ()
    )
    degraded_reasons = list(discussion.status_reasons)
    for marker in discussion.pagination:
        if not marker.complete and marker.status not in degraded_reasons:
            degraded_reasons.append(marker.status)

    if accepted_remote_cure_markers > 0:
        return (
            SubsequentReviewDecision(
                mode=command_mode,
                enabled=True,
                evidence_policy=evidence_policy,
                reasons=_ordered_unique([*reasons, "cure_pr_discussion_found"]),
                signal_counts=signal_counts,
                degraded_reasons=_ordered_unique(degraded_reasons),
            ),
            discussion,
        )
    ordered_degraded_reasons = _ordered_unique(degraded_reasons)
    if "operator_skipped_degraded_discussion" in ordered_degraded_reasons and remote_cure_markers == 0:
        return (
            SubsequentReviewDecision(
                mode=command_mode,
                enabled=bool(reasons),
                evidence_policy=evidence_policy,
                reasons=_ordered_unique(reasons) or ("no_prior_review_signals",),
                signal_counts=signal_counts,
                degraded_reasons=ordered_degraded_reasons,
            ),
            discussion,
        )
    if discussion.status is ModuleStatus.DEGRADED or degraded_reasons:
        if _degraded_remote_probe_requires_intake(ordered_degraded_reasons):
            return (
                SubsequentReviewDecision(
                    mode=command_mode,
                    enabled=True,
                    evidence_policy=evidence_policy,
                    reasons=_ordered_unique([*reasons, "remote_probe_degraded"]),
                    signal_counts=signal_counts,
                    degraded_reasons=ordered_degraded_reasons or ("remote_probe_degraded",),
                ),
                discussion,
            )
        return (
            SubsequentReviewDecision(
                mode=command_mode,
                enabled=bool(reasons),
                evidence_policy=evidence_policy,
                reasons=_ordered_unique(reasons) or ("no_prior_review_signals",),
                signal_counts=signal_counts,
                degraded_reasons=ordered_degraded_reasons,
                rejected_remote_cure_markers=disabled_rejected_remote_cure_markers,
            ),
            discussion,
        )
    return (
        SubsequentReviewDecision(
            mode=command_mode,
            enabled=bool(reasons),
            evidence_policy=evidence_policy,
            reasons=_ordered_unique(reasons) or ("no_prior_review_signals",),
            signal_counts=signal_counts,
            rejected_remote_cure_markers=disabled_rejected_remote_cure_markers,
        ),
        discussion,
    )


def write_decision_artifact(*, work_dir: Path, pr: Any, decision: SubsequentReviewDecision) -> Path:
    path = work_dir / "subsequent" / "decision.json"
    write_json(path, decision.to_json(pr=pr))
    return path


def _marker_label(marker: dict[str, Any]) -> str:
    source_type = str(marker.get("source_type") or "remote marker")
    source_label = "review" if source_type == "pr_review" else "comment"
    marker_id = str(marker.get("review_id") or marker.get("comment_id") or "").strip()
    return f"{source_label} {marker_id}" if marker_id else source_label


def _marker_location(marker: dict[str, Any]) -> str:
    parts: list[str] = []
    current_pr = marker.get("current_pr_number")
    current_head = str(marker.get("current_head") or "").strip()
    if current_pr or current_head:
        current = f"current PR {current_pr}" if current_pr else "current PR"
        if current_head:
            current = f"{current} at {current_head[:12]}"
        parts.append(current)
    footer_pr = marker.get("footer_pr_number")
    footer_session = str(marker.get("footer_session_id") or "").strip()
    footer_head = str(marker.get("footer_reviewed_head") or "").strip()
    if footer_pr or footer_session or footer_head:
        footer = f"footer PR {footer_pr}" if footer_pr else "footer PR unknown"
        if footer_session:
            footer = f"{footer}, session {footer_session}"
        if footer_head:
            footer = f"{footer}, head {footer_head[:12]}"
        parts.append(footer)
    event_head = str(marker.get("event_reviewed_head") or "").strip()
    if event_head:
        parts.append(f"event head {event_head[:12]}")
    return "; ".join(parts)


def format_rejected_remote_cure_marker_notice(markers: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> str | None:
    sanitized = [dict(marker) for marker in markers if isinstance(marker, dict)]
    if not sanitized:
        return None
    count = len(sanitized)
    plural = "s" if count != 1 else ""
    lines = [
        "CURe Operator Notice — Not part of the review",
        "",
        (
            f"CURe found {count} official-footer remote CURe marker{plural} but rejected "
            "them for current-run provenance mismatch. They were not used as prior-review context "
            "and are not included in the GitHub review body below."
        ),
        "",
        "Rejected marker details:",
    ]
    for marker in sanitized:
        label = _marker_label(marker)
        url = str(marker.get("url") or "").strip()
        author = str(marker.get("author") or "").strip()
        created_at = str(marker.get("created_at") or "").strip()
        reason = str(marker.get("audit_reason") or marker.get("reason") or "foreign provenance mismatch").strip()
        location = _marker_location(marker)
        details = [part for part in (url, f"author {author}" if author else "", created_at, location) if part]
        suffix = f" ({'; '.join(details)})" if details else ""
        lines.append(f"- {label}{suffix}: {reason}")
    lines.extend(
        [
            "",
            "Cleanup guidance: remove, update, or move the foreign CURe footer/comment if it should not appear in future audits; then rerun CURe.",
        ]
    )
    return "\n".join(lines)


def decision_meta_json(
    *,
    decision: SubsequentReviewDecision,
    decision_path: Path,
    artifact_dir: Path,
    manifest_path: Path | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "mode": decision.mode.value,
        "enabled": decision.enabled,
        "evidence_policy": decision.evidence_policy.value,
        "decision": {
            "reasons": list(decision.reasons),
            "signal_counts": dict(decision.signal_counts),
            "degraded_reasons": list(decision.degraded_reasons),
        },
        "rejected_remote_cure_markers": [dict(item) for item in decision.rejected_remote_cure_markers],
        "decision_path": str(decision_path),
        "artifact_dir": str(artifact_dir),
        "manifest_path": str(manifest_path) if manifest_path is not None else None,
    }


def summarize_decision(decision: SubsequentReviewDecision) -> str:
    if decision.mode is SubsequentReviewCommandMode.DISABLED:
        state = "disabled"
    else:
        state = "auto enabled" if decision.enabled else "auto disabled"
    reason_text = ", ".join(decision.reasons) if decision.reasons else "no reasons recorded"
    if decision.degraded_reasons:
        reason_text = f"{reason_text}; degraded: {', '.join(decision.degraded_reasons)}"
    return f"Subsequent review decision: {state}; reasons: {reason_text}"
