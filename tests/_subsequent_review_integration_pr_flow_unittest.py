# ruff: noqa: F403, F405
from _subsequent_review_test_support import *  # noqa: F401, F403


class SubsequentReviewPrFlowIntegrationTests(SubsequentReviewTestCase):
    def test_if_reviewed_historical_list_exits_before_sandbox_or_intake(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review = root / "prior.md"
            review.write_text("prior review\n", encoding="utf-8")
            completed = rf.HistoricalReviewSession(
                session_id="prior",
                session_dir=root,
                review_md_path=review,
                created_at="2026-01-01T00:00:00Z",
                completed_at="2026-01-02T00:00:00Z",
                verdicts=None,
            )
            args = rf.build_parser().parse_args(
                ["pr", "https://github.com/acme/repo/pull/14", "--if-reviewed", "list"]
            )
            paths = self._reviewflow_paths(root)
            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[completed]), mock.patch(
                "cure_subsequent_review.control_plane.run_subsequent_review_intake",
                side_effect=AssertionError("intake must not run for historical exits"),
            ), mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                self.assertEqual(rf._pr_flow_impl(args, paths=paths), 0)
            self.assertIn("prior", stdout.getvalue())
            self.assertFalse(paths.sandbox_root.exists())

    def test_if_reviewed_list_reports_unavailable_sessions_without_new_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unavailable = rf.HistoricalReviewSession(
                session_id="prior-missing",
                session_dir=root / "prior-missing",
                review_md_path=root / "prior-missing" / "missing-review.md",
                created_at="2026-01-01T00:00:00Z",
                completed_at="2026-01-02T00:00:00Z",
                verdicts=None,
                review_artifact_status="unavailable",
                review_artifact_reason="review_md_missing",
            )
            args = rf.build_parser().parse_args(
                ["pr", "https://github.com/acme/repo/pull/14", "--if-reviewed", "list"]
            )
            paths = self._reviewflow_paths(root)
            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[unavailable]), mock.patch(
                "cure_subsequent_review.control_plane.run_subsequent_review_intake",
                side_effect=AssertionError("intake must not run for historical exits"),
            ), mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                self.assertEqual(rf._pr_flow_impl(args, paths=paths), 0)
            self.assertIn("prior-missing", stdout.getvalue())
            self.assertIn("unavailable(review_md_missing)", stdout.getvalue())
            self.assertFalse(paths.sandbox_root.exists())

    def test_if_reviewed_latest_unavailable_session_fails_before_new_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unavailable = rf.HistoricalReviewSession(
                session_id="prior-missing",
                session_dir=root / "prior-missing",
                review_md_path=root / "prior-missing" / "missing-review.md",
                created_at="2026-01-01T00:00:00Z",
                completed_at="2026-01-02T00:00:00Z",
                verdicts=None,
                review_artifact_status="unavailable",
                review_artifact_reason="review_md_missing",
            )
            args = rf.build_parser().parse_args(
                ["pr", "https://github.com/acme/repo/pull/14", "--if-reviewed", "latest"]
            )
            paths = self._reviewflow_paths(root)
            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[unavailable]), mock.patch(
                "cure_subsequent_review.control_plane.run_subsequent_review_intake",
                side_effect=AssertionError("intake must not run for historical exits"),
            ), self.assertRaisesRegex(rf.ReviewflowError, "review_md_missing"):
                rf._pr_flow_impl(args, paths=paths)
            self.assertFalse(paths.sandbox_root.exists())

    def test_if_reviewed_new_default_auto_writes_decision_and_runs_intake_after_work_dir_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review = root / "prior.md"
            review.write_text("### A-01: Prior\nSeverity: high\nSection: Security\nEvidence: app.py:1\n", encoding="utf-8")
            completed = rf.HistoricalReviewSession(
                session_id="prior",
                session_dir=root,
                review_md_path=review,
                created_at="2026-01-01T00:00:00Z",
                completed_at="2026-01-02T00:00:00Z",
                verdicts=None,
            )
            args = self._new_pr_args()
            paths = self._reviewflow_paths(root)
            intake_calls: list[Path] = []

            def fake_intake(**kwargs: Any) -> Any:
                work_dir = kwargs["work_dir"]
                self.assertTrue(work_dir.is_dir())
                intake_calls.append(work_dir)
                manifest_path = work_dir / "subsequent" / "run_manifest.json"
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_path.write_text("{}\n", encoding="utf-8")
                return type("Result", (), {"manifest_path": manifest_path, "artifact_dir": work_dir / "subsequent"})()

            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[completed]), mock.patch.object(
                rf,
                "load_chunkhound_runtime_config",
                return_value=({}, {"chunkhound": {}}, {}),
            ), mock.patch.object(rf, "materialize_chunkhound_env_config"), mock.patch(
                "cure_subsequent_review.control_plane.run_subsequent_review_intake",
                side_effect=fake_intake,
            ):
                with self.assertRaises(rf.ReviewflowError):
                    rf._pr_flow_impl(args, paths=paths)
            self.assertEqual(len(intake_calls), 1)
            self.assertEqual(intake_calls[0].name, "work")
            decision_path = intake_calls[0] / "subsequent" / "decision.json"
            self.assertTrue(decision_path.is_file())
            decision = json.loads(decision_path.read_text(encoding="utf-8"))
            self.assertEqual(decision["mode"], "auto")
            self.assertTrue(decision["enabled"])
            self.assertIn("completed_sessions_found", decision["reasons"])
            meta = json.loads((intake_calls[0].parent / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["paths"]["subsequent_review_decision"], str(decision_path))
            self.assertEqual(meta["paths"]["subsequent_review_manifest"], str(intake_calls[0] / "subsequent" / "run_manifest.json"))
            self.assertTrue(meta["subsequent_review"]["enabled"])
            self.assertEqual(meta["subsequent_review"]["mode"], "auto")

    def test_new_sandbox_auto_disabled_writes_decision_meta_and_skips_intake(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = self._new_pr_args()
            paths = self._reviewflow_paths(root)
            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[]), mock.patch.object(
                rf,
                "load_chunkhound_runtime_config",
                return_value=({}, {"chunkhound": {}}, {}),
            ), mock.patch.object(rf, "materialize_chunkhound_env_config"), mock.patch.object(
                rf, "gh_api_list", return_value=[]
            ), mock.patch(
                "cure_subsequent_review.control_plane.run_subsequent_review_intake",
                side_effect=AssertionError("intake must not run for auto-disabled decisions"),
            ):
                with self.assertRaises(rf.ReviewflowError):
                    rf._pr_flow_impl(args, paths=paths)
            sessions = list(paths.sandbox_root.iterdir())
            self.assertEqual(len(sessions), 1)
            work_dir = sessions[0] / "work"
            decision_path = work_dir / "subsequent" / "decision.json"
            self.assertTrue(decision_path.is_file())
            decision = json.loads(decision_path.read_text(encoding="utf-8"))
            self.assertFalse(decision["enabled"])
            self.assertIn("no_prior_review_signals", decision["reasons"])
            self.assertFalse((work_dir / "subsequent" / "run_manifest.json").exists())
            meta = json.loads((sessions[0] / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["subsequent_review"]["mode"], "auto")
            self.assertFalse(meta["subsequent_review"]["enabled"])
            self.assertEqual(meta["subsequent_review"]["manifest_path"], None)
            self.assertEqual(meta["paths"]["subsequent_review_decision"], str(decision_path))

    def test_preflight_decision_failure_marks_meta_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = self._new_pr_args()
            paths = self._reviewflow_paths(root)
            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[]), mock.patch.object(
                rf,
                "load_chunkhound_runtime_config",
                return_value=({}, {"chunkhound": {}}, {}),
            ), mock.patch.object(rf, "materialize_chunkhound_env_config"), mock.patch(
                "cure_subsequent_review.decision.decide_subsequent_review",
                side_effect=RuntimeError("decision boom"),
            ):
                with self.assertRaisesRegex(RuntimeError, "decision boom"):
                    rf._pr_flow_impl(args, paths=paths)
            sessions = list(paths.sandbox_root.iterdir())
            self.assertEqual(len(sessions), 1)
            meta = json.loads((sessions[0] / "meta.json").read_text(encoding="utf-8"))
            self._assert_error_meta_preserves_common_artifacts(
                meta=meta,
                session_dir=sessions[0],
                message="decision boom",
            )

    def test_preflight_decision_artifact_write_failure_marks_meta_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = self._new_pr_args()
            paths = self._reviewflow_paths(root)
            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[]), mock.patch.object(
                rf,
                "load_chunkhound_runtime_config",
                return_value=({}, {"chunkhound": {}}, {}),
            ), mock.patch.object(rf, "materialize_chunkhound_env_config"), mock.patch.object(
                rf, "gh_api_list", return_value=[]
            ), mock.patch(
                "cure_subsequent_review.decision.write_json",
                side_effect=OSError("decision write boom"),
            ):
                with self.assertRaisesRegex(OSError, "decision write boom"):
                    rf._pr_flow_impl(args, paths=paths)
            sessions = list(paths.sandbox_root.iterdir())
            self.assertEqual(len(sessions), 1)
            meta = json.loads((sessions[0] / "meta.json").read_text(encoding="utf-8"))
            self._assert_error_meta_preserves_common_artifacts(
                meta=meta,
                session_dir=sessions[0],
                message="decision write boom",
            )

    def test_preflight_enabled_intake_failure_marks_meta_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review = root / "prior.md"
            review.write_text("### A-01: Prior\nSeverity: high\nSection: Security\nEvidence: app.py:1\n", encoding="utf-8")
            completed = rf.HistoricalReviewSession(
                session_id="prior",
                session_dir=root,
                review_md_path=review,
                created_at="2026-01-01T00:00:00Z",
                completed_at="2026-01-02T00:00:00Z",
                verdicts=None,
            )
            args = self._new_pr_args()
            paths = self._reviewflow_paths(root)
            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[completed]), mock.patch.object(
                rf,
                "load_chunkhound_runtime_config",
                return_value=({}, {"chunkhound": {}}, {}),
            ), mock.patch.object(rf, "materialize_chunkhound_env_config"), mock.patch(
                "cure_subsequent_review.control_plane.run_subsequent_review_intake",
                side_effect=RuntimeError("intake boom"),
            ):
                with self.assertRaisesRegex(RuntimeError, "intake boom"):
                    rf._pr_flow_impl(args, paths=paths)
            sessions = list(paths.sandbox_root.iterdir())
            self.assertEqual(len(sessions), 1)
            meta = json.loads((sessions[0] / "meta.json").read_text(encoding="utf-8"))
            self._assert_error_meta_preserves_common_artifacts(
                meta=meta,
                session_dir=sessions[0],
                message="intake boom",
            )

    def test_new_sandbox_explicit_disabled_writes_decision_meta_and_skips_intake(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = self._new_pr_args(subsequent_review_disabled=True)
            paths = self._reviewflow_paths(root)
            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[]), mock.patch.object(
                rf,
                "load_chunkhound_runtime_config",
                return_value=({}, {"chunkhound": {}}, {}),
            ), mock.patch.object(rf, "materialize_chunkhound_env_config"), mock.patch.object(
                rf, "gh_api_list", side_effect=AssertionError("disabled mode must not probe remote")
            ), mock.patch(
                "cure_subsequent_review.control_plane.run_subsequent_review_intake",
                side_effect=AssertionError("intake must not run for explicit-disabled decisions"),
            ):
                with self.assertRaises(rf.ReviewflowError):
                    rf._pr_flow_impl(args, paths=paths)
            sessions = list(paths.sandbox_root.iterdir())
            self.assertEqual(len(sessions), 1)
            work_dir = sessions[0] / "work"
            decision_path = work_dir / "subsequent" / "decision.json"
            self.assertTrue(decision_path.is_file())
            decision = json.loads(decision_path.read_text(encoding="utf-8"))
            self.assertEqual(decision["mode"], "disabled")
            self.assertFalse(decision["enabled"])
            self.assertEqual(decision["reasons"], ["operator_disabled"])
            self.assertFalse((work_dir / "subsequent" / "run_manifest.json").exists())
            meta = json.loads((sessions[0] / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["subsequent_review"]["mode"], "disabled")
            self.assertFalse(meta["subsequent_review"]["enabled"])
            self.assertEqual(meta["subsequent_review"]["manifest_path"], None)

    def test_if_reviewed_latest_available_session_exits_before_sandbox_or_intake(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review = root / "latest.md"
            review.write_text("latest review body\n", encoding="utf-8")
            completed = rf.HistoricalReviewSession(
                session_id="latest",
                session_dir=root,
                review_md_path=review,
                created_at="2026-01-01T00:00:00Z",
                completed_at="2026-01-02T00:00:00Z",
                verdicts=None,
            )
            args = rf.build_parser().parse_args(
                ["pr", "https://github.com/acme/repo/pull/14", "--if-reviewed", "latest"]
            )
            paths = self._reviewflow_paths(root)
            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[completed]), mock.patch(
                "cure_subsequent_review.control_plane.run_subsequent_review_intake",
                side_effect=AssertionError("intake must not run for historical exits"),
            ), mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                self.assertEqual(rf._pr_flow_impl(args, paths=paths), 0)
            self.assertEqual(stdout.getvalue(), "latest review body\n")
            self.assertFalse(paths.sandbox_root.exists())

    def test_if_reviewed_prompt_selected_historical_session_exits_before_sandbox_or_intake(self) -> None:
        class TtyInput(io.StringIO):
            def isatty(self) -> bool:
                return True

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review = root / "selected.md"
            review.write_text("selected review body\n", encoding="utf-8")
            completed = rf.HistoricalReviewSession(
                session_id="selected",
                session_dir=root,
                review_md_path=review,
                created_at="2026-01-01T00:00:00Z",
                completed_at="2026-01-02T00:00:00Z",
                verdicts=None,
            )
            args = rf.build_parser().parse_args(
                ["pr", "https://github.com/acme/repo/pull/14", "--if-reviewed", "prompt"]
            )
            paths = self._reviewflow_paths(root)
            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[completed]), mock.patch(
                "cure_subsequent_review.control_plane.run_subsequent_review_intake",
                side_effect=AssertionError("intake must not run for historical exits"),
            ), mock.patch("sys.stdin", TtyInput("1\n")), mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                self.assertEqual(rf._pr_flow_impl(args, paths=paths), 0)
            self.assertEqual(stdout.getvalue(), "selected review body\n")
            self.assertFalse(paths.sandbox_root.exists())

    def test_if_reviewed_prompt_non_tty_falls_back_to_new_and_runs_intake(self) -> None:
        class NonTtyInput(io.StringIO):
            def isatty(self) -> bool:
                return False

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review = root / "prior.md"
            review.write_text("### A-01: Prior\nSeverity: high\nSection: Security\nEvidence: app.py:1\n", encoding="utf-8")
            completed = rf.HistoricalReviewSession(
                session_id="prior",
                session_dir=root,
                review_md_path=review,
                created_at="2026-01-01T00:00:00Z",
                completed_at="2026-01-02T00:00:00Z",
                verdicts=None,
            )
            args = rf.build_parser().parse_args(
                ["pr", "https://github.com/acme/repo/pull/14", "--if-reviewed", "prompt", "--no-index", "--no-review"]
            )
            paths = self._reviewflow_paths(root)
            intake_calls: list[Path] = []

            def fake_intake(**kwargs: Any) -> Any:
                work_dir = kwargs["work_dir"]
                self.assertTrue(work_dir.is_dir())
                intake_calls.append(work_dir)
                manifest_path = work_dir / "subsequent" / "run_manifest.json"
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_path.write_text("{}\n", encoding="utf-8")
                return type("Result", (), {"manifest_path": manifest_path, "artifact_dir": work_dir / "subsequent"})()

            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[completed]), mock.patch.object(
                rf,
                "load_chunkhound_runtime_config",
                return_value=({}, {"chunkhound": {}}, {}),
            ), mock.patch.object(rf, "materialize_chunkhound_env_config"), mock.patch(
                "cure_subsequent_review.control_plane.run_subsequent_review_intake",
                side_effect=fake_intake,
            ), mock.patch("sys.stdin", NonTtyInput("1\n")):
                with self.assertRaises(rf.ReviewflowError):
                    rf._pr_flow_impl(args, paths=paths)
            self.assertEqual(len(intake_calls), 1)
            self.assertEqual(intake_calls[0].name, "work")


__all__ = ["SubsequentReviewPrFlowIntegrationTests"]
