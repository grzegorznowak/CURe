"""Typed contracts for subsequent PR review intake.

Story 01 defines contracts for all functional modules. Story 03 adds semantic
source-state, discussion-signal, and disposition contracts for modules 6-8.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


SUBSEQUENT_REVIEW_ARTIFACT_SCHEMA_VERSION = 1


class EvidencePolicy(str, Enum):
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"


class ModuleStatus(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    SUCCESS = "success"
    DEGRADED = "degraded"


class SourceState(str, Enum):
    RESOLVED_FROM_SOURCE = "resolved_from_source"
    STILL_OPEN = "still_open"
    PARTIALLY_RESOLVED = "partially_resolved"
    SOURCE_UNKNOWN = "source_unknown"
    NOT_VERIFIABLE = "not_verifiable"


class DiscussionSignalClass(str, Enum):
    DEVELOPER_CLAIM_FIXED = "developer_claim_fixed"
    RESOLVED_THREAD_HINT = "resolved_thread_hint"
    BY_DESIGN = "by_design"
    ADDRESSED_ELSEWHERE = "addressed_elsewhere"
    DUPLICATE_SUPERSEDED = "duplicate_superseded"
    UNRESOLVED_THREAD_HINT = "unresolved_thread_hint"
    PUSHBACK = "pushback"
    AUTHORITY_CONFLICT = "authority_conflict"


class DispositionAction(str, Enum):
    CONFIRM_RESOLVED = "confirm_resolved"
    REWORD_PARTIAL = "reword_partial"
    SUPPRESS_DUPLICATE = "suppress_duplicate"
    MOVE_OUT_OF_SCOPE = "move_out_of_scope"
    RE_REPORT = "re_report"


class SubsequentReviewModule(str, Enum):
    CONTROL_PLANE = "control_plane"
    PR_HISTORY_COLLECTOR = "pr_history_collector"
    PRIOR_REVIEW_CORPUS_BUILDER = "prior_review_corpus_builder"
    PRIOR_FINDING_EXTRACTOR = "prior_finding_extractor"
    FINDING_RECONCILER = "finding_reconciler"
    SOURCE_TRUTH_VERIFIER = "source_truth_verifier"
    DISCUSSION_SIGNAL_RESOLVER = "discussion_signal_resolver"
    DISPOSITION_ARBITER = "disposition_arbiter"
    REVIEW_CONTEXT_PACKAGER = "review_context_packager"
    REPORT_GOVERNOR = "report_governor"
    REVIEW_MEMORY_STORE = "review_memory_store"
    DEGRADED_RUNTIME_MANAGER = "degraded_runtime_manager"
    LANDMARK_TRACE_RUNNER = "landmark_trace_runner"


SubsequentReviewModules = SubsequentReviewModule


@dataclass(frozen=True)
class ModuleRunRecord:
    module: SubsequentReviewModule
    status: ModuleStatus
    reasons: tuple[str, ...] = ()
    artifact_path: str | None = None

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": self.status.value}
        if self.reasons:
            payload["reasons"] = list(self.reasons)
        if self.artifact_path:
            payload["artifact_path"] = self.artifact_path
        return payload


@dataclass(frozen=True)
class PaginationMarker:
    source: str
    complete: bool
    status: str = "complete"
    detail: str | None = None
    endpoint: str | None = None
    fetch: str | None = None
    cause: str | None = None
    exit_code: int | None = None
    stderr: str | None = None
    stdout: str | None = None
    command: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"source": self.source, "complete": self.complete, "status": self.status}
        if self.detail:
            payload["detail"] = self.detail
        if self.endpoint:
            payload["endpoint"] = self.endpoint
        if self.fetch:
            payload["fetch"] = self.fetch
        if self.cause:
            payload["cause"] = self.cause
        if self.exit_code is not None:
            payload["exit_code"] = self.exit_code
        if self.stderr:
            payload["stderr"] = self.stderr
        if self.stdout:
            payload["stdout"] = self.stdout
        if self.command:
            payload["command"] = list(self.command)
        return payload


@dataclass(frozen=True)
class DiscussionEvent:
    kind: str
    event_id: str
    author: str | None
    body: str
    url: str | None = None
    created_at: str | None = None
    path: str | None = None
    line: int | None = None
    review_state: str | None = None
    reviewed_head: str | None = None
    thread_state: str = "unknown"

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "event_id": self.event_id,
            "author": self.author,
            "body": self.body,
            "url": self.url,
            "created_at": self.created_at,
            "path": self.path,
            "line": self.line,
            "review_state": self.review_state,
            "reviewed_head": self.reviewed_head,
            "thread_state": self.thread_state,
        }


@dataclass(frozen=True)
class DiscussionArtifact:
    status: ModuleStatus
    events: tuple[DiscussionEvent, ...] = ()
    pagination: tuple[PaginationMarker, ...] = ()
    status_reasons: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": SUBSEQUENT_REVIEW_ARTIFACT_SCHEMA_VERSION,
            "status": self.status.value,
            "status_reasons": list(self.status_reasons),
            "events": [item.to_json() for item in self.events],
            "pagination": [item.to_json() for item in self.pagination],
        }


@dataclass(frozen=True)
class PriorReviewCorpusEntry:
    entry_id: str
    source_type: str
    provenance: dict[str, Any]
    body: str
    reviewed_head: str | None = None
    artifact_path: Path | None = None

    def to_json(self) -> dict[str, Any]:
        payload = {
            "entry_id": self.entry_id,
            "source_type": self.source_type,
            "provenance": self.provenance,
            "body": self.body,
            "reviewed_head": self.reviewed_head,
        }
        if self.artifact_path is not None:
            payload["artifact_path"] = str(self.artifact_path)
        return payload


@dataclass(frozen=True)
class PriorReviewCorpus:
    status: ModuleStatus
    entries: tuple[PriorReviewCorpusEntry, ...] = ()
    status_reasons: tuple[str, ...] = ()
    ignored_pr_comments: tuple[dict[str, Any], ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": SUBSEQUENT_REVIEW_ARTIFACT_SCHEMA_VERSION,
            "status": self.status.value,
            "status_reasons": list(self.status_reasons),
            "entries": [item.to_json() for item in self.entries],
            "ignored_pr_comments": list(self.ignored_pr_comments),
        }


@dataclass(frozen=True)
class FindingProvenance:
    corpus_entry_id: str
    source_type: str
    artifact_path: str | None = None
    comment_url: str | None = None
    reviewed_head: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "corpus_entry_id": self.corpus_entry_id,
            "source_type": self.source_type,
            "artifact_path": self.artifact_path,
            "comment_url": self.comment_url,
            "reviewed_head": self.reviewed_head,
        }


@dataclass(frozen=True)
class PriorFindingCandidate:
    finding_id: str
    severity: str
    section: str
    title: str
    source_evidence_snippets: tuple[str, ...]
    reviewed_head: str | None
    provenance: FindingProvenance
    fingerprint_hints: dict[str, str] = field(default_factory=dict)
    supersedes: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "severity": self.severity,
            "section": self.section,
            "title": self.title,
            "source_evidence_snippets": list(self.source_evidence_snippets),
            "reviewed_head": self.reviewed_head,
            "provenance": self.provenance.to_json(),
            "fingerprint_hints": self.fingerprint_hints,
            "supersedes": list(self.supersedes),
        }


@dataclass(frozen=True)
class PriorFindingLedger:
    status: ModuleStatus
    findings: tuple[PriorFindingCandidate, ...] = ()
    status_reasons: tuple[str, ...] = ()
    artifact_statuses: tuple[dict[str, Any], ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": SUBSEQUENT_REVIEW_ARTIFACT_SCHEMA_VERSION,
            "status": self.status.value,
            "status_reasons": list(self.status_reasons),
            "artifact_statuses": list(self.artifact_statuses),
            "findings": [item.to_json() for item in self.findings],
        }


@dataclass(frozen=True)
class ReconciledFindingGroup:
    group_id: str
    canonical_id: str
    finding_ids: tuple[str, ...]
    fingerprint: str
    provenance: tuple[FindingProvenance, ...]
    supersedes: tuple[str, ...] = ()
    local_findings: tuple[dict[str, Any], ...] = ()
    supersedes_edges: tuple[dict[str, Any], ...] = ()
    ambiguous_supersedes: tuple[dict[str, Any], ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "canonical_id": self.canonical_id,
            "finding_ids": list(self.finding_ids),
            "fingerprint": self.fingerprint,
            "provenance": [item.to_json() for item in self.provenance],
            "supersedes": list(self.supersedes),
            "local_findings": list(self.local_findings),
            "supersedes_edges": list(self.supersedes_edges),
            "ambiguous_supersedes": list(self.ambiguous_supersedes),
        }


@dataclass(frozen=True)
class ReconciliationLedger:
    status: ModuleStatus
    groups: tuple[ReconciledFindingGroup, ...] = ()
    status_reasons: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": SUBSEQUENT_REVIEW_ARTIFACT_SCHEMA_VERSION,
            "status": self.status.value,
            "status_reasons": list(self.status_reasons),
            "groups": [item.to_json() for item in self.groups],
        }


@dataclass(frozen=True)
class SourceVerificationRow:
    row_id: str
    group_id: str
    finding_ids: tuple[str, ...]
    source_state: SourceState
    current_source_citations: tuple[dict[str, Any], ...] = ()
    inspected_source_refs: tuple[str, ...] = ()
    unavailable_reasons: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "group_id": self.group_id,
            "finding_ids": list(self.finding_ids),
            "source_state": self.source_state.value,
            "current_source_citations": list(self.current_source_citations),
            "inspected_source_refs": list(self.inspected_source_refs),
            "unavailable_reasons": list(self.unavailable_reasons),
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class SourceVerificationLedger:
    status: ModuleStatus
    rows: tuple[SourceVerificationRow, ...] = ()
    status_reasons: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": SUBSEQUENT_REVIEW_ARTIFACT_SCHEMA_VERSION,
            "status": self.status.value,
            "status_reasons": list(self.status_reasons),
            "rows": [item.to_json() for item in self.rows],
        }


@dataclass(frozen=True)
class DiscussionSignalRow:
    row_id: str
    event_id: str
    group_ids: tuple[str, ...]
    finding_ids: tuple[str, ...]
    signal_class: DiscussionSignalClass
    evidence_policy: EvidencePolicy
    authority: str
    reasons: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "event_id": self.event_id,
            "group_ids": list(self.group_ids),
            "finding_ids": list(self.finding_ids),
            "signal_class": self.signal_class.value,
            "evidence_policy": self.evidence_policy.value,
            "authority": self.authority,
            "reasons": list(self.reasons),
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class DiscussionSignalLedger:
    status: ModuleStatus
    rows: tuple[DiscussionSignalRow, ...] = ()
    status_reasons: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": SUBSEQUENT_REVIEW_ARTIFACT_SCHEMA_VERSION,
            "status": self.status.value,
            "status_reasons": list(self.status_reasons),
            "rows": [item.to_json() for item in self.rows],
        }


@dataclass(frozen=True)
class DispositionRow:
    row_id: str
    group_id: str
    finding_ids: tuple[str, ...]
    action: DispositionAction
    source_verification_row_id: str
    discussion_signal_row_ids: tuple[str, ...]
    reconciliation_group_id: str
    provenance: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "group_id": self.group_id,
            "finding_ids": list(self.finding_ids),
            "action": self.action.value,
            "source_verification_row_id": self.source_verification_row_id,
            "discussion_signal_row_ids": list(self.discussion_signal_row_ids),
            "reconciliation_group_id": self.reconciliation_group_id,
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class DegradedFinding:
    group_id: str
    finding_ids: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "finding_ids": list(self.finding_ids),
            "blocking_reasons": list(self.blocking_reasons),
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class DispositionLedger:
    status: ModuleStatus
    dispositions: tuple[DispositionRow, ...] = ()
    degraded_findings: tuple[DegradedFinding, ...] = ()
    status_reasons: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": SUBSEQUENT_REVIEW_ARTIFACT_SCHEMA_VERSION,
            "status": self.status.value,
            "status_reasons": list(self.status_reasons),
            "dispositions": [item.to_json() for item in self.dispositions],
            "degraded_findings": [item.to_json() for item in self.degraded_findings],
        }
