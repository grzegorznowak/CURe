"""Prior CURe finding extraction from review artifacts/comments."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from cure_subsequent_review.contracts import (
    FindingProvenance,
    ModuleStatus,
    PriorFindingCandidate,
    PriorFindingLedger,
    PriorReviewCorpus,
    PriorReviewCorpusEntry,
)

_FINDING_HEADING_RE = re.compile(r"^#{1,6}\s+(?P<id>[A-Z]+-\d{2,4}|[AB]-\d{2})\s*[:\-–]?\s*(?P<title>.*)$", re.IGNORECASE)
_FINDING_BULLET_RE = re.compile(
    r"^-\s+\[(?P<id>[A-Z]+-\d{2,4}|[AB]-\d{2})\](?:\[(?P<severity>[^\]]+)\])?\s*(?P<title>.*)$",
    re.IGNORECASE,
)
_SECTION_HEADING_RE = re.compile(r"^##\s+(?P<section>[^#].*)$")
_INLINE_ID_RE = re.compile(r"\b(?P<id>[A-Z]+-\d{2,4}|[AB]-\d{2})\b")
_FIELD_RE = re.compile(r"^(?P<key>Severity|Section|Evidence|Source|Supersedes)\s*:\s*(?P<value>.*)$", re.IGNORECASE)
_SOURCE_REF_RE = re.compile(r"\b[\w./-]+:\d+\b")


def _stable_hint(*parts: str) -> str:
    raw = "\n".join(part.strip().lower() for part in parts if part.strip())
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _provenance(entry: PriorReviewCorpusEntry) -> FindingProvenance:
    return FindingProvenance(
        corpus_entry_id=entry.entry_id,
        source_type=entry.source_type,
        artifact_path=str(entry.artifact_path) if entry.artifact_path is not None else None,
        comment_url=str(entry.provenance.get("url") or "") or None,
        reviewed_head=entry.reviewed_head,
    )


def _candidate_from_block(
    *,
    entry: PriorReviewCorpusEntry,
    finding_id: str,
    title: str,
    block_lines: list[str],
) -> tuple[PriorFindingCandidate | None, dict[str, Any] | None]:
    fields: dict[str, list[str]] = {}
    evidence: list[str] = []
    supersedes: list[str] = []
    for line in block_lines:
        match = _FIELD_RE.match(line.strip())
        if match:
            key = match.group("key").lower()
            value = match.group("value").strip()
            fields.setdefault(key, []).append(value)
            if key in {"evidence", "source"} and value:
                evidence.append(value)
            if key == "supersedes":
                supersedes.extend(item.group("id").upper() for item in _INLINE_ID_RE.finditer(value))
            continue
        if _SOURCE_REF_RE.search(line):
            evidence.append(line.strip())
    severity = " ".join(fields.get("severity", [])).strip().lower()
    section = " ".join(fields.get("section", [])).strip() or "unknown"
    if not severity:
        return None, {"entry_id": entry.entry_id, "finding_id": finding_id, "status": "parse_degraded", "reason": "missing_severity"}
    clean_title = title.strip() or finding_id
    hints = {
        "title_hash": _stable_hint(clean_title),
        "structural_hash": _stable_hint(section, severity, clean_title),
    }
    return (
        PriorFindingCandidate(
            finding_id=finding_id.upper(),
            severity=severity,
            section=section,
            title=clean_title,
            source_evidence_snippets=tuple(dict.fromkeys(evidence)),
            reviewed_head=entry.reviewed_head,
            provenance=_provenance(entry),
            fingerprint_hints=hints,
            supersedes=tuple(dict.fromkeys(supersedes)),
        ),
        None,
    )


def _extract_from_entry(entry: PriorReviewCorpusEntry) -> tuple[list[PriorFindingCandidate], list[dict[str, Any]]]:
    findings: list[PriorFindingCandidate] = []
    statuses: list[dict[str, Any]] = []
    current_id: str | None = None
    current_title = ""
    current_section = ""
    block: list[str] = []

    def flush() -> None:
        nonlocal current_id, current_title, block
        if current_id is None:
            return
        candidate, status = _candidate_from_block(entry=entry, finding_id=current_id, title=current_title, block_lines=block)
        if candidate is not None:
            findings.append(candidate)
        if status is not None:
            statuses.append(status)
        current_id = None
        current_title = ""
        block = []

    for line in entry.body.splitlines():
        stripped = line.strip()
        section_heading = _SECTION_HEADING_RE.match(stripped)
        if section_heading:
            current_section = section_heading.group("section").strip()
        heading = _FINDING_HEADING_RE.match(stripped)
        bullet = _FINDING_BULLET_RE.match(stripped)
        if heading:
            flush()
            current_id = heading.group("id").upper()
            current_title = heading.group("title").strip()
            block = []
        elif bullet:
            flush()
            current_id = bullet.group("id").upper()
            current_title = bullet.group("title").strip()
            block = []
            severity = str(bullet.group("severity") or "").strip()
            if severity:
                block.append(f"Severity: {severity}")
            if current_section:
                block.append(f"Section: {current_section}")
        elif current_id is not None:
            block.append(line)
    flush()

    if not findings and not statuses and _INLINE_ID_RE.search(entry.body):
        statuses.append({"entry_id": entry.entry_id, "status": "parse_degraded", "reason": "finding_id_without_parseable_heading"})
    return findings, statuses


def extract_prior_findings(*, corpus: PriorReviewCorpus) -> PriorFindingLedger:
    findings: list[PriorFindingCandidate] = []
    artifact_statuses: list[dict[str, Any]] = []
    reasons: list[str] = []
    for entry in corpus.entries:
        entry_findings, entry_statuses = _extract_from_entry(entry)
        findings.extend(entry_findings)
        artifact_statuses.extend(entry_statuses)
    if artifact_statuses:
        reasons.append("parse_degraded")
    if corpus.status_reasons:
        reasons.extend(corpus.status_reasons)
    if not corpus.entries:
        reasons.append("no_prior_reviews")
    status = ModuleStatus.DEGRADED if reasons else ModuleStatus.SUCCESS
    return PriorFindingLedger(
        status=status,
        findings=tuple(findings),
        status_reasons=tuple(dict.fromkeys(reasons)),
        artifact_statuses=tuple(artifact_statuses),
    )
