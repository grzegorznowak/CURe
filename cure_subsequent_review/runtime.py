"""Runtime-phase orchestration helpers for subsequent PR review.

The Story 04 runtime orchestrator owns seams that sit outside the Story 01-03
semantic pipeline.  This module intentionally keeps post-review memory updates
small and auditable: completed semantic ledgers are read from the sandbox and
copied into the shared per-PR memory cache after the review run completes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Any

from cure_subsequent_review.contracts import (
    DiscussionSignalClass,
    DispositionAction,
    DispositionLedger,
    DispositionRow,
    EvidencePolicy,
    ModuleRunRecord,
    ModuleStatus,
    SourceState,
    SourceVerificationLedger,
    SourceVerificationRow,
    SubsequentReviewModule,
)
from cure_subsequent_review.memory_store import ReviewMemoryStore

SOURCE_VERIFICATION_ARTIFACT = "source_verification.json"
DISPOSITION_LEDGER_ARTIFACT = "disposition_ledger.json"
REVIEW_CONTEXT_PACKAGE_ARTIFACT = "review_context_package.json"
SUBSEQUENT_REVIEW_CONTEXT_ARTIFACT = "subsequent_review_context.md"
GOVERNOR_BRIEF_ARTIFACT = "governor_brief.md"
REPORT_GOVERNOR_RESULT_ARTIFACT = "report_governor_result.json"
REPORT_GOVERNOR_AWARENESS_QUESTION = "Does this review demonstrate awareness of the prior review context?"
ALLOWED_DISPOSITION_MAP_STATUSES = (
    "confirmed-resolved",
    "carried-forward/re_report",
    "degraded",
    "out-of-scope",
    "contradicted-with-evidence",
)
ISSUE_HISTORY_HEADING = "### Prior Review Issue History (required final output)"
INTERNAL_DA_COVERAGE_HEADING = "### Internal DA coverage (audit only)"


@dataclass(frozen=True)
class ReviewRuntimePrePromptResult:
    prior_review_brief: str
    context_package_path: Path
    context_markdown_path: Path
    governor_brief_path: Path | None
    records: tuple[ModuleRunRecord, ...]


def review_memory_root_from_sandbox_root(sandbox_root: Path) -> Path:
    """Return the shared per-PR memory root adjacent to CURe sandboxes.

    Defaults resolve to ``~/.local/state/cure/sandboxes`` and therefore place
    memory under ``~/.local/state/cure/pr``.  Tests using temporary sandbox
    roots get the same lifecycle-independent sibling layout.
    """

    return sandbox_root.parent / "pr"


def _load_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


def _dict_tuple(value: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, dict))


def _dict_value(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _write_json_object(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _artifact_state(path: Path) -> tuple[str, dict[str, Any] | None]:
    if not path.exists():
        return "missing", None
    payload = _load_json_object(path)
    if payload is None:
        return "degraded", None
    raw_status = str(payload.get("status") or "").strip().lower()
    status = "degraded" if raw_status == ModuleStatus.DEGRADED.value else "present"
    return status, payload


def _count_for_artifact(name: str, payload: dict[str, Any] | None) -> int:
    if payload is None:
        return 0
    key_by_name = {
        "pr_discussion": "events",
        "prior_review_corpus": "entries",
        "prior_findings": "findings",
        "reconciled_findings": "groups",
        "source_verification": "rows",
        "discussion_signals": "rows",
        "disposition_ledger": "dispositions",
    }
    key = key_by_name.get(name)
    if key is None:
        return 0
    value = payload.get(key)
    return len(value) if isinstance(value, list) else 0


def _manifest_module_statuses(manifest_payload: dict[str, Any] | None) -> dict[str, str]:
    modules = (manifest_payload or {}).get("modules")
    if not isinstance(modules, dict):
        return {}
    statuses: dict[str, str] = {}
    for module, record in modules.items():
        if isinstance(record, dict):
            statuses[str(module)] = str(record.get("status") or "unknown")
    return statuses


def _memory_artifact_status(memory_store_path: Path | None) -> dict[str, Any]:
    if memory_store_path is None:
        return {"path": None, "status": "missing", "count": 0}
    status, payload = _artifact_state(memory_store_path)
    findings = (payload or {}).get("findings")
    count = len(findings) if isinstance(findings, dict) else 0
    return {"path": str(memory_store_path), "status": status, "count": count}


def _has_official_footer(body: str) -> bool:
    start = body.find("<!-- CURE_REVIEW_FOOTER_START -->")
    end = body.find("<!-- CURE_REVIEW_FOOTER_END -->")
    return start >= 0 and end > start


def _footer_marker_policy_summary(corpus_payload: dict[str, Any] | None) -> dict[str, Any]:
    entries = (corpus_payload or {}).get("entries")
    ignored = (corpus_payload or {}).get("ignored_pr_comments")
    remote_entries = [entry for entry in entries if isinstance(entry, dict) and str(entry.get("source_type") or "") in {"pr_comment", "pr_review"}] if isinstance(entries, list) else []
    official_footer_remote_entries = sum(1 for entry in remote_entries if _has_official_footer(str(entry.get("body") or "")))
    body_only_rejected_comments = sum(
        1
        for item in ignored
        if isinstance(item, dict) and str(item.get("reason") or "") == "cure_authorship_not_established"
    ) if isinstance(ignored, list) else 0
    return {
        "policy": "official_footer_sufficient_regardless_of_author_login_body_only_rejected",
        "official_footer_remote_entries": official_footer_remote_entries,
        "body_only_rejected_comments": body_only_rejected_comments,
        "summary": (
            "Official CURe footer markers are accepted as prior-review provenance regardless of author/login; "
            "generic or body-only CURe-looking text remains rejected."
        ),
    }


def build_review_context_package(*, artifact_dir: Path, memory_store_path: Path | None = None) -> dict[str, Any]:
    """Build the module-9 audit package from available subsequent-review artifacts."""

    artifact_specs = {
        "decision": "decision.json",
        "pr_discussion": "pr_discussion.json",
        "prior_review_corpus": "prior_review_corpus.json",
        "prior_findings": "prior_findings.json",
        "reconciled_findings": "reconciled_findings.json",
        "source_verification": SOURCE_VERIFICATION_ARTIFACT,
        "discussion_signals": "discussion_signals.json",
        "disposition_ledger": DISPOSITION_LEDGER_ARTIFACT,
        "run_manifest": "run_manifest.json",
    }
    artifacts: dict[str, dict[str, Any]] = {}
    payloads: dict[str, dict[str, Any] | None] = {}
    for name, filename in artifact_specs.items():
        path = artifact_dir / filename
        status, payload = _artifact_state(path)
        payloads[name] = payload
        artifacts[name] = {
            "path": str(path),
            "status": status,
            "count": _count_for_artifact(name, payload),
        }
        if isinstance(payload, dict) and payload.get("status_reasons"):
            artifacts[name]["status_reasons"] = list(payload.get("status_reasons") or [])
    artifacts["cure_memory"] = _memory_artifact_status(memory_store_path)

    decision_payload = payloads.get("decision") or {}
    discussion_payload = payloads.get("pr_discussion") or {}
    decision_counts = decision_payload.get("signal_counts") if isinstance(decision_payload, dict) else {}
    decision_remote_events = int((decision_counts or {}).get("remote_events") or 0) if isinstance(decision_counts, dict) else 0
    discussion_events = discussion_payload.get("events") if isinstance(discussion_payload, dict) else []
    discussion_event_count = len(discussion_events) if isinstance(discussion_events, list) else 0

    return {
        "schema_version": 1,
        "artifact_dir": str(artifact_dir),
        "artifacts": artifacts,
        "module_statuses": _manifest_module_statuses(payloads.get("run_manifest")),
        "decision": {
            "enabled": bool(decision_payload.get("enabled")) if isinstance(decision_payload, dict) else False,
            "mode": str(decision_payload.get("mode") or "unknown") if isinstance(decision_payload, dict) else "unknown",
            "reasons": list(decision_payload.get("reasons") or []) if isinstance(decision_payload, dict) else [],
            "signal_counts": dict(decision_counts or {}) if isinstance(decision_counts, dict) else {},
        },
        "fb_010": {
            "decision_remote_events": decision_remote_events,
            "pr_discussion_events": discussion_event_count,
            "discussion_event_count_matches_decision": decision_remote_events == discussion_event_count,
        },
        "footer_marker_policy": _footer_marker_policy_summary(payloads.get("prior_review_corpus")),
    }


def _write_context_markdown(*, path: Path, package: dict[str, Any]) -> None:
    lines = ["# Subsequent Review Context", "", "## Artifacts"]
    raw_artifacts = package.get("artifacts")
    artifacts: dict[str, Any] = raw_artifacts if isinstance(raw_artifacts, dict) else {}
    for name in sorted(artifacts):
        artifact = artifacts[name]
        if not isinstance(artifact, dict):
            continue
        lines.append(
            f"- {name}: {artifact.get('status', 'unknown')} "
            f"({artifact.get('count', 0)}) — `{artifact.get('path', '')}`"
        )
    lines.extend(["", "## Module Statuses"])
    raw_statuses = package.get("module_statuses")
    statuses: dict[str, Any] = raw_statuses if isinstance(raw_statuses, dict) else {}
    if statuses:
        for module in sorted(statuses):
            lines.append(f"- {module}: {statuses[module]}")
    else:
        lines.append("- None recorded.")
    raw_footer_policy = package.get("footer_marker_policy")
    footer_policy: dict[str, Any] = raw_footer_policy if isinstance(raw_footer_policy, dict) else {}
    lines.extend(
        [
            "",
            "## Footer marker policy",
            f"- {footer_policy.get('summary', 'Official CURe footer markers identify prior CURe reviews; body-only markers are rejected.')}",
            f"- Official-footer remote entries: {footer_policy.get('official_footer_remote_entries', 0)}",
            f"- Body-only/generic rejected comments: {footer_policy.get('body_only_rejected_comments', 0)}",
            "",
            "## FB-010 discussion evidence reuse",
            f"- Decision remote events: {package.get('fb_010', {}).get('decision_remote_events', 0)}",
            f"- PR discussion events: {package.get('fb_010', {}).get('pr_discussion_events', 0)}",
            f"- Event counts match: {package.get('fb_010', {}).get('discussion_event_count_matches_decision', False)}",
            "",
            f"Package artifact: `{path.parent / REVIEW_CONTEXT_PACKAGE_ARTIFACT}`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _severity_label(severity: str) -> str:
    normalized = severity.strip().lower()
    emoji_by_severity = {
        "critical": "🔴 CRITICAL",
        "high": "🔴 HIGH",
        "medium": "🟡 MEDIUM",
        "low": "🔵 LOW",
        "info": "⚪ INFO",
        "informational": "⚪ INFO",
    }
    return emoji_by_severity.get(normalized, normalized.upper() if normalized else "UNKNOWN")


def _finding_metadata_by_id(payload: dict[str, Any] | None) -> dict[str, dict[str, str]]:
    findings = (payload or {}).get("findings")
    if not isinstance(findings, list):
        return {}
    out: dict[str, dict[str, str]] = {}
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        finding_id = str(finding.get("finding_id") or "").strip()
        if finding_id:
            out[finding_id] = {
                "severity": str(finding.get("severity") or "").strip(),
                "title": str(finding.get("title") or "").strip(),
            }
    return out


def _rows_by_id(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    rows = (payload or {}).get("rows")
    if not isinstance(rows, list):
        return {}
    return {str(row.get("row_id") or "").strip(): dict(row) for row in rows if isinstance(row, dict)}


def _strict_governor_validate_citation_ledgers(*, artifact_dir: Path, disposition_payload: dict[str, Any]) -> None:
    """Fail closed when strict governor context cannot cite required ledgers."""

    raw_dispositions = disposition_payload.get("dispositions")
    dispositions = [dict(row) for row in raw_dispositions if isinstance(row, dict)] if isinstance(raw_dispositions, list) else []
    source_row_ids = {str(row.get("source_verification_row_id") or "").strip() for row in dispositions}
    source_row_ids.discard("")
    discussion_row_ids = {row_id for row in dispositions for row_id in _string_tuple(row.get("discussion_signal_row_ids"))}

    if source_row_ids:
        source_path = artifact_dir / SOURCE_VERIFICATION_ARTIFACT
        if not source_path.is_file():
            raise ValueError(f"missing required subsequent-review artifact: {SOURCE_VERIFICATION_ARTIFACT}")
        source_payload = _load_json_object(source_path)
        if source_payload is None:
            raise ValueError(f"malformed required subsequent-review artifact: {SOURCE_VERIFICATION_ARTIFACT}")
        source_rows = _rows_by_id(source_payload)
        missing_source_rows = tuple(sorted(row_id for row_id in source_row_ids if row_id not in source_rows))
        if missing_source_rows:
            missing = ", ".join(missing_source_rows)
            raise ValueError(f"missing required source citation row(s) in {SOURCE_VERIFICATION_ARTIFACT}: {missing}")

    if discussion_row_ids:
        discussion_path = artifact_dir / "discussion_signals.json"
        if not discussion_path.is_file():
            raise ValueError("missing required subsequent-review artifact: discussion_signals.json")
        discussion_payload = _load_json_object(discussion_path)
        if discussion_payload is None:
            raise ValueError("malformed required subsequent-review artifact: discussion_signals.json")
        discussion_rows = _rows_by_id(discussion_payload)
        missing_discussion_rows = tuple(sorted(row_id for row_id in discussion_row_ids if row_id not in discussion_rows))
        if missing_discussion_rows:
            missing = ", ".join(missing_discussion_rows)
            raise ValueError(f"missing required discussion citation row(s) in discussion_signals.json: {missing}")


def _citation_text(row: dict[str, Any] | None) -> str:
    citations = (row or {}).get("current_source_citations")
    if not isinstance(citations, list) or not citations:
        return "source citation unavailable"
    parts = []
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        path = str(citation.get("path") or "").strip()
        line = citation.get("start_line") or citation.get("line")
        summary = str(citation.get("summary") or "").strip()
        location = f"{path}:{line}" if path and line else path or "unknown source"
        parts.append(f"{location} ({summary})" if summary else location)
    return "; ".join(parts) if parts else "source citation unavailable"


def _discussion_text(row_ids: tuple[str, ...], discussion_rows: dict[str, dict[str, Any]]) -> tuple[str, str | None]:
    if not row_ids:
        return "none", None
    parts: list[str] = []
    caveats: list[str] = []
    for row_id in row_ids:
        row = discussion_rows.get(row_id, {})
        signal = str(row.get("signal_class") or "unknown")
        policy = str(row.get("evidence_policy") or "unknown")
        authority = str(row.get("authority") or "unknown")
        parts.append(f"{row_id} {policy}/{signal} by {authority}")
        if (
            policy != EvidencePolicy.TRUSTED.value
            or authority in {"", "unknown", "developer"}
            or signal == DiscussionSignalClass.AUTHORITY_CONFLICT.value
        ):
            caveats.append(f"{row_id} has {policy} discussion authority ({authority})")
    return "; ".join(parts), "; ".join(caveats) if caveats else None


def _disposition_map_status_for_action(action: str) -> str:
    return {
        DispositionAction.CONFIRM_RESOLVED.value: "confirmed-resolved",
        DispositionAction.RE_REPORT.value: "carried-forward/re_report",
        DispositionAction.REWORD_PARTIAL.value: "carried-forward/re_report",
        DispositionAction.MOVE_OUT_OF_SCOPE.value: "out-of-scope",
        DispositionAction.SUPPRESS_DUPLICATE.value: "out-of-scope",
    }.get(action, "degraded")


def _disposition_map_rows(dispositions: list[Any]) -> dict[str, str]:
    rows: dict[str, str] = {}
    for raw in dispositions:
        if not isinstance(raw, dict):
            continue
        row_id = str(raw.get("row_id") or "").strip()
        if row_id:
            rows[row_id] = _disposition_map_status_for_action(str(raw.get("action") or ""))
    return rows


def _primary_finding_for_disposition(raw: dict[str, Any]) -> str:
    finding_ids = tuple(str(item) for item in raw.get("finding_ids") or [] if str(item).strip())
    return finding_ids[0] if finding_ids else str(raw.get("group_id") or "unknown")


def _issue_title_for_disposition(raw: dict[str, Any], finding_meta: dict[str, dict[str, str]]) -> str:
    primary_finding = _primary_finding_for_disposition(raw)
    metadata = finding_meta.get(primary_finding, {})
    return metadata.get("title", "") or primary_finding


def _issue_status_for_cluster(statuses: list[str]) -> str:
    priority = {
        "carried-forward/re_report": 0,
        "degraded": 1,
        "contradicted-with-evidence": 2,
        "out-of-scope": 3,
        "confirmed-resolved": 4,
    }
    return min(statuses, key=lambda status: priority.get(status, 99)) if statuses else "degraded"


def _issue_history_reason(status: str) -> str:
    return {
        "confirmed-resolved": "confirmed resolved in the current source or policy context",
        "carried-forward/re_report": "carried forward because the prior issue remains open or needs re-reporting",
        "degraded": "current status is uncertain because required evidence was degraded or unavailable",
        "out-of-scope": "resolved, suppressed, or moved out of scope for this review",
        "contradicted-with-evidence": "final review cites evidence contradicting the expected prior disposition",
    }.get(status, "current status is uncertain")


def _issue_history_rows(dispositions: list[Any], finding_meta: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    clusters: dict[str, dict[str, Any]] = {}
    for raw in dispositions:
        if not isinstance(raw, dict):
            continue
        row_id = str(raw.get("row_id") or "").strip()
        if not row_id:
            continue
        title = _issue_title_for_disposition(raw, finding_meta)
        key = re.sub(r"\s+", " ", title.strip().lower()) or row_id.lower()
        status = _disposition_map_status_for_action(str(raw.get("action") or ""))
        cluster = clusters.setdefault(key, {"title": title, "statuses": [], "row_ids": []})
        cluster["statuses"].append(status)
        cluster["row_ids"].append(row_id)
    rows: list[dict[str, Any]] = []
    for cluster in clusters.values():
        row_ids = sorted(str(row_id) for row_id in cluster["row_ids"])
        status = _issue_status_for_cluster([str(status) for status in cluster["statuses"]])
        rows.append(
            {
                "title": str(cluster["title"]),
                "status": status,
                "reason": _issue_history_reason(status),
                "row_ids": row_ids,
            }
        )
    return sorted(rows, key=lambda row: str(row["title"]).lower())


def _footer_policy_brief(corpus_payload: dict[str, Any] | None) -> list[str]:
    summary = _footer_marker_policy_summary(corpus_payload)
    if not summary["official_footer_remote_entries"] and not summary["body_only_rejected_comments"]:
        return []
    return [
        "### Footer Marker Policy",
        (
            "- Story 02/FB-026 policy: official CURe footer markers are accepted as prior-review provenance "
            "regardless of author/login; generic/body-only CURe-looking text remains rejected. "
            f"Accepted official-footer remote entries: {summary['official_footer_remote_entries']}; "
            f"body-only/generic rejected comments: {summary['body_only_rejected_comments']}."
        ),
    ]


def build_governor_brief(*, artifact_dir: Path) -> str:
    """Build the module-10 pre-review brief from disposition/source ledgers."""

    disposition_payload = _load_json_object(artifact_dir / DISPOSITION_LEDGER_ARTIFACT)
    corpus_payload = _load_json_object(artifact_dir / "prior_review_corpus.json")
    if disposition_payload is None:
        return "\n".join(_footer_policy_brief(corpus_payload))
    source_rows = _rows_by_id(_load_json_object(artifact_dir / SOURCE_VERIFICATION_ARTIFACT))
    discussion_rows = _rows_by_id(_load_json_object(artifact_dir / "discussion_signals.json"))
    finding_meta = _finding_metadata_by_id(_load_json_object(artifact_dir / "prior_findings.json"))
    dispositions = disposition_payload.get("dispositions")
    raw_degraded = disposition_payload.get("degraded_findings")
    sections: dict[str, list[str]] = {
        "### Confirmed Fixed": [],
        "### Still Open": [],
        "### Suppressed Duplicates": [],
        "### Out of Scope": [],
        "### Degraded": [],
    }
    action_section = {
        DispositionAction.CONFIRM_RESOLVED.value: "### Confirmed Fixed",
        DispositionAction.RE_REPORT.value: "### Still Open",
        DispositionAction.REWORD_PARTIAL.value: "### Still Open",
        DispositionAction.SUPPRESS_DUPLICATE.value: "### Suppressed Duplicates",
        DispositionAction.MOVE_OUT_OF_SCOPE.value: "### Out of Scope",
    }
    if isinstance(dispositions, list):
        for raw in dispositions:
            if not isinstance(raw, dict):
                continue
            row_id = str(raw.get("row_id") or "").strip()
            action = str(raw.get("action") or "").strip()
            heading = action_section.get(action)
            if not heading:
                continue
            finding_ids = tuple(str(item) for item in raw.get("finding_ids") or [] if str(item).strip())
            primary_finding = finding_ids[0] if finding_ids else str(raw.get("group_id") or "unknown")
            metadata = finding_meta.get(primary_finding, {})
            severity = _severity_label(metadata.get("severity", ""))
            title = metadata.get("title", "") or primary_finding
            source_row = source_rows.get(str(raw.get("source_verification_row_id") or ""))
            discussion_ids = tuple(str(item) for item in raw.get("discussion_signal_row_ids") or [] if str(item).strip())
            discussion, caveat = _discussion_text(discussion_ids, discussion_rows)
            line = (
                f"- {row_id} — {severity} {primary_finding}: {title}; action `{action}`. "
                f"Citation: `{DISPOSITION_LEDGER_ARTIFACT}#{row_id}`. "
                f"Source: {_citation_text(source_row)}. Discussion: {discussion}."
            )
            if caveat:
                line += f" Authority caveat: {caveat}."
            sections[heading].append(line)
    if isinstance(raw_degraded, list):
        for raw in raw_degraded:
            if isinstance(raw, dict):
                group_id = str(raw.get("group_id") or "unknown")
                reasons = ", ".join(str(item) for item in raw.get("blocking_reasons") or []) or "unknown"
                sections["### Degraded"].append(f"- {group_id}: {reasons}. Citation: `{DISPOSITION_LEDGER_ARTIFACT}`.")
    lines: list[str] = _footer_policy_brief(corpus_payload)
    raw_dispositions = dispositions if isinstance(dispositions, list) else []
    issue_rows = _issue_history_rows(raw_dispositions, finding_meta)
    map_rows = _disposition_map_rows(raw_dispositions)
    if issue_rows:
        if lines:
            lines.append("")
        lines.append(ISSUE_HISTORY_HEADING)
        lines.append("Raw DA IDs are internal provenance anchors; the final review should lead with these human-readable issue clusters.")
        lines.append("Allowed statuses: " + " | ".join(ALLOWED_DISPOSITION_MAP_STATUSES))
        for row in issue_rows:
            lines.append(
                f"- {row['title']} — status: {row['status']}. Reason: {row['reason']}. "
                f"Internal rows: {', '.join(row['row_ids'])}."
            )
    if map_rows:
        if lines:
            lines.append("")
        lines.append(INTERNAL_DA_COVERAGE_HEADING)
        lines.append("Allowed statuses: " + " | ".join(ALLOWED_DISPOSITION_MAP_STATUSES))
        for row_id in sorted(map_rows):
            lines.append(f"- {row_id}: {map_rows[row_id]} (cite `{DISPOSITION_LEDGER_ARTIFACT}#{row_id}`)")
    for heading, entries in sections.items():
        if entries:
            if lines:
                lines.append("")
            lines.append(heading)
            lines.extend(entries)
    return "\n".join(lines)


def _record_runtime_module_in_manifest(manifest_path: Path | None, record: ModuleRunRecord) -> None:
    if manifest_path is None:
        return
    payload = _load_json_object(manifest_path)
    if payload is None:
        return
    modules = payload.setdefault("modules", {})
    if isinstance(modules, dict):
        modules[record.module.value] = record.to_json()
        try:
            _write_json_object(manifest_path, payload)
        except OSError:
            return


def build_report_governor_sanitization_prompt(*, governor_brief: str, review_text: str) -> str:
    """Build the module-10 post-review sanitization prompt."""

    return "\n".join(
        [
            "You are auditing a CURe PR review for subsequent-review context awareness.",
            "Answer this exact question:",
            REPORT_GOVERNOR_AWARENESS_QUESTION,
            "",
            "The final review must lead with a human-readable Prior Review Issue History: stable issue titles first, current status second, and plain-English reason third.",
            "Raw DA-* row IDs are internal provenance anchors only; they may appear in optional/internal details but must not be the primary reader-facing representation.",
            "The final review must still include internal DA coverage for every DA-* row from disposition_ledger.json using allowed statuses: " + " | ".join(ALLOWED_DISPOSITION_MAP_STATUSES),
            "Official CURe footer markers are valid prior-review provenance regardless of author/login; body-only CURe-looking text remains rejected.",
            "",
            "Return JSON only with these fields:",
            '- awareness: one of "demonstrated", "partial", "missing", or "unknown"',
            "- judgment: concise qualitative assessment",
            "- evidence: array of short quotes or observations from the final review",
            "- warnings: optional array of caveats",
            "",
            "## Prior review context brief",
            governor_brief.strip(),
            "",
            "## Final review.md",
            review_text.strip(),
            "",
        ]
    )


def _list_of_strings(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _expected_disposition_map(artifact_dir: Path) -> dict[str, str]:
    payload = _load_json_object(artifact_dir / DISPOSITION_LEDGER_ARTIFACT)
    dispositions = (payload or {}).get("dispositions")
    if not isinstance(dispositions, list):
        return {}
    rows = _disposition_map_rows(dispositions)
    return {row_id: status for row_id, status in rows.items() if row_id.startswith("DA-")}


def _expected_issue_history_rows(artifact_dir: Path) -> list[dict[str, Any]]:
    payload = _load_json_object(artifact_dir / DISPOSITION_LEDGER_ARTIFACT)
    dispositions = (payload or {}).get("dispositions")
    if not isinstance(dispositions, list):
        return []
    finding_meta = _finding_metadata_by_id(_load_json_object(artifact_dir / "prior_findings.json"))
    return _issue_history_rows(dispositions, finding_meta)


def _actual_disposition_map(review_text: str) -> dict[str, str]:
    statuses = "|".join(re.escape(status) for status in ALLOWED_DISPOSITION_MAP_STATUSES)
    pattern = re.compile(rf"\b(DA-\d{{4,}})\b[^\n]*\b({statuses})\b", re.IGNORECASE)
    return {match.group(1): match.group(2).lower() for match in pattern.finditer(review_text)}


def _issue_history_warnings(*, artifact_dir: Path, review_text: str) -> list[str]:
    expected = _expected_issue_history_rows(artifact_dir)
    if not expected:
        return []
    normalized_review = re.sub(r"\s+", " ", review_text).lower()
    has_issue_history_heading = "prior review issue history" in normalized_review
    has_da_map_heading = "prior review disposition map" in normalized_review or "internal da coverage" in normalized_review
    warnings: list[str] = []
    missing_titles = tuple(
        sorted(
            str(row["title"])
            for row in expected
            if str(row["title"]).lower() not in normalized_review or str(row["status"]).lower() not in normalized_review
        )
    )
    if not has_issue_history_heading or missing_titles:
        warnings.append("missing_prior_review_issue_history")
    if missing_titles:
        warnings.append("missing_prior_review_issue_clusters:" + ",".join(missing_titles))
    if has_da_map_heading and (not has_issue_history_heading or missing_titles):
        warnings.append("raw_da_list_only")
    return warnings


def _disposition_map_warnings(*, artifact_dir: Path, review_text: str) -> list[str]:
    expected = _expected_disposition_map(artifact_dir)
    if not expected:
        return []
    actual = _actual_disposition_map(review_text)
    missing = tuple(sorted(row_id for row_id in expected if row_id not in actual))
    contradicted = tuple(
        sorted(
            row_id
            for row_id, expected_status in expected.items()
            if row_id in actual and actual[row_id] not in {expected_status, "contradicted-with-evidence"}
        )
    )
    warnings: list[str] = []
    if missing:
        warnings.append("missing_internal_da_coverage:" + ",".join(missing))
    if contradicted:
        warnings.append("contradicted_internal_da_coverage:" + ",".join(contradicted))
    warnings.extend(_issue_history_warnings(artifact_dir=artifact_dir, review_text=review_text))
    return warnings


def _write_report_governor_result(
    *,
    path: Path,
    status: ModuleStatus,
    reasons: tuple[str, ...] = (),
    review_path: Path,
    governor_brief_path: Path,
    awareness: str = "unknown",
    judgment: str = "",
    evidence: list[str] | None = None,
    warnings: list[str] | None = None,
    raw_response: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": status.value,
        "question": REPORT_GOVERNOR_AWARENESS_QUESTION,
        "awareness": awareness,
        "judgment": judgment,
        "evidence": evidence or [],
        "warnings": warnings or [],
        "paths": {"review_md": str(review_path), "governor_brief": str(governor_brief_path)},
    }
    if reasons:
        payload["status_reasons"] = list(reasons)
    if raw_response is not None:
        payload["raw_response"] = raw_response
    _write_json_object(path, payload)


def audit_review_report_after_review(
    *,
    artifact_dir: Path,
    review_path: Path,
    governor_mode: str,
    auditor: Callable[[str], str] | None = None,
    manifest_path: Path | None = None,
) -> ModuleRunRecord:
    """Run module-10 post-review sanitization as a warn-only audit.

    The audit is intentionally non-blocking: malformed inputs, LLM failures, and
    malformed LLM responses are recorded as degraded ``report_governor_result``
    artifacts but never raise to the caller.
    """

    normalized_mode = str(governor_mode or "strict").strip().lower()
    if normalized_mode == "off":
        record = ModuleRunRecord(
            module=SubsequentReviewModule.REPORT_GOVERNOR,
            status=ModuleStatus.DISABLED,
            reasons=("governor_mode_off",),
        )
        _record_runtime_module_in_manifest(manifest_path, record)
        return record

    governor_brief_path = artifact_dir / GOVERNOR_BRIEF_ARTIFACT
    try:
        governor_brief = governor_brief_path.read_text(encoding="utf-8")
    except OSError:
        governor_brief = ""
    if not governor_brief.strip():
        record = ModuleRunRecord(
            module=SubsequentReviewModule.REPORT_GOVERNOR,
            status=ModuleStatus.DISABLED,
            reasons=("empty_governor_brief",),
        )
        _record_runtime_module_in_manifest(manifest_path, record)
        return record

    result_path = artifact_dir / REPORT_GOVERNOR_RESULT_ARTIFACT

    def finish(status: ModuleStatus, reasons: tuple[str, ...] = ()) -> ModuleRunRecord:
        record = ModuleRunRecord(
            module=SubsequentReviewModule.REPORT_GOVERNOR,
            status=status,
            reasons=reasons,
            artifact_path=str(result_path),
        )
        _record_runtime_module_in_manifest(manifest_path, record)
        return record

    try:
        review_text = review_path.read_text(encoding="utf-8")
    except OSError as exc:
        reasons = ("missing_review_report",)
        _write_report_governor_result(
            path=result_path,
            status=ModuleStatus.DEGRADED,
            reasons=reasons,
            review_path=review_path,
            governor_brief_path=governor_brief_path,
            judgment="Final review report was unavailable for sanitization.",
            warnings=[str(exc)],
        )
        return finish(ModuleStatus.DEGRADED, reasons)

    if auditor is None:
        reasons = ("sanitization_auditor_not_configured",)
        _write_report_governor_result(
            path=result_path,
            status=ModuleStatus.DEGRADED,
            reasons=reasons,
            review_path=review_path,
            governor_brief_path=governor_brief_path,
            judgment="No sanitization auditor was configured.",
            warnings=["sanitization auditor not configured"],
        )
        return finish(ModuleStatus.DEGRADED, reasons)

    prompt = build_report_governor_sanitization_prompt(governor_brief=governor_brief, review_text=review_text)
    try:
        response = auditor(prompt)
    except Exception as exc:  # noqa: BLE001 - post-review audit is warn-only
        reasons = ("sanitization_auditor_failed",)
        _write_report_governor_result(
            path=result_path,
            status=ModuleStatus.DEGRADED,
            reasons=reasons,
            review_path=review_path,
            governor_brief_path=governor_brief_path,
            judgment="Sanitization auditor failed before returning a judgment.",
            warnings=[str(exc)],
        )
        return finish(ModuleStatus.DEGRADED, reasons)

    raw_response = str(response or "")
    try:
        parsed = json.loads(raw_response)
    except json.JSONDecodeError:
        reasons = ("sanitization_response_malformed",)
        _write_report_governor_result(
            path=result_path,
            status=ModuleStatus.DEGRADED,
            reasons=reasons,
            review_path=review_path,
            governor_brief_path=governor_brief_path,
            judgment="Sanitization auditor returned malformed JSON.",
            warnings=["sanitization response was not valid JSON"],
            raw_response=raw_response,
        )
        return finish(ModuleStatus.DEGRADED, reasons)
    if not isinstance(parsed, dict):
        reasons = ("sanitization_response_malformed",)
        _write_report_governor_result(
            path=result_path,
            status=ModuleStatus.DEGRADED,
            reasons=reasons,
            review_path=review_path,
            governor_brief_path=governor_brief_path,
            judgment="Sanitization auditor returned a non-object JSON payload.",
            warnings=["sanitization response was not a JSON object"],
            raw_response=raw_response,
        )
        return finish(ModuleStatus.DEGRADED, reasons)

    awareness = str(parsed.get("awareness") or "unknown").strip().lower() or "unknown"
    judgment = str(parsed.get("judgment") or "").strip()
    evidence = _list_of_strings(parsed.get("evidence"))
    warnings = _list_of_strings(parsed.get("warnings"))
    if awareness in {"partial", "missing"}:
        warnings.append(f"awareness_{awareness}")
    warnings.extend(_disposition_map_warnings(artifact_dir=artifact_dir, review_text=review_text))
    status = ModuleStatus.DEGRADED if warnings and awareness in {"partial", "missing", "unknown"} else ModuleStatus.SUCCESS
    if any(
        warning.startswith(
            (
                "missing_internal_da_coverage:",
                "contradicted_internal_da_coverage:",
                "missing_prior_review_issue_history",
                "missing_prior_review_issue_clusters:",
                "raw_da_list_only",
            )
        )
        for warning in warnings
    ):
        status = ModuleStatus.DEGRADED
    final_reasons: tuple[str, ...] = tuple(dict.fromkeys(warnings)) if status is ModuleStatus.DEGRADED else ()
    _write_report_governor_result(
        path=result_path,
        status=status,
        reasons=final_reasons,
        review_path=review_path,
        governor_brief_path=governor_brief_path,
        awareness=awareness,
        judgment=judgment,
        evidence=evidence,
        warnings=list(dict.fromkeys(warnings)),
    )
    return finish(status, final_reasons)


def finalize_review_runtime_context(
    *,
    artifact_dir: Path,
    memory_store_path: Path | None = None,
    manifest_path: Path | None = None,
    meta_path: Path | None = None,
) -> ModuleRunRecord:
    """Refresh module-9 artifacts after all runtime statuses have settled."""

    context_package_path = artifact_dir / REVIEW_CONTEXT_PACKAGE_ARTIFACT
    context_markdown_path = artifact_dir / SUBSEQUENT_REVIEW_CONTEXT_ARTIFACT
    packager_record = ModuleRunRecord(
        module=SubsequentReviewModule.REVIEW_CONTEXT_PACKAGER,
        status=ModuleStatus.SUCCESS,
        artifact_path=str(context_package_path),
    )
    _record_runtime_module_in_manifest(manifest_path, packager_record)
    package = build_review_context_package(artifact_dir=artifact_dir, memory_store_path=memory_store_path)
    _write_json_object(context_package_path, package)
    _write_context_markdown(path=context_markdown_path, package=package)

    if meta_path is not None and meta_path.is_file():
        meta = _load_json_object(meta_path)
        if meta is not None:
            runtime_modules = meta.setdefault("subsequent_review", {}).setdefault("runtime_modules", {})
            manifest_payload = _load_json_object(manifest_path) if manifest_path is not None else None
            modules = (manifest_payload or {}).get("modules")
            if isinstance(runtime_modules, dict) and isinstance(modules, dict):
                runtime_modules.clear()
                for module_name, record in modules.items():
                    if isinstance(record, dict):
                        runtime_modules[str(module_name)] = dict(record)
            try:
                _write_json_object(meta_path, meta)
            except OSError:
                pass
    return packager_record


def prepare_review_runtime_pre_prompt(
    *,
    artifact_dir: Path,
    governor_mode: str,
    memory_store_path: Path | None = None,
    manifest_path: Path | None = None,
) -> ReviewRuntimePrePromptResult:
    """Run module-9/10 pre-prompt transformations and return prompt vars."""

    normalized_mode = str(governor_mode or "strict").strip().lower()
    context_package_path = artifact_dir / REVIEW_CONTEXT_PACKAGE_ARTIFACT
    context_markdown_path = artifact_dir / SUBSEQUENT_REVIEW_CONTEXT_ARTIFACT
    package = build_review_context_package(artifact_dir=artifact_dir, memory_store_path=memory_store_path)
    _write_json_object(context_package_path, package)
    _write_context_markdown(path=context_markdown_path, package=package)
    packager_record = ModuleRunRecord(
        module=SubsequentReviewModule.REVIEW_CONTEXT_PACKAGER,
        status=ModuleStatus.SUCCESS,
        artifact_path=str(context_package_path),
    )
    _record_runtime_module_in_manifest(manifest_path, packager_record)

    if normalized_mode == "off":
        governor_record = ModuleRunRecord(
            module=SubsequentReviewModule.REPORT_GOVERNOR,
            status=ModuleStatus.DISABLED,
            reasons=("governor_mode_off",),
        )
        _record_runtime_module_in_manifest(manifest_path, governor_record)
        finalize_review_runtime_context(
            artifact_dir=artifact_dir,
            memory_store_path=memory_store_path,
            manifest_path=manifest_path,
        )
        return ReviewRuntimePrePromptResult(
            prior_review_brief="",
            context_package_path=context_package_path,
            context_markdown_path=context_markdown_path,
            governor_brief_path=None,
            records=(packager_record, governor_record),
        )

    if normalized_mode == "strict":
        disposition_path = artifact_dir / DISPOSITION_LEDGER_ARTIFACT
        if not disposition_path.is_file():
            raise ValueError(f"missing required subsequent-review artifact: {DISPOSITION_LEDGER_ARTIFACT}")
        disposition_payload = _load_json_object(disposition_path)
        if disposition_payload is None:
            raise ValueError(f"malformed required subsequent-review artifact: {DISPOSITION_LEDGER_ARTIFACT}")
        _strict_governor_validate_citation_ledgers(artifact_dir=artifact_dir, disposition_payload=disposition_payload)

    brief = build_governor_brief(artifact_dir=artifact_dir)
    governor_brief_path = artifact_dir / GOVERNOR_BRIEF_ARTIFACT
    if brief:
        governor_brief_path.write_text(brief + "\n", encoding="utf-8")
    else:
        governor_brief_path.write_text("", encoding="utf-8")
    governor_record = ModuleRunRecord(
        module=SubsequentReviewModule.REPORT_GOVERNOR,
        status=ModuleStatus.SUCCESS if brief else ModuleStatus.DEGRADED,
        reasons=() if brief else ("empty_disposition_ledger",),
        artifact_path=str(governor_brief_path),
    )
    _record_runtime_module_in_manifest(manifest_path, governor_record)
    finalize_review_runtime_context(
        artifact_dir=artifact_dir,
        memory_store_path=memory_store_path,
        manifest_path=manifest_path,
    )
    return ReviewRuntimePrePromptResult(
        prior_review_brief=brief,
        context_package_path=context_package_path,
        context_markdown_path=context_markdown_path,
        governor_brief_path=governor_brief_path,
        records=(packager_record, governor_record),
    )


def _source_verification_from_json(payload: dict[str, Any]) -> SourceVerificationLedger:
    rows: list[SourceVerificationRow] = []
    raw_rows = payload.get("rows")
    if isinstance(raw_rows, list):
        for raw in raw_rows:
            if not isinstance(raw, dict):
                continue
            rows.append(
                SourceVerificationRow(
                    row_id=str(raw.get("row_id") or "").strip(),
                    group_id=str(raw.get("group_id") or "").strip(),
                    finding_ids=_string_tuple(raw.get("finding_ids")),
                    source_state=SourceState(str(raw.get("source_state") or "source_unknown")),
                    current_source_citations=_dict_tuple(raw.get("current_source_citations")),
                    inspected_source_refs=_string_tuple(raw.get("inspected_source_refs")),
                    unavailable_reasons=_string_tuple(raw.get("unavailable_reasons")),
                    provenance=_dict_value(raw.get("provenance")),
                )
            )
    return SourceVerificationLedger(
        status=ModuleStatus(str(payload.get("status") or ModuleStatus.SUCCESS.value)),
        rows=tuple(rows),
        status_reasons=_string_tuple(payload.get("status_reasons")),
    )


def _disposition_ledger_from_json(payload: dict[str, Any]) -> DispositionLedger:
    rows: list[DispositionRow] = []
    raw_rows = payload.get("dispositions")
    if isinstance(raw_rows, list):
        for raw in raw_rows:
            if not isinstance(raw, dict):
                continue
            rows.append(
                DispositionRow(
                    row_id=str(raw.get("row_id") or "").strip(),
                    group_id=str(raw.get("group_id") or "").strip(),
                    finding_ids=_string_tuple(raw.get("finding_ids")),
                    action=DispositionAction(str(raw.get("action") or DispositionAction.RE_REPORT.value)),
                    source_verification_row_id=str(raw.get("source_verification_row_id") or "").strip(),
                    discussion_signal_row_ids=_string_tuple(raw.get("discussion_signal_row_ids")),
                    reconciliation_group_id=str(raw.get("reconciliation_group_id") or "").strip(),
                    provenance=_dict_value(raw.get("provenance")),
                )
            )
    return DispositionLedger(
        status=ModuleStatus(str(payload.get("status") or ModuleStatus.SUCCESS.value)),
        dispositions=tuple(rows),
        status_reasons=_string_tuple(payload.get("status_reasons")),
    )


def update_review_memory_after_review(
    *,
    artifact_dir: Path,
    memory_store: ReviewMemoryStore,
    current_head: str | None,
    run_provenance: dict[str, Any] | None = None,
    manifest_path: Path | None = None,
) -> ModuleRunRecord:
    """Update shared ``cure_memory.json`` from completed review ledgers.

    Missing or malformed semantic ledgers degrade the memory-store module only;
    memory is a performance/audit cache and must not fail publication of the
    review report.
    """

    def finish(record: ModuleRunRecord) -> ModuleRunRecord:
        if manifest_path is None:
            return record
        payload = _load_json_object(manifest_path)
        if payload is None:
            return record
        modules = payload.setdefault("modules", {})
        if isinstance(modules, dict):
            modules[SubsequentReviewModule.REVIEW_MEMORY_STORE.value] = record.to_json()
            try:
                manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            except OSError:
                return record
        return record

    head = str(current_head or "").strip()
    if not head:
        return finish(
            ModuleRunRecord(
                module=SubsequentReviewModule.REVIEW_MEMORY_STORE,
                status=ModuleStatus.DISABLED,
                reasons=("missing_current_head",),
            )
        )

    source_path = artifact_dir / SOURCE_VERIFICATION_ARTIFACT
    if not source_path.is_file():
        return finish(
            ModuleRunRecord(
                module=SubsequentReviewModule.REVIEW_MEMORY_STORE,
                status=ModuleStatus.DEGRADED,
                reasons=(f"missing_artifact:{SOURCE_VERIFICATION_ARTIFACT}",),
            )
        )

    source_payload = _load_json_object(source_path)
    if source_payload is None:
        return finish(
            ModuleRunRecord(
                module=SubsequentReviewModule.REVIEW_MEMORY_STORE,
                status=ModuleStatus.DEGRADED,
                reasons=(f"malformed_artifact:{SOURCE_VERIFICATION_ARTIFACT}",),
            )
        )

    try:
        source_ledger = _source_verification_from_json(source_payload)
    except ValueError as exc:
        return finish(
            ModuleRunRecord(
                module=SubsequentReviewModule.REVIEW_MEMORY_STORE,
                status=ModuleStatus.DEGRADED,
                reasons=(f"malformed_artifact:{SOURCE_VERIFICATION_ARTIFACT}:{exc}",),
            )
        )

    disposition_ledger: DispositionLedger | None = None
    disposition_path = artifact_dir / DISPOSITION_LEDGER_ARTIFACT
    if disposition_path.is_file():
        disposition_payload = _load_json_object(disposition_path)
        if disposition_payload is None:
            return finish(
                ModuleRunRecord(
                    module=SubsequentReviewModule.REVIEW_MEMORY_STORE,
                    status=ModuleStatus.DEGRADED,
                    reasons=(f"malformed_artifact:{DISPOSITION_LEDGER_ARTIFACT}",),
                )
            )
        try:
            disposition_ledger = _disposition_ledger_from_json(disposition_payload)
        except ValueError as exc:
            return finish(
                ModuleRunRecord(
                    module=SubsequentReviewModule.REVIEW_MEMORY_STORE,
                    status=ModuleStatus.DEGRADED,
                    reasons=(f"malformed_artifact:{DISPOSITION_LEDGER_ARTIFACT}:{exc}",),
                )
            )

    try:
        memory_store.update_findings(
            current_head=head,
            source_verification=source_ledger,
            disposition_ledger=disposition_ledger,
            run_provenance=run_provenance,
        )
    except Exception as exc:  # noqa: BLE001 - memory updates are warn/degraded-only runtime state
        return finish(
            ModuleRunRecord(
                module=SubsequentReviewModule.REVIEW_MEMORY_STORE,
                status=ModuleStatus.DEGRADED,
                reasons=(f"memory_update_failed:{exc}",),
            )
        )

    return finish(
        ModuleRunRecord(
            module=SubsequentReviewModule.REVIEW_MEMORY_STORE,
            status=ModuleStatus.SUCCESS,
            artifact_path=str(memory_store.path),
        )
    )
