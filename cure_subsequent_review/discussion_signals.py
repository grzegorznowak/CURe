"""Discussion signal normalization for subsequent-review semantics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from cure_subsequent_review.contracts import (
    DiscussionArtifact,
    DiscussionEvent,
    DiscussionSignalClass,
    DiscussionSignalLedger,
    DiscussionSignalRow,
    EvidencePolicy,
    ModuleStatus,
    ReconciledFindingGroup,
    ReconciliationLedger,
)


@dataclass(frozen=True)
class DiscussionLinkResult:
    group_ids: tuple[str, ...] = ()
    signal_class: DiscussionSignalClass | None = None
    rationale: str = ""


DiscussionLinker = Callable[[DiscussionEvent, tuple[ReconciledFindingGroup, ...]], DiscussionLinkResult]


def _classify_signal(event: DiscussionEvent) -> DiscussionSignalClass:
    body = event.body.lower()
    if event.thread_state == "resolved":
        return DiscussionSignalClass.RESOLVED_THREAD_HINT
    if event.thread_state == "unresolved":
        return DiscussionSignalClass.UNRESOLVED_THREAD_HINT
    if "authority conflict" in body or "conflict" in body:
        return DiscussionSignalClass.AUTHORITY_CONFLICT
    if "duplicate" in body or "superseded" in body or "supersedes" in body:
        return DiscussionSignalClass.DUPLICATE_SUPERSEDED
    if "external" in body or "elsewhere" in body or "ticket" in body or "follow-up" in body:
        return DiscussionSignalClass.ADDRESSED_ELSEWHERE
    if "by design" in body or "product scope" in body or "out of scope" in body:
        return DiscussionSignalClass.BY_DESIGN
    if "fixed" in body or "resolved" in body or "addressed" in body:
        return DiscussionSignalClass.DEVELOPER_CLAIM_FIXED
    return DiscussionSignalClass.PUSHBACK


def _text_link_groups(event: DiscussionEvent, groups: tuple[ReconciledFindingGroup, ...]) -> tuple[str, ...]:
    body = event.body.lower()
    linked: list[str] = []
    for group in groups:
        ids = {group.group_id.lower(), group.canonical_id.lower(), *(finding_id.lower() for finding_id in group.finding_ids)}
        titles = {str(item.get("title") or "").lower() for item in group.local_findings}
        if any(token and token in body for token in ids) or any(title and title in body for title in titles):
            linked.append(group.group_id)
            continue
        if event.path:
            for item in group.local_findings:
                snippets = item.get("source_evidence_snippets", ())
                if isinstance(snippets, list | tuple) and any(str(event.path) in str(snippet) for snippet in snippets):
                    linked.append(group.group_id)
                    break
    return tuple(dict.fromkeys(linked))


def _finding_ids_for_groups(groups: tuple[ReconciledFindingGroup, ...], group_ids: tuple[str, ...]) -> tuple[str, ...]:
    ids: list[str] = []
    wanted = set(group_ids)
    for group in groups:
        if group.group_id in wanted:
            ids.extend(group.finding_ids)
    return tuple(dict.fromkeys(ids))


def _authority(event: DiscussionEvent, signal_class: DiscussionSignalClass) -> tuple[str, EvidencePolicy, tuple[str, ...]]:
    author = (event.author or "").lower()
    if not author:
        return "unknown", EvidencePolicy.UNTRUSTED, ("unknown_authority",)
    if "security" in author:
        return "security", EvidencePolicy.TRUSTED, ()
    if "product" in author or "owner" in author:
        return "product", EvidencePolicy.TRUSTED, ()
    if "maintainer" in author:
        return "maintainer", EvidencePolicy.TRUSTED, ()
    if "bot" in author:
        return "automation", EvidencePolicy.UNTRUSTED, ("automation_authority_untrusted",)
    if signal_class in {DiscussionSignalClass.DEVELOPER_CLAIM_FIXED, DiscussionSignalClass.RESOLVED_THREAD_HINT}:
        return "author", EvidencePolicy.UNTRUSTED, ("claim_not_source_proof",)
    return "participant", EvidencePolicy.UNTRUSTED, ("insufficient_authority",)


def resolve_discussion_signals(
    *,
    discussion: DiscussionArtifact,
    reconciliation: ReconciliationLedger,
    linker: DiscussionLinker | None = None,
) -> DiscussionSignalLedger:
    rows: list[DiscussionSignalRow] = []
    status_reasons: list[str] = list(discussion.status_reasons)
    groups = reconciliation.groups

    for index, event in enumerate(discussion.events, start=1):
        link_result = linker(event, groups) if linker is not None else DiscussionLinkResult()
        signal_class = link_result.signal_class or _classify_signal(event)
        linked_groups = link_result.group_ids if linker is not None else _text_link_groups(event, groups)
        authority, policy, reasons = _authority(event, signal_class)
        if link_result.rationale.startswith("llm_linker_malformed"):
            status_reasons.append("llm_discussion_linker_malformed")
        provenance: dict[str, Any] = {
            "event_kind": event.kind,
            "event_url": event.url,
            "thread_state": event.thread_state,
        }
        if link_result.rationale:
            provenance["rationale"] = link_result.rationale
        rows.append(
            DiscussionSignalRow(
                row_id=f"DS-{index:04d}",
                event_id=event.event_id or f"event-{index}",
                group_ids=linked_groups,
                finding_ids=_finding_ids_for_groups(groups, linked_groups),
                signal_class=signal_class,
                evidence_policy=policy,
                authority=authority,
                reasons=reasons,
                provenance=provenance,
            )
        )

    status = ModuleStatus.DEGRADED if status_reasons else ModuleStatus.SUCCESS
    return DiscussionSignalLedger(status=status, rows=tuple(rows), status_reasons=tuple(dict.fromkeys(status_reasons)))
