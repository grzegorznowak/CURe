"""Source truth verification for subsequent-review semantic ledgers.

The verifier delegates current-source assessment to an injected provider.  This
module only prepares safe prior-finding context and serializes provider output;
it does not inspect files or treat PR discussion as source proof.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from cure_subsequent_review.contracts import (
    DiscussionSignalClass,
    DiscussionSignalLedger,
    DiscussionSignalRow,
    EvidencePolicy,
    ModuleStatus,
    ReconciledFindingGroup,
    ReconciliationLedger,
    SourceState,
    SourceVerificationLedger,
    SourceVerificationRow,
)


@dataclass(frozen=True)
class FindingVerificationRequest:
    group_id: str
    canonical_id: str
    finding_ids: tuple[str, ...]
    title: str | None
    severity: str | None
    section: str | None
    source_evidence_snippets: tuple[str, ...]
    reviewed_heads: tuple[str, ...]
    pr_files_changed: tuple[str, ...] = ()
    discussion_signals: tuple[dict[str, Any], ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FindingVerificationResult:
    source_state: SourceState
    current_source_citations: tuple[dict[str, Any], ...] = ()
    unavailable_reasons: tuple[str, ...] = ()
    rationale: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)


FindingVerifier = Callable[[FindingVerificationRequest], FindingVerificationResult]


class SourceVerificationMemory(Protocol):
    def synthesize_resolved_source_row(
        self,
        *,
        group_id: str,
        finding_ids: tuple[str, ...],
        row_id: str,
        current_head: str | None,
    ) -> SourceVerificationRow | None: ...


def _local_finding_value(group: ReconciledFindingGroup, key: str) -> str | None:
    for item in group.local_findings:
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return None


def _source_refs(group: ReconciledFindingGroup) -> tuple[str, ...]:
    refs: list[str] = []
    for item in group.local_findings:
        raw_refs = item.get("source_evidence_snippets", ())
        if isinstance(raw_refs, list | tuple):
            refs.extend(str(ref).strip() for ref in raw_refs if str(ref).strip())
    return tuple(dict.fromkeys(refs))


def _reviewed_heads(group: ReconciledFindingGroup) -> tuple[str, ...]:
    heads: list[str] = []
    for item in group.local_findings:
        head = str(item.get("reviewed_head") or "").strip()
        if head:
            heads.append(head)
    return tuple(dict.fromkeys(heads))


def _clean_pr_files_changed(pr_files_changed: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if not pr_files_changed:
        return ()
    return tuple(dict.fromkeys(str(path).strip() for path in pr_files_changed if str(path).strip()))


def _discussion_signal_context(rows: tuple[DiscussionSignalRow, ...]) -> tuple[dict[str, Any], ...]:
    return tuple(row.to_json() for row in rows)


def _request(
    group: ReconciledFindingGroup,
    *,
    pr_files_changed: tuple[str, ...] = (),
    discussion_rows: tuple[DiscussionSignalRow, ...] = (),
) -> FindingVerificationRequest:
    return FindingVerificationRequest(
        group_id=group.group_id,
        canonical_id=group.canonical_id,
        finding_ids=group.finding_ids,
        title=_local_finding_value(group, "title"),
        severity=_local_finding_value(group, "severity"),
        section=_local_finding_value(group, "section"),
        source_evidence_snippets=_source_refs(group),
        reviewed_heads=_reviewed_heads(group),
        pr_files_changed=_clean_pr_files_changed(pr_files_changed),
        discussion_signals=_discussion_signal_context(discussion_rows),
        provenance={"reconciliation_group_id": group.group_id, "fingerprint": group.fingerprint},
    )


def default_finding_verifier(_request: FindingVerificationRequest) -> FindingVerificationResult:
    """Conservative default provider used when no production verifier is wired.

    It never claims resolution.  Operators can inject a chunkhound/LLM/classifier
    provider at runtime; tests inject deterministic providers.
    """

    return FindingVerificationResult(
        source_state=SourceState.SOURCE_UNKNOWN,
        unavailable_reasons=("verifier_provider_not_configured",),
        rationale="no FindingVerifier provider configured",
    )


_DISCUSSION_SKIP_CLASSES = frozenset(
    {
        DiscussionSignalClass.PUSHBACK,
        DiscussionSignalClass.BY_DESIGN,
        DiscussionSignalClass.ADDRESSED_ELSEWHERE,
        DiscussionSignalClass.DUPLICATE_SUPERSEDED,
    }
)


def _discussion_rows_by_group(
    discussion_signals: DiscussionSignalLedger | None,
) -> dict[str, tuple[DiscussionSignalRow, ...]]:
    if discussion_signals is None:
        return {}
    grouped: dict[str, list[DiscussionSignalRow]] = {}
    for row in discussion_signals.rows:
        for group_id in row.group_ids:
            grouped.setdefault(group_id, []).append(row)
    return {group_id: tuple(rows) for group_id, rows in grouped.items()}


def _discussion_skips_source_verifier(rows: tuple[DiscussionSignalRow, ...]) -> bool:
    if not rows:
        return False
    return all(
        row.evidence_policy is EvidencePolicy.UNTRUSTED and row.signal_class in _DISCUSSION_SKIP_CLASSES
        for row in rows
    )


def _skipped_by_discussion_row(
    *,
    row_id: str,
    group: ReconciledFindingGroup,
    discussion_rows: tuple[DiscussionSignalRow, ...],
) -> SourceVerificationRow:
    return SourceVerificationRow(
        row_id=row_id,
        group_id=group.group_id,
        finding_ids=group.finding_ids,
        source_state=SourceState.STILL_OPEN,
        inspected_source_refs=_source_refs(group),
        unavailable_reasons=("source_verification_skipped_by_discussion_signals",),
        provenance={
            "reconciliation_group_id": group.group_id,
            "fingerprint": group.fingerprint,
            "discussion_signal_row_ids": [row.row_id for row in discussion_rows],
            "discussion_signal_classes": [row.signal_class.value for row in discussion_rows],
            "discussion_policies": [row.evidence_policy.value for row in discussion_rows],
            "not_source_proof": True,
            "rationale": (
                "source verifier skipped because all linked discussion signals are untrusted non-fix "
                "skip classes; prior finding remains reportable without treating discussion as source proof"
            ),
        },
    )


def verify_source_truth(
    *,
    reconciliation: ReconciliationLedger,
    verifier: FindingVerifier | None = None,
    memory_store: SourceVerificationMemory | None = None,
    current_head: str | None = None,
    discussion_signals: DiscussionSignalLedger | None = None,
    pr_files_changed: tuple[str, ...] = (),
) -> SourceVerificationLedger:
    provider = verifier or default_finding_verifier
    rows: list[SourceVerificationRow] = []
    reasons: list[str] = list(reconciliation.status_reasons)
    discussion_by_group = _discussion_rows_by_group(discussion_signals)

    for index, group in enumerate(reconciliation.groups, start=1):
        row_id = f"SV-{index:04d}"
        if memory_store is not None and str(current_head or "").strip():
            try:
                cached_row = memory_store.synthesize_resolved_source_row(
                    group_id=group.group_id,
                    finding_ids=group.finding_ids,
                    row_id=row_id,
                    current_head=current_head,
                )
            except Exception:  # noqa: BLE001 - memory is a performance cache; failures disable the gate
                cached_row = None
            if cached_row is not None:
                rows.append(cached_row)
                continue

        discussion_rows = discussion_by_group.get(group.group_id, ())
        if _discussion_skips_source_verifier(discussion_rows):
            rows.append(_skipped_by_discussion_row(row_id=row_id, group=group, discussion_rows=discussion_rows))
            continue

        request = _request(
            group,
            pr_files_changed=pr_files_changed,
            discussion_rows=discussion_rows,
        )
        if not request.source_evidence_snippets:
            rows.append(
                SourceVerificationRow(
                    row_id=row_id,
                    group_id=group.group_id,
                    finding_ids=group.finding_ids,
                    source_state=SourceState.NOT_VERIFIABLE,
                    unavailable_reasons=("missing_source_evidence",),
                    provenance={"rationale": "prior finding has no safe source references", **request.provenance},
                )
            )
            if "missing_source_evidence" not in reasons:
                reasons.append("missing_source_evidence")
            continue
        try:
            result = provider(request)
        except Exception as exc:  # noqa: BLE001 - provider failure is degraded evidence, not fatal runtime failure
            rows.append(
                SourceVerificationRow(
                    row_id=row_id,
                    group_id=group.group_id,
                    finding_ids=group.finding_ids,
                    source_state=SourceState.SOURCE_UNKNOWN,
                    inspected_source_refs=request.source_evidence_snippets,
                    unavailable_reasons=(f"provider_unavailable: {exc}",),
                    provenance={"rationale": "FindingVerifier provider failed", **request.provenance},
                )
            )
            if "provider_unavailable" not in reasons:
                reasons.append("provider_unavailable")
            continue

        result_reasons = tuple(str(reason) for reason in result.unavailable_reasons if str(reason).strip())
        if result_reasons:
            for reason in result_reasons:
                if reason not in reasons:
                    reasons.append(reason)
        provenance = {**request.provenance, **result.provenance}
        if result.rationale:
            provenance["rationale"] = result.rationale
        rows.append(
            SourceVerificationRow(
                row_id=row_id,
                group_id=group.group_id,
                finding_ids=group.finding_ids,
                source_state=result.source_state,
                current_source_citations=tuple(dict(item) for item in result.current_source_citations),
                inspected_source_refs=request.source_evidence_snippets,
                unavailable_reasons=result_reasons,
                provenance=provenance,
            )
        )

    status = ModuleStatus.DEGRADED if reasons else ModuleStatus.SUCCESS
    return SourceVerificationLedger(status=status, rows=tuple(rows), status_reasons=tuple(dict.fromkeys(reasons)))
