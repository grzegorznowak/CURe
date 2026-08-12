# ruff: noqa: F403, F405
import contextlib
import shutil

from _reviewflow_unittest_shared import *  # noqa: F401, F403


PR_URL = "https://github.com/acme/repo/pull/9"
REVIEW_TEXT = (
    "# Final Review\n\n"
    "## Verdicts\n"
    "- business: APPROVE\n"
    "- technical: APPROVE\n\n"
    "The PR looks good."
)
EXPLAIN_ARTIFACT_TEXT = "This is a human-friendly explanation."
DEFAULT_PROMPT_TEXT = "Default explain prompt text"


def _write_completed_session(
    *, root: Path, session_id: str = "session-1", extra_meta: dict[str, object] | None = None
) -> tuple[Path, Path]:
    session_dir = root / session_id
    repo_dir = session_dir / "repo"
    work_dir = session_dir / "work"
    repo_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    review_md = session_dir / "review.md"
    review_md.write_text(REVIEW_TEXT, encoding="utf-8")
    meta = {
        "session_id": session_id,
        "status": "done",
        "created_at": "2026-03-10T00:00:00+00:00",
        "completed_at": "2026-03-10T00:05:00+00:00",
        "pr_url": PR_URL,
        "host": "github.com",
        "owner": "acme",
        "repo": "repo",
        "number": 9,
        "base_ref": "main",
        "base_ref_for_review": "cure_base__main",
        "prompt": {"profile_resolved": "normal"},
        "paths": {
            "session_dir": str(session_dir),
            "repo_dir": str(repo_dir),
            "work_dir": str(work_dir),
            "review_md": str(review_md),
        },
    }
    meta.update(extra_meta or {})
    (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return session_dir, review_md


BASE_CODEX_SESSION_ID = "019fcb76-feae-7a92-bb26-004e32d93522"


def _write_fake_codex_session(
    *, codex_root: Path, session_id: str = BASE_CODEX_SESSION_ID
) -> Path:
    day_dir = codex_root / "sessions" / "2026" / "08" / "04"
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"rollout-2026-08-04T06-30-01-{session_id}.jsonl"
    meta_line = json.dumps(
        {
            "timestamp": "2026-08-04T06:30:01.000Z",
            "type": "session_meta",
            "payload": {
                "session_id": session_id,
                "id": session_id,
                "timestamp": "2026-08-04T06:30:01.000Z",
                "cwd": "/repo",
                "originator": "codex_exec",
                "cli_version": "0.144.6",
            },
        }
    )
    event_line = json.dumps(
        {
            "timestamp": "2026-08-04T06:31:00.000Z",
            "type": "event_msg",
            "payload": {"type": "agent_message", "text": "BASE CONTENT"},
        }
    )
    path.write_text(meta_line + "\n" + event_line + "\n", encoding="utf-8")
    return path


def _explain_args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "pr_url": PR_URL,
        "explain_prompt": None,
        "codex_model": None,
        "codex_effort": None,
        "codex_plan_effort": None,
        "quiet": True,
        "no_stream": True,
        "verbosity": "normal",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class ExplainCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = ROOT / ".tmp_test_explain_command"
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)
        self.paths = rf.ReviewflowPaths(sandbox_root=self.root, cache_root=self.root / "cache")

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def _patched_run(
        self,
        args: argparse.Namespace,
        *,
        resolved: dict[str, object] | None = None,
        resolve_error: bool = False,
        llm_fail: bool = False,
        record_file_lock: bool = False,
        staged_paths_value: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Run _explain_flow_impl with mocked LLM plumbing; return captured kwargs + stdout."""
        captured: dict[str, object] = {"_builtin_calls": []}
        llm_resolved = resolved or {
            "provider": "codex",
            "preset": "codex-cli",
            "model": "gpt-test",
        }

        def fake_run_llm_exec(**kwargs: object) -> rf.LlmRunResult:
            captured.update(kwargs)
            if llm_fail:
                raise rf.ReviewflowError("llm exploded")
            Path(str(kwargs["output_path"])).write_text(EXPLAIN_ARTIFACT_TEXT, encoding="utf-8")
            return rf.LlmRunResult(
                resume=None,
                adapter_meta={
                    "transport": "cli-codex",
                    "usage": {"input_tokens": 120, "output_tokens": 30},
                },
            )

        def fake_load_builtin_prompt_text(name: str) -> str:
            captured["_builtin_calls"].append(name)  # type: ignore[attr-defined]
            return DEFAULT_PROMPT_TEXT

        def fake_stage_auth_support(
            *, work_dir: Path, env: dict[str, str], stage_rf_jira: bool
        ) -> tuple[dict[str, str], dict[str, str]]:
            captured["_stage_rf_jira"] = stage_rf_jira
            return dict(env), (staged_paths_value if staged_paths_value is not None else {})

        out = StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "resolve_llm_config_from_args",
                    side_effect=rf.ReviewflowError("bad llm config") if resolve_error else None,
                    return_value=(
                        None if resolve_error else (llm_resolved, {})
                    ),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    rf, "_stage_review_auth_support", side_effect=fake_stage_auth_support
                )
            )
            stack.enter_context(mock.patch.object(rf, "run_llm_exec", side_effect=fake_run_llm_exec))
            stack.enter_context(
                mock.patch.object(rf, "load_builtin_prompt_text", side_effect=fake_load_builtin_prompt_text)
            )
            if record_file_lock:
                captured["_file_lock_mock"] = stack.enter_context(
                    mock.patch.object(rf, "file_lock", wraps=rf.file_lock)
                )
            with contextlib.redirect_stdout(out):
                rc = rf._explain_flow_impl(args, paths=self.paths)
        captured["_stdout"] = out.getvalue()
        captured["_rc"] = rc
        return captured

    # -- obligations -------------------------------------------------------

    def test_explain_flow_uses_default_prompt_and_prints_explanation(self) -> None:
        _write_completed_session(root=self.root)
        captured = self._patched_run(_explain_args())
        self.assertEqual(captured["_rc"], 0)
        self.assertEqual(captured["_builtin_calls"], ["explain.md"])

        prompt = str(captured["prompt"])
        self.assertIn(DEFAULT_PROMPT_TEXT, prompt)
        self.assertIn("## Final synthesized review", prompt)
        self.assertIn("The PR looks good.", prompt)
        self.assertIs(captured["stream"], False)

        output_path = Path(str(captured["output_path"]))
        self.assertTrue(output_path.is_file())
        self.assertEqual(output_path.read_text(encoding="utf-8"), EXPLAIN_ARTIFACT_TEXT)
        self.assertEqual(output_path.parent, self.root / "session-1" / "explain")

        stdout = str(captured["_stdout"])
        self.assertIn(EXPLAIN_ARTIFACT_TEXT, stdout)
        self.assertIn(str(output_path), stdout)

        meta = json.loads((self.root / "session-1" / "meta.json").read_text(encoding="utf-8"))
        # Explain usage/provenance is recorded per explanation, never merged into
        # the original review's top-level llm block (PR#37 review finding).
        self.assertNotIn("llm", meta)
        entry = meta["explains"][0]
        self.assertEqual(entry["output_path"], str(output_path))
        self.assertEqual(entry["prompt_source"], "builtin:explain.md")
        self.assertEqual(entry["provider"], "codex")
        self.assertEqual(entry["model"], "gpt-test")
        self.assertEqual(entry["preset"], "codex-cli")
        self.assertEqual(entry["transport"], "cli-codex")
        self.assertEqual(entry["usage"], {"input_tokens": 120, "output_tokens": 30, "total_tokens": 150})

    def test_explain_flow_user_question_appended_to_builtin_prompt(self) -> None:
        _write_completed_session(root=self.root)
        captured = self._patched_run(_explain_args(explain_prompt="Why did you flag X?"))
        self.assertEqual(captured["_rc"], 0)
        # The builtin template stays the base; the user text is appended as the
        # question (additive contract, PR#37 follow-up).
        self.assertEqual(captured["_builtin_calls"], ["explain.md"])
        prompt = str(captured["prompt"])
        self.assertTrue(prompt.startswith(DEFAULT_PROMPT_TEXT))
        self.assertIn("## User's question\nWhy did you flag X?", prompt)
        self.assertIn("## Final synthesized review", prompt)
        self.assertIn("The PR looks good.", prompt)
        # The question lands after the review so it is the last user content.
        self.assertLess(
            prompt.index("## Final synthesized review"), prompt.index("## User's question")
        )

        meta = json.loads((self.root / "session-1" / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["explains"][0]["prompt_source"], "user:explain_prompt")
        self.assertEqual(meta["explains"][0]["question"], "Why did you flag X?")

    def test_explain_flow_default_prompt_has_no_question_block(self) -> None:
        _write_completed_session(root=self.root)
        captured = self._patched_run(_explain_args())
        prompt = str(captured["prompt"])
        self.assertNotIn("## User's question", prompt)
        meta = json.loads((self.root / "session-1" / "meta.json").read_text(encoding="utf-8"))
        self.assertNotIn("question", meta["explains"][0])

    def test_explain_flow_fork_mode_appends_user_question(self) -> None:
        codex_root = self.root / "codex-home"
        _write_fake_codex_session(codex_root=codex_root)
        _write_completed_session(root=self.root, extra_meta=self._codex_meta())
        with mock.patch.dict(os.environ, {"CODEX_HOME": str(codex_root)}):
            captured = self._patched_run(
                _explain_args(explain_prompt="Explain in simpler terms with examples."),
                resolved={"provider": "codex", "preset": "codex-cli", "model": "gpt-5.6-sol"},
            )
        self.assertEqual(captured["_rc"], 0)
        prompt = str(captured["prompt"])
        self.assertIn("already in your conversation history", prompt)
        self.assertIn(DEFAULT_PROMPT_TEXT, prompt)
        self.assertIn("## User's question\nExplain in simpler terms with examples.", prompt)
        self.assertNotIn("## Final synthesized review", prompt)

    def test_explain_flow_streams_when_not_quiet(self) -> None:
        _write_completed_session(root=self.root)
        captured = self._patched_run(_explain_args(quiet=False, no_stream=False))
        self.assertEqual(captured["_rc"], 0)
        self.assertIs(captured["stream"], True)

    def test_explain_flow_skips_rf_jira_staging_in_repo_checkout(self) -> None:
        _write_completed_session(root=self.root)
        captured = self._patched_run(_explain_args())
        self.assertEqual(captured["_rc"], 0)
        self.assertIs(captured["_stage_rf_jira"], False)

    def test_explain_flow_skips_artifact_normalization(self) -> None:
        _write_completed_session(root=self.root)
        captured = self._patched_run(_explain_args())
        self.assertEqual(captured["_rc"], 0)
        self.assertIs(captured["normalize_artifact"], False)

    def test_explain_flow_merges_progress_meta_under_lock(self) -> None:
        _write_completed_session(root=self.root)
        progress_kwargs: dict[str, object] = {}

        class _RecordingProgress(rf.SessionProgress):
            def __init__(self, *args: object, **kwargs: object) -> None:
                progress_kwargs.update(kwargs)
                super().__init__(*args, **kwargs)  # type: ignore[arg-type]

        with mock.patch.object(rf, "SessionProgress", _RecordingProgress):
            captured = self._patched_run(_explain_args())
        self.assertEqual(captured["_rc"], 0)
        self.assertIs(progress_kwargs["merge_under_lock"], True)

    def test_explain_flow_rejects_repo_dir_outside_session(self) -> None:
        outside = self.root / "elsewhere"
        outside.mkdir(parents=True, exist_ok=True)
        _write_completed_session(
            root=self.root,
            extra_meta={"paths": {"repo_dir": str(outside)}},
        )
        with self.assertRaisesRegex(rf.ReviewflowError, "repo_dir.*session dir"):
            rf._explain_flow_impl(_explain_args(), paths=self.paths)

    def test_explain_flow_rejects_review_md_outside_session(self) -> None:
        outside = self.root / "outside-review.md"
        outside.write_text(REVIEW_TEXT, encoding="utf-8")
        _write_completed_session(
            root=self.root,
            extra_meta={"paths": {"review_md": str(outside)}},
        )
        with self.assertRaisesRegex(rf.ReviewflowError, "review_md.*session dir"):
            rf._explain_flow_impl(_explain_args(), paths=self.paths)

    def test_explain_flow_inline_prompt_has_no_resume_note(self) -> None:
        _write_completed_session(root=self.root)
        captured = self._patched_run(_explain_args())
        prompt = str(captured["prompt"])
        self.assertIn("## Final synthesized review", prompt)
        self.assertNotIn("already in your conversation history", prompt)

    def test_session_progress_merge_mode_preserves_concurrent_appends(self) -> None:
        session_dir, _ = _write_completed_session(root=self.root)
        meta_path = session_dir / "meta.json"
        # A concurrent explain run already appended its entry while this run held
        # its stale snapshot (PR#37 review finding: stale flushes erase appends).
        on_disk = json.loads(meta_path.read_text(encoding="utf-8"))
        on_disk.setdefault("explains", []).append({"prompt_source": "concurrent"})
        meta_path.write_text(json.dumps(on_disk), encoding="utf-8")

        stale = json.loads(meta_path.read_text(encoding="utf-8"))
        stale.pop("explains")
        progress = rf.SessionProgress(meta_path, quiet=True, merge_under_lock=True)
        progress.meta = stale
        progress.set_phase("explain")

        after = json.loads(meta_path.read_text(encoding="utf-8"))
        self.assertEqual(after["phase"], "explain")
        self.assertEqual([e["prompt_source"] for e in after["explains"]], ["concurrent"])

    def test_explain_flow_no_completed_session_raises(self) -> None:
        with self.assertRaisesRegex(rf.ReviewflowError, "No completed review session"):
            rf._explain_flow_impl(_explain_args(), paths=self.paths)

    def test_explain_flow_invalid_pr_url_raises(self) -> None:
        with self.assertRaisesRegex(rf.ReviewflowError, "Invalid PR URL"):
            rf._explain_flow_impl(_explain_args(pr_url="not a pr url at all"), paths=self.paths)

    def test_explain_flow_cleans_staged_paths_on_llm_failure(self) -> None:
        _write_completed_session(root=self.root)
        cleaned: list[object] = []

        def fake_stage_auth_support(
            *, work_dir: Path, env: dict[str, str], stage_rf_jira: bool
        ) -> tuple[dict[str, str], dict[str, str]]:
            return dict(env), {"staged": "path"}

        def fake_run_llm_exec(**kwargs: object) -> rf.LlmRunResult:
            raise rf.ReviewflowError("llm exploded")

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "resolve_llm_config_from_args",
                    return_value=({"provider": "codex", "preset": "codex-cli"}, {}),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    rf, "_stage_review_auth_support", side_effect=fake_stage_auth_support
                )
            )
            stack.enter_context(mock.patch.object(rf, "run_llm_exec", side_effect=fake_run_llm_exec))
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "cleanup_sensitive_staged_paths",
                    side_effect=lambda staged: cleaned.append(staged),
                )
            )
            with self.assertRaisesRegex(rf.ReviewflowError, "llm exploded"):
                rf._explain_flow_impl(_explain_args(), paths=self.paths)
        self.assertEqual(cleaned, [{"staged": "path"}])

    def test_explain_subparser_registers_arguments(self) -> None:
        parser = rf.build_parser(prog="cure")
        args = parser.parse_args(
            [
                "explain",
                PR_URL,
                "--explain-prompt",
                "hello",
                "--open-in-codex",
                "--quiet",
                "--no-stream",
            ]
        )
        self.assertEqual(args.cmd, "explain")
        self.assertEqual(args.pr_url, PR_URL)
        self.assertEqual(args.explain_prompt, "hello")
        self.assertTrue(args.open_in_codex)
        self.assertTrue(args.quiet)
        self.assertTrue(args.no_stream)

    def test_explain_subparser_requires_pr_url(self) -> None:
        parser = rf.build_parser(prog="cure")
        with self.assertRaises(SystemExit):
            parser.parse_args(["explain", "--explain-prompt", "hello"])

    def test_explain_catalog_entry_present(self) -> None:
        payload = cure_commands.build_commands_catalog_payload()
        names = [str(c["name"]) for c in payload["commands"]]
        self.assertIn("explain", names)

    def test_explain_flow_wrapper_delegates_to_impl(self) -> None:
        _write_completed_session(root=self.root)
        with mock.patch.object(rf, "_explain_flow_impl", return_value=7) as impl:
            rc = cure_commands.explain_flow(
                _explain_args(), paths=self.paths, config_path=None, codex_base_config_path=None
            )
        self.assertEqual(rc, 7)
        impl.assert_called_once()

    # -- codex resume-fork obligations --------------------------------------

    def _codex_meta(self) -> dict[str, object]:
        return {
            "llm": {
                "resume": {
                    "provider": "codex",
                    "session_id": BASE_CODEX_SESSION_ID,
                    "cwd": "/repo",
                    "command": "codex resume " + BASE_CODEX_SESSION_ID,
                }
            },
            "codex": {"resume": {"session_id": BASE_CODEX_SESSION_ID}},
        }

    def test_explain_flow_forks_codex_session_and_resumes(self) -> None:
        codex_root = self.root / "codex-home"
        base_path = _write_fake_codex_session(codex_root=codex_root)
        base_before = base_path.read_bytes()
        _write_completed_session(root=self.root, extra_meta=self._codex_meta())

        with mock.patch.dict(os.environ, {"CODEX_HOME": str(codex_root)}), mock.patch.object(
            rf, "log"
        ) as log_mock:
            captured = self._patched_run(
                _explain_args(),
                resolved={"provider": "codex", "preset": "codex-cli", "model": "gpt-5.6-sol"},
            )

        resume_lines = [
            str(c.args[0]) for c in log_mock.call_args_list if "EXPLAIN resume" in str(c.args[0])
        ]
        self.assertEqual(len(resume_lines), 1)
        self.assertIn("replaying the full review context", resume_lines[0])

        self.assertEqual(captured["_rc"], 0)
        self.assertEqual(captured["_builtin_calls"], ["explain.md"])

        fork_id = captured.get("resume_session_id")
        self.assertIsNotNone(fork_id)
        self.assertNotEqual(str(fork_id), BASE_CODEX_SESSION_ID)
        self.assertIs(captured["stream"], False)

        # The fork must exist in the codex store and carry the base content.
        forks = sorted(codex_root.glob("sessions/*/*/*/rollout-*.jsonl"))
        self.assertEqual([p for p in forks if p != base_path], [p for p in forks if str(fork_id) in p.name])
        fork_path = next(p for p in forks if p != base_path)
        fork_text = fork_path.read_text(encoding="utf-8")
        self.assertIn(str(fork_id), fork_text)
        self.assertNotIn(BASE_CODEX_SESSION_ID, fork_text)
        self.assertIn("BASE CONTENT", fork_text)
        # The base must remain byte-identical.
        self.assertEqual(base_path.read_bytes(), base_before)

        # Resume mode passes the builtin template WITHOUT appending the review
        # text, but WITH an explicit instruction that the review is already in
        # context and must not be re-produced (PR#37 report: the model re-emitted
        # the whole review when the template referenced 'below' content that does
        # not exist in fork mode).
        prompt = str(captured["prompt"])
        self.assertIn(DEFAULT_PROMPT_TEXT, prompt)
        self.assertIn("already in your conversation history", prompt)
        self.assertIn("Do NOT re-produce", prompt)
        self.assertNotIn("## Final synthesized review", prompt)

        meta = json.loads((self.root / "session-1" / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(
            meta["explains"][0]["resume"],
            {
                "mode": "fork",
                "base_session_id": BASE_CODEX_SESSION_ID,
                "fork_session_id": str(fork_id),
                "interactive_command": f"codex resume {fork_id}",
            },
        )
        # The recorded resume info must NOT be overwritten (interactive gates pristine base).
        self.assertEqual(
            meta["llm"]["resume"]["session_id"], BASE_CODEX_SESSION_ID
        )

    def test_explain_flow_open_in_codex_hands_off_to_interactive_resume(self) -> None:
        codex_root = self.root / "codex-home"
        _write_fake_codex_session(codex_root=codex_root)
        _write_completed_session(root=self.root, extra_meta=self._codex_meta())
        handoffs: list[dict[str, object]] = []

        def fake_handoff(**kwargs: object) -> int:
            handoffs.append(kwargs)
            return 0

        with mock.patch.dict(os.environ, {"CODEX_HOME": str(codex_root)}), mock.patch.object(
            rf, "_open_interactive_codex_resume", side_effect=fake_handoff
        ):
            captured = self._patched_run(
                _explain_args(open_in_codex=True),
                resolved={"provider": "codex", "preset": "codex-cli", "model": "gpt-5.6-sol"},
            )

        self.assertEqual(captured["_rc"], 0)
        self.assertEqual(len(handoffs), 1)
        fork_id = captured.get("resume_session_id")
        self.assertIsNotNone(fork_id)
        self.assertEqual(handoffs[0]["fork_session_id"], str(fork_id))
        self.assertEqual(handoffs[0]["repo_dir"], self.root / "session-1" / "repo")
        handoff_env = handoffs[0]["base_env"]
        assert isinstance(handoff_env, dict)
        # Staged credential pointers are dropped: the interactive session uses
        # the user's own credentials.
        for key in ("GH_CONFIG_DIR", "JIRA_CONFIG_FILE", "NETRC"):
            self.assertNotIn(key, handoff_env)

    def test_explain_flow_does_not_hand_off_without_flag(self) -> None:
        codex_root = self.root / "codex-home"
        _write_fake_codex_session(codex_root=codex_root)
        _write_completed_session(root=self.root, extra_meta=self._codex_meta())

        with mock.patch.dict(os.environ, {"CODEX_HOME": str(codex_root)}), mock.patch.object(
            rf, "_open_interactive_codex_resume"
        ) as handoff_mock:
            captured = self._patched_run(
                _explain_args(),
                resolved={"provider": "codex", "preset": "codex-cli", "model": "gpt-5.6-sol"},
            )

        self.assertEqual(captured["_rc"], 0)
        handoff_mock.assert_not_called()

    def test_explain_flow_inline_when_codex_without_resume_info(self) -> None:
        codex_root = self.root / "codex-home"
        _write_fake_codex_session(codex_root=codex_root)
        _write_completed_session(root=self.root)

        with mock.patch.dict(os.environ, {"CODEX_HOME": str(codex_root)}):
            captured = self._patched_run(
                _explain_args(),
                resolved={"provider": "codex", "preset": "codex-cli", "model": "gpt-5.6-sol"},
            )

        self.assertIsNone(captured.get("resume_session_id"))
        self.assertIn("## Final synthesized review", str(captured["prompt"]))
        rollouts = list(codex_root.glob("sessions/*/*/*/rollout-*.jsonl"))
        self.assertEqual(len(rollouts), 1)

    def test_explain_flow_inline_when_base_codex_session_is_missing(self) -> None:
        codex_root = self.root / "codex-home"
        _write_completed_session(root=self.root, extra_meta=self._codex_meta())

        with mock.patch.dict(os.environ, {"CODEX_HOME": str(codex_root)}):
            captured = self._patched_run(_explain_args())

        self.assertIsNone(captured.get("resume_session_id"))
        self.assertIn("## Final synthesized review", str(captured["prompt"]))
        rollouts = list(codex_root.glob("sessions/*/*/*/rollout-*.jsonl"))
        self.assertEqual(rollouts, [])

    def test_explain_flow_forks_fallback_inline_when_base_missing(self) -> None:
        codex_root = self.root / "codex-home"
        codex_root.mkdir(parents=True, exist_ok=True)
        _write_completed_session(root=self.root, extra_meta=self._codex_meta())

        with mock.patch.dict(os.environ, {"CODEX_HOME": str(codex_root)}):
            captured = self._patched_run(
                _explain_args(),
                resolved={"provider": "codex", "preset": "codex-cli", "model": "gpt-5.6-sol"},
            )

        self.assertEqual(captured["_rc"], 0)
        self.assertIsNone(captured.get("resume_session_id"))
        self.assertIn("## Final synthesized review", str(captured["prompt"]))
        meta = json.loads((self.root / "session-1" / "meta.json").read_text(encoding="utf-8"))
        self.assertNotIn("resume", meta["explains"][0])

    def test_fork_codex_session_raises_when_base_missing(self) -> None:
        codex_root = self.root / "codex-home"
        codex_root.mkdir(parents=True, exist_ok=True)
        with self.assertRaisesRegex(rf.ReviewflowError, "not found"):
            rf.fork_codex_session(
                codex_root=codex_root,
                session_id=BASE_CODEX_SESSION_ID,
                created_at="2026-08-04T06:30:00+00:00",
                completed_at="2026-08-04T06:35:31+00:00",
            )

    def test_fork_codex_session_treats_malformed_rollout_as_missing(self) -> None:
        """Valid JSON that is not an object (null / []) must behave like a
        missing base — a normal fork failure — never a programming error."""
        for malformed in ("null", "[]", '"a string"', "42"):
            codex_root = self.root / f"codex-home-malformed-{malformed}"
            shutil.rmtree(codex_root, ignore_errors=True)
            _write_fake_codex_session(codex_root=codex_root)
            rollout_name = f"rollout-2026-08-04T06-30-01-{BASE_CODEX_SESSION_ID}.jsonl"
            rollout = codex_root / "sessions" / "2026" / "08" / "04" / rollout_name
            rollout.write_text(malformed + "\n", encoding="utf-8")
            with self.assertRaisesRegex(rf.ReviewflowError, "not found"):
                rf.fork_codex_session(
                    codex_root=codex_root,
                    session_id=BASE_CODEX_SESSION_ID,
                    created_at="2026-08-04T06:30:00+00:00",
                    completed_at="2026-08-04T06:35:31+00:00",
                )

    def test_fork_codex_session_rewrites_ids_and_preserves_base(self) -> None:
        codex_root = self.root / "codex-home"
        base_path = _write_fake_codex_session(codex_root=codex_root)
        base_before = base_path.read_bytes()

        new_id, fork_path = rf.fork_codex_session(
            codex_root=codex_root,
            session_id=BASE_CODEX_SESSION_ID,
            created_at="2026-08-04T06:30:00+00:00",
            completed_at="2026-08-04T06:35:31+00:00",
        )

        self.assertNotEqual(new_id, BASE_CODEX_SESSION_ID)
        self.assertTrue(fork_path.is_file())
        fork_text = fork_path.read_text(encoding="utf-8")
        self.assertIn(new_id, fork_text)
        self.assertNotIn(BASE_CODEX_SESSION_ID, fork_text)
        self.assertEqual(base_path.read_bytes(), base_before)

    # -- PR #37 review remediation obligations ------------------------------

    def test_build_codex_exec_cmd_resume_filters_incompatible_flags_and_read_only(self) -> None:
        cmd = rf.build_codex_exec_cmd(
            repo_dir=self.root,
            codex_flags=[
                "-m", "gpt-5.6-sol",
                "--sandbox", "workspace-write",
                "--search",
                "-c", "model_reasoning_effort=high",
            ],
            codex_config_overrides=[],
            review_md_path=self.root / "out.md",
            prompt="why?",
            skip_git_repo_check=True,
            dangerously_bypass_approvals_and_sandbox=False,
            json_output=True,
            resume_session_id="fork-1",
            sandbox_mode="read-only",
        )
        self.assertEqual(cmd[:4], ["codex", "exec", "resume", "fork-1"])
        self.assertIn("-m", cmd)
        self.assertIn("gpt-5.6-sol", cmd)
        self.assertIn("-c", cmd)
        self.assertIn("model_reasoning_effort=high", cmd)
        self.assertIn('sandbox_mode="read-only"', cmd)
        self.assertIn("--skip-git-repo-check", cmd)
        self.assertNotIn("--sandbox", cmd)
        self.assertNotIn("--search", cmd)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", cmd)

    def test_build_codex_exec_cmd_exec_read_only_without_bypass(self) -> None:
        cmd = rf.build_codex_exec_cmd(
            repo_dir=self.root,
            codex_flags=["-m", "gpt-5.6-sol", "--sandbox", "workspace-write"],
            codex_config_overrides=[],
            review_md_path=self.root / "out.md",
            prompt="why?",
            dangerously_bypass_approvals_and_sandbox=False,
            approval_policy=None,
            json_output=True,
            sandbox_mode="read-only",
        )
        self.assertIn("--sandbox", cmd)
        self.assertIn("read-only", cmd)
        self.assertEqual(cmd.count("--sandbox"), 1)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", cmd)
        self.assertNotIn("-a", cmd)
        self.assertNotIn("--search", cmd)

    def test_explain_flow_constrains_codex_runtime(self) -> None:
        codex_root = self.root / "codex-home"
        _write_fake_codex_session(codex_root=codex_root)
        _write_completed_session(root=self.root, extra_meta=self._codex_meta())

        with mock.patch.dict(os.environ, {"CODEX_HOME": str(codex_root)}):
            captured = self._patched_run(
                _explain_args(),
                resolved={"provider": "codex", "preset": "codex-cli", "model": "gpt-5.6-sol"},
            )

        self.assertEqual(captured["_rc"], 0)
        self.assertEqual(
            captured["runtime_policy"],
            {"dangerously_bypass_approvals_and_sandbox": False, "approval_policy": None},
        )
        self.assertEqual(captured["sandbox_mode"], "read-only")

    def test_explain_flow_cleans_staged_paths_on_config_failure(self) -> None:
        _write_completed_session(root=self.root)
        cleaned: list[object] = []

        with mock.patch.object(
            rf,
            "cleanup_sensitive_staged_paths",
            side_effect=lambda staged: cleaned.append(staged),
        ):
            with self.assertRaisesRegex(rf.ReviewflowError, "bad llm config"):
                self._patched_run(
                    _explain_args(), resolve_error=True, staged_paths_value={"staged": "path"}
                )
        self.assertEqual(cleaned, [{"staged": "path"}])

    def test_explain_flow_unique_artifact_names(self) -> None:
        _write_completed_session(root=self.root)
        first = self._patched_run(_explain_args())
        second = self._patched_run(_explain_args())
        first_path = Path(str(first["output_path"]))
        second_path = Path(str(second["output_path"]))
        self.assertNotEqual(first_path, second_path)
        self.assertTrue(first_path.name.startswith("explain-"))
        self.assertEqual(len(first_path.name.rsplit(".", 1)[0].split("-")[-1]), 8)

    def test_explain_flow_locks_sidecar_meta_lock_file(self) -> None:
        """The meta.json lock must live on a stable sidecar, never on meta.json
        itself: flushing replaces meta.json with a new filesystem object, so a
        lock on the file would let concurrent processes lock different
        versions of the same path."""
        _write_completed_session(root=self.root)
        captured = self._patched_run(_explain_args(), record_file_lock=True)
        self.assertEqual(captured["_rc"], 0)
        lock_mock = captured["_file_lock_mock"]
        self.assertTrue(lock_mock.called)
        self.assertEqual(
            lock_mock.call_args.args[0], self.root / ".session-1.meta.lock"
        )

    def test_session_progress_merge_flush_locks_sidecar_meta_lock_file(self) -> None:
        meta_path = self.root / "session-1" / "meta.json"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        captured: dict[str, object] = {}

        class _RecLock:
            def __init__(self, lock_path: Path, *, quiet: bool) -> None:
                captured["lock_path"] = lock_path

            def __enter__(self) -> "_RecLock":
                return self

            def __exit__(self, *exc: object) -> bool:
                return False

        with mock.patch.object(rf, "file_lock", _RecLock):
            progress = rf.SessionProgress(meta_path, quiet=True, merge_under_lock=True)
            progress.flush()

        self.assertEqual(captured["lock_path"], self.root / ".session-1.meta.lock")

    def test_explain_flow_removes_fork_on_llm_failure(self) -> None:
        codex_root = self.root / "codex-home"
        base_path = _write_fake_codex_session(codex_root=codex_root)
        base_before = base_path.read_bytes()
        _write_completed_session(root=self.root, extra_meta=self._codex_meta())

        with mock.patch.dict(os.environ, {"CODEX_HOME": str(codex_root)}):
            with self.assertRaisesRegex(rf.ReviewflowError, "llm exploded"):
                self._patched_run(
                    _explain_args(),
                    resolved={"provider": "codex", "preset": "codex-cli", "model": "gpt-5.6-sol"},
                    llm_fail=True,
                )

        rollouts = list(codex_root.glob("sessions/*/*/*/rollout-*.jsonl"))
        self.assertEqual([p for p in rollouts if p != base_path], [])
        self.assertEqual(base_path.read_bytes(), base_before)

    def test_fork_codex_session_io_failure_raises_reviewflow_error(self) -> None:
        codex_root = self.root / "codex-home"
        _write_fake_codex_session(codex_root=codex_root)
        import datetime as _dt

        now = _dt.datetime(2026, 8, 10, 12, 0, 0, tzinfo=_dt.timezone.utc)
        day_dir = codex_root / "sessions" / "2026" / "08" / "10"
        day_dir.mkdir(parents=True, exist_ok=True)
        day_dir.chmod(0o500)
        try:
            with self.assertRaisesRegex(rf.ReviewflowError, "Cannot fork"):
                rf.fork_codex_session(
                    codex_root=codex_root,
                    session_id=BASE_CODEX_SESSION_ID,
                    created_at="2026-08-04T06:30:00+00:00",
                    completed_at="2026-08-04T06:35:31+00:00",
                    now=now,
                )
        finally:
            day_dir.chmod(0o700)

    def test_fork_codex_session_removes_partial_rollout_on_write_failure(self) -> None:
        codex_root = self.root / "codex-home"
        _write_fake_codex_session(codex_root=codex_root)
        import datetime as _dt
        import pathlib

        now = _dt.datetime(2026, 8, 10, 12, 0, 0, tzinfo=_dt.timezone.utc)
        day_dir = codex_root / "sessions" / "2026" / "08" / "10"
        day_dir.mkdir(parents=True, exist_ok=True)
        original_write_text = pathlib.Path.write_text

        def _fail_after_partial_write(path: Path, *args: object, **kwargs: object) -> None:
            # Simulate a disk failure partway through the rollout write: the
            # destination file already exists on disk when the error is raised.
            original_write_text(path, "PARTIAL", encoding="utf-8")
            raise OSError("disk full")

        with mock.patch(
            "pathlib.Path.write_text", autospec=True, side_effect=_fail_after_partial_write
        ):
            with self.assertRaisesRegex(rf.ReviewflowError, "Cannot fork"):
                rf.fork_codex_session(
                    codex_root=codex_root,
                    session_id=BASE_CODEX_SESSION_ID,
                    created_at="2026-08-04T06:30:00+00:00",
                    completed_at="2026-08-04T06:35:31+00:00",
                    now=now,
                )
        self.assertEqual(list(day_dir.glob("rollout-*.jsonl")), [])
