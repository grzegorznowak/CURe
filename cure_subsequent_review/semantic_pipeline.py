"""Story 03 semantic module pipeline for subsequent-review intake."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from meta import write_json

from cure_subsequent_review.contracts import (
    DiscussionArtifact,
    ModuleRunRecord,
    ModuleStatus,
    PriorReviewCorpus,
    ReconciliationLedger,
    SubsequentReviewModule,
)
from cure_subsequent_review.discussion_signals import DiscussionLinker, resolve_discussion_signals
from cure_subsequent_review.disposition import arbitrate_dispositions
from cure_subsequent_review.source_truth import FindingVerifier, verify_source_truth


@dataclass(frozen=True)
class ModuleRegistryEntry:
    requires: tuple[str, ...]
    produces: str
    artifact_name: str | None


MODULE_REGISTRY: dict[SubsequentReviewModule, ModuleRegistryEntry] = {
    SubsequentReviewModule.SOURCE_TRUTH_VERIFIER: ModuleRegistryEntry(
        requires=("reconciliation",),
        produces="source_verification",
        artifact_name="source_verification.json",
    ),
    SubsequentReviewModule.DISCUSSION_SIGNAL_RESOLVER: ModuleRegistryEntry(
        requires=("discussion_artifact", "corpus"),
        produces="discussion_signals",
        artifact_name="discussion_signals.json",
    ),
    SubsequentReviewModule.DISPOSITION_ARBITER: ModuleRegistryEntry(
        requires=("reconciliation", "source_verification", "discussion_signals"),
        produces="disposition_ledger",
        artifact_name="disposition_ledger.json",
    ),
}


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


def _missing(context: dict[str, Any], requires: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(f"missing_dependency:{name}" for name in requires if context.get(name) is None)


def run_semantic_pipeline(
    *,
    artifact_dir: Path,
    config: Any,
    records: dict[SubsequentReviewModule, ModuleRunRecord],
    reconciliation: ReconciliationLedger | None,
    discussion: DiscussionArtifact | None,
    corpus: PriorReviewCorpus | None,
    source_verifier: FindingVerifier | None = None,
    discussion_linker: DiscussionLinker | None = None,
) -> None:
    """Run Story 03 modules in registry order and persist semantic ledgers."""

    context: dict[str, Any] = {
        "reconciliation": reconciliation,
        "discussion_artifact": discussion,
        "corpus": corpus,
    }

    for module, entry in MODULE_REGISTRY.items():
        if not config.module_enabled(module):
            _record(records, module, ModuleStatus.DISABLED)
            continue
        missing = _missing(context, entry.requires)
        if module is not SubsequentReviewModule.DISPOSITION_ARBITER and missing:
            _record(records, module, ModuleStatus.DISABLED, reasons=missing)
            continue

        artifact_path = artifact_dir / str(entry.artifact_name)
        ledger: Any
        if module is SubsequentReviewModule.SOURCE_TRUTH_VERIFIER:
            ledger = verify_source_truth(reconciliation=context["reconciliation"], verifier=source_verifier)
            context[entry.produces] = ledger
        elif module is SubsequentReviewModule.DISCUSSION_SIGNAL_RESOLVER:
            reconciliation_for_discussion = context["reconciliation"] or ReconciliationLedger(status=ModuleStatus.SUCCESS)
            ledger = resolve_discussion_signals(
                discussion=context["discussion_artifact"],
                reconciliation=reconciliation_for_discussion,
                linker=discussion_linker,
            )
            context[entry.produces] = ledger
        else:
            # The arbiter writes an explicit degraded_findings artifact when its
            # semantic dependencies are absent/degraded instead of inventing an
            # ask/escalate action or silently suppressing findings.
            if context.get("reconciliation") is None:
                _record(records, module, ModuleStatus.DISABLED, reasons=missing)
                continue
            ledger = arbitrate_dispositions(
                reconciliation=context["reconciliation"],
                source_verification=context.get("source_verification"),
                discussion_signals=context.get("discussion_signals"),
            )
            context[entry.produces] = ledger
        write_json(artifact_path, ledger.to_json())
        _record(records, module, ledger.status, reasons=ledger.status_reasons, artifact_path=artifact_path)
