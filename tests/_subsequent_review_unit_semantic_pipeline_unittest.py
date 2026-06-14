# ruff: noqa: F403, F405
from _subsequent_review_test_support import *  # noqa: F401, F403


class SubsequentReviewSemanticPipelineTests(SubsequentReviewTestCase):
    def _reconciliation(self) -> Any:
        return reconcile_findings(
            findings=(
                self._finding_candidate(finding_id="A-01", title="Prior bug", evidence="src/app.py:10"),
                self._finding_candidate(finding_id="B-01", title="Second bug", evidence="src/app.py:20"),
            )
        )

    def test_discussion_resolver_runs_before_source_truth_verifier(self) -> None:
        from cure_subsequent_review.contracts import SubsequentReviewModule
        from cure_subsequent_review.semantic_pipeline import MODULE_REGISTRY

        order = tuple(MODULE_REGISTRY)

        self.assertLess(
            order.index(SubsequentReviewModule.DISCUSSION_SIGNAL_RESOLVER),
            order.index(SubsequentReviewModule.SOURCE_TRUTH_VERIFIER),
        )

    def test_untrusted_skip_class_discussion_filters_group_before_verifier(self) -> None:
        from cure_subsequent_review.contracts import (
            DiscussionSignalClass,
            DiscussionSignalLedger,
            DiscussionSignalRow,
            EvidencePolicy,
            SourceState,
        )
        from cure_subsequent_review.source_truth import FindingVerificationResult, verify_source_truth

        reconciliation = self._reconciliation()
        discussion_signals = DiscussionSignalLedger(
            status=ModuleStatus.SUCCESS,
            rows=(
                DiscussionSignalRow(
                    row_id="DS-0001",
                    event_id="C-01",
                    group_ids=("G-0001",),
                    finding_ids=("A-01",),
                    signal_class=DiscussionSignalClass.PUSHBACK,
                    evidence_policy=EvidencePolicy.UNTRUSTED,
                    authority="participant",
                ),
                DiscussionSignalRow(
                    row_id="DS-0002",
                    event_id="C-02",
                    group_ids=("G-0001",),
                    finding_ids=("A-01",),
                    signal_class=DiscussionSignalClass.BY_DESIGN,
                    evidence_policy=EvidencePolicy.UNTRUSTED,
                    authority="participant",
                ),
            ),
        )
        calls: list[str] = []

        def provider(request: Any) -> FindingVerificationResult:
            calls.append(request.group_id)
            return FindingVerificationResult(source_state=SourceState.STILL_OPEN, rationale="checked source")

        ledger = verify_source_truth(
            reconciliation=reconciliation,
            verifier=provider,
            discussion_signals=discussion_signals,
        )

        by_group = {row.group_id: row for row in ledger.rows}
        self.assertEqual(calls, ["G-0002"])
        self.assertEqual(by_group["G-0001"].source_state, SourceState.STILL_OPEN)
        self.assertEqual(by_group["G-0001"].unavailable_reasons, ("source_verification_skipped_by_discussion_signals",))
        self.assertEqual(by_group["G-0001"].provenance["discussion_signal_row_ids"], ["DS-0001", "DS-0002"])
        self.assertEqual(by_group["G-0002"].provenance["rationale"], "checked source")

    def test_trusted_or_verify_class_discussion_keeps_group_in_verifier(self) -> None:
        from cure_subsequent_review.contracts import (
            DiscussionSignalClass,
            DiscussionSignalLedger,
            DiscussionSignalRow,
            EvidencePolicy,
            SourceState,
        )
        from cure_subsequent_review.source_truth import FindingVerificationResult, verify_source_truth

        reconciliation = self._reconciliation()
        discussion_signals = DiscussionSignalLedger(
            status=ModuleStatus.SUCCESS,
            rows=(
                DiscussionSignalRow(
                    row_id="DS-0001",
                    event_id="C-01",
                    group_ids=("G-0001",),
                    finding_ids=("A-01",),
                    signal_class=DiscussionSignalClass.PUSHBACK,
                    evidence_policy=EvidencePolicy.TRUSTED,
                    authority="maintainer",
                ),
                DiscussionSignalRow(
                    row_id="DS-0002",
                    event_id="C-02",
                    group_ids=("G-0002",),
                    finding_ids=("B-01",),
                    signal_class=DiscussionSignalClass.DEVELOPER_CLAIM_FIXED,
                    evidence_policy=EvidencePolicy.UNTRUSTED,
                    authority="author",
                ),
            ),
        )
        calls: list[str] = []

        def provider(request: Any) -> FindingVerificationResult:
            calls.append(request.group_id)
            return FindingVerificationResult(source_state=SourceState.STILL_OPEN, rationale="checked source")

        ledger = verify_source_truth(
            reconciliation=reconciliation,
            verifier=provider,
            discussion_signals=discussion_signals,
        )

        self.assertEqual(calls, ["G-0001", "G-0002"])
        self.assertTrue(all(row.provenance["rationale"] == "checked source" for row in ledger.rows))


__all__ = ["SubsequentReviewSemanticPipelineTests"]
