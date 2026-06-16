# ruff: noqa: F403, F405
from _subsequent_review_test_support import *  # noqa: F401, F403

from cure_subsequent_review.contracts import DiscussionArtifact, DiscussionEvent
from cure_subsequent_review.degraded_runtime import DiscussionFetchAborted, DiscussionFetchController


class SubsequentReviewDegradedRuntimeTests(SubsequentReviewTestCase):
    def test_controller_writes_success_artifact_for_healthy_empty_first_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            controller = DiscussionFetchController(
                fetch_discussion=lambda: DiscussionArtifact(status=ModuleStatus.SUCCESS, events=()),
                artifact_dir=artifact_dir,
                interactive=False,
            )
            result = controller.fetch()
            runtime = json.loads((artifact_dir / "degraded_runtime.json").read_text(encoding="utf-8"))

        self.assertEqual(result.status, ModuleStatus.SUCCESS)
        self.assertEqual(result.events, ())
        self.assertEqual(runtime["status"], "success")
        self.assertEqual(runtime["final_reason"], "discussion_available")
        self.assertEqual(runtime["attempts"][0]["status"], "success")
        self.assertEqual(runtime["attempts"][0]["event_count"], 0)

    def test_controller_retries_degraded_discussion_before_accepting_success(self) -> None:
        attempts: list[int] = []
        choices = iter(["retry"])

        def fetch() -> DiscussionArtifact:
            attempts.append(len(attempts) + 1)
            if len(attempts) == 1:
                return DiscussionArtifact(status=ModuleStatus.DEGRADED, status_reasons=("discussion_unavailable",))
            return DiscussionArtifact(
                status=ModuleStatus.SUCCESS,
                events=(DiscussionEvent(kind="issue_comment", event_id="c1", author="cure-bot", body="CURe Review"),),
            )

        with tempfile.TemporaryDirectory() as tmp:
            controller = DiscussionFetchController(
                fetch_discussion=fetch,
                artifact_dir=Path(tmp),
                interactive=True,
                choice_provider=lambda _artifact, _attempt: next(choices),
            )
            result = controller.fetch()
            runtime = json.loads((Path(tmp) / "degraded_runtime.json").read_text(encoding="utf-8"))

        self.assertEqual(result.status, ModuleStatus.SUCCESS)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(runtime["status"], "success")
        self.assertEqual([item["choice"] for item in runtime["operator_choices"]], ["retry"])

    def test_controller_accepts_metadata_only_thread_state_gap_without_erasing_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            controller = DiscussionFetchController(
                fetch_discussion=lambda: DiscussionArtifact(
                    status=ModuleStatus.DEGRADED,
                    events=(
                        DiscussionEvent(
                            kind="issue_comment",
                            event_id="official-footer",
                            author="human-operator",
                            body=f"CURe Review\n{CURE_FOOTER_BLOCK}",
                        ),
                    ),
                    status_reasons=("thread_state_unavailable",),
                ),
                artifact_dir=artifact_dir,
                interactive=False,
            )
            result = controller.fetch()

            decision, _discussion = decide_subsequent_review(
                pr=PR(),
                completed_sessions=[],
                mode=SubsequentReviewCommandMode.AUTO,
                evidence_policy=EvidencePolicy.UNTRUSTED,
                discussion=result,
            )

        self.assertEqual(len(result.events), 1)
        self.assertFalse((artifact_dir / "degraded_runtime.json").exists())
        self.assertTrue(decision.enabled)
        self.assertIn("cure_pr_discussion_found", decision.reasons)
        self.assertIn("thread_state_unavailable", decision.degraded_reasons)

    def test_controller_skip_records_auditable_empty_discussion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            controller = DiscussionFetchController(
                fetch_discussion=lambda: DiscussionArtifact(
                    status=ModuleStatus.DEGRADED,
                    events=(DiscussionEvent(kind="issue_comment", event_id="tentative", author="human", body="partial"),),
                    status_reasons=("discussion_incomplete",),
                ),
                artifact_dir=Path(tmp),
                interactive=True,
                choice_provider=lambda _artifact, _attempt: "skip",
            )
            result = controller.fetch()
            runtime = json.loads((Path(tmp) / "degraded_runtime.json").read_text(encoding="utf-8"))

        self.assertEqual(result.status, ModuleStatus.DEGRADED)
        self.assertEqual(result.events, ())
        self.assertIn("operator_skipped_degraded_discussion", result.status_reasons)
        self.assertEqual(runtime["status"], "degraded")
        self.assertEqual(runtime["operator_choices"][0]["choice"], "skip")

    def test_controller_abort_records_runtime_artifact_and_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            controller = DiscussionFetchController(
                fetch_discussion=lambda: DiscussionArtifact(
                    status=ModuleStatus.DEGRADED,
                    status_reasons=("discussion_payload_malformed",),
                ),
                artifact_dir=artifact_dir,
                interactive=True,
                choice_provider=lambda _artifact, _attempt: "abort",
            )
            with self.assertRaises(DiscussionFetchAborted):
                controller.fetch()
            runtime = json.loads((artifact_dir / "degraded_runtime.json").read_text(encoding="utf-8"))

        self.assertEqual(runtime["status"], "aborted")
        self.assertEqual(runtime["operator_choices"][0]["choice"], "abort")
        self.assertIn("discussion_payload_malformed", runtime["attempts"][0]["status_reasons"])

    def test_noninteractive_controller_retries_at_most_three_times_then_skips(self) -> None:
        attempts = 0

        def fetch() -> DiscussionArtifact:
            nonlocal attempts
            attempts += 1
            return DiscussionArtifact(status=ModuleStatus.DEGRADED, status_reasons=("discussion_unavailable",))

        with tempfile.TemporaryDirectory() as tmp:
            result = DiscussionFetchController(fetch_discussion=fetch, artifact_dir=Path(tmp), interactive=False).fetch()
            runtime = json.loads((Path(tmp) / "degraded_runtime.json").read_text(encoding="utf-8"))

        self.assertEqual(attempts, 3)
        self.assertEqual(result.events, ())
        self.assertIn("operator_skipped_degraded_discussion", result.status_reasons)
        self.assertEqual([item["choice"] for item in runtime["operator_choices"]], ["retry", "retry", "skip"])


__all__ = ["SubsequentReviewDegradedRuntimeTests"]
