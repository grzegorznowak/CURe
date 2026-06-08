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


__all__ = ["SubsequentReviewSourceTruthTests"]
