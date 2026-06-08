"""Source truth verification for subsequent-review semantic ledgers.

The verifier delegates current-source assessment to an injected provider.  This
module only prepares safe prior-finding context and serializes provider output;
it does not inspect files or treat PR discussion as source proof.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from cure_subsequent_review.contracts import (
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
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FindingVerificationResult:
    source_state: SourceState
    current_source_citations: tuple[dict[str, Any], ...] = ()
    unavailable_reasons: tuple[str, ...] = ()
    rationale: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)


FindingVerifier = Callable[[FindingVerificationRequest], FindingVerificationResult]


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


def _request(group: ReconciledFindingGroup) -> FindingVerificationRequest:
    return FindingVerificationRequest(
        group_id=group.group_id,
        canonical_id=group.canonical_id,
        finding_ids=group.finding_ids,
        title=_local_finding_value(group, "title"),
        severity=_local_finding_value(group, "severity"),
        section=_local_finding_value(group, "section"),
        source_evidence_snippets=_source_refs(group),
        reviewed_heads=_reviewed_heads(group),
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


def verify_source_truth(
    *,
    reconciliation: ReconciliationLedger,
    verifier: FindingVerifier | None = None,
) -> SourceVerificationLedger:
    provider = verifier or default_finding_verifier
    rows: list[SourceVerificationRow] = []
    reasons: list[str] = list(reconciliation.status_reasons)

    for index, group in enumerate(reconciliation.groups, start=1):
        request = _request(group)
        if not request.source_evidence_snippets:
            rows.append(
                SourceVerificationRow(
                    row_id=f"SV-{index:04d}",
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
                    row_id=f"SV-{index:04d}",
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
                row_id=f"SV-{index:04d}",
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
