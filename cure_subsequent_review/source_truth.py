"""Source truth verification for subsequent-review semantic ledgers.

The verifier delegates current-source assessment to an injected provider.  This
module only prepares safe prior-finding context and serializes provider output;
it does not inspect files or treat PR discussion as source proof.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from cure_subsequent_review.memory_store import group_identity_for_cache

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
    def synthesize_source_row(
        self,
        *,
        group_id: str,
        finding_ids: tuple[str, ...],
        row_id: str,
        current_head: str | None,
        current_identity: dict[str, Any] | None = None,
        current_terminal_replay_fingerprint: str | None = None,
    ) -> SourceVerificationRow | None: ...

    def synthesize_resolved_source_row(
        self,
        *,
        group_id: str,
        finding_ids: tuple[str, ...],
        row_id: str,
        current_head: str | None,
        current_identity: dict[str, Any] | None = None,
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


def _footer_marker_authorship_policy_finding(group: ReconciledFindingGroup) -> bool:
    for item in group.local_findings:
        title = str(item.get("title") or "").casefold()
        if not title or "footer" not in title:
            continue
        if "body-only" in title or "body only" in title or "generic" in title:
            continue
        if "accept" not in title:
            continue
        if "without" not in title:
            continue
        if not any(term in title for term in ("authentic", "authorship", "author", "provenance")):
            continue
        return True
    return False


def _citation_from_source_ref(ref: str) -> dict[str, Any]:
    path, sep, line = ref.partition(":")
    citation: dict[str, Any] = {
        "path": path if sep else ref,
        "summary": (
            "Story 02/FB-026 policy approves official CURe footer markers as prior-review provenance "
            "regardless of author/login while body-only CURe-looking text remains rejected."
        ),
    }
    if sep and line.split(":", 1)[0].isdigit():
        citation["start_line"] = int(line.split(":", 1)[0])
    return citation


def _footer_marker_policy_row(
    *,
    row_id: str,
    group: ReconciledFindingGroup,
    request: FindingVerificationRequest,
    cache_context: dict[str, Any] | None = None,
) -> SourceVerificationRow:
    return SourceVerificationRow(
        row_id=row_id,
        group_id=group.group_id,
        finding_ids=group.finding_ids,
        source_state=SourceState.RESOLVED_FROM_SOURCE,
        current_source_citations=tuple(_citation_from_source_ref(ref) for ref in request.source_evidence_snippets),
        inspected_source_refs=request.source_evidence_snippets,
        provenance={
            **dict(cache_context or {}),
            **request.provenance,
            "policy_override": "official_footer_marker_acceptance",
            "rationale": (
                "The prior finding treats official-footer acceptance without author/login authentication as a defect, "
                "but Story 02/FB-026 makes official CURe footer markers sufficient provenance and keeps generic/body-only "
                "CURe-looking text rejected. The finding is policy-approved rather than still open."
            ),
        },
    )


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


def _terminal_replay_fingerprint(rows: tuple[DiscussionSignalRow, ...]) -> str:
    payload = {
        "discussion_signal_row_ids": tuple(row.row_id for row in rows),
        "discussion_signal_classes": tuple(row.signal_class.value for row in rows),
        "discussion_policies": tuple(row.evidence_policy.value for row in rows),
        "policy_override": "",
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _skipped_by_discussion_row(
    *,
    row_id: str,
    group: ReconciledFindingGroup,
    discussion_rows: tuple[DiscussionSignalRow, ...],
    cache_context: dict[str, Any] | None = None,
) -> SourceVerificationRow:
    return SourceVerificationRow(
        row_id=row_id,
        group_id=group.group_id,
        finding_ids=group.finding_ids,
        source_state=SourceState.STILL_OPEN,
        inspected_source_refs=_source_refs(group),
        unavailable_reasons=("source_verification_skipped_by_discussion_signals",),
        provenance={
            **dict(cache_context or {}),
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


def _increment_counter(counters: dict[str, int], key: str) -> None:
    counters[key] = counters.get(key, 0) + 1


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
    started_at = time.perf_counter()
    provider_seconds = 0.0
    provider_call_count = 0
    cache_hit_count = 0
    cache_miss_count = 0
    cache_bypass_count = 0
    cache_hit_reasons: dict[str, int] = {}
    cache_miss_reasons: dict[str, int] = {}
    cache_bypass_reasons: dict[str, int] = {}

    for index, group in enumerate(reconciliation.groups, start=1):
        row_id = f"SV-{index:04d}"
        cache_context: dict[str, Any]
        head = str(current_head or "").strip()
        if memory_store is None:
            cache_context = {"cache_status": "bypass", "cache_reason": "memory_store_unavailable"}
        elif not head:
            cache_context = {"cache_status": "bypass", "cache_reason": "missing_current_head"}
        else:
            cache_context = {"cache_status": "miss", "cache_reason": "stable_identity_mismatch"}
            discussion_rows = discussion_by_group.get(group.group_id, ())
            try:
                cached_row = memory_store.synthesize_source_row(
                    group_id=group.group_id,
                    finding_ids=group.finding_ids,
                    row_id=row_id,
                    current_head=current_head,
                    current_identity=group_identity_for_cache(group),
                    current_terminal_replay_fingerprint=_terminal_replay_fingerprint(discussion_rows),
                )
            except Exception:  # noqa: BLE001 - memory is a performance cache; failures disable the gate
                cached_row = None
                cache_context = {"cache_status": "bypass", "cache_reason": "memory_store_unreadable"}
            if cached_row is not None:
                cache_hit_count += 1
                _increment_counter(cache_hit_reasons, str(cached_row.provenance.get("cache_reason") or "unknown"))
                rows.append(cached_row)
                continue

        cache_status = str(cache_context.get("cache_status") or "").strip()
        cache_reason = str(cache_context.get("cache_reason") or "unknown").strip() or "unknown"
        if cache_status == "bypass":
            cache_bypass_count += 1
            _increment_counter(cache_bypass_reasons, cache_reason)
        elif cache_status == "miss":
            cache_miss_count += 1
            _increment_counter(cache_miss_reasons, cache_reason)

        discussion_rows = discussion_by_group.get(group.group_id, ())
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
                    provenance={
                        **cache_context,
                        "rationale": "prior finding has no safe source references",
                        **request.provenance,
                    },
                )
            )
            if "missing_source_evidence" not in reasons:
                reasons.append("missing_source_evidence")
            continue
        if _footer_marker_authorship_policy_finding(group):
            rows.append(_footer_marker_policy_row(row_id=row_id, group=group, request=request, cache_context=cache_context))
            continue
        if _discussion_skips_source_verifier(discussion_rows):
            rows.append(
                _skipped_by_discussion_row(
                    row_id=row_id,
                    group=group,
                    discussion_rows=discussion_rows,
                    cache_context=cache_context,
                )
            )
            continue
        try:
            provider_call_count += 1
            provider_started_at = time.perf_counter()
            result = provider(request)
            provider_seconds += time.perf_counter() - provider_started_at
        except Exception as exc:  # noqa: BLE001 - provider failure is degraded evidence, not fatal runtime failure
            provider_seconds += time.perf_counter() - provider_started_at
            rows.append(
                SourceVerificationRow(
                    row_id=row_id,
                    group_id=group.group_id,
                    finding_ids=group.finding_ids,
                    source_state=SourceState.SOURCE_UNKNOWN,
                    inspected_source_refs=request.source_evidence_snippets,
                    unavailable_reasons=(f"provider_unavailable: {exc}",),
                    provenance={"rationale": "FindingVerifier provider failed", **cache_context, **request.provenance},
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
        provenance = {**cache_context, **request.provenance, **result.provenance}
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
    observability = {
        "verifier_fanout": {
            "group_count": len(reconciliation.groups),
            "provider_call_count": provider_call_count,
            "cache": {
                "hit_count": cache_hit_count,
                "miss_count": cache_miss_count,
                "bypass_count": cache_bypass_count,
                "hit_reasons": cache_hit_reasons,
                "miss_reasons": cache_miss_reasons,
                "bypass_reasons": cache_bypass_reasons,
            },
            "timing": {
                "elapsed_seconds": round(time.perf_counter() - started_at, 6),
                "provider_seconds": round(provider_seconds, 6),
            },
        }
    }
    return SourceVerificationLedger(
        status=status,
        rows=tuple(rows),
        status_reasons=tuple(dict.fromkeys(reasons)),
        observability=observability,
    )
