"""Control plane for Story 01 subsequent-review intake."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from meta import write_json

from cure_subsequent_review.contracts import (
    DiscussionArtifact,
    EvidencePolicy,
    ModuleRunRecord,
    ModuleStatus,
    SubsequentReviewModule,
)
from cure_subsequent_review.finding_identity import reconcile_findings
from cure_subsequent_review.github_history import JsonFetcher, collect_pr_discussion
from cure_subsequent_review.prior_corpus import build_prior_review_corpus
from cure_subsequent_review.prior_findings import extract_prior_findings
from cure_subsequent_review.semantic_pipeline import MODULE_REGISTRY, run_semantic_pipeline
from cure_subsequent_review.source_truth import FindingVerifier, SourceVerificationMemory
from cure_subsequent_review.discussion_signals import DiscussionLinker

SummaryWriter = Callable[[str], None]
DiscussionFetcher = Callable[[], DiscussionArtifact]

_STORY_01_MODULES = {
    SubsequentReviewModule.CONTROL_PLANE,
    SubsequentReviewModule.PR_HISTORY_COLLECTOR,
    SubsequentReviewModule.PRIOR_REVIEW_CORPUS_BUILDER,
    SubsequentReviewModule.PRIOR_FINDING_EXTRACTOR,
    SubsequentReviewModule.FINDING_RECONCILER,
}


@dataclass(frozen=True)
class SubsequentReviewConfig:
    enabled: bool = False
    evidence_policy: EvidencePolicy = EvidencePolicy.UNTRUSTED
    module_overrides: dict[SubsequentReviewModule, ModuleStatus] = field(default_factory=dict)

    def module_enabled(self, module: SubsequentReviewModule) -> bool:
        status = self.module_overrides.get(module)
        if status is ModuleStatus.DISABLED:
            return False
        return module in _STORY_01_MODULES or module in MODULE_REGISTRY


@dataclass(frozen=True)
class SubsequentReviewIntakeResult:
    manifest_path: Path
    artifact_dir: Path
    summary: str


def _record(
    records: dict[SubsequentReviewModule, ModuleRunRecord],
    module: SubsequentReviewModule,
    status: ModuleStatus,
    *,
    reasons: tuple[str, ...] = (),
    artifact_path: Path | None = None,
) -> None:
    records[module] = ModuleRunRecord(
        module=module,
        status=status,
        reasons=reasons,
        artifact_path=str(artifact_path) if artifact_path is not None else None,
    )


def _manifest_json(*, pr: Any, config: SubsequentReviewConfig, records: dict[SubsequentReviewModule, ModuleRunRecord]) -> dict[str, Any]:
    modules = {}
    for module in SubsequentReviewModule:
        record = records.get(module)
        if record is None:
            default_status = ModuleStatus.ENABLED if config.module_enabled(module) else ModuleStatus.DISABLED
            record = ModuleRunRecord(module=module, status=default_status)
        modules[module.value] = record.to_json()
    return {
        "schema_version": 1,
        "pr": {"host": pr.host, "owner": pr.owner, "repo": pr.repo, "number": pr.number},
        "enabled": True,
        "evidence_policy": config.evidence_policy.value,
        "modules": modules,
    }


def _summary(*, completed_count: int, discussion_count: int, records: dict[SubsequentReviewModule, ModuleRunRecord]) -> str:
    status_text = ", ".join(
        f"{module.value}={records[module].status.value if module in records else ModuleStatus.DISABLED.value}"
        for module in SubsequentReviewModule
    )
    source_observability = records.get(SubsequentReviewModule.SOURCE_TRUTH_VERIFIER)
    fanout = (source_observability.observability if source_observability is not None else {}).get("verifier_fanout", {})
    observability_text = ""
    if isinstance(fanout, dict):
        cache = fanout.get("cache", {})
        if isinstance(cache, dict) and "provider_call_count" in fanout:
            observability_text = (
                f"; source_verifier_calls={fanout.get('provider_call_count', 0)}"
                f" cache_hits={cache.get('hit_count', 0)}"
                f" cache_misses={cache.get('miss_count', 0)}"
                f" cache_bypasses={cache.get('bypass_count', 0)}"
            )
    return (
        "Subsequent review intake: "
        f"prior completed sessions: {completed_count}; "
        f"discussion events: {discussion_count}; "
        f"modules: {status_text}"
        f"{observability_text}"
    )


def run_subsequent_review_intake(
    *,
    pr: Any,
    work_dir: Path,
    completed_sessions: list[Any] | tuple[Any, ...],
    config: SubsequentReviewConfig,
    fetch_json: JsonFetcher | None = None,
    summary_writer: SummaryWriter | None = None,
    prefetched_discussion: DiscussionArtifact | None = None,
    discussion_fetcher: DiscussionFetcher | None = None,
    degraded_runtime_path: Path | None = None,
    source_verifier: FindingVerifier | None = None,
    discussion_linker: DiscussionLinker | None = None,
    memory_store: SourceVerificationMemory | None = None,
    current_head: str | None = None,
    pr_files_changed: tuple[str, ...] = (),
) -> SubsequentReviewIntakeResult | None:
    """Run Story 01 intake after a new sandbox work directory exists.

    Disabled top-level mode is a no-op and deliberately creates no
    ``work/subsequent`` directory.
    """

    if not config.enabled:
        return None

    artifact_dir = work_dir / "subsequent"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    records: dict[SubsequentReviewModule, ModuleRunRecord] = {}
    _record(records, SubsequentReviewModule.CONTROL_PLANE, ModuleStatus.SUCCESS)

    discussion = None
    if config.module_enabled(SubsequentReviewModule.PR_HISTORY_COLLECTOR):
        if prefetched_discussion is not None:
            discussion = prefetched_discussion
        elif discussion_fetcher is not None:
            discussion = discussion_fetcher()
        elif fetch_json is not None:
            discussion = collect_pr_discussion(pr=pr, fetch_json=fetch_json)
        else:
            raise ValueError("run_subsequent_review_intake requires prefetched_discussion, discussion_fetcher, or fetch_json")
        discussion_path = artifact_dir / "pr_discussion.json"
        write_json(discussion_path, discussion.to_json())
        _record(
            records,
            SubsequentReviewModule.PR_HISTORY_COLLECTOR,
            discussion.status,
            reasons=discussion.status_reasons,
            artifact_path=discussion_path,
        )
    else:
        _record(records, SubsequentReviewModule.PR_HISTORY_COLLECTOR, ModuleStatus.DISABLED)

    if degraded_runtime_path is not None:
        status = ModuleStatus.DEGRADED if discussion is not None and discussion.status is ModuleStatus.DEGRADED else ModuleStatus.SUCCESS
        _record(
            records,
            SubsequentReviewModule.DEGRADED_RUNTIME_MANAGER,
            status,
            reasons=discussion.status_reasons if discussion is not None else (),
            artifact_path=degraded_runtime_path,
        )

    corpus = None
    if config.module_enabled(SubsequentReviewModule.PRIOR_REVIEW_CORPUS_BUILDER):
        corpus = build_prior_review_corpus(pr=pr, sessions=completed_sessions, discussion=discussion, current_head=current_head)
        corpus_path = artifact_dir / "prior_review_corpus.json"
        write_json(corpus_path, corpus.to_json())
        _record(
            records,
            SubsequentReviewModule.PRIOR_REVIEW_CORPUS_BUILDER,
            corpus.status,
            reasons=corpus.status_reasons,
            artifact_path=corpus_path,
        )
    else:
        _record(records, SubsequentReviewModule.PRIOR_REVIEW_CORPUS_BUILDER, ModuleStatus.DISABLED)

    finding_ledger = None
    reconciliation = None
    if corpus is not None and config.module_enabled(SubsequentReviewModule.PRIOR_FINDING_EXTRACTOR):
        finding_ledger = extract_prior_findings(corpus=corpus)
        findings_path = artifact_dir / "prior_findings.json"
        write_json(findings_path, finding_ledger.to_json())
        _record(
            records,
            SubsequentReviewModule.PRIOR_FINDING_EXTRACTOR,
            finding_ledger.status,
            reasons=finding_ledger.status_reasons,
            artifact_path=findings_path,
        )
    else:
        _record(records, SubsequentReviewModule.PRIOR_FINDING_EXTRACTOR, ModuleStatus.DISABLED)

    if finding_ledger is not None and config.module_enabled(SubsequentReviewModule.FINDING_RECONCILER):
        reconciliation = reconcile_findings(
            findings=finding_ledger.findings,
            upstream_status_reasons=finding_ledger.status_reasons,
        )
        reconciliation_path = artifact_dir / "reconciled_findings.json"
        write_json(reconciliation_path, reconciliation.to_json())
        _record(
            records,
            SubsequentReviewModule.FINDING_RECONCILER,
            reconciliation.status,
            reasons=reconciliation.status_reasons,
            artifact_path=reconciliation_path,
        )
    else:
        _record(records, SubsequentReviewModule.FINDING_RECONCILER, ModuleStatus.DISABLED)

    run_semantic_pipeline(
        artifact_dir=artifact_dir,
        config=config,
        records=records,
        reconciliation=reconciliation,
        discussion=discussion,
        corpus=corpus,
        source_verifier=source_verifier,
        discussion_linker=discussion_linker,
        memory_store=memory_store,
        current_head=current_head,
        pr_files_changed=pr_files_changed,
    )

    if config.module_overrides.get(SubsequentReviewModule.REVIEW_MEMORY_STORE) is ModuleStatus.DISABLED:
        _record(records, SubsequentReviewModule.REVIEW_MEMORY_STORE, ModuleStatus.DISABLED)
    elif memory_store is not None and hasattr(memory_store, "update_findings") and hasattr(memory_store, "path"):
        from cure_subsequent_review.runtime import update_review_memory_after_intake

        runtime_memory_store: Any = memory_store
        records[SubsequentReviewModule.REVIEW_MEMORY_STORE] = update_review_memory_after_intake(
            artifact_dir=artifact_dir,
            memory_store=runtime_memory_store,
            current_head=current_head,
            run_provenance={"stage": "intake_complete"},
        )

    manifest_path = artifact_dir / "run_manifest.json"
    write_json(manifest_path, _manifest_json(pr=pr, config=config, records=records))
    summary = _summary(completed_count=len(completed_sessions), discussion_count=len(discussion.events) if discussion else 0, records=records)
    if summary_writer is not None:
        summary_writer(summary)
    return SubsequentReviewIntakeResult(manifest_path=manifest_path, artifact_dir=artifact_dir, summary=summary)
