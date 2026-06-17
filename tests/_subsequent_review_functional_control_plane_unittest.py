# ruff: noqa: F403, F405
from _subsequent_review_test_support import *  # noqa: F401, F403


class SubsequentReviewControlPlaneTests(SubsequentReviewTestCase):
    def test_runtime_modules_are_enabled_by_default_and_respect_disabled_overrides(self) -> None:
        config = SubsequentReviewConfig(enabled=True, evidence_policy=EvidencePolicy.UNTRUSTED)
        for module in (
            SubsequentReviewModule.REVIEW_CONTEXT_PACKAGER,
            SubsequentReviewModule.REPORT_GOVERNOR,
            SubsequentReviewModule.REVIEW_MEMORY_STORE,
            SubsequentReviewModule.DEGRADED_RUNTIME_MANAGER,
        ):
            with self.subTest(module=module.value):
                self.assertTrue(config.module_enabled(module))
                disabled = SubsequentReviewConfig(
                    enabled=True,
                    evidence_policy=EvidencePolicy.UNTRUSTED,
                    module_overrides={module: ModuleStatus.DISABLED},
                )
                self.assertFalse(disabled.module_enabled(module))
        self.assertFalse(config.module_enabled(SubsequentReviewModule.LANDMARK_TRACE_RUNNER))

    def test_new_sandbox_intake_receives_unavailable_completed_sessions_for_degradation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._reviewflow_paths(root)
            prior_session = paths.sandbox_root / "prior-missing"
            prior_session.mkdir(parents=True)
            (prior_session / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "prior-missing",
                        "status": "done",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 14,
                        "created_at": "2026-01-01T00:00:00Z",
                        "completed_at": "2026-01-02T00:00:00Z",
                        "paths": {"review_md": "missing-review.md"},
                    }
                ),
                encoding="utf-8",
            )
            args = self._new_pr_args()
            intake_sessions: list[Any] = []

            def fake_intake(**kwargs: Any) -> Any:
                intake_sessions.extend(kwargs["completed_sessions"])
                work_dir = kwargs["work_dir"]
                manifest_path = work_dir / "subsequent" / "run_manifest.json"
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_path.write_text("{}\n", encoding="utf-8")
                return type("Result", (), {"manifest_path": manifest_path, "artifact_dir": work_dir / "subsequent"})()

            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(
                rf,
                "load_chunkhound_runtime_config",
                return_value=({}, {"chunkhound": {}}, {}),
            ), mock.patch.object(rf, "materialize_chunkhound_env_config"), mock.patch.object(
                rf, "gh_api_list", return_value=[]
            ), mock.patch(
                "cure_subsequent_review.control_plane.run_subsequent_review_intake",
                side_effect=fake_intake,
            ):
                with self.assertRaises(rf.ReviewflowError):
                    rf._pr_flow_impl(args, paths=paths)

            self.assertEqual([item.session_id for item in intake_sessions], ["prior-missing"])
            self.assertEqual(getattr(intake_sessions[0], "review_artifact_reason", None), "review_md_missing")

    def test_degraded_discussion_status_propagates_through_intake_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            comment_body = (
                "CURe Review\n"
                "### CURE-79: Degraded discussion finding\n"
                "Severity: medium\n"
                "Section: Reliability\n"
                "Evidence: app/jobs.py:9 retries missing\n"
            )

            def fetch(path: str) -> Any:
                if path.endswith("/issues/9999/comments"):
                    return {
                        "items": [
                            {
                                "id": 801,
                                "html_url": "comment-url",
                                "user": {"login": "cure-bot"},
                                "body": comment_body,
                                "created_at": "2026-01-04T00:00:00Z",
                            }
                        ],
                        "complete": False,
                        "status": "discussion_incomplete",
                    }
                return []

            run_subsequent_review_intake(
                pr=PR(),
                work_dir=root / "work",
                completed_sessions=[],
                config=SubsequentReviewConfig(enabled=True, evidence_policy=EvidencePolicy.UNTRUSTED),
                fetch_json=fetch,
            )
            subsequent = root / "work" / "subsequent"
            corpus = json.loads((subsequent / "prior_review_corpus.json").read_text(encoding="utf-8"))
            findings = json.loads((subsequent / "prior_findings.json").read_text(encoding="utf-8"))
            reconciled = json.loads((subsequent / "reconciled_findings.json").read_text(encoding="utf-8"))
            manifest = json.loads((subsequent / "run_manifest.json").read_text(encoding="utf-8"))

        for artifact in (corpus, findings, reconciled):
            self.assertEqual(artifact["status"], "degraded")
            self.assertIn("discussion_incomplete", artifact["status_reasons"])
        self.assertEqual(manifest["modules"]["prior_review_corpus_builder"]["status"], "degraded")
        self.assertEqual(manifest["modules"]["prior_finding_extractor"]["status"], "degraded")
        self.assertEqual(manifest["modules"]["finding_reconciler"]["status"], "degraded")
        self.assertIn("discussion_incomplete", manifest["modules"]["finding_reconciler"]["reasons"])

    def test_intake_reuses_prefetched_discussion_without_fetching_again(self) -> None:
        from cure_subsequent_review.contracts import DiscussionArtifact, DiscussionEvent

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = DiscussionArtifact(
                status=ModuleStatus.SUCCESS,
                events=(
                    DiscussionEvent(
                        kind="issue_comment",
                        event_id="prefetched-1",
                        author="cure-bot",
                        body="CURe Review\n### CURE-88: Prefetched finding\nSeverity: medium\nSection: Security\nEvidence: app.py:1",
                    ),
                ),
            )
            run_subsequent_review_intake(
                pr=PR(),
                work_dir=root / "work",
                completed_sessions=[],
                config=SubsequentReviewConfig(enabled=True, evidence_policy=EvidencePolicy.UNTRUSTED),
                prefetched_discussion=artifact,
                fetch_json=lambda _path: (_ for _ in ()).throw(AssertionError("prefetched discussion must be reused")),
            )
            discussion = json.loads((root / "work" / "subsequent" / "pr_discussion.json").read_text(encoding="utf-8"))

        self.assertEqual([event["event_id"] for event in discussion["events"]], ["prefetched-1"])

    def test_intake_records_degraded_runtime_manager_success_for_healthy_empty_controller_artifact(self) -> None:
        from cure_subsequent_review.contracts import DiscussionArtifact
        from cure_subsequent_review.degraded_runtime import DiscussionFetchController

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_dir = root / "work" / "subsequent"
            controller = DiscussionFetchController(
                fetch_discussion=lambda: DiscussionArtifact(status=ModuleStatus.SUCCESS, events=()),
                artifact_dir=artifact_dir,
                interactive=False,
            )
            discussion = controller.fetch()
            self.assertTrue(controller.artifact_path.is_file())
            run_subsequent_review_intake(
                pr=PR(),
                work_dir=root / "work",
                completed_sessions=[],
                config=SubsequentReviewConfig(enabled=True, evidence_policy=EvidencePolicy.UNTRUSTED),
                prefetched_discussion=discussion,
                degraded_runtime_path=controller.artifact_path,
            )
            manifest = json.loads((artifact_dir / "run_manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["modules"]["degraded_runtime_manager"]["status"], "success")
        self.assertEqual(manifest["modules"]["degraded_runtime_manager"]["artifact_path"], str(controller.artifact_path))

    def test_control_plane_writes_story_01_artifacts_only_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pr = PR()
            disabled = run_subsequent_review_intake(
                pr=pr,
                work_dir=root / "disabled" / "work",
                completed_sessions=[],
                config=SubsequentReviewConfig(enabled=False),
                fetch_json=lambda _path: [],
            )
            self.assertIsNone(disabled)
            self.assertFalse((root / "disabled" / "work" / "subsequent").exists())

            review = root / "review.md"
            review.write_text("### A-01: Prior finding\nSeverity: high\nSection: Security\nEvidence: app.py:1 example\n", encoding="utf-8")
            session = Session("s1", root, review, review_head_sha="abc123")
            summaries: list[str] = []
            result = run_subsequent_review_intake(
                pr=pr,
                work_dir=root / "enabled" / "work",
                completed_sessions=[session],
                config=SubsequentReviewConfig(enabled=True, evidence_policy=EvidencePolicy.UNTRUSTED),
                fetch_json=lambda _path: [],
                summary_writer=summaries.append,
            )
            self.assertIsNotNone(result)
            subsequent = root / "enabled" / "work" / "subsequent"
            self.assertTrue((subsequent / "run_manifest.json").is_file())
            self.assertTrue((subsequent / "pr_discussion.json").is_file())
            self.assertTrue((subsequent / "prior_review_corpus.json").is_file())
            self.assertTrue((subsequent / "prior_findings.json").is_file())
            self.assertTrue((subsequent / "reconciled_findings.json").is_file())
            manifest = json.loads((subsequent / "run_manifest.json").read_text(encoding="utf-8"))
            for artifact_name in (
                "pr_discussion.json",
                "prior_review_corpus.json",
                "prior_findings.json",
                "reconciled_findings.json",
                "source_verification.json",
                "discussion_signals.json",
                "disposition_ledger.json",
            ):
                payload = json.loads((subsequent / artifact_name).read_text(encoding="utf-8"))
                self.assertEqual(payload["schema_version"], 1, artifact_name)
            self.assertEqual(manifest["evidence_policy"], "untrusted")
            self.assertEqual(manifest["modules"]["source_truth_verifier"]["status"], "degraded")
            self.assertEqual(manifest["modules"]["discussion_signal_resolver"]["status"], "success")
            self.assertEqual(manifest["modules"]["disposition_arbiter"]["status"], "degraded")
            self.assertEqual(
                manifest["modules"]["source_truth_verifier"]["artifact_path"],
                str(subsequent / "source_verification.json"),
            )
            dispositions = json.loads((subsequent / "disposition_ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(dispositions["degraded_findings"][0]["blocking_reasons"], ["verifier_provider_not_configured"])
            self.assertIn("prior completed sessions: 1", summaries[0])
            self.assertIn("discussion events: 0", summaries[0])
            self.assertIn("control_plane=success", summaries[0])
            self.assertIn("source_truth_verifier=degraded", summaries[0])
            self.assertIn("landmark_trace_runner=disabled", summaries[0])

    def test_injected_source_verifier_produces_successful_semantic_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            from cure_subsequent_review.contracts import SourceState
            from cure_subsequent_review.source_truth import FindingVerificationResult

            root = Path(tmp)
            review = root / "review.md"
            review.write_text("### A-01: Prior finding\nSeverity: high\nSection: Security\nEvidence: app.py:1 example\n", encoding="utf-8")
            session = Session("s1", root, review, review_head_sha="abc123")

            summaries: list[str] = []
            verifier_calls: list[Any] = []

            def source_verifier(request: Any) -> FindingVerificationResult:
                verifier_calls.append(request)
                return FindingVerificationResult(
                    source_state=SourceState.RESOLVED_FROM_SOURCE,
                    current_source_citations=({"path": "app.py", "start_line": 1, "summary": "fixed"},),
                    rationale="fixture source proves resolution",
                )

            run_subsequent_review_intake(
                pr=PR(),
                work_dir=root / "work",
                completed_sessions=[session],
                config=SubsequentReviewConfig(enabled=True, evidence_policy=EvidencePolicy.UNTRUSTED),
                fetch_json=lambda _path: [],
                source_verifier=source_verifier,
                summary_writer=summaries.append,
            )
            subsequent = root / "work" / "subsequent"
            manifest = json.loads((subsequent / "run_manifest.json").read_text(encoding="utf-8"))
            source = json.loads((subsequent / "source_verification.json").read_text(encoding="utf-8"))
            dispositions = json.loads((subsequent / "disposition_ledger.json").read_text(encoding="utf-8"))

        self.assertEqual([request.group_id for request in verifier_calls], ["G-0001"])
        self.assertEqual(manifest["modules"]["source_truth_verifier"]["status"], "success")
        self.assertEqual(manifest["modules"]["source_truth_verifier"]["observability"]["verifier_fanout"]["provider_call_count"], 1)
        self.assertEqual(manifest["modules"]["disposition_arbiter"]["status"], "success")
        self.assertEqual(source["observability"]["verifier_fanout"]["provider_call_count"], 1)
        self.assertIn("elapsed_seconds", source["observability"]["verifier_fanout"]["timing"])
        self.assertIn("source_verifier_calls=1", summaries[0])
        self.assertEqual(source["rows"][0]["source_state"], "resolved_from_source")
        self.assertEqual(dispositions["dispositions"][0]["action"], "confirm_resolved")
        self.assertEqual(dispositions["degraded_findings"], [])

    def test_review_memory_store_override_disabled_skips_intake_memory_write(self) -> None:
        from cure_subsequent_review.contracts import SourceState
        from cure_subsequent_review.memory_store import ReviewMemoryStore
        from cure_subsequent_review.source_truth import FindingVerificationResult

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review = root / "review.md"
            review.write_text("### A-01: Prior finding\nSeverity: high\nSection: Security\nEvidence: app.py:1 example\n", encoding="utf-8")
            session = Session("s1", root, review, review_head_sha="abc123")
            store = ReviewMemoryStore.for_pr(root=root / "pr", pr=PR())

            def source_verifier(_request: Any) -> FindingVerificationResult:
                return FindingVerificationResult(
                    source_state=SourceState.RESOLVED_FROM_SOURCE,
                    current_source_citations=({"path": "app.py", "start_line": 1, "summary": "fixed"},),
                    rationale="fixture source proves resolution",
                )

            run_subsequent_review_intake(
                pr=PR(),
                work_dir=root / "work",
                completed_sessions=[session],
                config=SubsequentReviewConfig(
                    enabled=True,
                    evidence_policy=EvidencePolicy.UNTRUSTED,
                    module_overrides={SubsequentReviewModule.REVIEW_MEMORY_STORE: ModuleStatus.DISABLED},
                ),
                fetch_json=lambda _path: [],
                source_verifier=source_verifier,
                memory_store=store,
                current_head="abc123",
            )
            manifest = json.loads((root / "work" / "subsequent" / "run_manifest.json").read_text(encoding="utf-8"))

        self.assertFalse(store.path.exists())
        self.assertEqual(manifest["modules"]["review_memory_store"]["status"], "disabled")
        self.assertNotIn("artifact_path", manifest["modules"]["review_memory_store"])

    def test_semantic_module_override_disables_source_and_degrades_arbiter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review = root / "review.md"
            review.write_text("### A-01: Prior finding\nSeverity: high\nSection: Security\nEvidence: app.py:1 example\n", encoding="utf-8")
            session = Session("s1", root, review, review_head_sha="abc123")
            run_subsequent_review_intake(
                pr=PR(),
                work_dir=root / "work",
                completed_sessions=[session],
                config=SubsequentReviewConfig(
                    enabled=True,
                    evidence_policy=EvidencePolicy.UNTRUSTED,
                    module_overrides={SubsequentReviewModule.SOURCE_TRUTH_VERIFIER: ModuleStatus.DISABLED},
                ),
                fetch_json=lambda _path: [],
            )
            subsequent = root / "work" / "subsequent"
            manifest = json.loads((subsequent / "run_manifest.json").read_text(encoding="utf-8"))
            dispositions = json.loads((subsequent / "disposition_ledger.json").read_text(encoding="utf-8"))

        self.assertFalse((subsequent / "source_verification.json").exists())
        self.assertEqual(manifest["modules"]["source_truth_verifier"]["status"], "disabled")
        self.assertEqual(manifest["modules"]["disposition_arbiter"]["status"], "degraded")
        self.assertEqual(dispositions["degraded_findings"][0]["blocking_reasons"], ["source_verification_missing"])


__all__ = ["SubsequentReviewControlPlaneTests"]
