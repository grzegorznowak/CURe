# ruff: noqa: F403, F405
from _reviewflow_unittest_shared import *  # noqa: F401, F403


class LocalMarkdownNormalizationTests(unittest.TestCase):
    def test_normalize_markdown_local_refs_rewrites_local_links_and_paths(self) -> None:
        session_dir = ROOT / ".tmp_test_norm_session"
        repo_file = session_dir / "repo" / "resources" / "js" / "Card.vue"
        work_file = session_dir / "work" / "review_plan.json"
        followup_file = session_dir / "followups" / "followup-1.md"
        text = (
            f"See [resources/js/Card.vue:36]({repo_file}#L36) and `{work_file}#L12`.\n"
            f"Follow-up: {followup_file}\n"
            "External: https://github.com/example-org/example-repo/pull/75#discussion_r1\n"
            "Already plain: resources/js/Card.vue:36\n"
        )

        normalized = rf.normalize_markdown_local_refs(text, session_dir=session_dir)

        self.assertIn("resources/js/Card.vue:36", normalized)
        self.assertIn("`work/review_plan.json:12`", normalized)
        self.assertIn("followups/followup-1.md", normalized)
        self.assertIn("https://github.com/example-org/example-repo/pull/75#discussion_r1", normalized)
        self.assertNotIn(f"[resources/js/Card.vue:36]({repo_file}#L36)", normalized)
        self.assertNotIn(str(repo_file), normalized)
        self.assertNotIn(str(work_file), normalized)

    def test_normalize_markdown_artifact_is_idempotent_for_plain_refs(self) -> None:
        session_dir = ROOT / ".tmp_test_norm_session2"
        md = session_dir / "review.md"
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            original = "Issue at resources/js/Card.vue:36\n"
            md.write_text(original, encoding="utf-8")
            rf.normalize_markdown_artifact(markdown_path=md, session_dir=session_dir)
            self.assertEqual(md.read_text(encoding="utf-8"), original)
        finally:
            shutil.rmtree(session_dir, ignore_errors=True)

    def test_normalize_markdown_artifact_strips_whole_document_markdown_fence(self) -> None:
        session_dir = ROOT / ".tmp_test_norm_session3"
        md = session_dir / "review.md"
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            md.write_text(
                "\n".join(
                    [
                        "```markdown",
                        "**Summary**: ok",
                        "**Decision**: APPROVE",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            rf.normalize_markdown_artifact(markdown_path=md, session_dir=session_dir)
            self.assertEqual(
                md.read_text(encoding="utf-8"),
                "**Summary**: ok\n**Decision**: APPROVE\n",
            )
        finally:
            shutil.rmtree(session_dir, ignore_errors=True)

    def test_normalize_markdown_artifact_rewrites_review_subsection_labels(self) -> None:
        session_dir = ROOT / ".tmp_test_norm_session4"
        md = session_dir / "review.md"
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            md.write_text(
                "\n".join(
                    [
                        "**Summary**: ok",
                        "",
                        "## Business / Product Assessment",
                        "**Verdict**: APPROVE",
                        "**Strengths**:",
                        "- One",
                        "**In Scope Issues**:",
                        "- None.",
                        "**Out of Scope Issues**:",
                        "- None.",
                        "",
                        "## Technical Assessment",
                        "**Verdict**: APPROVE",
                        "**Strengths**:",
                        "- Two",
                        "**In Scope Issues**:",
                        "- None.",
                        "**Out of Scope Issues**:",
                        "- None.",
                        "**Reusability**:",
                        "- None.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            rf.normalize_markdown_artifact(markdown_path=md, session_dir=session_dir)
            normalized = md.read_text(encoding="utf-8")
            self.assertIn("\n### Strengths\n", normalized)
            self.assertIn("\n### In Scope Issues\n", normalized)
            self.assertIn("\n### Out of Scope Issues\n", normalized)
            self.assertIn("\n### Reusability\n", normalized)
            self.assertNotIn("**Strengths**:", normalized)
            self.assertNotIn("**In Scope Issues**:", normalized)
        finally:
            shutil.rmtree(session_dir, ignore_errors=True)

    def test_format_review_artifact_footer_renders_expected_v1_contract(self) -> None:
        footer = cure_output.format_review_artifact_footer(
            review_head_sha="sha1234-example-review-head",
            model="gpt-5.2",
            reasoning_effort="high",
            input_tokens=18_400,
            output_tokens=4_300,
            total_tokens=22_700,
            session_id="20260322-abc123",
            created_at="2026-03-22T00:00:00+00:00",
            completed_at="2026-03-22T00:06:12+00:00",
        )

        self.assertEqual(
            footer,
            "_CURe review · sha sha1234 · model gpt-5.2/high · tok 18k/4k/23k · session 20260322-abc123 · 6m12s · [Project: CURe](https://github.com/grzegorznowak/CURe)_",
        )

    def test_upsert_review_artifact_footer_is_idempotent_and_replaces_existing_footer(self) -> None:
        session_dir = ROOT / ".tmp_test_review_footer_upsert"
        md = session_dir / "review.md"
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            md.write_text(_sectioned_review_markdown(business="APPROVE", technical="APPROVE"), encoding="utf-8")

            cure_output.upsert_review_artifact_footer(
                markdown_path=md,
                footer_line="_CURe review · sha abc1234 · model gpt-5.2/high · tok 1k/2k/3k · session s1 · 5m0s · [Project: CURe](https://github.com/grzegorznowak/CURe)_",
            )
            cure_output.upsert_review_artifact_footer(
                markdown_path=md,
                footer_line="_CURe review · sha def5678 · model gpt-5.2/high · tok 4k/5k/9k · session s1 · 7m0s · [Project: CURe](https://github.com/grzegorznowak/CURe)_",
            )

            rendered = md.read_text(encoding="utf-8")
            self.assertEqual(rendered.count("CURE_REVIEW_FOOTER_START"), 1)
            self.assertIn("sha def5678", rendered)
            self.assertNotIn("sha abc1234", rendered)
        finally:
            shutil.rmtree(session_dir, ignore_errors=True)

    def test_record_llm_usage_aggregates_usage_across_runs(self) -> None:
        llm_meta: dict[str, object] = {}

        first = rf.record_llm_usage(
            llm_meta,
            {"usage": {"input_tokens": 1000, "output_tokens": 250, "total_tokens": 1250}},
        )
        second = rf.record_llm_usage(
            llm_meta,
            {"usage": {"input_tokens": 500, "output_tokens": 125}},
        )

        self.assertEqual(first, {"input_tokens": 1000, "output_tokens": 250, "total_tokens": 1250})
        self.assertEqual(second, {"input_tokens": 1500, "output_tokens": 375, "total_tokens": 1875})
        self.assertEqual(llm_meta["usage"], {"input_tokens": 1500, "output_tokens": 375, "total_tokens": 1875})

    def test_extract_codex_usage_from_event_slice_sums_turn_usage(self) -> None:
        root = ROOT / ".tmp_test_codex_usage_slice"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            events_path = root / "codex.events.jsonl"
            payloads = [
                {"type": "turn.started"},
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 1200, "output_tokens": 300, "total_tokens": 1500},
                },
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 800, "output_tokens": 200, "total_tokens": 1000},
                },
            ]
            events_path.write_text("\n".join(json.dumps(payload) for payload in payloads) + "\n", encoding="utf-8")

            usage = cure_llm._extract_codex_usage_from_event_slice(
                events_path=events_path,
                start_offset=0,
                end_offset=events_path.stat().st_size,
            )

            self.assertEqual(
                usage,
                {"input_tokens": 2000, "output_tokens": 500, "total_tokens": 2500},
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)


class CodexResumeTests(unittest.TestCase):
    def test_build_codex_resume_command_includes_env_flags_and_session_id(self) -> None:
        repo_dir = ROOT / ".tmp_test_resume_repo" / "repo"
        session_dir = repo_dir.parent
        cmd = rf.build_codex_resume_command(
            repo_dir=repo_dir,
            session_id="019cd0ef-73cd-79c2-a4b9-dbb34c9a2eed",
            env={
                "GH_CONFIG_DIR": str(session_dir / "work" / "gh_config"),
                "CURE_WORK_DIR": str(session_dir / "work"),
            },
            codex_flags=["-m", "gpt-5.2", "--search", "--sandbox", "danger-full-access"],
            codex_config_overrides=['mcp_servers.chunkhound.command="chunkhound"'],
            add_dirs=[session_dir],
        )

        self.assertIn(f"cd {repo_dir}", cmd)
        self.assertIn("env GH_CONFIG_DIR=", cmd)
        self.assertIn("CURE_WORK_DIR=", cmd)
        self.assertIn("codex resume", cmd)
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", cmd)
        self.assertIn("--add-dir /tmp", cmd)
        self.assertNotIn(f"--add-dir {session_dir}", cmd)
        self.assertIn("--search", cmd)
        self.assertIn("danger-full-access", cmd)
        self.assertIn('mcp_servers.chunkhound.command="chunkhound"', cmd)
        self.assertIn("019cd0ef-73cd-79c2-a4b9-dbb34c9a2eed", cmd)

    def test_build_codex_resume_command_does_not_duplicate_approval_flag(self) -> None:
        cmd = rf.build_codex_resume_command(
            repo_dir=ROOT / ".tmp_test_resume_repo" / "repo",
            session_id="session-123",
            env={},
            codex_flags=["--sandbox", "workspace-write", "-a", "never"],
            codex_config_overrides=[],
            approval_policy="never",
            dangerously_bypass_approvals_and_sandbox=False,
        )
        self.assertEqual(cmd.count(" -a "), 1)

    def test_find_codex_resume_info_picks_newest_matching_cwd(self) -> None:
        codex_root = ROOT / ".tmp_test_codex_resume_root"
        repo_dir = ROOT / ".tmp_test_codex_resume_repo" / "repo"
        day_dir = codex_root / "sessions" / "2026" / "03" / "09"
        try:
            day_dir.mkdir(parents=True, exist_ok=True)
            repo_dir.mkdir(parents=True, exist_ok=True)

            def write_session(name: str, payload: dict[str, str]) -> None:
                (day_dir / name).write_text(
                    json.dumps({"type": "session_meta", "payload": payload}) + "\n",
                    encoding="utf-8",
                )

            write_session(
                "rollout-2026-03-09T04-59-00-old.jsonl",
                {
                    "id": "old",
                    "timestamp": "2026-03-09T04:59:00+00:00",
                    "cwd": str(repo_dir),
                    "originator": "codex_exec",
                },
            )
            write_session(
                "rollout-2026-03-09T05-01-00-other.jsonl",
                {
                    "id": "other",
                    "timestamp": "2026-03-09T05:01:00+00:00",
                    "cwd": str(ROOT / ".tmp_other_repo"),
                    "originator": "codex_exec",
                },
            )
            write_session(
                "rollout-2026-03-09T05-02-00-newest.jsonl",
                {
                    "id": "newest",
                    "timestamp": "2026-03-09T05:02:00+00:00",
                    "cwd": str(repo_dir),
                    "originator": "codex_exec",
                },
            )

            info = rf.find_codex_resume_info(
                repo_dir=repo_dir,
                started_at=datetime(2026, 3, 9, 5, 0, 30, tzinfo=timezone.utc),
                env={"CURE_WORK_DIR": str(repo_dir.parent / "work")},
                codex_flags=[],
                codex_config_overrides=None,
                add_dirs=[repo_dir.parent],
                codex_root=codex_root,
            )

            self.assertIsNotNone(info)
            assert info is not None
            self.assertEqual(info.session_id, "newest")
            self.assertEqual(info.cwd, repo_dir.resolve())
            self.assertIn("codex resume", info.command)
            self.assertIn("newest", info.command)
        finally:
            shutil.rmtree(codex_root, ignore_errors=True)
            shutil.rmtree(repo_dir.parent, ignore_errors=True)

    def test_find_codex_resume_info_accepts_interactive_codex_originator(self) -> None:
        codex_root = ROOT / ".tmp_test_codex_resume_cli_root"
        repo_dir = ROOT / ".tmp_test_codex_resume_cli_repo" / "repo"
        day_dir = codex_root / "sessions" / "2026" / "03" / "09"
        try:
            day_dir.mkdir(parents=True, exist_ok=True)
            repo_dir.mkdir(parents=True, exist_ok=True)
            (day_dir / "rollout-2026-03-09T16-32-08-cli.jsonl").write_text(
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {
                            "id": "cli-session",
                            "timestamp": "2026-03-09T16:32:08+00:00",
                            "cwd": str(repo_dir),
                            "originator": "codex_cli_rs",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            info = rf.find_codex_resume_info(
                repo_dir=repo_dir,
                started_at=datetime(2026, 3, 9, 16, 31, 0, tzinfo=timezone.utc),
                env={"CURE_WORK_DIR": str(repo_dir.parent / "work")},
                codex_flags=["-m", "gpt-5.4"],
                codex_config_overrides=None,
                add_dirs=None,
                codex_root=codex_root,
            )

            self.assertIsNotNone(info)
            assert info is not None
            self.assertEqual(info.session_id, "cli-session")
            self.assertIn("codex resume", info.command)
            self.assertIn("cli-session", info.command)
        finally:
            shutil.rmtree(codex_root, ignore_errors=True)
            shutil.rmtree(repo_dir.parent, ignore_errors=True)

    def test_find_codex_resume_info_ignores_newer_subagent_session(self) -> None:
        codex_root = ROOT / ".tmp_test_codex_resume_subagent_root"
        repo_dir = ROOT / ".tmp_test_codex_resume_subagent_repo" / "repo"
        day_dir = codex_root / "sessions" / "2026" / "03" / "10"
        try:
            day_dir.mkdir(parents=True, exist_ok=True)
            repo_dir.mkdir(parents=True, exist_ok=True)
            (day_dir / "rollout-parent.jsonl").write_text(
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {
                            "id": "parent-session",
                            "timestamp": "2026-03-10T10:05:32+00:00",
                            "cwd": str(repo_dir),
                            "originator": "codex_exec",
                            "source": "exec",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (day_dir / "rollout-child.jsonl").write_text(
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {
                            "id": "child-session",
                            "forked_from_id": "parent-session",
                            "timestamp": "2026-03-10T10:18:32+00:00",
                            "cwd": str(repo_dir),
                            "originator": "codex_exec",
                            "source": {"subagent": {"thread_spawn": {"parent_thread_id": "parent-session"}}},
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            info = rf.find_codex_resume_info(
                repo_dir=repo_dir,
                started_at=datetime(2026, 3, 10, 10, 0, 0, tzinfo=timezone.utc),
                env={"CURE_WORK_DIR": str(repo_dir.parent / "work")},
                codex_flags=[],
                codex_config_overrides=None,
                add_dirs=None,
                codex_root=codex_root,
            )

            self.assertIsNotNone(info)
            assert info is not None
            self.assertEqual(info.session_id, "parent-session")
            self.assertIn("parent-session", info.command)
            self.assertNotIn("child-session", info.command)
        finally:
            shutil.rmtree(codex_root, ignore_errors=True)
            shutil.rmtree(repo_dir.parent, ignore_errors=True)


class CodexResumeOutputTests(unittest.TestCase):
    class _FakeStderr:
        def __init__(self) -> None:
            self.parts: list[str] = []

        def write(self, s: str) -> int:
            self.parts.append(str(s))
            return len(s)

        def flush(self) -> None:
            return None

        def getvalue(self) -> str:
            return "".join(self.parts)

    def test_maybe_print_codex_resume_command_is_silent(self) -> None:
        err = self._FakeStderr()
        rf.maybe_print_codex_resume_command(
            stderr=err,
            command="cd /tmp/repo && codex resume 019cd0ef-73cd-79c2-a4b9-dbb34c9a2eed",
        )
        self.assertEqual(err.getvalue(), "")


class EnsureBaseCacheTests(unittest.TestCase):
    def test_ensure_base_cache_reprime_when_review_config_fingerprint_changes(self) -> None:
        tmp_cache = ROOT / ".tmp_test_cache_fp_mismatch"
        tmp_sandbox = ROOT / ".tmp_test_sandbox_fp_mismatch"
        try:
            tmp_cache.mkdir(parents=True, exist_ok=True)
            tmp_sandbox.mkdir(parents=True, exist_ok=True)

            paths = rf.ReviewflowPaths(
                sandbox_root=tmp_sandbox,
                cache_root=tmp_cache,
                review_chunkhound_config=ROOT / ".tmp_unused_review_cfg.json",
                main_chunkhound_config=ROOT / ".tmp_unused_main_cfg.json",
            )
            pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=1)
            base_ref = "main"

            base_root = rf.base_dir(paths, pr.host, pr.owner, pr.repo, base_ref)
            base_root.mkdir(parents=True, exist_ok=True)
            meta_path = base_root / "meta.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "indexed_at": "2026-03-05T00:00:00+00:00",
                        "config_fingerprint": "stale",
                    }
                ),
                encoding="utf-8",
            )

            called: dict[str, object] = {}

            def fake_cache_prime(**kwargs):  # type: ignore[no-untyped-def]
                called["kwargs"] = kwargs
                return {"primed": True}

            old_cache_prime = rf.cache_prime
            rf.cache_prime = fake_cache_prime  # type: ignore[assignment]
            try:
                with mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(
                            base_config_path=ROOT / ".tmp_chunkhound_base.json"
                        ),
                        {"chunkhound": {"base_config_path": "/tmp/base.json"}},
                        {"indexing": {"exclude": []}},
                    ),
                ):
                    out = rf.ensure_base_cache(
                        paths=paths,
                        pr=pr,
                        base_ref=base_ref,
                        ttl_hours=24,
                        refresh=False,
                        quiet=True,
                        no_stream=True,
                    )
            finally:
                rf.cache_prime = old_cache_prime  # type: ignore[assignment]

            self.assertEqual(out, {"primed": True})
            self.assertIn("kwargs", called)
        finally:
            shutil.rmtree(tmp_sandbox, ignore_errors=True)
            shutil.rmtree(tmp_cache, ignore_errors=True)


class BaselineSelectionTests(unittest.TestCase):
    def test_resolve_pr_review_baseline_selection_prefers_default_branch_within_threshold(self) -> None:
        pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=7)
        pr_meta = {
            "base": {
                "ref": "release/1.2",
                "repo": {"default_branch": "main"},
            }
        }
        compare_payload = {
            "ahead_by": 12,
            "behind_by": 4,
            "files": [
                {"filename": "a.py", "additions": 10, "deletions": 3},
                {"filename": "b.py", "additions": 5, "deletions": 2},
            ],
        }

        with mock.patch.object(rf, "gh_api_json", return_value=compare_payload) as gh_api_json:
            selection = rf.resolve_pr_review_baseline_selection(pr=pr, pr_meta=pr_meta)

        self.assertEqual(selection["base_ref"], "release/1.2")
        self.assertEqual(selection["repo_default_ref"], "main")
        self.assertEqual(selection["selected_baseline_ref"], "main")
        self.assertEqual(selection["selection_reason"], "default_within_threshold")
        self.assertEqual(
            selection["divergence"],
            {
                "source": "github_compare",
                "files_truncated": False,
                "ahead_by": 12,
                "behind_by": 4,
                "changed_files": 2,
                "additions": 15,
                "deletions": 5,
                "changed_lines": 20,
            },
        )
        gh_api_json.assert_called_once()

    def test_resolve_pr_review_baseline_selection_uses_target_branch_when_commit_distance_exceeded(self) -> None:
        pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=7)
        pr_meta = {
            "base": {
                "ref": "release/1.2",
                "repo": {"default_branch": "main"},
            }
        }
        compare_payload = {
            "ahead_by": 251,
            "behind_by": 1,
            "files": [{"filename": "a.py", "additions": 1, "deletions": 1}],
        }

        with mock.patch.object(rf, "gh_api_json", return_value=compare_payload):
            selection = rf.resolve_pr_review_baseline_selection(pr=pr, pr_meta=pr_meta)

        self.assertEqual(selection["selected_baseline_ref"], "release/1.2")
        self.assertEqual(selection["selection_reason"], "target_diverged")

    def test_resolve_pr_review_baseline_selection_uses_target_branch_when_diff_volume_exceeded(self) -> None:
        pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=7)
        pr_meta = {
            "base": {
                "ref": "release/1.2",
                "repo": {"default_branch": "main"},
            }
        }
        compare_payload = {
            "ahead_by": 5,
            "behind_by": 5,
            "files": [{"filename": "huge.patch", "additions": 75001, "deletions": 25001}],
        }

        with mock.patch.object(rf, "gh_api_json", return_value=compare_payload):
            selection = rf.resolve_pr_review_baseline_selection(pr=pr, pr_meta=pr_meta)

        self.assertEqual(selection["selected_baseline_ref"], "release/1.2")
        self.assertEqual(selection["selection_reason"], "target_diverged")
        self.assertEqual(selection["divergence"]["changed_lines"], 100002)

    def test_resolve_pr_review_baseline_selection_falls_back_when_default_branch_missing(self) -> None:
        pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=7)
        pr_meta = {"base": {"ref": "release/1.2", "repo": {}}}

        with mock.patch.object(rf, "gh_api_json", side_effect=AssertionError("compare should not run")):
            selection = rf.resolve_pr_review_baseline_selection(pr=pr, pr_meta=pr_meta)

        self.assertEqual(selection["selected_baseline_ref"], "release/1.2")
        self.assertEqual(selection["selection_reason"], "default_ref_unavailable")
        self.assertIsNone(selection["repo_default_ref"])
        self.assertEqual(selection["divergence"]["source"], "default_ref_unavailable")
        self.assertIsNone(selection["divergence"]["files_truncated"])

    def test_resolve_pr_review_baseline_selection_treats_compare_file_cap_as_diverged(self) -> None:
        pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=7)
        pr_meta = {
            "base": {
                "ref": "release/1.2",
                "repo": {"default_branch": "main"},
            }
        }
        compare_payload = {
            "ahead_by": 5,
            "behind_by": 5,
            "files": [{"filename": f"f{i}.py", "additions": 1, "deletions": 1} for i in range(300)],
        }

        with mock.patch.object(rf, "gh_api_json", return_value=compare_payload):
            selection = rf.resolve_pr_review_baseline_selection(pr=pr, pr_meta=pr_meta)

        self.assertEqual(selection["selected_baseline_ref"], "release/1.2")
        self.assertEqual(selection["selection_reason"], "target_diverged")
        self.assertEqual(selection["divergence"]["source"], "github_compare_truncated_files")
        self.assertTrue(selection["divergence"]["files_truncated"])
        self.assertEqual(selection["divergence"]["changed_files"], 300)
        self.assertEqual(selection["divergence"]["changed_lines"], 600)

    def test_pr_flow_uses_selected_baseline_and_records_metadata(self) -> None:
        root = ROOT / ".tmp_test_pr_selected_baseline"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            sandbox_root = root / "sandboxes"
            cache_root = root / "cache"
            sandbox_root.mkdir(parents=True, exist_ok=True)
            cache_root.mkdir(parents=True, exist_ok=True)
            seed = root / "seed"
            seed.mkdir(parents=True, exist_ok=True)
            base_db = root / "base.chunkhound.db"
            base_db.write_text("db", encoding="utf-8")
            base_cfg = root / "chunkhound-base.json"
            base_cfg.write_text("{}", encoding="utf-8")
            config_path = root / "reviewflow.toml"
            config_path.write_text(
                "\n".join(
                    [
                        "[chunkhound]",
                        f'base_config_path = "{base_cfg}"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            args = rf.build_parser().parse_args(
                [
                    "pr",
                    "https://github.com/acme/repo/pull/14",
                    "--if-reviewed",
                    "new",
                    "--no-review",
                    "--ui",
                    "off",
                    "--quiet",
                    "--no-stream",
                ]
            )
            paths = rf.ReviewflowPaths(sandbox_root=sandbox_root, cache_root=cache_root)

            class _Result:
                def __init__(self, stdout: str = "") -> None:
                    self.stdout = stdout
                    self.stderr = ""
                    self.duration_seconds = 0.0

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> _Result:
                if cmd[:2] == ["git", "clone"]:
                    Path(str(cmd[-1])).mkdir(parents=True, exist_ok=True)
                    return _Result()
                if cmd[:5] == ["git", "-C", str(seed), "remote", "get-url"]:
                    return _Result("https://github.com/acme/repo.git\n")
                if cmd[:4] == ["git", "-C", str(seed), "rev-parse"]:
                    return _Result("true\n")
                if cmd[:4] == ["git", "-C", str(Path(str(cmd[2]))), "rev-parse"]:
                    return _Result("deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n")
                if cmd[:3] == ["gh", "pr", "checkout"]:
                    return _Result()
                if cmd and cmd[0] in {"git", "rsync", "chunkhound"}:
                    return _Result()
                raise AssertionError(f"unexpected command: {cmd}")

            def fake_materialize_chunkhound_env_config(
                *,
                resolved_config: dict[str, object],
                output_config_path: Path,
                database_provider: str,
                database_path: Path,
            ) -> None:
                output_config_path.parent.mkdir(parents=True, exist_ok=True)
                output_config_path.write_text("{}", encoding="utf-8")
                database_path.parent.mkdir(parents=True, exist_ok=True)

            def fake_copy_duckdb_files(src: Path, dest: Path) -> None:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

            def fake_write_pr_context_file(*, work_dir: Path, pr: rf.PullRequestRef, pr_meta: dict[str, object]) -> Path:
                context_path = work_dir / "pr-context.md"
                context_path.write_text("context", encoding="utf-8")
                return context_path

            stdout = StringIO()
            with contextlib.ExitStack() as stack:
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "gh_api_json",
                        side_effect=[
                            {
                                "base": {
                                    "ref": "release/1.2",
                                    "repo": {"default_branch": "main"},
                                },
                                "head": {"sha": "1111111111111111111111111111111111111111"},
                                "title": "Baseline selection PR",
                            },
                            {
                                "ahead_by": 12,
                                "behind_by": 4,
                                "files": [
                                    {"filename": "a.py", "additions": 10, "deletions": 3},
                                    {"filename": "b.py", "additions": 5, "deletions": 2},
                                ],
                            },
                        ],
                    )
                )
                stack.enter_context(mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[]))
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_chunkhound_runtime_config",
                        return_value=(
                            rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                            {"chunkhound": {"base_config_path": str(base_cfg)}},
                            {"indexing": {"exclude": []}},
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "materialize_chunkhound_env_config",
                        side_effect=fake_materialize_chunkhound_env_config,
                    )
                )
                stack.enter_context(
                    mock.patch.object(rf, "write_pr_context_file", side_effect=fake_write_pr_context_file)
                )
                ensure_base_cache = stack.enter_context(
                    mock.patch.object(rf, "ensure_base_cache", return_value={"db_path": str(base_db)})
                )
                stack.enter_context(mock.patch.object(rf, "seed_dir", return_value=seed))
                stack.enter_context(mock.patch.object(rf, "ensure_clean_git_worktree"))
                stack.enter_context(mock.patch.object(rf, "same_device", return_value=True))
                stack.enter_context(mock.patch.object(rf, "copy_duckdb_files", side_effect=fake_copy_duckdb_files))
                stack.enter_context(mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd))
                stack.enter_context(
                    mock.patch.object(
                        rf.ReviewflowOutput,
                        "run_logged_cmd",
                        autospec=True,
                        side_effect=lambda output, cmd, **kwargs: fake_run_cmd(cmd, **kwargs),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_review_intelligence_config",
                        side_effect=AssertionError("review setup should be skipped"),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_reviewflow_multipass_defaults",
                        side_effect=AssertionError("multipass defaults should be skipped"),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "resolve_prompt_profile",
                        side_effect=AssertionError("prompt selection should be skipped"),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "require_builtin_review_intelligence",
                        side_effect=AssertionError("review validation should be skipped"),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "resolve_llm_config_from_args",
                        side_effect=AssertionError("llm resolution should be skipped"),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "prepare_review_agent_runtime",
                        side_effect=AssertionError("runtime setup should be skipped"),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "run_llm_exec",
                        side_effect=AssertionError("review execution should be skipped"),
                    )
                )
                stack.enter_context(mock.patch("sys.stdout", stdout))
                rc = rf.pr_flow(
                    args,
                    paths=paths,
                    config_path=config_path,
                    codex_base_config_path=root / "codex.toml",
                )

            self.assertEqual(rc, 0)
            self.assertEqual(ensure_base_cache.call_args.kwargs["base_ref"], "main")
            session_dir = Path(stdout.getvalue().strip())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["base_ref"], "release/1.2")
            self.assertEqual(
                meta["baseline_selection"],
                {
                    "base_ref": "release/1.2",
                    "repo_default_ref": "main",
                    "selected_baseline_ref": "main",
                    "selection_reason": "default_within_threshold",
                    "divergence": {
                        "source": "github_compare",
                        "files_truncated": False,
                        "ahead_by": 12,
                        "behind_by": 4,
                        "changed_files": 2,
                        "additions": 15,
                        "deletions": 5,
                        "changed_lines": 20,
                    },
                },
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_resume_flow_restores_missing_session_db_from_selected_baseline(self) -> None:
        root = ROOT / ".tmp_test_resume_selected_baseline_restore"
        cfg = root / "reviewflow.toml"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            base_cfg = root / "chunkhound-base.json"
            base_cfg.write_text("{}", encoding="utf-8")
            cfg.write_text(
                f"[chunkhound]\nbase_config_path = {json.dumps(str(base_cfg))}\n",
                encoding="utf-8",
            )
            session_dir = root / "session-1"
            repo_dir = session_dir / "repo"
            work_dir = session_dir / "work"
            repo_dir.mkdir(parents=True, exist_ok=True)
            work_dir.mkdir(parents=True, exist_ok=True)
            review_md = session_dir / "review.md"
            review_md.write_text("review", encoding="utf-8")
            base_db = root / "shared-base.chunkhound.db"
            base_db.write_text("db", encoding="utf-8")
            meta = {
                "session_id": "session-1",
                "status": "error",
                "created_at": "2026-03-10T00:00:00+00:00",
                "failed_at": "2026-03-10T00:05:00+00:00",
                "pr_url": "https://github.com/acme/repo/pull/9",
                "host": "github.com",
                "owner": "acme",
                "repo": "repo",
                "number": 9,
                "base_ref": "release/1.2",
                "base_ref_for_review": "cure_base__release_1_2",
                "notes": {"no_index": False},
                "llm": {"provider": "openai", "capabilities": {"supports_resume": True}},
                "baseline_selection": {
                    "base_ref": "release/1.2",
                    "repo_default_ref": "main",
                    "selected_baseline_ref": "main",
                    "selection_reason": "default_within_threshold",
                    "divergence": {
                        "source": "github_compare",
                        "files_truncated": False,
                        "ahead_by": 12,
                        "behind_by": 4,
                        "changed_files": 2,
                        "additions": 15,
                        "deletions": 5,
                        "changed_lines": 20,
                    },
                },
                "paths": {
                    "session_dir": str(session_dir),
                    "repo_dir": str(repo_dir),
                    "work_dir": str(work_dir),
                    "chunkhound_cwd": str(work_dir / "chunkhound"),
                    "chunkhound_db": str(work_dir / "chunkhound" / ".chunkhound.db"),
                    "chunkhound_config": str(work_dir / "chunkhound" / "chunkhound.json"),
                    "review_md": str(review_md),
                },
            }
            (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

            args = argparse.Namespace(
                session_id="session-1",
                from_phase="plan",
                no_index=False,
                codex_model=None,
                codex_effort=None,
                codex_plan_effort=None,
                quiet=True,
                no_stream=True,
                ui="off",
                verbosity="normal",
            )
            paths = rf.ReviewflowPaths(sandbox_root=root, cache_root=root / "cache")

            with (
                mock.patch.object(rf, "ensure_review_config"),
                mock.patch.object(rf, "ensure_base_cache", return_value={"db_path": str(base_db)}) as ensure_base_cache,
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    side_effect=RuntimeError("resume stopped after restore"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "resume stopped after restore"):
                    rf.resume_flow(args, paths=paths, config_path=cfg, codex_base_config_path=cfg)

            ensure_base_cache.assert_called_once()
            self.assertEqual(ensure_base_cache.call_args.kwargs["base_ref"], "main")
            restored_db = work_dir / "chunkhound" / ".chunkhound.db"
            self.assertTrue(restored_db.is_file())
            self.assertEqual(restored_db.read_text(encoding="utf-8"), "db")
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_followup_flow_restores_missing_session_db_from_selected_baseline(self) -> None:
        root = ROOT / ".tmp_test_followup_selected_baseline_restore"
        cfg = root / "reviewflow.toml"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            base_cfg = root / "chunkhound-base.json"
            base_cfg.write_text("{}", encoding="utf-8")
            cfg.write_text(
                f"[chunkhound]\nbase_config_path = {json.dumps(str(base_cfg))}\n",
                encoding="utf-8",
            )
            session_dir = root / "session-1"
            repo_dir = session_dir / "repo"
            work_dir = session_dir / "work"
            repo_dir.mkdir(parents=True, exist_ok=True)
            work_dir.mkdir(parents=True, exist_ok=True)
            review_md = session_dir / "review.md"
            review_md.write_text("review", encoding="utf-8")
            base_db = root / "shared-base.chunkhound.db"
            base_db.write_text("db", encoding="utf-8")
            meta = {
                "session_id": "session-1",
                "status": "done",
                "created_at": "2026-03-10T00:00:00+00:00",
                "completed_at": "2026-03-10T00:05:00+00:00",
                "pr_url": "https://github.com/acme/repo/pull/9",
                "host": "github.com",
                "owner": "acme",
                "repo": "repo",
                "number": 9,
                "base_ref": "release/1.2",
                "base_ref_for_review": "cure_base__release_1_2",
                "baseline_selection": {
                    "base_ref": "release/1.2",
                    "repo_default_ref": "main",
                    "selected_baseline_ref": "main",
                    "selection_reason": "default_within_threshold",
                    "divergence": {
                        "source": "github_compare",
                        "files_truncated": False,
                        "ahead_by": 12,
                        "behind_by": 4,
                        "changed_files": 2,
                        "additions": 15,
                        "deletions": 5,
                        "changed_lines": 20,
                    },
                },
                "paths": {
                    "session_dir": str(session_dir),
                    "repo_dir": str(repo_dir),
                    "work_dir": str(work_dir),
                    "chunkhound_cwd": str(work_dir / "chunkhound"),
                    "chunkhound_db": str(work_dir / "chunkhound" / ".chunkhound.db"),
                    "chunkhound_config": str(work_dir / "chunkhound" / "chunkhound.json"),
                    "review_md": str(review_md),
                },
            }
            (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

            args = argparse.Namespace(
                session_id="session-1",
                no_update=True,
                codex_model=None,
                codex_effort=None,
                codex_plan_effort=None,
                quiet=True,
                no_stream=True,
                ui="off",
                verbosity="normal",
            )
            paths = rf.ReviewflowPaths(sandbox_root=root, cache_root=root / "cache")

            with (
                mock.patch.object(rf, "ensure_review_config"),
                mock.patch.object(rf, "ensure_base_cache", return_value={"db_path": str(base_db)}) as ensure_base_cache,
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    side_effect=RuntimeError("followup stopped after restore"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "followup stopped after restore"):
                    rf.followup_flow(args, paths=paths, config_path=cfg, codex_base_config_path=cfg)

            ensure_base_cache.assert_called_once()
            self.assertEqual(ensure_base_cache.call_args.kwargs["base_ref"], "main")
            restored_db = work_dir / "chunkhound" / ".chunkhound.db"
            self.assertTrue(restored_db.is_file())
            self.assertEqual(restored_db.read_text(encoding="utf-8"), "db")
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_followup_flow_prefers_legacy_repo_local_chunkhound_db_before_baseline_restore(self) -> None:
        root = ROOT / ".tmp_test_followup_legacy_repo_db_precedence"
        cfg = root / "reviewflow.toml"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            base_cfg = root / "chunkhound-base.json"
            base_cfg.write_text("{}", encoding="utf-8")
            cfg.write_text(
                f"[chunkhound]\nbase_config_path = {json.dumps(str(base_cfg))}\n",
                encoding="utf-8",
            )
            session_dir = root / "session-1"
            repo_dir = session_dir / "repo"
            work_dir = session_dir / "work"
            repo_dir.mkdir(parents=True, exist_ok=True)
            work_dir.mkdir(parents=True, exist_ok=True)
            review_md = session_dir / "review.md"
            review_md.write_text("review", encoding="utf-8")
            legacy_db = repo_dir / ".chunkhound.db"
            legacy_db.write_text("legacy-db", encoding="utf-8")
            meta = {
                "session_id": "session-1",
                "status": "done",
                "created_at": "2026-03-10T00:00:00+00:00",
                "completed_at": "2026-03-10T00:05:00+00:00",
                "pr_url": "https://github.com/acme/repo/pull/9",
                "host": "github.com",
                "owner": "acme",
                "repo": "repo",
                "number": 9,
                "base_ref": "release/1.2",
                "base_ref_for_review": "cure_base__release_1_2",
                "baseline_selection": {
                    "base_ref": "release/1.2",
                    "repo_default_ref": "main",
                    "selected_baseline_ref": "main",
                    "selection_reason": "default_within_threshold",
                    "divergence": {
                        "source": "github_compare",
                        "files_truncated": False,
                        "ahead_by": 12,
                        "behind_by": 4,
                        "changed_files": 2,
                        "additions": 15,
                        "deletions": 5,
                        "changed_lines": 20,
                    },
                },
                "paths": {
                    "session_dir": str(session_dir),
                    "repo_dir": str(repo_dir),
                    "work_dir": str(work_dir),
                    "chunkhound_cwd": str(work_dir / "chunkhound"),
                    "chunkhound_db": str(work_dir / "chunkhound" / ".chunkhound.db"),
                    "chunkhound_config": str(work_dir / "chunkhound" / "chunkhound.json"),
                    "review_md": str(review_md),
                },
            }
            (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

            args = argparse.Namespace(
                session_id="session-1",
                no_update=True,
                codex_model=None,
                codex_effort=None,
                codex_plan_effort=None,
                quiet=True,
                no_stream=True,
                ui="off",
                verbosity="normal",
            )
            paths = rf.ReviewflowPaths(sandbox_root=root, cache_root=root / "cache")
            captured: dict[str, Path] = {}

            def fake_materialize_chunkhound_env_config(
                *,
                resolved_config: dict[str, object],
                output_config_path: Path,
                database_provider: str,
                database_path: Path,
            ) -> None:
                captured["database_path"] = database_path
                raise RuntimeError("followup stopped after chunkhound path selection")

            with (
                mock.patch.object(rf, "ensure_review_config"),
                mock.patch.object(
                    rf,
                    "ensure_base_cache",
                    side_effect=AssertionError("baseline restore should not run"),
                ),
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                        {"chunkhound": {"base_config_path": str(base_cfg)}},
                        {},
                    ),
                ),
                mock.patch.object(
                    rf,
                    "materialize_chunkhound_env_config",
                    side_effect=fake_materialize_chunkhound_env_config,
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "followup stopped after chunkhound path selection"):
                    rf.followup_flow(args, paths=paths, config_path=cfg, codex_base_config_path=cfg)

            self.assertEqual(captured["database_path"], legacy_db.resolve())
            self.assertEqual(legacy_db.read_text(encoding="utf-8"), "legacy-db")
            self.assertFalse((work_dir / "chunkhound" / ".chunkhound.db").exists())
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)


class ExactRepoLocalDuckdbReuseTests(unittest.TestCase):
    def _runtime_seed_config(self) -> dict[str, object]:
        return {
            "indexing": {
                "exclude": ["**/.git/**"],
                "include": ["**/*.py"],
            },
            "research": {"algorithm": "hybrid"},
        }

    def _write_repo_local_chunkhound_state(
        self,
        *,
        repo_root: Path,
        resolved_runtime_config: dict[str, object],
        db_rel: str = ".chunkhound",
        config_name: str = ".chunkhound.json",
        mutate_config: Any | None = None,
    ) -> tuple[Path, Path]:
        db_path = repo_root / db_rel
        db_path.mkdir(parents=True, exist_ok=True)
        (db_path / "chunks.db").write_text("db", encoding="utf-8")
        config = json.loads(json.dumps(resolved_runtime_config))
        if mutate_config is not None:
            mutate_config(config)
        config["database"] = {"provider": "duckdb", "path": db_rel}
        config_path = repo_root / config_name
        config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return config_path, db_path

    def test_discover_repo_local_chunkhound_config_prefers_chunkhound_json(self) -> None:
        root = ROOT / ".tmp_test_repo_local_chunkhound_discovery_precedence"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_root = root / "repo"
            invocation_cwd = repo_root / "src"
            invocation_cwd.mkdir(parents=True, exist_ok=True)
            resolved_runtime_config = self._runtime_seed_config()
            selected_config_path, selected_db_path = self._write_repo_local_chunkhound_state(
                repo_root=repo_root,
                resolved_runtime_config=resolved_runtime_config,
                db_rel=".chunkhound-primary",
                config_name="chunkhound.json",
            )
            self._write_repo_local_chunkhound_state(
                repo_root=repo_root,
                resolved_runtime_config=resolved_runtime_config,
                db_rel=".chunkhound-fallback",
                config_name=".chunkhound.json",
            )

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                if cmd == ["git", "-C", str(invocation_cwd), "rev-parse", "--show-toplevel"]:
                    return mock.Mock(stdout=f"{repo_root}\n", stderr="", duration_seconds=0.0)
                raise AssertionError(f"unexpected command: {cmd}")

            with mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd):
                candidate = cure_flows.discover_repo_local_chunkhound_config(
                    invocation_cwd=invocation_cwd,
                    resolved_runtime_config=resolved_runtime_config,
                )

            self.assertEqual(
                candidate,
                {
                    "candidate_state": "candidate",
                    "reason": None,
                    "repo_root": str(repo_root.resolve()),
                    "config_path": str(selected_config_path.resolve()),
                    "config_file_name": "chunkhound.json",
                    "db_provider": "duckdb",
                    "db_path": str(selected_db_path.resolve()),
                    "repo_identity": None,
                    "expected_repo_identity": None,
                    "target_match_state": "not_requested",
                    "runtime_match_state": "compatible",
                },
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_discover_repo_local_chunkhound_config_falls_back_to_dot_chunkhound_json(self) -> None:
        root = ROOT / ".tmp_test_repo_local_chunkhound_discovery_fallback"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_root = root / "repo"
            invocation_cwd = repo_root / "src"
            invocation_cwd.mkdir(parents=True, exist_ok=True)
            resolved_runtime_config = self._runtime_seed_config()
            config_path, db_path = self._write_repo_local_chunkhound_state(
                repo_root=repo_root,
                resolved_runtime_config=resolved_runtime_config,
                config_name=".chunkhound.json",
            )

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                if cmd == ["git", "-C", str(invocation_cwd), "rev-parse", "--show-toplevel"]:
                    return mock.Mock(stdout=f"{repo_root}\n", stderr="", duration_seconds=0.0)
                raise AssertionError(f"unexpected command: {cmd}")

            with mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd):
                candidate = cure_flows.discover_repo_local_chunkhound_config(
                    invocation_cwd=invocation_cwd,
                    resolved_runtime_config=resolved_runtime_config,
                )

            self.assertEqual(candidate["candidate_state"], "candidate")
            self.assertEqual(candidate["config_path"], str(config_path.resolve()))
            self.assertEqual(candidate["config_file_name"], ".chunkhound.json")
            self.assertEqual(candidate["db_path"], str(db_path.resolve()))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_discover_repo_local_chunkhound_config_reports_non_git_cwd(self) -> None:
        root = ROOT / ".tmp_test_repo_local_chunkhound_discovery_not_git"
        try:
            shutil.rmtree(root, ignore_errors=True)
            invocation_cwd = root / "cwd"
            invocation_cwd.mkdir(parents=True, exist_ok=True)

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                raise RuntimeError("not a git worktree")

            with mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd):
                candidate = cure_flows.discover_repo_local_chunkhound_config(
                    invocation_cwd=invocation_cwd,
                )

            self.assertEqual(candidate["candidate_state"], "absent")
            self.assertEqual(candidate["reason"], "cwd_not_git_worktree")
            self.assertIsNone(candidate["repo_root"])
            self.assertEqual(candidate["runtime_match_state"], "not_requested")
            self.assertEqual(candidate["target_match_state"], "not_requested")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_discover_repo_local_chunkhound_config_reports_broader_workspace_config(self) -> None:
        root = ROOT / ".tmp_test_repo_local_chunkhound_discovery_workspace_reject"
        try:
            shutil.rmtree(root, ignore_errors=True)
            workspace_root = root / "workspace"
            repo_root = workspace_root / "repo"
            invocation_cwd = repo_root / "src"
            invocation_cwd.mkdir(parents=True, exist_ok=True)
            resolved_runtime_config = self._runtime_seed_config()
            config_path, _ = self._write_repo_local_chunkhound_state(
                repo_root=workspace_root,
                resolved_runtime_config=resolved_runtime_config,
                config_name="chunkhound.json",
            )

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                if cmd == ["git", "-C", str(invocation_cwd), "rev-parse", "--show-toplevel"]:
                    return mock.Mock(stdout=f"{repo_root}\n", stderr="", duration_seconds=0.0)
                raise AssertionError(f"unexpected command: {cmd}")

            with mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd):
                candidate = cure_flows.discover_repo_local_chunkhound_config(
                    invocation_cwd=invocation_cwd,
                    resolved_runtime_config=resolved_runtime_config,
                )

            self.assertEqual(candidate["candidate_state"], "incompatible")
            self.assertEqual(candidate["reason"], "config_not_at_repo_root")
            self.assertEqual(candidate["repo_root"], str(repo_root.resolve()))
            self.assertEqual(candidate["config_path"], str(config_path.resolve()))
            self.assertIsNone(candidate["db_path"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_discover_repo_local_chunkhound_config_reports_invalid_config(self) -> None:
        root = ROOT / ".tmp_test_repo_local_chunkhound_discovery_invalid_config"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_root = root / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            (repo_root / "chunkhound.json").write_text("{", encoding="utf-8")

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                if cmd == ["git", "-C", str(repo_root), "rev-parse", "--show-toplevel"]:
                    return mock.Mock(stdout=f"{repo_root}\n", stderr="", duration_seconds=0.0)
                raise AssertionError(f"unexpected command: {cmd}")

            with mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd):
                candidate = cure_flows.discover_repo_local_chunkhound_config(
                    invocation_cwd=repo_root,
                )

            self.assertEqual(candidate["candidate_state"], "incompatible")
            self.assertEqual(candidate["reason"], "invalid_candidate_config")
            self.assertEqual(candidate["config_file_name"], "chunkhound.json")
            self.assertIsNone(candidate["db_provider"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_discover_repo_local_chunkhound_config_reports_missing_db_path(self) -> None:
        root = ROOT / ".tmp_test_repo_local_chunkhound_discovery_missing_db_path"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_root = root / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            config_path = repo_root / "chunkhound.json"
            config_path.write_text(
                json.dumps({"database": {"provider": "duckdb"}}, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                if cmd == ["git", "-C", str(repo_root), "rev-parse", "--show-toplevel"]:
                    return mock.Mock(stdout=f"{repo_root}\n", stderr="", duration_seconds=0.0)
                raise AssertionError(f"unexpected command: {cmd}")

            with mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd):
                candidate = cure_flows.discover_repo_local_chunkhound_config(
                    invocation_cwd=repo_root,
                )

            self.assertEqual(candidate["candidate_state"], "incompatible")
            self.assertEqual(candidate["reason"], "missing_candidate_db_path")
            self.assertEqual(candidate["config_path"], str(config_path.resolve()))
            self.assertEqual(candidate["db_provider"], "duckdb")
            self.assertIsNone(candidate["db_path"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_discover_repo_local_chunkhound_config_reports_ambiguous_origin_for_targeted_review(self) -> None:
        root = ROOT / ".tmp_test_repo_local_chunkhound_discovery_ambiguous_origin"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_root = root / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            resolved_runtime_config = self._runtime_seed_config()
            config_path, db_path = self._write_repo_local_chunkhound_state(
                repo_root=repo_root,
                resolved_runtime_config=resolved_runtime_config,
                config_name="chunkhound.json",
            )
            pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=17)

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                if cmd == ["git", "-C", str(repo_root), "rev-parse", "--show-toplevel"]:
                    return mock.Mock(stdout=f"{repo_root}\n", stderr="", duration_seconds=0.0)
                if cmd == ["git", "-C", str(repo_root), "remote", "get-url", "origin"]:
                    raise RuntimeError("origin missing")
                raise AssertionError(f"unexpected command: {cmd}")

            with mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd):
                candidate = cure_flows.discover_repo_local_chunkhound_config(
                    invocation_cwd=repo_root,
                    pr=pr,
                    resolved_runtime_config=resolved_runtime_config,
                )

            self.assertEqual(candidate["candidate_state"], "ambiguous")
            self.assertEqual(candidate["reason"], "origin_remote_unavailable")
            self.assertEqual(candidate["config_path"], str(config_path.resolve()))
            self.assertEqual(candidate["db_path"], str(db_path.resolve()))
            self.assertEqual(candidate["expected_repo_identity"], "github.com/acme/repo")
            self.assertEqual(candidate["repo_identity"], None)
            self.assertEqual(candidate["target_match_state"], "unknown")
            self.assertEqual(candidate["runtime_match_state"], "compatible")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_discover_exact_repo_local_chunkhound_seed_candidate_accepts_matching_repo_local_duckdb(self) -> None:
        root = ROOT / ".tmp_test_exact_repo_seed_accept"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_root = root / "repo"
            invocation_cwd = repo_root / "src"
            invocation_cwd.mkdir(parents=True, exist_ok=True)
            resolved_runtime_config = self._runtime_seed_config()
            config_path, db_path = self._write_repo_local_chunkhound_state(
                repo_root=repo_root,
                resolved_runtime_config=resolved_runtime_config,
            )
            pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=17)

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                if cmd == ["git", "-C", str(invocation_cwd), "rev-parse", "--show-toplevel"]:
                    return mock.Mock(stdout=f"{repo_root}\n", stderr="", duration_seconds=0.0)
                if cmd == ["git", "-C", str(repo_root), "remote", "get-url", "origin"]:
                    return mock.Mock(
                        stdout="git@github.com:acme/repo.git\n",
                        stderr="",
                        duration_seconds=0.0,
                    )
                raise AssertionError(f"unexpected command: {cmd}")

            with mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd):
                candidate = cure_flows.discover_exact_repo_local_chunkhound_seed_candidate(
                    pr=pr,
                    resolved_runtime_config=resolved_runtime_config,
                    invocation_cwd=invocation_cwd,
                )

            self.assertEqual(
                candidate,
                {
                    "repo_root": str(repo_root.resolve()),
                    "config_path": str(config_path.resolve()),
                    "db_path": str(db_path.resolve()),
                    "acceptance_state": "accepted",
                    "rejection_reason": None,
                },
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_discover_exact_repo_local_chunkhound_seed_candidate_rejects_broader_workspace_root_candidate(self) -> None:
        root = ROOT / ".tmp_test_exact_repo_seed_workspace_reject"
        try:
            shutil.rmtree(root, ignore_errors=True)
            workspace_root = root / "workspace"
            repo_root = workspace_root / "repo"
            invocation_cwd = repo_root / "src"
            invocation_cwd.mkdir(parents=True, exist_ok=True)
            resolved_runtime_config = self._runtime_seed_config()
            self._write_repo_local_chunkhound_state(
                repo_root=workspace_root,
                resolved_runtime_config=resolved_runtime_config,
            )
            pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=17)

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                if cmd == ["git", "-C", str(invocation_cwd), "rev-parse", "--show-toplevel"]:
                    return mock.Mock(stdout=f"{repo_root}\n", stderr="", duration_seconds=0.0)
                if cmd == ["git", "-C", str(repo_root), "remote", "get-url", "origin"]:
                    return mock.Mock(
                        stdout="https://github.com/acme/repo.git\n",
                        stderr="",
                        duration_seconds=0.0,
                    )
                raise AssertionError(f"unexpected command: {cmd}")

            with mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd):
                candidate = cure_flows.discover_exact_repo_local_chunkhound_seed_candidate(
                    pr=pr,
                    resolved_runtime_config=resolved_runtime_config,
                    invocation_cwd=invocation_cwd,
                )

            self.assertEqual(candidate["acceptance_state"], "absent")
            self.assertEqual(candidate["rejection_reason"], "missing_repo_local_config")
            self.assertEqual(candidate["repo_root"], str(repo_root.resolve()))
            self.assertIsNone(candidate["config_path"])
            self.assertIsNone(candidate["db_path"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_discover_exact_repo_local_chunkhound_seed_candidate_rejects_remote_mismatch(self) -> None:
        root = ROOT / ".tmp_test_exact_repo_seed_remote_mismatch"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_root = root / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            resolved_runtime_config = self._runtime_seed_config()
            self._write_repo_local_chunkhound_state(
                repo_root=repo_root,
                resolved_runtime_config=resolved_runtime_config,
            )
            pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=17)

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                if cmd == ["git", "-C", str(repo_root), "rev-parse", "--show-toplevel"]:
                    return mock.Mock(stdout=f"{repo_root}\n", stderr="", duration_seconds=0.0)
                if cmd == ["git", "-C", str(repo_root), "remote", "get-url", "origin"]:
                    return mock.Mock(
                        stdout="git@github.com:other/repo.git\n",
                        stderr="",
                        duration_seconds=0.0,
                    )
                raise AssertionError(f"unexpected command: {cmd}")

            with mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd):
                candidate = cure_flows.discover_exact_repo_local_chunkhound_seed_candidate(
                    pr=pr,
                    resolved_runtime_config=resolved_runtime_config,
                    invocation_cwd=repo_root,
                )

            self.assertEqual(candidate["acceptance_state"], "rejected")
            self.assertEqual(candidate["rejection_reason"], "repo_remote_mismatch")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_discover_exact_repo_local_chunkhound_seed_candidate_rejects_config_mismatch(self) -> None:
        root = ROOT / ".tmp_test_exact_repo_seed_config_mismatch"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_root = root / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            resolved_runtime_config = self._runtime_seed_config()
            self._write_repo_local_chunkhound_state(
                repo_root=repo_root,
                resolved_runtime_config=resolved_runtime_config,
                mutate_config=lambda config: config.setdefault("research", {}).__setitem__("algorithm", "semantic"),
            )
            pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=17)

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                if cmd == ["git", "-C", str(repo_root), "rev-parse", "--show-toplevel"]:
                    return mock.Mock(stdout=f"{repo_root}\n", stderr="", duration_seconds=0.0)
                if cmd == ["git", "-C", str(repo_root), "remote", "get-url", "origin"]:
                    return mock.Mock(
                        stdout="https://github.com/acme/repo.git\n",
                        stderr="",
                        duration_seconds=0.0,
                    )
                raise AssertionError(f"unexpected command: {cmd}")

            with mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd):
                candidate = cure_flows.discover_exact_repo_local_chunkhound_seed_candidate(
                    pr=pr,
                    resolved_runtime_config=resolved_runtime_config,
                    invocation_cwd=repo_root,
                )

            self.assertEqual(candidate["acceptance_state"], "rejected")
            self.assertEqual(candidate["rejection_reason"], "config_mismatch")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_discover_exact_repo_local_chunkhound_seed_candidate_rejects_orphan_duckdb_without_repo_local_config(self) -> None:
        root = ROOT / ".tmp_test_exact_repo_seed_orphan_db"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_root = root / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            orphan_db = repo_root / ".chunkhound"
            orphan_db.mkdir(parents=True, exist_ok=True)
            (orphan_db / "chunks.db").write_text("db", encoding="utf-8")
            pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=17)

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                if cmd == ["git", "-C", str(repo_root), "rev-parse", "--show-toplevel"]:
                    return mock.Mock(stdout=f"{repo_root}\n", stderr="", duration_seconds=0.0)
                if cmd == ["git", "-C", str(repo_root), "remote", "get-url", "origin"]:
                    return mock.Mock(
                        stdout="https://github.com/acme/repo.git\n",
                        stderr="",
                        duration_seconds=0.0,
                    )
                raise AssertionError(f"unexpected command: {cmd}")

            with mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd):
                candidate = cure_flows.discover_exact_repo_local_chunkhound_seed_candidate(
                    pr=pr,
                    resolved_runtime_config=self._runtime_seed_config(),
                    invocation_cwd=repo_root,
                )

            self.assertEqual(candidate["acceptance_state"], "absent")
            self.assertEqual(candidate["rejection_reason"], "missing_repo_local_config")
            self.assertIsNone(candidate["config_path"])
            self.assertIsNone(candidate["db_path"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_flow_prefers_exact_repo_local_chunkhound_seed_and_records_seed_source_metadata(self) -> None:
        root = ROOT / ".tmp_test_pr_exact_repo_seed"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            sandbox_root = root / "sandboxes"
            cache_root = root / "cache"
            sandbox_root.mkdir(parents=True, exist_ok=True)
            cache_root.mkdir(parents=True, exist_ok=True)
            seed = root / "seed"
            seed.mkdir(parents=True, exist_ok=True)
            base_db = root / "base.chunkhound.db"
            base_db.write_text("base-db", encoding="utf-8")
            base_cache_cfg = root / "base-cache-chunkhound.json"
            base_cache_cfg.write_text("{}", encoding="utf-8")
            base_cfg = root / "chunkhound-base.json"
            base_cfg.write_text("{}", encoding="utf-8")
            config_path = root / "reviewflow.toml"
            config_path.write_text(
                "\n".join(
                    [
                        "[chunkhound]",
                        f'base_config_path = "{base_cfg}"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            local_repo = root / "local-repo"
            local_repo.mkdir(parents=True, exist_ok=True)
            resolved_runtime_config = self._runtime_seed_config()
            local_config_path, local_db_path = self._write_repo_local_chunkhound_state(
                repo_root=local_repo,
                resolved_runtime_config=resolved_runtime_config,
            )
            args = rf.build_parser().parse_args(
                [
                    "pr",
                    "https://github.com/acme/repo/pull/14",
                    "--if-reviewed",
                    "new",
                    "--no-review",
                    "--ui",
                    "off",
                    "--quiet",
                    "--no-stream",
                ]
            )
            paths = rf.ReviewflowPaths(sandbox_root=sandbox_root, cache_root=cache_root)
            copy_calls: list[tuple[Path, Path]] = []

            class _Result:
                def __init__(self, stdout: str = "") -> None:
                    self.stdout = stdout
                    self.stderr = ""
                    self.duration_seconds = 0.0

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> _Result:
                if cmd[:2] == ["git", "clone"]:
                    Path(str(cmd[-1])).mkdir(parents=True, exist_ok=True)
                    return _Result()
                if cmd == ["git", "-C", str(local_repo), "rev-parse", "--show-toplevel"]:
                    return _Result(f"{local_repo}\n")
                if cmd == ["git", "-C", str(local_repo), "remote", "get-url", "origin"]:
                    return _Result("git@github.com:acme/repo.git\n")
                if cmd[:5] == ["git", "-C", str(seed), "remote", "get-url"]:
                    return _Result("https://github.com/acme/repo.git\n")
                if cmd[:4] == ["git", "-C", str(seed), "rev-parse"]:
                    return _Result("true\n")
                if cmd[:4] == ["git", "-C", str(Path(str(cmd[2]))), "rev-parse"]:
                    return _Result("deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n")
                if cmd[:3] == ["gh", "pr", "checkout"]:
                    return _Result()
                if cmd and cmd[0] in {"git", "rsync", "chunkhound"}:
                    return _Result()
                raise AssertionError(f"unexpected command: {cmd}")

            def fake_materialize_chunkhound_env_config(
                *,
                resolved_config: dict[str, object],
                output_config_path: Path,
                database_provider: str,
                database_path: Path,
            ) -> None:
                output_config_path.parent.mkdir(parents=True, exist_ok=True)
                output_config_path.write_text("{}", encoding="utf-8")
                database_path.parent.mkdir(parents=True, exist_ok=True)

            def fake_copy_duckdb_files(src: Path, dest: Path) -> None:
                copy_calls.append((src, dest))
                dest.parent.mkdir(parents=True, exist_ok=True)
                if src.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                    (dest / "chunks.db").write_text((src / "chunks.db").read_text(encoding="utf-8"), encoding="utf-8")
                    return
                dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

            def fake_write_pr_context_file(*, work_dir: Path, pr: rf.PullRequestRef, pr_meta: dict[str, object]) -> Path:
                context_path = work_dir / "pr-context.md"
                context_path.write_text("context", encoding="utf-8")
                return context_path

            stdout = StringIO()
            with contextlib.ExitStack() as stack:
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "gh_api_json",
                        return_value={
                            "base": {"ref": "main"},
                            "head": {"sha": "1111111111111111111111111111111111111111"},
                            "title": "Exact repo local seed PR",
                        },
                    )
                )
                stack.enter_context(mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[]))
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_chunkhound_runtime_config",
                        return_value=(
                            rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                            {"chunkhound": {"base_config_path": str(base_cfg)}},
                            resolved_runtime_config,
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "materialize_chunkhound_env_config",
                        side_effect=fake_materialize_chunkhound_env_config,
                    )
                )
                stack.enter_context(
                    mock.patch.object(rf, "write_pr_context_file", side_effect=fake_write_pr_context_file)
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "ensure_base_cache",
                        return_value={
                            "db_path": str(base_db),
                            "chunkhound_config_path": str(base_cache_cfg),
                        },
                    )
                )
                stack.enter_context(mock.patch.object(rf, "seed_dir", return_value=seed))
                stack.enter_context(mock.patch.object(rf, "ensure_clean_git_worktree"))
                stack.enter_context(mock.patch.object(rf, "same_device", return_value=True))
                stack.enter_context(mock.patch.object(rf, "copy_duckdb_files", side_effect=fake_copy_duckdb_files))
                stack.enter_context(mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd))
                stack.enter_context(mock.patch.object(rf.Path, "cwd", return_value=local_repo))
                stack.enter_context(
                    mock.patch.object(
                        rf.ReviewflowOutput,
                        "run_logged_cmd",
                        autospec=True,
                        side_effect=lambda output, cmd, **kwargs: fake_run_cmd(cmd, **kwargs),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_review_intelligence_config",
                        side_effect=AssertionError("review setup should be skipped"),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_reviewflow_multipass_defaults",
                        side_effect=AssertionError("multipass defaults should be skipped"),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "resolve_prompt_profile",
                        side_effect=AssertionError("prompt selection should be skipped"),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "require_builtin_review_intelligence",
                        side_effect=AssertionError("review validation should be skipped"),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "resolve_llm_config_from_args",
                        side_effect=AssertionError("llm resolution should be skipped"),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "prepare_review_agent_runtime",
                        side_effect=AssertionError("runtime setup should be skipped"),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "run_llm_exec",
                        side_effect=AssertionError("review execution should be skipped"),
                    )
                )
                stack.enter_context(mock.patch("sys.stdout", stdout))
                rc = rf.pr_flow(
                    args,
                    paths=paths,
                    config_path=config_path,
                    codex_base_config_path=root / "codex.toml",
                )

            self.assertEqual(rc, 0)
            self.assertEqual(copy_calls[0][0], local_db_path.resolve())
            session_dir = Path(stdout.getvalue().strip())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(
                meta["chunkhound"]["seed_source"],
                {
                    "source_kind": "repo_local_duckdb",
                    "repo_root": str(local_repo.resolve()),
                    "db_path": str(local_db_path.resolve()),
                    "config_path": str(local_config_path.resolve()),
                    "acceptance_state": "accepted",
                    "rejection_reason": None,
                    "candidate_db_path": str(local_db_path.resolve()),
                    "candidate_config_path": str(local_config_path.resolve()),
                },
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)


class RefactorRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        rf._set_disabled_reviewflow_config_path(None)
        cure_runtime._set_disabled_reviewflow_config_path(None)

    def tearDown(self) -> None:
        rf._set_disabled_reviewflow_config_path(None)
        cure_runtime._set_disabled_reviewflow_config_path(None)

    def test_load_toml_raises_on_malformed_content(self) -> None:
        cfg = ROOT / ".tmp_test_malformed_reviewflow.toml"
        try:
            cfg.write_text("[paths\nsandbox_root = \"/tmp/x\"\n", encoding="utf-8")
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.load_toml(cfg)
            self.assertIn(str(cfg), str(ctx.exception))
        finally:
            cfg.unlink(missing_ok=True)

    def test_load_toml_raises_on_unreadable_file(self) -> None:
        cfg = ROOT / ".tmp_test_unreadable_reviewflow.toml"
        try:
            cfg.write_text("[paths]\n", encoding="utf-8")
            original_read_text = Path.read_text

            def fake_read_text(path: Path, *args: object, **kwargs: object) -> str:
                if path == cfg:
                    raise PermissionError("denied")
                return original_read_text(path, *args, **kwargs)

            with mock.patch.object(Path, "read_text", autospec=True, side_effect=fake_read_text):
                with self.assertRaises(rf.ReviewflowError) as ctx:
                    rf.load_toml(cfg)
            self.assertIn(str(cfg), str(ctx.exception))
            self.assertIn("denied", str(ctx.exception))
        finally:
            cfg.unlink(missing_ok=True)

    def test_scan_completed_sessions_for_pr_matches_case_insensitive_identity(self) -> None:
        root = ROOT / ".tmp_test_case_insensitive_history"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)

            session_dir = root / "s1"
            session_dir.mkdir()
            review_md = session_dir / "review.md"
            review_md.write_text(
                _sectioned_review_markdown(business="APPROVE", technical="REQUEST CHANGES"),
                encoding="utf-8",
            )
            (session_dir / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s1",
                        "status": "done",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 11,
                        "created_at": "2026-03-03T00:00:00+00:00",
                        "completed_at": "2026-03-03T01:00:00+00:00",
                        "head_sha": "1111111111111111111111111111111111111111",
                        "paths": {"review_md": str(review_md)},
                    }
                ),
                encoding="utf-8",
            )

            pr = rf.PullRequestRef(host="GitHub.COM", owner="AcMe", repo="Repo", number=11)
            sessions = rf.scan_completed_sessions_for_pr(sandbox_root=root, pr=pr)

            self.assertEqual([session.session_id for session in sessions], ["s1"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_select_zip_sources_for_pr_head_matches_case_insensitive_identity(self) -> None:
        root = ROOT / ".tmp_test_case_insensitive_zip"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)

            session_dir = root / "zip-session"
            session_dir.mkdir()
            review_md = session_dir / "review.md"
            review_md.write_text(
                _sectioned_review_markdown(business="APPROVE", technical="APPROVE"),
                encoding="utf-8",
            )
            (session_dir / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "zip-session",
                        "status": "done",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 12,
                        "head_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                        "review_head_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                        "created_at": "2026-03-03T00:00:00+00:00",
                        "completed_at": "2026-03-03T01:00:00+00:00",
                        "paths": {"review_md": str(review_md)},
                    }
                ),
                encoding="utf-8",
            )

            pr = rf.PullRequestRef(host="GitHub.COM", owner="AcMe", repo="Repo", number=12)
            sources = rf.select_zip_sources_for_pr_head(
                sandbox_root=root,
                pr=pr,
                head_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            )

            self.assertEqual([source.session_id for source in sources], ["zip-session"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_status_flow_matches_mixed_case_pr_url(self) -> None:
        root = ROOT / ".tmp_test_case_insensitive_status"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            paths = rf.ReviewflowPaths(
                sandbox_root=root,
                cache_root=root / "cache",
            )
            session_dir = root / "status-session"
            session_dir.mkdir()
            review_md = session_dir / "review.md"
            review_md.write_text("**Decision**: APPROVE\n", encoding="utf-8")
            (session_dir / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "status-session",
                        "status": "done",
                        "phase": "review",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 13,
                        "created_at": "2026-03-03T00:00:00+00:00",
                        "completed_at": "2026-03-03T01:00:00+00:00",
                        "paths": {"review_md": str(review_md)},
                    }
                ),
                encoding="utf-8",
            )

            stdout = StringIO()
            rc = rf.status_flow(
                argparse.Namespace(target="https://GitHub.com/AcMe/Repo/pull/13", json_output=True),
                paths=paths,
                stdout=stdout,
            )
            payload = json.loads(stdout.getvalue())

            self.assertEqual(rc, 0)
            self.assertEqual(payload["resolved_target"]["session_id"], "status-session")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_flow_no_review_skips_review_only_setup(self) -> None:
        root = ROOT / ".tmp_test_pr_no_review"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            sandbox_root = root / "sandboxes"
            cache_root = root / "cache"
            sandbox_root.mkdir(parents=True, exist_ok=True)
            cache_root.mkdir(parents=True, exist_ok=True)
            seed = root / "seed"
            seed.mkdir(parents=True, exist_ok=True)
            base_db = root / "base.chunkhound.db"
            base_db.write_text("db", encoding="utf-8")
            base_cfg = root / "chunkhound-base.json"
            base_cfg.write_text("{}", encoding="utf-8")
            config_path = root / "reviewflow.toml"
            config_path.write_text(
                "\n".join(
                    [
                        "[chunkhound]",
                        f'base_config_path = "{base_cfg}"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            args = rf.build_parser().parse_args(
                [
                    "pr",
                    "https://github.com/acme/repo/pull/14",
                    "--if-reviewed",
                    "new",
                    "--no-review",
                    "--ui",
                    "off",
                    "--quiet",
                    "--no-stream",
                ]
            )

            paths = rf.ReviewflowPaths(
                sandbox_root=sandbox_root,
                cache_root=cache_root,
            )

            class _Result:
                def __init__(self, stdout: str = "") -> None:
                    self.stdout = stdout
                    self.stderr = ""
                    self.duration_seconds = 0.0

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> _Result:
                if cmd[:2] == ["git", "clone"]:
                    Path(str(cmd[-1])).mkdir(parents=True, exist_ok=True)
                    return _Result()
                if cmd[:5] == ["git", "-C", str(seed), "remote", "get-url"]:
                    return _Result("https://github.com/acme/repo.git\n")
                if cmd[:4] == ["git", "-C", str(seed), "rev-parse"]:
                    return _Result("true\n")
                if cmd[:4] == ["git", "-C", str(Path(str(cmd[2]))), "rev-parse"]:
                    return _Result("deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n")
                if cmd[:3] == ["gh", "pr", "checkout"]:
                    return _Result()
                if cmd and cmd[0] in {"git", "rsync", "chunkhound"}:
                    return _Result()
                raise AssertionError(f"unexpected command: {cmd}")

            def fake_copy_duckdb_files(src: Path, dest: Path) -> None:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

            def fake_materialize_chunkhound_env_config(
                *,
                resolved_config: dict[str, object],
                output_config_path: Path,
                database_provider: str,
                database_path: Path,
            ) -> None:
                output_config_path.parent.mkdir(parents=True, exist_ok=True)
                output_config_path.write_text("{}", encoding="utf-8")
                database_path.parent.mkdir(parents=True, exist_ok=True)

            def fake_write_pr_context_file(*, work_dir: Path, pr: rf.PullRequestRef, pr_meta: dict[str, object]) -> Path:
                context_path = work_dir / "pr-context.md"
                context_path.write_text("context", encoding="utf-8")
                return context_path

            stdout = StringIO()
            stderr = StringIO()
            with contextlib.ExitStack() as stack:
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "gh_api_json",
                        return_value={
                            "base": {"ref": "main"},
                            "head": {"sha": "1111111111111111111111111111111111111111"},
                            "title": "No review PR",
                        },
                    )
                )
                stack.enter_context(mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[]))
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_chunkhound_runtime_config",
                        return_value=(
                            rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                            {"chunkhound": {"base_config_path": str(base_cfg)}},
                            {"indexing": {"exclude": []}},
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "materialize_chunkhound_env_config",
                        side_effect=fake_materialize_chunkhound_env_config,
                    )
                )
                stack.enter_context(
                    mock.patch.object(rf, "write_pr_context_file", side_effect=fake_write_pr_context_file)
                )
                stack.enter_context(mock.patch.object(rf, "ensure_base_cache", return_value={"db_path": str(base_db)}))
                stack.enter_context(mock.patch.object(rf, "seed_dir", return_value=seed))
                stack.enter_context(mock.patch.object(rf, "ensure_clean_git_worktree"))
                stack.enter_context(mock.patch.object(rf, "same_device", return_value=True))
                stack.enter_context(mock.patch.object(rf, "copy_duckdb_files", side_effect=fake_copy_duckdb_files))
                stack.enter_context(mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd))
                stack.enter_context(
                    mock.patch.object(
                        rf.ReviewflowOutput,
                        "run_logged_cmd",
                        autospec=True,
                        side_effect=lambda self, cmd, **kwargs: fake_run_cmd(cmd, **kwargs),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_review_intelligence_config",
                        side_effect=AssertionError("review setup should be skipped"),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_reviewflow_multipass_defaults",
                        side_effect=AssertionError("multipass defaults should be skipped"),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "resolve_prompt_profile",
                        side_effect=AssertionError("prompt selection should be skipped"),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "require_builtin_review_intelligence",
                        side_effect=AssertionError("review validation should be skipped"),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "resolve_llm_config_from_args",
                        side_effect=AssertionError("llm resolution should be skipped"),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "prepare_review_agent_runtime",
                        side_effect=AssertionError("runtime setup should be skipped"),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "run_llm_exec",
                        side_effect=AssertionError("review execution should be skipped"),
                    )
                )
                stack.enter_context(mock.patch("sys.stdout", stdout))
                stack.enter_context(mock.patch("sys.stderr", stderr))
                rc = rf.pr_flow(args, paths=paths, config_path=config_path, codex_base_config_path=root / "codex.toml")

            session_dir = Path(stdout.getvalue().strip())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(rc, 0)
            self.assertTrue(session_dir.is_dir())
            self.assertTrue((session_dir / "work" / "logs" / "cure.log").is_file())
            self.assertTrue((session_dir / "work" / "chunkhound" / "chunkhound.json").is_file())
            self.assertTrue(meta["notes"]["no_review"])
            self.assertEqual(meta["status"], "done")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_flow_review_renders_review_intelligence_guidance(self) -> None:
        root = ROOT / ".tmp_test_pr_review_guidance"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            sandbox_root = root / "sandboxes"
            cache_root = root / "cache"
            sandbox_root.mkdir(parents=True, exist_ok=True)
            cache_root.mkdir(parents=True, exist_ok=True)
            seed = root / "seed"
            seed.mkdir(parents=True, exist_ok=True)
            base_db = root / "base.chunkhound.db"
            base_db.write_text("db", encoding="utf-8")
            base_cfg = root / "chunkhound-base.json"
            base_cfg.write_text("{}", encoding="utf-8")
            config_path = root / "reviewflow.toml"
            config_path.write_text(
                "\n".join(
                    [
                        "[chunkhound]",
                        f'base_config_path = "{base_cfg}"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            args = rf.build_parser().parse_args(
                [
                    "pr",
                    "https://github.com/acme/repo/pull/14",
                    "--if-reviewed",
                    "new",
                    "--ui",
                    "off",
                    "--quiet",
                    "--no-stream",
                ]
            )

            paths = rf.ReviewflowPaths(
                sandbox_root=sandbox_root,
                cache_root=cache_root,
            )

            class _Result:
                def __init__(self, stdout: str = "") -> None:
                    self.stdout = stdout
                    self.stderr = ""
                    self.duration_seconds = 0.0

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> _Result:
                if cmd[:2] == ["git", "clone"]:
                    Path(str(cmd[-1])).mkdir(parents=True, exist_ok=True)
                    return _Result()
                if cmd[:5] == ["git", "-C", str(seed), "remote", "get-url"]:
                    return _Result("https://github.com/acme/repo.git\n")
                if cmd[:4] == ["git", "-C", str(seed), "rev-parse"]:
                    return _Result("true\n")
                if cmd[:4] == ["git", "-C", str(Path(str(cmd[2]))), "rev-parse"]:
                    return _Result("deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n")
                if cmd[:3] == ["gh", "pr", "checkout"]:
                    return _Result()
                if cmd and cmd[0] in {"git", "rsync", "chunkhound"}:
                    return _Result()
                raise AssertionError(f"unexpected command: {cmd}")

            def fake_copy_duckdb_files(src: Path, dest: Path) -> None:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

            def fake_materialize_chunkhound_env_config(
                *,
                resolved_config: dict[str, object],
                output_config_path: Path,
                database_provider: str,
                database_path: Path,
            ) -> None:
                output_config_path.parent.mkdir(parents=True, exist_ok=True)
                output_config_path.write_text("{}", encoding="utf-8")
                database_path.parent.mkdir(parents=True, exist_ok=True)

            def fake_write_pr_context_file(
                *,
                work_dir: Path,
                pr: rf.PullRequestRef,
                pr_meta: dict[str, object],
            ) -> Path:
                context_path = work_dir / "pr-context.md"
                context_path.write_text("context", encoding="utf-8")
                return context_path

            captured: dict[str, str] = {}

            def fake_run_llm_exec(**kwargs: object) -> rf.CodexRunResult:
                prompt = kwargs["prompt"]
                assert isinstance(prompt, str)
                captured["prompt"] = prompt
                raise RuntimeError("stop after prompt render")

            staged_gh = root / "staged-gh"
            staged_gh.mkdir(parents=True, exist_ok=True)
            staged_jira_cfg = root / "jira.yml"
            staged_jira_cfg.write_text("jira", encoding="utf-8")
            staged_jira_helper = root / "rf-jira"
            staged_jira_helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            staged_jira_helper.chmod(0o755)

            with contextlib.ExitStack() as stack:
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "gh_api_json",
                        return_value={
                            "base": {"ref": "main"},
                            "head": {"sha": "1111111111111111111111111111111111111111"},
                            "title": "Guided review PR",
                        },
                    )
                )
                stack.enter_context(mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[]))
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_chunkhound_runtime_config",
                        return_value=(
                            rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                            {"chunkhound": {"base_config_path": str(base_cfg)}},
                            {"indexing": {"exclude": []}},
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "materialize_chunkhound_env_config",
                        side_effect=fake_materialize_chunkhound_env_config,
                    )
                )
                stack.enter_context(
                    mock.patch.object(rf, "write_pr_context_file", side_effect=fake_write_pr_context_file)
                )
                stack.enter_context(mock.patch.object(rf, "ensure_base_cache", return_value={"db_path": str(base_db)}))
                stack.enter_context(mock.patch.object(rf, "seed_dir", return_value=seed))
                stack.enter_context(mock.patch.object(rf, "ensure_clean_git_worktree"))
                stack.enter_context(mock.patch.object(rf, "same_device", return_value=True))
                stack.enter_context(mock.patch.object(rf, "copy_duckdb_files", side_effect=fake_copy_duckdb_files))
                stack.enter_context(mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd))
                stack.enter_context(
                    mock.patch.object(
                        rf.ReviewflowOutput,
                        "run_logged_cmd",
                        autospec=True,
                        side_effect=lambda self, cmd, **kwargs: fake_run_cmd(cmd, **kwargs),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_review_intelligence_config",
                        return_value=(
                            _review_intelligence_cfg(),
                            _review_intelligence_meta(_review_intelligence_cfg()),
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_reviewflow_multipass_defaults",
                        return_value=(
                            {"enabled": False, "max_steps": 20},
                            {"enabled": False, "max_steps": 20},
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "resolve_prompt_profile",
                        return_value=("normal", "forced:test"),
                    )
                )
                stack.enter_context(mock.patch.object(rf, "require_builtin_review_intelligence"))
                stack.enter_context(
                    mock.patch.object(
                        shutil,
                        "which",
                        side_effect=lambda name: f"/usr/bin/{name}" if name in {"gh", "jira"} else None,
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "resolve_llm_config_from_args",
                        return_value=(
                            {"provider": "openai", "preset": "test-openai"},
                            {},
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "prepare_review_agent_runtime",
                        return_value={
                            "env": {
                                "GH_CONFIG_DIR": str(staged_gh),
                                "JIRA_CONFIG_FILE": str(staged_jira_cfg),
                            },
                            "metadata": {},
                            "staged_paths": {"rf_jira": str(staged_jira_helper)},
                            "add_dirs": [],
                        },
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_builtin_prompt_text",
                        return_value=(
                            "Prompt header\n"
                            "$REVIEW_INTELLIGENCE_GUIDANCE\n"
                            "Context: $PR_CONTEXT_PATH\n"
                        ),
                    )
                )
                stack.enter_context(mock.patch.object(rf, "run_llm_exec", side_effect=fake_run_llm_exec))
                with self.assertRaisesRegex(RuntimeError, "stop after prompt render"):
                    rf.pr_flow(args, paths=paths, config_path=config_path, codex_base_config_path=root / "codex.toml")

            self.assertIn("Configured sources:", captured["prompt"])
            self.assertIn("`github` (`auto`, `available`)", captured["prompt"])
            self.assertIn("Use local `git` as the authoritative source for code changes.", captured["prompt"])
            self.assertNotIn("GitHub MCP", captured["prompt"])
            self.assertIn("Context: ", captured["prompt"])
            session_dirs = sorted(sandbox_root.iterdir())
            self.assertEqual(len(session_dirs), 1)
            meta = json.loads((session_dirs[0] / "meta.json").read_text(encoding="utf-8"))
            capability_sources = {
                source["name"]: source["capability"] for source in meta["review_intelligence"]["sources"]
            }
            self.assertEqual(capability_sources["github"]["status"], "available")
            self.assertEqual(meta["review_intelligence"]["capabilities"]["status_counts"]["available"], 2)
        finally:
            shutil.rmtree(root, ignore_errors=True)

class MultipassGroundingRuntimeTests(unittest.TestCase):
    def _fake_run_cmd(self, *, seed: Path) -> object:
        class _Result:
            def __init__(self, stdout: str = "") -> None:
                self.stdout = stdout
                self.stderr = ""
                self.duration_seconds = 0.0

        def runner(cmd: list[str], **kwargs: object) -> _Result:
            if cmd[:2] == ["git", "clone"]:
                Path(str(cmd[-1])).mkdir(parents=True, exist_ok=True)
                return _Result()
            if cmd[:5] == ["git", "-C", str(seed), "remote", "get-url"]:
                return _Result("https://github.com/acme/repo.git\n")
            if cmd[:4] == ["git", "-C", str(seed), "rev-parse"]:
                return _Result("true\n")
            if cmd[:4] == ["git", "-C", str(Path(str(cmd[2]))), "rev-parse"]:
                return _Result("deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n")
            if cmd[:3] == ["gh", "pr", "checkout"]:
                return _Result()
            if cmd and cmd[0] in {"git", "rsync", "chunkhound"}:
                return _Result()
            raise AssertionError(f"unexpected command: {cmd}")

        return runner

    def _fake_materialize_chunkhound_env_config(
        self,
        *,
        resolved_config: dict[str, object],
        output_config_path: Path,
        database_provider: str,
        database_path: Path,
    ) -> None:
        output_config_path.parent.mkdir(parents=True, exist_ok=True)
        output_config_path.write_text("{}", encoding="utf-8")
        database_path.parent.mkdir(parents=True, exist_ok=True)

    def _fake_write_pr_context_file(
        self,
        *,
        work_dir: Path,
        pr: rf.PullRequestRef,
        pr_meta: dict[str, object],
    ) -> Path:
        context_path = work_dir / "pr-context.md"
        context_path.write_text("context", encoding="utf-8")
        return context_path

    def _valid_synth_markdown(self, primary_citation: str = "work/pr-context.md:1") -> str:
        return "\n".join(
            [
                "### Steps taken",
                "- Read step output",
                "",
                "**Summary**: ok",
                "",
                "## Business / Product Assessment",
                "**Verdict**: APPROVE",
                "",
                "### Strengths",
                f"- Business value is clear. Sources: `{primary_citation}`",
                "",
                "### In Scope Issues",
                "- None.",
                "",
                "### Out of Scope Issues",
                "- None.",
                "",
                "## Technical Assessment",
                "**Verdict**: REQUEST CHANGES",
                "",
                "### Strengths",
                f"- Technical read happened. Sources: `{primary_citation}`",
                "",
                "### In Scope Issues",
                f"- Missing provenance hygiene. Sources: `{primary_citation}`",
                "",
                "### Out of Scope Issues",
                "- None.",
                "",
                "### Reusability",
                f"- Artifact stays inspectable. Sources: `{primary_citation}`",
                "",
            ]
        )

    def _run_pr_flow_with_grounding(self, *, grounding_mode: str) -> tuple[Path, list[str]]:
        root = ROOT / f".tmp_test_pr_grounding_{grounding_mode}"
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        sandbox_root = root / "sandboxes"
        cache_root = root / "cache"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        cache_root.mkdir(parents=True, exist_ok=True)
        seed = root / "seed"
        seed.mkdir(parents=True, exist_ok=True)
        base_db = root / "base.chunkhound.db"
        base_db.write_text("db", encoding="utf-8")
        base_cfg = root / "chunkhound-base.json"
        base_cfg.write_text("{}", encoding="utf-8")
        config_path = root / "reviewflow.toml"
        config_path.write_text(
            f"[chunkhound]\nbase_config_path = {json.dumps(str(base_cfg))}\n",
            encoding="utf-8",
        )
        paths = rf.ReviewflowPaths(sandbox_root=sandbox_root, cache_root=cache_root)
        args = rf.build_parser().parse_args(
            [
                "pr",
                "https://github.com/acme/repo/pull/14",
                "--if-reviewed",
                "new",
                "--ui",
                "off",
                "--quiet",
                "--no-stream",
            ]
        )
        calls: list[str] = []
        def fake_copy_duckdb_files(src: Path, dest: Path) -> None:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

        def fake_run_llm_exec(**kwargs: object) -> rf.LlmRunResult:
            output_path = Path(str(kwargs["output_path"]))
            calls.append(output_path.name)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if output_path.name == "review.plan.md":
                output_path.write_text(
                    "\n".join(
                        [
                            "### Plan JSON",
                            "```json",
                            json.dumps(
                                {
                                    "abort": False,
                                    "abort_reason": None,
                                    "jira_keys": ["ABC-1"],
                                    "steps": [{"id": "01", "title": "API review", "focus": "grounding"}],
                                }
                            ),
                            "```",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
            elif output_path.name == "review.step-01.md":
                output_path.write_text(
                    "\n".join(
                        [
                            "### Step Result: 01 — API review",
                            "**Focus**: grounding",
                            "",
                            "### Steps taken",
                            "- checked repo",
                            "",
                            "### Findings",
                            "- Missing provenance on this finding.",
                            "",
                            "### Suggested actions",
                            "- Add evidence suffixes",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
            elif output_path.name == "review.md":
                output_path.write_text(self._valid_synth_markdown(), encoding="utf-8")
            else:
                raise AssertionError(f"unexpected output path: {output_path}")
            return rf.LlmRunResult(resume=None)

        with contextlib.ExitStack() as stack:
            fake_run_cmd = self._fake_run_cmd(seed=seed)
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "gh_api_json",
                    return_value={
                        "base": {"ref": "main"},
                        "head": {"sha": "1111111111111111111111111111111111111111"},
                        "title": "Grounding PR",
                    },
                )
            )
            stack.enter_context(mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[]))
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                        {"chunkhound": {"base_config_path": str(base_cfg)}},
                        {"indexing": {"exclude": []}},
                    ),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "materialize_chunkhound_env_config",
                    side_effect=self._fake_materialize_chunkhound_env_config,
                )
            )
            stack.enter_context(
                mock.patch.object(rf, "write_pr_context_file", side_effect=self._fake_write_pr_context_file)
            )
            stack.enter_context(mock.patch.object(rf, "ensure_base_cache", return_value={"db_path": str(base_db)}))
            stack.enter_context(mock.patch.object(rf, "seed_dir", return_value=seed))
            stack.enter_context(mock.patch.object(rf, "ensure_clean_git_worktree"))
            stack.enter_context(mock.patch.object(rf, "same_device", return_value=True))
            stack.enter_context(mock.patch.object(rf, "copy_duckdb_files", side_effect=fake_copy_duckdb_files))
            stack.enter_context(mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd))
            stack.enter_context(
                mock.patch.object(
                    rf.ReviewflowOutput,
                    "run_logged_cmd",
                    autospec=True,
                    side_effect=lambda output, cmd, **kwargs: fake_run_cmd(cmd, **kwargs),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "load_review_intelligence_config",
                    return_value=(
                        _review_intelligence_cfg(),
                        _review_intelligence_meta(_review_intelligence_cfg()),
                    ),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "load_reviewflow_multipass_defaults",
                    return_value=(
                        {"enabled": True, "max_steps": 20, "grounding_mode": grounding_mode},
                        {"multipass": {"enabled": True, "max_steps": 20, "grounding_mode": grounding_mode}},
                    ),
                )
            )
            stack.enter_context(mock.patch.object(rf, "resolve_prompt_profile", return_value=("big", "forced:test")))
            stack.enter_context(mock.patch.object(rf, "require_builtin_review_intelligence"))
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "resolve_llm_config_from_args",
                    return_value=(
                        {"provider": "openai", "preset": "test-openai"},
                        {},
                    ),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "prepare_review_agent_runtime",
                    return_value={
                        "env": {},
                        "metadata": {},
                        "staged_paths": {},
                        "add_dirs": [],
                        "codex_config_overrides": [],
                    },
                )
            )
            stack.enter_context(mock.patch.object(rf, "run_llm_exec", side_effect=fake_run_llm_exec))
            if grounding_mode == "strict":
                with self.assertRaisesRegex(rf.ReviewflowError, "grounding validation failed"):
                    rf.pr_flow(
                        args,
                        paths=paths,
                        config_path=config_path,
                        codex_base_config_path=root / "codex.toml",
                    )
            else:
                rc = rf.pr_flow(
                    args,
                    paths=paths,
                    config_path=config_path,
                    codex_base_config_path=root / "codex.toml",
                )
                self.assertEqual(rc, 0)
        return root, calls

    def _run_pr_flow_with_synth_grounding(self, *, synth_markdown: str) -> tuple[Path, list[str]]:
        root = ROOT / ".tmp_test_pr_synth_grounding"
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        sandbox_root = root / "sandboxes"
        cache_root = root / "cache"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        cache_root.mkdir(parents=True, exist_ok=True)
        seed = root / "seed"
        seed.mkdir(parents=True, exist_ok=True)
        base_db = root / "base.chunkhound.db"
        base_db.write_text("db", encoding="utf-8")
        base_cfg = root / "chunkhound-base.json"
        base_cfg.write_text("{}", encoding="utf-8")
        config_path = root / "reviewflow.toml"
        config_path.write_text(
            f"[chunkhound]\nbase_config_path = {json.dumps(str(base_cfg))}\n",
            encoding="utf-8",
        )
        paths = rf.ReviewflowPaths(sandbox_root=sandbox_root, cache_root=cache_root)
        args = rf.build_parser().parse_args(
            [
                "pr",
                "https://github.com/acme/repo/pull/14",
                "--if-reviewed",
                "new",
                "--ui",
                "off",
                "--quiet",
                "--no-stream",
            ]
        )
        calls: list[str] = []
        def fake_copy_duckdb_files(src: Path, dest: Path) -> None:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

        def fake_run_llm_exec(**kwargs: object) -> rf.LlmRunResult:
            output_path = Path(str(kwargs["output_path"]))
            repo_dir = Path(str(kwargs["repo_dir"]))
            calls.append(output_path.name)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if output_path.name == "review.plan.md":
                output_path.write_text(
                    "\n".join(
                        [
                            "### Plan JSON",
                            "```json",
                            json.dumps(
                                {
                                    "abort": False,
                                    "abort_reason": None,
                                    "jira_keys": ["ABC-1"],
                                    "steps": [{"id": "01", "title": "API review", "focus": "grounding"}],
                                }
                            ),
                            "```",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
            elif output_path.name == "review.step-01.md":
                (repo_dir / "src").mkdir(parents=True, exist_ok=True)
                (repo_dir / "src" / "app.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
                output_path.write_text(
                    "\n".join(
                        [
                            "### Step Result: 01 — API review",
                            "**Focus**: grounding",
                            "",
                            "### Steps taken",
                            "- checked repo",
                            "",
                            "### Findings",
                            "- Input lacks validation. Evidence: `src/app.py:2`",
                            "",
                            "### Suggested actions",
                            "- Add checks",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
            elif output_path.name == "review.md":
                work_context = output_path.parent / "work" / "pr-context.md"
                work_context.parent.mkdir(parents=True, exist_ok=True)
                work_context.write_text("context\n", encoding="utf-8")
                output_path.write_text(synth_markdown, encoding="utf-8")
            else:
                raise AssertionError(f"unexpected output path: {output_path}")
            return rf.LlmRunResult(resume=None)

        with contextlib.ExitStack() as stack:
            fake_run_cmd = self._fake_run_cmd(seed=seed)
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "gh_api_json",
                    return_value={
                        "base": {"ref": "main"},
                        "head": {"sha": "1111111111111111111111111111111111111111"},
                        "title": "Grounding PR",
                    },
                )
            )
            stack.enter_context(mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[]))
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                        {"chunkhound": {"base_config_path": str(base_cfg)}},
                        {"indexing": {"exclude": []}},
                    ),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "materialize_chunkhound_env_config",
                    side_effect=self._fake_materialize_chunkhound_env_config,
                )
            )
            stack.enter_context(
                mock.patch.object(rf, "write_pr_context_file", side_effect=self._fake_write_pr_context_file)
            )
            stack.enter_context(mock.patch.object(rf, "ensure_base_cache", return_value={"db_path": str(base_db)}))
            stack.enter_context(mock.patch.object(rf, "seed_dir", return_value=seed))
            stack.enter_context(mock.patch.object(rf, "ensure_clean_git_worktree"))
            stack.enter_context(mock.patch.object(rf, "same_device", return_value=True))
            stack.enter_context(mock.patch.object(rf, "copy_duckdb_files", side_effect=fake_copy_duckdb_files))
            stack.enter_context(mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd))
            stack.enter_context(
                mock.patch.object(
                    rf.ReviewflowOutput,
                    "run_logged_cmd",
                    autospec=True,
                    side_effect=lambda output, cmd, **kwargs: fake_run_cmd(cmd, **kwargs),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "load_review_intelligence_config",
                    return_value=(
                        _review_intelligence_cfg(),
                        _review_intelligence_meta(_review_intelligence_cfg()),
                    ),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "load_reviewflow_multipass_defaults",
                    return_value=(
                        {"enabled": True, "max_steps": 20, "grounding_mode": "strict"},
                        {"multipass": {"enabled": True, "max_steps": 20, "grounding_mode": "strict"}},
                    ),
                )
            )
            stack.enter_context(mock.patch.object(rf, "resolve_prompt_profile", return_value=("big", "forced:test")))
            stack.enter_context(mock.patch.object(rf, "require_builtin_review_intelligence"))
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "resolve_llm_config_from_args",
                    return_value=(
                        {"provider": "openai", "preset": "test-openai"},
                        {},
                    ),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "prepare_review_agent_runtime",
                    return_value={
                        "env": {},
                        "metadata": {},
                        "staged_paths": {},
                        "add_dirs": [],
                        "codex_config_overrides": [],
                    },
                )
            )
            stack.enter_context(mock.patch.object(rf, "run_llm_exec", side_effect=fake_run_llm_exec))
            rc = rf.pr_flow(
                args,
                paths=paths,
                config_path=config_path,
                codex_base_config_path=root / "codex.toml",
            )
            self.assertEqual(rc, 0)
        return root, calls

    def test_pr_flow_strict_grounding_fails_before_synth_and_writes_report(self) -> None:
        root, calls = self._run_pr_flow_with_grounding(grounding_mode="strict")
        try:
            session_dir = next((root / "sandboxes").iterdir())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            report = json.loads((session_dir / "work" / "grounding_report.json").read_text(encoding="utf-8"))
            self.assertEqual(calls, ["review.plan.md", "review.step-01.md"])
            self.assertEqual(meta["status"], "error")
            self.assertIn("step-01", report["invalid_artifacts"])
            self.assertFalse(report["artifacts"]["step-01"]["valid"])
            self.assertEqual(meta["multipass"]["validation"]["report_path"], str(session_dir / "work" / "grounding_report.json"))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_flow_warn_grounding_records_findings_and_completes(self) -> None:
        root, calls = self._run_pr_flow_with_grounding(grounding_mode="warn")
        try:
            session_dir = next((root / "sandboxes").iterdir())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            report = json.loads((session_dir / "work" / "grounding_report.json").read_text(encoding="utf-8"))
            self.assertEqual(calls, ["review.plan.md", "review.step-01.md", "review.md"])
            self.assertEqual(meta["status"], "done")
            self.assertTrue((session_dir / "review.md").is_file())
            self.assertIn("step-01", report["invalid_artifacts"])
            self.assertNotIn("synth", report["invalid_artifacts"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_flow_strict_grounding_rejects_step_only_synth_citations(self) -> None:
        root = ROOT / ".tmp_test_pr_synth_grounding"
        synth_markdown = "\n".join(
            [
                "### Steps taken",
                "- Read step output",
                "",
                "**Summary**: ok",
                "",
                "## Business / Product Assessment",
                "**Verdict**: APPROVE",
                "",
                "### Strengths",
                "- Business value is clear. Sources: `review.step-01.md:8`",
                "",
                "### In Scope Issues",
                "- None.",
                "",
                "### Out of Scope Issues",
                "- None.",
                "",
                "## Technical Assessment",
                "**Verdict**: REQUEST CHANGES",
                "",
                "### Strengths",
                "- Technical read happened. Sources: `review.step-01.md:8`",
                "",
                "### In Scope Issues",
                "- Missing provenance hygiene. Sources: `review.step-01.md:8`",
                "",
                "### Out of Scope Issues",
                "- None.",
                "",
                "### Reusability",
                "- Artifact stays inspectable. Sources: `review.step-01.md:8`",
                "",
            ]
        )
        with self.assertRaisesRegex(rf.ReviewflowError, "Multipass synth grounding validation failed"):
            self._run_pr_flow_with_synth_grounding(synth_markdown=synth_markdown)
        try:
            session_dir = next((root / "sandboxes").iterdir())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            report = json.loads((session_dir / "work" / "grounding_report.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["status"], "error")
            self.assertIn("synth", report["invalid_artifacts"])
            self.assertIn(
                "step-artifact citations alone are insufficient",
                "\n".join(report["artifacts"]["synth"]["errors"]),
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_flow_strict_grounding_accepts_primary_evidence_synth_citations(self) -> None:
        root, calls = self._run_pr_flow_with_synth_grounding(
            synth_markdown=self._valid_synth_markdown(primary_citation="work/pr-context.md:1")
        )
        try:
            session_dir = next((root / "sandboxes").iterdir())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            report = json.loads((session_dir / "work" / "grounding_report.json").read_text(encoding="utf-8"))
            self.assertEqual(calls, ["review.plan.md", "review.step-01.md", "review.md"])
            self.assertEqual(meta["status"], "done")
            self.assertNotIn("synth", report["invalid_artifacts"])
            self.assertTrue(report["artifacts"]["synth"]["valid"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_resume_flow_reruns_invalid_existing_step_artifact(self) -> None:
        root = ROOT / ".tmp_test_resume_grounding_rerun"
        cfg = root / "reviewflow.toml"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            base_cfg = root / "chunkhound-base.json"
            base_cfg.write_text("{}", encoding="utf-8")
            cfg.write_text(
                f"[chunkhound]\nbase_config_path = {json.dumps(str(base_cfg))}\n",
                encoding="utf-8",
            )
            session_dir = root / "session-1"
            repo_dir = session_dir / "repo"
            work_dir = session_dir / "work"
            chunkhound_dir = work_dir / "chunkhound"
            repo_dir.mkdir(parents=True, exist_ok=True)
            chunkhound_dir.mkdir(parents=True, exist_ok=True)
            (repo_dir / "src").mkdir(parents=True, exist_ok=True)
            (repo_dir / "src" / "app.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
            plan_json = work_dir / "review_plan.json"
            plan_json.parent.mkdir(parents=True, exist_ok=True)
            plan_json.write_text(
                json.dumps(
                    {
                        "abort": False,
                        "abort_reason": None,
                        "jira_keys": ["ABC-1"],
                        "steps": [{"id": "01", "title": "API review", "focus": "grounding"}],
                    }
                ),
                encoding="utf-8",
            )
            step_output = session_dir / "review.step-01.md"
            step_output.write_text(
                "\n".join(
                    [
                        "### Step Result: 01 — API review",
                        "**Focus**: grounding",
                        "",
                        "### Findings",
                        "- Missing provenance",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            review_md = session_dir / "review.md"
            review_md.write_text(self._valid_synth_markdown(primary_citation="src/app.py:2"), encoding="utf-8")
            invalid_step = rf.validate_multipass_step_grounding(
                artifact_path=step_output,
                repo_dir=repo_dir,
                step_index=1,
            )
            rf._update_grounding_state(
                meta={
                    "multipass": {
                        "enabled": True,
                        "grounding_mode": "strict",
                    }
                },
                work_dir=work_dir,
                grounding_mode="strict",
                result=invalid_step,
            )
            meta = {
                "session_id": "session-1",
                "status": "done",
                "created_at": "2026-03-10T00:00:00+00:00",
                "completed_at": "2026-03-10T01:00:00+00:00",
                "pr_url": "https://github.com/acme/repo/pull/9",
                "host": "github.com",
                "owner": "acme",
                "repo": "repo",
                "number": 9,
                "base_ref_for_review": "cure_base__main",
                "llm": {"provider": "openai", "capabilities": {"supports_resume": True}},
                "notes": {"no_index": False},
                "paths": {
                    "session_dir": str(session_dir),
                    "repo_dir": str(repo_dir),
                    "work_dir": str(work_dir),
                    "chunkhound_cwd": str(chunkhound_dir),
                    "chunkhound_db": str(chunkhound_dir / ".chunkhound.db"),
                    "chunkhound_config": str(chunkhound_dir / "chunkhound.json"),
                    "review_md": str(review_md),
                },
                "multipass": {
                    "enabled": True,
                    "plan_json_path": str(plan_json),
                    "grounding_mode": "strict",
                    "validation": {
                        "mode": "strict",
                        "invalid_artifacts": ["step-01"],
                        "has_invalid_artifacts": True,
                        "artifacts": {"step-01": invalid_step},
                        "report_path": str(work_dir / "grounding_report.json"),
                    },
                },
            }
            (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

            calls: list[str] = []

            def fake_run_llm_exec(**kwargs: object) -> rf.LlmRunResult:
                output_path = Path(str(kwargs["output_path"]))
                calls.append(output_path.name)
                if output_path.name == "review.step-01.md":
                    output_path.write_text(
                        "\n".join(
                            [
                                "### Step Result: 01 — API review",
                                "**Focus**: grounding",
                                "",
                                "### Steps taken",
                                "- checked repo",
                                "",
                                "### Findings",
                                "- Input lacks validation. Evidence: `src/app.py:2`",
                                "",
                                "### Suggested actions",
                                "- Add checks",
                                "",
                            ]
                        ),
                        encoding="utf-8",
                    )
                elif output_path.name == "review.md":
                    output_path.write_text(self._valid_synth_markdown(primary_citation="src/app.py:2"), encoding="utf-8")
                else:
                    raise AssertionError(f"unexpected output path: {output_path}")
                return rf.LlmRunResult(resume=None)

            args = argparse.Namespace(
                session_id="session-1",
                from_phase="auto",
                no_index=False,
                codex_model=None,
                codex_effort=None,
                codex_plan_effort=None,
                quiet=True,
                no_stream=True,
                ui="off",
                verbosity="normal",
            )
            paths = rf.ReviewflowPaths(sandbox_root=root, cache_root=root / "cache")

            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(rf, "ensure_review_config"))
                stack.enter_context(mock.patch.object(rf, "restore_session_chunkhound_db_from_baseline"))
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_chunkhound_runtime_config",
                        return_value=(
                            rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                            {"chunkhound": {"base_config_path": str(base_cfg)}},
                            {"indexing": {"exclude": []}},
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "materialize_chunkhound_env_config",
                        side_effect=self._fake_materialize_chunkhound_env_config,
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_review_intelligence_config",
                        return_value=(
                            _review_intelligence_cfg(),
                            _review_intelligence_meta(_review_intelligence_cfg()),
                        ),
                    )
                )
                stack.enter_context(mock.patch.object(rf, "require_builtin_review_intelligence"))
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "resolve_llm_config_from_args",
                        return_value=(
                            {"provider": "openai", "preset": "test-openai", "capabilities": {"supports_resume": True}},
                            {},
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "prepare_review_agent_runtime",
                        return_value={
                            "env": {},
                            "metadata": {},
                            "staged_paths": {},
                            "add_dirs": [],
                            "codex_config_overrides": [],
                        },
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_reviewflow_multipass_defaults",
                        return_value=(
                            {"enabled": True, "max_steps": 20, "grounding_mode": "strict"},
                            {"multipass": {"enabled": True, "max_steps": 20, "grounding_mode": "strict"}},
                        ),
                    )
                )
                stack.enter_context(mock.patch.object(rf, "_run_review_intelligence_preflight"))
                stack.enter_context(mock.patch.object(rf, "run_llm_exec", side_effect=fake_run_llm_exec))
                rc = rf.resume_flow(args, paths=paths, config_path=cfg, codex_base_config_path=cfg)

            self.assertEqual(rc, 0)
            self.assertEqual(calls, ["review.step-01.md", "review.md"])
            refreshed = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(refreshed["status"], "done")
            self.assertFalse(refreshed["multipass"]["validation"]["has_invalid_artifacts"])
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)


class ChunkHoundToolProofValidationTests(unittest.TestCase):
    def _write_event_payloads(self, *, root: Path, payloads: list[dict[str, object]]) -> dict[str, object]:
        logs_dir = root / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        events_path = logs_dir / "codex.events.jsonl"
        start = events_path.stat().st_size if events_path.exists() else 0
        with events_path.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(json.dumps(payload) for payload in payloads) + "\n")
        end = events_path.stat().st_size
        return {
            "codex_events_path": str(events_path),
            "codex_events_start_offset": start,
            "codex_events_end_offset": end,
        }

    def _write_codex_events(
        self,
        *,
        root: Path,
        tool_names: list[str],
        server: str = "chunkhound",
    ) -> dict[str, object]:
        payloads: list[dict[str, object]] = []
        if not tool_names:
            payloads.append({"type": "thread.started", "thread_id": "tool-proof-test"})
        for tool_name in tool_names:
            payloads.append(
                {
                    "type": "item.completed",
                    "item": {
                        "id": f"tool-{tool_name}",
                        "type": "mcp_tool_call",
                        "server": server,
                        "tool_name": tool_name,
                    },
                }
            )
        return self._write_event_payloads(root=root, payloads=payloads)

    def _write_helper_command_events(
        self,
        *,
        root: Path,
        commands: list[str],
        discovery_tool_names: list[str] | None = None,
        command: str | None = None,
        raw_outputs: dict[str, object] | None = None,
    ) -> dict[str, object]:
        helper_path = "/tmp/cure/work/bin/cure-chunkhound"
        payloads: list[dict[str, object]] = []
        for tool_name in discovery_tool_names or []:
            payloads.append(
                {
                    "type": "item.completed",
                    "item": {
                        "id": f"discovery-{tool_name}",
                        "type": "mcp_tool_call",
                        "server": "codex",
                        "tool_name": tool_name,
                    },
                }
            )
        for command_name in commands:
            if raw_outputs and command_name in raw_outputs:
                aggregated_output = raw_outputs[command_name]
            elif command_name == "preflight":
                aggregated_output = {
                    "ok": True,
                    "command": "preflight",
                    "available_tools": ["search", "code_research"],
                    "helper_path": helper_path,
                }
            else:
                query = "needle" if command_name == "search" else "cross-file question"
                tool_name = "search" if command_name == "search" else "code_research"
                result_text = "{\"results\": []}" if command_name == "search" else "SYNTH_OK"
                aggregated_output = {
                    "ok": True,
                    "command": command_name,
                    "tool_name": tool_name,
                    "query": query,
                    "helper_path": helper_path,
                    "result": {
                        "content": [{"type": "text", "text": result_text}],
                        "isError": False,
                    },
                }
            payloads.append(
                {
                    "type": "item.completed",
                    "item": {
                        "id": f"helper-{command_name}",
                        "type": "command_execution",
                        "command": command
                        or f'/bin/bash -lc \'"$CURE_CHUNKHOUND_HELPER" {command_name} "query"\'',
                        "aggregated_output": (
                            aggregated_output
                            if isinstance(aggregated_output, str)
                            else json.dumps(aggregated_output, indent=2)
                        ),
                        "exit_code": 0,
                        "status": "completed",
                    },
                }
            )
        return self._write_event_payloads(root=root, payloads=payloads)

    def test_validate_and_record_chunkhound_tool_proof_persists_report_and_meta(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_tool_proof_validation"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            work_dir = root / "work"
            work_dir.mkdir(parents=True, exist_ok=True)
            meta: dict[str, object] = {"chunkhound": {"base_config_path": "/tmp/base.json"}}

            report = rf.validate_and_record_codex_chunkhound_tool_proof(
                meta=meta,
                work_dir=work_dir,
                provider="codex",
                review_stage="singlepass_review",
                prompt_template_name="mrereview_gh_local.md",
                adapter_meta=self._write_codex_events(
                    root=root,
                    tool_names=["search", "list_mcp_resources", "code_research"],
                ),
            )

            persisted = json.loads((work_dir / "chunkhound_tool_validation.json").read_text(encoding="utf-8"))
            self.assertIsNotNone(report)
            assert report is not None
            self.assertTrue(report["valid"])
            self.assertEqual(report["ignored_discovery_calls"], ["list_mcp_resources"])
            self.assertEqual(report["observed_successful_calls"], ["search", "code_research"])
            self.assertEqual(report["observed_evidence_sources"], ["mcp_tool_call"])
            self.assertEqual(
                [detail["tool_name"] for detail in report["observed_successful_call_details"]],
                ["search", "code_research"],
            )
            self.assertTrue(meta["chunkhound"]["tool_validation"]["valid"])
            self.assertEqual(meta["chunkhound"]["tool_validation"]["evidence_sources"], ["mcp_tool_call"])
            self.assertEqual(persisted["runs"][0]["review_stage"], "singlepass_review")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_and_record_chunkhound_tool_proof_latest_valid_overrides_prior_failure(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_tool_proof_recovery"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            work_dir = root / "work"
            work_dir.mkdir(parents=True, exist_ok=True)
            meta: dict[str, object] = {"chunkhound": {"base_config_path": "/tmp/base.json"}}

            first = rf.validate_and_record_codex_chunkhound_tool_proof(
                meta=meta,
                work_dir=work_dir,
                provider="codex",
                review_stage="singlepass_review",
                prompt_template_name="mrereview_gh_local.md",
                adapter_meta=self._write_codex_events(
                    root=root,
                    tool_names=["list_mcp_resources"],
                ),
            )
            second = rf.validate_and_record_codex_chunkhound_tool_proof(
                meta=meta,
                work_dir=work_dir,
                provider="codex",
                review_stage="singlepass_review",
                prompt_template_name="mrereview_gh_local.md",
                adapter_meta=self._write_codex_events(
                    root=root,
                    tool_names=["search", "code_research"],
                ),
            )

            persisted = json.loads((work_dir / "chunkhound_tool_validation.json").read_text(encoding="utf-8"))
            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            assert first is not None
            assert second is not None
            self.assertFalse(first["valid"])
            self.assertTrue(second["valid"])
            self.assertTrue(persisted["valid"])
            self.assertEqual(len(persisted["runs"]), 2)
            self.assertTrue(meta["chunkhound"]["tool_validation"]["valid"])
            self.assertTrue(meta["chunkhound"]["tool_validation"]["latest_run_valid"])
            self.assertEqual(meta["chunkhound"]["tool_validation"]["run_count"], 2)
            self.assertEqual(meta["chunkhound"]["tool_validation"]["evidence_sources"], ["mcp_tool_call"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_detect_multipass_plan_abort_contradiction_matches_valid_plan_proof(self) -> None:
        root = ROOT / ".tmp_test_multipass_plan_abort_contradiction_match"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            work_dir = root / "work"
            work_dir.mkdir(parents=True, exist_ok=True)
            meta: dict[str, object] = {"chunkhound": {"base_config_path": "/tmp/base.json"}}

            report = rf.validate_and_record_codex_chunkhound_tool_proof(
                meta=meta,
                work_dir=work_dir,
                provider="codex",
                review_stage="multipass_plan",
                prompt_template_name="mrereview_gh_local_big_plan.md",
                adapter_meta=self._write_helper_command_events(
                    root=root,
                    commands=["search", "research"],
                ),
            )
            contradiction = rf.detect_multipass_plan_abort_contradiction(
                meta=meta,
                work_dir=work_dir,
                plan={
                    "abort": True,
                    "abort_reason": "Mandatory helper gate failed because research never completed.",
                    "steps": [],
                },
                plan_tool_report=report,
            )

            self.assertIsNotNone(contradiction)
            assert contradiction is not None
            self.assertEqual(contradiction["review_stage"], "multipass_plan")
            self.assertEqual(contradiction["tool_validation_source"], "live_plan_report")
            self.assertEqual(contradiction["validated_tools"], ["search", "code_research"])
            self.assertEqual(
                contradiction["matched_categories"],
                ["helper_failure", "missing_code_research", "helper_gate_failure"],
            )
            self.assertNotIn("missing_search", contradiction["matched_categories"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_detect_multipass_plan_abort_contradiction_ignores_unrelated_abort_reason(self) -> None:
        root = ROOT / ".tmp_test_multipass_plan_abort_contradiction_unrelated"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            work_dir = root / "work"
            work_dir.mkdir(parents=True, exist_ok=True)
            meta: dict[str, object] = {"chunkhound": {"base_config_path": "/tmp/base.json"}}

            report = rf.validate_and_record_codex_chunkhound_tool_proof(
                meta=meta,
                work_dir=work_dir,
                provider="codex",
                review_stage="multipass_plan",
                prompt_template_name="mrereview_gh_local_big_plan.md",
                adapter_meta=self._write_helper_command_events(
                    root=root,
                    commands=["search", "research"],
                ),
            )
            contradiction = rf.detect_multipass_plan_abort_contradiction(
                meta=meta,
                work_dir=work_dir,
                plan={
                    "abort": True,
                    "abort_reason": "missing required Jira context",
                    "steps": [],
                },
                plan_tool_report=report,
            )

            self.assertIsNone(contradiction)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_detect_multipass_plan_abort_contradiction_uses_persisted_plan_stage_proof(self) -> None:
        root = ROOT / ".tmp_test_multipass_plan_abort_contradiction_persisted"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            work_dir = root / "work"
            work_dir.mkdir(parents=True, exist_ok=True)
            meta: dict[str, object] = {"chunkhound": {"base_config_path": "/tmp/base.json"}}

            rf.validate_and_record_codex_chunkhound_tool_proof(
                meta=meta,
                work_dir=work_dir,
                provider="codex",
                review_stage="multipass_plan",
                prompt_template_name="mrereview_gh_local_big_plan.md",
                adapter_meta=self._write_helper_command_events(
                    root=root,
                    commands=["search", "research"],
                ),
            )
            rf.validate_and_record_codex_chunkhound_tool_proof(
                meta=meta,
                work_dir=work_dir,
                provider="codex",
                review_stage="multipass_step",
                prompt_template_name="mrereview_gh_local_big_step.md",
                adapter_meta=self._write_helper_command_events(
                    root=root,
                    commands=["search"],
                ),
            )

            contradiction = rf.detect_multipass_plan_abort_contradiction(
                meta=meta,
                work_dir=work_dir,
                plan={
                    "abort": True,
                    "abort_reason": "ChunkHound helper failed and no plan steps could be emitted because research never completed.",
                    "steps": [],
                },
                plan_tool_report=None,
            )

            self.assertIsNotNone(contradiction)
            assert contradiction is not None
            self.assertEqual(contradiction["tool_validation_source"], "persisted_plan_report")
            self.assertEqual(contradiction["tool_validation_run_index"], 0)
            self.assertIn("helper_gate_failure", contradiction["matched_categories"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_chunkhound_tool_proof_ignores_discovery_only_runs(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_tool_proof_discovery_only"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            report = rf.validate_codex_chunkhound_tool_proof(
                provider="codex",
                review_stage="multipass_plan",
                prompt_template_name="mrereview_gh_local_big_plan.md",
                adapter_meta=self._write_codex_events(
                    root=root,
                    tool_names=["list_mcp_resources", "list_mcp_resource_templates"],
                ),
            )

            self.assertIsNotNone(report)
            assert report is not None
            self.assertFalse(report["valid"])
            self.assertEqual(
                report["ignored_discovery_calls"],
                ["list_mcp_resources", "list_mcp_resource_templates"],
            )
            self.assertIn("search", str(report["failure_reason"]))
            self.assertIn("code_research", str(report["failure_reason"]))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_chunkhound_tool_proof_accepts_native_codex_server_events(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_tool_proof_codex_server"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            report = rf.validate_codex_chunkhound_tool_proof(
                provider="codex",
                review_stage="singlepass_review",
                prompt_template_name="mrereview_gh_local.md",
                adapter_meta=self._write_codex_events(
                    root=root,
                    tool_names=["search", "code_research"],
                    server="codex",
                ),
            )

            self.assertIsNotNone(report)
            assert report is not None
            self.assertTrue(report["valid"])
            self.assertEqual(report["observed_evidence_sources"], ["mcp_tool_call"])
            self.assertEqual(
                [detail["server"] for detail in report["observed_successful_call_details"]],
                ["codex", "codex"],
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_chunkhound_tool_proof_accepts_helper_command_execution(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_helper_tool_proof_success"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            report = rf.validate_codex_chunkhound_tool_proof(
                provider="codex",
                review_stage="multipass_plan",
                prompt_template_name="mrereview_gh_local_big_plan.md",
                adapter_meta=self._write_helper_command_events(
                    root=root,
                    commands=["search", "research"],
                ),
            )

            self.assertIsNotNone(report)
            assert report is not None
            self.assertTrue(report["valid"])
            self.assertEqual(report["observed_successful_calls"], ["search", "code_research"])
            self.assertEqual(report["observed_evidence_sources"], ["cli_helper_command_execution"])
            self.assertEqual(
                [detail["evidence_source"] for detail in report["observed_successful_call_details"]],
                ["cli_helper_command_execution", "cli_helper_command_execution"],
            )
            self.assertTrue(
                all(
                    "CURE_CHUNKHOUND_HELPER" in str(detail["command_excerpt"])
                    for detail in report["observed_successful_call_details"]
                )
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_chunkhound_tool_proof_accepts_cli_shaped_helper_results(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_helper_tool_proof_cli_payloads"
        helper_path = "/tmp/cure/work/bin/cure-chunkhound"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            report = rf.validate_codex_chunkhound_tool_proof(
                provider="codex",
                review_stage="multipass_plan",
                prompt_template_name="mrereview_gh_local_big_plan.md",
                adapter_meta=self._write_helper_command_events(
                    root=root,
                    commands=["search", "research"],
                    raw_outputs={
                        "search": {
                            "ok": True,
                            "command": "search",
                            "tool_name": "search",
                            "query": "needle",
                            "helper_path": helper_path,
                            "result": {
                                "results": [],
                                "pagination": {"offset": 0, "total_results": 0},
                            },
                            "execution_stage": "tools/call",
                            "execution_stage_status": "ok",
                        },
                        "research": {
                            "ok": True,
                            "command": "research",
                            "tool_name": "code_research",
                            "query": "cross-file question",
                            "helper_path": helper_path,
                            "result": {"summary": "grounded answer"},
                            "execution_stage": "tools/call",
                            "execution_stage_status": "ok",
                        },
                    },
                ),
            )

            self.assertIsNotNone(report)
            assert report is not None
            self.assertTrue(report["valid"])
            self.assertEqual(report["observed_successful_calls"], ["search", "code_research"])
            self.assertEqual(report["observed_failed_call_details"], [])
            self.assertEqual(report["observed_evidence_sources"], ["cli_helper_command_execution"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_chunkhound_tool_proof_mixed_discovery_and_helper_execution_passes(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_helper_tool_proof_mixed"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            report = rf.validate_codex_chunkhound_tool_proof(
                provider="codex",
                review_stage="multipass_plan",
                prompt_template_name="mrereview_gh_local_big_plan.md",
                adapter_meta=self._write_helper_command_events(
                    root=root,
                    commands=["search", "research"],
                    discovery_tool_names=["list_mcp_resources", "list_mcp_resource_templates"],
                ),
            )

            self.assertIsNotNone(report)
            assert report is not None
            self.assertTrue(report["valid"])
            self.assertEqual(
                report["ignored_discovery_calls"],
                ["list_mcp_resources", "list_mcp_resource_templates"],
            )
            self.assertEqual(report["observed_evidence_sources"], ["cli_helper_command_execution"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_chunkhound_tool_proof_malformed_helper_json_fails_closed(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_helper_tool_proof_bad_json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            report = rf.validate_codex_chunkhound_tool_proof(
                provider="codex",
                review_stage="multipass_plan",
                prompt_template_name="mrereview_gh_local_big_plan.md",
                adapter_meta=self._write_helper_command_events(
                    root=root,
                    commands=["search"],
                    raw_outputs={"search": "not-json\n"},
                ),
            )

            self.assertIsNotNone(report)
            assert report is not None
            self.assertFalse(report["valid"])
            self.assertEqual(report["observed_successful_calls"], [])
            self.assertEqual(report["observed_evidence_sources"], [])
            self.assertIn("code_research", str(report["failure_reason"]))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_chunkhound_tool_proof_helper_ok_false_fails_closed(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_helper_tool_proof_ok_false"
        helper_path = "/tmp/cure/work/bin/cure-chunkhound"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            report = rf.validate_codex_chunkhound_tool_proof(
                provider="codex",
                review_stage="multipass_plan",
                prompt_template_name="mrereview_gh_local_big_plan.md",
                adapter_meta=self._write_helper_command_events(
                    root=root,
                    commands=["search", "research"],
                    raw_outputs={
                        "search": {
                            "ok": False,
                            "command": "search",
                            "tool_name": "search",
                            "query": "needle",
                            "helper_path": helper_path,
                            "error": "helper search failed",
                            "execution_stage": "tools/call",
                            "execution_stage_status": "error",
                            "execution_timeout_seconds": 15.0,
                        },
                        "research": {
                            "ok": True,
                            "command": "research",
                            "tool_name": "code_research",
                            "query": "cross-file question",
                            "helper_path": helper_path,
                            "result": {"summary": "grounded answer"},
                        },
                    },
                ),
            )

            self.assertIsNotNone(report)
            assert report is not None
            self.assertFalse(report["valid"])
            self.assertEqual(report["observed_successful_calls"], ["code_research"])
            self.assertEqual(report["observed_failed_call_details"][0]["tool_name"], "search")
            self.assertEqual(report["observed_failed_call_details"][0]["stage"], "tools/call")
            self.assertIn("search failed during tools/call (error)", str(report["failure_reason"]))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_chunkhound_tool_proof_helper_missing_result_fails_closed(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_helper_tool_proof_missing_result"
        helper_path = "/tmp/cure/work/bin/cure-chunkhound"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            report = rf.validate_codex_chunkhound_tool_proof(
                provider="codex",
                review_stage="multipass_plan",
                prompt_template_name="mrereview_gh_local_big_plan.md",
                adapter_meta=self._write_helper_command_events(
                    root=root,
                    commands=["search", "research"],
                    raw_outputs={
                        "search": {
                            "ok": True,
                            "command": "search",
                            "tool_name": "search",
                            "query": "needle",
                            "helper_path": helper_path,
                        },
                        "research": {
                            "ok": True,
                            "command": "research",
                            "tool_name": "code_research",
                            "query": "cross-file question",
                            "helper_path": helper_path,
                            "result": {"summary": "grounded answer"},
                        },
                    },
                ),
            )

            self.assertIsNotNone(report)
            assert report is not None
            self.assertFalse(report["valid"])
            self.assertEqual(report["observed_successful_calls"], ["code_research"])
            self.assertIn("search", str(report["failure_reason"]))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_chunkhound_tool_proof_search_metadata_only_result_fails_closed(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_helper_tool_proof_search_metadata_only"
        helper_path = "/tmp/cure/work/bin/cure-chunkhound"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            report = rf.validate_codex_chunkhound_tool_proof(
                provider="codex",
                review_stage="multipass_plan",
                prompt_template_name="mrereview_gh_local_big_plan.md",
                adapter_meta=self._write_helper_command_events(
                    root=root,
                    commands=["search", "research"],
                    raw_outputs={
                        "search": {
                            "ok": True,
                            "command": "search",
                            "tool_name": "search",
                            "query": "needle",
                            "helper_path": helper_path,
                            "result": {
                                "pagination": {"offset": 0, "total_results": 0},
                            },
                        },
                        "research": {
                            "ok": True,
                            "command": "research",
                            "tool_name": "code_research",
                            "query": "cross-file question",
                            "helper_path": helper_path,
                            "result": {"summary": "grounded answer"},
                        },
                    },
                ),
            )

            self.assertIsNotNone(report)
            assert report is not None
            self.assertFalse(report["valid"])
            self.assertEqual(report["observed_successful_calls"], ["code_research"])
            self.assertEqual(report["observed_failed_call_details"][0]["tool_name"], "search")
            self.assertIn("search", str(report["failure_reason"]))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_chunkhound_tool_proof_research_metadata_only_result_fails_closed(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_helper_tool_proof_research_metadata_only"
        helper_path = "/tmp/cure/work/bin/cure-chunkhound"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            report = rf.validate_codex_chunkhound_tool_proof(
                provider="codex",
                review_stage="multipass_plan",
                prompt_template_name="mrereview_gh_local_big_plan.md",
                adapter_meta=self._write_helper_command_events(
                    root=root,
                    commands=["search", "research"],
                    raw_outputs={
                        "search": {
                            "ok": True,
                            "command": "search",
                            "tool_name": "search",
                            "query": "needle",
                            "helper_path": helper_path,
                            "result": {
                                "results": [],
                                "pagination": {"offset": 0, "total_results": 0},
                            },
                        },
                        "research": {
                            "ok": True,
                            "command": "research",
                            "tool_name": "code_research",
                            "query": "cross-file question",
                            "helper_path": helper_path,
                            "result": {"metadata": {"tokens": 17}},
                        },
                    },
                ),
            )

            self.assertIsNotNone(report)
            assert report is not None
            self.assertFalse(report["valid"])
            self.assertEqual(report["observed_successful_calls"], ["search"])
            self.assertEqual(report["observed_failed_call_details"][0]["tool_name"], "code_research")
            self.assertIn("code_research", str(report["failure_reason"]))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_chunkhound_tool_proof_reports_tools_call_timeout_diagnostics(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_helper_tool_proof_timeout_diagnostics"
        helper_path = "/tmp/cure/work/bin/cure-chunkhound"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            report = rf.validate_codex_chunkhound_tool_proof(
                provider="codex",
                review_stage="multipass_plan",
                prompt_template_name="mrereview_gh_local_big_plan.md",
                adapter_meta=self._write_helper_command_events(
                    root=root,
                    commands=["search", "research"],
                    raw_outputs={
                        "search": {
                            "ok": True,
                            "command": "search",
                            "tool_name": "search",
                            "query": "needle",
                            "helper_path": helper_path,
                            "result": {
                                "results": [],
                                "pagination": {"offset": 0, "total_results": 0},
                            },
                            "execution_stage": "tools/call",
                            "execution_stage_status": "ok",
                        },
                        "research": {
                            "ok": False,
                            "command": "research",
                            "tool_name": "code_research",
                            "query": "cross-file question",
                            "helper_path": helper_path,
                            "error": "timed out after 1200.0s waiting for stage tools/call",
                            "execution_stage": "tools/call",
                            "execution_stage_status": "timeout",
                            "execution_timeout_seconds": 1200.0,
                        },
                    },
                ),
            )

            self.assertIsNotNone(report)
            assert report is not None
            self.assertFalse(report["valid"])
            self.assertEqual(report["observed_successful_calls"], ["search"])
            self.assertEqual(report["observed_failed_call_details"][0]["tool_name"], "code_research")
            self.assertEqual(report["observed_failed_call_details"][0]["stage_status"], "timeout")
            self.assertIn(
                "code_research failed during tools/call (timeout) after 1200.0s",
                str(report["failure_reason"]),
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_chunkhound_tool_proof_preflight_only_does_not_count(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_helper_tool_proof_preflight_only"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            report = rf.validate_codex_chunkhound_tool_proof(
                provider="codex",
                review_stage="singlepass_review",
                prompt_template_name="mrereview_gh_local.md",
                adapter_meta=self._write_helper_command_events(
                    root=root,
                    commands=["preflight"],
                ),
            )

            self.assertIsNotNone(report)
            assert report is not None
            self.assertFalse(report["valid"])
            self.assertEqual(report["observed_successful_calls"], [])
            self.assertEqual(report["observed_evidence_sources"], [])
            self.assertIn("search", str(report["failure_reason"]))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_chunkhound_tool_proof_incomplete_helper_execution_fails_closed(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_helper_tool_proof_incomplete"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            report = rf.validate_codex_chunkhound_tool_proof(
                provider="codex",
                review_stage="multipass_plan",
                prompt_template_name="mrereview_gh_local_big_plan.md",
                adapter_meta=self._write_helper_command_events(
                    root=root,
                    commands=["search"],
                ),
            )

            self.assertIsNotNone(report)
            assert report is not None
            self.assertFalse(report["valid"])
            self.assertEqual(report["observed_successful_calls"], ["search"])
            self.assertEqual(report["observed_evidence_sources"], ["cli_helper_command_execution"])
            self.assertIn("code_research", str(report["failure_reason"]))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_chunkhound_tool_proof_plain_chunkhound_shell_command_does_not_count(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_helper_tool_proof_wrong_command"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            report = rf.validate_codex_chunkhound_tool_proof(
                provider="codex",
                review_stage="singlepass_review",
                prompt_template_name="mrereview_gh_local.md",
                adapter_meta=self._write_helper_command_events(
                    root=root,
                    commands=["search", "research"],
                    command="/bin/bash -lc 'chunkhound search needle'",
                ),
            )

            self.assertIsNotNone(report)
            assert report is not None
            self.assertFalse(report["valid"])
            self.assertEqual(report["observed_successful_calls"], [])
            self.assertEqual(report["observed_evidence_sources"], [])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_chunkhound_tool_proof_same_name_wrapper_does_not_count(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_helper_tool_proof_same_name_wrapper"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            report = rf.validate_codex_chunkhound_tool_proof(
                provider="codex",
                review_stage="singlepass_review",
                prompt_template_name="mrereview_gh_local.md",
                adapter_meta=self._write_helper_command_events(
                    root=root,
                    commands=["search", "research"],
                    command="/bin/bash -lc '/tmp/other/cure-chunkhound search needle'",
                ),
            )

            self.assertIsNotNone(report)
            assert report is not None
            self.assertFalse(report["valid"])
            self.assertEqual(report["observed_successful_calls"], [])
            self.assertEqual(report["observed_evidence_sources"], [])
        finally:
            shutil.rmtree(root, ignore_errors=True)


class CodexToolProofFlowTests(unittest.TestCase):
    def _fake_run_cmd(self, *, seed: Path) -> object:
        class _Result:
            def __init__(self, stdout: str = "") -> None:
                self.stdout = stdout
                self.stderr = ""
                self.duration_seconds = 0.0

        def runner(cmd: list[str], **kwargs: object) -> _Result:
            if cmd[:2] == ["git", "clone"]:
                Path(str(cmd[-1])).mkdir(parents=True, exist_ok=True)
                return _Result()
            if cmd[:5] == ["git", "-C", str(seed), "remote", "get-url"]:
                return _Result("https://github.com/acme/repo.git\n")
            if cmd[:4] == ["git", "-C", str(seed), "rev-parse"]:
                return _Result("true\n")
            if cmd[:4] == ["git", "-C", str(Path(str(cmd[2]))), "rev-parse"]:
                return _Result("deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n")
            if cmd[:3] == ["gh", "pr", "checkout"]:
                return _Result()
            if cmd and cmd[0] in {"git", "rsync", "chunkhound"}:
                return _Result()
            raise AssertionError(f"unexpected command: {cmd}")

        return runner

    def _fake_materialize_chunkhound_env_config(
        self,
        *,
        resolved_config: dict[str, object],
        output_config_path: Path,
        database_provider: str,
        database_path: Path,
    ) -> None:
        output_config_path.parent.mkdir(parents=True, exist_ok=True)
        output_config_path.write_text("{}", encoding="utf-8")
        database_path.parent.mkdir(parents=True, exist_ok=True)

    def _fake_write_pr_context_file(
        self,
        *,
        work_dir: Path,
        pr: rf.PullRequestRef,
        pr_meta: dict[str, object],
    ) -> Path:
        context_path = work_dir / "pr-context.md"
        context_path.write_text("context", encoding="utf-8")
        return context_path

    def _codex_runtime_policy(self) -> dict[str, object]:
        return {
            "env": {},
            "metadata": {},
            "staged_paths": {},
            "add_dirs": [],
            "codex_config_overrides": [],
            "codex_flags": [],
            "dangerously_bypass_approvals_and_sandbox": True,
        }

    def _write_event_payloads(self, *, work_dir: Path, payloads: list[dict[str, object]]) -> dict[str, object]:
        logs_dir = work_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        events_path = logs_dir / "codex.events.jsonl"
        start = events_path.stat().st_size if events_path.exists() else 0
        with events_path.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(json.dumps(payload) for payload in payloads) + "\n")
        end = events_path.stat().st_size
        return {
            "codex_events_path": str(events_path),
            "codex_events_start_offset": start,
            "codex_events_end_offset": end,
        }

    def _write_codex_events(
        self,
        *,
        work_dir: Path,
        tool_names: list[str],
        server: str = "chunkhound",
    ) -> dict[str, object]:
        payloads: list[dict[str, object]] = []
        if not tool_names:
            payloads.append({"type": "thread.started", "thread_id": "tool-proof-test"})
        for tool_name in tool_names:
            payloads.append(
                {
                    "type": "item.completed",
                    "item": {
                        "id": f"tool-{tool_name}",
                        "type": "mcp_tool_call",
                        "server": server,
                        "tool_name": tool_name,
                    },
                }
            )
        return self._write_event_payloads(work_dir=work_dir, payloads=payloads)

    def _write_helper_command_events(
        self,
        *,
        work_dir: Path,
        commands: list[str],
        command: str | None = None,
        raw_outputs: dict[str, object] | None = None,
    ) -> dict[str, object]:
        helper_path = "/tmp/cure/work/bin/cure-chunkhound"
        payloads: list[dict[str, object]] = []
        for command_name in commands:
            if raw_outputs and command_name in raw_outputs:
                payload = raw_outputs[command_name]
            elif command_name == "preflight":
                payload = {
                    "ok": True,
                    "command": "preflight",
                    "available_tools": ["search", "code_research"],
                    "helper_path": helper_path,
                }
            else:
                query = "tool proof" if command_name == "search" else "flow proof"
                tool_name = "search" if command_name == "search" else "code_research"
                result_text = "{\"results\": []}" if command_name == "search" else "SYNTH_OK"
                payload = {
                    "ok": True,
                    "command": command_name,
                    "tool_name": tool_name,
                    "query": query,
                    "helper_path": helper_path,
                    "result": {
                        "content": [{"type": "text", "text": result_text}],
                        "isError": False,
                    },
                }
            payloads.append(
                {
                    "type": "item.completed",
                    "item": {
                        "id": f"helper-{command_name}",
                        "type": "command_execution",
                        "command": command
                        or f'/bin/bash -lc \'"$CURE_CHUNKHOUND_HELPER" {command_name} "query"\'',
                        "aggregated_output": json.dumps(payload, indent=2),
                        "exit_code": 0,
                        "status": "completed",
                    },
                }
            )
        return self._write_event_payloads(work_dir=work_dir, payloads=payloads)

    def _run_pr_flow_for_tool_proof(
        self,
        *,
        root: Path,
        profile_resolved: str,
        multipass_enabled: bool,
        step_workers: int = 4,
        llm_side_effect: Any,
        expect_error: str | None = None,
        helper_preflight_side_effect: Any | None = None,
        multipass_defaults_override: dict[str, object] | None = None,
        llm_resolved_override: dict[str, object] | None = None,
        llm_resolution_meta_override: dict[str, object] | None = None,
        runtime_policy_override: dict[str, object] | None = None,
    ) -> tuple[Path, list[str]]:
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        sandbox_root = root / "sandboxes"
        cache_root = root / "cache"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        cache_root.mkdir(parents=True, exist_ok=True)
        seed = root / "seed"
        seed.mkdir(parents=True, exist_ok=True)
        base_db = root / "base.chunkhound.db"
        base_db.write_text("db", encoding="utf-8")
        base_cfg = root / "chunkhound-base.json"
        base_cfg.write_text("{}", encoding="utf-8")
        config_path = root / "reviewflow.toml"
        config_path.write_text(
            f"[chunkhound]\nbase_config_path = {json.dumps(str(base_cfg))}\n",
            encoding="utf-8",
        )
        paths = rf.ReviewflowPaths(sandbox_root=sandbox_root, cache_root=cache_root)
        args = rf.build_parser().parse_args(
            [
                "pr",
                "https://github.com/acme/repo/pull/14",
                "--if-reviewed",
                "new",
                "--ui",
                "off",
                "--quiet",
                "--no-stream",
            ]
        )
        calls: list[str] = []
        llm_param_count = len(inspect.signature(llm_side_effect).parameters)
        multipass_defaults = (
            dict(multipass_defaults_override)
            if isinstance(multipass_defaults_override, dict)
            else {
                "enabled": multipass_enabled,
                "max_steps": 20,
                "step_workers": step_workers,
                "grounding_mode": "off",
            }
        )
        llm_resolved = (
            dict(llm_resolved_override)
            if isinstance(llm_resolved_override, dict)
            else {"provider": "codex", "preset": "test-codex"}
        )
        llm_resolution_meta = (
            dict(llm_resolution_meta_override)
            if isinstance(llm_resolution_meta_override, dict)
            else {}
        )
        runtime_policy = (
            dict(runtime_policy_override)
            if isinstance(runtime_policy_override, dict)
            else self._codex_runtime_policy()
        )

        def fake_copy_duckdb_files(src: Path, dest: Path) -> None:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

        def fake_run_llm_exec(**kwargs: object) -> rf.LlmRunResult:
            output_path = Path(str(kwargs["output_path"]))
            calls.append(output_path.name)
            work_dir = Path(str(kwargs["repo_dir"])).parent / "work"
            if llm_param_count >= 3:
                return llm_side_effect(output_path, work_dir, kwargs)
            return llm_side_effect(output_path, work_dir)

        with contextlib.ExitStack() as stack:
            fake_run_cmd = self._fake_run_cmd(seed=seed)
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "gh_api_json",
                    return_value={
                        "base": {"ref": "main"},
                        "head": {"sha": "1111111111111111111111111111111111111111"},
                        "title": "Tool proof PR",
                    },
                )
            )
            stack.enter_context(mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[]))
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                        {"chunkhound": {"base_config_path": str(base_cfg)}},
                        {"indexing": {"exclude": []}},
                    ),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "materialize_chunkhound_env_config",
                    side_effect=self._fake_materialize_chunkhound_env_config,
                )
            )
            stack.enter_context(
                mock.patch.object(rf, "write_pr_context_file", side_effect=self._fake_write_pr_context_file)
            )
            stack.enter_context(mock.patch.object(rf, "ensure_base_cache", return_value={"db_path": str(base_db)}))
            stack.enter_context(mock.patch.object(rf, "seed_dir", return_value=seed))
            stack.enter_context(mock.patch.object(rf, "ensure_clean_git_worktree"))
            stack.enter_context(mock.patch.object(rf, "same_device", return_value=True))
            stack.enter_context(mock.patch.object(rf, "copy_duckdb_files", side_effect=fake_copy_duckdb_files))
            stack.enter_context(mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd))
            stack.enter_context(
                mock.patch.object(
                    rf.ReviewflowOutput,
                    "run_logged_cmd",
                    autospec=True,
                    side_effect=lambda output, cmd, **kwargs: fake_run_cmd(cmd, **kwargs),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "load_review_intelligence_config",
                    return_value=(
                        _review_intelligence_cfg(),
                        _review_intelligence_meta(_review_intelligence_cfg()),
                    ),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "load_reviewflow_multipass_defaults",
                    return_value=(
                        multipass_defaults,
                        {"multipass": dict(multipass_defaults)},
                    ),
                )
            )
            stack.enter_context(
                mock.patch.object(rf, "resolve_prompt_profile", return_value=(profile_resolved, "forced:test"))
            )
            stack.enter_context(mock.patch.object(rf, "require_builtin_review_intelligence"))
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "resolve_llm_config_from_args",
                    return_value=(llm_resolved, llm_resolution_meta),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    rf,
                    "prepare_review_agent_runtime",
                    return_value=runtime_policy,
                )
            )
            if helper_preflight_side_effect is None:
                stack.enter_context(
                    mock.patch.object(rf, "_run_chunkhound_access_preflight", return_value=None)
                )
            else:
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "_run_chunkhound_access_preflight",
                        side_effect=helper_preflight_side_effect,
                    )
                )
            stack.enter_context(mock.patch.object(rf, "_run_review_intelligence_preflight"))
            stack.enter_context(mock.patch.object(rf, "run_llm_exec", side_effect=fake_run_llm_exec))
            if expect_error is not None:
                with self.assertRaisesRegex(rf.ReviewflowError, expect_error):
                    rf.pr_flow(
                        args,
                        paths=paths,
                        config_path=config_path,
                        codex_base_config_path=root / "codex.toml",
                    )
            else:
                rc = rf.pr_flow(
                    args,
                    paths=paths,
                    config_path=config_path,
                    codex_base_config_path=root / "codex.toml",
                )
                self.assertEqual(rc, 0)
        return root, calls

    def test_pr_flow_codex_plain_chunkhound_execution_aborts_plan_without_singlepass_fallback(self) -> None:
        root = ROOT / ".tmp_test_codex_tool_proof_plan_failure"

        def llm_side_effect(output_path: Path, work_dir: Path) -> rf.LlmRunResult:
            output_path.write_text(
                "\n".join(
                    [
                        "### Plan JSON",
                        "```json",
                        json.dumps(
                            {
                                "abort": False,
                                "abort_reason": None,
                                "jira_keys": [],
                                "steps": [{"id": "01", "title": "API review", "focus": "tool proof"}],
                            }
                        ),
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            adapter_meta = self._write_helper_command_events(
                work_dir=work_dir,
                commands=["search", "research"],
                command="/bin/bash -lc 'chunkhound search needle'",
            )
            return rf.LlmRunResult(resume=None, adapter_meta=adapter_meta)

        root, calls = self._run_pr_flow_for_tool_proof(
            root=root,
            profile_resolved="big",
            multipass_enabled=True,
            llm_side_effect=llm_side_effect,
            expect_error="ChunkHound tool proof failed for multipass plan",
        )
        try:
            session_dir = next((root / "sandboxes").iterdir())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            report = json.loads((session_dir / "work" / "chunkhound_tool_validation.json").read_text(encoding="utf-8"))
            self.assertEqual(calls, ["review.plan.md"])
            self.assertEqual(meta["status"], "error")
            self.assertNotEqual(meta["multipass"]["mode"], "fallback_singlepass")
            self.assertEqual(report["runs"][0]["observed_successful_calls"], [])
            self.assertEqual(report["runs"][0]["observed_evidence_sources"], [])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_flow_codex_helper_execution_incomplete_plan_proof_aborts(self) -> None:
        root = ROOT / ".tmp_test_codex_helper_tool_proof_plan_failure"

        def llm_side_effect(output_path: Path, work_dir: Path) -> rf.LlmRunResult:
            output_path.write_text(
                "\n".join(
                    [
                        "### Plan JSON",
                        "```json",
                        json.dumps(
                            {
                                "abort": False,
                                "abort_reason": None,
                                "jira_keys": [],
                                "steps": [{"id": "01", "title": "API review", "focus": "tool proof"}],
                            }
                        ),
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            adapter_meta = self._write_helper_command_events(
                work_dir=work_dir,
                commands=["search"],
            )
            return rf.LlmRunResult(resume=None, adapter_meta=adapter_meta)

        root, calls = self._run_pr_flow_for_tool_proof(
            root=root,
            profile_resolved="big",
            multipass_enabled=True,
            llm_side_effect=llm_side_effect,
            expect_error="ChunkHound tool proof failed for multipass plan",
        )
        try:
            session_dir = next((root / "sandboxes").iterdir())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            report = json.loads((session_dir / "work" / "chunkhound_tool_validation.json").read_text(encoding="utf-8"))
            self.assertEqual(calls, ["review.plan.md"])
            self.assertEqual(meta["status"], "error")
            self.assertNotEqual(meta["multipass"]["mode"], "fallback_singlepass")
            self.assertEqual(report["runs"][0]["observed_successful_calls"], ["search"])
            self.assertEqual(report["runs"][0]["observed_evidence_sources"], ["cli_helper_command_execution"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_flow_codex_helper_cli_shaped_search_proof_allows_multipass_completion(self) -> None:
        root = ROOT / ".tmp_test_codex_helper_cli_search_multipass"
        helper_path = "/tmp/cure/work/bin/cure-chunkhound"

        def llm_side_effect(output_path: Path, work_dir: Path) -> rf.LlmRunResult:
            if output_path.name == "review.plan.md":
                output_path.write_text(
                    "\n".join(
                        [
                            "### Plan JSON",
                            "```json",
                            json.dumps(
                                {
                                    "abort": False,
                                    "abort_reason": None,
                                    "jira_keys": ["ABC-1"],
                                    "steps": [{"id": "01", "title": "API review", "focus": "tool proof"}],
                                }
                            ),
                            "```",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                adapter_meta = self._write_helper_command_events(
                    work_dir=work_dir,
                    commands=["search", "research"],
                    raw_outputs={
                        "search": {
                            "ok": True,
                            "command": "search",
                            "tool_name": "search",
                            "query": "tool proof",
                            "helper_path": helper_path,
                            "result": {
                                "results": [],
                                "pagination": {"offset": 0, "total_results": 0},
                            },
                            "execution_stage": "tools/call",
                            "execution_stage_status": "ok",
                        },
                        "research": {
                            "ok": True,
                            "command": "research",
                            "tool_name": "code_research",
                            "query": "flow proof",
                            "helper_path": helper_path,
                            "result": {"summary": "grounded answer"},
                            "execution_stage": "tools/call",
                            "execution_stage_status": "ok",
                        },
                    },
                )
            elif output_path.name == "review.step-01.md":
                output_path.write_text(
                    "\n".join(
                        [
                            "### Step Result: 01 — API review",
                            "**Focus**: tool proof",
                            "",
                            "### Steps taken",
                            "- checked repo",
                            "",
                            "### Findings",
                            "- Input lacks validation. Evidence: `src/app.py:2`",
                            "",
                            "### Suggested actions",
                            "- Add checks",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                adapter_meta = self._write_helper_command_events(
                    work_dir=work_dir,
                    commands=["search", "research"],
                )
            elif output_path.name == "review.md":
                output_path.write_text(
                    _sectioned_review_markdown(business="APPROVE", technical="REQUEST CHANGES"),
                    encoding="utf-8",
                )
                adapter_meta = self._write_helper_command_events(
                    work_dir=work_dir,
                    commands=["search", "research"],
                )
            else:
                raise AssertionError(f"unexpected output path: {output_path}")
            return rf.LlmRunResult(resume=None, adapter_meta=adapter_meta)

        root, calls = self._run_pr_flow_for_tool_proof(
            root=root,
            profile_resolved="big",
            multipass_enabled=True,
            llm_side_effect=llm_side_effect,
        )
        try:
            session_dir = next((root / "sandboxes").iterdir())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            report = json.loads((session_dir / "work" / "chunkhound_tool_validation.json").read_text(encoding="utf-8"))
            review_md = (session_dir / "review.md").read_text(encoding="utf-8")
            self.assertEqual(calls, ["review.plan.md", "review.step-01.md", "review.md"])
            self.assertEqual(meta["status"], "done")
            self.assertTrue(meta["chunkhound"]["tool_validation"]["valid"])
            self.assertEqual(report["runs"][0]["observed_successful_calls"], ["search", "code_research"])
            self.assertEqual(report["runs"][0]["observed_evidence_sources"], ["cli_helper_command_execution"])
            self.assertIn("<!-- CURE_REVIEW_FOOTER_START -->", review_md)
            self.assertIn("session ", review_md)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_flow_codex_tool_proof_success_allows_singlepass_completion(self) -> None:
        root = ROOT / ".tmp_test_codex_tool_proof_singlepass"

        def llm_side_effect(output_path: Path, work_dir: Path) -> rf.LlmRunResult:
            output_path.write_text(
                _sectioned_review_markdown(business="APPROVE", technical="APPROVE"),
                encoding="utf-8",
            )
            adapter_meta = self._write_helper_command_events(
                work_dir=work_dir,
                commands=["search", "research"],
            )
            return rf.LlmRunResult(resume=None, adapter_meta=adapter_meta)

        root, calls = self._run_pr_flow_for_tool_proof(
            root=root,
            profile_resolved="normal",
            multipass_enabled=False,
            llm_side_effect=llm_side_effect,
        )
        try:
            session_dir = next((root / "sandboxes").iterdir())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            report = json.loads((session_dir / "work" / "chunkhound_tool_validation.json").read_text(encoding="utf-8"))
            review_md = (session_dir / "review.md").read_text(encoding="utf-8")
            self.assertEqual(calls, ["review.md"])
            self.assertEqual(meta["status"], "done")
            self.assertTrue(meta["chunkhound"]["tool_validation"]["valid"])
            self.assertEqual([run["review_stage"] for run in report["runs"]], ["singlepass_review"])
            self.assertIn("<!-- CURE_REVIEW_FOOTER_START -->", review_md)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_flow_contradictory_plan_abort_raises_inconsistency_error(self) -> None:
        root = ROOT / ".tmp_test_codex_tool_proof_abort_contradiction"

        def llm_side_effect(output_path: Path, work_dir: Path) -> rf.LlmRunResult:
            output_path.write_text(
                "\n".join(
                    [
                        "### Plan JSON",
                        "```json",
                        json.dumps(
                            {
                                "abort": True,
                                "abort_reason": "Mandatory helper gate failed because research never completed.",
                                "jira_keys": [],
                                "steps": [],
                            }
                        ),
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            adapter_meta = self._write_helper_command_events(
                work_dir=work_dir,
                commands=["search", "research"],
            )
            return rf.LlmRunResult(resume=None, adapter_meta=adapter_meta)

        root, calls = self._run_pr_flow_for_tool_proof(
            root=root,
            profile_resolved="big",
            multipass_enabled=True,
            llm_side_effect=llm_side_effect,
            expect_error="Multipass planner/runtime inconsistency",
        )
        try:
            session_dir = next((root / "sandboxes").iterdir())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            report = json.loads((session_dir / "work" / "chunkhound_tool_validation.json").read_text(encoding="utf-8"))
            self.assertEqual(calls, ["review.plan.md"])
            self.assertEqual(meta["status"], "error")
            self.assertEqual(meta["multipass"]["status"], "planner_runtime_inconsistency")
            self.assertIn("plan_contradiction", meta["multipass"])
            self.assertIn(
                "Multipass planner/runtime inconsistency",
                str((meta.get("error") or {}).get("message") or ""),
            )
            self.assertTrue(report["runs"][0]["valid"])
            self.assertEqual(report["runs"][0]["observed_successful_calls"], ["search", "code_research"])
            self.assertFalse((session_dir / "review.md").exists())
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_flow_plan_abort_writes_footerized_abort_review(self) -> None:
        root = ROOT / ".tmp_test_codex_tool_proof_abort_review"

        def llm_side_effect(output_path: Path, work_dir: Path) -> rf.LlmRunResult:
            output_path.write_text(
                "\n".join(
                    [
                        "### Plan JSON",
                        "```json",
                        json.dumps(
                            {
                                "abort": True,
                                "abort_reason": "missing required Jira context",
                                "jira_keys": [],
                                "steps": [],
                            }
                        ),
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            adapter_meta = self._write_helper_command_events(
                work_dir=work_dir,
                commands=["search", "research"],
            )
            return rf.LlmRunResult(resume=None, adapter_meta=adapter_meta)

        root, calls = self._run_pr_flow_for_tool_proof(
            root=root,
            profile_resolved="big",
            multipass_enabled=True,
            llm_side_effect=llm_side_effect,
        )
        try:
            session_dir = next((root / "sandboxes").iterdir())
            review_md = (session_dir / "review.md").read_text(encoding="utf-8")
            self.assertEqual(calls, ["review.plan.md"])
            self.assertIn("missing required Jira context", review_md)
            self.assertIn("<!-- CURE_REVIEW_FOOTER_START -->", review_md)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_flow_codex_tool_proof_success_allows_multipass_completion(self) -> None:
        root = ROOT / ".tmp_test_codex_tool_proof_multipass"

        def llm_side_effect(output_path: Path, work_dir: Path) -> rf.LlmRunResult:
            if output_path.name == "review.plan.md":
                output_path.write_text(
                    "\n".join(
                        [
                            "### Plan JSON",
                            "```json",
                            json.dumps(
                                {
                                    "abort": False,
                                    "abort_reason": None,
                                    "jira_keys": ["ABC-1"],
                                    "steps": [{"id": "01", "title": "API review", "focus": "tool proof"}],
                                }
                            ),
                            "```",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                commands = ["search", "research"]
            elif output_path.name == "review.step-01.md":
                output_path.write_text(
                    "\n".join(
                        [
                            "### Step Result: 01 — API review",
                            "**Focus**: tool proof",
                            "",
                            "### Steps taken",
                            "- checked repo",
                            "",
                            "### Findings",
                            "- Input lacks validation. Evidence: `src/app.py:2`",
                            "",
                            "### Suggested actions",
                            "- Add checks",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                commands = ["search"]
            elif output_path.name == "review.md":
                output_path.write_text(_sectioned_review_markdown(business="APPROVE", technical="APPROVE"), encoding="utf-8")
                commands = []
            else:
                raise AssertionError(f"unexpected output path: {output_path}")
            adapter_meta = (
                self._write_helper_command_events(work_dir=work_dir, commands=commands)
                if commands
                else self._write_codex_events(work_dir=work_dir, tool_names=[])
            )
            return rf.LlmRunResult(resume=None, adapter_meta=adapter_meta)

        root, calls = self._run_pr_flow_for_tool_proof(
            root=root,
            profile_resolved="big",
            multipass_enabled=True,
            llm_side_effect=llm_side_effect,
        )
        try:
            session_dir = next((root / "sandboxes").iterdir())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            report = json.loads((session_dir / "work" / "chunkhound_tool_validation.json").read_text(encoding="utf-8"))
            self.assertEqual(calls, ["review.plan.md", "review.step-01.md", "review.md"])
            self.assertEqual(meta["status"], "done")
            self.assertTrue(meta["chunkhound"]["tool_validation"]["valid"])
            self.assertEqual(
                [run["review_stage"] for run in report["runs"]],
                ["multipass_plan", "multipass_step", "multipass_synth"],
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_flow_multipass_stage_effort_overrides_update_stage_metadata_and_footer(self) -> None:
        root = ROOT / ".tmp_test_multipass_stage_effort_overrides"
        stage_invocations: dict[str, dict[str, object]] = {}

        def llm_side_effect(output_path: Path, work_dir: Path, kwargs: dict[str, object]) -> rf.LlmRunResult:
            resolved = kwargs["resolved"] if isinstance(kwargs.get("resolved"), dict) else {}
            resolution_meta = kwargs["resolution_meta"] if isinstance(kwargs.get("resolution_meta"), dict) else {}
            runtime_policy = kwargs["runtime_policy"] if isinstance(kwargs.get("runtime_policy"), dict) else {}
            stage_invocations[output_path.name] = {
                "reasoning_effort": resolved.get("reasoning_effort"),
                "plan_reasoning_effort": resolved.get("plan_reasoning_effort"),
                "reasoning_effort_source": ((resolution_meta.get("resolved") or {}).get("reasoning_effort_source")),
                "plan_reasoning_effort_source": (
                    (resolution_meta.get("resolved") or {}).get("plan_reasoning_effort_source")
                ),
                "codex_flags": list(runtime_policy.get("codex_flags") or []),
            }
            if output_path.name == "review.plan.md":
                output_path.write_text(
                    "\n".join(
                        [
                            "### Plan JSON",
                            "```json",
                            json.dumps(
                                {
                                    "abort": False,
                                    "abort_reason": None,
                                    "jira_keys": ["ABC-1"],
                                    "steps": [{"id": "01", "title": "API review", "focus": "tool proof"}],
                                }
                            ),
                            "```",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                adapter_meta = self._write_helper_command_events(work_dir=work_dir, commands=["search", "research"])
            elif output_path.name == "review.step-01.md":
                output_path.write_text(
                    "\n".join(
                        [
                            "### Step Result: 01 — API review",
                            "**Focus**: tool proof",
                            "",
                            "### Steps taken",
                            "- checked repo",
                            "",
                            "### Findings",
                            "- Input lacks validation. Evidence: `src/app.py:2`",
                            "",
                            "### Suggested actions",
                            "- Add checks",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                adapter_meta = self._write_helper_command_events(work_dir=work_dir, commands=["search"])
            elif output_path.name == "review.md":
                output_path.write_text(
                    _sectioned_review_markdown(business="APPROVE", technical="REQUEST CHANGES"),
                    encoding="utf-8",
                )
                adapter_meta = self._write_codex_events(work_dir=work_dir, tool_names=[])
            else:
                raise AssertionError(f"unexpected output path: {output_path}")
            return rf.LlmRunResult(resume=None, adapter_meta=adapter_meta)

        root, calls = self._run_pr_flow_for_tool_proof(
            root=root,
            profile_resolved="big",
            multipass_enabled=True,
            llm_side_effect=llm_side_effect,
            multipass_defaults_override={
                "enabled": True,
                "max_steps": 20,
                "step_workers": 1,
                "grounding_mode": "off",
                "plan_reasoning_effort": "minimal",
                "step_reasoning_effort": "low",
                "synth_reasoning_effort": "xhigh",
            },
            llm_resolved_override={
                "provider": "codex",
                "preset": "test-codex",
                "model": "gpt-5.4",
                "reasoning_effort": "medium",
                "plan_reasoning_effort": "high",
                "capabilities": {"supports_resume": True},
            },
            llm_resolution_meta_override={
                "resolved": {
                    "model_source": "cli",
                    "reasoning_effort_source": "cli",
                    "plan_reasoning_effort_source": "preset",
                }
            },
            runtime_policy_override={
                "env": {},
                "metadata": {},
                "staged_paths": {},
                "add_dirs": [],
                "codex_config_overrides": [],
                "codex_flags": [],
                "dangerously_bypass_approvals_and_sandbox": False,
                "sandbox_mode": "workspace-write",
                "approval_policy": "never",
            },
        )
        try:
            session_dir = next((root / "sandboxes").iterdir())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            review_md = (session_dir / "review.md").read_text(encoding="utf-8")
            self.assertEqual(calls, ["review.plan.md", "review.step-01.md", "review.md"])
            self.assertEqual(stage_invocations["review.plan.md"]["reasoning_effort"], "medium")
            self.assertEqual(stage_invocations["review.plan.md"]["plan_reasoning_effort"], "minimal")
            self.assertEqual(stage_invocations["review.plan.md"]["plan_reasoning_effort_source"], "multipass_config")
            self.assertIn('plan_mode_reasoning_effort="minimal"', stage_invocations["review.plan.md"]["codex_flags"])
            self.assertEqual(stage_invocations["review.step-01.md"]["reasoning_effort"], "low")
            self.assertEqual(stage_invocations["review.step-01.md"]["reasoning_effort_source"], "multipass_config")
            self.assertIn('model_reasoning_effort="low"', stage_invocations["review.step-01.md"]["codex_flags"])
            self.assertEqual(stage_invocations["review.md"]["reasoning_effort"], "xhigh")
            self.assertEqual(stage_invocations["review.md"]["reasoning_effort_source"], "multipass_config")
            self.assertIn('model_reasoning_effort="xhigh"', stage_invocations["review.md"]["codex_flags"])
            self.assertEqual(meta["llm"]["reasoning_effort"], "medium")
            self.assertEqual(meta["multipass"]["llm"]["stages"]["plan"]["effective_reasoning_effort"], "minimal")
            self.assertEqual(meta["multipass"]["llm"]["stages"]["step"]["effective_reasoning_effort"], "low")
            self.assertEqual(meta["multipass"]["llm"]["stages"]["synth"]["effective_reasoning_effort"], "xhigh")
            self.assertEqual(meta["multipass"]["llm"]["review_artifact_stage"], "synth")
            self.assertEqual(
                meta["multipass"]["llm"]["review_artifact_llm"]["effective_reasoning_effort"],
                "xhigh",
            )
            self.assertEqual(meta["multipass"]["runs"][0]["llm"]["effective_reasoning_effort"], "minimal")
            self.assertIn("model gpt-5.4/xhigh", review_md)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_flow_parallel_multipass_steps_preserve_ordered_synth_inputs(self) -> None:
        root = ROOT / ".tmp_test_codex_tool_proof_parallel_multipass"
        step_one_started = threading.Event()
        step_two_finished = threading.Event()
        synth_prompts: list[str] = []

        def llm_side_effect(output_path: Path, work_dir: Path, kwargs: dict[str, object]) -> rf.LlmRunResult:
            if output_path.name == "review.plan.md":
                output_path.write_text(
                    "\n".join(
                        [
                            "### Plan JSON",
                            "```json",
                            json.dumps(
                                {
                                    "abort": False,
                                    "abort_reason": None,
                                    "jira_keys": ["ABC-1"],
                                    "steps": [
                                        {"id": "01", "title": "API review", "focus": "api"},
                                        {"id": "02", "title": "Tests review", "focus": "tests"},
                                    ],
                                }
                            ),
                            "```",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                adapter_meta = self._write_helper_command_events(
                    work_dir=work_dir,
                    commands=["search", "research"],
                )
            elif output_path.name == "review.step-01.md":
                step_one_started.set()
                self.assertTrue(step_two_finished.wait(timeout=2))
                output_path.write_text(
                    "\n".join(
                        [
                            "### Step Result: 01 — API review",
                            "**Focus**: api",
                            "",
                            "### Findings",
                            "- API concern",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                adapter_meta = self._write_helper_command_events(work_dir=work_dir, commands=["search"])
            elif output_path.name == "review.step-02.md":
                self.assertTrue(step_one_started.wait(timeout=2))
                output_path.write_text(
                    "\n".join(
                        [
                            "### Step Result: 02 — Tests review",
                            "**Focus**: tests",
                            "",
                            "### Findings",
                            "- Test concern",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                step_two_finished.set()
                adapter_meta = self._write_helper_command_events(work_dir=work_dir, commands=["search"])
            elif output_path.name == "review.md":
                synth_prompts.append(str(kwargs["prompt"]))
                output_path.write_text(
                    _sectioned_review_markdown(business="APPROVE", technical="REQUEST CHANGES"),
                    encoding="utf-8",
                )
                adapter_meta = self._write_codex_events(work_dir=work_dir, tool_names=[])
            else:
                raise AssertionError(f"unexpected output path: {output_path}")
            return rf.LlmRunResult(resume=None, adapter_meta=adapter_meta)

        root, calls = self._run_pr_flow_for_tool_proof(
            root=root,
            profile_resolved="big",
            multipass_enabled=True,
            step_workers=2,
            llm_side_effect=llm_side_effect,
        )
        try:
            session_dir = next((root / "sandboxes").iterdir())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(
                calls,
                ["review.plan.md", "review.step-01.md", "review.step-02.md", "review.md"],
            )
            self.assertEqual(meta["multipass"]["step_workers"], 2)
            self.assertEqual(meta["multipass"]["effective_step_workers"], 2)
            self.assertEqual(
                meta["multipass"]["artifacts"]["step_outputs"],
                [
                    str(session_dir / "review.step-01.md"),
                    str(session_dir / "review.step-02.md"),
                ],
            )
            self.assertEqual(
                [item["status"] for item in meta["multipass"]["step_states"]],
                ["completed", "completed"],
            )
            self.assertEqual(len(synth_prompts), 1)
            self.assertLess(
                synth_prompts[0].index("review.step-01.md"),
                synth_prompts[0].index("review.step-02.md"),
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_flow_parallel_multipass_step_failure_blocks_synth(self) -> None:
        root = ROOT / ".tmp_test_codex_tool_proof_parallel_step_failure"

        def llm_side_effect(output_path: Path, work_dir: Path) -> rf.LlmRunResult:
            if output_path.name == "review.plan.md":
                output_path.write_text(
                    "\n".join(
                        [
                            "### Plan JSON",
                            "```json",
                            json.dumps(
                                {
                                    "abort": False,
                                    "abort_reason": None,
                                    "jira_keys": ["ABC-1"],
                                    "steps": [
                                        {"id": "01", "title": "API review", "focus": "api"},
                                        {"id": "02", "title": "Tests review", "focus": "tests"},
                                    ],
                                }
                            ),
                            "```",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                adapter_meta = self._write_helper_command_events(work_dir=work_dir, commands=["search", "research"])
                return rf.LlmRunResult(resume=None, adapter_meta=adapter_meta)
            if output_path.name == "review.step-01.md":
                output_path.write_text(
                    "\n".join(
                        [
                            "### Step Result: 01 — API review",
                            "**Focus**: api",
                            "",
                            "### Findings",
                            "- API concern",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                adapter_meta = self._write_helper_command_events(work_dir=work_dir, commands=["search"])
                return rf.LlmRunResult(resume=None, adapter_meta=adapter_meta)
            if output_path.name == "review.step-02.md":
                raise rf.ReviewflowError("simulated parallel step failure")
            if output_path.name == "review.md":
                raise AssertionError("synth should not run after a step failure")
            raise AssertionError(f"unexpected output path: {output_path}")

        root, calls = self._run_pr_flow_for_tool_proof(
            root=root,
            profile_resolved="big",
            multipass_enabled=True,
            step_workers=2,
            llm_side_effect=llm_side_effect,
            expect_error="simulated parallel step failure",
        )
        try:
            session_dir = next((root / "sandboxes").iterdir())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertNotIn("review.md", calls)
            self.assertEqual(meta["status"], "error")
            self.assertEqual(meta["multipass"]["status"], "step_failed")
            self.assertEqual(
                [item["status"] for item in meta["multipass"]["step_states"]],
                ["completed", "failed"],
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_flow_codex_helper_execution_proof_allows_multipass_completion(self) -> None:
        root = ROOT / ".tmp_test_codex_helper_tool_proof_multipass"

        def llm_side_effect(output_path: Path, work_dir: Path) -> rf.LlmRunResult:
            if output_path.name == "review.plan.md":
                output_path.write_text(
                    "\n".join(
                        [
                            "### Plan JSON",
                            "```json",
                            json.dumps(
                                {
                                    "abort": False,
                                    "abort_reason": None,
                                    "jira_keys": ["ABC-1"],
                                    "steps": [{"id": "01", "title": "API review", "focus": "tool proof"}],
                                }
                            ),
                            "```",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                adapter_meta = self._write_helper_command_events(
                    work_dir=work_dir,
                    commands=["search", "research"],
                )
            elif output_path.name == "review.step-01.md":
                output_path.write_text(
                    "\n".join(
                        [
                            "### Step Result: 01 — API review",
                            "**Focus**: tool proof",
                            "",
                            "### Steps taken",
                            "- checked repo",
                            "",
                            "### Findings",
                            "- Input lacks validation. Evidence: `src/app.py:2`",
                            "",
                            "### Suggested actions",
                            "- Add checks",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                adapter_meta = self._write_helper_command_events(
                    work_dir=work_dir,
                    commands=["search"],
                )
            elif output_path.name == "review.md":
                output_path.write_text(
                    _sectioned_review_markdown(business="APPROVE", technical="APPROVE"),
                    encoding="utf-8",
                )
                adapter_meta = self._write_codex_events(work_dir=work_dir, tool_names=[])
            else:
                raise AssertionError(f"unexpected output path: {output_path}")
            return rf.LlmRunResult(resume=None, adapter_meta=adapter_meta)

        root, calls = self._run_pr_flow_for_tool_proof(
            root=root,
            profile_resolved="big",
            multipass_enabled=True,
            llm_side_effect=llm_side_effect,
        )
        try:
            session_dir = next((root / "sandboxes").iterdir())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            report = json.loads((session_dir / "work" / "chunkhound_tool_validation.json").read_text(encoding="utf-8"))
            self.assertEqual(calls, ["review.plan.md", "review.step-01.md", "review.md"])
            self.assertEqual(meta["status"], "done")
            self.assertTrue(meta["chunkhound"]["tool_validation"]["valid"])
            self.assertEqual(meta["chunkhound"]["tool_validation"]["evidence_sources"], ["cli_helper_command_execution"])
            self.assertEqual(meta["chunkhound"]["tool_validation"]["latest_evidence_sources"], [])
            self.assertEqual(
                [run["review_stage"] for run in report["runs"]],
                ["multipass_plan", "multipass_step", "multipass_synth"],
            )
            self.assertEqual(report["evidence_sources"], ["cli_helper_command_execution"])
            self.assertEqual(report["latest_evidence_sources"], [])
            self.assertEqual(report["runs"][0]["observed_evidence_sources"], ["cli_helper_command_execution"])
            self.assertEqual(report["runs"][1]["observed_evidence_sources"], ["cli_helper_command_execution"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_flow_helper_preflight_failure_aborts_before_review_generation(self) -> None:
        root = ROOT / ".tmp_test_codex_helper_preflight_failure"

        def llm_side_effect(output_path: Path, work_dir: Path) -> rf.LlmRunResult:
            raise AssertionError("review generation should not start when helper preflight fails")

        root, calls = self._run_pr_flow_for_tool_proof(
            root=root,
            profile_resolved="normal",
            multipass_enabled=False,
            llm_side_effect=llm_side_effect,
            expect_error="ChunkHound helper preflight failed before review generation",
            helper_preflight_side_effect=rf.ReviewflowError(
                "ChunkHound helper preflight failed before review generation: helper failed."
            ),
        )
        try:
            session_dir = next((root / "sandboxes").iterdir())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(calls, [])
            self.assertEqual(meta["status"], "error")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_flow_helper_preflight_timeout_persists_access_metadata(self) -> None:
        root = ROOT / ".tmp_test_codex_helper_preflight_timeout"

        def llm_side_effect(output_path: Path, work_dir: Path) -> rf.LlmRunResult:
            raise AssertionError("review generation should not start when helper preflight fails")

        def helper_preflight_timeout(*, meta: dict[str, Any], **_: Any) -> None:
            meta.setdefault("chunkhound", {})["access"] = {
                "provider": "codex",
                "mode": "cli_helper_daemon",
                "helper_env_var": "CURE_CHUNKHOUND_HELPER",
                "helper_path": "/tmp/session/work/bin/cure-chunkhound",
                "chunkhound_path": "/usr/bin/chunkhound",
                "chunkhound_runtime_python": "/usr/bin/python3",
                "chunkhound_module_path": "/opt/chunkhound/site-packages/chunkhound/__init__.py",
                "daemon_lock_path": "/tmp/chunkhound-runtime/daemon.lock",
                "daemon_socket_path": "/tmp/chunkhound-runtime.sock",
                "daemon_log_path": "/tmp/chunkhound-runtime/daemon.log",
                "daemon_pid": 5150,
                "daemon_runtime_dir": "/tmp/chunkhound-runtime",
                "daemon_registry_entry_path": "/tmp/chunkhound-runtime/registry/repo.json",
                "preflight_ok": False,
                "error": "ChunkHound daemon did not start within 30.0s while waiting for IPC readiness",
            }
            raise rf.ReviewflowError(
                "ChunkHound helper preflight failed before review generation: "
                "ChunkHound daemon did not start within 30.0s while waiting for IPC readiness."
            )

        root, calls = self._run_pr_flow_for_tool_proof(
            root=root,
            profile_resolved="normal",
            multipass_enabled=False,
            llm_side_effect=llm_side_effect,
            expect_error="ChunkHound helper preflight failed before review generation",
            helper_preflight_side_effect=helper_preflight_timeout,
        )
        try:
            session_dir = next((root / "sandboxes").iterdir())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(calls, [])
            self.assertEqual(meta["status"], "error")
            self.assertEqual(meta["chunkhound"]["access"]["chunkhound_runtime_python"], "/usr/bin/python3")
            self.assertEqual(meta["chunkhound"]["access"]["daemon_lock_path"], "/tmp/chunkhound-runtime/daemon.lock")
            self.assertEqual(meta["chunkhound"]["access"]["daemon_runtime_dir"], "/tmp/chunkhound-runtime")
            self.assertFalse(meta["chunkhound"]["access"]["preflight_ok"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_followup_flow_codex_tool_proof_success_allows_completion(self) -> None:
        root = ROOT / ".tmp_test_codex_tool_proof_followup"
        cfg = root / "reviewflow.toml"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            base_cfg = root / "chunkhound-base.json"
            base_cfg.write_text("{}", encoding="utf-8")
            cfg.write_text(
                f"[chunkhound]\nbase_config_path = {json.dumps(str(base_cfg))}\n",
                encoding="utf-8",
            )
            session_dir = root / "session-1"
            repo_dir = session_dir / "repo"
            work_dir = session_dir / "work"
            chunkhound_dir = work_dir / "chunkhound"
            repo_dir.mkdir(parents=True, exist_ok=True)
            chunkhound_dir.mkdir(parents=True, exist_ok=True)
            review_md = session_dir / "review.md"
            review_md.write_text(_sectioned_review_markdown(business="APPROVE", technical="APPROVE"), encoding="utf-8")
            meta = {
                "session_id": "session-1",
                "status": "done",
                "created_at": "2026-03-10T00:00:00+00:00",
                "completed_at": "2026-03-10T00:05:00+00:00",
                "pr_url": "https://github.com/acme/repo/pull/9",
                "host": "github.com",
                "owner": "acme",
                "repo": "repo",
                "number": 9,
                "base_ref": "main",
                "base_ref_for_review": "cure_base__main",
                "prompt": {"profile_resolved": "normal"},
                "llm": {"provider": "codex", "capabilities": {"supports_resume": True}},
                "notes": {"no_index": False},
                "paths": {
                    "session_dir": str(session_dir),
                    "repo_dir": str(repo_dir),
                    "work_dir": str(work_dir),
                    "chunkhound_cwd": str(chunkhound_dir),
                    "chunkhound_db": str(chunkhound_dir / ".chunkhound.db"),
                    "chunkhound_config": str(chunkhound_dir / "chunkhound.json"),
                    "review_md": str(review_md),
                },
            }
            (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

            args = argparse.Namespace(
                session_id="session-1",
                no_update=True,
                codex_model=None,
                codex_effort=None,
                codex_plan_effort=None,
                quiet=True,
                no_stream=True,
                ui="off",
                verbosity="normal",
            )
            paths = rf.ReviewflowPaths(sandbox_root=root, cache_root=root / "cache")

            class _Result:
                def __init__(self, stdout: str = "") -> None:
                    self.stdout = stdout
                    self.stderr = ""
                    self.duration_seconds = 0.0

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> _Result:
                if cmd[:4] == ["git", "-C", str(repo_dir), "rev-parse"]:
                    return _Result("deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n")
                if cmd and cmd[0] == "chunkhound":
                    return _Result()
                raise AssertionError(f"unexpected command: {cmd}")

            def fake_run_llm_exec(**kwargs: object) -> rf.LlmRunResult:
                output_path = Path(str(kwargs["output_path"]))
                output_path.write_text(
                    _sectioned_review_markdown(business="APPROVE", technical="REQUEST CHANGES"),
                    encoding="utf-8",
                )
                adapter_meta = self._write_helper_command_events(work_dir=work_dir, commands=["search"])
                return rf.LlmRunResult(resume=None, adapter_meta=adapter_meta)

            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(rf, "ensure_review_config"))
                stack.enter_context(mock.patch.object(rf, "restore_session_chunkhound_db_from_baseline"))
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_chunkhound_runtime_config",
                        return_value=(
                            rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                            {"chunkhound": {"base_config_path": str(base_cfg)}},
                            {"indexing": {"exclude": []}},
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "materialize_chunkhound_env_config",
                        side_effect=self._fake_materialize_chunkhound_env_config,
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_review_intelligence_config",
                        return_value=(
                            _review_intelligence_cfg(),
                            _review_intelligence_meta(_review_intelligence_cfg()),
                        ),
                    )
                )
                stack.enter_context(mock.patch.object(rf, "require_builtin_review_intelligence"))
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "resolve_llm_config_from_args",
                        return_value=(
                            {"provider": "codex", "preset": "test-codex"},
                            {},
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "prepare_review_agent_runtime",
                        return_value=self._codex_runtime_policy(),
                    )
                )
                stack.enter_context(mock.patch.object(rf, "_run_review_intelligence_preflight"))
                stack.enter_context(mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd))
                stack.enter_context(
                    mock.patch.object(
                        rf.ReviewflowOutput,
                        "run_logged_cmd",
                        autospec=True,
                        side_effect=lambda output, cmd, **kwargs: fake_run_cmd(cmd, **kwargs),
                    )
                )
                stack.enter_context(mock.patch.object(rf, "run_llm_exec", side_effect=fake_run_llm_exec))
                rc = rf.followup_flow(args, paths=paths, config_path=cfg, codex_base_config_path=cfg)

            refreshed = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            report = json.loads((work_dir / "chunkhound_tool_validation.json").read_text(encoding="utf-8"))
            followup_path = Path(str(refreshed["followups"][0]["output_path"]))
            followup_md = followup_path.read_text(encoding="utf-8")
            self.assertEqual(rc, 0)
            self.assertEqual(len(refreshed["followups"]), 1)
            self.assertTrue(refreshed["chunkhound"]["tool_validation"]["valid"])
            self.assertEqual(refreshed["chunkhound"]["tool_validation"]["evidence_sources"], ["cli_helper_command_execution"])
            self.assertEqual([run["review_stage"] for run in report["runs"]], ["followup"])
            self.assertIn("<!-- CURE_REVIEW_FOOTER_START -->", followup_md)
            self.assertIn("sha deadbee", followup_md)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_followup_flow_codex_tool_proof_failure_persists_meta_before_raise(self) -> None:
        root = ROOT / ".tmp_test_codex_tool_proof_followup_failure"
        cfg = root / "reviewflow.toml"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            base_cfg = root / "chunkhound-base.json"
            base_cfg.write_text("{}", encoding="utf-8")
            cfg.write_text(
                f"[chunkhound]\nbase_config_path = {json.dumps(str(base_cfg))}\n",
                encoding="utf-8",
            )
            session_dir = root / "session-1"
            repo_dir = session_dir / "repo"
            work_dir = session_dir / "work"
            chunkhound_dir = work_dir / "chunkhound"
            repo_dir.mkdir(parents=True, exist_ok=True)
            chunkhound_dir.mkdir(parents=True, exist_ok=True)
            review_md = session_dir / "review.md"
            review_md.write_text(_sectioned_review_markdown(business="APPROVE", technical="APPROVE"), encoding="utf-8")
            meta = {
                "session_id": "session-1",
                "status": "done",
                "created_at": "2026-03-10T00:00:00+00:00",
                "completed_at": "2026-03-10T00:05:00+00:00",
                "pr_url": "https://github.com/acme/repo/pull/9",
                "host": "github.com",
                "owner": "acme",
                "repo": "repo",
                "number": 9,
                "base_ref": "main",
                "base_ref_for_review": "cure_base__main",
                "prompt": {"profile_resolved": "normal"},
                "llm": {"provider": "codex", "capabilities": {"supports_resume": True}},
                "notes": {"no_index": False},
                "paths": {
                    "session_dir": str(session_dir),
                    "repo_dir": str(repo_dir),
                    "work_dir": str(work_dir),
                    "chunkhound_cwd": str(chunkhound_dir),
                    "chunkhound_db": str(chunkhound_dir / ".chunkhound.db"),
                    "chunkhound_config": str(chunkhound_dir / "chunkhound.json"),
                    "review_md": str(review_md),
                },
            }
            (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

            args = argparse.Namespace(
                session_id="session-1",
                no_update=True,
                codex_model=None,
                codex_effort=None,
                codex_plan_effort=None,
                quiet=True,
                no_stream=True,
                ui="off",
                verbosity="normal",
            )
            paths = rf.ReviewflowPaths(sandbox_root=root, cache_root=root / "cache")

            class _Result:
                def __init__(self, stdout: str = "") -> None:
                    self.stdout = stdout
                    self.stderr = ""
                    self.duration_seconds = 0.0

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> _Result:
                if cmd[:4] == ["git", "-C", str(repo_dir), "rev-parse"]:
                    return _Result("deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n")
                if cmd and cmd[0] == "chunkhound":
                    return _Result()
                raise AssertionError(f"unexpected command: {cmd}")

            def fake_run_llm_exec(**kwargs: object) -> rf.LlmRunResult:
                output_path = Path(str(kwargs["output_path"]))
                output_path.write_text(
                    _sectioned_review_markdown(business="APPROVE", technical="REQUEST CHANGES"),
                    encoding="utf-8",
                )
                adapter_meta = self._write_helper_command_events(
                    work_dir=work_dir,
                    commands=["search"],
                    command="/bin/bash -lc 'chunkhound search needle'",
                )
                return rf.LlmRunResult(resume=None, adapter_meta=adapter_meta)

            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(rf, "ensure_review_config"))
                stack.enter_context(mock.patch.object(rf, "restore_session_chunkhound_db_from_baseline"))
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_chunkhound_runtime_config",
                        return_value=(
                            rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                            {"chunkhound": {"base_config_path": str(base_cfg)}},
                            {"indexing": {"exclude": []}},
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "materialize_chunkhound_env_config",
                        side_effect=self._fake_materialize_chunkhound_env_config,
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_review_intelligence_config",
                        return_value=(
                            _review_intelligence_cfg(),
                            _review_intelligence_meta(_review_intelligence_cfg()),
                        ),
                    )
                )
                stack.enter_context(mock.patch.object(rf, "require_builtin_review_intelligence"))
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "resolve_llm_config_from_args",
                        return_value=(
                            {"provider": "codex", "preset": "test-codex"},
                            {},
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "prepare_review_agent_runtime",
                        return_value=self._codex_runtime_policy(),
                    )
                )
                stack.enter_context(mock.patch.object(rf, "_run_review_intelligence_preflight"))
                stack.enter_context(mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd))
                stack.enter_context(
                    mock.patch.object(
                        rf.ReviewflowOutput,
                        "run_logged_cmd",
                        autospec=True,
                        side_effect=lambda output, cmd, **kwargs: fake_run_cmd(cmd, **kwargs),
                    )
                )
                stack.enter_context(mock.patch.object(rf, "run_llm_exec", side_effect=fake_run_llm_exec))
                with self.assertRaisesRegex(rf.ReviewflowError, "ChunkHound tool proof failed for followup"):
                    rf.followup_flow(args, paths=paths, config_path=cfg, codex_base_config_path=cfg)

            refreshed = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            report = json.loads((work_dir / "chunkhound_tool_validation.json").read_text(encoding="utf-8"))
            self.assertFalse(refreshed["chunkhound"]["tool_validation"]["valid"])
            self.assertFalse(refreshed["chunkhound"]["tool_validation"]["latest_run_valid"])
            self.assertEqual(refreshed["chunkhound"]["tool_validation"]["latest_review_stage"], "followup")
            self.assertEqual(report["runs"][0]["observed_evidence_sources"], [])
            self.assertEqual([run["review_stage"] for run in report["runs"]], ["followup"])
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_resume_flow_existing_contradictory_abort_plan_raises_inconsistency_error(self) -> None:
        root = ROOT / ".tmp_test_codex_tool_proof_resume_abort_contradiction"
        cfg = root / "reviewflow.toml"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            base_cfg = root / "chunkhound-base.json"
            base_cfg.write_text("{}", encoding="utf-8")
            cfg.write_text(
                f"[chunkhound]\nbase_config_path = {json.dumps(str(base_cfg))}\n",
                encoding="utf-8",
            )
            session_dir = root / "session-1"
            repo_dir = session_dir / "repo"
            work_dir = session_dir / "work"
            chunkhound_dir = work_dir / "chunkhound"
            repo_dir.mkdir(parents=True, exist_ok=True)
            chunkhound_dir.mkdir(parents=True, exist_ok=True)
            (repo_dir / "src").mkdir(parents=True, exist_ok=True)
            (repo_dir / "src" / "app.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
            plan_json = work_dir / "review_plan.json"
            plan_json.write_text(
                json.dumps(
                    {
                        "abort": True,
                        "abort_reason": "Mandatory helper gate failed because research never completed.",
                        "jira_keys": [],
                        "steps": [],
                    }
                ),
                encoding="utf-8",
            )
            meta = {
                "session_id": "session-1",
                "status": "done",
                "created_at": "2026-03-10T00:00:00+00:00",
                "completed_at": "2026-03-10T01:00:00+00:00",
                "pr_url": "https://github.com/acme/repo/pull/9",
                "host": "github.com",
                "owner": "acme",
                "repo": "repo",
                "number": 9,
                "base_ref_for_review": "cure_base__main",
                "llm": {"provider": "codex", "capabilities": {"supports_resume": True}},
                "notes": {"no_index": False},
                "paths": {
                    "session_dir": str(session_dir),
                    "repo_dir": str(repo_dir),
                    "work_dir": str(work_dir),
                    "chunkhound_cwd": str(chunkhound_dir),
                    "chunkhound_db": str(chunkhound_dir / ".chunkhound.db"),
                    "chunkhound_config": str(chunkhound_dir / "chunkhound.json"),
                    "review_md": str(session_dir / "review.md"),
                },
                "multipass": {
                    "enabled": True,
                    "plan_json_path": str(plan_json),
                    "grounding_mode": "strict",
                },
            }
            rf.validate_and_record_codex_chunkhound_tool_proof(
                meta=meta,
                work_dir=work_dir,
                provider="codex",
                review_stage="multipass_plan",
                prompt_template_name="mrereview_gh_local_big_plan.md",
                adapter_meta=self._write_helper_command_events(
                    work_dir=work_dir,
                    commands=["search", "research"],
                ),
            )
            (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

            args = argparse.Namespace(
                session_id="session-1",
                from_phase="auto",
                no_index=False,
                codex_model=None,
                codex_effort=None,
                codex_plan_effort=None,
                quiet=True,
                no_stream=True,
                ui="off",
                verbosity="normal",
            )
            paths = rf.ReviewflowPaths(sandbox_root=root, cache_root=root / "cache")

            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(rf, "ensure_review_config"))
                stack.enter_context(mock.patch.object(rf, "restore_session_chunkhound_db_from_baseline"))
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_chunkhound_runtime_config",
                        return_value=(
                            rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                            {"chunkhound": {"base_config_path": str(base_cfg)}},
                            {"indexing": {"exclude": []}},
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "materialize_chunkhound_env_config",
                        side_effect=self._fake_materialize_chunkhound_env_config,
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_review_intelligence_config",
                        return_value=(
                            _review_intelligence_cfg(),
                            _review_intelligence_meta(_review_intelligence_cfg()),
                        ),
                    )
                )
                stack.enter_context(mock.patch.object(rf, "require_builtin_review_intelligence"))
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "resolve_llm_config_from_args",
                        return_value=(
                            {
                                "provider": "codex",
                                "preset": "test-codex",
                                "model": "gpt-5.4",
                                "reasoning_effort": "medium",
                                "plan_reasoning_effort": "high",
                                "capabilities": {"supports_resume": True},
                            },
                            {
                                "resolved": {
                                    "model_source": "cli",
                                    "reasoning_effort_source": "cli",
                                    "plan_reasoning_effort_source": "preset",
                                }
                            },
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "prepare_review_agent_runtime",
                        return_value=self._codex_runtime_policy(),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_reviewflow_multipass_defaults",
                        return_value=(
                            {
                                "enabled": True,
                                "max_steps": 20,
                                "grounding_mode": "strict",
                                "step_reasoning_effort": "low",
                                "synth_reasoning_effort": "xhigh",
                            },
                            {
                                "multipass": {
                                    "enabled": True,
                                    "max_steps": 20,
                                    "grounding_mode": "strict",
                                    "step_reasoning_effort": "low",
                                    "synth_reasoning_effort": "xhigh",
                                }
                            },
                        ),
                    )
                )
                stack.enter_context(mock.patch.object(rf, "_run_review_intelligence_preflight"))
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "run_llm_exec",
                        side_effect=AssertionError("resume should not rerun review generation"),
                    )
                )
                with self.assertRaisesRegex(rf.ReviewflowError, "Multipass planner/runtime inconsistency"):
                    rf.resume_flow(args, paths=paths, config_path=cfg, codex_base_config_path=cfg)

            refreshed = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(refreshed["status"], "error")
            self.assertTrue(refreshed["chunkhound"]["tool_validation"]["valid"])
            self.assertEqual(refreshed["multipass"]["status"], "planner_runtime_inconsistency")
            self.assertIn("plan_contradiction", refreshed["multipass"])
            self.assertFalse((session_dir / "review.md").exists())
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_resume_flow_codex_helper_tool_proof_success_allows_completion(self) -> None:
        root = ROOT / ".tmp_test_codex_tool_proof_resume"
        cfg = root / "reviewflow.toml"
        valid_synth_markdown = "\n".join(
            [
                "### Steps taken",
                "- Read step output",
                "",
                "**Summary**: ok",
                "",
                "## Business / Product Assessment",
                "**Verdict**: APPROVE",
                "",
                "### Strengths",
                "- Business value is clear. Sources: `src/app.py:2`",
                "",
                "### In Scope Issues",
                "- None.",
                "",
                "### Out of Scope Issues",
                "- None.",
                "",
                "## Technical Assessment",
                "**Verdict**: REQUEST CHANGES",
                "",
                "### Strengths",
                "- Technical read happened. Sources: `src/app.py:2`",
                "",
                "### In Scope Issues",
                "- Missing provenance hygiene. Sources: `src/app.py:2`",
                "",
                "### Out of Scope Issues",
                "- None.",
                "",
                "### Reusability",
                "- Artifact stays inspectable. Sources: `src/app.py:2`",
                "",
            ]
        )
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            base_cfg = root / "chunkhound-base.json"
            base_cfg.write_text("{}", encoding="utf-8")
            cfg.write_text(
                f"[chunkhound]\nbase_config_path = {json.dumps(str(base_cfg))}\n",
                encoding="utf-8",
            )
            session_dir = root / "session-1"
            repo_dir = session_dir / "repo"
            work_dir = session_dir / "work"
            chunkhound_dir = work_dir / "chunkhound"
            repo_dir.mkdir(parents=True, exist_ok=True)
            chunkhound_dir.mkdir(parents=True, exist_ok=True)
            (repo_dir / "src").mkdir(parents=True, exist_ok=True)
            (repo_dir / "src" / "app.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
            plan_json = work_dir / "review_plan.json"
            plan_json.write_text(
                json.dumps(
                    {
                        "abort": False,
                        "abort_reason": None,
                        "jira_keys": ["ABC-1"],
                        "steps": [{"id": "01", "title": "API review", "focus": "tool proof"}],
                    }
                ),
                encoding="utf-8",
            )
            step_output = session_dir / "review.step-01.md"
            step_output.write_text(
                "\n".join(
                    [
                        "### Step Result: 01 — API review",
                        "**Focus**: tool proof",
                        "",
                        "### Findings",
                        "- Missing provenance",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            review_md = session_dir / "review.md"
            review_md.write_text(valid_synth_markdown, encoding="utf-8")
            invalid_step = rf.validate_multipass_step_grounding(
                artifact_path=step_output,
                repo_dir=repo_dir,
                step_index=1,
            )
            rf._update_grounding_state(
                meta={"multipass": {"enabled": True, "grounding_mode": "strict"}},
                work_dir=work_dir,
                grounding_mode="strict",
                result=invalid_step,
            )
            meta = {
                "session_id": "session-1",
                "status": "done",
                "created_at": "2026-03-10T00:00:00+00:00",
                "completed_at": "2026-03-10T01:00:00+00:00",
                "pr_url": "https://github.com/acme/repo/pull/9",
                "host": "github.com",
                "owner": "acme",
                "repo": "repo",
                "number": 9,
                "base_ref_for_review": "cure_base__main",
                "llm": {"provider": "codex", "capabilities": {"supports_resume": True}},
                "notes": {"no_index": False},
                "paths": {
                    "session_dir": str(session_dir),
                    "repo_dir": str(repo_dir),
                    "work_dir": str(work_dir),
                    "chunkhound_cwd": str(chunkhound_dir),
                    "chunkhound_db": str(chunkhound_dir / ".chunkhound.db"),
                    "chunkhound_config": str(chunkhound_dir / "chunkhound.json"),
                    "review_md": str(review_md),
                },
                "multipass": {
                    "enabled": True,
                    "plan_json_path": str(plan_json),
                    "grounding_mode": "strict",
                    "validation": {
                        "mode": "strict",
                        "invalid_artifacts": ["step-01"],
                        "has_invalid_artifacts": True,
                        "artifacts": {"step-01": invalid_step},
                        "report_path": str(work_dir / "grounding_report.json"),
                    },
                },
            }
            (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

            calls: list[str] = []
            stage_invocations: dict[str, dict[str, object]] = {}

            def fake_run_llm_exec(**kwargs: object) -> rf.LlmRunResult:
                output_path = Path(str(kwargs["output_path"]))
                calls.append(output_path.name)
                resolved = kwargs["resolved"] if isinstance(kwargs.get("resolved"), dict) else {}
                resolution_meta = kwargs["resolution_meta"] if isinstance(kwargs.get("resolution_meta"), dict) else {}
                stage_invocations[output_path.name] = {
                    "reasoning_effort": resolved.get("reasoning_effort"),
                    "plan_reasoning_effort": resolved.get("plan_reasoning_effort"),
                    "reasoning_effort_source": ((resolution_meta.get("resolved") or {}).get("reasoning_effort_source")),
                    "plan_reasoning_effort_source": (
                        (resolution_meta.get("resolved") or {}).get("plan_reasoning_effort_source")
                    ),
                }
                if output_path.name == "review.step-01.md":
                    output_path.write_text(
                        "\n".join(
                            [
                                "### Step Result: 01 — API review",
                                "**Focus**: tool proof",
                                "",
                                "### Steps taken",
                                "- checked repo",
                                "",
                                "### Findings",
                                "- Input lacks validation. Evidence: `src/app.py:2`",
                                "",
                                "### Suggested actions",
                                "- Add checks",
                                "",
                            ]
                        ),
                        encoding="utf-8",
                    )
                    adapter_meta = self._write_helper_command_events(work_dir=work_dir, commands=["search"])
                elif output_path.name == "review.md":
                    output_path.write_text(valid_synth_markdown, encoding="utf-8")
                    adapter_meta = self._write_codex_events(work_dir=work_dir, tool_names=[])
                else:
                    raise AssertionError(f"unexpected output path: {output_path}")
                return rf.LlmRunResult(resume=None, adapter_meta=adapter_meta)

            args = argparse.Namespace(
                session_id="session-1",
                from_phase="auto",
                no_index=False,
                codex_model=None,
                codex_effort=None,
                codex_plan_effort=None,
                quiet=True,
                no_stream=True,
                ui="off",
                verbosity="normal",
            )
            paths = rf.ReviewflowPaths(sandbox_root=root, cache_root=root / "cache")

            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(rf, "ensure_review_config"))
                stack.enter_context(mock.patch.object(rf, "restore_session_chunkhound_db_from_baseline"))
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_chunkhound_runtime_config",
                        return_value=(
                            rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                            {"chunkhound": {"base_config_path": str(base_cfg)}},
                            {"indexing": {"exclude": []}},
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "materialize_chunkhound_env_config",
                        side_effect=self._fake_materialize_chunkhound_env_config,
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_review_intelligence_config",
                        return_value=(
                            _review_intelligence_cfg(),
                            _review_intelligence_meta(_review_intelligence_cfg()),
                        ),
                    )
                )
                stack.enter_context(mock.patch.object(rf, "require_builtin_review_intelligence"))
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "resolve_llm_config_from_args",
                        return_value=(
                            {
                                "provider": "codex",
                                "preset": "test-codex",
                                "model": "gpt-5.4",
                                "reasoning_effort": "medium",
                                "plan_reasoning_effort": "high",
                                "capabilities": {"supports_resume": True},
                            },
                            {
                                "resolved": {
                                    "model_source": "cli",
                                    "reasoning_effort_source": "cli",
                                    "plan_reasoning_effort_source": "preset",
                                }
                            },
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "prepare_review_agent_runtime",
                        return_value=self._codex_runtime_policy(),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_reviewflow_multipass_defaults",
                        return_value=(
                            {
                                "enabled": True,
                                "max_steps": 20,
                                "grounding_mode": "strict",
                                "step_reasoning_effort": "low",
                                "synth_reasoning_effort": "xhigh",
                            },
                            {
                                "multipass": {
                                    "enabled": True,
                                    "max_steps": 20,
                                    "grounding_mode": "strict",
                                    "step_reasoning_effort": "low",
                                    "synth_reasoning_effort": "xhigh",
                                }
                            },
                        ),
                    )
                )
                stack.enter_context(mock.patch.object(rf, "_run_review_intelligence_preflight"))
                stack.enter_context(mock.patch.object(rf, "run_llm_exec", side_effect=fake_run_llm_exec))
                rc = rf.resume_flow(args, paths=paths, config_path=cfg, codex_base_config_path=cfg)

            refreshed = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            report = json.loads((work_dir / "chunkhound_tool_validation.json").read_text(encoding="utf-8"))
            review_md_text = review_md.read_text(encoding="utf-8")
            self.assertEqual(rc, 0)
            self.assertEqual(calls, ["review.step-01.md", "review.md"])
            self.assertEqual(refreshed["status"], "done")
            self.assertTrue(refreshed["chunkhound"]["tool_validation"]["valid"])
            self.assertEqual(refreshed["chunkhound"]["tool_validation"]["evidence_sources"], ["cli_helper_command_execution"])
            self.assertEqual([run["review_stage"] for run in report["runs"]], ["multipass_step", "multipass_synth"])
            self.assertEqual(stage_invocations["review.step-01.md"]["reasoning_effort"], "low")
            self.assertEqual(stage_invocations["review.step-01.md"]["reasoning_effort_source"], "multipass_config")
            self.assertEqual(stage_invocations["review.md"]["reasoning_effort"], "xhigh")
            self.assertEqual(stage_invocations["review.md"]["reasoning_effort_source"], "multipass_config")
            self.assertEqual(refreshed["llm"]["reasoning_effort"], "medium")
            self.assertEqual(refreshed["multipass"]["llm"]["stages"]["step"]["effective_reasoning_effort"], "low")
            self.assertEqual(refreshed["multipass"]["llm"]["stages"]["synth"]["effective_reasoning_effort"], "xhigh")
            self.assertEqual(
                refreshed["multipass"]["llm"]["review_artifact_llm"]["effective_reasoning_effort"],
                "xhigh",
            )
            self.assertEqual(review_md_text.count("<!-- CURE_REVIEW_FOOTER_START -->"), 1)
            self.assertIn("model gpt-5.4/xhigh", review_md_text)
            self.assertIn("session session-1", review_md_text)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_resume_flow_preserves_reused_stage_effort_metadata_under_config_drift(self) -> None:
        root = ROOT / ".tmp_test_resume_stage_effort_metadata_drift"
        cfg = root / "reviewflow.toml"
        valid_step_markdown = "\n".join(
            [
                "### Step Result: 01 — API review",
                "**Focus**: tool proof",
                "",
                "### Steps taken",
                "- checked repo",
                "",
                "### Findings",
                "- Input lacks validation. Evidence: `src/app.py:2`",
                "",
                "### Suggested actions",
                "- Add checks",
                "",
            ]
        )
        valid_synth_markdown = "\n".join(
            [
                "### Steps taken",
                "- Read step output",
                "",
                "**Summary**: ok",
                "",
                "## Business / Product Assessment",
                "**Verdict**: APPROVE",
                "",
                "### Strengths",
                "- Business value is clear. Sources: `src/app.py:2`",
                "",
                "### In Scope Issues",
                "- None.",
                "",
                "### Out of Scope Issues",
                "- None.",
                "",
                "## Technical Assessment",
                "**Verdict**: APPROVE",
                "",
                "### Strengths",
                "- Technical read happened. Sources: `src/app.py:2`",
                "",
                "### In Scope Issues",
                "- None.",
                "",
                "### Out of Scope Issues",
                "- None.",
                "",
                "### Reusability",
                "- Artifact stays inspectable. Sources: `src/app.py:2`",
                "",
            ]
        )
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            base_cfg = root / "chunkhound-base.json"
            base_cfg.write_text("{}", encoding="utf-8")
            cfg.write_text(
                f"[chunkhound]\nbase_config_path = {json.dumps(str(base_cfg))}\n",
                encoding="utf-8",
            )
            session_dir = root / "session-1"
            repo_dir = session_dir / "repo"
            work_dir = session_dir / "work"
            chunkhound_dir = work_dir / "chunkhound"
            repo_dir.mkdir(parents=True, exist_ok=True)
            chunkhound_dir.mkdir(parents=True, exist_ok=True)
            (repo_dir / "src").mkdir(parents=True, exist_ok=True)
            (repo_dir / "src" / "app.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
            plan_json = work_dir / "review_plan.json"
            plan_json.write_text(
                json.dumps(
                    {
                        "abort": False,
                        "abort_reason": None,
                        "jira_keys": ["ABC-1"],
                        "steps": [{"id": "01", "title": "API review", "focus": "tool proof"}],
                    }
                ),
                encoding="utf-8",
            )
            step_output = session_dir / "review.step-01.md"
            step_output.write_text(valid_step_markdown, encoding="utf-8")
            review_md = session_dir / "review.md"
            old_review_md = session_dir / "review.previous.md"
            old_review_md.write_text(valid_synth_markdown, encoding="utf-8")
            step_validation = rf.validate_multipass_step_grounding(
                artifact_path=step_output,
                repo_dir=repo_dir,
                step_index=1,
            )
            synth_validation = rf.validate_multipass_synth_grounding(
                artifact_path=old_review_md,
                step_outputs=[step_output],
                repo_dir=repo_dir,
                work_dir=work_dir,
            )
            meta = {
                "session_id": "session-1",
                "status": "done",
                "created_at": "2026-03-10T00:00:00+00:00",
                "completed_at": "2026-03-10T01:00:00+00:00",
                "pr_url": "https://github.com/acme/repo/pull/9",
                "host": "github.com",
                "owner": "acme",
                "repo": "repo",
                "number": 9,
                "base_ref_for_review": "cure_base__main",
                "llm": {
                    "provider": "codex",
                    "model": "gpt-5.4",
                    "reasoning_effort": "medium",
                    "capabilities": {"supports_resume": True},
                },
                "notes": {"no_index": False},
                "paths": {
                    "session_dir": str(session_dir),
                    "repo_dir": str(repo_dir),
                    "work_dir": str(work_dir),
                    "chunkhound_cwd": str(chunkhound_dir),
                    "chunkhound_db": str(chunkhound_dir / ".chunkhound.db"),
                    "chunkhound_config": str(chunkhound_dir / "chunkhound.json"),
                    "review_md": str(review_md),
                },
                "multipass": {
                    "enabled": True,
                    "plan_json_path": str(plan_json),
                    "grounding_mode": "strict",
                    "artifacts": {"step_outputs": [str(step_output)]},
                    "llm": {
                        "stages": {
                            "plan": {
                                "stage": "plan",
                                "model": "gpt-5.4",
                                "effective_reasoning_effort": "high",
                                "effective_reasoning_effort_source": "inherited",
                            },
                            "step": {
                                "stage": "step",
                                "model": "gpt-5.4",
                                "effective_reasoning_effort": "medium",
                                "effective_reasoning_effort_source": "inherited",
                            },
                            "synth": {
                                "stage": "synth",
                                "model": "gpt-5.4",
                                "effective_reasoning_effort": "medium",
                                "effective_reasoning_effort_source": "inherited",
                            },
                        },
                        "review_artifact_stage": "synth",
                        "review_artifact_llm": {
                            "stage": "synth",
                            "model": "gpt-5.4",
                            "effective_reasoning_effort": "medium",
                            "effective_reasoning_effort_source": "inherited",
                        },
                    },
                    "validation": {
                        "mode": "strict",
                        "invalid_artifacts": ["synth"],
                        "has_invalid_artifacts": True,
                        "artifacts": {
                            "step-01": step_validation,
                            "synth": synth_validation,
                        },
                        "report_path": str(work_dir / "grounding_report.json"),
                    },
                },
            }
            (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

            calls: list[str] = []
            stage_invocations: dict[str, dict[str, object]] = {}

            def fake_run_llm_exec(**kwargs: object) -> rf.LlmRunResult:
                output_path = Path(str(kwargs["output_path"]))
                calls.append(output_path.name)
                resolved = kwargs["resolved"] if isinstance(kwargs.get("resolved"), dict) else {}
                resolution_meta = kwargs["resolution_meta"] if isinstance(kwargs.get("resolution_meta"), dict) else {}
                stage_invocations[output_path.name] = {
                    "reasoning_effort": resolved.get("reasoning_effort"),
                    "plan_reasoning_effort": resolved.get("plan_reasoning_effort"),
                    "reasoning_effort_source": ((resolution_meta.get("resolved") or {}).get("reasoning_effort_source")),
                    "plan_reasoning_effort_source": (
                        (resolution_meta.get("resolved") or {}).get("plan_reasoning_effort_source")
                    ),
                }
                if output_path.name != "review.md":
                    raise AssertionError(f"unexpected rerun path: {output_path}")
                output_path.write_text(valid_synth_markdown, encoding="utf-8")
                adapter_meta = self._write_codex_events(work_dir=work_dir, tool_names=[])
                return rf.LlmRunResult(resume=None, adapter_meta=adapter_meta)

            args = argparse.Namespace(
                session_id="session-1",
                from_phase="auto",
                no_index=False,
                codex_model=None,
                codex_effort=None,
                codex_plan_effort=None,
                quiet=True,
                no_stream=True,
                ui="off",
                verbosity="normal",
            )
            paths = rf.ReviewflowPaths(sandbox_root=root, cache_root=root / "cache")

            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(rf, "ensure_review_config"))
                stack.enter_context(mock.patch.object(rf, "restore_session_chunkhound_db_from_baseline"))
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_chunkhound_runtime_config",
                        return_value=(
                            rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                            {"chunkhound": {"base_config_path": str(base_cfg)}},
                            {"indexing": {"exclude": []}},
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "materialize_chunkhound_env_config",
                        side_effect=self._fake_materialize_chunkhound_env_config,
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_review_intelligence_config",
                        return_value=(
                            _review_intelligence_cfg(),
                            _review_intelligence_meta(_review_intelligence_cfg()),
                        ),
                    )
                )
                stack.enter_context(mock.patch.object(rf, "require_builtin_review_intelligence"))
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "resolve_llm_config_from_args",
                        return_value=(
                            {
                                "provider": "codex",
                                "preset": "test-codex",
                                "model": "gpt-5.4",
                                "reasoning_effort": "medium",
                                "plan_reasoning_effort": "high",
                                "capabilities": {"supports_resume": True},
                            },
                            {
                                "resolved": {
                                    "model_source": "cli",
                                    "reasoning_effort_source": "cli",
                                    "plan_reasoning_effort_source": "preset",
                                }
                            },
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "prepare_review_agent_runtime",
                        return_value=self._codex_runtime_policy(),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_reviewflow_multipass_defaults",
                        return_value=(
                            {
                                "enabled": True,
                                "max_steps": 20,
                                "grounding_mode": "strict",
                                "step_reasoning_effort": "low",
                                "synth_reasoning_effort": "xhigh",
                            },
                            {
                                "multipass": {
                                    "enabled": True,
                                    "max_steps": 20,
                                    "grounding_mode": "strict",
                                    "step_reasoning_effort": "low",
                                    "synth_reasoning_effort": "xhigh",
                                }
                            },
                        ),
                    )
                )
                stack.enter_context(mock.patch.object(rf, "_run_review_intelligence_preflight"))
                stack.enter_context(mock.patch.object(rf, "run_llm_exec", side_effect=fake_run_llm_exec))
                rc = rf.resume_flow(args, paths=paths, config_path=cfg, codex_base_config_path=cfg)

            refreshed = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            review_md_text = review_md.read_text(encoding="utf-8")
            self.assertEqual(rc, 0)
            self.assertEqual(calls, ["review.md"])
            self.assertEqual(stage_invocations["review.md"]["reasoning_effort"], "xhigh")
            self.assertEqual(stage_invocations["review.md"]["reasoning_effort_source"], "multipass_config")
            self.assertEqual(refreshed["multipass"]["llm"]["stages"]["plan"]["effective_reasoning_effort"], "high")
            self.assertEqual(refreshed["multipass"]["llm"]["stages"]["step"]["effective_reasoning_effort"], "medium")
            self.assertEqual(refreshed["multipass"]["llm"]["stages"]["synth"]["effective_reasoning_effort"], "xhigh")
            self.assertEqual(refreshed["multipass"]["llm"]["review_artifact_stage"], "synth")
            self.assertEqual(
                refreshed["multipass"]["llm"]["review_artifact_llm"]["effective_reasoning_effort"],
                "xhigh",
            )
            self.assertIn("model gpt-5.4/xhigh", review_md_text)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_resume_flow_parallel_multipass_reuses_valid_steps_and_reruns_missing_subset(self) -> None:
        root = ROOT / ".tmp_test_codex_tool_proof_resume_parallel_subset"
        cfg = root / "reviewflow.toml"
        valid_synth_markdown = "\n".join(
            [
                "### Steps taken",
                "- Read step outputs",
                "",
                "**Summary**: ok",
                "",
                "## Business / Product Assessment",
                "**Verdict**: APPROVE",
                "",
                "### Strengths",
                "- Business value is clear. Sources: `src/app.py:2`",
                "",
                "### In Scope Issues",
                "- None.",
                "",
                "### Out of Scope Issues",
                "- None.",
                "",
                "## Technical Assessment",
                "**Verdict**: APPROVE",
                "",
                "### Strengths",
                "- Technical read happened. Sources: `src/app.py:2`",
                "",
                "### In Scope Issues",
                "- None.",
                "",
                "### Out of Scope Issues",
                "- None.",
                "",
                "### Reusability",
                "- Artifact stays inspectable. Sources: `src/app.py:2`",
                "",
            ]
        )
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            base_cfg = root / "chunkhound-base.json"
            base_cfg.write_text("{}", encoding="utf-8")
            cfg.write_text(
                f"[chunkhound]\nbase_config_path = {json.dumps(str(base_cfg))}\n",
                encoding="utf-8",
            )
            session_dir = root / "session-1"
            repo_dir = session_dir / "repo"
            work_dir = session_dir / "work"
            chunkhound_dir = work_dir / "chunkhound"
            repo_dir.mkdir(parents=True, exist_ok=True)
            chunkhound_dir.mkdir(parents=True, exist_ok=True)
            (repo_dir / "src").mkdir(parents=True, exist_ok=True)
            (repo_dir / "src" / "app.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
            plan_json = work_dir / "review_plan.json"
            plan_json.write_text(
                json.dumps(
                    {
                        "abort": False,
                        "abort_reason": None,
                        "jira_keys": ["ABC-1"],
                        "steps": [
                            {"id": "01", "title": "API review", "focus": "api"},
                            {"id": "02", "title": "Tests review", "focus": "tests"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            step_one_output = session_dir / "review.step-01.md"
            step_one_output.write_text(
                "\n".join(
                    [
                        "### Step Result: 01 — API review",
                        "**Focus**: api",
                        "",
                        "### Steps taken",
                        "- checked repo",
                        "",
                        "### Findings",
                        "- API concern. Evidence: `src/app.py:2`",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            valid_step_one = rf.validate_multipass_step_grounding(
                artifact_path=step_one_output,
                repo_dir=repo_dir,
                step_index=1,
            )
            rf._update_grounding_state(
                meta={"multipass": {"enabled": True, "grounding_mode": "strict"}},
                work_dir=work_dir,
                grounding_mode="strict",
                result=valid_step_one,
            )
            review_md = session_dir / "review.md"
            meta = {
                "session_id": "session-1",
                "status": "error",
                "created_at": "2026-03-10T00:00:00+00:00",
                "failed_at": "2026-03-10T01:00:00+00:00",
                "pr_url": "https://github.com/acme/repo/pull/9",
                "host": "github.com",
                "owner": "acme",
                "repo": "repo",
                "number": 9,
                "base_ref_for_review": "cure_base__main",
                "llm": {"provider": "codex", "capabilities": {"supports_resume": True}},
                "notes": {"no_index": False},
                "paths": {
                    "session_dir": str(session_dir),
                    "repo_dir": str(repo_dir),
                    "work_dir": str(work_dir),
                    "chunkhound_cwd": str(chunkhound_dir),
                    "chunkhound_db": str(chunkhound_dir / ".chunkhound.db"),
                    "chunkhound_config": str(chunkhound_dir / "chunkhound.json"),
                    "review_md": str(review_md),
                },
                "multipass": {
                    "enabled": True,
                    "plan_json_path": str(plan_json),
                    "grounding_mode": "strict",
                    "validation": {
                        "mode": "strict",
                        "invalid_artifacts": [],
                        "has_invalid_artifacts": False,
                        "artifacts": {"step-01": valid_step_one},
                        "report_path": str(work_dir / "grounding_report.json"),
                    },
                },
            }
            (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

            calls: list[str] = []

            def fake_run_llm_exec(**kwargs: object) -> rf.LlmRunResult:
                output_path = Path(str(kwargs["output_path"]))
                calls.append(output_path.name)
                if output_path.name == "review.step-02.md":
                    output_path.write_text(
                        "\n".join(
                            [
                                "### Step Result: 02 — Tests review",
                                "**Focus**: tests",
                                "",
                                "### Steps taken",
                                "- checked tests",
                                "",
                                "### Findings",
                                "- Test concern. Evidence: `src/app.py:3`",
                                "",
                            ]
                        ),
                        encoding="utf-8",
                    )
                    adapter_meta = self._write_helper_command_events(work_dir=work_dir, commands=["search"])
                elif output_path.name == "review.md":
                    output_path.write_text(valid_synth_markdown, encoding="utf-8")
                    adapter_meta = self._write_codex_events(work_dir=work_dir, tool_names=[])
                else:
                    raise AssertionError(f"unexpected output path: {output_path}")
                return rf.LlmRunResult(resume=None, adapter_meta=adapter_meta)

            args = argparse.Namespace(
                session_id="session-1",
                from_phase="auto",
                no_index=False,
                codex_model=None,
                codex_effort=None,
                codex_plan_effort=None,
                quiet=True,
                no_stream=True,
                ui="off",
                verbosity="normal",
            )
            paths = rf.ReviewflowPaths(sandbox_root=root, cache_root=root / "cache")

            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(rf, "ensure_review_config"))
                stack.enter_context(mock.patch.object(rf, "restore_session_chunkhound_db_from_baseline"))
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_chunkhound_runtime_config",
                        return_value=(
                            rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                            {"chunkhound": {"base_config_path": str(base_cfg)}},
                            {"indexing": {"exclude": []}},
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "materialize_chunkhound_env_config",
                        side_effect=self._fake_materialize_chunkhound_env_config,
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_review_intelligence_config",
                        return_value=(
                            _review_intelligence_cfg(),
                            _review_intelligence_meta(_review_intelligence_cfg()),
                        ),
                    )
                )
                stack.enter_context(mock.patch.object(rf, "require_builtin_review_intelligence"))
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "resolve_llm_config_from_args",
                        return_value=(
                            {"provider": "codex", "preset": "test-codex", "capabilities": {"supports_resume": True}},
                            {},
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "prepare_review_agent_runtime",
                        return_value=self._codex_runtime_policy(),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "load_reviewflow_multipass_defaults",
                        return_value=(
                            {
                                "enabled": True,
                                "max_steps": 20,
                                "step_workers": 2,
                                "grounding_mode": "strict",
                            },
                            {
                                "multipass": {
                                    "enabled": True,
                                    "max_steps": 20,
                                    "step_workers": 2,
                                    "grounding_mode": "strict",
                                }
                            },
                        ),
                    )
                )
                stack.enter_context(mock.patch.object(rf, "_run_review_intelligence_preflight"))
                stack.enter_context(mock.patch.object(rf, "run_llm_exec", side_effect=fake_run_llm_exec))
                rc = rf.resume_flow(args, paths=paths, config_path=cfg, codex_base_config_path=cfg)

            refreshed = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(rc, 0)
            self.assertEqual(calls, ["review.step-02.md", "review.md"])
            self.assertEqual(refreshed["status"], "done")
            self.assertEqual(refreshed["multipass"]["step_workers"], 2)
            self.assertEqual(refreshed["multipass"]["effective_step_workers"], 1)
            self.assertEqual(
                [item["status"] for item in refreshed["multipass"]["step_states"]],
                ["reused", "completed"],
            )
            self.assertEqual(
                refreshed["multipass"]["artifacts"]["step_outputs"],
                [
                    str(session_dir / "review.step-01.md"),
                    str(session_dir / "review.step-02.md"),
                ],
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)


class ExtractionOwnershipTests(unittest.TestCase):
    def _runtime(self) -> argparse.Namespace:
        return argparse.Namespace(
            paths=rf.ReviewflowPaths(
                sandbox_root=Path("/tmp/reviewflow-sandboxes"),
                cache_root=Path("/tmp/reviewflow-cache"),
            ),
            config_path=Path("/tmp/reviewflow.toml"),
            codex_base_config_path=Path("/tmp/codex.toml"),
        )

    def test_reviewflow_reexports_active_extracted_owners(self) -> None:
        import cure_commands as command_surface  # noqa: E402
        import cure_flows as flow_surface  # noqa: E402

        self.assertIs(rf.render_prompt, flow_surface.render_prompt)
        self.assertIs(rf.resolve_prompt_profile, flow_surface.resolve_prompt_profile)
        self.assertIs(rf.resolve_pr_review_baseline_selection, flow_surface.resolve_pr_review_baseline_selection)
        self.assertIs(
            rf.restore_session_chunkhound_db_from_baseline,
            flow_surface.restore_session_chunkhound_db_from_baseline,
        )
        self.assertIs(rf.commands_flow, command_surface.commands_flow)
        self.assertIs(rf.status_flow, command_surface.status_flow)
        self.assertIs(rf.watch_flow, command_surface.watch_flow)
        self.assertIs(rf.doctor_flow, command_surface.doctor_flow)

    def test_main_dispatches_pr_through_cure_commands(self) -> None:
        runtime = self._runtime()
        with mock.patch("cure_runtime.resolve_runtime", return_value=runtime) as resolve_runtime, mock.patch(
            "cure_commands.pr_flow",
            return_value=23,
        ) as pr_flow:
            rc = rf.main(["pr", "https://github.com/acme/repo/pull/1"])

        self.assertEqual(rc, 23)
        resolve_runtime.assert_called_once()
        self.assertEqual(pr_flow.call_count, 1)
        self.assertEqual(pr_flow.call_args.args[0].pr_url, "https://github.com/acme/repo/pull/1")
        self.assertEqual(pr_flow.call_args.kwargs["paths"], runtime.paths)
        self.assertEqual(pr_flow.call_args.kwargs["config_path"], runtime.config_path)
        self.assertEqual(pr_flow.call_args.kwargs["codex_base_config_path"], runtime.codex_base_config_path)

    def test_main_dispatches_status_through_cure_commands(self) -> None:
        runtime = self._runtime()
        with mock.patch("cure_runtime.resolve_runtime", return_value=runtime) as resolve_runtime, mock.patch(
            "cure_commands.status_flow",
            return_value=17,
        ) as status_flow:
            rc = rf.main(["status", "session-123", "--json"])

        self.assertEqual(rc, 17)
        resolve_runtime.assert_called_once()
        self.assertEqual(status_flow.call_count, 1)
        self.assertEqual(status_flow.call_args.args[0].target, "session-123")
        self.assertTrue(status_flow.call_args.args[0].json_output)
        self.assertEqual(status_flow.call_args.kwargs["paths"], runtime.paths)

    def test_main_dispatches_doctor_through_cure_commands(self) -> None:
        runtime = self._runtime()
        with mock.patch("cure_runtime.resolve_runtime", return_value=runtime) as resolve_runtime, mock.patch(
            "cure_commands.doctor_flow",
            return_value=11,
        ) as doctor_flow:
            rc = rf.main(["doctor", "--json"])

        self.assertEqual(rc, 11)
        resolve_runtime.assert_called_once()
        self.assertEqual(doctor_flow.call_count, 1)
        self.assertTrue(doctor_flow.call_args.args[0].json_output)
        self.assertIs(doctor_flow.call_args.kwargs["runtime"], runtime)

    def test_console_main_dispatches_for_reviewflow_argv_without_warning(self) -> None:
        stderr = StringIO()
        with mock.patch.object(rf, "main", return_value=7) as main_mock, mock.patch.object(
            sys,
            "argv",
            ["reviewflow", "commands", "--json"],
        ), mock.patch.object(sys, "stderr", stderr):
            rc = rf.console_main()

        self.assertEqual(rc, 7)
        self.assertEqual(stderr.getvalue(), "")
        main_mock.assert_called_once_with(["commands", "--json"], prog="cure")
