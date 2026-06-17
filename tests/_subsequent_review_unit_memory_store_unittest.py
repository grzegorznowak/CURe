# ruff: noqa: F403, F405
from _subsequent_review_test_support import *  # noqa: F401, F403


class SubsequentReviewMemoryStoreTests(SubsequentReviewTestCase):
    def _source_ledger(
        self,
        *,
        state: Any,
        group_id: str = "G-0001",
        finding_id: str = "A-01",
        fingerprint: str = "",
        source_ref: str = "app.py:10",
        provenance: dict[str, Any] | None = None,
    ) -> Any:
        from cure_subsequent_review.contracts import SourceVerificationLedger, SourceVerificationRow

        return SourceVerificationLedger(
            status=ModuleStatus.SUCCESS,
            rows=(
                SourceVerificationRow(
                    row_id="SV-0001",
                    group_id=group_id,
                    finding_ids=(finding_id,),
                    source_state=state,
                    current_source_citations=({"path": source_ref.split(":", 1)[0], "start_line": int(source_ref.split(":", 1)[1]), "summary": "fixed"},),
                    inspected_source_refs=(source_ref,),
                    provenance={"rationale": "source checked", "fingerprint": fingerprint, **dict(provenance or {})},
                ),
            ),
        )

    def _disposition_ledger(self, *, action: Any, group_id: str = "G-0001", finding_id: str = "A-01") -> Any:
        from cure_subsequent_review.contracts import DispositionLedger, DispositionRow

        return DispositionLedger(
            status=ModuleStatus.SUCCESS,
            dispositions=(
                DispositionRow(
                    row_id="D-0001",
                    group_id=group_id,
                    finding_ids=(finding_id,),
                    action=action,
                    source_verification_row_id="SV-0001",
                    discussion_signal_row_ids=(),
                    reconciliation_group_id=group_id,
                    provenance={"rationale": "confirmed"},
                ),
            ),
        )

    def test_memory_store_persists_per_pr_finding_state_independent_of_sandbox(self) -> None:
        from cure_subsequent_review.contracts import DispositionAction, SourceState
        from cure_subsequent_review.memory_store import ReviewMemoryStore

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "pr"
            store = ReviewMemoryStore.for_pr(root=root, pr=PR())

            store.update_findings(
                current_head="abc123",
                source_verification=self._source_ledger(state=SourceState.RESOLVED_FROM_SOURCE),
                disposition_ledger=self._disposition_ledger(action=DispositionAction.CONFIRM_RESOLVED),
                run_provenance={"session_id": "run-1"},
            )

            payload = json.loads(store.path.read_text(encoding="utf-8"))
            self.assertEqual(store.path, root / "github.com" / "example" / "demo" / "9999" / "cure_memory.json")
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["findings"]["G-0001"]["source_state"], "resolved_from_source")
            self.assertEqual(payload["findings"]["G-0001"]["disposition"], "confirm_resolved")
            self.assertEqual(payload["findings"]["G-0001"]["last_seen_head"], "abc123")
            self.assertEqual(payload["findings"]["G-0001"]["run_provenance"]["session_id"], "run-1")

            store.update_findings(
                current_head="def456",
                source_verification=self._source_ledger(state=SourceState.STILL_OPEN),
                disposition_ledger=self._disposition_ledger(action=DispositionAction.RE_REPORT),
                run_provenance={"session_id": "run-2"},
            )
            updated = json.loads(store.path.read_text(encoding="utf-8"))["findings"]["G-0001"]
            self.assertEqual(updated["source_state"], "still_open")
            self.assertEqual(updated["disposition"], "re_report")
            self.assertEqual(updated["last_seen_head"], "def456")
            self.assertEqual(updated["previous_heads"], ["abc123"])
            self.assertEqual(updated["heads"]["abc123"]["source_state"], "resolved_from_source")
            self.assertEqual(updated["heads"]["def456"]["source_state"], "still_open")

    def test_matching_head_resolved_findings_are_synthesized_without_provider_call(self) -> None:
        from cure_subsequent_review.contracts import DispositionAction, SourceState
        from cure_subsequent_review.memory_store import ReviewMemoryStore
        from cure_subsequent_review.source_truth import FindingVerificationResult, verify_source_truth

        first = self._finding_candidate(finding_id="A-01", title="fixed finding", evidence="app.py:10")
        second = self._finding_candidate(finding_id="A-02", title="stale finding", evidence="app.py:20")
        reconciliation = reconcile_findings(findings=(first, second))

        with tempfile.TemporaryDirectory() as tmp:
            store = ReviewMemoryStore(path=Path(tmp) / "cure_memory.json")
            store.update_findings(
                current_head="head-ok",
                source_verification=self._source_ledger(
                    state=SourceState.RESOLVED_FROM_SOURCE,
                    group_id="G-0001",
                    finding_id="A-01",
                    fingerprint=reconciliation.groups[0].fingerprint,
                ),
                disposition_ledger=self._disposition_ledger(action=DispositionAction.CONFIRM_RESOLVED, group_id="G-0001", finding_id="A-01"),
                run_provenance={"session_id": "run-1"},
            )
            provider_calls: list[Any] = []

            def provider(request: Any) -> FindingVerificationResult:
                provider_calls.append(request)
                return FindingVerificationResult(source_state=SourceState.STILL_OPEN, rationale="fresh check")

            ledger = verify_source_truth(
                reconciliation=reconciliation,
                verifier=provider,
                memory_store=store,
                current_head="head-ok",
            )

            self.assertEqual([row.group_id for row in ledger.rows], ["G-0001", "G-0002"])
            self.assertEqual(ledger.rows[0].source_state, SourceState.RESOLVED_FROM_SOURCE)
            self.assertEqual(ledger.rows[0].provenance["source"], "memory_cache")
            self.assertEqual(ledger.rows[0].provenance["not_source_proof"], True)
            self.assertEqual([call.group_id for call in provider_calls], ["G-0002"])
            self.assertEqual(ledger.observability["verifier_fanout"]["provider_call_count"], 1)
            self.assertEqual(ledger.observability["verifier_fanout"]["cache"]["hit_count"], 1)
            self.assertEqual(ledger.observability["verifier_fanout"]["cache"]["miss_count"], 1)

            provider_calls.clear()
            stale = verify_source_truth(
                reconciliation=reconciliation,
                verifier=provider,
                memory_store=store,
                current_head="different-head",
            )
            self.assertEqual([call.group_id for call in provider_calls], ["G-0001", "G-0002"])
            self.assertNotEqual(stale.rows[0].provenance.get("source"), "memory_cache")

    def test_policy_approved_footer_replay_preserves_provenance_and_disposition(self) -> None:
        from cure_subsequent_review.contracts import (
            DiscussionSignalLedger,
            DispositionAction,
            SourceState,
        )
        from cure_subsequent_review.disposition import arbitrate_dispositions
        from cure_subsequent_review.memory_store import ReviewMemoryStore
        from cure_subsequent_review.source_truth import FindingVerificationResult, verify_source_truth

        finding = self._finding_candidate(
            finding_id="CURE-001",
            title="Footer-marked PR comments are accepted without authenticated CURe authorship provenance",
            evidence="cure_subsequent_review/prior_corpus.py:24",
        )
        reconciliation = reconcile_findings(findings=(finding,))
        discussion = DiscussionSignalLedger(status=ModuleStatus.SUCCESS)

        with tempfile.TemporaryDirectory() as tmp:
            store = ReviewMemoryStore(path=Path(tmp) / "cure_memory.json")
            fresh = verify_source_truth(
                reconciliation=reconciliation,
                verifier=lambda _request: FindingVerificationResult(source_state=SourceState.STILL_OPEN),
                memory_store=store,
                current_head="head-ok",
            )
            fresh_disposition = arbitrate_dispositions(
                reconciliation=reconciliation,
                source_verification=fresh,
                discussion_signals=discussion,
            )
            self.assertEqual(fresh.rows[0].provenance["policy_override"], "official_footer_marker_acceptance")
            self.assertEqual(fresh_disposition.dispositions[0].action, DispositionAction.MOVE_OUT_OF_SCOPE)
            store.update_findings(
                current_head="head-ok",
                source_verification=fresh,
                disposition_ledger=fresh_disposition,
            )

            provider_calls: list[Any] = []

            def provider(request: Any) -> FindingVerificationResult:
                provider_calls.append(request)
                return FindingVerificationResult(source_state=SourceState.STILL_OPEN, rationale="would re-report if called")

            replayed = verify_source_truth(
                reconciliation=reconciliation,
                verifier=provider,
                memory_store=store,
                current_head="head-ok",
            )
            replayed_disposition = arbitrate_dispositions(
                reconciliation=reconciliation,
                source_verification=replayed,
                discussion_signals=discussion,
            )

            self.assertEqual(provider_calls, [])
            self.assertEqual(replayed.rows[0].provenance["source"], "memory_cache")
            self.assertEqual(replayed.rows[0].provenance["policy_override"], "official_footer_marker_acceptance")
            self.assertEqual(replayed_disposition.dispositions[0].action, DispositionAction.MOVE_OUT_OF_SCOPE)

    def test_resolved_replay_rejects_same_ordinal_group_with_different_finding_identity(self) -> None:
        from cure_subsequent_review.contracts import DispositionAction, SourceState
        from cure_subsequent_review.memory_store import ReviewMemoryStore

        with tempfile.TemporaryDirectory() as tmp:
            store = ReviewMemoryStore(path=Path(tmp) / "cure_memory.json")
            store.update_findings(
                current_head="head-a",
                source_verification=self._source_ledger(
                    state=SourceState.RESOLVED_FROM_SOURCE,
                    group_id="G-0001",
                    finding_id="A-01",
                ),
                disposition_ledger=self._disposition_ledger(
                    action=DispositionAction.CONFIRM_RESOLVED,
                    group_id="G-0001",
                    finding_id="A-01",
                ),
            )

            row = store.synthesize_resolved_source_row(
                group_id="G-0001",
                finding_ids=("B-99",),
                row_id="SV-0001",
                current_head="head-a",
            )

            self.assertIsNone(row)

    def test_resolved_replay_requires_top_level_last_seen_head_match(self) -> None:
        from cure_subsequent_review.contracts import DispositionAction, SourceState
        from cure_subsequent_review.memory_store import ReviewMemoryStore

        with tempfile.TemporaryDirectory() as tmp:
            store = ReviewMemoryStore(path=Path(tmp) / "cure_memory.json")
            store.update_findings(
                current_head="head-a",
                source_verification=self._source_ledger(state=SourceState.RESOLVED_FROM_SOURCE),
                disposition_ledger=self._disposition_ledger(action=DispositionAction.CONFIRM_RESOLVED),
                run_provenance={"session_id": "run-a"},
            )
            store.update_findings(
                current_head="head-b",
                source_verification=self._source_ledger(state=SourceState.STILL_OPEN),
                disposition_ledger=self._disposition_ledger(action=DispositionAction.RE_REPORT),
                run_provenance={"session_id": "run-b"},
            )

            row = store.synthesize_resolved_source_row(
                group_id="G-0001",
                finding_ids=("A-01",),
                row_id="SV-0099",
                current_head="head-a",
            )

            self.assertIsNone(row)

    def test_terminal_non_reportable_replay_uses_stable_identity_and_marks_not_source_proof(self) -> None:
        from cure_subsequent_review.contracts import DispositionAction, SourceState
        from cure_subsequent_review.memory_store import ReviewMemoryStore
        from cure_subsequent_review.source_truth import FindingVerificationResult, verify_source_truth

        finding = self._finding_candidate(finding_id="A-01", title="duplicate finding", evidence="app.py:10")
        reconciliation = reconcile_findings(findings=(finding,))

        with tempfile.TemporaryDirectory() as tmp:
            store = ReviewMemoryStore(path=Path(tmp) / "cure_memory.json")
            store.update_findings(
                current_head="head-ok",
                source_verification=self._source_ledger(
                    state=SourceState.STILL_OPEN,
                    group_id="G-0001",
                    finding_id="A-01",
                    fingerprint=reconciliation.groups[0].fingerprint,
                ),
                disposition_ledger=self._disposition_ledger(
                    action=DispositionAction.SUPPRESS_DUPLICATE,
                    group_id="G-0001",
                    finding_id="A-01",
                ),
            )
            provider_calls: list[Any] = []

            def provider(request: Any) -> FindingVerificationResult:
                provider_calls.append(request)
                return FindingVerificationResult(source_state=SourceState.STILL_OPEN, rationale="fresh check")

            ledger = verify_source_truth(
                reconciliation=reconciliation,
                verifier=provider,
                memory_store=store,
                current_head="head-ok",
            )

            self.assertEqual(provider_calls, [])
            self.assertEqual(ledger.rows[0].source_state, SourceState.STILL_OPEN)
            self.assertEqual(ledger.rows[0].provenance["source"], "memory_cache")
            self.assertEqual(ledger.rows[0].provenance["cache_status"], "hit")
            self.assertEqual(ledger.rows[0].provenance["cache_reason"], "terminal_non_reportable_replay")
            self.assertEqual(ledger.rows[0].provenance["cached_disposition"], "suppress_duplicate")
            self.assertEqual(ledger.rows[0].provenance["not_source_proof"], True)

    def test_terminal_replay_matrix_only_replays_safe_outcomes(self) -> None:
        from cure_subsequent_review.contracts import DispositionAction, SourceState
        from cure_subsequent_review.memory_store import ReviewMemoryStore
        from cure_subsequent_review.source_truth import FindingVerificationResult, verify_source_truth

        cases = (
            ("resolved_from_source", SourceState.RESOLVED_FROM_SOURCE, DispositionAction.CONFIRM_RESOLVED, True, "resolved_from_source_replay"),
            ("duplicate", SourceState.STILL_OPEN, DispositionAction.SUPPRESS_DUPLICATE, True, "terminal_non_reportable_replay"),
            ("out_of_scope", SourceState.STILL_OPEN, DispositionAction.MOVE_OUT_OF_SCOPE, True, "terminal_non_reportable_replay"),
            ("dropped_not_relevant", SourceState.STILL_OPEN, DispositionAction.MOVE_OUT_OF_SCOPE, True, "terminal_non_reportable_replay"),
            ("still_open_reportable", SourceState.STILL_OPEN, DispositionAction.RE_REPORT, False, ""),
            ("source_unknown", SourceState.SOURCE_UNKNOWN, DispositionAction.SUPPRESS_DUPLICATE, False, ""),
            ("not_verifiable", SourceState.NOT_VERIFIABLE, DispositionAction.MOVE_OUT_OF_SCOPE, False, ""),
        )
        for label, cached_state, cached_action, should_replay, expected_reason in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                current = self._finding_candidate(finding_id="A-01", title=f"{label} finding", evidence="app.py:10")
                reconciliation = reconcile_findings(findings=(current,))
                store = ReviewMemoryStore(path=Path(tmp) / "cure_memory.json")
                store.update_findings(
                    current_head="head-ok",
                    source_verification=self._source_ledger(
                        state=cached_state,
                        group_id="G-0001",
                        finding_id="A-01",
                        fingerprint=reconciliation.groups[0].fingerprint,
                    ),
                    disposition_ledger=self._disposition_ledger(
                        action=cached_action,
                        group_id="G-0001",
                        finding_id="A-01",
                    ),
                )
                provider_calls: list[Any] = []

                def provider(request: Any) -> FindingVerificationResult:
                    provider_calls.append(request)
                    return FindingVerificationResult(source_state=SourceState.STILL_OPEN, rationale="fresh verification")

                ledger = verify_source_truth(
                    reconciliation=reconciliation,
                    verifier=provider,
                    memory_store=store,
                    current_head="head-ok",
                )

                if should_replay:
                    self.assertEqual(provider_calls, [])
                    self.assertEqual(ledger.rows[0].provenance["source"], "memory_cache")
                    self.assertEqual(ledger.rows[0].provenance["cache_reason"], expected_reason)
                    if cached_state is not SourceState.RESOLVED_FROM_SOURCE:
                        self.assertEqual(ledger.rows[0].provenance["not_source_proof"], True)
                        self.assertEqual(ledger.rows[0].source_state, SourceState.STILL_OPEN)
                    else:
                        self.assertEqual(ledger.rows[0].source_state, SourceState.RESOLVED_FROM_SOURCE)
                else:
                    self.assertEqual([call.group_id for call in provider_calls], ["G-0001"])
                    self.assertNotEqual(ledger.rows[0].provenance.get("source"), "memory_cache")
                    self.assertEqual(ledger.rows[0].provenance["cache_status"], "miss")
                    self.assertNotIn("not_source_proof", ledger.rows[0].provenance)

    def test_stable_identity_can_hit_after_reordered_group_id(self) -> None:
        from cure_subsequent_review.contracts import DispositionAction, SourceState
        from cure_subsequent_review.memory_store import ReviewMemoryStore
        from cure_subsequent_review.source_truth import FindingVerificationResult, verify_source_truth

        current = self._finding_candidate(finding_id="A-01", title="stable finding", evidence="app.py:10")
        reconciliation = reconcile_findings(findings=(current,))

        with tempfile.TemporaryDirectory() as tmp:
            store = ReviewMemoryStore(path=Path(tmp) / "cure_memory.json")
            store.update_findings(
                current_head="head-ok",
                source_verification=self._source_ledger(
                    state=SourceState.RESOLVED_FROM_SOURCE,
                    group_id="G-0099",
                    finding_id="A-01",
                    fingerprint=reconciliation.groups[0].fingerprint,
                ),
                disposition_ledger=self._disposition_ledger(
                    action=DispositionAction.CONFIRM_RESOLVED,
                    group_id="G-0099",
                    finding_id="A-01",
                ),
            )
            provider_calls: list[Any] = []

            def provider(request: Any) -> FindingVerificationResult:
                provider_calls.append(request)
                return FindingVerificationResult(source_state=SourceState.STILL_OPEN, rationale="fresh check")

            ledger = verify_source_truth(
                reconciliation=reconciliation,
                verifier=provider,
                memory_store=store,
                current_head="head-ok",
            )

            self.assertEqual(provider_calls, [])
            self.assertEqual(ledger.rows[0].group_id, "G-0001")
            self.assertEqual(ledger.rows[0].provenance["cached_group_id"], "G-0099")
            self.assertEqual(ledger.rows[0].provenance["cache_status"], "hit")
            self.assertEqual(ledger.rows[0].source_state, SourceState.RESOLVED_FROM_SOURCE)

    def test_persisting_replayed_row_preserves_stable_identity_for_next_same_head_run(self) -> None:
        from cure_subsequent_review.contracts import DispositionAction, SourceState
        from cure_subsequent_review.memory_store import ReviewMemoryStore
        from cure_subsequent_review.source_truth import FindingVerificationResult, verify_source_truth

        current = self._finding_candidate(finding_id="A-01", title="stable replay finding", evidence="app.py:10")
        reconciliation = reconcile_findings(findings=(current,))

        with tempfile.TemporaryDirectory() as tmp:
            store = ReviewMemoryStore(path=Path(tmp) / "cure_memory.json")
            store.update_findings(
                current_head="head-ok",
                source_verification=self._source_ledger(
                    state=SourceState.RESOLVED_FROM_SOURCE,
                    group_id="G-0001",
                    finding_id="A-01",
                    fingerprint=reconciliation.groups[0].fingerprint,
                ),
                disposition_ledger=self._disposition_ledger(action=DispositionAction.CONFIRM_RESOLVED),
            )

            first_replay = verify_source_truth(
                reconciliation=reconciliation,
                verifier=lambda _request: FindingVerificationResult(source_state=SourceState.STILL_OPEN),
                memory_store=store,
                current_head="head-ok",
            )
            self.assertEqual(first_replay.rows[0].provenance["source"], "memory_cache")

            store.update_findings(
                current_head="head-ok",
                source_verification=first_replay,
                disposition_ledger=self._disposition_ledger(action=DispositionAction.CONFIRM_RESOLVED),
            )
            persisted = json.loads(store.path.read_text(encoding="utf-8"))["findings"]["G-0001"]
            self.assertEqual(persisted["stable_identity"]["fingerprint"], reconciliation.groups[0].fingerprint)

            provider_calls: list[Any] = []

            def provider(request: Any) -> FindingVerificationResult:
                provider_calls.append(request)
                return FindingVerificationResult(source_state=SourceState.STILL_OPEN, rationale="should not be called")

            second_replay = verify_source_truth(
                reconciliation=reconciliation,
                verifier=provider,
                memory_store=store,
                current_head="head-ok",
            )

            self.assertEqual(provider_calls, [])
            self.assertEqual(second_replay.rows[0].provenance["source"], "memory_cache")

    def test_replay_persisted_row_with_changed_source_reference_misses_cache(self) -> None:
        from cure_subsequent_review.contracts import DispositionAction, SourceState
        from cure_subsequent_review.memory_store import ReviewMemoryStore
        from cure_subsequent_review.source_truth import FindingVerificationResult, verify_source_truth

        cached = self._finding_candidate(finding_id="A-01", title="same finding title", evidence="app.py:10")
        cached_reconciliation = reconcile_findings(findings=(cached,))
        changed_source = self._finding_candidate(finding_id="A-01", title="same finding title", evidence="app.py:44")
        changed_reconciliation = reconcile_findings(findings=(changed_source,))

        with tempfile.TemporaryDirectory() as tmp:
            store = ReviewMemoryStore(path=Path(tmp) / "cure_memory.json")
            store.update_findings(
                current_head="head-ok",
                source_verification=self._source_ledger(
                    state=SourceState.RESOLVED_FROM_SOURCE,
                    group_id="G-0001",
                    finding_id="A-01",
                    fingerprint=cached_reconciliation.groups[0].fingerprint,
                    source_ref="app.py:10",
                ),
                disposition_ledger=self._disposition_ledger(action=DispositionAction.CONFIRM_RESOLVED),
            )

            first_replay = verify_source_truth(
                reconciliation=cached_reconciliation,
                verifier=lambda _request: FindingVerificationResult(source_state=SourceState.STILL_OPEN),
                memory_store=store,
                current_head="head-ok",
            )
            self.assertEqual(first_replay.rows[0].provenance["source"], "memory_cache")

            store.update_findings(
                current_head="head-ok",
                source_verification=first_replay,
                disposition_ledger=self._disposition_ledger(action=DispositionAction.CONFIRM_RESOLVED),
            )

            provider_calls: list[Any] = []

            def provider(request: Any) -> FindingVerificationResult:
                provider_calls.append(request)
                return FindingVerificationResult(source_state=SourceState.STILL_OPEN, rationale="fresh source reference check")

            ledger = verify_source_truth(
                reconciliation=changed_reconciliation,
                verifier=provider,
                memory_store=store,
                current_head="head-ok",
            )

            self.assertEqual([call.group_id for call in provider_calls], ["G-0001"])
            self.assertEqual(ledger.rows[0].provenance["cache_status"], "miss")
            self.assertEqual(ledger.rows[0].provenance["cache_reason"], "stable_identity_mismatch")

    def test_repeated_display_id_with_different_stable_identity_misses_cache(self) -> None:
        from cure_subsequent_review.contracts import DispositionAction, SourceState
        from cure_subsequent_review.memory_store import ReviewMemoryStore
        from cure_subsequent_review.source_truth import FindingVerificationResult, verify_source_truth

        cached = self._finding_candidate(finding_id="A-01", title="cached display id finding", evidence="app.py:10")
        cached_reconciliation = reconcile_findings(findings=(cached,))
        current = self._finding_candidate(finding_id="A-01", title="new repeated display id finding", evidence="worker.py:30")
        current_reconciliation = reconcile_findings(findings=(current,))

        with tempfile.TemporaryDirectory() as tmp:
            store = ReviewMemoryStore(path=Path(tmp) / "cure_memory.json")
            store.update_findings(
                current_head="head-ok",
                source_verification=self._source_ledger(
                    state=SourceState.RESOLVED_FROM_SOURCE,
                    group_id="G-0001",
                    finding_id="A-01",
                    fingerprint=cached_reconciliation.groups[0].fingerprint,
                ),
                disposition_ledger=self._disposition_ledger(action=DispositionAction.CONFIRM_RESOLVED),
            )
            provider_calls: list[Any] = []

            def provider(request: Any) -> FindingVerificationResult:
                provider_calls.append(request)
                return FindingVerificationResult(source_state=SourceState.STILL_OPEN, rationale="fresh check")

            ledger = verify_source_truth(
                reconciliation=current_reconciliation,
                verifier=provider,
                memory_store=store,
                current_head="head-ok",
            )

            self.assertEqual([call.group_id for call in provider_calls], ["G-0001"])
            self.assertEqual(ledger.rows[0].provenance["cache_status"], "miss")
            self.assertEqual(ledger.rows[0].provenance["cache_reason"], "stable_identity_mismatch")

    def test_changed_source_reference_with_same_display_id_misses_cache(self) -> None:
        from cure_subsequent_review.contracts import DispositionAction, SourceState
        from cure_subsequent_review.memory_store import ReviewMemoryStore
        from cure_subsequent_review.source_truth import FindingVerificationResult, verify_source_truth

        cached = self._finding_candidate(finding_id="A-01", title="same finding title", evidence="app.py:10")
        cached_reconciliation = reconcile_findings(findings=(cached,))
        current = self._finding_candidate(finding_id="A-01", title="same finding title", evidence="app.py:44")
        current_reconciliation = reconcile_findings(findings=(current,))

        with tempfile.TemporaryDirectory() as tmp:
            store = ReviewMemoryStore(path=Path(tmp) / "cure_memory.json")
            store.update_findings(
                current_head="head-ok",
                source_verification=self._source_ledger(
                    state=SourceState.RESOLVED_FROM_SOURCE,
                    group_id="G-0001",
                    finding_id="A-01",
                    fingerprint=cached_reconciliation.groups[0].fingerprint,
                ),
                disposition_ledger=self._disposition_ledger(action=DispositionAction.CONFIRM_RESOLVED),
            )
            provider_calls: list[Any] = []

            def provider(request: Any) -> FindingVerificationResult:
                provider_calls.append(request)
                return FindingVerificationResult(source_state=SourceState.STILL_OPEN, rationale="fresh check")

            ledger = verify_source_truth(
                reconciliation=current_reconciliation,
                verifier=provider,
                memory_store=store,
                current_head="head-ok",
            )

            self.assertEqual([call.group_id for call in provider_calls], ["G-0001"])
            self.assertEqual(ledger.rows[0].provenance["cache_status"], "miss")
            self.assertEqual(ledger.rows[0].provenance["cache_reason"], "stable_identity_mismatch")

    def test_cache_miss_records_reason_when_only_ordinal_group_matches(self) -> None:
        from cure_subsequent_review.contracts import DispositionAction, SourceState
        from cure_subsequent_review.memory_store import ReviewMemoryStore
        from cure_subsequent_review.source_truth import FindingVerificationResult, verify_source_truth

        current = self._finding_candidate(finding_id="A-01", title="current finding", evidence="app.py:10")
        reconciliation = reconcile_findings(findings=(current,))

        with tempfile.TemporaryDirectory() as tmp:
            store = ReviewMemoryStore(path=Path(tmp) / "cure_memory.json")
            store.update_findings(
                current_head="head-ok",
                source_verification=self._source_ledger(
                    state=SourceState.RESOLVED_FROM_SOURCE,
                    group_id="G-0001",
                    finding_id="A-01",
                    fingerprint="cached-different-fingerprint",
                ),
                disposition_ledger=self._disposition_ledger(action=DispositionAction.CONFIRM_RESOLVED),
            )
            provider_calls: list[Any] = []

            def provider(request: Any) -> FindingVerificationResult:
                provider_calls.append(request)
                return FindingVerificationResult(source_state=SourceState.STILL_OPEN, rationale="fresh check")

            ledger = verify_source_truth(
                reconciliation=reconciliation,
                verifier=provider,
                memory_store=store,
                current_head="head-ok",
            )

            self.assertEqual([call.group_id for call in provider_calls], ["G-0001"])
            self.assertEqual(ledger.rows[0].source_state, SourceState.STILL_OPEN)
            self.assertEqual(ledger.rows[0].provenance["cache_status"], "miss")
            self.assertEqual(ledger.rows[0].provenance["cache_reason"], "stable_identity_mismatch")

    def test_cache_bypass_reason_is_recorded_when_memory_gate_is_off(self) -> None:
        from cure_subsequent_review.contracts import SourceState
        from cure_subsequent_review.source_truth import FindingVerificationResult, verify_source_truth

        reconciliation = reconcile_findings(
            findings=(self._finding_candidate(finding_id="A-01", title="fresh finding", evidence="app.py:10"),)
        )

        def provider(_request: Any) -> FindingVerificationResult:
            return FindingVerificationResult(source_state=SourceState.STILL_OPEN, rationale="fresh check")

        ledger = verify_source_truth(reconciliation=reconciliation, verifier=provider)

        self.assertEqual(ledger.rows[0].provenance["cache_status"], "bypass")
        self.assertEqual(ledger.rows[0].provenance["cache_reason"], "memory_store_unavailable")


__all__ = ["SubsequentReviewMemoryStoreTests"]
