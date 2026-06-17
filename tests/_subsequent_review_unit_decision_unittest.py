# ruff: noqa: F403, F405
from _subsequent_review_test_support import *  # noqa: F401, F403


class SubsequentReviewDecisionTests(SubsequentReviewTestCase):
    def _footer_block(self, *, session_id: str, review_head_sha: str) -> str:
        return (
            "<!-- CURE_REVIEW_FOOTER_START -->\n"
            "_review generated with [CURe](https://github.com/grzegorznowak/CURe) v. 0.1.4"
            f" · single-stage · sha {review_head_sha[:7]} · model gpt-5.2/high · tok 1k/2k/3k"
            f" · session {session_id} · 5m0s_\n"
            "<!-- CURE_REVIEW_FOOTER_END -->"
        )

    def test_decision_counts_pull_review_event_head_mismatch_as_foreign_footer_provenance(self) -> None:
        pr = PR(owner="grzegorznowak", repo="cure", number=18)
        current_head = "a" * 40
        event_head = "b" * 40
        review_body = (
            "CURe Review\n"
            "### CURE-22: Foreign event-head finding\n"
            "Severity: high\n"
            "Section: Reliability\n"
            "Evidence: app/pr22.py:4 belongs to a different head\n"
            f"\n{self._footer_block(session_id='grzegorznowak-cure-pr18-20260615-120000-abcd', review_head_sha=current_head)}\n"
        )

        def fetch(path: str) -> Any:
            if path.endswith("/issues/18/comments"):
                return []
            if path.endswith("/pulls/18/reviews"):
                return [
                    {
                        "id": 901,
                        "html_url": "review-url",
                        "user": {"login": "human-operator"},
                        "body": review_body,
                        "state": "COMMENTED",
                        "commit_id": event_head,
                        "submitted_at": "2026-06-15T12:00:00Z",
                    }
                ]
            if path.endswith("/pulls/18/comments"):
                return []
            raise AssertionError(path)

        decision, discussion = decide_subsequent_review(
            pr=pr,
            completed_sessions=[],
            mode=SubsequentReviewCommandMode.AUTO,
            evidence_policy=EvidencePolicy.UNTRUSTED,
            fetch_json=fetch,
            current_head=current_head,
        )

        self.assertIsNotNone(discussion)
        self.assertFalse(decision.enabled)
        self.assertNotIn("cure_pr_discussion_found", decision.reasons)
        self.assertEqual(decision.signal_counts["remote_cure_markers"], 1)
        self.assertEqual(decision.signal_counts["accepted_remote_cure_markers"], 0)
        self.assertEqual(decision.signal_counts["foreign_remote_cure_markers"], 1)
        rejected = decision.rejected_remote_cure_markers
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["source_type"], "pr_review")
        self.assertEqual(rejected[0]["review_id"], "901")
        self.assertEqual(rejected[0]["url"], "review-url")
        self.assertEqual(rejected[0]["author"], "human-operator")
        self.assertEqual(rejected[0]["created_at"], "2026-06-15T12:00:00Z")
        self.assertEqual(rejected[0]["submitted_at"], "2026-06-15T12:00:00Z")
        self.assertEqual(rejected[0]["reason"], "foreign_cure_footer_provenance")
        self.assertEqual(rejected[0]["current_pr_number"], 18)
        self.assertEqual(rejected[0]["current_head"], current_head)
        self.assertEqual(rejected[0]["footer_pr_number"], 18)
        self.assertEqual(rejected[0]["footer_session_id"], "grzegorznowak-cure-pr18-20260615-120000-abcd")
        self.assertEqual(rejected[0]["footer_reviewed_head"], current_head[:7])
        self.assertEqual(rejected[0]["event_reviewed_head"], event_head)
        self.assertNotIn("body", rejected[0])
        serialized = decision.to_json(pr=pr)
        self.assertEqual(serialized["rejected_remote_cure_markers"], list(rejected))
        self.assertNotIn("Foreign event-head finding", json.dumps(serialized))
        from cure_subsequent_review.decision import decision_meta_json

        meta_payload = decision_meta_json(
            decision=decision,
            decision_path=Path("work/subsequent/decision.json"),
            artifact_dir=Path("work/subsequent"),
            manifest_path=None,
        )
        self.assertEqual(meta_payload["rejected_remote_cure_markers"], list(rejected))
        from cure_subsequent_review.decision import format_rejected_remote_cure_marker_notice

        notice = format_rejected_remote_cure_marker_notice(rejected)
        self.assertIsNotNone(notice)
        self.assertIn("CURe Operator Notice — Not part of the review", notice or "")
        self.assertIn("review 901", notice or "")
        self.assertIn("review-url", notice or "")
        self.assertIn("Cleanup guidance", notice or "")
        self.assertNotIn("Foreign event-head finding", notice or "")

    def test_decision_service_auto_modes_and_explicit_disabled(self) -> None:
        pr = PR()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review = root / "review.md"
            review.write_text("prior\n", encoding="utf-8")
            session = Session("s1", root, review)
            local, local_discussion = decide_subsequent_review(
                pr=pr,
                completed_sessions=[session],
                mode=SubsequentReviewCommandMode.AUTO,
                evidence_policy=EvidencePolicy.UNTRUSTED,
                fetch_json=lambda _path: (_ for _ in ()).throw(AssertionError("remote probe not needed with local sessions")),
            )
        self.assertIsNone(local_discussion)
        self.assertTrue(local.enabled)
        self.assertIn("completed_sessions_found", local.reasons)
        self.assertEqual(local.signal_counts["completed_sessions"], 1)

        remote, remote_discussion = decide_subsequent_review(
            pr=pr,
            completed_sessions=[],
            mode=SubsequentReviewCommandMode.AUTO,
            evidence_policy=EvidencePolicy.TRUSTED,
            fetch_json=lambda path: [
                {
                    "id": 1,
                    "user": {"login": "human-operator"},
                    "body": f"CURe Review\n{CURE_FOOTER_BLOCK}",
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ] if path.endswith("/issues/9999/comments") else [],
        )
        self.assertIsNotNone(remote_discussion)
        self.assertTrue(remote.enabled)
        self.assertIn("cure_pr_discussion_found", remote.reasons)
        self.assertEqual(remote.signal_counts["remote_cure_markers"], 1)
        self.assertEqual(remote.evidence_policy, EvidencePolicy.TRUSTED)

        first_run, first_run_discussion = decide_subsequent_review(
            pr=pr,
            completed_sessions=[],
            mode=SubsequentReviewCommandMode.AUTO,
            evidence_policy=EvidencePolicy.UNTRUSTED,
            fetch_json=lambda path: [
                {"id": 2, "user": {"login": "human"}, "body": "looks good"}
            ] if path.endswith("/issues/9999/comments") else [],
        )
        self.assertIsNotNone(first_run_discussion)
        self.assertFalse(first_run.enabled)
        self.assertIn("no_prior_review_signals", first_run.reasons)

        public_fallback_empty, public_fallback_discussion = decide_subsequent_review(
            pr=pr,
            completed_sessions=[],
            mode=SubsequentReviewCommandMode.AUTO,
            evidence_policy=EvidencePolicy.UNTRUSTED,
            fetch_json=lambda _path: {
                "items": [],
                "complete": False,
                "status": "discussion_incomplete",
                "fetch": "public_github_api",
            },
        )
        self.assertIsNotNone(public_fallback_discussion)
        self.assertFalse(public_fallback_empty.enabled)
        self.assertEqual(public_fallback_empty.reasons, ("no_prior_review_signals",))
        self.assertEqual(public_fallback_empty.signal_counts["remote_cure_markers"], 0)
        self.assertIn("discussion_incomplete", public_fallback_empty.degraded_reasons)

        degraded, degraded_discussion = decide_subsequent_review(
            pr=pr,
            completed_sessions=[],
            mode=SubsequentReviewCommandMode.AUTO,
            evidence_policy=EvidencePolicy.UNTRUSTED,
            fetch_json=lambda _path: (_ for _ in ()).throw(RuntimeError("offline")),
        )
        self.assertIsNotNone(degraded_discussion)
        self.assertTrue(degraded.enabled)
        self.assertIn("remote_probe_degraded", degraded.reasons)
        self.assertIn("discussion_unavailable", degraded.degraded_reasons)

        explicit, explicit_discussion = decide_subsequent_review(
            pr=pr,
            completed_sessions=[object()],
            mode=SubsequentReviewCommandMode.DISABLED,
            evidence_policy=EvidencePolicy.UNTRUSTED,
            fetch_json=lambda _path: (_ for _ in ()).throw(AssertionError("disabled mode must not probe remote")),
        )
        self.assertIsNone(explicit_discussion)
        self.assertFalse(explicit.enabled)
        self.assertEqual(explicit.reasons, ("operator_disabled",))

    def test_operator_skipped_degraded_discussion_does_not_enable_first_run(self) -> None:
        from cure_subsequent_review.contracts import DiscussionArtifact

        decision, discussion = decide_subsequent_review(
            pr=PR(),
            completed_sessions=[],
            mode=SubsequentReviewCommandMode.AUTO,
            evidence_policy=EvidencePolicy.UNTRUSTED,
            discussion=DiscussionArtifact(
                status=ModuleStatus.DEGRADED,
                status_reasons=("discussion_unavailable", "operator_skipped_degraded_discussion"),
            ),
        )

        self.assertIsNotNone(discussion)
        self.assertFalse(decision.enabled)
        self.assertEqual(decision.reasons, ("no_prior_review_signals",))
        self.assertIn("operator_skipped_degraded_discussion", decision.degraded_reasons)

    def test_decision_service_rejects_false_positive_remote_markers(self) -> None:
        pr = PR()
        cases: tuple[tuple[str, dict[str, Any], bool, str], ...] = (
            (
                "human_cure_looking_issue_comment",
                {"id": 10, "user": {"login": "human"}, "body": "CURe review found this", "created_at": "2026-01-01T00:00:00Z"},
                False,
                "no_prior_review_signals",
            ),
            (
                "missing_author_cure_looking_issue_comment",
                {"id": 11, "body": "<!-- cure --> CURe review", "created_at": "2026-01-01T00:00:00Z"},
                False,
                "no_prior_review_signals",
            ),
            (
                "resolved_thread_metadata_only",
                {"id": 12, "user": {"login": "human"}, "body": "CURe review", "resolved": True, "path": "a.py", "line": 1},
                False,
                "no_prior_review_signals",
            ),
            (
                "unresolved_thread_metadata_only",
                {"id": 13, "user": {"login": "human"}, "body": "CURe review", "resolved": False, "path": "a.py", "line": 1},
                False,
                "no_prior_review_signals",
            ),
            (
                "missing_thread_state_metadata",
                {"id": 14, "user": {"login": "human"}, "body": "CURe review", "path": "a.py", "line": 1},
                False,
                "no_prior_review_signals",
            ),
            (
                "cure_looking_review_comment_thread_excluded_from_auto_markers",
                {
                    "id": 15,
                    "user": {"login": "cure-bot"},
                    "body": "CURe Review\n### CURE-90: line comment text",
                    "path": "a.py",
                    "line": 1,
                    "thread_state": "unresolved",
                },
                False,
                "no_prior_review_signals",
            ),
            (
                "spoofed_cure_login_issue_comment",
                {
                    "id": 16,
                    "user": {"login": "cure-fake"},
                    "body": "CURe Review\n### CURE-91: spoofed",
                    "created_at": "2026-01-01T00:00:00Z",
                },
                False,
                "no_prior_review_signals",
            ),
            (
                "allowlisted_author_without_official_footer",
                {
                    "id": 17,
                    "user": {"login": "cure-bot"},
                    "body": "CURe Review\n### CURE-92: old body-only marker",
                    "created_at": "2026-01-01T00:00:00Z",
                },
                False,
                "no_prior_review_signals",
            ),
        )
        for name, payload, expected_enabled, expected_reason in cases:
            with self.subTest(name=name):
                def fetch(path: str) -> Any:
                    if path.endswith("/issues/9999/comments") and ("issue_comment" in name or name == "allowlisted_author_without_official_footer"):
                        return [payload]
                    if path.endswith("/pulls/9999/comments") and "thread" in name:
                        return [payload]
                    return []

                decision, discussion = decide_subsequent_review(
                    pr=pr,
                    completed_sessions=[],
                    mode=SubsequentReviewCommandMode.AUTO,
                    evidence_policy=EvidencePolicy.UNTRUSTED,
                    fetch_json=fetch,
                )
                self.assertIsNotNone(discussion)
                self.assertEqual(decision.enabled, expected_enabled)
                self.assertEqual(decision.signal_counts["remote_cure_markers"], 0)
                self.assertNotIn("cure_pr_discussion_found", decision.reasons)
                self.assertIn(expected_reason, decision.reasons)
                if name == "missing_thread_state_metadata":
                    self.assertIn("thread_state_unavailable", decision.degraded_reasons)


__all__ = ["SubsequentReviewDecisionTests"]
