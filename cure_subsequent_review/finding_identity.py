"""Deterministic finding identity and reconciliation."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any

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


def _origin_key(finding: PriorFindingCandidate) -> str:
    return f"{finding.provenance.corpus_entry_id}:{finding.finding_id}"


class _DisjointSet:
    def __init__(self, keys: list[str]) -> None:
        self.parent = {key: key for key in keys}

    def find(self, key: str) -> str:
        parent = self.parent[key]
        if parent != key:
            self.parent[key] = self.find(parent)
        return self.parent[key]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        winner, loser = sorted((left_root, right_root))
        self.parent[loser] = winner


def _local_finding_payload(finding: PriorFindingCandidate) -> dict[str, Any]:
    return {
        "origin_key": _origin_key(finding),
        "finding_id": finding.finding_id,
        "corpus_entry_id": finding.provenance.corpus_entry_id,
        "source_type": finding.provenance.source_type,
        "artifact_path": finding.provenance.artifact_path,
        "comment_url": finding.provenance.comment_url,
        "reviewed_head": finding.reviewed_head,
    }


def reconcile_findings(*, findings: list[PriorFindingCandidate] | tuple[PriorFindingCandidate, ...]) -> ReconciliationLedger:
    ordered_findings = list(findings)
    origin_keys = [_origin_key(finding) for finding in ordered_findings]
    dsu = _DisjointSet(origin_keys)

    by_fingerprint: dict[str, list[PriorFindingCandidate]] = defaultdict(list)
    by_display_id: dict[str, list[PriorFindingCandidate]] = defaultdict(list)
    by_origin_key = {_origin_key(finding): finding for finding in ordered_findings}
    for finding in ordered_findings:
        by_fingerprint[finding_fingerprint(finding)].append(finding)
        by_display_id[finding.finding_id].append(finding)

    for grouped in by_fingerprint.values():
        first = _origin_key(grouped[0])
        for finding in grouped[1:]:
            dsu.union(first, _origin_key(finding))

    supersedes_edges: list[dict[str, Any]] = []
    ambiguous_supersedes: list[dict[str, Any]] = []
    for finding in ordered_findings:
        source_key = _origin_key(finding)
        for superseded_id in finding.supersedes:
            targets = by_display_id.get(superseded_id, [])
            if len(targets) == 1:
                target_key = _origin_key(targets[0])
                dsu.union(source_key, target_key)
                supersedes_edges.append(
                    {
                        "source_origin_key": source_key,
                        "source_display_id": finding.finding_id,
                        "target_origin_key": target_key,
                        "target_display_id": superseded_id,
                    }
                )
            elif len(targets) > 1:
                ambiguous_supersedes.append(
                    {
                        "source_origin_key": source_key,
                        "source_display_id": finding.finding_id,
                        "target_display_id": superseded_id,
                        "target_origin_keys": [_origin_key(target) for target in targets],
                        "reason": "ambiguous_local_display_id",
                    }
                )
            else:
                supersedes_edges.append(
                    {
                        "source_origin_key": source_key,
                        "source_display_id": finding.finding_id,
                        "target_origin_key": None,
                        "target_display_id": superseded_id,
                        "status": "target_not_found",
                    }
                )

    grouped_by_root: dict[str, list[PriorFindingCandidate]] = defaultdict(list)
    for key, finding in by_origin_key.items():
        grouped_by_root[dsu.find(key)].append(finding)

    edge_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in supersedes_edges:
        edge_group[dsu.find(str(edge["source_origin_key"]))].append(edge)
    ambiguity_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for marker in ambiguous_supersedes:
        ambiguity_group[dsu.find(str(marker["source_origin_key"]))].append(marker)

    groups: list[ReconciledFindingGroup] = []
    for index, (_root, grouped) in enumerate(sorted(grouped_by_root.items()), start=1):
        grouped.sort(key=lambda item: (_normalized_title(item.title), item.finding_id, _origin_key(item)))
        canonical = grouped[-1]
        supersedes: list[str] = []
        for finding in grouped:
            supersedes.extend(finding.supersedes)
        root = dsu.find(_origin_key(grouped[0]))
        groups.append(
            ReconciledFindingGroup(
                group_id=f"G-{index:04d}",
                canonical_id=canonical.finding_id,
                finding_ids=tuple(item.finding_id for item in grouped),
                fingerprint=finding_fingerprint(canonical),
                provenance=tuple(item.provenance for item in grouped),
                supersedes=tuple(dict.fromkeys(supersedes)),
                local_findings=tuple(_local_finding_payload(item) for item in grouped),
                supersedes_edges=tuple(edge_group.get(root, ())),
                ambiguous_supersedes=tuple(ambiguity_group.get(root, ())),
            )
        )
    return ReconciliationLedger(status=ModuleStatus.SUCCESS, groups=tuple(groups))
