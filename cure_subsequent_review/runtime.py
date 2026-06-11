"""Runtime-phase orchestration helpers for subsequent PR review.

The Story 04 runtime orchestrator owns seams that sit outside the Story 01-03
semantic pipeline.  This module intentionally keeps post-review memory updates
small and auditable: completed semantic ledgers are read from the sandbox and
copied into the shared per-PR memory cache after the review run completes.
"""

from __future__ import annotations

import json
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
    lines.extend(
        [
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
        if policy != EvidencePolicy.TRUSTED.value or authority in {"", "unknown", "developer"} or signal == DiscussionSignalClass.AUTHORITY_CONFLICT.value:
            caveats.append(f"{row_id} has {policy} discussion authority ({authority})")
    return "; ".join(parts), "; ".join(caveats) if caveats else None


def build_governor_brief(*, artifact_dir: Path) -> str:
    """Build the module-10 pre-review brief from disposition/source ledgers."""

    disposition_payload = _load_json_object(artifact_dir / DISPOSITION_LEDGER_ARTIFACT)
    if disposition_payload is None:
        return ""
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
    lines: list[str] = []
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

    awareness = str(parsed.get("awareness") or "unknown").strip() or "unknown"
    judgment = str(parsed.get("judgment") or "").strip()
    evidence = _list_of_strings(parsed.get("evidence"))
    warnings = _list_of_strings(parsed.get("warnings"))
    _write_report_governor_result(
        path=result_path,
        status=ModuleStatus.SUCCESS,
        review_path=review_path,
        governor_brief_path=governor_brief_path,
        awareness=awareness,
        judgment=judgment,
        evidence=evidence,
        warnings=warnings,
    )
    return finish(ModuleStatus.SUCCESS)


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
