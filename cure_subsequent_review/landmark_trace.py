"""Deterministic test-only landmark trace runner for subsequent PR review.

This module is intentionally outside the runtime semantic registry.  It exists to
exercise a complete local Story 04 simulation fixture through the runtime seams
that are otherwise spread across PR flow integration tests.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cure_subsequent_review.contracts import ModuleRunRecord, ModuleStatus, SubsequentReviewModule
from cure_subsequent_review.memory_store import ReviewMemoryStore
from cure_subsequent_review.runtime import (
    audit_review_report_after_review,
    prepare_review_runtime_pre_prompt,
    update_review_memory_after_review,
)

LANDMARK_TRACE_SUMMARY_ARTIFACT = "landmark_trace_summary.json"

_STAGE_MODULES: tuple[SubsequentReviewModule, ...] = (
    SubsequentReviewModule.CONTROL_PLANE,
    SubsequentReviewModule.PR_HISTORY_COLLECTOR,
    SubsequentReviewModule.PRIOR_REVIEW_CORPUS_BUILDER,
    SubsequentReviewModule.PRIOR_FINDING_EXTRACTOR,
    SubsequentReviewModule.FINDING_RECONCILER,
    SubsequentReviewModule.SOURCE_TRUTH_VERIFIER,
    SubsequentReviewModule.DISCUSSION_SIGNAL_RESOLVER,
    SubsequentReviewModule.DISPOSITION_ARBITER,
    SubsequentReviewModule.REVIEW_CONTEXT_PACKAGER,
    SubsequentReviewModule.REPORT_GOVERNOR,
    SubsequentReviewModule.REVIEW_MEMORY_STORE,
    SubsequentReviewModule.DEGRADED_RUNTIME_MANAGER,
)


@dataclass(frozen=True)
class LandmarkTraceResult:
    summary_path: Path
    summary: dict[str, Any]
    record: ModuleRunRecord


def run_landmark_trace(*, fixture_dir: Path, output_dir: Path) -> LandmarkTraceResult:
    """Run the deterministic local landmark trace fixture and write a summary.

    The fixture supplies deterministic Story 01-03 artifacts plus a final
    ``review.md``.  The runner copies those artifacts to ``output_dir`` and then
    exercises modules 9-11 through the same runtime helpers used by PR flow.  It
    reads module-12's degraded-runtime artifact from the fixture to keep this
    test-only trace live-network-free while still proving the degraded outcome is
    represented in the golden.
    """

    fixture_artifacts = fixture_dir / "artifacts"
    artifact_dir = output_dir / "work" / "subsequent"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    _copy_fixture_artifacts(fixture_artifacts=fixture_artifacts, artifact_dir=artifact_dir)

    review_path = artifact_dir / "review.md"
    manifest_path = artifact_dir / "run_manifest.json"
    memory_store = ReviewMemoryStore(path=output_dir / "shared_pr_memory" / "cure_memory.json")

    prepare_review_runtime_pre_prompt(
        artifact_dir=artifact_dir,
        governor_mode="strict",
        memory_store_path=memory_store.path,
        manifest_path=manifest_path,
    )
    audit_review_report_after_review(
        artifact_dir=artifact_dir,
        review_path=review_path,
        governor_mode="strict",
        auditor=_deterministic_awareness_auditor,
        manifest_path=manifest_path,
    )
    update_review_memory_after_review(
        artifact_dir=artifact_dir,
        memory_store=memory_store,
        current_head="landmark-head-sha",
        run_provenance={"trace": "landmark"},
        manifest_path=manifest_path,
    )

    summary = _build_summary(artifact_dir=artifact_dir, memory_store=memory_store)
    summary_path = artifact_dir / LANDMARK_TRACE_SUMMARY_ARTIFACT
    _write_json(summary_path, summary)
    record = ModuleRunRecord(
        module=SubsequentReviewModule.LANDMARK_TRACE_RUNNER,
        status=ModuleStatus.SUCCESS,
        artifact_path=str(summary_path),
    )
    return LandmarkTraceResult(summary_path=summary_path, summary=summary, record=record)


def _copy_fixture_artifacts(*, fixture_artifacts: Path, artifact_dir: Path) -> None:
    if not fixture_artifacts.is_dir():
        raise FileNotFoundError(f"landmark trace fixture artifacts not found: {fixture_artifacts}")
    for source in sorted(fixture_artifacts.iterdir()):
        if not source.is_file():
            continue
        shutil.copyfile(source, artifact_dir / source.name)


def _deterministic_awareness_auditor(prompt: str) -> str:
    awareness = "demonstrated" if "F-002" in prompt and "prior review" in prompt.lower() else "partial"
    return json.dumps(
        {
            "awareness": awareness,
            "judgment": "Deterministic fixture review references the prior open finding and source citation.",
            "evidence": ["F-002 remains open", "prior review context"],
            "warnings": [],
        },
        sort_keys=True,
    )


def _build_summary(*, artifact_dir: Path, memory_store: ReviewMemoryStore) -> dict[str, Any]:
    manifest = _read_json_object(artifact_dir / "run_manifest.json")
    disposition = _read_json_object(artifact_dir / "disposition_ledger.json")
    source = _read_json_object(artifact_dir / "source_verification.json")
    context_package = _read_json_object(artifact_dir / "review_context_package.json")
    degraded_runtime = _read_json_object(artifact_dir / "degraded_runtime.json")
    report_governor = _read_json_object(artifact_dir / "report_governor_result.json")
    memory = memory_store.load()

    modules = _module_statuses(manifest=manifest, degraded_runtime=degraded_runtime)
    headings = _markdown_headings(artifact_dir / "governor_brief.md")
    raw_memory_findings = memory.get("findings")
    memory_findings: dict[str, Any] = (
        {str(key): value for key, value in raw_memory_findings.items()} if isinstance(raw_memory_findings, dict) else {}
    )
    resolved_memory_count = len(
        [
            entry
            for entry in memory_findings.values()
            if isinstance(entry, dict) and entry.get("source_state") == "resolved_from_source"
        ]
    )

    return {
        "schema_version": 1,
        "module": SubsequentReviewModule.LANDMARK_TRACE_RUNNER.value,
        "status": ModuleStatus.SUCCESS.value,
        "stage_coverage": [{"module": module.value, "status": modules.get(module.value, "missing")} for module in _STAGE_MODULES],
        "dispositions": {
            "action_counts": _value_counts(disposition.get("dispositions"), key="action"),
            "degraded_count": _list_count(disposition.get("degraded_findings")),
        },
        "source_verification": {"state_counts": _value_counts(source.get("rows"), key="source_state")},
        "governor_brief": {"headings": headings},
        "report_governor": {
            "status": str(report_governor.get("status") or "missing"),
            "awareness": str(report_governor.get("awareness") or "unknown"),
        },
        "memory": {
            "finding_count": len(memory_findings),
            "resolved_from_source_count": resolved_memory_count,
        },
        "degraded_runtime": {
            "status": str(degraded_runtime.get("status") or "missing"),
            "final_reason": str(degraded_runtime.get("final_reason") or "missing"),
            "operator_choices": [str(item.get("choice")) for item in _dict_items(degraded_runtime.get("operator_choices"))],
        },
        "fb_010": {
            "discussion_event_count_matches_decision": bool(
                (context_package.get("fb_010") or {}).get("discussion_event_count_matches_decision")
            )
        },
    }


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _module_statuses(*, manifest: dict[str, Any], degraded_runtime: dict[str, Any]) -> dict[str, str]:
    raw_modules = manifest.get("modules")
    modules: dict[str, str] = {}
    if isinstance(raw_modules, dict):
        for name, raw in raw_modules.items():
            if isinstance(raw, dict):
                modules[str(name)] = str(raw.get("status") or "unknown")
    if degraded_runtime:
        modules[SubsequentReviewModule.DEGRADED_RUNTIME_MANAGER.value] = str(degraded_runtime.get("status") or "unknown")
    return modules


def _markdown_headings(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [line.strip() for line in lines if line.startswith("### ")]


def _dict_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _list_count(value: object) -> int:
    return len(value) if isinstance(value, list) else 0


def _value_counts(value: object, *, key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in _dict_items(value):
        raw = str(item.get(key) or "unknown")
        counts[raw] = counts.get(raw, 0) + 1
    return dict(sorted(counts.items()))


__all__ = ["LANDMARK_TRACE_SUMMARY_ARTIFACT", "LandmarkTraceResult", "run_landmark_trace"]
