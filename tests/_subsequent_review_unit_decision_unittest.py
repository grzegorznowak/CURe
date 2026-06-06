# ruff: noqa: F403, F405
from _subsequent_review_test_support import *  # noqa: F401, F403


class SubsequentReviewDecisionTests(SubsequentReviewTestCase):
    def test_decision_service_auto_modes_and_explicit_disabled(self) -> None:
        pr = PR()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review = root / "review.md"
            review.write_text("prior\n", encoding="utf-8")
            session = Session("s1", root, review)
            local = decide_subsequent_review(
                pr=pr,
                completed_sessions=[session],
                mode=SubsequentReviewCommandMode.AUTO,
                evidence_policy=EvidencePolicy.UNTRUSTED,
                fetch_json=lambda _path: (_ for _ in ()).throw(AssertionError("remote probe not needed with local sessions")),
            )
        self.assertTrue(local.enabled)
        self.assertIn("completed_sessions_found", local.reasons)
        self.assertEqual(local.signal_counts["completed_sessions"], 1)

        remote = decide_subsequent_review(
            pr=pr,
            completed_sessions=[],
            mode=SubsequentReviewCommandMode.AUTO,
            evidence_policy=EvidencePolicy.TRUSTED,
            fetch_json=lambda path: [
                {"id": 1, "user": {"login": "cure-bot"}, "body": "CURe review", "created_at": "2026-01-01T00:00:00Z"}
            ] if path.endswith("/issues/9999/comments") else [],
        )
        self.assertTrue(remote.enabled)
        self.assertIn("cure_pr_discussion_found", remote.reasons)
        self.assertEqual(remote.signal_counts["remote_cure_markers"], 1)
        self.assertEqual(remote.evidence_policy, EvidencePolicy.TRUSTED)

        first_run = decide_subsequent_review(
            pr=pr,
            completed_sessions=[],
            mode=SubsequentReviewCommandMode.AUTO,
            evidence_policy=EvidencePolicy.UNTRUSTED,
            fetch_json=lambda path: [
                {"id": 2, "user": {"login": "human"}, "body": "looks good"}
            ] if path.endswith("/issues/9999/comments") else [],
        )
        self.assertFalse(first_run.enabled)
        self.assertIn("no_prior_review_signals", first_run.reasons)

        public_fallback_empty = decide_subsequent_review(
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
        self.assertFalse(public_fallback_empty.enabled)
        self.assertEqual(public_fallback_empty.reasons, ("no_prior_review_signals",))
        self.assertEqual(public_fallback_empty.signal_counts["remote_cure_markers"], 0)
        self.assertIn("discussion_incomplete", public_fallback_empty.degraded_reasons)

        degraded = decide_subsequent_review(
            pr=pr,
            completed_sessions=[],
            mode=SubsequentReviewCommandMode.AUTO,
            evidence_policy=EvidencePolicy.UNTRUSTED,
            fetch_json=lambda _path: (_ for _ in ()).throw(RuntimeError("offline")),
        )
        self.assertTrue(degraded.enabled)
        self.assertIn("remote_probe_degraded", degraded.reasons)
        self.assertIn("discussion_unavailable", degraded.degraded_reasons)

        explicit = decide_subsequent_review(
            pr=pr,
            completed_sessions=[object()],
            mode=SubsequentReviewCommandMode.DISABLED,
            evidence_policy=EvidencePolicy.UNTRUSTED,
            fetch_json=lambda _path: (_ for _ in ()).throw(AssertionError("disabled mode must not probe remote")),
        )
        self.assertFalse(explicit.enabled)
        self.assertEqual(explicit.reasons, ("operator_disabled",))

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
        )
        for name, payload, expected_enabled, expected_reason in cases:
            with self.subTest(name=name):
                def fetch(path: str) -> Any:
                    if path.endswith("/issues/9999/comments") and "issue_comment" in name:
                        return [payload]
                    if path.endswith("/pulls/9999/comments") and "thread" in name:
                        return [payload]
                    return []

                decision = decide_subsequent_review(
                    pr=pr,
                    completed_sessions=[],
                    mode=SubsequentReviewCommandMode.AUTO,
                    evidence_policy=EvidencePolicy.UNTRUSTED,
                    fetch_json=fetch,
                )
                self.assertEqual(decision.enabled, expected_enabled)
                self.assertEqual(decision.signal_counts["remote_cure_markers"], 0)
                self.assertNotIn("cure_pr_discussion_found", decision.reasons)
                self.assertIn(expected_reason, decision.reasons)
                if name == "missing_thread_state_metadata":
                    self.assertIn("thread_state_unavailable", decision.degraded_reasons)


__all__ = ["SubsequentReviewDecisionTests"]
