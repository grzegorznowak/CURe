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
_SOURCE_REF_RE = re.compile(r"\b[\w./-]+:\d+(?:-\d+)?\b")
_GENERATED_SEVERITY_RE = re.compile(r"<summary>.*?<b>(?P<severity>[^<]+)</b>\s+severity", re.IGNORECASE)
_GENERATED_SOURCES_RE = re.compile(r"\bSources:\s*(?P<sources>.*)$", re.IGNORECASE)


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


def _status_provenance(entry: PriorReviewCorpusEntry) -> dict[str, Any]:
    return {
        "entry_id": entry.entry_id,
        "source_type": entry.source_type,
        "artifact_path": str(entry.artifact_path) if entry.artifact_path is not None else None,
        "comment_url": str(entry.provenance.get("url") or "") or None,
        "reviewed_head": entry.reviewed_head,
    }


def _candidate_from_block(
    *,
    entry: PriorReviewCorpusEntry,
    finding_id: str,
    title: str,
    block_lines: list[str],
    default_section: str | None = None,
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
        if _source_refs(line):
            evidence.append(line.strip())
    severity = " ".join(fields.get("severity", [])).strip().lower()
    section = " ".join(fields.get("section", [])).strip() or (default_section or "unknown")
    if not severity:
        return None, {
            **_status_provenance(entry),
            "finding_id": finding_id,
            "status": "parse_degraded",
            "reason": "missing_severity",
            "section": section,
            "title": title.strip() or finding_id,
            "source_evidence_snippets": list(dict.fromkeys(evidence)),
        }
    if not evidence:
        return None, {
            **_status_provenance(entry),
            "finding_id": finding_id,
            "status": "parse_degraded",
            "reason": "missing_evidence",
            "section": section,
            "title": title.strip() or finding_id,
            "source_evidence_snippets": [],
        }
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


def _looks_like_source_ref(ref: str, *, allow_extensionless_root_path: bool = False) -> bool:
    location = ref.rsplit(":", 1)[0]
    if "/" in location or "." in location:
        return True
    if not allow_extensionless_root_path:
        return False
    return location.upper() == location and bool(re.search(r"[A-Z]", location))


def _source_refs(text: str, *, allow_extensionless_root_paths: bool = False) -> list[str]:
    refs = [match.group(0).strip("`.,") for match in _SOURCE_REF_RE.finditer(text)]
    return [ref for ref in refs if _looks_like_source_ref(ref, allow_extensionless_root_path=allow_extensionless_root_paths)]


def _strip_generated_sources(title: str) -> tuple[str, list[str]]:
    match = _GENERATED_SOURCES_RE.search(title)
    if not match:
        return title.strip(), []
    refs = _source_refs(match.group("sources"), allow_extensionless_root_paths=True)
    return title[: match.start()].strip().rstrip(".:- "), refs


def _extract_generated_review_issues(entry: PriorReviewCorpusEntry) -> tuple[list[PriorFindingCandidate], list[dict[str, Any]]]:
    findings: list[PriorFindingCandidate] = []
    statuses: list[dict[str, Any]] = []
    current_section = "unknown"
    in_scope_issues = False
    current_title = ""
    current_block: list[str] = []
    current_sources: list[str] = []
    saw_clean_none = False
    saw_legacy_finding_bullet = False

    def status_payload(*, title: str, reason: str, evidence: list[str]) -> dict[str, Any]:
        return {
            **_status_provenance(entry),
            "status": "parse_degraded",
            "reason": reason,
            "title": title,
            "section": current_section,
            "source_evidence_snippets": list(dict.fromkeys(evidence)),
        }

    def flush() -> None:
        nonlocal current_title, current_block, current_sources
        if not current_title:
            return
        severity = ""
        evidence = list(current_sources)
        for line in current_block:
            severity_match = _GENERATED_SEVERITY_RE.search(line)
            if severity_match and not severity:
                severity = severity_match.group("severity").strip().lower()
            evidence.extend(
                _source_refs(line, allow_extensionless_root_paths=_GENERATED_SOURCES_RE.search(line) is not None)
            )
        if severity and evidence:
            index = len(findings) + 1
            block = [f"Severity: {severity}", f"Section: {current_section}"]
            block.extend(f"Evidence: {item}" for item in dict.fromkeys(evidence))
            candidate, _status = _candidate_from_block(
                entry=entry,
                finding_id=f"CURE-{index:03d}",
                title=current_title,
                block_lines=block,
            )
            if candidate is not None:
                findings.append(candidate)
        elif severity:
            statuses.append(status_payload(title=current_title, reason="missing_generated_sources", evidence=evidence))
        else:
            statuses.append(status_payload(title=current_title, reason="missing_generated_severity", evidence=evidence))
        current_title = ""
        current_block = []
        current_sources = []

    for line in entry.body.splitlines():
        stripped = line.strip()
        h2 = _SECTION_HEADING_RE.match(stripped)
        if h2:
            flush()
            current_section = h2.group("section").strip()
            in_scope_issues = False
            continue
        if stripped.startswith("### "):
            flush()
            in_scope_issues = stripped.lower().startswith("### in scope issues")
            continue
        if not in_scope_issues:
            continue
        if line.startswith("- "):
            flush()
            bullet_text = stripped[2:].strip()
            if _FINDING_BULLET_RE.match(stripped):
                saw_legacy_finding_bullet = True
                current_title = ""
                current_block = []
                current_sources = []
                continue
            if bullet_text.lower().rstrip(".") == "none":
                saw_clean_none = True
                current_title = ""
                current_block = []
                current_sources = []
                continue
            current_title, current_sources = _strip_generated_sources(bullet_text)
            current_block = [line]
        elif current_title:
            current_block.append(line)
    flush()

    if (
        not findings
        and not statuses
        and not saw_clean_none
        and not saw_legacy_finding_bullet
        and ("### In Scope Issues" in entry.body or "**Verdict**: REQUEST CHANGES" in entry.body)
    ):
        statuses.append(
            {
                **_status_provenance(entry),
                "status": "parse_degraded",
                "reason": "generated_review_without_parseable_findings",
            }
        )
    return findings, statuses


def _extract_from_entry(entry: PriorReviewCorpusEntry) -> tuple[list[PriorFindingCandidate], list[dict[str, Any]]]:
    findings: list[PriorFindingCandidate] = []
    statuses: list[dict[str, Any]] = []
    current_id: str | None = None
    current_title = ""
    current_section = ""
    current_default_section = ""
    block: list[str] = []

    def flush() -> None:
        nonlocal current_id, current_title, current_default_section, block
        if current_id is None:
            return
        candidate, status = _candidate_from_block(
            entry=entry,
            finding_id=current_id,
            title=current_title,
            block_lines=block,
            default_section=current_default_section or None,
        )
        if candidate is not None:
            findings.append(candidate)
        if status is not None:
            statuses.append(status)
        current_id = None
        current_title = ""
        current_default_section = ""
        block = []

    for line in entry.body.splitlines():
        stripped = line.strip()
        heading = _FINDING_HEADING_RE.match(stripped)
        bullet = _FINDING_BULLET_RE.match(stripped)
        if heading:
            flush()
            current_id = heading.group("id").upper()
            current_title = heading.group("title").strip()
            current_default_section = current_section
            block = []
        elif bullet:
            flush()
            current_id = bullet.group("id").upper()
            current_title = bullet.group("title").strip()
            current_default_section = current_section
            block = []
            severity = str(bullet.group("severity") or "").strip()
            if severity:
                block.append(f"Severity: {severity}")
        else:
            section_heading = _SECTION_HEADING_RE.match(stripped)
            if section_heading:
                current_section = section_heading.group("section").strip()
            if current_id is not None:
                block.append(line)
    flush()

    if not findings or "### In Scope Issues" in entry.body:
        generated_findings, generated_statuses = _extract_generated_review_issues(entry)
        findings.extend(generated_findings)
        statuses.extend(generated_statuses)
    if not findings and not statuses and _INLINE_ID_RE.search(entry.body):
        statuses.append(
            {
                **_status_provenance(entry),
                "status": "parse_degraded",
                "reason": "finding_id_without_parseable_heading",
            }
        )
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
