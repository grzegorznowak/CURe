# ruff: noqa: F403, F405
from _subsequent_review_test_support import *  # noqa: F401, F403


class SubsequentReviewDiscussionLinkerTests(SubsequentReviewTestCase):
    def _groups(self) -> tuple[Any, ...]:
        return reconcile_findings(
            findings=(
                self._finding_candidate(finding_id="A-01", title="Parser null check", evidence="src/parser.py:42"),
                self._finding_candidate(finding_id="B-01", title="UI race", evidence="src/ui.py:12"),
            )
        ).groups

    def test_llm_linker_receives_event_and_full_finding_bodies(self) -> None:
        from cure_subsequent_review.contracts import DiscussionEvent, DiscussionSignalClass
        from cure_subsequent_review.discussion_linker import LlmDiscussionLinker

        prompts: list[str] = []

        def llm(prompt: str) -> str:
            prompts.append(prompt)
            return json.dumps(
                {
                    "group_ids": ["G-0001"],
                    "signal_class": "developer_claim_fixed",
                    "rationale": "comment names the parser issue",
                }
            )

        linker = LlmDiscussionLinker(classifier=llm, current_head="head-1")
        event = DiscussionEvent(kind="issue_comment", event_id="C-01", author="developer", body="A-01 is fixed now")

        result = linker(event, self._groups())

        self.assertEqual(result.group_ids, ("G-0001",))
        self.assertEqual(result.signal_class, DiscussionSignalClass.DEVELOPER_CLAIM_FIXED)
        self.assertEqual(result.rationale, "comment names the parser issue")
        self.assertEqual(len(prompts), 1)
        self.assertIn("A-01 is fixed now", prompts[0])
        self.assertIn("Parser null check", prompts[0])
        self.assertIn("src/parser.py:42", prompts[0])

    def test_llm_linker_low_confidence_null_group_returns_no_group(self) -> None:
        from cure_subsequent_review.contracts import DiscussionEvent, DiscussionSignalClass
        from cure_subsequent_review.discussion_linker import LlmDiscussionLinker

        linker = LlmDiscussionLinker(
            classifier=lambda _prompt: json.dumps(
                {"group_ids": [None], "signal_class": "by_design", "rationale": "topical but no confident finding id"}
            ),
            current_head="head-1",
        )

        result = linker(
            DiscussionEvent(kind="issue_comment", event_id="C-02", author="developer", body="This is by design"),
            self._groups(),
        )

        self.assertEqual(result.group_ids, ())
        self.assertEqual(result.signal_class, DiscussionSignalClass.BY_DESIGN)
        self.assertEqual(result.rationale, "topical but no confident finding id")

    def test_malformed_llm_linker_output_degrades_without_aborting_signal_resolution(self) -> None:
        from cure_subsequent_review.contracts import DiscussionArtifact, DiscussionEvent, ModuleStatus
        from cure_subsequent_review.discussion_linker import LlmDiscussionLinker
        from cure_subsequent_review.discussion_signals import resolve_discussion_signals

        event = DiscussionEvent(
            kind="issue_comment",
            event_id="C-04",
            author="developer",
            body="Parser null check is by design",
        )
        linker = LlmDiscussionLinker(classifier=lambda _prompt: "not json", current_head="head-1")

        ledger = resolve_discussion_signals(
            discussion=DiscussionArtifact(status=ModuleStatus.SUCCESS, events=(event,)),
            reconciliation=reconcile_findings(
                findings=(
                    self._finding_candidate(finding_id="A-01", title="Parser null check", evidence="src/parser.py:42"),
                )
            ),
            linker=linker,
        )

        self.assertEqual(ledger.status, ModuleStatus.DEGRADED)
        self.assertIn("llm_discussion_linker_malformed", ledger.status_reasons)
        self.assertEqual(len(ledger.rows), 1)
        self.assertEqual(ledger.rows[0].group_ids, ())
        self.assertIn("llm_linker_malformed", ledger.rows[0].provenance["rationale"])

    def test_llm_linker_replays_cached_result_for_same_event_body_and_head(self) -> None:
        from cure_subsequent_review.contracts import DiscussionEvent, DiscussionSignalClass
        from cure_subsequent_review.discussion_linker import LlmDiscussionLinker
        from cure_subsequent_review.memory_store import ReviewMemoryStore, group_identity_for_cache

        with tempfile.TemporaryDirectory() as tmp:
            store = ReviewMemoryStore(path=Path(tmp) / "cure_memory.json")
            event = DiscussionEvent(kind="issue_comment", event_id="C-03", author="developer", body="Duplicate of A-01")
            groups = self._groups()
            store.update_linker_result(
                event_id="C-03",
                body=event.body,
                current_head="head-1",
                group_ids=("G-0001",),
                signal_class=DiscussionSignalClass.DUPLICATE_SUPERSEDED,
                rationale="cached",
                group_identities={"G-0001": group_identity_for_cache(groups[0])},
            )
            calls: list[str] = []
            linker = LlmDiscussionLinker(classifier=calls.append, current_head="head-1", memory_store=store)

            result = linker(event, groups)

            self.assertEqual(calls, [])
            self.assertEqual(result.group_ids, ("G-0001",))
            self.assertEqual(result.signal_class, DiscussionSignalClass.DUPLICATE_SUPERSEDED)
            self.assertEqual(result.rationale, "cached")


__all__ = ["SubsequentReviewDiscussionLinkerTests"]
