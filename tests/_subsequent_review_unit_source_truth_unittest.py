# ruff: noqa: F403, F405
from _subsequent_review_test_support import *  # noqa: F401, F403


class SubsequentReviewSourceTruthTests(SubsequentReviewTestCase):
    def _group(self) -> tuple[Any, Any]:
        finding = self._finding_candidate(
            finding_id="A-01",
            title="Prior source bug",
            severity="high",
            evidence="src/app.py:10 old buggy branch",
        )
        reconciliation = reconcile_findings(findings=(finding,))
        return finding, reconciliation

    def test_verifier_uses_injected_provider_output_for_each_source_state(self) -> None:
        from cure_subsequent_review.contracts import SourceState
        from cure_subsequent_review.source_truth import FindingVerificationResult, verify_source_truth

        _finding, reconciliation = self._group()
        for state in SourceState:
            with self.subTest(state=state.value):
                requests: list[Any] = []

                def provider(request: Any) -> FindingVerificationResult:
                    requests.append(request)
                    return FindingVerificationResult(
                        source_state=state,
                        current_source_citations=(
                            {"path": "src/app.py", "start_line": 10, "end_line": 12, "summary": "checked current source"},
                        ),
                        rationale="provider classified current source",
                    )

                ledger = verify_source_truth(reconciliation=reconciliation, verifier=provider)

                self.assertEqual(ledger.status, ModuleStatus.SUCCESS)
                self.assertEqual(ledger.rows[0].source_state, state)
                self.assertEqual(ledger.rows[0].current_source_citations[0]["path"], "src/app.py")
                self.assertEqual(ledger.rows[0].provenance["rationale"], "provider classified current source")
                self.assertEqual(len(requests), 1)
                self.assertEqual(requests[0].group_id, "G-0001")
                self.assertIn("src/app.py:10", requests[0].source_evidence_snippets[0])
                self.assertFalse(hasattr(requests[0], "discussion_events"))

    def test_provider_failure_is_source_unknown_degraded_not_discussion_proof(self) -> None:
        from cure_subsequent_review.contracts import SourceState
        from cure_subsequent_review.source_truth import verify_source_truth

        _finding, reconciliation = self._group()

        def provider(_request: Any) -> Any:
            raise RuntimeError("provider unavailable")

        ledger = verify_source_truth(reconciliation=reconciliation, verifier=provider)

        self.assertEqual(ledger.status, ModuleStatus.DEGRADED)
        self.assertEqual(ledger.rows[0].source_state, SourceState.SOURCE_UNKNOWN)
        self.assertIn("provider_unavailable", ledger.status_reasons)
        self.assertIn("provider unavailable", ledger.rows[0].unavailable_reasons[0])

    def test_missing_source_refs_are_not_verifiable_without_provider_call(self) -> None:
        from cure_subsequent_review.contracts import SourceState
        from cure_subsequent_review.source_truth import verify_source_truth

        finding = self._finding_candidate(finding_id="A-02", title="No source refs", evidence="")
        reconciliation = reconcile_findings(findings=(finding,))
        provider_calls: list[Any] = []

        ledger = verify_source_truth(reconciliation=reconciliation, verifier=provider_calls.append)

        self.assertEqual(ledger.status, ModuleStatus.DEGRADED)
        self.assertEqual(ledger.rows[0].source_state, SourceState.NOT_VERIFIABLE)
        self.assertEqual(provider_calls, [])
        self.assertIn("missing_source_evidence", ledger.rows[0].unavailable_reasons)

    def test_official_footer_authorship_false_positive_is_policy_approved_without_provider_call(self) -> None:
        from cure_subsequent_review.contracts import SourceState
        from cure_subsequent_review.source_truth import FindingVerificationResult, verify_source_truth

        finding = self._finding_candidate(
            finding_id="CURE-001",
            title="Footer-marked PR comments and reviews are still accepted as prior CURe reviews without authenticated CURe provenance",
            evidence="cure_subsequent_review/prior_corpus.py:24",
        )
        reconciliation = reconcile_findings(findings=(finding,))
        provider_calls: list[Any] = []

        def provider(request: Any) -> FindingVerificationResult:
            provider_calls.append(request)
            return FindingVerificationResult(source_state=SourceState.STILL_OPEN, rationale="old false positive")

        ledger = verify_source_truth(reconciliation=reconciliation, verifier=provider)

        self.assertEqual(provider_calls, [])
        self.assertEqual(ledger.status, ModuleStatus.SUCCESS)
        self.assertEqual(ledger.rows[0].source_state, SourceState.RESOLVED_FROM_SOURCE)
        self.assertEqual(ledger.rows[0].provenance["policy_override"], "official_footer_marker_acceptance")
        self.assertIn("official CURe footer", ledger.rows[0].provenance["rationale"])
        self.assertIn("body-only", ledger.rows[0].current_source_citations[0]["summary"])

    def test_official_footer_policy_preempts_untrusted_skip_discussion(self) -> None:
        from cure_subsequent_review.contracts import (
            DiscussionSignalClass,
            DiscussionSignalLedger,
            DiscussionSignalRow,
            DispositionAction,
            EvidencePolicy,
            SourceState,
        )
        from cure_subsequent_review.disposition import arbitrate_dispositions
        from cure_subsequent_review.source_truth import FindingVerificationResult, verify_source_truth

        finding = self._finding_candidate(
            finding_id="CURE-001",
            title="Footer-marked PR comments are accepted without authenticated CURe authorship provenance",
            evidence="cure_subsequent_review/prior_corpus.py:24",
        )
        reconciliation = reconcile_findings(findings=(finding,))
        discussion = DiscussionSignalLedger(
            status=ModuleStatus.SUCCESS,
            rows=(
                DiscussionSignalRow(
                    row_id="DS-0001",
                    event_id="C-01",
                    group_ids=("G-0001",),
                    finding_ids=("CURE-001",),
                    signal_class=DiscussionSignalClass.PUSHBACK,
                    evidence_policy=EvidencePolicy.UNTRUSTED,
                    authority="developer",
                    reasons=("operator_pushback",),
                    provenance={"rationale": "untrusted pushback is discussion context, not source truth"},
                ),
            ),
        )
        provider_calls: list[Any] = []

        def provider(request: Any) -> FindingVerificationResult:
            provider_calls.append(request)
            return FindingVerificationResult(source_state=SourceState.STILL_OPEN, rationale="would re-report if called")

        ledger = verify_source_truth(reconciliation=reconciliation, verifier=provider, discussion_signals=discussion)
        disposition = arbitrate_dispositions(
            reconciliation=reconciliation,
            source_verification=ledger,
            discussion_signals=discussion,
        )

        self.assertEqual(provider_calls, [])
        self.assertEqual(ledger.rows[0].source_state, SourceState.RESOLVED_FROM_SOURCE)
        self.assertEqual(ledger.rows[0].provenance["policy_override"], "official_footer_marker_acceptance")
        self.assertNotIn("source_verification_skipped_by_discussion_signals", ledger.rows[0].unavailable_reasons)
        self.assertEqual(disposition.dispositions[0].action, DispositionAction.MOVE_OUT_OF_SCOPE)

    def test_body_only_cure_text_finding_still_uses_source_verifier(self) -> None:
        from cure_subsequent_review.contracts import (
            DiscussionSignalClass,
            DiscussionSignalLedger,
            DiscussionSignalRow,
            EvidencePolicy,
            SourceState,
        )
        from cure_subsequent_review.source_truth import FindingVerificationResult, verify_source_truth

        finding = self._finding_candidate(
            finding_id="CURE-002",
            title="Generic body-only CURe-looking PR comments are accepted as prior reviews without official footer",
            evidence="cure_subsequent_review/prior_corpus.py:117",
        )
        reconciliation = reconcile_findings(findings=(finding,))
        discussion = DiscussionSignalLedger(
            status=ModuleStatus.SUCCESS,
            rows=(
                DiscussionSignalRow(
                    row_id="DS-0001",
                    event_id="C-01",
                    group_ids=("G-0001",),
                    finding_ids=("CURE-002",),
                    signal_class=DiscussionSignalClass.DEVELOPER_CLAIM_FIXED,
                    evidence_policy=EvidencePolicy.UNTRUSTED,
                    authority="developer",
                    reasons=("linked_by_llm",),
                    provenance={},
                ),
            ),
        )
        provider_calls: list[Any] = []

        def provider(request: Any) -> FindingVerificationResult:
            provider_calls.append(request)
            return FindingVerificationResult(source_state=SourceState.STILL_OPEN, rationale="body-only text is still rejected")

        ledger = verify_source_truth(reconciliation=reconciliation, verifier=provider, discussion_signals=discussion)

        self.assertEqual([request.group_id for request in provider_calls], ["G-0001"])
        self.assertEqual(ledger.rows[0].source_state, SourceState.STILL_OPEN)
        self.assertEqual(provider_calls[0].discussion_signals[0]["row_id"], "DS-0001")
        self.assertNotIn("policy_override", ledger.rows[0].provenance)

    def test_verifier_fanout_observability_records_call_counts_cache_and_timing(self) -> None:
        from cure_subsequent_review.contracts import SourceState
        from cure_subsequent_review.source_truth import FindingVerificationResult, verify_source_truth

        first = self._finding_candidate(finding_id="A-01", title="First prior bug", evidence="src/app.py:10")
        second = self._finding_candidate(finding_id="A-02", title="Second prior bug", evidence="src/other.py:20")
        reconciliation = reconcile_findings(findings=(first, second))
        provider_calls: list[Any] = []

        def provider(request: Any) -> FindingVerificationResult:
            provider_calls.append(request)
            return FindingVerificationResult(source_state=SourceState.STILL_OPEN, rationale="checked source")

        ledger = verify_source_truth(reconciliation=reconciliation, verifier=provider)

        fanout = ledger.observability["verifier_fanout"]
        self.assertEqual([request.group_id for request in provider_calls], ["G-0001", "G-0002"])
        self.assertEqual(fanout["group_count"], 2)
        self.assertEqual(fanout["provider_call_count"], 2)
        self.assertEqual(fanout["cache"]["bypass_count"], 2)
        self.assertEqual(fanout["cache"]["bypass_reasons"]["memory_store_unavailable"], 2)
        self.assertIn("elapsed_seconds", fanout["timing"])
        self.assertIn("provider_seconds", fanout["timing"])

    def test_variant_c_request_includes_changed_files_and_linked_discussion_signals(self) -> None:
        from cure_subsequent_review.contracts import (
            DiscussionSignalClass,
            DiscussionSignalLedger,
            DiscussionSignalRow,
            EvidencePolicy,
            SourceState,
        )
        from cure_subsequent_review.source_truth import FindingVerificationResult, verify_source_truth

        _finding, reconciliation = self._group()
        requests: list[Any] = []
        discussion_signals = DiscussionSignalLedger(
            status=ModuleStatus.SUCCESS,
            rows=(
                DiscussionSignalRow(
                    row_id="DS-0001",
                    event_id="C-01",
                    group_ids=("G-0001",),
                    finding_ids=("A-01",),
                    signal_class=DiscussionSignalClass.DEVELOPER_CLAIM_FIXED,
                    evidence_policy=EvidencePolicy.UNTRUSTED,
                    authority="developer",
                    reasons=("linked_by_llm",),
                    provenance={"rationale": "developer claims a fix"},
                ),
            ),
        )

        def provider(request: Any) -> FindingVerificationResult:
            requests.append(request)
            return FindingVerificationResult(source_state=SourceState.STILL_OPEN)

        verify_source_truth(
            reconciliation=reconciliation,
            verifier=provider,
            discussion_signals=discussion_signals,
            pr_files_changed=("src/app.py", "tests/test_app.py"),
        )

        self.assertEqual(requests[0].pr_files_changed, ("src/app.py", "tests/test_app.py"))
        self.assertEqual(requests[0].discussion_signals[0]["row_id"], "DS-0001")
        self.assertEqual(requests[0].discussion_signals[0]["signal_class"], "developer_claim_fixed")
        self.assertEqual(requests[0].discussion_signals[0]["provenance"]["rationale"], "developer claims a fix")


__all__ = ["SubsequentReviewSourceTruthTests"]
