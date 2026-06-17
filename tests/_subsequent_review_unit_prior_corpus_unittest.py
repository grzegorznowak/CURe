# ruff: noqa: F403, F405
from _subsequent_review_test_support import *  # noqa: F401, F403


class SubsequentReviewPriorCorpusTests(SubsequentReviewTestCase):
    def _footer_block(self, *, session_id: str, review_head_sha: str) -> str:
        return (
            "<!-- CURE_REVIEW_FOOTER_START -->\n"
            "_review generated with [CURe](https://github.com/grzegorznowak/CURe) v. 0.1.4"
            f" · single-stage · sha {review_head_sha[:7]} · model gpt-5.2/high · tok 1k/2k/3k"
            f" · session {session_id} · 5m0s_\n"
            "<!-- CURE_REVIEW_FOOTER_END -->"
        )

    def test_official_footer_pull_review_body_enables_and_enters_prior_corpus_regardless_of_author(self) -> None:
        pr = PR()
        review_body = (
            "CURe Review\n"
            "### CURE-77: Pull review finding\n"
            "Severity: high\n"
            "Section: Security\n"
            "Evidence: app/auth.py:42 missing check\n"
            f"\n{CURE_FOOTER_BLOCK}\n"
        )

        def fetch(path: str) -> Any:
            if path.endswith("/issues/9999/comments"):
                return []
            if path.endswith("/pulls/9999/reviews"):
                return [
                    {
                        "id": 901,
                        "html_url": "review-url",
                        "user": {"login": "human-operator"},
                        "body": review_body,
                        "state": "COMMENTED",
                        "commit_id": "review-head-sha-901",
                        "submitted_at": "2026-01-05T00:00:00Z",
                    }
                ]
            if path.endswith("/pulls/9999/comments"):
                return []
            raise AssertionError(path)

        decision, discussion_from_decision = decide_subsequent_review(
            pr=pr,
            completed_sessions=[],
            mode=SubsequentReviewCommandMode.AUTO,
            evidence_policy=EvidencePolicy.UNTRUSTED,
            fetch_json=fetch,
        )
        self.assertIsNotNone(discussion_from_decision)
        self.assertTrue(decision.enabled)
        self.assertIn("cure_pr_discussion_found", decision.reasons)
        self.assertEqual(decision.signal_counts["remote_cure_markers"], 1)

        discussion = collect_pr_discussion(pr=pr, fetch_json=fetch)
        review_event = next(event for event in discussion.events if event.kind == "review")
        self.assertEqual(review_event.reviewed_head, "review-head-sha-901")

        corpus = build_prior_review_corpus(pr=pr, sessions=[], discussion=discussion)
        self.assertEqual(corpus.status, ModuleStatus.SUCCESS)
        self.assertNotIn("no_prior_reviews", corpus.status_reasons)
        review_entries = [entry for entry in corpus.entries if entry.source_type == "pr_review"]
        self.assertEqual(len(review_entries), 1)
        entry = review_entries[0]
        self.assertEqual(entry.entry_id, "pr_review:901")
        self.assertEqual(entry.body, review_body)
        self.assertEqual(entry.provenance["review_id"], "901")
        self.assertEqual(entry.provenance["url"], "review-url")
        self.assertEqual(entry.provenance["author"], "human-operator")
        self.assertEqual(entry.provenance["state"], "COMMENTED")
        self.assertEqual(entry.reviewed_head, "review-head-sha-901")
        self.assertEqual(entry.provenance["reviewed_head"], "review-head-sha-901")

        findings = extract_prior_findings(corpus=corpus)
        self.assertEqual(findings.status, ModuleStatus.SUCCESS)
        self.assertNotIn("no_prior_reviews", findings.status_reasons)
        self.assertIn("CURE-77", {item.finding_id for item in findings.findings})
        pull_review_finding = next(item for item in findings.findings if item.finding_id == "CURE-77")
        self.assertEqual(pull_review_finding.provenance.source_type, "pr_review")
        self.assertEqual(pull_review_finding.provenance.comment_url, "review-url")
        self.assertEqual(pull_review_finding.reviewed_head, "review-head-sha-901")
        self.assertEqual(pull_review_finding.provenance.reviewed_head, "review-head-sha-901")

    def test_official_footer_issue_comment_remote_only_corpus_status_is_success_regardless_of_author(self) -> None:
        pr = PR()
        comment_body = (
            "CURe Review\n"
            "### CURE-78: Issue comment finding\n"
            "Severity: medium\n"
            "Section: Reliability\n"
            "Evidence: app/jobs.py:9 retries missing\n"
            f"\n{CURE_FOOTER_BLOCK}\n"
        )

        def fetch(path: str) -> Any:
            if path.endswith("/issues/9999/comments"):
                return [
                    {
                        "id": 801,
                        "html_url": "comment-url",
                        "user": {"login": "human-operator"},
                        "body": comment_body,
                        "created_at": "2026-01-04T00:00:00Z",
                    }
                ]
            if path.endswith(("/pulls/9999/reviews", "/pulls/9999/comments")):
                return []
            raise AssertionError(path)

        discussion = collect_pr_discussion(pr=pr, fetch_json=fetch)
        corpus = build_prior_review_corpus(pr=pr, sessions=[], discussion=discussion)
        self.assertEqual(corpus.status, ModuleStatus.SUCCESS)
        self.assertNotIn("no_prior_reviews", corpus.status_reasons)
        self.assertEqual([entry.source_type for entry in corpus.entries], ["pr_comment"])

        findings = extract_prior_findings(corpus=corpus)
        self.assertEqual(findings.status, ModuleStatus.SUCCESS)
        self.assertNotIn("no_prior_reviews", findings.status_reasons)
        self.assertIn("CURE-78", {item.finding_id for item in findings.findings})

    def test_foreign_official_footer_is_audited_and_excluded_before_prior_finding_extraction(self) -> None:
        pr = PR(owner="grzegorznowak", repo="cure", number=18)
        current_head = "a" * 40
        compatible_body = (
            "CURe Review\n"
            "### CURE-18: Compatible PR18 finding\n"
            "Severity: medium\n"
            "Section: Reliability\n"
            "Evidence: app/pr18.py:9 matches current run\n"
            f"\n{self._footer_block(session_id='grzegorznowak-cure-pr18-20260615-120000-abcd', review_head_sha=current_head)}\n"
        )
        foreign_body = (
            "CURe Review\n"
            "### CURE-22: Foreign PR22 finding\n"
            "Severity: high\n"
            "Section: Security\n"
            "Evidence: app/pr22.py:1 does not belong to PR18\n"
            f"\n{self._footer_block(session_id='grzegorznowak-cure-pr22-20260615-103420-b86b', review_head_sha='b' * 40)}\n"
        )

        def fetch(path: str) -> Any:
            if path.endswith("/issues/18/comments"):
                return [
                    {
                        "id": 4707013048,
                        "html_url": "https://github.com/grzegorznowak/CURe/pull/18#issuecomment-4707013048",
                        "user": {"login": "untrusted-human"},
                        "body": compatible_body,
                        "created_at": "2026-06-15T10:30:00Z",
                    },
                    {
                        "id": 4707013049,
                        "html_url": "https://github.com/grzegorznowak/CURe/pull/18#issuecomment-4707013049",
                        "user": {"login": "grzegorznowak"},
                        "body": foreign_body,
                        "created_at": "2026-06-15T10:34:20Z",
                    },
                    {
                        "id": 4707013050,
                        "user": {"login": "cure-bot"},
                        "body": "CURe Review\n### CURE-FAKE: body-only marker",
                    },
                ]
            if path.endswith(("/pulls/18/reviews", "/pulls/18/comments")):
                return []
            raise AssertionError(path)

        decision, _discussion_from_decision = decide_subsequent_review(
            pr=pr,
            completed_sessions=[],
            mode=SubsequentReviewCommandMode.AUTO,
            evidence_policy=EvidencePolicy.UNTRUSTED,
            fetch_json=fetch,
            current_head=current_head,
        )
        self.assertTrue(decision.enabled)
        self.assertIn("cure_pr_discussion_found", decision.reasons)
        self.assertEqual(decision.signal_counts["remote_cure_markers"], 2)
        self.assertEqual(decision.signal_counts["accepted_remote_cure_markers"], 1)
        self.assertEqual(decision.signal_counts["foreign_remote_cure_markers"], 1)

        discussion = collect_pr_discussion(pr=pr, fetch_json=fetch)
        corpus = build_prior_review_corpus(pr=pr, sessions=[], discussion=discussion, current_head=current_head)
        self.assertEqual([entry.entry_id for entry in corpus.entries], ["pr_comment:4707013048"])
        self.assertEqual(corpus.entries[0].provenance["footer_session_id"], "grzegorznowak-cure-pr18-20260615-120000-abcd")
        self.assertEqual(corpus.entries[0].provenance["footer_reviewed_head"], current_head[:7])
        ignored_by_id = {item.get("comment_id"): item for item in corpus.ignored_pr_comments}
        self.assertEqual(ignored_by_id["4707013050"]["reason"], "cure_authorship_not_established")
        foreign = ignored_by_id["4707013049"]
        self.assertEqual(foreign["reason"], "foreign_cure_footer_provenance")
        self.assertIn("official footer belongs to PR22/session grzegorznowak-cure-pr22-20260615-103420-b86b", foreign["audit_reason"])
        self.assertIn("while this run is reviewing PR18", foreign["audit_reason"])
        self.assertIn("not used as PR18 prior-review provenance", foreign["audit_reason"])

        findings = extract_prior_findings(corpus=corpus)
        self.assertEqual({item.finding_id for item in findings.findings}, {"CURE-18"})
        self.assertNotIn("CURE-22", {item.finding_id for item in findings.findings})

    def test_pull_review_event_head_mismatch_is_audited_and_excluded_before_extraction(self) -> None:
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
                        "html_url": "https://github.com/grzegorznowak/CURe/pull/18#pullrequestreview-901",
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

        decision, discussion_from_decision = decide_subsequent_review(
            pr=pr,
            completed_sessions=[],
            mode=SubsequentReviewCommandMode.AUTO,
            evidence_policy=EvidencePolicy.UNTRUSTED,
            fetch_json=fetch,
            current_head=current_head,
        )
        self.assertIsNotNone(discussion_from_decision)
        self.assertFalse(decision.enabled)
        self.assertNotIn("cure_pr_discussion_found", decision.reasons)
        self.assertEqual(decision.signal_counts["remote_cure_markers"], 1)
        self.assertEqual(decision.signal_counts["accepted_remote_cure_markers"], 0)
        self.assertEqual(decision.signal_counts["foreign_remote_cure_markers"], 1)

        discussion = collect_pr_discussion(pr=pr, fetch_json=fetch)
        corpus = build_prior_review_corpus(pr=pr, sessions=[], discussion=discussion, current_head=current_head)
        self.assertEqual(corpus.entries, ())
        ignored_by_id = {item.get("review_id"): item for item in corpus.ignored_pr_comments}
        foreign = ignored_by_id["901"]
        self.assertEqual(foreign["reason"], "foreign_cure_footer_provenance")
        self.assertEqual(foreign["footer_session_id"], "grzegorznowak-cure-pr18-20260615-120000-abcd")
        self.assertEqual(foreign["footer_reviewed_head"], current_head[:7])
        self.assertEqual(foreign["event_reviewed_head"], event_head)
        self.assertIn("event reviewed_head bbbbbbb", foreign["audit_reason"])
        self.assertIn("while this run is reviewing PR18", foreign["audit_reason"])
        self.assertIn("not used as PR18 prior-review provenance", foreign["audit_reason"])

        findings = extract_prior_findings(corpus=corpus)
        self.assertEqual(findings.findings, ())
        self.assertIn("no_prior_reviews", findings.status_reasons)

    def test_foreign_official_footer_alone_does_not_enable_remote_prior_review(self) -> None:
        pr = PR(owner="grzegorznowak", repo="cure", number=18)
        current_head = "a" * 40
        foreign_body = (
            "CURe Review\n"
            "### CURE-22: Foreign PR22 finding\n"
            "Severity: high\n"
            "Section: Security\n"
            "Evidence: app/pr22.py:1 does not belong to PR18\n"
            f"\n{self._footer_block(session_id='grzegorznowak-cure-pr22-20260615-103420-b86b', review_head_sha='b' * 40)}\n"
        )

        def fetch(path: str) -> Any:
            if path.endswith("/issues/18/comments"):
                return [{"id": 4707013049, "user": {"login": "grzegorznowak"}, "body": foreign_body}]
            if path.endswith(("/pulls/18/reviews", "/pulls/18/comments")):
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

    def test_prior_corpus_rejects_untrusted_pull_review_bodies(self) -> None:
        pr = PR()

        def fetch(path: str) -> Any:
            if path.endswith("/issues/9999/comments"):
                return [
                    {
                        "id": 901,
                        "user": {"login": "cure-fake"},
                        "body": "CURe Review\n### CURE-87: Spoofed issue comment",
                    },
                    {
                        "id": 906,
                        "user": {"login": "cure-bot"},
                        "body": "CURe Review\n### CURE-92: Allowlisted author without official footer",
                    },
                ]
            if path.endswith("/pulls/9999/reviews"):
                return [
                    {"id": 902, "user": {"login": "human"}, "body": "CURe Review\n### CURE-88: Human text"},
                    {"id": 903, "body": "<!-- cure --> CURe review\n### CURE-89: Missing author"},
                    {
                        "id": 905,
                        "user": {"login": "cure-fake"},
                        "body": "CURe Review\n### CURE-91: Spoofed review",
                    },
                ]
            if path.endswith("/pulls/9999/comments"):
                return [
                    {
                        "id": 904,
                        "user": {"login": "cure-bot"},
                        "body": "CURe Review\n### CURE-90: Review comment text",
                        "path": "a.py",
                        "line": 1,
                        "thread_state": "unresolved",
                    }
                ]
            raise AssertionError(path)

        discussion = collect_pr_discussion(pr=pr, fetch_json=fetch)
        corpus = build_prior_review_corpus(pr=pr, sessions=[], discussion=discussion)
        self.assertFalse(corpus.entries)
        ignored = {
            (item.get("source_type"), item.get("comment_id"), item.get("review_id"), item.get("reason"))
            for item in corpus.ignored_pr_comments
        }
        self.assertIn(("pr_comment", "901", None, "cure_authorship_not_established"), ignored)
        self.assertIn(("pr_comment", "906", None, "cure_authorship_not_established"), ignored)
        self.assertIn(("pr_review", None, "902", "cure_authorship_not_established"), ignored)
        self.assertIn(("pr_review", None, "903", "cure_authorship_not_established"), ignored)
        self.assertIn(("pr_review", None, "905", "cure_authorship_not_established"), ignored)

    def test_completed_session_artifact_boundary_and_missing_reviews_are_degraded_corpus_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sandbox_root = root / "sandboxes"
            outside = root / "unrelated-review.md"
            outside.write_text(
                "### CURE-OUT: unrelated source truth\nSeverity: high\nSection: Security\nEvidence: unrelated.py:1\n",
                encoding="utf-8",
            )

            outside_session = sandbox_root / "outside-session"
            outside_session.mkdir(parents=True)
            (outside_session / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "outside-session",
                        "status": "done",
                        "host": "github.com",
                        "owner": "example",
                        "repo": "demo",
                        "number": 9999,
                        "created_at": "2026-01-01T00:00:00Z",
                        "completed_at": "2026-01-02T00:00:00Z",
                        "paths": {"review_md": str(outside)},
                    }
                ),
                encoding="utf-8",
            )

            missing_session = sandbox_root / "missing-session"
            missing_session.mkdir(parents=True)
            (missing_session / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "missing-session",
                        "status": "done",
                        "host": "github.com",
                        "owner": "example",
                        "repo": "demo",
                        "number": 9999,
                        "created_at": "2026-01-03T00:00:00Z",
                        "completed_at": "2026-01-04T00:00:00Z",
                        "paths": {"review_md": "missing-review.md"},
                    }
                ),
                encoding="utf-8",
            )

            historical = rf.scan_completed_sessions_for_pr(sandbox_root=sandbox_root, pr=PR())
            self.assertEqual(historical, [])

            corpus_candidates = rf.scan_completed_sessions_for_pr(
                sandbox_root=sandbox_root,
                pr=PR(),
                include_unavailable=True,
            )
            self.assertEqual({item.session_id for item in corpus_candidates}, {"outside-session", "missing-session"})
            reasons = {item.session_id: getattr(item, "review_artifact_reason", None) for item in corpus_candidates}
            self.assertEqual(reasons["outside-session"], "review_md_outside_session")
            self.assertEqual(reasons["missing-session"], "review_md_missing")

            corpus = build_prior_review_corpus(pr=PR(), sessions=corpus_candidates)
            self.assertEqual(corpus.status, ModuleStatus.DEGRADED)
            self.assertEqual(corpus.entries, ())
            self.assertIn("prior_review_artifact_unavailable", corpus.status_reasons)
            ignored = {item.get("session_id"): item for item in corpus.ignored_pr_comments}
            self.assertEqual(ignored["outside-session"].get("reason"), "review_md_outside_session")
            self.assertEqual(ignored["missing-session"].get("reason"), "review_md_missing")
            self.assertEqual(ignored["outside-session"].get("review_md_path"), str(outside))

    def test_completed_session_review_md_resolve_failures_are_degraded_corpus_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sandbox_root = root / "sandboxes"
            session = sandbox_root / "loop-session"
            session.mkdir(parents=True)
            loop = session / "review-loop.md"
            loop.symlink_to(loop)
            (session / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "loop-session",
                        "status": "done",
                        "host": "github.com",
                        "owner": "example",
                        "repo": "demo",
                        "number": 9999,
                        "created_at": "2026-01-01T00:00:00Z",
                        "completed_at": "2026-01-02T00:00:00Z",
                        "paths": {"review_md": "review-loop.md"},
                    }
                ),
                encoding="utf-8",
            )

            historical = rf.scan_completed_sessions_for_pr(sandbox_root=sandbox_root, pr=PR())
            corpus_candidates = rf.scan_completed_sessions_for_pr(
                sandbox_root=sandbox_root,
                pr=PR(),
                include_unavailable=True,
            )

            self.assertEqual(historical, [])
            self.assertEqual([item.session_id for item in corpus_candidates], ["loop-session"])
            self.assertEqual(getattr(corpus_candidates[0], "review_artifact_reason", None), "review_md_unresolvable")
            corpus = build_prior_review_corpus(pr=PR(), sessions=corpus_candidates)
            self.assertEqual(corpus.status, ModuleStatus.DEGRADED)
            ignored = {item.get("session_id"): item for item in corpus.ignored_pr_comments}
            self.assertEqual(ignored["loop-session"].get("reason"), "review_md_unresolvable")

    def test_completed_session_scan_rejects_meta_json_symlink_outside_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sandbox_root = root / "sandboxes"
            sandbox_root.mkdir()
            session = sandbox_root / "meta-link-session"
            session.mkdir()
            outside_review = root / "outside-review.md"
            outside_review.write_text(
                "### CURE-META: outside metadata should not be read\n"
                "Severity: high\n"
                "Section: Security\n"
                "Evidence: outside.py:1\n",
                encoding="utf-8",
            )
            outside_meta = root / "outside-meta.json"
            outside_meta.write_text(
                json.dumps(
                    {
                        "session_id": "meta-link-session",
                        "status": "done",
                        "host": "github.com",
                        "owner": "example",
                        "repo": "demo",
                        "number": 9999,
                        "created_at": "2026-01-01T00:00:00Z",
                        "completed_at": "2026-01-02T00:00:00Z",
                        "paths": {"review_md": str(outside_review)},
                    }
                ),
                encoding="utf-8",
            )
            (session / "meta.json").symlink_to(outside_meta)

            historical = rf.scan_completed_sessions_for_pr(sandbox_root=sandbox_root, pr=PR())
            corpus_candidates = rf.scan_completed_sessions_for_pr(
                sandbox_root=sandbox_root,
                pr=PR(),
                include_unavailable=True,
            )

            self.assertEqual(historical, [])
            self.assertEqual(corpus_candidates, [])

    def test_completed_session_scan_rejects_symlink_session_dirs_outside_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sandbox_root = root / "sandboxes"
            sandbox_root.mkdir()
            outside_session = root / "outside-session"
            outside_session.mkdir()
            outside_review = outside_session / "review.md"
            outside_review.write_text(
                "### CURE-LINK: symlinked session should not be read\n"
                "Severity: high\n"
                "Section: Security\n"
                "Evidence: outside.py:1\n",
                encoding="utf-8",
            )
            (outside_session / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "outside-session",
                        "status": "done",
                        "host": "github.com",
                        "owner": "example",
                        "repo": "demo",
                        "number": 9999,
                        "created_at": "2026-01-01T00:00:00Z",
                        "completed_at": "2026-01-02T00:00:00Z",
                        "paths": {"review_md": "review.md"},
                    }
                ),
                encoding="utf-8",
            )
            (sandbox_root / "linked-session").symlink_to(outside_session, target_is_directory=True)

            historical = rf.scan_completed_sessions_for_pr(sandbox_root=sandbox_root, pr=PR())
            corpus_candidates = rf.scan_completed_sessions_for_pr(
                sandbox_root=sandbox_root,
                pr=PR(),
                include_unavailable=True,
            )

            self.assertEqual(historical, [])
            self.assertEqual(corpus_candidates, [])
            corpus = build_prior_review_corpus(pr=PR(), sessions=corpus_candidates)
            ledger = extract_prior_findings(corpus=corpus)
            self.assertNotIn("CURE-LINK", {item.finding_id for item in ledger.findings})


__all__ = ["SubsequentReviewPriorCorpusTests"]
