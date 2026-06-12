"""Disposition arbitration for subsequent-review semantic ledgers."""

from __future__ import annotations

from cure_subsequent_review.contracts import (
    DegradedFinding,
    DiscussionSignalClass,
    DiscussionSignalLedger,
    DispositionAction,
    DispositionLedger,
    DispositionRow,
    EvidencePolicy,
    ModuleStatus,
    ReconciledFindingGroup,
    ReconciliationLedger,
    SourceState,
    SourceVerificationLedger,
    SourceVerificationRow,
)


def _degraded(group: ReconciledFindingGroup, reasons: tuple[str, ...]) -> DegradedFinding:
    return DegradedFinding(
        group_id=group.group_id,
        finding_ids=group.finding_ids,
        blocking_reasons=tuple(dict.fromkeys(reason for reason in reasons if reason)),
        provenance={"reconciliation_group_id": group.group_id},
    )


def _source_is_footer_policy_approved(source: SourceVerificationRow) -> bool:
    return source.provenance.get("policy_override") == "official_footer_marker_acceptance"


def _action_for(source: SourceVerificationRow, signals: tuple) -> tuple[DispositionAction, str]:
    if _source_is_footer_policy_approved(source):
        return (
            DispositionAction.MOVE_OUT_OF_SCOPE,
            "official CURe footer acceptance is approved by FB-026 policy; generic/body-only text remains rejected",
        )
    if source.source_state is SourceState.RESOLVED_FROM_SOURCE:
        return DispositionAction.CONFIRM_RESOLVED, "current source verification confirms the prior finding is resolved"
    if source.source_state is SourceState.PARTIALLY_RESOLVED:
        return DispositionAction.REWORD_PARTIAL, "current source verification narrowed the finding; downstream packager should reword from source row"

    trusted_classes = {
        signal.signal_class
        for signal in signals
        if signal.evidence_policy is EvidencePolicy.TRUSTED
    }
    if DiscussionSignalClass.DUPLICATE_SUPERSEDED in trusted_classes:
        return DispositionAction.SUPPRESS_DUPLICATE, "trusted discussion marks this finding as duplicate/superseded"
    if trusted_classes.intersection({DiscussionSignalClass.ADDRESSED_ELSEWHERE, DiscussionSignalClass.BY_DESIGN}):
        return DispositionAction.MOVE_OUT_OF_SCOPE, "trusted discussion retargets remaining work outside this PR scope"
    return DispositionAction.RE_REPORT, "source remains open or untrusted discussion is insufficient to suppress"


def arbitrate_dispositions(
    *,
    reconciliation: ReconciliationLedger,
    source_verification: SourceVerificationLedger | None,
    discussion_signals: DiscussionSignalLedger | None,
) -> DispositionLedger:
    degraded_reasons: list[str] = []
    if source_verification is None:
        degraded_reasons.append("source_verification_missing")
    elif source_verification.status is ModuleStatus.DEGRADED:
        degraded_reasons.extend(source_verification.status_reasons or ("source_verification_degraded",))
    if discussion_signals is None:
        degraded_reasons.append("discussion_signals_missing")
    elif discussion_signals.status is ModuleStatus.DEGRADED:
        degraded_reasons.extend(discussion_signals.status_reasons or ("discussion_signals_degraded",))

    if degraded_reasons:
        return DispositionLedger(
            status=ModuleStatus.DEGRADED,
            degraded_findings=tuple(_degraded(group, tuple(degraded_reasons)) for group in reconciliation.groups),
            status_reasons=tuple(dict.fromkeys(degraded_reasons)),
        )

    assert source_verification is not None
    assert discussion_signals is not None
    source_by_group = {row.group_id: row for row in source_verification.rows}
    signals_by_group = {
        group.group_id: tuple(row for row in discussion_signals.rows if group.group_id in row.group_ids)
        for group in reconciliation.groups
    }

    dispositions: list[DispositionRow] = []
    degraded: list[DegradedFinding] = []
    status_reasons: list[str] = []
    for index, group in enumerate(reconciliation.groups, start=1):
        source = source_by_group.get(group.group_id)
        if source is None:
            reason = "source_verification_row_missing"
            degraded.append(_degraded(group, (reason,)))
            status_reasons.append(reason)
            continue
        if source.source_state in {SourceState.SOURCE_UNKNOWN, SourceState.NOT_VERIFIABLE}:
            reasons = source.unavailable_reasons or (source.source_state.value,)
            degraded.append(_degraded(group, tuple(reasons)))
            status_reasons.extend(reasons)
            continue
        signals = signals_by_group[group.group_id]
        action, rationale = _action_for(source, signals)
        dispositions.append(
            DispositionRow(
                row_id=f"DA-{index:04d}",
                group_id=group.group_id,
                finding_ids=group.finding_ids,
                action=action,
                source_verification_row_id=source.row_id,
                discussion_signal_row_ids=tuple(signal.row_id for signal in signals),
                reconciliation_group_id=group.group_id,
                provenance={
                    "rationale": rationale,
                    "source_state": source.source_state.value,
                    "discussion_signal_classes": [signal.signal_class.value for signal in signals],
                    "discussion_policies": [signal.evidence_policy.value for signal in signals],
                },
            )
        )

    status = ModuleStatus.DEGRADED if degraded else ModuleStatus.SUCCESS
    return DispositionLedger(
        status=status,
        dispositions=tuple(dispositions),
        degraded_findings=tuple(degraded),
        status_reasons=tuple(dict.fromkeys(status_reasons)),
    )
