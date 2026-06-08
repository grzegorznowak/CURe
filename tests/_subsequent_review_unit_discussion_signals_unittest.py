# ruff: noqa: F403, F405
from _subsequent_review_test_support import *  # noqa: F401, F403


class SubsequentReviewDiscussionSignalsTests(SubsequentReviewTestCase):
    def _reconciliation(self) -> Any:
        return reconcile_findings(
            findings=(
                self._finding_candidate(finding_id="A-01", title="Prior bug", evidence="src/app.py:10"),
                self._finding_candidate(finding_id="B-01", title="Replacement bug", entry_id="session-b", evidence="src/app.py:10"),
            )
        )

    def test_discussion_signals_link_findings_without_setting_source_truth(self) -> None:
        from cure_subsequent_review.contracts import DiscussionArtifact, DiscussionEvent, DiscussionSignalClass
        from cure_subsequent_review.discussion_signals import resolve_discussion_signals

        artifact = DiscussionArtifact(
            status=ModuleStatus.SUCCESS,
            events=(
                DiscussionEvent(kind="issue_comment", event_id="C-01", author="developer", body="A-01 is fixed now"),
                DiscussionEvent(
                    kind="review_comment",
                    event_id="C-02",
                    author="reviewer",
                    body="Thread for A-01 was resolved",
                    thread_state="resolved",
                ),
                DiscussionEvent(
                    kind="issue_comment",
                    event_id="C-03",
                    author="maintainer",
                    body="Maintainer: A-01 is handled in an external ticket",
                ),
            ),
        )

        ledger = resolve_discussion_signals(discussion=artifact, reconciliation=self._reconciliation())

        by_event = {row.event_id: row for row in ledger.rows}
        self.assertEqual(by_event["C-01"].signal_class, DiscussionSignalClass.DEVELOPER_CLAIM_FIXED)
        self.assertEqual(by_event["C-01"].evidence_policy, EvidencePolicy.UNTRUSTED)
        self.assertEqual(by_event["C-02"].signal_class, DiscussionSignalClass.RESOLVED_THREAD_HINT)
        self.assertEqual(by_event["C-02"].evidence_policy, EvidencePolicy.UNTRUSTED)
        self.assertEqual(by_event["C-03"].signal_class, DiscussionSignalClass.ADDRESSED_ELSEWHERE)
        self.assertEqual(by_event["C-03"].evidence_policy, EvidencePolicy.TRUSTED)
        self.assertNotIn("source_state", by_event["C-01"].to_json())
        self.assertTrue(by_event["C-01"].group_ids)

    def test_unknown_authority_is_untrusted_and_visible(self) -> None:
        from cure_subsequent_review.contracts import DiscussionArtifact, DiscussionEvent, DiscussionSignalClass
        from cure_subsequent_review.discussion_signals import resolve_discussion_signals

        artifact = DiscussionArtifact(
            status=ModuleStatus.SUCCESS,
            events=(DiscussionEvent(kind="issue_comment", event_id="C-04", author=None, body="A-01 is a duplicate"),),
        )

        ledger = resolve_discussion_signals(discussion=artifact, reconciliation=self._reconciliation())

        self.assertEqual(ledger.status, ModuleStatus.SUCCESS)
        self.assertEqual(ledger.rows[0].signal_class, DiscussionSignalClass.DUPLICATE_SUPERSEDED)
        self.assertEqual(ledger.rows[0].evidence_policy, EvidencePolicy.UNTRUSTED)
        self.assertEqual(ledger.rows[0].authority, "unknown")
        self.assertIn("unknown_authority", ledger.rows[0].reasons)

    def test_injected_linker_can_supply_llm_style_links(self) -> None:
        from cure_subsequent_review.contracts import DiscussionArtifact, DiscussionEvent, DiscussionSignalClass
        from cure_subsequent_review.discussion_signals import DiscussionLinkResult, resolve_discussion_signals

        artifact = DiscussionArtifact(
            status=ModuleStatus.SUCCESS,
            events=(DiscussionEvent(kind="issue_comment", event_id="C-05", author="maintainer", body="This belongs to product scope"),),
        )

        def linker(_event: Any, _groups: tuple[Any, ...]) -> DiscussionLinkResult:
            return DiscussionLinkResult(group_ids=("G-0001",), signal_class=DiscussionSignalClass.BY_DESIGN, rationale="llm linked topic")

        ledger = resolve_discussion_signals(discussion=artifact, reconciliation=self._reconciliation(), linker=linker)

        self.assertEqual(ledger.rows[0].group_ids, ("G-0001",))
        self.assertEqual(ledger.rows[0].signal_class, DiscussionSignalClass.BY_DESIGN)
        self.assertEqual(ledger.rows[0].provenance["rationale"], "llm linked topic")


__all__ = ["SubsequentReviewDiscussionSignalsTests"]
