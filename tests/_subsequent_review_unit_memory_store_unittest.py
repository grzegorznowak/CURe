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
                    current_source_citations=({"path": "app.py", "start_line": 10, "summary": "fixed"},),
                    inspected_source_refs=("app.py:10",),
                    provenance={"rationale": "source checked", "fingerprint": fingerprint},
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

            provider_calls.clear()
            stale = verify_source_truth(
                reconciliation=reconciliation,
                verifier=provider,
                memory_store=store,
                current_head="different-head",
            )
            self.assertEqual([call.group_id for call in provider_calls], ["G-0001", "G-0002"])
            self.assertNotEqual(stale.rows[0].provenance.get("source"), "memory_cache")

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


__all__ = ["SubsequentReviewMemoryStoreTests"]
