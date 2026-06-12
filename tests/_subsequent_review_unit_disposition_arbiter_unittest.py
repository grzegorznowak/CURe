# ruff: noqa: F403, F405
from _subsequent_review_test_support import *  # noqa: F401, F403


class SubsequentReviewDispositionArbiterTests(SubsequentReviewTestCase):
    def _reconciliation(self) -> Any:
        return reconcile_findings(findings=(self._finding_candidate(finding_id="A-01", title="Prior bug", severity="high"),))

    def _source_ledger(self, state: Any, *, provenance: dict[str, Any] | None = None) -> Any:
        from cure_subsequent_review.contracts import SourceVerificationLedger, SourceVerificationRow

        return SourceVerificationLedger(
            status=ModuleStatus.SUCCESS,
            rows=(
                SourceVerificationRow(
                    row_id="SV-0001",
                    group_id="G-0001",
                    finding_ids=("A-01",),
                    source_state=state,
                    current_source_citations=({"path": "app.py", "start_line": 1},),
                    provenance={"rationale": "source says " + state.value, **(provenance or {})},
                ),
            ),
        )

    def _signals(self, signal_class: Any, policy: EvidencePolicy = EvidencePolicy.TRUSTED) -> Any:
        from cure_subsequent_review.contracts import DiscussionSignalLedger, DiscussionSignalRow

        return DiscussionSignalLedger(
            status=ModuleStatus.SUCCESS,
            rows=(
                DiscussionSignalRow(
                    row_id="DS-0001",
                    event_id="C-01",
                    group_ids=("G-0001",),
                    finding_ids=("A-01",),
                    signal_class=signal_class,
                    evidence_policy=policy,
                    authority="maintainer" if policy is EvidencePolicy.TRUSTED else "author",
                    provenance={"rationale": "discussion signal"},
                ),
            ),
        )

    def test_action_matrix_is_limited_to_five_dispositions(self) -> None:
        from cure_subsequent_review.contracts import DiscussionSignalClass, DispositionAction, SourceState
        from cure_subsequent_review.disposition import arbitrate_dispositions

        cases = (
            (SourceState.RESOLVED_FROM_SOURCE, DiscussionSignalClass.DEVELOPER_CLAIM_FIXED, EvidencePolicy.UNTRUSTED, DispositionAction.CONFIRM_RESOLVED),
            (SourceState.PARTIALLY_RESOLVED, DiscussionSignalClass.DEVELOPER_CLAIM_FIXED, EvidencePolicy.UNTRUSTED, DispositionAction.REWORD_PARTIAL),
            (SourceState.STILL_OPEN, DiscussionSignalClass.DUPLICATE_SUPERSEDED, EvidencePolicy.TRUSTED, DispositionAction.SUPPRESS_DUPLICATE),
            (SourceState.STILL_OPEN, DiscussionSignalClass.ADDRESSED_ELSEWHERE, EvidencePolicy.TRUSTED, DispositionAction.MOVE_OUT_OF_SCOPE),
            (SourceState.STILL_OPEN, DiscussionSignalClass.PUSHBACK, EvidencePolicy.UNTRUSTED, DispositionAction.RE_REPORT),
        )
        for source_state, signal_class, policy, expected in cases:
            with self.subTest(expected=expected.value):
                ledger = arbitrate_dispositions(
                    reconciliation=self._reconciliation(),
                    source_verification=self._source_ledger(source_state),
                    discussion_signals=self._signals(signal_class, policy),
                )

                self.assertEqual(ledger.status, ModuleStatus.SUCCESS)
                self.assertEqual(ledger.dispositions[0].action, expected)
                self.assertIn(ledger.dispositions[0].action, set(DispositionAction))
                self.assertEqual(ledger.dispositions[0].source_verification_row_id, "SV-0001")
                self.assertEqual(ledger.dispositions[0].discussion_signal_row_ids, ("DS-0001",))
                self.assertEqual(ledger.dispositions[0].reconciliation_group_id, "G-0001")
                self.assertIn("rationale", ledger.dispositions[0].provenance)

    def test_footer_marker_policy_approved_prior_finding_moves_out_of_scope(self) -> None:
        from cure_subsequent_review.contracts import DiscussionSignalClass, DispositionAction, SourceState
        from cure_subsequent_review.disposition import arbitrate_dispositions

        ledger = arbitrate_dispositions(
            reconciliation=self._reconciliation(),
            source_verification=self._source_ledger(
                SourceState.RESOLVED_FROM_SOURCE,
                provenance={"policy_override": "official_footer_marker_acceptance"},
            ),
            discussion_signals=self._signals(DiscussionSignalClass.DEVELOPER_CLAIM_FIXED, EvidencePolicy.UNTRUSTED),
        )

        self.assertEqual(ledger.dispositions[0].action, DispositionAction.MOVE_OUT_OF_SCOPE)
        self.assertEqual(ledger.dispositions[0].provenance["source_state"], SourceState.RESOLVED_FROM_SOURCE.value)
        self.assertIn("footer", ledger.dispositions[0].provenance["rationale"])

    def test_source_open_developer_fixed_claim_is_re_reported(self) -> None:
        from cure_subsequent_review.contracts import DiscussionSignalClass, DispositionAction, SourceState
        from cure_subsequent_review.disposition import arbitrate_dispositions

        ledger = arbitrate_dispositions(
            reconciliation=self._reconciliation(),
            source_verification=self._source_ledger(SourceState.STILL_OPEN),
            discussion_signals=self._signals(DiscussionSignalClass.DEVELOPER_CLAIM_FIXED, EvidencePolicy.UNTRUSTED),
        )

        self.assertEqual(ledger.dispositions[0].action, DispositionAction.RE_REPORT)
        self.assertIn("source remains open", ledger.dispositions[0].provenance["rationale"])

    def test_simulation_derived_representative_golden_cases(self) -> None:
        from cure_subsequent_review.contracts import DiscussionSignalClass, DispositionAction, SourceState
        from cure_subsequent_review.disposition import arbitrate_dispositions

        fixture = json.loads((Path(__file__).parent / "fixtures" / "subsequent_review" / "simulation_raw.json").read_text(encoding="utf-8"))
        self.assertEqual({item["id"] for item in fixture["discussion"]}, {f"C-{index:02d}" for index in range(1, 11)})
        self.assertEqual({item["id"] for item in fixture["source_facts"]}, {f"S-{index:02d}" for index in range(1, 9)})

        golden = (
            ("source-confirmed", SourceState.RESOLVED_FROM_SOURCE, DiscussionSignalClass.DEVELOPER_CLAIM_FIXED, EvidencePolicy.UNTRUSTED, DispositionAction.CONFIRM_RESOLVED),
            ("partial-reword", SourceState.PARTIALLY_RESOLVED, DiscussionSignalClass.PUSHBACK, EvidencePolicy.UNTRUSTED, DispositionAction.REWORD_PARTIAL),
            ("trusted-duplicate", SourceState.STILL_OPEN, DiscussionSignalClass.DUPLICATE_SUPERSEDED, EvidencePolicy.TRUSTED, DispositionAction.SUPPRESS_DUPLICATE),
            ("external-scope", SourceState.STILL_OPEN, DiscussionSignalClass.ADDRESSED_ELSEWHERE, EvidencePolicy.TRUSTED, DispositionAction.MOVE_OUT_OF_SCOPE),
            ("weak-pushback", SourceState.STILL_OPEN, DiscussionSignalClass.PUSHBACK, EvidencePolicy.UNTRUSTED, DispositionAction.RE_REPORT),
        )
        for case_id, source_state, signal_class, policy, expected in golden:
            with self.subTest(case_id=case_id):
                ledger = arbitrate_dispositions(
                    reconciliation=self._reconciliation(),
                    source_verification=self._source_ledger(source_state),
                    discussion_signals=self._signals(signal_class, policy),
                )
                self.assertEqual(ledger.dispositions[0].action, expected)
                self.assertEqual(ledger.degraded_findings, ())

    def test_missing_or_degraded_dependency_goes_to_degraded_findings_without_action(self) -> None:
        from cure_subsequent_review.contracts import DiscussionSignalClass, SourceVerificationLedger
        from cure_subsequent_review.disposition import arbitrate_dispositions

        ledger = arbitrate_dispositions(
            reconciliation=self._reconciliation(),
            source_verification=SourceVerificationLedger(status=ModuleStatus.DEGRADED, rows=(), status_reasons=("provider_unavailable",)),
            discussion_signals=self._signals(DiscussionSignalClass.PUSHBACK),
        )

        self.assertEqual(ledger.status, ModuleStatus.DEGRADED)
        self.assertEqual(ledger.dispositions, ())
        self.assertEqual(ledger.degraded_findings[0].group_id, "G-0001")
        self.assertIn("provider_unavailable", ledger.degraded_findings[0].blocking_reasons)
        self.assertNotIn("action", ledger.degraded_findings[0].to_json())

    def test_degraded_source_dependency_with_partial_rows_blocks_actions(self) -> None:
        from cure_subsequent_review.contracts import DiscussionSignalClass, SourceState, SourceVerificationLedger
        from cure_subsequent_review.disposition import arbitrate_dispositions

        source = self._source_ledger(SourceState.RESOLVED_FROM_SOURCE)
        ledger = arbitrate_dispositions(
            reconciliation=self._reconciliation(),
            source_verification=SourceVerificationLedger(
                status=ModuleStatus.DEGRADED,
                rows=source.rows,
                status_reasons=("source_scan_incomplete",),
            ),
            discussion_signals=self._signals(DiscussionSignalClass.PUSHBACK),
        )

        self.assertEqual(ledger.status, ModuleStatus.DEGRADED)
        self.assertEqual(ledger.dispositions, ())
        self.assertEqual(ledger.degraded_findings[0].group_id, "G-0001")
        self.assertIn("source_scan_incomplete", ledger.degraded_findings[0].blocking_reasons)
        self.assertNotIn("action", ledger.degraded_findings[0].to_json())

    def test_degraded_discussion_dependency_with_trusted_partial_rows_blocks_actions(self) -> None:
        from cure_subsequent_review.contracts import DiscussionSignalClass, DiscussionSignalLedger, SourceState
        from cure_subsequent_review.disposition import arbitrate_dispositions

        signals = self._signals(DiscussionSignalClass.DUPLICATE_SUPERSEDED, EvidencePolicy.TRUSTED)
        ledger = arbitrate_dispositions(
            reconciliation=self._reconciliation(),
            source_verification=self._source_ledger(SourceState.STILL_OPEN),
            discussion_signals=DiscussionSignalLedger(
                status=ModuleStatus.DEGRADED,
                rows=signals.rows,
                status_reasons=("discussion_incomplete",),
            ),
        )

        self.assertEqual(ledger.status, ModuleStatus.DEGRADED)
        self.assertEqual(ledger.dispositions, ())
        self.assertEqual(ledger.degraded_findings[0].group_id, "G-0001")
        self.assertIn("discussion_incomplete", ledger.degraded_findings[0].blocking_reasons)
        self.assertNotIn("action", ledger.degraded_findings[0].to_json())


__all__ = ["SubsequentReviewDispositionArbiterTests"]
