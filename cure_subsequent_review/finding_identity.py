"""Deterministic finding identity and reconciliation."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict

from cure_subsequent_review.contracts import (
    ModuleStatus,
    PriorFindingCandidate,
    ReconciledFindingGroup,
    ReconciliationLedger,
)

_WORD_RE = re.compile(r"[^a-z0-9]+")


def _normalized_title(title: str) -> str:
    words = [word for word in _WORD_RE.sub(" ", title.lower()).split() if word not in {"still", "possible", "prior"}]
    return " ".join(words)


def finding_fingerprint(finding: PriorFindingCandidate) -> str:
    raw = "\n".join((finding.severity.lower(), finding.section.lower(), _normalized_title(finding.title)))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def reconcile_findings(*, findings: list[PriorFindingCandidate] | tuple[PriorFindingCandidate, ...]) -> ReconciliationLedger:
    by_fingerprint: dict[str, list[PriorFindingCandidate]] = defaultdict(list)
    by_id = {finding.finding_id: finding for finding in findings}
    for finding in findings:
        by_fingerprint[finding_fingerprint(finding)].append(finding)

    # Explicit supersession links should join groups even if the title drifted.
    for finding in findings:
        for superseded_id in finding.supersedes:
            superseded = by_id.get(superseded_id)
            if superseded is None:
                continue
            source_fp = finding_fingerprint(finding)
            old_fp = finding_fingerprint(superseded)
            if source_fp == old_fp:
                continue
            by_fingerprint[source_fp].extend(by_fingerprint.pop(old_fp, []))

    groups: list[ReconciledFindingGroup] = []
    for index, (fingerprint, grouped) in enumerate(sorted(by_fingerprint.items()), start=1):
        unique: dict[str, PriorFindingCandidate] = {}
        for finding in grouped:
            unique[finding.finding_id] = finding
        ordered = list(unique.values())
        ordered.sort(key=lambda item: item.finding_id)
        canonical = ordered[-1]
        supersedes: list[str] = []
        for finding in ordered:
            supersedes.extend(finding.supersedes)
        groups.append(
            ReconciledFindingGroup(
                group_id=f"G-{index:04d}",
                canonical_id=canonical.finding_id,
                finding_ids=tuple(item.finding_id for item in ordered),
                fingerprint=fingerprint,
                provenance=tuple(item.provenance for item in ordered),
                supersedes=tuple(dict.fromkeys(supersedes)),
            )
        )
    return ReconciliationLedger(status=ModuleStatus.SUCCESS, groups=tuple(groups))
