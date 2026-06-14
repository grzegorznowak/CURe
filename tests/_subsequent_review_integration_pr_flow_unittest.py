# ruff: noqa: F403, F405
from types import SimpleNamespace

from _subsequent_review_test_support import *  # noqa: F401, F403


class SubsequentReviewPrFlowIntegrationTests(SubsequentReviewTestCase):
    def test_pr_flow_rejects_missing_head_sha_before_sandbox_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = self._new_pr_args()
            paths = self._reviewflow_paths(root)
            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {}, "title": "PR"}
            ), self.assertRaisesRegex(rf.ReviewflowError, "head SHA"):
                rf._pr_flow_impl(args, paths=paths)
            self.assertFalse(paths.sandbox_root.exists())

    def test_pr_flow_rejects_invalid_governor_mode_before_sandbox_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = root / "cure.toml"
            cfg.write_text('[subsequent_review]\ngovernor_mode = "audit"\n', encoding="utf-8")
            args = self._new_pr_args()
            paths = self._reviewflow_paths(root)
            with mock.patch.object(rf, "ensure_review_config"), self.assertRaisesRegex(
                rf.ReviewflowError, "governor_mode"
            ):
                rf._pr_flow_impl(args, paths=paths, config_path=cfg)
            self.assertFalse(paths.sandbox_root.exists())

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
                self.assertEqual(kwargs["current_head"], "abc")
                self.assertEqual(
                    kwargs["memory_store"].path,
                    paths.sandbox_root.parent / "pr" / "github.com" / "acme" / "repo" / "14" / "cure_memory.json",
                )
                manifest_path = work_dir / "subsequent" / "run_manifest.json"
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_path.write_text("{}\n", encoding="utf-8")
                return type("Result", (), {"manifest_path": manifest_path, "artifact_dir": work_dir / "subsequent"})()

            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[completed]), mock.patch.object(
                rf,
                "load_chunkhound_runtime_config",
                return_value=(SimpleNamespace(base_config_path=None), {"chunkhound": {}}, {}),
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

    def test_pr_flow_wires_llm_discussion_linker_when_review_llm_is_resolved(self) -> None:
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
                ["pr", "https://github.com/acme/repo/pull/14", "--if-reviewed", "new", "--no-index", "--prompt", "Review"]
            )
            paths = self._reviewflow_paths(root)
            rf.seed_dir(paths, "github.com", "acme", "repo").mkdir(parents=True)
            linker_seen: list[Any] = []

            def fake_run_cmd(cmd: list[str], **_kwargs: Any) -> Any:
                if cmd[:2] == ["git", "clone"]:
                    repo_dir = Path(cmd[-1])
                    repo_dir.mkdir(parents=True, exist_ok=True)
                    (repo_dir / "app.py").write_text("print('current')\n", encoding="utf-8")
                stdout = "abc\n" if cmd[-2:] == ["rev-parse", "HEAD"] else "https://github.com/acme/repo.git\n"
                return rf.CommandResult(cmd=cmd, cwd=None, exit_code=0, duration_seconds=0.0, stdout=stdout, stderr="")

            def fake_checkout(*, repo_dir: Path, pr: Any) -> None:
                _ = pr
                repo_dir.mkdir(parents=True, exist_ok=True)
                (repo_dir / "app.py").write_text("print('current')\n", encoding="utf-8")

            def fake_intake(**kwargs: Any) -> Any:
                linker_seen.append(kwargs.get("discussion_linker"))
                self.assertIsNotNone(kwargs.get("discussion_linker"))
                self.assertEqual(kwargs["current_head"], "abc")
                raise RuntimeError("stop after linker wiring proof")

            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[completed]), mock.patch.object(
                rf,
                "load_chunkhound_runtime_config",
                return_value=(SimpleNamespace(base_config_path=None), {"chunkhound": {}}, {}),
            ), mock.patch.object(rf, "materialize_chunkhound_env_config"), mock.patch.object(
                rf, "gh_api_list", return_value=[]
            ), mock.patch.object(
                rf,
                "resolve_llm_config_from_args",
                return_value=({"provider": "http", "preset": "fixture", "model": "fixture"}, {"source": "test"}),
            ), mock.patch.object(
                rf,
                "_maybe_apply_pr_llm_picker",
                side_effect=lambda *, llm_resolved, llm_resolution_meta: (llm_resolved, llm_resolution_meta),
            ), mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd), mock.patch.object(
                rf, "ensure_clean_git_worktree"
            ), mock.patch.object(rf, "checkout_pr_in_repo", side_effect=fake_checkout), mock.patch.object(
                rf, "compute_pr_stats", return_value={"changed_files": 1, "changed_lines": 1}
            ), mock.patch.object(
                rf,
                "prepare_review_agent_runtime",
                return_value={"env": {}, "metadata": {}, "add_dirs": [], "codex_config_overrides": []},
            ), mock.patch.object(rf, "_run_chunkhound_access_preflight"), mock.patch.object(
                rf, "_run_review_intelligence_preflight"
            ), mock.patch(
                "cure_subsequent_review.control_plane.run_subsequent_review_intake",
                side_effect=fake_intake,
            ):
                with self.assertRaisesRegex(RuntimeError, "linker wiring proof"):
                    rf._pr_flow_impl(args, paths=paths)

            self.assertEqual(len(linker_seen), 1)
            from cure_subsequent_review.discussion_linker import LlmDiscussionLinker

            self.assertIsInstance(linker_seen[0], LlmDiscussionLinker)

    def test_pr_flow_wires_llm_finding_verifier_after_repo_checkout(self) -> None:
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
                ["pr", "https://github.com/acme/repo/pull/14", "--if-reviewed", "new", "--no-index", "--prompt", "Review"]
            )
            paths = self._reviewflow_paths(root)
            rf.seed_dir(paths, "github.com", "acme", "repo").mkdir(parents=True)
            verifier_seen: list[Any] = []

            def fake_run_cmd(cmd: list[str], **_kwargs: Any) -> Any:
                if cmd[:2] == ["git", "clone"]:
                    repo_dir = Path(cmd[-1])
                    repo_dir.mkdir(parents=True, exist_ok=True)
                    (repo_dir / "app.py").write_text("print('current')\n", encoding="utf-8")
                stdout = "abc\n" if cmd[-2:] == ["rev-parse", "HEAD"] else "https://github.com/acme/repo.git\n"
                return rf.CommandResult(cmd=cmd, cwd=None, exit_code=0, duration_seconds=0.0, stdout=stdout, stderr="")

            def fake_checkout(*, repo_dir: Path, pr: Any) -> None:
                _ = pr
                repo_dir.mkdir(parents=True, exist_ok=True)
                (repo_dir / "app.py").write_text("print('current')\n", encoding="utf-8")

            def fake_intake(**kwargs: Any) -> Any:
                verifier = kwargs.get("source_verifier")
                verifier_seen.append(verifier)
                self.assertIsNotNone(verifier)
                self.assertTrue((verifier.repo_dir / "app.py").is_file())
                self.assertEqual(kwargs["pr_files_changed"], ("app.py",))
                raise RuntimeError("stop after verifier wiring proof")

            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[completed]), mock.patch.object(
                rf,
                "load_chunkhound_runtime_config",
                return_value=(SimpleNamespace(base_config_path=None), {"chunkhound": {}}, {}),
            ), mock.patch.object(rf, "materialize_chunkhound_env_config"), mock.patch.object(
                rf, "gh_api_list", return_value=[]
            ), mock.patch.object(
                rf,
                "resolve_llm_config_from_args",
                return_value=({"provider": "http", "preset": "fixture", "model": "fixture"}, {"source": "test"}),
            ), mock.patch.object(
                rf,
                "_maybe_apply_pr_llm_picker",
                side_effect=lambda *, llm_resolved, llm_resolution_meta: (llm_resolved, llm_resolution_meta),
            ), mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd), mock.patch.object(
                rf, "ensure_clean_git_worktree"
            ), mock.patch.object(rf, "checkout_pr_in_repo", side_effect=fake_checkout), mock.patch.object(
                rf, "compute_pr_stats", return_value={"changed_files": 1, "changed_lines": 1, "files": ["app.py"]}
            ), mock.patch.object(
                rf,
                "prepare_review_agent_runtime",
                return_value={"env": {}, "metadata": {}, "add_dirs": [], "codex_config_overrides": []},
            ), mock.patch.object(rf, "_run_chunkhound_access_preflight"), mock.patch.object(
                rf, "_run_review_intelligence_preflight"
            ), mock.patch(
                "cure_subsequent_review.control_plane.run_subsequent_review_intake",
                side_effect=fake_intake,
            ):
                with self.assertRaisesRegex(RuntimeError, "verifier wiring proof"):
                    rf._pr_flow_impl(args, paths=paths)

            self.assertEqual(len(verifier_seen), 1)
            from cure_subsequent_review.llm_verifier import LlmFindingVerifier

            self.assertIsInstance(verifier_seen[0], LlmFindingVerifier)

    def test_pr_flow_reuses_controller_discussion_for_decision_and_intake(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = self._new_pr_args()
            paths = self._reviewflow_paths(root)
            api_paths: list[str] = []
            intake_kwargs: list[dict[str, Any]] = []

            def fake_gh_list(*, host: str, path: str, allow_public_fallback: bool = False) -> Any:
                api_paths.append(path)
                self.assertEqual(host, "github.com")
                self.assertTrue(allow_public_fallback)
                if path.endswith("/issues/14/comments"):
                    return [
                        {
                            "id": 777,
                            "user": {"login": "human-operator"},
                            "body": "CURe Review\n### CURE-777: prior finding\nSeverity: high\nSection: Security\nEvidence: app.py:1\n" + CURE_FOOTER_BLOCK,
                            "created_at": "2026-01-01T00:00:00Z",
                        }
                    ]
                return []

            def fake_intake(**kwargs: Any) -> Any:
                intake_kwargs.append(kwargs)
                prefetched = kwargs["prefetched_discussion"]
                self.assertIsNotNone(prefetched)
                self.assertEqual([event.event_id for event in prefetched.events], ["777"])
                work_dir = kwargs["work_dir"]
                manifest_path = work_dir / "subsequent" / "run_manifest.json"
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_path.write_text("{}\n", encoding="utf-8")
                return type("Result", (), {"manifest_path": manifest_path, "artifact_dir": work_dir / "subsequent"})()

            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[]), mock.patch.object(
                rf,
                "load_chunkhound_runtime_config",
                return_value=(SimpleNamespace(base_config_path=None), {"chunkhound": {}}, {}),
            ), mock.patch.object(rf, "materialize_chunkhound_env_config"), mock.patch.object(
                rf, "gh_api_list", side_effect=fake_gh_list
            ), mock.patch(
                "cure_subsequent_review.control_plane.run_subsequent_review_intake",
                side_effect=fake_intake,
            ):
                with self.assertRaises(rf.ReviewflowError):
                    rf._pr_flow_impl(args, paths=paths)

            self.assertEqual(len(intake_kwargs), 1)
            self.assertEqual(len(api_paths), 3)
            sessions = list(paths.sandbox_root.iterdir())
            decision = json.loads((sessions[0] / "work" / "subsequent" / "decision.json").read_text(encoding="utf-8"))
            self.assertTrue(decision["enabled"])
            self.assertEqual(decision["signal_counts"]["remote_events"], 1)
            self.assertEqual(decision["signal_counts"]["remote_cure_markers"], 1)

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
                return_value=(SimpleNamespace(base_config_path=None), {"chunkhound": {}}, {}),
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
            self.assertFalse((work_dir / "subsequent" / "degraded_runtime.json").exists())
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
                return_value=(SimpleNamespace(base_config_path=None), {"chunkhound": {}}, {}),
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
                return_value=(SimpleNamespace(base_config_path=None), {"chunkhound": {}}, {}),
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
                return_value=(SimpleNamespace(base_config_path=None), {"chunkhound": {}}, {}),
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
                return_value=(SimpleNamespace(base_config_path=None), {"chunkhound": {}}, {}),
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
                return_value=(SimpleNamespace(base_config_path=None), {"chunkhound": {}}, {}),
            ), mock.patch.object(rf, "materialize_chunkhound_env_config"), mock.patch(
                "cure_subsequent_review.control_plane.run_subsequent_review_intake",
                side_effect=fake_intake,
            ), mock.patch("sys.stdin", NonTtyInput("1\n")):
                with self.assertRaises(rf.ReviewflowError):
                    rf._pr_flow_impl(args, paths=paths)
            self.assertEqual(len(intake_calls), 1)
            self.assertEqual(intake_calls[0].name, "work")


__all__ = ["SubsequentReviewPrFlowIntegrationTests"]
