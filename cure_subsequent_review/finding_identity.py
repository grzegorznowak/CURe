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


def _normalized_evidence(finding: PriorFindingCandidate) -> str:
    snippets = (" ".join(snippet.lower().split()) for snippet in finding.source_evidence_snippets)
    return "\n".join(sorted(dict.fromkeys(snippet for snippet in snippets if snippet)))


def finding_fingerprint(finding: PriorFindingCandidate) -> str:
    raw = "\n".join(
        (
            finding.severity.lower(),
            finding.section.lower(),
            _normalized_title(finding.title),
            _normalized_evidence(finding),
        )
    )
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


def _local_finding_payload(finding: PriorFindingCandidate, *, origin_key: str) -> dict[str, Any]:
    return {
        "origin_key": origin_key,
        "finding_id": finding.finding_id,
        "severity": finding.severity,
        "section": finding.section,
        "title": finding.title,
        "source_evidence_snippets": list(finding.source_evidence_snippets),
        "corpus_entry_id": finding.provenance.corpus_entry_id,
        "source_type": finding.provenance.source_type,
        "artifact_path": finding.provenance.artifact_path,
        "comment_url": finding.provenance.comment_url,
        "reviewed_head": finding.reviewed_head,
    }


def _indexed_origin_items(findings: list[PriorFindingCandidate]) -> tuple[list[tuple[str, PriorFindingCandidate]], tuple[str, ...]]:
    base_keys = [_origin_key(finding) for finding in findings]
    duplicate_base_keys = {key for key in base_keys if base_keys.count(key) > 1}
    seen: dict[str, int] = defaultdict(int)
    indexed: list[tuple[str, PriorFindingCandidate]] = []
    for base_key, finding in zip(base_keys, findings, strict=True):
        if base_key in duplicate_base_keys:
            seen[base_key] += 1
            indexed.append((f"{base_key}#{seen[base_key]}", finding))
        else:
            indexed.append((base_key, finding))
    return indexed, tuple(sorted(duplicate_base_keys))


def reconcile_findings(
    *,
    findings: list[PriorFindingCandidate] | tuple[PriorFindingCandidate, ...],
    upstream_status_reasons: tuple[str, ...] = (),
) -> ReconciliationLedger:
    ordered_findings = list(findings)
    indexed_findings, duplicate_origin_keys = _indexed_origin_items(ordered_findings)
    origin_keys = [key for key, _finding in indexed_findings]
    dsu = _DisjointSet(origin_keys)

    by_fingerprint: dict[str, list[tuple[str, PriorFindingCandidate]]] = defaultdict(list)
    by_display_id: dict[str, list[tuple[str, PriorFindingCandidate]]] = defaultdict(list)
    by_origin_key = dict(indexed_findings)
    for origin_key, finding in indexed_findings:
        by_fingerprint[finding_fingerprint(finding)].append((origin_key, finding))
        by_display_id[finding.finding_id].append((origin_key, finding))

    for grouped in by_fingerprint.values():
        first_key = grouped[0][0]
        for origin_key, _finding in grouped[1:]:
            dsu.union(first_key, origin_key)

    supersedes_edges: list[dict[str, Any]] = []
    ambiguous_supersedes: list[dict[str, Any]] = []
    for source_key, finding in indexed_findings:
        for superseded_id in finding.supersedes:
            targets = by_display_id.get(superseded_id, [])
            if len(targets) == 1:
                target_key = targets[0][0]
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
                targets_by_root: dict[str, list[str]] = defaultdict(list)
                for target_key, _target in targets:
                    targets_by_root[dsu.find(target_key)].append(target_key)
                if len(targets_by_root) == 1:
                    target_root, target_origin_keys = next(iter(targets_by_root.items()))
                    dsu.union(source_key, target_root)
                    supersedes_edges.append(
                        {
                            "source_origin_key": source_key,
                            "source_display_id": finding.finding_id,
                            "target_origin_key": target_root,
                            "target_origin_keys": target_origin_keys,
                            "target_display_id": superseded_id,
                        }
                    )
                else:
                    ambiguous_supersedes.append(
                        {
                            "source_origin_key": source_key,
                            "source_display_id": finding.finding_id,
                            "target_display_id": superseded_id,
                            "target_origin_keys": [target_key for target_key, _target in targets],
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
                        "reason": "supersedes_target_not_found",
                    }
                )

    grouped_by_root: dict[str, list[tuple[str, PriorFindingCandidate]]] = defaultdict(list)
    for key, finding in by_origin_key.items():
        grouped_by_root[dsu.find(key)].append((key, finding))

    edge_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in supersedes_edges:
        edge_group[dsu.find(str(edge["source_origin_key"]))].append(edge)
    ambiguity_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for marker in ambiguous_supersedes:
        ambiguity_group[dsu.find(str(marker["source_origin_key"]))].append(marker)

    superseded_targets_by_root: dict[str, set[str]] = defaultdict(set)
    for edge in supersedes_edges:
        edge_target_keys = edge.get("target_origin_keys")
        if not isinstance(edge_target_keys, list):
            edge_target_key = edge.get("target_origin_key")
            edge_target_keys = [] if edge_target_key is None else [str(edge_target_key)]
        for edge_target_key in edge_target_keys:
            superseded_targets_by_root[dsu.find(str(edge["source_origin_key"]))].add(str(edge_target_key))

    groups: list[ReconciledFindingGroup] = []
    for index, (_root, grouped) in enumerate(sorted(grouped_by_root.items()), start=1):
        grouped.sort(key=lambda item: (_normalized_title(item[1].title), item[1].finding_id, item[0]))
        root = dsu.find(grouped[0][0])
        superseded_targets = superseded_targets_by_root.get(root, set())
        canonical_candidates = [item for item in grouped if item[0] not in superseded_targets] or grouped
        canonical = canonical_candidates[-1][1]
        supersedes: list[str] = []
        for _origin_key_value, finding in grouped:
            supersedes.extend(finding.supersedes)
        groups.append(
            ReconciledFindingGroup(
                group_id=f"G-{index:04d}",
                canonical_id=canonical.finding_id,
                finding_ids=tuple(item.finding_id for _origin_key_value, item in grouped),
                fingerprint=finding_fingerprint(canonical),
                provenance=tuple(item.provenance for _origin_key_value, item in grouped),
                supersedes=tuple(dict.fromkeys(supersedes)),
                local_findings=tuple(_local_finding_payload(item, origin_key=origin_key_value) for origin_key_value, item in grouped),
                supersedes_edges=tuple(edge_group.get(root, ())),
                ambiguous_supersedes=tuple(ambiguity_group.get(root, ())),
            )
        )
    status_reasons = list(upstream_status_reasons)
    if duplicate_origin_keys:
        status_reasons.append("duplicate_origin_keys")
    if ambiguous_supersedes:
        status_reasons.append("ambiguous_supersedes")
    if any(edge.get("status") == "target_not_found" for edge in supersedes_edges):
        status_reasons.append("supersedes_target_not_found")
    deduped_reasons = tuple(dict.fromkeys(status_reasons))
    status = ModuleStatus.DEGRADED if deduped_reasons else ModuleStatus.SUCCESS
    return ReconciliationLedger(status=status, groups=tuple(groups), status_reasons=deduped_reasons)
