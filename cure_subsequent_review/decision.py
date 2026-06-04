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

from cure_subsequent_review.contracts import EvidencePolicy, ModuleStatus
from cure_subsequent_review.github_history import JsonFetcher, collect_pr_discussion
from cure_subsequent_review.prior_corpus import _looks_cure_authored


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


def decide_subsequent_review(
    *,
    pr: Any,
    completed_sessions: list[Any] | tuple[Any, ...],
    mode: SubsequentReviewCommandMode | str,
    evidence_policy: EvidencePolicy,
    fetch_json: JsonFetcher | None = None,
) -> SubsequentReviewDecision:
    """Return the command-mode decision for a new sandbox run."""

    command_mode = normalize_command_mode(mode)
    completed_count = len(completed_sessions)
    sessions_with_subsequent_artifacts = sum(1 for session in completed_sessions if _session_has_subsequent_artifacts(session))
    signal_counts = {
        "completed_sessions": completed_count,
        "sessions_with_subsequent_artifacts": sessions_with_subsequent_artifacts,
        "remote_events": 0,
        "remote_cure_markers": 0,
    }

    if command_mode is SubsequentReviewCommandMode.DISABLED:
        return SubsequentReviewDecision(
            mode=command_mode,
            enabled=False,
            evidence_policy=evidence_policy,
            reasons=("operator_disabled",),
            signal_counts=signal_counts,
        )

    reasons: list[str] = []
    if completed_count > 0:
        reasons.append("completed_sessions_found")
    if sessions_with_subsequent_artifacts > 0:
        reasons.append("prior_subsequent_artifacts_found")
    if reasons:
        return SubsequentReviewDecision(
            mode=command_mode,
            enabled=True,
            evidence_policy=evidence_policy,
            reasons=_ordered_unique(reasons),
            signal_counts=signal_counts,
        )

    if fetch_json is None:
        return SubsequentReviewDecision(
            mode=command_mode,
            enabled=True,
            evidence_policy=evidence_policy,
            reasons=("remote_probe_degraded",),
            signal_counts=signal_counts,
            degraded_reasons=("remote_probe_unavailable",),
        )

    discussion = collect_pr_discussion(pr=pr, fetch_json=fetch_json)
    signal_counts["remote_events"] = len(discussion.events)
    remote_cure_markers = sum(1 for event in discussion.events if _looks_cure_authored(author=event.author, body=event.body))
    signal_counts["remote_cure_markers"] = remote_cure_markers
    degraded_reasons = list(discussion.status_reasons)
    for marker in discussion.pagination:
        if not marker.complete and marker.status not in degraded_reasons:
            degraded_reasons.append(marker.status)

    if remote_cure_markers > 0:
        return SubsequentReviewDecision(
            mode=command_mode,
            enabled=True,
            evidence_policy=evidence_policy,
            reasons=("cure_pr_discussion_found",),
            signal_counts=signal_counts,
            degraded_reasons=_ordered_unique(degraded_reasons),
        )
    if discussion.status is ModuleStatus.DEGRADED or degraded_reasons:
        return SubsequentReviewDecision(
            mode=command_mode,
            enabled=True,
            evidence_policy=evidence_policy,
            reasons=("remote_probe_degraded",),
            signal_counts=signal_counts,
            degraded_reasons=_ordered_unique(degraded_reasons) or ("remote_probe_degraded",),
        )
    return SubsequentReviewDecision(
        mode=command_mode,
        enabled=False,
        evidence_policy=evidence_policy,
        reasons=("no_prior_review_signals",),
        signal_counts=signal_counts,
    )


def write_decision_artifact(*, work_dir: Path, pr: Any, decision: SubsequentReviewDecision) -> Path:
    path = work_dir / "subsequent" / "decision.json"
    write_json(path, decision.to_json(pr=pr))
    return path


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
