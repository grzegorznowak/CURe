# ruff: noqa: F403, F405
from typing import Any

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

    def test_normalize_markdown_artifact_removes_stray_hash_delimiter_lines(self) -> None:
        session_dir = ROOT / ".tmp_test_norm_session5"
        md = session_dir / "review.md"
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            md.write_text(
                "\n".join(
                    [
                        "## Technical Assessment",
                        "**Verdict**: APPROVE",
                        "####",
                        "#### Valid Heading",
                        "- None.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            rf.normalize_markdown_artifact(markdown_path=md, session_dir=session_dir)
            normalized = md.read_text(encoding="utf-8")
            self.assertNotIn("\n####\n", "\n" + normalized + "\n")
            self.assertIn("#### Valid Heading", normalized)
        finally:
            shutil.rmtree(session_dir, ignore_errors=True)

    def test_normalize_markdown_artifact_preserves_hash_delimiters_inside_fenced_blocks(self) -> None:
        session_dir = ROOT / ".tmp_test_norm_session6"
        md = session_dir / "review.md"
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            md.write_text(
                "\n".join(
                    [
                        "## Technical Assessment",
                        "####",
                        "```text",
                        "####",
                        "literal sample",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            rf.normalize_markdown_artifact(markdown_path=md, session_dir=session_dir)
            normalized = md.read_text(encoding="utf-8")
            self.assertNotIn("\n## Technical Assessment\n####\n```text", "\n" + normalized)
            self.assertIn("```text\n####\nliteral sample\n```", normalized)
        finally:
            shutil.rmtree(session_dir, ignore_errors=True)

    def test_normalize_markdown_artifact_strips_llm_preamble(self) -> None:
        session_dir = ROOT / ".tmp_test_norm_preamble"
        md = session_dir / "review.step-01.md"
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            md.write_text(
                "\n".join(
                    [
                        "I now have all the context needed. Let me produce the review output.",
                        "",
                        "### Step Result: 01 — Safety review",
                        "**Focus**: Check safety.",
                        "",
                        "### Findings",
                        "- None.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            rf.normalize_markdown_artifact(markdown_path=md, session_dir=session_dir)
            normalized = md.read_text(encoding="utf-8")
            self.assertTrue(
                normalized.startswith("### Step Result:"),
                f"Expected preamble to be stripped, got: {normalized[:80]!r}",
            )
            self.assertNotIn("context needed", normalized)
            self.assertIn("### Findings", normalized)
        finally:
            shutil.rmtree(session_dir, ignore_errors=True)

    def test_normalize_markdown_artifact_preserves_text_starting_with_heading(self) -> None:
        session_dir = ROOT / ".tmp_test_norm_no_preamble"
        md = session_dir / "review.step-01.md"
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            original = "### Step Result: 01 — Safety review\n**Focus**: Check safety.\n"
            md.write_text(original, encoding="utf-8")
            rf.normalize_markdown_artifact(markdown_path=md, session_dir=session_dir)
            self.assertEqual(md.read_text(encoding="utf-8"), original)
        finally:
            shutil.rmtree(session_dir, ignore_errors=True)

    def test_normalize_markdown_artifact_unchanged_when_no_heading_present(self) -> None:
        session_dir = ROOT / ".tmp_test_norm_no_heading"
        md = session_dir / "review.step-01.md"
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            original = "Just plain text with no heading.\nAnother line.\n"
            md.write_text(original, encoding="utf-8")
            rf.normalize_markdown_artifact(markdown_path=md, session_dir=session_dir)
            self.assertEqual(md.read_text(encoding="utf-8"), original)
        finally:
            shutil.rmtree(session_dir, ignore_errors=True)

    def test_normalize_markdown_artifact_unchanged_for_deeper_heading_at_line_zero(self) -> None:
        session_dir = ROOT / ".tmp_test_norm_deep_heading"
        md = session_dir / "review.step-01.md"
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            original = "#### Deep Heading At Line Zero\nSome content here.\n"
            md.write_text(original, encoding="utf-8")
            rf.normalize_markdown_artifact(markdown_path=md, session_dir=session_dir)
            self.assertEqual(md.read_text(encoding="utf-8"), original)
        finally:
            shutil.rmtree(session_dir, ignore_errors=True)

    def test_normalize_markdown_artifact_strips_blank_lines_before_heading(self) -> None:
        session_dir = ROOT / ".tmp_test_norm_blank_before_heading"
        md = session_dir / "review.step-01.md"
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            md.write_text(
                "\n".join(
                    [
                        "",
                        "",
                        "## Review Findings",
                        "- Something important.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            rf.normalize_markdown_artifact(markdown_path=md, session_dir=session_dir)
            normalized = md.read_text(encoding="utf-8")
            self.assertTrue(
                normalized.startswith("## Review Findings"),
                f"Expected blank preamble to be stripped, got: {normalized[:80]!r}",
            )
        finally:
            shutil.rmtree(session_dir, ignore_errors=True)

    def test_normalize_markdown_artifact_crlf_input_structurally_correct(self) -> None:
        session_dir = ROOT / ".tmp_test_norm_crlf"
        md = session_dir / "review.step-01.md"
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            md.write_bytes(
                b"Let me produce the output.\r\n\r\n## Step Result\r\nContent here.\r\n"
            )
            rf.normalize_markdown_artifact(markdown_path=md, session_dir=session_dir)
            normalized = md.read_text(encoding="utf-8")
            self.assertTrue(
                normalized.startswith("## Step Result"),
                f"Expected CRLF preamble stripped, got: {normalized[:80]!r}",
            )
            self.assertNotIn("produce the output", normalized)
            self.assertIn("Content here.", normalized)
        finally:
            shutil.rmtree(session_dir, ignore_errors=True)

    def test_format_review_artifact_footer_renders_expected_v1_contract(self) -> None:
        version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
        footer = cure_output.format_review_artifact_footer(
            cure_version=version,
            stage_shape_label="multi-stage - stages: 4",
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
            f"_review generated with [CURe](https://github.com/grzegorznowak/CURe) v. {version} · multi-stage - stages: 4 · sha sha1234 · model gpt-5.2/high · tok 18k/4k/23k · session 20260322-abc123 · 6m12s_",
        )

    def test_format_review_artifact_footer_renders_single_stage_contract(self) -> None:
        version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
        footer = cure_output.format_review_artifact_footer(
            cure_version=version,
            stage_shape_label="single-stage",
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
            f"_review generated with [CURe](https://github.com/grzegorznowak/CURe) v. {version} · single-stage · sha sha1234 · model gpt-5.2/high · tok 18k/4k/23k · session 20260322-abc123 · 6m12s_",
        )

    def test_refresh_session_review_footer_prefers_resumed_at_for_elapsed_window(self) -> None:
        session_dir = ROOT / ".tmp_test_review_footer_resume_elapsed"
        md = session_dir / "review.md"
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            md.write_text(_sectioned_review_markdown(business="APPROVE", technical="APPROVE"), encoding="utf-8")

            rf._refresh_session_review_footer(
                meta={
                    "session_id": "session-1",
                    "created_at": "2026-03-10T00:00:00+00:00",
                    "resumed_at": "2026-03-12T22:00:00+00:00",
                    "completed_at": "2026-03-12T22:00:07+00:00",
                    "review_head_sha": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
                    "llm": {
                        "model": "gpt-5.4",
                        "reasoning_effort": "medium",
                        "usage": {"input_tokens": 1200, "output_tokens": 300, "total_tokens": 1500},
                    },
                },
                markdown_path=md,
            )

            rendered = md.read_text(encoding="utf-8")
            self.assertIn("review generated with [CURe]", rendered)
            self.assertIn(" · 7s_", rendered)
            self.assertNotIn("70h", rendered)
        finally:
            shutil.rmtree(session_dir, ignore_errors=True)

    def test_refresh_session_review_footer_prefers_runtime_adapter_model_when_top_level_missing(self) -> None:
        session_dir = ROOT / ".tmp_test_review_footer_runtime_model"
        md = session_dir / "review.md"
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            md.write_text(_sectioned_review_markdown(business="APPROVE", technical="APPROVE"), encoding="utf-8")

            rf._refresh_session_review_footer(
                meta={
                    "session_id": "session-claude",
                    "created_at": "2026-03-12T22:00:00+00:00",
                    "completed_at": "2026-03-12T22:00:07+00:00",
                    "review_head_sha": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
                    "llm": {
                        "preset": "claude-cli",
                        "provider": "claude",
                        "model": None,
                        "reasoning_effort": "high",
                        "adapter": {
                            "provider": "claude",
                            "model": "claude-sonnet-4-6",
                        },
                        "usage": {"input_tokens": 1200, "output_tokens": 300, "total_tokens": 1500},
                    },
                },
                markdown_path=md,
            )

            rendered = md.read_text(encoding="utf-8")
            self.assertIn("model claude-sonnet-4-6/high", rendered)
            self.assertNotIn("model -/high", rendered)
        finally:
            shutil.rmtree(session_dir, ignore_errors=True)

    def test_upsert_review_artifact_footer_is_idempotent_and_replaces_existing_footer(self) -> None:
        session_dir = ROOT / ".tmp_test_review_footer_upsert"
        md = session_dir / "review.md"
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            md.write_text(_sectioned_review_markdown(business="APPROVE", technical="APPROVE"), encoding="utf-8")

            cure_output.upsert_review_artifact_footer(
                markdown_path=md,
                footer_line="_review generated with [CURe](https://github.com/grzegorznowak/CURe) v. 0.1.4 · single-stage · sha abc1234 · model gpt-5.2/high · tok 1k/2k/3k · session s1 · 5m0s_",
            )
            cure_output.upsert_review_artifact_footer(
                markdown_path=md,
                footer_line="_review generated with [CURe](https://github.com/grzegorznowak/CURe) v. 0.1.4 · multi-stage - stages: 4 · sha def5678 · model gpt-5.2/high · tok 4k/5k/9k · session s1 · 7m0s_",
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
                "CURE_CHUNKHOUND_DRY_RUN": "1",
            },
            codex_flags=["-m", "gpt-5.2", "--search", "--sandbox", "danger-full-access"],
            codex_config_overrides=['mcp_servers.chunkhound.command="chunkhound"'],
            add_dirs=[session_dir],
        )

        self.assertIn(f"cd {repo_dir}", cmd)
        self.assertIn("env GH_CONFIG_DIR=", cmd)
        self.assertIn("CURE_WORK_DIR=", cmd)
        self.assertIn("CURE_CHUNKHOUND_DRY_RUN=", cmd)
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
    class _FakeTty(StringIO):
        def isatty(self) -> bool:
            return True

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
                with (
                    mock.patch.object(
                        rf,
                        "load_chunkhound_runtime_config",
                        return_value=(
                            rf.ReviewflowChunkHoundConfig(
                                base_config_path=ROOT / ".tmp_chunkhound_base.json"
                            ),
                            {"chunkhound": {"base_config_path": "/tmp/base.json"}},
                            {"indexing": {"exclude": []}},
                        ),
                    ),
                    mock.patch.object(
                        cure_flows,
                        "load_chunkhound_runtime_config",
                        return_value=(
                            rf.ReviewflowChunkHoundConfig(
                                base_config_path=ROOT / ".tmp_chunkhound_base.json"
                            ),
                            {"chunkhound": {"base_config_path": "/tmp/base.json"}},
                            {"indexing": {"exclude": []}},
                        ),
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
            self.assertEqual(called["kwargs"]["reason"], "config changed")
        finally:
            shutil.rmtree(tmp_sandbox, ignore_errors=True)
            shutil.rmtree(tmp_cache, ignore_errors=True)

    def test_ensure_base_cache_rebuilds_when_compatibility_canary_rejects_reuse(self) -> None:
        tmp_cache = Path(tempfile.mkdtemp(prefix="cure_test_cache_version_canary_reject_", dir=ROOT))
        tmp_sandbox = Path(tempfile.mkdtemp(prefix="cure_test_sandbox_version_canary_reject_", dir=ROOT))
        try:
            paths = rf.ReviewflowPaths(
                sandbox_root=tmp_sandbox,
                cache_root=tmp_cache,
                review_chunkhound_config=ROOT / ".tmp_unused_review_cfg.json",
                main_chunkhound_config=ROOT / ".tmp_unused_main_cfg.json",
            )
            pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=1)
            base_ref = "main"
            chunkhound_meta = {"chunkhound": {"base_config_path": "/tmp/base.json"}}
            cfg_fp = rf.fingerprint_chunkhound_reviewflow_config(chunkhound_meta)

            base_root = rf.base_dir(paths, pr.host, pr.owner, pr.repo, base_ref)
            base_root.mkdir(parents=True, exist_ok=True)
            db_path = base_root / "db" / ".chunkhound.db"
            db_path.mkdir(parents=True, exist_ok=True)
            (db_path / "chunks.db").write_text("stale", encoding="utf-8")
            meta_path = base_root / "meta.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "indexed_at": "3026-03-05T00:00:00+00:00",
                        "config_fingerprint": cfg_fp,
                        "chunkhound_version": "chunkhound old",
                        "db_path": str(db_path),
                    }
                ),
                encoding="utf-8",
            )

            called: dict[str, object] = {}

            def fake_cache_prime_locked(**kwargs):  # type: ignore[no-untyped-def]
                called["kwargs"] = kwargs
                return {"primed": True}

            with (
                mock.patch.object(
                    rf,
                    "cache_prime",
                    side_effect=AssertionError("public cache_prime wrapper should not be called"),
                ),
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(
                            base_config_path=ROOT / ".tmp_chunkhound_base.json"
                        ),
                        chunkhound_meta,
                        {"indexing": {"exclude": []}},
                    ),
                ),
                mock.patch.object(
                    cure_flows,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(
                            base_config_path=ROOT / ".tmp_chunkhound_base.json"
                        ),
                        chunkhound_meta,
                        {"indexing": {"exclude": []}},
                    ),
                ),
                mock.patch.object(
                    rf,
                    "run_cmd",
                    return_value=mock.Mock(
                        stdout="chunkhound new\n",
                        stderr="",
                        duration_seconds=0.0,
                    ),
                ),
                mock.patch.object(
                    cure_flows,
                    "_cache_prime_locked",
                    side_effect=fake_cache_prime_locked,
                ) as cache_prime_locked,
                mock.patch.object(
                    cure_flows,
                    "_run_base_cache_compatibility_canary",
                    return_value={
                        "checked_at": "2026-03-30T07:00:00+00:00",
                        "cached_chunkhound_version": "chunkhound old",
                        "current_chunkhound_version": "chunkhound new",
                        "decision": "rebuild",
                        "result": "probe_failed",
                        "reason": "compatibility canary exited with code 134",
                        "probe_timeout_seconds": 30,
                    },
                ) as canary,
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

            canary.assert_called_once()
            cache_prime_locked.assert_called_once()
            self.assertTrue(out["primed"])
            self.assertEqual(out["compatibility"]["decision"], "rebuild")
            self.assertEqual(out["cache_origin"], "fresh_rebuild")
            self.assertIn("kwargs", called)
            self.assertEqual(
                called["kwargs"]["reason"],
                "ChunkHound compatibility canary rejected reuse (chunkhound old -> chunkhound new)",
            )
        finally:
            shutil.rmtree(tmp_sandbox, ignore_errors=True)
            shutil.rmtree(tmp_cache, ignore_errors=True)

    def test_public_ensure_base_cache_canary_reject_rebuild_completes_without_deadlock(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="cure_test_cache_reject_subprocess_", dir=ROOT))
        try:
            import textwrap

            script = textwrap.dedent(
                """
                import json
                import sys
                import tempfile
                from pathlib import Path
                from unittest import mock

                import cure as rf
                import cure_flows

                root = Path(sys.argv[1])
                cache_root = root / "cache"
                sandbox_root = root / "sandbox"
                seed_root = root / "seed"
                cache_root.mkdir(parents=True, exist_ok=True)
                sandbox_root.mkdir(parents=True, exist_ok=True)
                seed_root.mkdir(parents=True, exist_ok=True)

                base_cfg = root / "chunkhound-base.json"
                base_cfg.write_text(
                    json.dumps({"embedding": {"provider": "openai", "model": "text-embedding-3-small"}}),
                    encoding="utf-8",
                )

                paths = rf.ReviewflowPaths(
                    sandbox_root=sandbox_root,
                    cache_root=cache_root,
                    review_chunkhound_config=root / "reviewflow.toml",
                    main_chunkhound_config=root / "chunkhound.toml",
                )
                pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=1)
                base_ref = "main"
                chunkhound_meta = {"chunkhound": {"base_config_path": str(base_cfg)}}
                cfg_fp = rf.fingerprint_chunkhound_reviewflow_config(chunkhound_meta)

                base_root = rf.base_dir(paths, pr.host, pr.owner, pr.repo, base_ref)
                db_path = base_root / "db" / ".chunkhound.db"
                db_path.mkdir(parents=True, exist_ok=True)
                (db_path / "chunks.db").write_text("stale", encoding="utf-8")
                meta_path = base_root / "meta.json"
                meta_path.parent.mkdir(parents=True, exist_ok=True)
                meta_path.write_text(
                    json.dumps(
                        {
                            "indexed_at": "3026-03-05T00:00:00+00:00",
                            "config_fingerprint": cfg_fp,
                            "chunkhound_version": "chunkhound old",
                            "db_path": str(db_path),
                        }
                    ),
                    encoding="utf-8",
                )

                def fake_materialize(
                    *,
                    resolved_config,
                    output_config_path,
                    database_provider,
                    database_path,
                ):
                    output_config_path.parent.mkdir(parents=True, exist_ok=True)
                    output_config_path.write_text("{}", encoding="utf-8")
                    database_path.parent.mkdir(parents=True, exist_ok=True)

                def fake_run_cmd(cmd, **kwargs):
                    if cmd == ["chunkhound", "--version"]:
                        return mock.Mock(stdout="chunkhound new\\n", stderr="", duration_seconds=0.0)
                    if cmd[:2] == ["chunkhound", "index"]:
                        target = base_root / "db" / ".chunkhound.db"
                        target.mkdir(parents=True, exist_ok=True)
                        (target / "chunks.db").write_text("fresh", encoding="utf-8")
                        return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
                    if cmd[:1] == ["git"]:
                        return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
                    raise AssertionError(f"unexpected command: {cmd}")

                with (
                    mock.patch.object(rf, "ensure_review_config"),
                    mock.patch.object(cure_flows, "ensure_review_config"),
                    mock.patch.object(
                        rf,
                        "load_chunkhound_runtime_config",
                        return_value=(
                            rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                            chunkhound_meta,
                            {"embedding": {"provider": "openai", "model": "text-embedding-3-small"}},
                        ),
                    ),
                    mock.patch.object(
                        cure_flows,
                        "load_chunkhound_runtime_config",
                        return_value=(
                            rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                            chunkhound_meta,
                            {"embedding": {"provider": "openai", "model": "text-embedding-3-small"}},
                        ),
                    ),
                    mock.patch.object(rf, "materialize_chunkhound_env_config", side_effect=fake_materialize),
                    mock.patch.object(cure_flows, "materialize_chunkhound_env_config", side_effect=fake_materialize),
                    mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd),
                    mock.patch.object(cure_flows, "_run_cmd", side_effect=fake_run_cmd),
                    mock.patch.object(rf, "seed_dir", return_value=seed_root),
                    mock.patch.object(
                        cure_flows,
                        "_sync_seed_checkout",
                        return_value=(seed_root, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"),
                    ),
                    mock.patch.object(
                        cure_flows,
                        "_run_base_cache_compatibility_canary",
                        return_value={
                            "checked_at": "2026-04-04T09:13:33+00:00",
                            "cached_chunkhound_version": "chunkhound old",
                            "current_chunkhound_version": "chunkhound new",
                            "decision": "rebuild",
                            "result": "probe_failed",
                            "reason": "compatibility canary exited with code 134",
                            "probe_timeout_seconds": 30,
                        },
                    ),
                ):
                    result = rf.ensure_base_cache(
                        paths=paths,
                        config_path=root / "reviewflow.toml",
                        pr=pr,
                        base_ref=base_ref,
                        ttl_hours=24,
                        refresh=False,
                        quiet=True,
                        no_stream=True,
                    )

                print(json.dumps({"cache_origin": result["cache_origin"], "db_path": result["db_path"]}))
                """
            )

            completed = subprocess.run(
                [sys.executable, "-c", script, str(root)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            payload = json.loads(completed.stdout.strip())
            self.assertEqual(payload["cache_origin"], "fresh_rebuild")
            self.assertTrue(Path(payload["db_path"]).exists())
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_restore_session_chunkhound_db_from_baseline_refreshes_stale_base_cache(self) -> None:
        root = ROOT / ".tmp_test_restore_chunkhound_db_version_mismatch"
        try:
            shutil.rmtree(root, ignore_errors=True)
            cache_root = root / "cache"
            sandbox_root = root / "sandbox"
            cache_root.mkdir(parents=True, exist_ok=True)
            sandbox_root.mkdir(parents=True, exist_ok=True)
            stale_db = root / "stale-db"
            fresh_db = root / "fresh-db"
            stale_db.mkdir(parents=True, exist_ok=True)
            fresh_db.mkdir(parents=True, exist_ok=True)
            (stale_db / "chunks.db").write_text("stale", encoding="utf-8")
            (fresh_db / "chunks.db").write_text("fresh", encoding="utf-8")
            chunkhound_db_path = root / "session" / "work" / "chunkhound" / ".chunkhound.db"

            paths = rf.ReviewflowPaths(
                sandbox_root=sandbox_root,
                cache_root=cache_root,
                review_chunkhound_config=ROOT / ".tmp_unused_review_cfg.json",
                main_chunkhound_config=ROOT / ".tmp_unused_main_cfg.json",
            )
            pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=1)
            meta = {
                "base_cache": {
                    "db_path": str(stale_db),
                    "chunkhound_version": "chunkhound old",
                },
                "baseline_selection": {
                    "selected_baseline_ref": "main",
                },
            }

            with (
                mock.patch.object(
                    rf,
                    "ensure_base_cache",
                    return_value={
                        "db_path": str(fresh_db),
                        "chunkhound_version": "chunkhound new",
                    },
                ) as ensure_base_cache,
                mock.patch.object(
                    rf,
                    "run_cmd",
                    return_value=mock.Mock(
                        stdout="chunkhound new\n",
                        stderr="",
                        duration_seconds=0.0,
                    ),
                ),
            ):
                restored = rf.restore_session_chunkhound_db_from_baseline(
                    meta=meta,
                    paths=paths,
                    config_path=None,
                    pr=pr,
                    chunkhound_db_path=chunkhound_db_path,
                    quiet=True,
                    no_stream=True,
                )

            ensure_base_cache.assert_called_once()
            self.assertEqual(restored["db_path"], str(fresh_db))
            self.assertEqual((chunkhound_db_path / "chunks.db").read_text(encoding="utf-8"), "fresh")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_restore_session_chunkhound_db_from_baseline_replaces_stale_session_db(self) -> None:
        root = ROOT / ".tmp_test_restore_session_db_version_mismatch"
        try:
            shutil.rmtree(root, ignore_errors=True)
            cache_root = root / "cache"
            sandbox_root = root / "sandbox"
            cache_root.mkdir(parents=True, exist_ok=True)
            sandbox_root.mkdir(parents=True, exist_ok=True)
            stale_db = root / "stale-db"
            fresh_db = root / "fresh-db"
            stale_db.mkdir(parents=True, exist_ok=True)
            fresh_db.mkdir(parents=True, exist_ok=True)
            (stale_db / "chunks.db").write_text("stale", encoding="utf-8")
            (fresh_db / "chunks.db").write_text("fresh", encoding="utf-8")
            chunkhound_db_path = root / "session" / "work" / "chunkhound" / ".chunkhound.db"
            chunkhound_db_path.mkdir(parents=True, exist_ok=True)
            (chunkhound_db_path / "chunks.db").write_text("session-stale", encoding="utf-8")

            paths = rf.ReviewflowPaths(
                sandbox_root=sandbox_root,
                cache_root=cache_root,
                review_chunkhound_config=ROOT / ".tmp_unused_review_cfg.json",
                main_chunkhound_config=ROOT / ".tmp_unused_main_cfg.json",
            )
            pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=1)
            meta = {
                "base_cache": {
                    "db_path": str(stale_db),
                    "chunkhound_version": "chunkhound old",
                },
                "baseline_selection": {
                    "selected_baseline_ref": "main",
                },
            }

            with (
                mock.patch.object(
                    rf,
                    "ensure_base_cache",
                    return_value={
                        "db_path": str(fresh_db),
                        "chunkhound_version": "chunkhound new",
                    },
                ) as ensure_base_cache,
                mock.patch.object(
                    rf,
                    "run_cmd",
                    return_value=mock.Mock(
                        stdout="chunkhound new\n",
                        stderr="",
                        duration_seconds=0.0,
                    ),
                ),
            ):
                restored = rf.restore_session_chunkhound_db_from_baseline(
                    meta=meta,
                    paths=paths,
                    config_path=None,
                    pr=pr,
                    chunkhound_db_path=chunkhound_db_path,
                    quiet=True,
                    no_stream=True,
                )

            ensure_base_cache.assert_called_once()
            self.assertEqual(restored["db_path"], str(fresh_db))
            self.assertEqual((chunkhound_db_path / "chunks.db").read_text(encoding="utf-8"), "fresh")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_ensure_base_cache_cold_miss_uses_operator_seed_resolver(self) -> None:
        tmp_cache = ROOT / ".tmp_test_cache_hot_start_resolver"
        tmp_sandbox = ROOT / ".tmp_test_sandbox_hot_start_resolver"
        try:
            shutil.rmtree(tmp_cache, ignore_errors=True)
            shutil.rmtree(tmp_sandbox, ignore_errors=True)
            tmp_cache.mkdir(parents=True, exist_ok=True)
            tmp_sandbox.mkdir(parents=True, exist_ok=True)

            paths = rf.ReviewflowPaths(
                sandbox_root=tmp_sandbox,
                cache_root=tmp_cache,
                review_chunkhound_config=ROOT / ".tmp_unused_review_cfg.json",
                main_chunkhound_config=ROOT / ".tmp_unused_main_cfg.json",
            )
            pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=1)

            hot_start_seed = {
                "source_kind": "operator_workspace_config",
                "workspace_path": "/tmp/workspace",
                "config_path": "/tmp/workspace/chunkhound.json",
                "db_path": "/tmp/workspace/.chunkhound",
                "target_match_state": "match",
                "runtime_match_state": "compatible",
            }
            called: dict[str, object] = {}

            def fake_cache_prime(**kwargs):  # type: ignore[no-untyped-def]
                called["kwargs"] = kwargs
                return {"primed": True}

            with (
                mock.patch.object(rf, "cache_prime", side_effect=fake_cache_prime),
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(
                            base_config_path=ROOT / ".tmp_chunkhound_base.json"
                        ),
                        {"chunkhound": {"base_config_path": "/tmp/base.json"}},
                        {"indexing": {"exclude": []}},
                    ),
                ),
                mock.patch.object(
                    rf,
                    "prompt_operator_chunkhound_base_cache_hot_start",
                    return_value=hot_start_seed,
                ) as prompt_hot_start,
            ):
                out = rf.ensure_base_cache(
                    paths=paths,
                    pr=pr,
                    base_ref="main",
                    ttl_hours=24,
                    refresh=False,
                    quiet=True,
                    no_stream=True,
                )

            self.assertEqual(out, {"primed": True})
            prompt_hot_start.assert_called_once()
            self.assertEqual(called["kwargs"]["hot_start_seed"], hot_start_seed)
            self.assertEqual(called["kwargs"]["reason"], "cache miss")
        finally:
            shutil.rmtree(tmp_sandbox, ignore_errors=True)
            shutil.rmtree(tmp_cache, ignore_errors=True)

    def test_ensure_base_cache_hit_skips_operator_hot_start_prompt(self) -> None:
        tmp_cache = ROOT / ".tmp_test_cache_hot_start_hit"
        tmp_sandbox = ROOT / ".tmp_test_sandbox_hot_start_hit"
        try:
            shutil.rmtree(tmp_cache, ignore_errors=True)
            shutil.rmtree(tmp_sandbox, ignore_errors=True)
            tmp_cache.mkdir(parents=True, exist_ok=True)
            tmp_sandbox.mkdir(parents=True, exist_ok=True)

            paths = rf.ReviewflowPaths(
                sandbox_root=tmp_sandbox,
                cache_root=tmp_cache,
                review_chunkhound_config=ROOT / ".tmp_unused_review_cfg.json",
                main_chunkhound_config=ROOT / ".tmp_unused_main_cfg.json",
            )
            pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=1)
            base_root = rf.base_dir(paths, pr.host, pr.owner, pr.repo, "main")
            base_root.mkdir(parents=True, exist_ok=True)
            (base_root / "meta.json").write_text(
                json.dumps(
                    {
                        "indexed_at": "3026-03-26T00:00:00+00:00",
                        "config_fingerprint": "stable",
                        "chunkhound_version": "chunkhound stable",
                    }
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(
                            base_config_path=ROOT / ".tmp_chunkhound_base.json"
                        ),
                        {"chunkhound": {"base_config_path": "/tmp/base.json"}},
                        {"indexing": {"exclude": []}},
                    ),
                ),
                mock.patch.object(
                    cure_flows,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(
                            base_config_path=ROOT / ".tmp_chunkhound_base.json"
                        ),
                        {"chunkhound": {"base_config_path": "/tmp/base.json"}},
                        {"indexing": {"exclude": []}},
                    ),
                ),
                mock.patch.object(rf, "fingerprint_chunkhound_reviewflow_config", return_value="stable"),
                mock.patch.object(cure_flows, "fingerprint_chunkhound_reviewflow_config", return_value="stable"),
                mock.patch.object(
                    rf,
                    "run_cmd",
                    return_value=mock.Mock(
                        stdout="chunkhound stable\n",
                        stderr="",
                        duration_seconds=0.0,
                    ),
                ),
                mock.patch.object(
                    rf,
                    "prompt_operator_chunkhound_base_cache_hot_start",
                    side_effect=AssertionError("should not prompt on cache hit"),
                ),
                mock.patch.object(
                    cure_flows,
                    "_run_base_cache_compatibility_canary",
                    side_effect=AssertionError("should not probe on version match"),
                ),
            ):
                out = rf.ensure_base_cache(
                    paths=paths,
                    pr=pr,
                    base_ref="main",
                    ttl_hours=24,
                    refresh=False,
                    quiet=True,
                    no_stream=True,
                )

            self.assertEqual(out["config_fingerprint"], "stable")
        finally:
            shutil.rmtree(tmp_sandbox, ignore_errors=True)
            shutil.rmtree(tmp_cache, ignore_errors=True)

    def test_ensure_base_cache_version_mismatch_promotes_compatible_cache(self) -> None:
        tmp_cache = ROOT / ".tmp_test_cache_version_canary_success"
        tmp_sandbox = ROOT / ".tmp_test_sandbox_version_canary_success"
        try:
            shutil.rmtree(tmp_cache, ignore_errors=True)
            shutil.rmtree(tmp_sandbox, ignore_errors=True)
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
            chunkhound_meta = {"chunkhound": {"base_config_path": "/tmp/base.json"}}
            cfg_fp = rf.fingerprint_chunkhound_reviewflow_config(chunkhound_meta)

            base_root = rf.base_dir(paths, pr.host, pr.owner, pr.repo, base_ref)
            base_root.mkdir(parents=True, exist_ok=True)
            db_path = base_root / "db" / ".chunkhound.db"
            db_path.mkdir(parents=True, exist_ok=True)
            (db_path / "chunks.db").write_text("compatible", encoding="utf-8")
            meta_path = base_root / "meta.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "indexed_at": "3026-03-05T00:00:00+00:00",
                        "config_fingerprint": cfg_fp,
                        "chunkhound_version": "chunkhound old",
                        "db_path": str(db_path),
                    }
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(
                            base_config_path=ROOT / ".tmp_chunkhound_base.json"
                        ),
                        chunkhound_meta,
                        {"indexing": {"exclude": []}},
                    ),
                ),
                mock.patch.object(
                    cure_flows,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(
                            base_config_path=ROOT / ".tmp_chunkhound_base.json"
                        ),
                        chunkhound_meta,
                        {"indexing": {"exclude": []}},
                    ),
                ),
                mock.patch.object(
                    rf,
                    "run_cmd",
                    return_value=mock.Mock(
                        stdout="chunkhound new\n",
                        stderr="",
                        duration_seconds=0.0,
                    ),
                ),
                mock.patch.object(
                    rf,
                    "cache_prime",
                    side_effect=AssertionError("should not rebuild when canary accepts reuse"),
                ),
                mock.patch.object(
                    cure_flows,
                    "_run_base_cache_compatibility_canary",
                    return_value={
                        "checked_at": "2026-03-30T07:00:00+00:00",
                        "cached_chunkhound_version": "chunkhound old",
                        "current_chunkhound_version": "chunkhound new",
                        "decision": "reuse",
                        "result": "compatible",
                        "reason": "compatibility canary accepted cached DB reuse",
                        "probe_timeout_seconds": 30,
                    },
                ) as canary,
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

            canary.assert_called_once()
            self.assertEqual(out["chunkhound_version"], "chunkhound new")
            self.assertEqual(out["cache_origin"], "compatibility_canary_promoted_reuse")
            self.assertEqual(out["compatibility"]["decision"], "reuse")
            saved = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["chunkhound_version"], "chunkhound new")
            self.assertEqual(saved["compatibility"]["result"], "compatible")
        finally:
            shutil.rmtree(tmp_sandbox, ignore_errors=True)
            shutil.rmtree(tmp_cache, ignore_errors=True)

    def test_base_cache_compatibility_canary_syncs_seed_to_requested_base_ref(self) -> None:
        root = ROOT / ".tmp_test_canary_seed_sync"
        try:
            shutil.rmtree(root, ignore_errors=True)
            cache_root = root / "cache"
            sandbox_root = root / "sandbox"
            cache_root.mkdir(parents=True, exist_ok=True)
            sandbox_root.mkdir(parents=True, exist_ok=True)

            paths = rf.ReviewflowPaths(
                sandbox_root=sandbox_root,
                cache_root=cache_root,
                review_chunkhound_config=ROOT / ".tmp_unused_review_cfg.json",
                main_chunkhound_config=ROOT / ".tmp_unused_main_cfg.json",
            )
            pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=1)
            base_root = rf.base_dir(paths, pr.host, pr.owner, pr.repo, "main")
            base_root.mkdir(parents=True, exist_ok=True)
            seed = rf.seed_dir(paths, pr.host, pr.owner, pr.repo)
            seed.mkdir(parents=True, exist_ok=True)
            source_db = root / "source-db"
            source_db.mkdir(parents=True, exist_ok=True)
            (source_db / "chunks.db").write_text("seed", encoding="utf-8")

            seen_cmds: list[list[str]] = []

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                seen_cmds.append(list(cmd))
                if cmd[:4] == ["git", "-C", str(seed), "rev-parse"]:
                    return mock.Mock(stdout="deadbeef\n", stderr="", duration_seconds=0.0)
                if cmd[:4] == ["git", "-C", str(seed), "fetch"]:
                    return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
                if cmd[:4] == ["git", "-C", str(seed), "checkout"]:
                    return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
                raise AssertionError(f"unexpected command: {cmd}")

            with (
                mock.patch.object(
                    cure_flows,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(
                            base_config_path=ROOT / ".tmp_chunkhound_base.json"
                        ),
                        {"chunkhound": {"base_config_path": "/tmp/base.json"}},
                        {"indexing": {"exclude": []}},
                    ),
                ),
                mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd),
                mock.patch.object(
                    cure_flows.subprocess,
                    "run",
                    return_value=mock.Mock(returncode=0, stdout="", stderr=""),
                ),
            ):
                result = cure_flows._run_base_cache_compatibility_canary(
                    paths=paths,
                    config_path=ROOT / ".tmp_unused_review_cfg.json",
                    pr=pr,
                    base_ref="main",
                    base_root=base_root,
                    source_db_path=source_db,
                    cached_chunkhound_version="chunkhound old",
                    current_chunkhound_version="chunkhound new",
                    quiet=True,
                )

            self.assertEqual(result["decision"], "reuse")
            self.assertIn(["git", "-C", str(seed), "fetch", "origin", "main"], seen_cmds)
            self.assertIn(
                ["git", "-C", str(seed), "checkout", "-B", "main", "origin/main"],
                seen_cmds,
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_ensure_base_cache_skips_reprobe_after_successful_canary_promotion(self) -> None:
        tmp_cache = ROOT / ".tmp_test_cache_version_canary_no_reprobe"
        tmp_sandbox = ROOT / ".tmp_test_sandbox_version_canary_no_reprobe"
        try:
            shutil.rmtree(tmp_cache, ignore_errors=True)
            shutil.rmtree(tmp_sandbox, ignore_errors=True)
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
            chunkhound_meta = {"chunkhound": {"base_config_path": "/tmp/base.json"}}
            cfg_fp = rf.fingerprint_chunkhound_reviewflow_config(chunkhound_meta)
            base_root = rf.base_dir(paths, pr.host, pr.owner, pr.repo, base_ref)
            base_root.mkdir(parents=True, exist_ok=True)
            db_path = base_root / "db" / ".chunkhound.db"
            db_path.mkdir(parents=True, exist_ok=True)
            (db_path / "chunks.db").write_text("compatible", encoding="utf-8")
            meta_path = base_root / "meta.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "indexed_at": "3026-03-05T00:00:00+00:00",
                        "config_fingerprint": cfg_fp,
                        "chunkhound_version": "chunkhound old",
                        "db_path": str(db_path),
                    }
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(
                            base_config_path=ROOT / ".tmp_chunkhound_base.json"
                        ),
                        chunkhound_meta,
                        {"indexing": {"exclude": []}},
                    ),
                ),
                mock.patch.object(
                    cure_flows,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(
                            base_config_path=ROOT / ".tmp_chunkhound_base.json"
                        ),
                        chunkhound_meta,
                        {"indexing": {"exclude": []}},
                    ),
                ),
                mock.patch.object(
                    rf,
                    "run_cmd",
                    return_value=mock.Mock(
                        stdout="chunkhound new\n",
                        stderr="",
                        duration_seconds=0.0,
                    ),
                ),
                mock.patch.object(
                    cure_flows,
                    "_run_base_cache_compatibility_canary",
                    return_value={
                        "checked_at": "2026-03-30T07:00:00+00:00",
                        "cached_chunkhound_version": "chunkhound old",
                        "current_chunkhound_version": "chunkhound new",
                        "decision": "reuse",
                        "result": "compatible",
                        "reason": "compatibility canary accepted cached DB reuse",
                        "probe_timeout_seconds": 30,
                    },
                ) as canary,
            ):
                first = rf.ensure_base_cache(
                    paths=paths,
                    pr=pr,
                    base_ref=base_ref,
                    ttl_hours=24,
                    refresh=False,
                    quiet=True,
                    no_stream=True,
                )

            self.assertEqual(first["chunkhound_version"], "chunkhound new")
            self.assertEqual(canary.call_count, 1)

            with (
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(
                            base_config_path=ROOT / ".tmp_chunkhound_base.json"
                        ),
                        chunkhound_meta,
                        {"indexing": {"exclude": []}},
                    ),
                ),
                mock.patch.object(
                    cure_flows,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(
                            base_config_path=ROOT / ".tmp_chunkhound_base.json"
                        ),
                        chunkhound_meta,
                        {"indexing": {"exclude": []}},
                    ),
                ),
                mock.patch.object(
                    rf,
                    "run_cmd",
                    return_value=mock.Mock(
                        stdout="chunkhound new\n",
                        stderr="",
                        duration_seconds=0.0,
                    ),
                ),
                mock.patch.object(
                    cure_flows,
                    "_run_base_cache_compatibility_canary",
                    side_effect=AssertionError("should not reprobe after promotion"),
                ),
            ):
                second = rf.ensure_base_cache(
                    paths=paths,
                    pr=pr,
                    base_ref=base_ref,
                    ttl_hours=24,
                    refresh=False,
                    quiet=True,
                    no_stream=True,
                )

            self.assertEqual(second["chunkhound_version"], "chunkhound new")
            self.assertEqual(second["compatibility"]["decision"], "reuse")
        finally:
            shutil.rmtree(tmp_sandbox, ignore_errors=True)
            shutil.rmtree(tmp_cache, ignore_errors=True)

    def test_cure_flows_ensure_base_cache_cold_miss_uses_operator_seed_resolver(self) -> None:
        tmp_cache = ROOT / ".tmp_test_flow_cache_hot_start_resolver"
        tmp_sandbox = ROOT / ".tmp_test_flow_sandbox_hot_start_resolver"
        try:
            shutil.rmtree(tmp_cache, ignore_errors=True)
            shutil.rmtree(tmp_sandbox, ignore_errors=True)
            tmp_cache.mkdir(parents=True, exist_ok=True)
            tmp_sandbox.mkdir(parents=True, exist_ok=True)

            paths = rf.ReviewflowPaths(
                sandbox_root=tmp_sandbox,
                cache_root=tmp_cache,
                review_chunkhound_config=ROOT / ".tmp_unused_review_cfg.json",
                main_chunkhound_config=ROOT / ".tmp_unused_main_cfg.json",
            )
            pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=1)
            hot_start_seed = {
                "source_kind": "operator_workspace_config",
                "workspace_path": "/tmp/workspace",
                "config_path": "/tmp/workspace/chunkhound.json",
                "db_path": "/tmp/workspace/.chunkhound",
                "target_match_state": "match",
                "runtime_match_state": "compatible",
            }
            called: dict[str, object] = {}

            def fake_cache_prime(**kwargs):  # type: ignore[no-untyped-def]
                called["kwargs"] = kwargs
                return {"primed": True}

            out = None
            with mock.patch.object(rf, "cache_prime", side_effect=fake_cache_prime):
                out = cure_flows.ensure_base_cache(
                    paths=paths,
                    pr=pr,
                    base_ref="main",
                    ttl_hours=24,
                    refresh=False,
                    operator_hot_start_resolver=lambda: hot_start_seed,
                    quiet=True,
                    no_stream=True,
                )

            self.assertEqual(out, {"primed": True})
            self.assertEqual(called["kwargs"]["hot_start_seed"], hot_start_seed)
        finally:
            shutil.rmtree(tmp_sandbox, ignore_errors=True)
            shutil.rmtree(tmp_cache, ignore_errors=True)

    def test_prompt_operator_chunkhound_base_cache_hot_start_retries_until_valid(self) -> None:
        pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=1)
        reader = StringIO("/tmp/bad-workspace\n/tmp/bad-workspace/chunkhound.json\n/tmp/good-workspace\n/tmp/good-workspace/chunkhound.json\n")
        writer = StringIO()
        reader.close = lambda: None  # type: ignore[assignment]
        writer.close = lambda: None  # type: ignore[assignment]
        results = iter(
            [
                {
                    "candidate_state": "rejected",
                    "reason": "candidate_db_missing",
                    "message": "ChunkHound DuckDB files are missing.",
                },
                {
                    "candidate_state": "accepted",
                    "source_kind": "operator_workspace_config",
                    "workspace_path": "/tmp/good-workspace",
                    "config_path": "/tmp/good-workspace/chunkhound.json",
                    "db_path": "/tmp/good-workspace/.chunkhound",
                    "target_match_state": "match",
                    "runtime_match_state": "compatible",
                },
            ]
        )

        with mock.patch.object(
            rf,
            "_open_prompt_tty",
            return_value=(reader, writer),
        ), mock.patch.object(
            rf,
            "validate_operator_chunkhound_seed_source",
            side_effect=lambda **kwargs: next(results),
        ) as validate_seed:
            selected = rf.prompt_operator_chunkhound_base_cache_hot_start(
                pr=pr,
                resolved_runtime_config={"indexing": {"exclude": []}},
            )

        self.assertEqual(validate_seed.call_count, 2)
        self.assertEqual(selected["db_path"], "/tmp/good-workspace/.chunkhound")
        rendered = writer.getvalue()
        self.assertIn("No usable CURe base cache exists", rendered)
        self.assertIn("candidate_db_missing", rendered)
        self.assertIn("ChunkHound DuckDB files are missing.", rendered)

    def test_prompt_operator_chunkhound_base_cache_hot_start_blank_input_retries_until_new(self) -> None:
        pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=1)
        reader = StringIO("\n\nnew\n")
        writer = StringIO()
        reader.close = lambda: None  # type: ignore[assignment]
        writer.close = lambda: None  # type: ignore[assignment]

        with mock.patch.object(
            rf,
            "_open_prompt_tty",
            return_value=(reader, writer),
        ), mock.patch.object(
            rf,
            "validate_operator_chunkhound_seed_source",
            side_effect=AssertionError("blank input should not validate"),
        ):
            selected = rf.prompt_operator_chunkhound_base_cache_hot_start(
                pr=pr,
                resolved_runtime_config={"indexing": {"exclude": []}},
            )

        self.assertIsNone(selected)
        rendered = writer.getvalue()
        self.assertIn("workspace_required", rendered)

    def test_prompt_operator_chunkhound_base_cache_hot_start_non_tty_skips_prompt(self) -> None:
        pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=1)

        with mock.patch.object(
            rf,
            "_open_prompt_tty",
            return_value=None,
        ), mock.patch.object(
            rf,
            "validate_operator_chunkhound_seed_source",
            side_effect=AssertionError("non-tty prompt should not validate"),
        ):
            selected = rf.prompt_operator_chunkhound_base_cache_hot_start(
                pr=pr,
                resolved_runtime_config={"indexing": {"exclude": []}},
            )

        self.assertIsNone(selected)

    def test_prompt_operator_chunkhound_base_cache_hot_start_closes_tty_handles(self) -> None:
        pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=1)
        reader = StringIO("new\n")
        writer = StringIO()
        reader_closed = False
        writer_closed = False

        def _mark_reader_closed() -> None:
            nonlocal reader_closed
            reader_closed = True

        def _mark_writer_closed() -> None:
            nonlocal writer_closed
            writer_closed = True

        reader.close = _mark_reader_closed  # type: ignore[assignment]
        writer.close = _mark_writer_closed  # type: ignore[assignment]

        with mock.patch.object(rf, "_open_prompt_tty", return_value=(reader, writer)):
            selected = rf.prompt_operator_chunkhound_base_cache_hot_start(
                pr=pr,
                resolved_runtime_config={"indexing": {"exclude": []}},
            )

        self.assertIsNone(selected)
        self.assertTrue(reader_closed, "reader handle was not closed by try/finally")
        self.assertTrue(writer_closed, "writer handle was not closed by try/finally")

    def test_prompt_operator_chunkhound_base_cache_hot_start_swallows_close_exceptions(self) -> None:
        pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=1)
        reader = StringIO("new\n")
        writer = StringIO()

        def _exploding_close() -> None:
            raise OSError("simulated close failure")

        reader.close = _exploding_close  # type: ignore[assignment]
        writer.close = _exploding_close  # type: ignore[assignment]

        with mock.patch.object(rf, "_open_prompt_tty", return_value=(reader, writer)):
            selected = rf.prompt_operator_chunkhound_base_cache_hot_start(
                pr=pr,
                resolved_runtime_config={"indexing": {"exclude": []}},
            )

        self.assertIsNone(selected)

    def test_prompt_operator_chunkhound_base_cache_hot_start_pauses_and_resumes_dashboard(self) -> None:
        pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=1)
        reader = StringIO("new\n")
        writer = StringIO()
        reader.close = lambda: None  # type: ignore[assignment]
        writer.close = lambda: None  # type: ignore[assignment]

        dashboard = mock.MagicMock()
        output = mock.MagicMock()
        output.dashboard = dashboard

        with mock.patch.object(rf, "_open_prompt_tty", return_value=(reader, writer)), \
             mock.patch.object(rf, "active_output", return_value=output):
            selected = rf.prompt_operator_chunkhound_base_cache_hot_start(
                pr=pr,
                resolved_runtime_config={"indexing": {"exclude": []}},
            )

        self.assertIsNone(selected)
        dashboard.pause.assert_called_once()
        dashboard.resume.assert_called_once()

    def test_cache_prime_records_hot_start_metadata_and_copies_seed_db(self) -> None:
        root = ROOT / ".tmp_test_cache_prime_hot_start"
        try:
            shutil.rmtree(root, ignore_errors=True)
            cache_root = root / "cache"
            sandbox_root = root / "sandbox"
            seed_root = root / "seed"
            source_workspace = root / "workspace"
            cache_root.mkdir(parents=True, exist_ok=True)
            sandbox_root.mkdir(parents=True, exist_ok=True)
            seed_root.mkdir(parents=True, exist_ok=True)
            source_workspace.mkdir(parents=True, exist_ok=True)

            source_db = source_workspace / ".chunkhound"
            source_db.mkdir(parents=True, exist_ok=True)
            (source_db / "chunks.db").write_text("seed-db", encoding="utf-8")
            base_cfg = root / "chunkhound-base.json"
            base_cfg.write_text(
                json.dumps({"embedding": {"provider": "openai", "model": "text-embedding-3-small"}}),
                encoding="utf-8",
            )

            paths = rf.ReviewflowPaths(
                sandbox_root=sandbox_root,
                cache_root=cache_root,
                review_chunkhound_config=ROOT / ".tmp_unused_review_cfg.json",
                main_chunkhound_config=ROOT / ".tmp_unused_main_cfg.json",
            )

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                if cmd[:3] == ["git", "-C", str(seed_root)]:
                    if cmd[3:5] == ["rev-parse", "--is-inside-work-tree"]:
                        return mock.Mock(stdout="true\n", stderr="", duration_seconds=0.0)
                    if cmd[3:5] == ["fetch", "--prune"]:
                        return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
                    if cmd[3:5] == ["fetch", "origin"]:
                        return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
                    if cmd[3:5] == ["checkout", "-B"]:
                        return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
                    if cmd[3:4] == ["rev-parse"]:
                        return mock.Mock(
                            stdout="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n",
                            stderr="",
                            duration_seconds=0.0,
                        )
                if cmd[:2] == ["chunkhound", "index"]:
                    return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
                if cmd == ["chunkhound", "--version"]:
                    return mock.Mock(stdout="chunkhound 1.2.3\n", stderr="", duration_seconds=0.0)
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

            with (
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                        {"chunkhound": {"base_config_path": str(base_cfg)}},
                        {
                            "embedding": {"provider": "openai", "model": "text-embedding-3-small"},
                            "indexing": {"exclude": []},
                        },
                    ),
                ),
                mock.patch.object(rf, "ensure_review_config"),
                mock.patch.object(rf, "materialize_chunkhound_env_config", side_effect=fake_materialize_chunkhound_env_config),
                mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd),
                mock.patch.object(rf, "seed_dir", return_value=seed_root),
            ):
                meta = rf.cache_prime(
                    paths=paths,
                    host="github.com",
                    owner="acme",
                    repo="repo",
                    base_ref="main",
                    force=False,
                    hot_start_seed={
                        "source_kind": "operator_workspace_config",
                        "workspace_path": str(source_workspace),
                        "config_path": str(source_workspace / "chunkhound.json"),
                        "db_path": str(source_db),
                        "target_match_state": "match",
                        "runtime_match_state": "compatible",
                    },
                    quiet=True,
                    no_stream=True,
                )

            self.assertEqual(meta["hot_start"]["source_kind"], "operator_workspace_config")
            self.assertEqual(meta["hot_start"]["workspace_path"], str(source_workspace))
            copied_db = Path(meta["db_path"]) / "chunks.db"
            self.assertEqual(copied_db.read_text(encoding="utf-8"), "seed-db")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_cache_prime_rebuilds_base_db_when_chunkhound_version_changes(self) -> None:
        root = ROOT / ".tmp_test_cache_prime_version_mismatch"
        try:
            shutil.rmtree(root, ignore_errors=True)
            cache_root = root / "cache"
            sandbox_root = root / "sandbox"
            seed_root = root / "seed"
            cache_root.mkdir(parents=True, exist_ok=True)
            sandbox_root.mkdir(parents=True, exist_ok=True)
            seed_root.mkdir(parents=True, exist_ok=True)
            base_cfg = root / "chunkhound-base.json"
            base_cfg.write_text(
                json.dumps({"embedding": {"provider": "openai", "model": "text-embedding-3-small"}}),
                encoding="utf-8",
            )

            paths = rf.ReviewflowPaths(
                sandbox_root=sandbox_root,
                cache_root=cache_root,
                review_chunkhound_config=ROOT / ".tmp_unused_review_cfg.json",
                main_chunkhound_config=ROOT / ".tmp_unused_main_cfg.json",
            )
            chunkhound_meta = {"chunkhound": {"base_config_path": str(base_cfg)}}
            cfg_fp = rf.fingerprint_chunkhound_reviewflow_config(chunkhound_meta)
            base_root = rf.base_dir(paths, "github.com", "acme", "repo", "main")
            db_path = base_root / "db" / ".chunkhound.db"
            db_path.mkdir(parents=True, exist_ok=True)
            (db_path / "chunks.db").write_text("stale", encoding="utf-8")
            meta_path = base_root / "meta.json"
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            meta_path.write_text(
                json.dumps(
                    {
                        "config_fingerprint": cfg_fp,
                        "chunkhound_version": "chunkhound old",
                    }
                ),
                encoding="utf-8",
            )

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                if cmd[:3] == ["git", "-C", str(seed_root)]:
                    if cmd[3:5] == ["rev-parse", "--is-inside-work-tree"]:
                        return mock.Mock(stdout="true\n", stderr="", duration_seconds=0.0)
                    if cmd[3:5] == ["fetch", "--prune"]:
                        return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
                    if cmd[3:5] == ["fetch", "origin"]:
                        return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
                    if cmd[3:5] == ["checkout", "-B"]:
                        return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
                    if cmd[3:4] == ["rev-parse"]:
                        return mock.Mock(
                            stdout="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n",
                            stderr="",
                            duration_seconds=0.0,
                        )
                if cmd == ["chunkhound", "--version"]:
                    return mock.Mock(stdout="chunkhound new\n", stderr="", duration_seconds=0.0)
                if cmd[:2] == ["chunkhound", "index"]:
                    self.assertFalse(db_path.exists())
                    db_path.mkdir(parents=True, exist_ok=True)
                    (db_path / "chunks.db").write_text("fresh", encoding="utf-8")
                    return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
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

            with (
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                        chunkhound_meta,
                        {
                            "embedding": {"provider": "openai", "model": "text-embedding-3-small"},
                            "indexing": {"exclude": []},
                        },
                    ),
                ),
                mock.patch.object(rf, "ensure_review_config"),
                mock.patch.object(
                    rf,
                    "materialize_chunkhound_env_config",
                    side_effect=fake_materialize_chunkhound_env_config,
                ),
                mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd),
                mock.patch.object(rf, "seed_dir", return_value=seed_root),
            ):
                meta = rf.cache_prime(
                    paths=paths,
                    host="github.com",
                    owner="acme",
                    repo="repo",
                    base_ref="main",
                    force=False,
                    quiet=True,
                    no_stream=True,
                )

            self.assertEqual(meta["chunkhound_version"], "chunkhound new")
            self.assertEqual((Path(meta["db_path"]) / "chunks.db").read_text(encoding="utf-8"), "fresh")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_cache_prime_fails_before_chunkhound_index_when_embedding_config_is_missing_without_tty(self) -> None:
        root = ROOT / ".tmp_test_cache_prime_missing_embedding"
        try:
            shutil.rmtree(root, ignore_errors=True)
            cache_root = root / "cache"
            sandbox_root = root / "sandbox"
            seed_root = root / "seed"
            cache_root.mkdir(parents=True, exist_ok=True)
            sandbox_root.mkdir(parents=True, exist_ok=True)
            seed_root.mkdir(parents=True, exist_ok=True)
            base_cfg = root / "chunkhound-base.json"
            base_cfg.write_text("{}", encoding="utf-8")

            paths = rf.ReviewflowPaths(
                sandbox_root=sandbox_root,
                cache_root=cache_root,
                review_chunkhound_config=ROOT / ".tmp_unused_review_cfg.json",
                main_chunkhound_config=ROOT / ".tmp_unused_main_cfg.json",
            )

            commands: list[list[str]] = []

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                commands.append(cmd)
                if cmd[:3] == ["git", "-C", str(seed_root)]:
                    if cmd[3:5] == ["rev-parse", "--is-inside-work-tree"]:
                        return mock.Mock(stdout="true\n", stderr="", duration_seconds=0.0)
                    if cmd[3:5] == ["fetch", "--prune"]:
                        return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
                    if cmd[3:5] == ["fetch", "origin"]:
                        return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
                    if cmd[3:5] == ["checkout", "-B"]:
                        return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
                    if cmd[3:4] == ["rev-parse"]:
                        return mock.Mock(stdout="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n", stderr="", duration_seconds=0.0)
                if cmd == ["chunkhound", "--version"]:
                    return mock.Mock(stdout="chunkhound 1.2.3\n", stderr="", duration_seconds=0.0)
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

            with (
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                        {"chunkhound": {"base_config_path": str(base_cfg)}},
                        {},
                    ),
                ),
                mock.patch.object(rf, "ensure_review_config"),
                mock.patch.object(rf, "materialize_chunkhound_env_config", side_effect=fake_materialize_chunkhound_env_config),
                mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd),
                mock.patch.object(rf, "seed_dir", return_value=seed_root),
                mock.patch("sys.stdin", StringIO()),
                mock.patch("sys.stderr", StringIO()),
            ):
                with self.assertRaises(rf.ReviewflowError) as ctx:
                    rf.cache_prime(
                        paths=paths,
                        host="github.com",
                        owner="acme",
                        repo="repo",
                        base_ref="main",
                        force=False,
                        quiet=True,
                        no_stream=True,
                    )

            self.assertIn("ChunkHound embedding config is missing", str(ctx.exception))
            self.assertIn("run `cure setup`", str(ctx.exception).lower())
            self.assertFalse(any(cmd[:2] == ["chunkhound", "index"] for cmd in commands))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_cache_prime_preserves_existing_db_when_version_drift_hits_missing_embedding_without_tty(self) -> None:
        root = ROOT / ".tmp_test_cache_prime_version_drift_missing_embedding"
        try:
            shutil.rmtree(root, ignore_errors=True)
            cache_root = root / "cache"
            sandbox_root = root / "sandbox"
            seed_root = root / "seed"
            cache_root.mkdir(parents=True, exist_ok=True)
            sandbox_root.mkdir(parents=True, exist_ok=True)
            seed_root.mkdir(parents=True, exist_ok=True)
            base_cfg = root / "chunkhound-base.json"
            base_cfg.write_text("{}", encoding="utf-8")

            paths = rf.ReviewflowPaths(
                sandbox_root=sandbox_root,
                cache_root=cache_root,
                review_chunkhound_config=ROOT / ".tmp_unused_review_cfg.json",
                main_chunkhound_config=ROOT / ".tmp_unused_main_cfg.json",
            )
            chunkhound_meta = {"chunkhound": {"base_config_path": str(base_cfg)}}
            cfg_fp = rf.fingerprint_chunkhound_reviewflow_config(chunkhound_meta)
            base_root = rf.base_dir(paths, "github.com", "acme", "repo", "main")
            db_path = base_root / "db" / ".chunkhound.db"
            db_path.mkdir(parents=True, exist_ok=True)
            chunks_db = db_path / "chunks.db"
            chunks_db.write_text("stale", encoding="utf-8")
            meta_path = base_root / "meta.json"
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            meta_payload = {
                "config_fingerprint": cfg_fp,
                "chunkhound_version": "chunkhound old",
                "db_path": str(db_path),
            }
            meta_path.write_text(json.dumps(meta_payload), encoding="utf-8")

            commands: list[list[str]] = []

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                commands.append(cmd)
                if cmd[:3] == ["git", "-C", str(seed_root)]:
                    if cmd[3:5] == ["rev-parse", "--is-inside-work-tree"]:
                        return mock.Mock(stdout="true\n", stderr="", duration_seconds=0.0)
                    if cmd[3:5] == ["fetch", "--prune"]:
                        return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
                    if cmd[3:5] == ["fetch", "origin"]:
                        return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
                    if cmd[3:5] == ["checkout", "-B"]:
                        return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
                    if cmd[3:4] == ["rev-parse"]:
                        return mock.Mock(stdout="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n", stderr="", duration_seconds=0.0)
                if cmd == ["chunkhound", "--version"]:
                    return mock.Mock(stdout="chunkhound new\n", stderr="", duration_seconds=0.0)
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

            with (
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                        chunkhound_meta,
                        {},
                    ),
                ),
                mock.patch.object(rf, "ensure_review_config"),
                mock.patch.object(rf, "materialize_chunkhound_env_config", side_effect=fake_materialize_chunkhound_env_config),
                mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd),
                mock.patch.object(rf, "seed_dir", return_value=seed_root),
                mock.patch("sys.stdin", StringIO()),
                mock.patch("sys.stderr", StringIO()),
            ):
                with self.assertRaises(rf.ReviewflowError) as ctx:
                    rf.cache_prime(
                        paths=paths,
                        host="github.com",
                        owner="acme",
                        repo="repo",
                        base_ref="main",
                        force=False,
                        quiet=True,
                        no_stream=True,
                    )

            self.assertIn("ChunkHound embedding config is missing", str(ctx.exception))
            self.assertEqual(chunks_db.read_text(encoding="utf-8"), "stale")
            self.assertEqual(json.loads(meta_path.read_text(encoding="utf-8")), meta_payload)
            self.assertFalse(any(cmd[:2] == ["chunkhound", "index"] for cmd in commands))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_cache_prime_tty_embedding_setup_persists_discovered_embedding_config(self) -> None:
        root = ROOT / ".tmp_test_cache_prime_tty_embedding_setup"
        try:
            shutil.rmtree(root, ignore_errors=True)
            cache_root = root / "cache"
            sandbox_root = root / "sandbox"
            seed_root = root / "seed"
            cache_root.mkdir(parents=True, exist_ok=True)
            sandbox_root.mkdir(parents=True, exist_ok=True)
            seed_root.mkdir(parents=True, exist_ok=True)
            base_cfg = root / "chunkhound-base.json"
            base_cfg.write_text(
                json.dumps({"embedding": {"provider": "openai", "model": "text-embedding-3-small"}}),
                encoding="utf-8",
            )

            paths = rf.ReviewflowPaths(
                sandbox_root=sandbox_root,
                cache_root=cache_root,
                review_chunkhound_config=ROOT / ".tmp_unused_review_cfg.json",
                main_chunkhound_config=ROOT / ".tmp_unused_main_cfg.json",
            )

            commands: list[list[str]] = []

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                commands.append(cmd)
                if cmd[:3] == ["git", "-C", str(seed_root)]:
                    if cmd[3:5] == ["rev-parse", "--is-inside-work-tree"]:
                        return mock.Mock(stdout="true\n", stderr="", duration_seconds=0.0)
                    if cmd[3:5] == ["fetch", "--prune"]:
                        return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
                    if cmd[3:5] == ["fetch", "origin"]:
                        return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
                    if cmd[3:5] == ["checkout", "-B"]:
                        return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
                    if cmd[3:4] == ["rev-parse"]:
                        return mock.Mock(stdout="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n", stderr="", duration_seconds=0.0)
                if cmd == ["chunkhound", "--version"]:
                    return mock.Mock(stdout="chunkhound 1.2.3\n", stderr="", duration_seconds=0.0)
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

            def fake_subprocess_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                self.assertEqual(cmd[:2], ["chunkhound", "index"])
                (seed_root / ".chunkhound.json").write_text(
                    json.dumps(
                        {
                            "embedding": {
                                "provider": "voyage",
                                "model": "voyage-code-3",
                                "api_key": "wizard-secret",  # pragma: allowlist secret
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(cmd, 0, "", "")

            class _Tty(StringIO):
                def isatty(self) -> bool:  # pragma: no cover
                    return True

            with (
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                        {"chunkhound": {"base_config_path": str(base_cfg)}},
                        {},
                    ),
                ),
                mock.patch.object(rf, "ensure_review_config"),
                mock.patch.object(rf, "materialize_chunkhound_env_config", side_effect=fake_materialize_chunkhound_env_config),
                mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd),
                mock.patch.object(rf, "seed_dir", return_value=seed_root),
                mock.patch.object(cure_flows.subprocess, "run", side_effect=fake_subprocess_run) as subprocess_run,
                mock.patch("sys.stdin", _Tty()),
                mock.patch("sys.stderr", _Tty()),
            ):
                meta = rf.cache_prime(
                    paths=paths,
                    host="github.com",
                    owner="acme",
                    repo="repo",
                    base_ref="main",
                    force=False,
                    quiet=True,
                    no_stream=True,
                )

            base_payload = json.loads(base_cfg.read_text(encoding="utf-8"))
            self.assertEqual(base_payload["embedding"]["provider"], "voyage")
            self.assertEqual(base_payload["embedding"]["model"], "voyage-code-3")
            self.assertEqual(base_payload["embedding"]["api_key"], "wizard-secret")  # pragma: allowlist secret
            subprocess_run.assert_called_once()
            self.assertFalse(any(cmd[:2] == ["chunkhound", "index"] for cmd in commands))
            self.assertEqual(meta["chunkhound_version"], "chunkhound 1.2.3")
        finally:
            shutil.rmtree(root, ignore_errors=True)


class ChunkhoundCacheBuildLiveProgressTests(unittest.TestCase):
    def test_cache_prime_publishes_live_progress_when_session_progress_is_available(self) -> None:
        root = ROOT / ".tmp_test_cache_prime_live_progress"
        try:
            shutil.rmtree(root, ignore_errors=True)
            cache_root = root / "cache"
            sandbox_root = root / "sandbox"
            seed_root = root / "seed"
            cache_root.mkdir(parents=True, exist_ok=True)
            sandbox_root.mkdir(parents=True, exist_ok=True)
            seed_root.mkdir(parents=True, exist_ok=True)
            base_cfg = root / "chunkhound-base.json"
            base_cfg.write_text("{}", encoding="utf-8")

            paths = rf.ReviewflowPaths(
                sandbox_root=sandbox_root,
                cache_root=cache_root,
                review_chunkhound_config=ROOT / ".tmp_unused_review_cfg.json",
                main_chunkhound_config=ROOT / ".tmp_unused_main_cfg.json",
            )

            class _Progress:
                def __init__(self) -> None:
                    self.meta: dict[str, object] = {"status": "running", "phase": "ensure_base_cache"}

                def flush(self) -> None:
                    return None

            class _Result:
                def __init__(self, *, stdout: str = "", stderr: str = "", duration_seconds: float = 0.0) -> None:
                    self.stdout = stdout
                    self.stderr = stderr
                    self.duration_seconds = duration_seconds

            progress = _Progress()
            active_output = mock.Mock()

            def fake_run_logged_cmd(cmd: list[str], **kwargs: object) -> _Result:
                callback = kwargs.get("stream_text_callback")
                assert callable(callback)
                current = progress.meta["live_progress"]["current"]["text"]
                self.assertIn("Refreshing base cache", str(current))
                self.assertIn("cache miss", str(current))
                callback("Initial stats: 120 files, 4091 chunks, 4091 embeddings\n")
                current = progress.meta["live_progress"]["current"]["text"]
                self.assertIn("120 files/4091 chunks/4091 emb", str(current))
                return _Result(
                    stdout="\n".join(
                        [
                            "Processed: 4 files",
                            "Skipped: 1 files",
                            "Errors: 0 files",
                            "Total chunks: 84",
                            "Embeddings: 84",
                            "Time: 17.23s",
                        ]
                    )
                    + "\n",
                    duration_seconds=17.23,
                )

            active_output.run_logged_cmd.side_effect = fake_run_logged_cmd

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                if cmd[:3] == ["git", "-C", str(seed_root)]:
                    if cmd[3:5] == ["rev-parse", "--is-inside-work-tree"]:
                        return mock.Mock(stdout="true\n", stderr="", duration_seconds=0.0)
                    if cmd[3:5] == ["fetch", "--prune"]:
                        return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
                    if cmd[3:5] == ["fetch", "origin"]:
                        return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
                    if cmd[3:5] == ["checkout", "-B"]:
                        return mock.Mock(stdout="", stderr="", duration_seconds=0.0)
                    if cmd[3:4] == ["rev-parse"]:
                        return mock.Mock(
                            stdout="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n",
                            stderr="",
                            duration_seconds=0.0,
                        )
                if cmd == ["chunkhound", "--version"]:
                    return mock.Mock(stdout="chunkhound 1.2.3\n", stderr="", duration_seconds=0.0)
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

            with (
                mock.patch.object(
                    cure_flows,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                        {"chunkhound": {"base_config_path": str(base_cfg)}},
                        {
                            "embedding": {"provider": "openai", "model": "text-embedding-3-small"},
                            "indexing": {"exclude": []},
                        },
                    ),
                ),
                mock.patch.object(cure_flows, "ensure_review_config"),
                mock.patch.object(
                    cure_flows,
                    "materialize_chunkhound_env_config",
                    side_effect=fake_materialize_chunkhound_env_config,
                ),
                mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd),
                mock.patch.object(cure_flows, "seed_dir", return_value=seed_root),
                mock.patch.object(cure_flows, "active_output", return_value=active_output),
            ):
                meta = cure_flows.cache_prime(
                    paths=paths,
                    progress=progress,
                    host="github.com",
                    owner="acme",
                    repo="repo",
                    base_ref="main",
                    force=False,
                    quiet=True,
                    no_stream=True,
                )

            self.assertNotIn("live_progress", progress.meta)
            self.assertEqual(progress.meta["chunkhound"]["last_index"]["scope"], "base_cache")
            self.assertEqual(meta["index_summary"]["processed_files"], 4)
            self.assertEqual(meta["cache_build_reason"], "cache miss")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_flow_publishes_topup_live_progress_and_clears_it_after_indexing(self) -> None:
        root = ROOT / ".tmp_test_pr_flow_chunkhound_live_progress"
        try:
            shutil.rmtree(root, ignore_errors=True)
            sandbox_root = root / "sandbox"
            cache_root = root / "cache"
            seed = root / "seed-repo"
            config_path = root / "reviewflow.toml"
            base_cfg = root / "chunkhound-base.json"
            sandbox_root.mkdir(parents=True, exist_ok=True)
            cache_root.mkdir(parents=True, exist_ok=True)
            seed.mkdir(parents=True, exist_ok=True)
            base_db = root / "base-db"
            base_db.write_text("db", encoding="utf-8")
            base_cfg.write_text("{}", encoding="utf-8")
            config_path.write_text(
                f"[chunkhound]\nbase_config_path = {json.dumps(str(base_cfg))}\n",
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

            def fake_write_pr_context_file(
                *,
                work_dir: Path,
                pr: rf.PullRequestRef,
                pr_meta: dict[str, object],
            ) -> Path:
                context_path = work_dir / "pr-context.md"
                context_path.write_text("context", encoding="utf-8")
                return context_path

            def fake_run_logged_cmd(output: object, cmd: list[str], **kwargs: object) -> _Result:
                callback = kwargs.get("stream_text_callback")
                assert callable(callback)
                meta_path = Path(str(getattr(output, "meta_path")))
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                self.assertEqual(meta["phase"], "index_topup")
                self.assertIn(
                    "Building session index top-up",
                    str(meta["live_progress"]["current"]["text"]),
                )
                callback("Initial stats: 12 files, 48 chunks, 48 embeddings\n")
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                self.assertIn(
                    "12 files/48 chunks/48 emb",
                    str(meta["live_progress"]["current"]["text"]),
                )
                return _Result()

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
                        side_effect=fake_run_logged_cmd,
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
            self.assertIn("progress", ensure_base_cache.call_args.kwargs)
            session_dir = Path(stdout.getvalue().strip())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertNotIn("live_progress", meta)
            self.assertEqual(meta["chunkhound"]["last_index"]["scope"], "topup")
            self.assertEqual(meta["phases"]["index_topup"]["status"], "done")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_flow_retries_topup_once_with_clean_rebuild_after_reused_db_failure(self) -> None:
        root = ROOT / ".tmp_test_pr_flow_topup_rebuild_retry"
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
            cache_root = root / "cache"
            sandbox_root = root / "sandbox"
            seed = cache_root / "seed"
            base_db = cache_root / "base-db"
            base_db.parent.mkdir(parents=True, exist_ok=True)
            base_db.write_text("base", encoding="utf-8")
            seed.mkdir(parents=True, exist_ok=True)

            args = rf.build_parser().parse_args(
                [
                    "pr",
                    "https://github.com/acme/repo/pull/7",
                    "--if-reviewed",
                    "new",
                    "--no-review",
                    "--ui",
                    "off",
                    "--quiet",
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
                if cmd and cmd[0] in {"git", "rsync"}:
                    return _Result()
                raise AssertionError(f"unexpected command: {cmd}")

            copy_calls: list[tuple[Path, Path]] = []

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
                dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

            def fake_write_pr_context_file(
                *,
                work_dir: Path,
                pr: rf.PullRequestRef,
                pr_meta: dict[str, object],
            ) -> Path:
                context_path = work_dir / "pr-context.md"
                context_path.write_text("context", encoding="utf-8")
                return context_path

            attempts = {"count": 0}

            def fake_run_logged_cmd(output: object, cmd: list[str], **kwargs: object) -> _Result:
                attempts["count"] += 1
                callback = kwargs.get("stream_text_callback")
                assert callable(callback)
                meta_path = Path(str(getattr(output, "meta_path")))
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                self.assertEqual(meta["phase"], "index_topup")
                if attempts["count"] == 1:
                    self.assertNotIn("reason", meta["live_progress"])
                    raise rf.ReviewflowSubprocessError(
                        cmd=cmd,
                        cwd=Path(str(kwargs["cwd"])),
                        exit_code=134,
                        stdout="",
                        stderr="pure virtual method called",
                    )
                self.assertEqual(
                    meta["live_progress"]["reason"],
                    "compatibility canary or reuse failure",
                )
                callback("Initial stats: 12 files, 48 chunks, 48 embeddings\n")
                return _Result()

            stdout = StringIO()
            with contextlib.ExitStack() as stack:
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "gh_api_json",
                        side_effect=[
                            {
                                "base": {"ref": "main", "repo": {"default_branch": "main"}},
                                "head": {"sha": "1111111111111111111111111111111111111111"},
                                "title": "Retry PR",
                            }
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
                stack.enter_context(mock.patch.object(rf, "write_pr_context_file", side_effect=fake_write_pr_context_file))
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "ensure_base_cache",
                        return_value={"db_path": str(base_db), "chunkhound_version": "chunkhound new"},
                    )
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
                        side_effect=fake_run_logged_cmd,
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
                    config_path=cfg,
                    codex_base_config_path=root / "codex.toml",
                )

            self.assertEqual(rc, 0)
            self.assertEqual(attempts["count"], 2)
            self.assertEqual(len(copy_calls), 1)
            session_dir = Path(stdout.getvalue().strip())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["chunkhound"]["reuse_rebuild_fallback"]["status"], "recovered")
            self.assertEqual(meta["chunkhound"]["reuse_rebuild_fallback"]["scope"], "topup")
            self.assertEqual(
                meta["chunkhound"]["reuse_rebuild_fallback"]["reuse_source_kind"],
                "shared_base_cache",
            )
            self.assertEqual(meta["phases"]["index_topup"]["status"], "done")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_followup_flow_publishes_followup_index_live_progress_and_clears_without_provider_updates(self) -> None:
        root = ROOT / ".tmp_test_followup_chunkhound_live_progress"
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

            def fake_run_logged_cmd(output: object, cmd: list[str], **kwargs: object) -> _Result:
                callback = kwargs.get("stream_text_callback")
                assert callable(callback)
                meta_path = Path(str(getattr(output, "meta_path")))
                current_meta = json.loads(meta_path.read_text(encoding="utf-8"))
                self.assertEqual(current_meta["phase"], "followup_index")
                self.assertIn(
                    "Building follow-up index",
                    str(current_meta["live_progress"]["current"]["text"]),
                )
                callback("Initial stats: 9 files, 36 chunks, 36 embeddings\n")
                current_meta = json.loads(meta_path.read_text(encoding="utf-8"))
                self.assertIn(
                    "9 files/36 chunks/36 emb",
                    str(current_meta["live_progress"]["current"]["text"]),
                )
                return _Result()

            def fake_run_llm_exec(**kwargs: object) -> rf.LlmRunResult:
                output_path = Path(str(kwargs["output_path"]))
                output_path.write_text(
                    _sectioned_review_markdown(business="APPROVE", technical="REQUEST CHANGES"),
                    encoding="utf-8",
                )
                return rf.LlmRunResult(resume=None, adapter_meta={"transport": "http-openai"})

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
                        side_effect=fake_materialize_chunkhound_env_config,
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
                            "metadata": {"profile": "balanced", "provider": "openai"},
                            "add_dirs": [],
                            "codex_flags": [],
                        },
                    )
                )
                stack.enter_context(mock.patch.object(rf, "_run_review_intelligence_preflight"))
                stack.enter_context(mock.patch.object(rf, "_run_chunkhound_access_preflight"))
                stack.enter_context(mock.patch.object(rf, "load_builtin_prompt_text", return_value="Prompt"))
                stack.enter_context(mock.patch.object(rf, "review_intelligence_prompt_vars", return_value={}))
                stack.enter_context(mock.patch.object(rf, "render_prompt", return_value="Prompt"))
                stack.enter_context(mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd))
                stack.enter_context(
                    mock.patch.object(
                        rf.ReviewflowOutput,
                        "run_logged_cmd",
                        autospec=True,
                        side_effect=fake_run_logged_cmd,
                    )
                )
                stack.enter_context(mock.patch.object(rf, "run_llm_exec", side_effect=fake_run_llm_exec))
                rc = rf.followup_flow(args, paths=paths, config_path=cfg, codex_base_config_path=cfg)

            refreshed = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(rc, 0)
            self.assertNotIn("live_progress", refreshed)
            self.assertEqual(refreshed["chunkhound"]["last_index"]["scope"], "followup")
            self.assertEqual(refreshed["phases"]["followup_index"]["status"], "done")
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_followup_flow_retries_followup_index_once_with_clean_rebuild(self) -> None:
        root = ROOT / ".tmp_test_followup_chunkhound_rebuild_retry"
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
            chunkhound_db_path = chunkhound_dir / ".chunkhound.db"
            repo_dir.mkdir(parents=True, exist_ok=True)
            chunkhound_db_path.mkdir(parents=True, exist_ok=True)
            (chunkhound_db_path / "chunks.db").write_text("stale", encoding="utf-8")
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
                "llm": {"provider": "openai", "capabilities": {"supports_resume": True}},
                "notes": {"no_index": False},
                "paths": {
                    "session_dir": str(session_dir),
                    "repo_dir": str(repo_dir),
                    "work_dir": str(work_dir),
                    "chunkhound_cwd": str(chunkhound_dir),
                    "chunkhound_db": str(chunkhound_db_path),
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

            attempts = {"count": 0}

            def fake_run_logged_cmd(output: object, cmd: list[str], **kwargs: object) -> _Result:
                attempts["count"] += 1
                meta_path = Path(str(getattr(output, "meta_path")))
                current_meta = json.loads(meta_path.read_text(encoding="utf-8"))
                self.assertEqual(current_meta["phase"], "followup_index")
                if attempts["count"] == 1:
                    self.assertNotIn("reason", current_meta["live_progress"])
                    raise rf.ReviewflowSubprocessError(
                        cmd=cmd,
                        cwd=Path(str(kwargs["cwd"])),
                        exit_code=134,
                        stdout="",
                        stderr="terminate called without an active exception",
                    )
                self.assertEqual(
                    current_meta["live_progress"]["reason"],
                    "compatibility canary or reuse failure",
                )
                callback = kwargs.get("stream_text_callback")
                assert callable(callback)
                callback("Initial stats: 9 files, 36 chunks, 36 embeddings\n")
                return _Result()

            def fake_run_llm_exec(**kwargs: object) -> rf.LlmRunResult:
                output_path = Path(str(kwargs["output_path"]))
                output_path.write_text(
                    _sectioned_review_markdown(business="APPROVE", technical="REQUEST CHANGES"),
                    encoding="utf-8",
                )
                return rf.LlmRunResult(resume=None, adapter_meta={"transport": "http-openai"})

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
                        side_effect=fake_materialize_chunkhound_env_config,
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
                            "metadata": {"profile": "balanced", "provider": "openai"},
                            "add_dirs": [],
                            "codex_flags": [],
                        },
                    )
                )
                stack.enter_context(mock.patch.object(rf, "_run_review_intelligence_preflight"))
                stack.enter_context(mock.patch.object(rf, "_run_chunkhound_access_preflight"))
                stack.enter_context(mock.patch.object(rf, "load_builtin_prompt_text", return_value="Prompt"))
                stack.enter_context(mock.patch.object(rf, "review_intelligence_prompt_vars", return_value={}))
                stack.enter_context(mock.patch.object(rf, "render_prompt", return_value="Prompt"))
                stack.enter_context(mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd))
                stack.enter_context(
                    mock.patch.object(
                        rf.ReviewflowOutput,
                        "run_logged_cmd",
                        autospec=True,
                        side_effect=fake_run_logged_cmd,
                    )
                )
                stack.enter_context(mock.patch.object(rf, "run_llm_exec", side_effect=fake_run_llm_exec))
                rc = rf.followup_flow(args, paths=paths, config_path=cfg, codex_base_config_path=cfg)

            refreshed = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(rc, 0)
            self.assertEqual(attempts["count"], 2)
            self.assertEqual(refreshed["chunkhound"]["reuse_rebuild_fallback"]["status"], "recovered")
            self.assertEqual(refreshed["chunkhound"]["reuse_rebuild_fallback"]["scope"], "followup")
            self.assertEqual(
                refreshed["chunkhound"]["reuse_rebuild_fallback"]["reuse_source_kind"],
                "session_local_restore",
            )
            self.assertEqual(refreshed["phases"]["followup_index"]["status"], "done")
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)


class BaselineSelectionTests(unittest.TestCase):
    def _make_pr_flow_root(self, name: str) -> tuple[Path, Path, Path, Path]:
        root = Path(tempfile.mkdtemp(prefix=name, dir=str(ROOT)))
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        sandbox_root = root / "sandboxes"
        cache_root = root / "cache"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        cache_root.mkdir(parents=True, exist_ok=True)
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
        return root, sandbox_root, cache_root, config_path

    def _patch_pr_flow_early_setup(
        self,
        stack: contextlib.ExitStack,
        *,
        rf_module: object,
        base_cfg: Path,
        root: Path,
    ) -> None:
        stack.enter_context(
            mock.patch.object(
                rf_module,
                "load_chunkhound_runtime_config",
                return_value=(
                    rf.ReviewflowChunkHoundConfig(base_config_path=base_cfg),
                    {"chunkhound": {"base_config_path": str(base_cfg)}},
                    {"indexing": {"exclude": []}},
                ),
            )
        )
        stack.enter_context(mock.patch.object(rf_module, "materialize_chunkhound_env_config"))
        stack.enter_context(
            mock.patch.object(
                rf_module,
                "write_pr_context_file",
                side_effect=lambda *, work_dir, pr, pr_meta: work_dir / "pr-context.md",
            )
        )
        stack.enter_context(mock.patch.object(rf_module, "clear_active_output"))
        stack.enter_context(mock.patch.object(rf.ReviewflowOutput, "start"))
        stack.enter_context(mock.patch.object(rf.ReviewflowOutput, "stop"))
        stack.enter_context(mock.patch.object(rf_module, "maybe_print_markdown_after_tui"))
        stack.enter_context(mock.patch.object(rf_module, "maybe_print_codex_resume_command"))

    def test_pr_flow_runs_picker_before_ensure_base_cache(self) -> None:
        root, sandbox_root, cache_root, config_path = self._make_pr_flow_root(
            ".tmp_test_pr_picker_before_base_cache_"
        )
        try:
            args = rf.build_parser().parse_args(
                [
                    "pr",
                    "https://github.com/acme/repo/pull/14",
                    "--if-reviewed",
                    "new",
                    "--prompt",
                    "review",
                    "--ui",
                    "off",
                    "--quiet",
                    "--no-stream",
                ]
            )
            paths = rf.ReviewflowPaths(sandbox_root=sandbox_root, cache_root=cache_root)
            events: list[str] = []
            with contextlib.ExitStack() as stack:
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "gh_api_json",
                        side_effect=[
                            {
                                "base": {"ref": "main", "repo": {"default_branch": "main"}},
                                "head": {"sha": "1" * 40},
                                "title": "Picker ordering PR",
                            }
                        ],
                    )
                )
                stack.enter_context(mock.patch.object(rf, "resolve_pr_review_baseline_selection", return_value={"selected_baseline_ref": "main"}))
                stack.enter_context(mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[]))
                self._patch_pr_flow_early_setup(stack, rf_module=rf, base_cfg=root / "chunkhound-base.json", root=root)
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "resolve_llm_config_from_args",
                        side_effect=lambda *a, **k: (
                            events.append("resolve")
                            or (
                                {
                                    "provider": "claude",
                                    "preset": "claude-cli",
                                    "model": "claude-sonnet-4-6",
                                    "reasoning_effort": "high",
                                },
                                {"resolved": {"model_source": "preset", "reasoning_effort_source": "preset"}},
                            )
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "_maybe_apply_pr_llm_picker",
                        side_effect=lambda **kwargs: (
                            events.append("picker") or (kwargs["llm_resolved"], kwargs["llm_resolution_meta"])
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "ensure_base_cache",
                        side_effect=lambda **kwargs: (events.append("ensure_base_cache"), (_ for _ in ()).throw(RuntimeError("stop after ensure")))[1],
                    )
                )
                with self.assertRaisesRegex(RuntimeError, "stop after ensure"):
                    rf.pr_flow(args, paths=paths, config_path=config_path, codex_base_config_path=root / "codex.toml")
            self.assertEqual(events[:3], ["resolve", "picker", "ensure_base_cache"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_flow_picker_abort_leaves_no_created_session(self) -> None:
        root, sandbox_root, cache_root, config_path = self._make_pr_flow_root(
            ".tmp_test_pr_picker_abort_cleanup_"
        )
        try:
            args = rf.build_parser().parse_args(
                [
                    "pr",
                    "https://github.com/acme/repo/pull/14",
                    "--if-reviewed",
                    "new",
                    "--prompt",
                    "review",
                    "--ui",
                    "off",
                    "--quiet",
                    "--no-stream",
                ]
            )
            paths = rf.ReviewflowPaths(sandbox_root=sandbox_root, cache_root=cache_root)
            with contextlib.ExitStack() as stack:
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "gh_api_json",
                        return_value={
                            "base": {"ref": "main", "repo": {"default_branch": "main"}},
                            "head": {"sha": "1" * 40},
                            "title": "Picker abort PR",
                        },
                    )
                )
                stack.enter_context(mock.patch.object(rf, "resolve_pr_review_baseline_selection", return_value={"selected_baseline_ref": "main"}))
                stack.enter_context(mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[]))
                self._patch_pr_flow_early_setup(stack, rf_module=rf, base_cfg=root / "chunkhound-base.json", root=root)
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "resolve_llm_config_from_args",
                        return_value=(
                            {
                                "provider": "claude",
                                "preset": "claude-cli",
                                "model": "claude-sonnet-4-6",
                                "reasoning_effort": "high",
                            },
                            {"resolved": {"model_source": "preset", "reasoning_effort_source": "preset"}},
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "_maybe_apply_pr_llm_picker",
                        side_effect=rf.ReviewflowError("picker aborted"),
                    )
                )
                ensure_base_cache = stack.enter_context(mock.patch.object(rf, "ensure_base_cache"))
                with self.assertRaisesRegex(rf.ReviewflowError, "picker aborted"):
                    rf.pr_flow(args, paths=paths, config_path=config_path, codex_base_config_path=root / "codex.toml")
            ensure_base_cache.assert_not_called()
            self.assertEqual(list(sandbox_root.iterdir()), [])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_flow_prior_review_latest_happens_before_picker(self) -> None:
        root, sandbox_root, cache_root, config_path = self._make_pr_flow_root(
            ".tmp_test_pr_prior_review_before_picker_"
        )
        try:
            review_md = root / "prior-review.md"
            review_md.write_text("prior review\n", encoding="utf-8")
            completed = mock.Mock(review_md_path=review_md)
            args = rf.build_parser().parse_args(
                [
                    "pr",
                    "https://github.com/acme/repo/pull/14",
                    "--if-reviewed",
                    "latest",
                    "--prompt",
                    "review",
                    "--ui",
                    "off",
                    "--quiet",
                    "--no-stream",
                ]
            )
            paths = rf.ReviewflowPaths(sandbox_root=sandbox_root, cache_root=cache_root)
            stdout = StringIO()
            with contextlib.ExitStack() as stack:
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "gh_api_json",
                        return_value={
                            "base": {"ref": "main", "repo": {"default_branch": "main"}},
                            "head": {"sha": "1" * 40},
                            "title": "Prior review PR",
                        },
                    )
                )
                stack.enter_context(mock.patch.object(rf, "resolve_pr_review_baseline_selection", return_value={"selected_baseline_ref": "main"}))
                stack.enter_context(mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[completed]))
                stack.enter_context(mock.patch.object(rf, "_maybe_apply_pr_llm_picker", side_effect=AssertionError("picker should not run")))
                stack.enter_context(mock.patch("sys.stdout", stdout))
                rc = rf.pr_flow(args, paths=paths, config_path=config_path, codex_base_config_path=root / "codex.toml")
            self.assertEqual(rc, 0)
            self.assertEqual(stdout.getvalue(), "prior review\n")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_flow_non_tty_picker_skip_still_reaches_ensure_base_cache(self) -> None:
        root, sandbox_root, cache_root, config_path = self._make_pr_flow_root(
            ".tmp_test_pr_non_tty_picker_skip_"
        )
        try:
            args = rf.build_parser().parse_args(
                [
                    "pr",
                    "https://github.com/acme/repo/pull/14",
                    "--if-reviewed",
                    "new",
                    "--prompt",
                    "review",
                    "--ui",
                    "off",
                    "--quiet",
                    "--no-stream",
                ]
            )
            paths = rf.ReviewflowPaths(sandbox_root=sandbox_root, cache_root=cache_root)
            with contextlib.ExitStack() as stack:
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "gh_api_json",
                        return_value={
                            "base": {"ref": "main", "repo": {"default_branch": "main"}},
                            "head": {"sha": "1" * 40},
                            "title": "Non tty picker PR",
                        },
                    )
                )
                stack.enter_context(mock.patch.object(rf, "resolve_pr_review_baseline_selection", return_value={"selected_baseline_ref": "main"}))
                stack.enter_context(mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[]))
                self._patch_pr_flow_early_setup(stack, rf_module=rf, base_cfg=root / "chunkhound-base.json", root=root)
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "resolve_llm_config_from_args",
                        return_value=(
                            {
                                "provider": "claude",
                                "preset": "claude-cli",
                                "model": "claude-sonnet-4-6",
                                "reasoning_effort": "high",
                            },
                            {"resolved": {"model_source": "preset", "reasoning_effort_source": "preset"}},
                        ),
                    )
                )
                prompt_picker = stack.enter_context(
                    mock.patch.object(rf, "prompt_pr_model_and_effort_picker", return_value=None)
                )
                ensure_base_cache = stack.enter_context(
                    mock.patch.object(rf, "ensure_base_cache", side_effect=RuntimeError("stop after ensure"))
                )
                with self.assertRaisesRegex(RuntimeError, "stop after ensure"):
                    rf.pr_flow(args, paths=paths, config_path=config_path, codex_base_config_path=root / "codex.toml")
            prompt_picker.assert_called_once()
            ensure_base_cache.assert_called_once()
        finally:
            shutil.rmtree(root, ignore_errors=True)

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
        root = Path(tempfile.mkdtemp(prefix=".tmp_test_pr_selected_baseline_", dir=str(ROOT)))
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
        root = Path(tempfile.mkdtemp(prefix=".tmp_test_resume_selected_baseline_restore_", dir=str(ROOT)))
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
        root = Path(tempfile.mkdtemp(prefix=".tmp_test_followup_selected_baseline_restore_", dir=str(ROOT)))
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
        root = Path(tempfile.mkdtemp(prefix=".tmp_test_followup_legacy_repo_db_precedence_", dir=str(ROOT)))
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

    def test_validate_operator_chunkhound_seed_source_accepts_matching_workspace_config(self) -> None:
        root = ROOT / ".tmp_test_operator_seed_accept"
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
                if cmd == ["git", "-C", str(repo_root), "remote", "get-url", "origin"]:
                    return mock.Mock(
                        stdout="git@github.com:acme/repo.git\n",
                        stderr="",
                        duration_seconds=0.0,
                    )
                raise AssertionError(f"unexpected command: {cmd}")

            with mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd):
                candidate = cure_flows.validate_operator_chunkhound_seed_source(
                    workspace_path=repo_root,
                    config_path=config_path,
                    pr=pr,
                    resolved_runtime_config=resolved_runtime_config,
                )

            self.assertEqual(candidate["candidate_state"], "accepted")
            self.assertEqual(candidate["db_path"], str(db_path.resolve()))
            self.assertEqual(candidate["config_path"], str(config_path.resolve()))
            self.assertEqual(candidate["workspace_path"], str(repo_root.resolve()))
            self.assertEqual(candidate["target_match_state"], "match")
            self.assertEqual(candidate["runtime_match_state"], "compatible")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_operator_chunkhound_seed_source_rejects_remote_mismatch(self) -> None:
        root = ROOT / ".tmp_test_operator_seed_remote_mismatch"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_root = root / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            resolved_runtime_config = self._runtime_seed_config()
            config_path, _ = self._write_repo_local_chunkhound_state(
                repo_root=repo_root,
                resolved_runtime_config=resolved_runtime_config,
                config_name="chunkhound.json",
            )
            pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=17)

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                if cmd == ["git", "-C", str(repo_root), "remote", "get-url", "origin"]:
                    return mock.Mock(stdout="git@github.com:other/repo.git\n", stderr="", duration_seconds=0.0)
                raise AssertionError(f"unexpected command: {cmd}")

            with mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd):
                candidate = cure_flows.validate_operator_chunkhound_seed_source(
                    workspace_path=repo_root,
                    config_path=config_path,
                    pr=pr,
                    resolved_runtime_config=resolved_runtime_config,
                )

            self.assertEqual(candidate["candidate_state"], "rejected")
            self.assertEqual(candidate["reason"], "repo_remote_mismatch")
            self.assertEqual(candidate["target_match_state"], "mismatch")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_operator_chunkhound_seed_source_rejects_config_mismatch(self) -> None:
        root = ROOT / ".tmp_test_operator_seed_config_mismatch"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_root = root / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            resolved_runtime_config = self._runtime_seed_config()
            config_path, _ = self._write_repo_local_chunkhound_state(
                repo_root=repo_root,
                resolved_runtime_config=resolved_runtime_config,
                config_name="chunkhound.json",
                mutate_config=lambda config: config.setdefault("research", {}).__setitem__("algorithm", "semantic"),
            )
            pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=17)

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                if cmd == ["git", "-C", str(repo_root), "remote", "get-url", "origin"]:
                    return mock.Mock(stdout="git@github.com:acme/repo.git\n", stderr="", duration_seconds=0.0)
                raise AssertionError(f"unexpected command: {cmd}")

            with mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd):
                candidate = cure_flows.validate_operator_chunkhound_seed_source(
                    workspace_path=repo_root,
                    config_path=config_path,
                    pr=pr,
                    resolved_runtime_config=resolved_runtime_config,
                )

            self.assertEqual(candidate["candidate_state"], "rejected")
            self.assertEqual(candidate["reason"], "config_mismatch")
            self.assertEqual(candidate["runtime_match_state"], "incompatible")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_operator_chunkhound_seed_source_rejects_missing_db(self) -> None:
        root = ROOT / ".tmp_test_operator_seed_missing_db"
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
            shutil.rmtree(db_path, ignore_errors=True)
            pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=17)

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                if cmd == ["git", "-C", str(repo_root), "remote", "get-url", "origin"]:
                    return mock.Mock(stdout="git@github.com:acme/repo.git\n", stderr="", duration_seconds=0.0)
                raise AssertionError(f"unexpected command: {cmd}")

            with mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd):
                candidate = cure_flows.validate_operator_chunkhound_seed_source(
                    workspace_path=repo_root,
                    config_path=config_path,
                    pr=pr,
                    resolved_runtime_config=resolved_runtime_config,
                )

            self.assertEqual(candidate["candidate_state"], "rejected")
            self.assertEqual(candidate["reason"], "candidate_db_missing")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_operator_chunkhound_seed_source_rejects_workspace_root_mismatch(self) -> None:
        root = ROOT / ".tmp_test_operator_seed_workspace_root_mismatch"
        try:
            shutil.rmtree(root, ignore_errors=True)
            workspace_root = root / "workspace"
            repo_root = workspace_root / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            resolved_runtime_config = self._runtime_seed_config()
            config_path, _ = self._write_repo_local_chunkhound_state(
                repo_root=workspace_root,
                resolved_runtime_config=resolved_runtime_config,
                config_name="chunkhound.json",
            )
            pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=17)

            with mock.patch.object(
                rf,
                "run_cmd",
                side_effect=AssertionError("workspace-root mismatch should fail before git validation"),
            ):
                candidate = cure_flows.validate_operator_chunkhound_seed_source(
                    workspace_path=repo_root,
                    config_path=config_path,
                    pr=pr,
                    resolved_runtime_config=resolved_runtime_config,
                )

            self.assertEqual(candidate["candidate_state"], "rejected")
            self.assertEqual(candidate["reason"], "config_not_at_workspace_root")
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

    def _capture_eprint_messages(self):
        messages: list[str] = []

        def capture(*args: object) -> None:
            messages.append(" ".join(str(arg) for arg in args))

        return messages, capture

    def _assert_grounding_playbook(
        self,
        playbook: str,
        *,
        session_id: str,
        artifact_name: str,
        resume_from: str,
        error_fragment: str,
    ) -> None:
        self.assertIn(f"`{artifact_name}`", playbook)
        self.assertIn("grounding_report.json", playbook)
        self.assertIn("logs directory:", playbook)
        self.assertIn(error_fragment, playbook)
        self.assertIn(f"cure status {session_id} --json", playbook)
        self.assertIn(f"cure watch {session_id}", playbook)
        self.assertIn(f"cure resume {session_id}", playbook)
        self.assertIn(f"cure resume {session_id} --from {resume_from}", playbook)
        self.assertIn('[multipass].grounding_mode = "warn"', playbook)
        self.assertIn("- strict: blocks completion for invalid artifacts", playbook)
        self.assertIn("- warn: records validation findings and continues", playbook)
        self.assertIn("- off: skips grounding validation", playbook)

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
            elif output_path.name in {"review.md", "review.candidate.md"}:
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
                with self.assertRaisesRegex(
                    rf.ReviewflowError,
                    "grounding validation failed|grounding-skipped; review synthesis cannot continue",
                ):
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
                            "- Input lacks validation. Sources: `src/app.py:2`",
                            "",
                            "### Suggested actions",
                            "- Add checks",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
            elif output_path.name in {"review.md", "review.candidate.md"}:
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
        messages, capture = self._capture_eprint_messages()
        with mock.patch.object(rf, "_eprint", side_effect=capture):
            root, calls = self._run_pr_flow_with_grounding(grounding_mode="strict")
        try:
            session_dir = next((root / "sandboxes").iterdir())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            report = json.loads((session_dir / "work" / "grounding_report.json").read_text(encoding="utf-8"))
            playbook = "\n".join(messages)
            self.assertEqual(calls, ["review.plan.md", "review.step-01.md", "review.step-01.md"])
            self.assertEqual(meta["status"], "error")
            self.assertEqual(meta["multipass"]["status"], "step_failed")
            self.assertEqual(meta["multipass"]["grounding_valid_step_count"], 0)
            self.assertIn("step-01", report["invalid_artifacts"])
            self.assertFalse(report["artifacts"]["step-01"]["valid"])
            self.assertEqual(meta["multipass"]["validation"]["report_path"], str(session_dir / "work" / "grounding_report.json"))
            self.assertIn("All planned steps were grounding-skipped; no synth inputs remain.", playbook)
            self.assertIn("`review.md`", playbook)
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
        messages, capture = self._capture_eprint_messages()
        with mock.patch.object(rf, "_eprint", side_effect=capture):
            with self.assertRaisesRegex(rf.ReviewflowError, "Multipass synth grounding validation failed"):
                self._run_pr_flow_with_synth_grounding(synth_markdown=synth_markdown)
        try:
            session_dir = next((root / "sandboxes").iterdir())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            report = json.loads((session_dir / "work" / "grounding_report.json").read_text(encoding="utf-8"))
            playbook = "\n".join(messages)
            self.assertEqual(meta["status"], "error")
            self.assertIn("synth", report["invalid_artifacts"])
            self.assertIn(
                "step-artifact citations alone are insufficient",
                "\n".join(report["artifacts"]["synth"]["errors"]),
            )
            self._assert_grounding_playbook(
                playbook,
                session_id=session_dir.name,
                artifact_name="review.candidate.md",
                resume_from="synth",
                error_fragment="step-artifact citations alone are insufficient",
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

    def test_step_grounding_rejects_mixed_complete_and_incomplete_sources_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_dir = root / "repo"
            repo_dir.mkdir()
            (repo_dir / "src").mkdir()
            (repo_dir / "src" / "app.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
            step_output = root / "review.step-01.md"
            step_output.write_text(
                "\n".join(
                    [
                        "### Step Result: 01 — API review",
                        "**Focus**: grounding",
                        "",
                        "### Findings",
                        "- Mixed citations. Sources: `src/app.py:2`, `src/app.py`",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            validation = rf.validate_multipass_step_grounding(
                artifact_path=step_output,
                repo_dir=repo_dir,
                step_index=1,
            )

        self.assertFalse(validation["valid"])
        self.assertIn("incomplete `Sources:` suffix", "\n".join(validation["errors"]))

    def test_synth_grounding_rejects_mixed_complete_and_incomplete_sources_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_dir = root / "repo"
            work_dir = root / "work"
            repo_dir.mkdir()
            work_dir.mkdir()
            (repo_dir / "src").mkdir()
            (repo_dir / "src" / "app.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
            review_md = root / "review.md"
            review_md.write_text(
                self._valid_synth_markdown(primary_citation="src/app.py:2").replace(
                    "Sources: `src/app.py:2`",
                    "Sources: `src/app.py:2`, `src/app.py`",
                    1,
                ),
                encoding="utf-8",
            )

            validation = rf.validate_multipass_synth_grounding(
                artifact_path=review_md,
                step_outputs=[],
                repo_dir=repo_dir,
                work_dir=work_dir,
            )

        self.assertFalse(validation["valid"])
        self.assertIn("incomplete `Sources:` suffix", "\n".join(validation["errors"]))
        self.assertEqual(validation["invalid_bullets"][0]["bullet_index"], 1)

    def test_synth_grounding_marks_mixed_valid_and_invalid_primary_citations_for_finalization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_dir = root / "repo"
            work_dir = root / "work"
            repo_dir.mkdir()
            work_dir.mkdir()
            (repo_dir / "src").mkdir()
            (repo_dir / "src" / "app.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
            review_md = root / "review.md"
            review_md.write_text(
                self._valid_synth_markdown(primary_citation="src/app.py:2").replace(
                    "Sources: `src/app.py:2`",
                    "Sources: `src/app.py:2`, `src/app.py:99`",
                    1,
                ),
                encoding="utf-8",
            )

            validation = rf.validate_multipass_synth_grounding(
                artifact_path=review_md,
                step_outputs=[],
                repo_dir=repo_dir,
                work_dir=work_dir,
            )

        self.assertFalse(validation["valid"])
        self.assertIn("missing source line src/app.py:99", "\n".join(validation["errors"]))
        self.assertEqual(validation["invalid_bullets"][0]["bullet_index"], 1)
        self.assertIn("missing source line src/app.py:99", validation["invalid_bullets"][0]["reason"])

    def test_step_grounding_rejects_backtick_plus_bare_residue_sources_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_dir = root / "repo"
            repo_dir.mkdir()
            (repo_dir / "src").mkdir()
            (repo_dir / "src" / "app.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
            step_output = root / "review.step-01.md"
            step_output.write_text(
                "\n".join(
                    [
                        "### Step Result: 01 — API review",
                        "**Focus**: grounding",
                        "",
                        "### Findings",
                        "- Mixed citations. Sources: `src/app.py:2` src/app.py",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            validation = rf.validate_multipass_step_grounding(
                artifact_path=step_output,
                repo_dir=repo_dir,
                step_index=1,
            )

        self.assertFalse(validation["valid"])
        self.assertIn("incomplete `Sources:` suffix", "\n".join(validation["errors"]))

    def test_synth_grounding_rejects_backtick_plus_bare_residue_sources_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_dir = root / "repo"
            work_dir = root / "work"
            repo_dir.mkdir()
            work_dir.mkdir()
            (repo_dir / "src").mkdir()
            (repo_dir / "src" / "app.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
            review_md = root / "review.md"
            review_md.write_text(
                self._valid_synth_markdown(primary_citation="src/app.py:2").replace(
                    "Sources: `src/app.py:2`",
                    "Sources: `src/app.py:2` src/app.py",
                    1,
                ),
                encoding="utf-8",
            )

            validation = rf.validate_multipass_synth_grounding(
                artifact_path=review_md,
                step_outputs=[],
                repo_dir=repo_dir,
                work_dir=work_dir,
            )

        self.assertFalse(validation["valid"])
        self.assertIn("incomplete `Sources:` suffix", "\n".join(validation["errors"]))
        self.assertEqual(validation["invalid_bullets"][0]["bullet_index"], 1)

    def test_synth_grounding_requires_required_sections_under_each_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_dir = root / "repo"
            work_dir = root / "work"
            repo_dir.mkdir()
            work_dir.mkdir()
            (repo_dir / "src").mkdir()
            (repo_dir / "src" / "app.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
            review_md = root / "review.md"
            review_md.write_text(
                "\n".join(
                    [
                        "### Steps taken",
                        "- Read step output",
                        "",
                        "**Summary**: ok",
                        "",
                        "## Business / Product Assessment",
                        "**Verdict**: APPROVE",
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
                        "- Technical strength one. Sources: `src/app.py:2`",
                        "",
                        "### Strengths",
                        "- Technical strength two. Sources: `src/app.py:2`",
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
                ),
                encoding="utf-8",
            )

            validation = rf.validate_multipass_synth_grounding(
                artifact_path=review_md,
                step_outputs=[],
                repo_dir=repo_dir,
                work_dir=work_dir,
            )

        self.assertFalse(validation["valid"])
        self.assertIn(
            "Missing required synth section '### Strengths' under '## Business / Product Assessment'.",
            "\n".join(validation["errors"]),
        )

    def test_synth_grounding_prefers_repo_source_for_same_name_step_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_dir = root / "repo"
            work_dir = root / "work"
            repo_dir.mkdir()
            work_dir.mkdir()
            repo_root_review = repo_dir / "review.step-01.md"
            repo_root_review.write_text("repo root evidence\n", encoding="utf-8")
            step_output = root / "session-step-output" / "review.step-01.md"
            step_output.parent.mkdir(parents=True)
            step_output.write_text("step artifact evidence\n", encoding="utf-8")
            review_md = root / "review.md"
            review_md.write_text(
                self._valid_synth_markdown(primary_citation="review.step-01.md:1"),
                encoding="utf-8",
            )

            validation = rf.validate_multipass_synth_grounding(
                artifact_path=review_md,
                step_outputs=[step_output],
                repo_dir=repo_dir,
                work_dir=work_dir,
            )

        self.assertTrue(validation["valid"], validation["errors"])
        repo_citations = [
            item
            for item in validation["citations"]
            if item["path"] == "review.step-01.md"
            and item["section"] in {"Strengths", "In Scope Issues", "Reusability"}
        ]
        self.assertTrue(repo_citations)
        self.assertTrue(all(item["source_kind"] == "repo" for item in repo_citations))
        self.assertTrue(all(item["counts_as_primary"] is True for item in repo_citations))

    def test_synth_grounding_rejects_repo_fallback_for_missing_work_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_dir = root / "repo"
            work_dir = root / "work"
            repo_dir.mkdir()
            work_dir.mkdir()
            (repo_dir / "work").mkdir()
            (repo_dir / "work" / "pr-context.md").write_text("repo copy only\n", encoding="utf-8")
            review_md = root / "review.md"
            review_md.write_text(
                self._valid_synth_markdown(primary_citation="work/pr-context.md:1"),
                encoding="utf-8",
            )

            validation = rf.validate_multipass_synth_grounding(
                artifact_path=review_md,
                step_outputs=[],
                repo_dir=repo_dir,
                work_dir=work_dir,
            )

        self.assertFalse(validation["valid"])
        synth_citations = [
            item
            for item in validation["citations"]
            if item["path"] == "work/pr-context.md"
            and item["section"] in {"Strengths", "In Scope Issues", "Reusability"}
        ]
        self.assertTrue(synth_citations)
        self.assertTrue(all(item["source_kind"] is None for item in synth_citations))
        self.assertTrue(all(item["counts_as_primary"] is False for item in synth_citations))
        self.assertTrue(
            any("cites unsupported synth source work/pr-context.md:1" in err for err in validation["errors"])
        )

    def test_synth_grounding_rejects_indented_pseudo_bullets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_dir = root / "repo"
            work_dir = root / "work"
            repo_dir.mkdir()
            work_dir.mkdir()
            (repo_dir / "src").mkdir()
            (repo_dir / "src" / "app.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
            review_md = root / "review.md"
            review_md.write_text(
                "\n".join(
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
                        "    - Indented pseudo-bullet. Sources: `src/app.py:2`",
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
                        "- Technical strength. Sources: `src/app.py:2`",
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
                ),
                encoding="utf-8",
            )

            validation = rf.validate_multipass_synth_grounding(
                artifact_path=review_md,
                step_outputs=[],
                repo_dir=repo_dir,
                work_dir=work_dir,
            )

        self.assertFalse(validation["valid"])
        self.assertIn(
            "Section '### Strengths' under '## Business / Product Assessment' (line 9) must include at least one bullet.",
            "\n".join(validation["errors"]),
        )

    def test_synth_grounding_invalid_bullets_keep_specific_citation_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_dir = root / "repo"
            work_dir = root / "work"
            repo_dir.mkdir()
            work_dir.mkdir()
            (repo_dir / "src").mkdir()
            (repo_dir / "src" / "app.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
            review_md = root / "review.md"
            review_md.write_text(
                self._valid_synth_markdown(primary_citation="src/app.py:2").replace(
                    "Sources: `src/app.py:2`",
                    "Sources: `src/app.py:99`",
                    1,
                ),
                encoding="utf-8",
            )

            validation = rf.validate_multipass_synth_grounding(
                artifact_path=review_md,
                step_outputs=[],
                repo_dir=repo_dir,
                work_dir=work_dir,
            )

        self.assertFalse(validation["valid"])
        self.assertIn("cites missing source line", validation["invalid_bullets"][0]["reason"])

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
                                "- Input lacks validation. Sources: `src/app.py:2`",
                                "",
                                "### Suggested actions",
                                "- Add checks",
                                "",
                            ]
                        ),
                        encoding="utf-8",
                    )
                elif output_path.name in {"review.md", "review.candidate.md"}:
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

    def _claude_helper_adapter_meta(
        self,
        *,
        payloads: list[dict[str, object]],
        helper_path: str = "/tmp/cure/work/bin/cure-chunkhound",
        command: str | None = None,
    ) -> dict[str, object]:
        entries = []
        for payload in payloads:
            payload_command = str((payload if isinstance(payload, dict) else {}).get("command") or "").strip().lower()
            default_command = (
                '/bin/bash -lc \'"$CURE_CHUNKHOUND_HELPER" search "needle"\''
                if payload_command == "search"
                else '/bin/bash -lc \'"$CURE_CHUNKHOUND_HELPER" research "cross-file question"\''
            )
            entries.append(
                {
                    "payload": payload,
                    "stdout_excerpt": json.dumps(payload, sort_keys=True),
                    "command": command or default_command,
                }
            )
        return {
            "provider": "claude",
            "chunkhound_helper_path": helper_path,
            "chunkhound_tool_proof_entries": entries,
        }

    def test_validate_and_record_chunkhound_tool_proof_persists_report_and_meta(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_tool_proof_validation"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            work_dir = root / "work"
            work_dir.mkdir(parents=True, exist_ok=True)
            meta: dict[str, object] = {"chunkhound": {"base_config_path": "/tmp/base.json"}}

            report = rf.validate_and_record_chunkhound_tool_proof(
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

            first = rf.validate_and_record_chunkhound_tool_proof(
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
            second = rf.validate_and_record_chunkhound_tool_proof(
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

            report = rf.validate_and_record_chunkhound_tool_proof(
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

            report = rf.validate_and_record_chunkhound_tool_proof(
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

            rf.validate_and_record_chunkhound_tool_proof(
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
            rf.validate_and_record_chunkhound_tool_proof(
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
            report = rf.validate_chunkhound_tool_proof(
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
            report = rf.validate_chunkhound_tool_proof(
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
            report = rf.validate_chunkhound_tool_proof(
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
            report = rf.validate_chunkhound_tool_proof(
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
            report = rf.validate_chunkhound_tool_proof(
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

    def test_validate_chunkhound_tool_proof_accepts_mixed_helper_output_with_final_json(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_helper_tool_proof_mixed_output_json"
        helper_path = "/tmp/cure/work/bin/cure-chunkhound"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            search_payload = {
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
            }
            research_payload = {
                "ok": True,
                "command": "research",
                "tool_name": "code_research",
                "query": "cross-file question",
                "helper_path": helper_path,
                "result": {"summary": "grounded answer"},
                "execution_stage": "tools/call",
                "execution_stage_status": "ok",
            }
            report = rf.validate_chunkhound_tool_proof(
                provider="codex",
                review_stage="multipass_plan",
                prompt_template_name="mrereview_gh_local_big_plan.md",
                adapter_meta=self._write_helper_command_events(
                    root=root,
                    commands=["search", "research"],
                    raw_outputs={
                        "search": "\n".join(
                            [
                                "preflight stage=initialize status=ok",
                                "preflight stage=tools/list status=ok",
                                json.dumps(search_payload, indent=2),
                            ]
                        ),
                        "research": "\n".join(
                            [
                                "preflight stage=initialize status=ok",
                                "preflight stage=notifications/initialized status=ok",
                                "preflight stage=tools/list status=ok",
                                json.dumps(research_payload, indent=2),
                            ]
                        ),
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

    def test_validate_chunkhound_tool_proof_malformed_helper_json_fails_closed(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_helper_tool_proof_bad_json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            report = rf.validate_chunkhound_tool_proof(
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
            report = rf.validate_chunkhound_tool_proof(
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
            report = rf.validate_chunkhound_tool_proof(
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
            report = rf.validate_chunkhound_tool_proof(
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
            report = rf.validate_chunkhound_tool_proof(
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
            report = rf.validate_chunkhound_tool_proof(
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
            report = rf.validate_chunkhound_tool_proof(
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
            report = rf.validate_chunkhound_tool_proof(
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
            report = rf.validate_chunkhound_tool_proof(
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
            report = rf.validate_chunkhound_tool_proof(
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

    def test_validate_chunkhound_tool_proof_accepts_claude_helper_entries(self) -> None:
        helper_path = "/tmp/cure/work/bin/cure-chunkhound"
        report = rf.validate_chunkhound_tool_proof(
            provider="claude",
            review_stage="singlepass_review",
            prompt_template_name="mrereview_gh_local.md",
            adapter_meta=self._claude_helper_adapter_meta(
                helper_path=helper_path,
                payloads=[
                    {
                        "ok": True,
                        "command": "search",
                        "tool_name": "search",
                        "query": "needle",
                        "helper_path": helper_path,
                        "result": {"results": [], "pagination": {"offset": 0, "total_results": 0}},
                        "execution_stage": "tools/call",
                        "execution_stage_status": "ok",
                    },
                    {
                        "ok": True,
                        "command": "research",
                        "tool_name": "code_research",
                        "query": "cross-file question",
                        "helper_path": helper_path,
                        "result": {"summary": "grounded answer"},
                        "execution_stage": "tools/call",
                        "execution_stage_status": "ok",
                    },
                ],
            ),
        )

        self.assertIsNotNone(report)
        assert report is not None
        self.assertTrue(report["valid"])
        self.assertEqual(report["provider"], "claude")
        self.assertEqual(report["observed_successful_calls"], ["search", "code_research"])
        self.assertEqual(report["observed_evidence_sources"], ["cli_helper_command_execution"])
        self.assertEqual(
            [detail["command_excerpt"] for detail in report["observed_successful_call_details"]],
            [
                f"claude tool_use_result via {helper_path}",
                f"claude tool_use_result via {helper_path}",
            ],
        )

    def test_validate_and_record_chunkhound_tool_proof_accepts_real_claude_background_task_success_fixture(self) -> None:
        root = ROOT / ".tmp_test_real_claude_background_task_success_report"

        class _StubProgress:
            def __init__(self) -> None:
                self.meta: dict[str, object] = {}

        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            work_dir = root / "work"
            work_dir.mkdir(parents=True, exist_ok=True)
            meta: dict[str, object] = {"chunkhound": {"base_config_path": "/tmp/base.json"}}
            progress = _StubProgress()
            state: dict[str, Any] = {"content": ""}

            search_fixture_path = ROOT / "tests" / "fixtures" / "claude_stream" / "search_tool_result.ndjson"
            search_fixture_text = search_fixture_path.read_text(encoding="utf-8")
            search_tool_use_id = ""
            for raw in search_fixture_text.splitlines():
                payload = json.loads(raw)
                if not isinstance(payload, dict) or str(payload.get("type") or "") != "user":
                    continue
                message = payload.get("message")
                if not isinstance(message, dict):
                    continue
                for block in message.get("content") or []:
                    if not isinstance(block, dict) or str(block.get("type") or "") != "tool_result":
                        continue
                    search_tool_use_id = str(block.get("tool_use_id") or "").strip()
                    if search_tool_use_id:
                        break
                if search_tool_use_id:
                    break
            self.assertTrue(search_tool_use_id)
            state["bash_tool_commands_by_id"] = {search_tool_use_id: '"$CURE_CHUNKHOUND_HELPER" search "<QUERY>"'}
            cure_llm._ensure_text_cli_live_progress(progress=progress, provider="claude", label="Claude CLI started.")
            cure_llm._handle_claude_stream_chunk(progress=progress, state=state, chunk=search_fixture_text)

            stream_fixture_path = (
                ROOT / "tests" / "fixtures" / "claude_stream" / "code_research_background_task_success.ndjson"
            )
            output_fixture_path = (
                ROOT / "tests" / "fixtures" / "claude_stream" / "code_research_background_task_success.output.json"
            )
            output_path = root / "background_task_output.json"
            output_path.write_text(output_fixture_path.read_text(encoding="utf-8"), encoding="utf-8")
            rewritten_lines: list[str] = []
            research_tool_use_id = ""
            research_command_text = ""
            for raw in stream_fixture_path.read_text(encoding="utf-8").splitlines():
                payload = json.loads(raw)
                if isinstance(payload, dict) and str(payload.get("type") or "") == "assistant":
                    message = payload.get("message")
                    if isinstance(message, dict):
                        for block in message.get("content") or []:
                            if not isinstance(block, dict) or str(block.get("type") or "") != "tool_use":
                                continue
                            research_tool_use_id = str(block.get("id") or "").strip() or research_tool_use_id
                            tool_input = block.get("input")
                            if isinstance(tool_input, dict):
                                research_command_text = str(tool_input.get("command") or "").strip() or research_command_text
                if (
                    isinstance(payload, dict)
                    and str(payload.get("type") or "") == "system"
                    and str(payload.get("subtype") or "") == "task_notification"
                    and str(payload.get("status") or "") == "completed"
                ):
                    payload["output_file"] = str(output_path)
                    research_tool_use_id = str(payload.get("tool_use_id") or "").strip() or research_tool_use_id
                rewritten_lines.append(json.dumps(payload))
            self.assertTrue(research_tool_use_id)
            self.assertTrue(research_command_text)
            state["bash_tool_commands_by_id"][research_tool_use_id] = research_command_text
            cure_llm._handle_claude_stream_chunk(
                progress=progress,
                state=state,
                chunk="\n".join(rewritten_lines),
            )

            report = rf.validate_and_record_chunkhound_tool_proof(
                meta=meta,
                work_dir=work_dir,
                provider="claude",
                review_stage="multipass_plan",
                prompt_template_name="mrereview_gh_local.md",
                adapter_meta={
                    "provider": "claude",
                    "chunkhound_helper_path": "<CURE_CHUNKHOUND_HELPER>",
                    "chunkhound_tool_proof_entries": list(state["chunkhound_tool_proof_entries"]),
                },
            )

            persisted = json.loads((work_dir / "chunkhound_tool_validation.json").read_text(encoding="utf-8"))
            self.assertIsNotNone(report)
            assert report is not None
            self.assertTrue(report["valid"])
            self.assertEqual(report["provider"], "claude")
            self.assertEqual(report["observed_successful_calls"], ["search", "code_research"])
            self.assertEqual(report["observed_evidence_sources"], ["cli_helper_command_execution"])
            self.assertEqual(persisted["provider"], "claude")
            self.assertTrue(persisted["valid"])
            self.assertEqual(persisted["runs"][0]["review_stage"], "multipass_plan")
            self.assertEqual(persisted["runs"][0]["observed_successful_calls"], ["search", "code_research"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_and_record_chunkhound_tool_proof_accepts_persisted_output_recovery(self) -> None:
        """End-to-end: proof recovered from a <persisted-output> wrapper file survives
        validate_and_record and records observed_successful_calls == ["search", "code_research"]."""
        import tempfile

        root = ROOT / ".tmp_test_persisted_output_proof_recovery_report"

        class _StubProgress:
            def __init__(self) -> None:
                self.meta: dict[str, object] = {}

        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            work_dir = root / "work"
            work_dir.mkdir(parents=True, exist_ok=True)
            meta: dict[str, object] = {"chunkhound": {"base_config_path": "/tmp/base.json"}}
            progress = _StubProgress()
            state: dict[str, Any] = {"content": ""}
            helper_path = "<CURE_CHUNKHOUND_HELPER>"

            # --- Phase 1: inline search proof (same as the background-task test) ---
            search_fixture_path = ROOT / "tests" / "fixtures" / "claude_stream" / "search_tool_result.ndjson"
            search_fixture_text = search_fixture_path.read_text(encoding="utf-8")
            search_tool_use_id = ""
            for raw in search_fixture_text.splitlines():
                payload = json.loads(raw)
                if not isinstance(payload, dict) or str(payload.get("type") or "") != "user":
                    continue
                message = payload.get("message")
                if not isinstance(message, dict):
                    continue
                for block in message.get("content") or []:
                    if not isinstance(block, dict) or str(block.get("type") or "") != "tool_result":
                        continue
                    search_tool_use_id = str(block.get("tool_use_id") or "").strip()
                    if search_tool_use_id:
                        break
                if search_tool_use_id:
                    break
            self.assertTrue(search_tool_use_id)
            state["bash_tool_commands_by_id"] = {search_tool_use_id: '"$CURE_CHUNKHOUND_HELPER" search "<QUERY>"'}
            cure_llm._ensure_text_cli_live_progress(progress=progress, provider="claude", label="Claude CLI started.")
            cure_llm._handle_claude_stream_chunk(progress=progress, state=state, chunk=search_fixture_text)

            # --- Phase 2: research proof via <persisted-output> wrapper ---
            research_proof_json = json.dumps(
                {
                    "ok": True,
                    "command": "research",
                    "tool_name": "code_research",
                    "query": "how does X work",
                    "helper_path": helper_path,
                    "result": {"summary": "grounded answer"},
                    "execution_stage": "tools/call",
                    "execution_stage_status": "ok",
                }
            )
            full_output = "\n".join(
                [
                    "cure-chunkhound: tools/call waiting (10.0s elapsed)",
                    research_proof_json,
                    "Some additional research text " * 50,
                ]
            )
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8", dir=str(root)
            ) as f:
                f.write(full_output)
                persisted_path = f.name

            wrapper_text = (
                "<persisted-output>\n"
                f"Output too large (33.2KB). Full output saved to: {persisted_path}\n"
                "\n"
                "Preview (first 2KB):\n"
                "cure-chunkhound: tools/call waiting (10.0s elapsed)\n"
                "</persisted-output>"
            )
            research_tool_use_id = "toolu_research_po"
            state["bash_tool_commands_by_id"][research_tool_use_id] = (
                '"$CURE_CHUNKHOUND_HELPER" research "how does X work"'
            )
            cure_llm._handle_claude_stream_chunk(
                progress=progress,
                state=state,
                chunk="\n".join(
                    [
                        json.dumps(
                            {
                                "type": "stream_event",
                                "event": {
                                    "type": "content_block_start",
                                    "index": 1,
                                    "content_block": {
                                        "type": "tool_use",
                                        "id": research_tool_use_id,
                                        "name": "Bash",
                                        "input": {},
                                    },
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "type": "stream_event",
                                "event": {
                                    "type": "content_block_delta",
                                    "index": 1,
                                    "delta": {
                                        "type": "input_json_delta",
                                        "partial_json": '{"command":"\\"$CURE_CHUNKHOUND_HELPER\\" research \\"how does X work\\"","description":"Run research"}',
                                    },
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "type": "user",
                                "message": {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "tool_result",
                                            "tool_use_id": research_tool_use_id,
                                            "content": wrapper_text,
                                            "is_error": False,
                                        }
                                    ],
                                },
                                "tool_use_result": {
                                    "stdout": wrapper_text,
                                    "stderr": "",
                                },
                            }
                        ),
                    ]
                ),
            )

            # --- Phase 3: validate and record ---
            entries = state.get("chunkhound_tool_proof_entries", [])
            self.assertEqual(len(entries), 2)

            report = rf.validate_and_record_chunkhound_tool_proof(
                meta=meta,
                work_dir=work_dir,
                provider="claude",
                review_stage="multipass_plan",
                prompt_template_name="mrereview_gh_local.md",
                adapter_meta={
                    "provider": "claude",
                    "chunkhound_helper_path": helper_path,
                    "chunkhound_tool_proof_entries": list(entries),
                },
            )

            persisted = json.loads((work_dir / "chunkhound_tool_validation.json").read_text(encoding="utf-8"))
            self.assertIsNotNone(report)
            assert report is not None
            self.assertTrue(report["valid"])
            self.assertEqual(report["provider"], "claude")
            self.assertEqual(report["observed_successful_calls"], ["search", "code_research"])
            self.assertEqual(report["observed_evidence_sources"], ["cli_helper_command_execution"])
            self.assertEqual(persisted["provider"], "claude")
            self.assertTrue(persisted["valid"])
            self.assertEqual(persisted["runs"][0]["review_stage"], "multipass_plan")
            self.assertEqual(persisted["runs"][0]["observed_successful_calls"], ["search", "code_research"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_chunkhound_tool_proof_rejects_forged_claude_stdout_without_helper_command(self) -> None:
        helper_path = "/tmp/cure/work/bin/cure-chunkhound"
        report = rf.validate_chunkhound_tool_proof(
            provider="claude",
            review_stage="singlepass_review",
            prompt_template_name="mrereview_gh_local.md",
            adapter_meta=self._claude_helper_adapter_meta(
                helper_path=helper_path,
                command='/bin/bash -lc \'printf "$CURE_CHUNKHOUND_HELPER"; printf "{\\"ok\\": true}"\'',
                payloads=[
                    {
                        "ok": True,
                        "command": "search",
                        "tool_name": "search",
                        "query": "needle",
                        "helper_path": helper_path,
                        "result": {"results": [], "pagination": {"offset": 0, "total_results": 0}},
                        "execution_stage": "tools/call",
                        "execution_stage_status": "ok",
                    },
                    {
                        "ok": True,
                        "command": "research",
                        "tool_name": "code_research",
                        "query": "cross-file question",
                        "helper_path": helper_path,
                        "result": {"summary": "grounded answer"},
                        "execution_stage": "tools/call",
                        "execution_stage_status": "ok",
                    },
                ],
            ),
        )

        self.assertIsNotNone(report)
        assert report is not None
        self.assertFalse(report["valid"])
        self.assertIn("search", str(report["failure_reason"]))
        self.assertTrue(
            any("did not invoke staged helper for the claimed tool" in str(detail.get("detail") or "") for detail in report["observed_failed_call_details"])
        )

    def test_validate_chunkhound_tool_proof_accepts_batched_claude_helper_entries(self) -> None:
        helper_path = "/tmp/cure/work/bin/cure-chunkhound"
        report = rf.validate_chunkhound_tool_proof(
            provider="claude",
            review_stage="singlepass_review",
            prompt_template_name="mrereview_gh_local.md",
            adapter_meta={
                "provider": "claude",
                "chunkhound_helper_path": helper_path,
                "chunkhound_tool_proof_entries": [
                    {
                        "payload": {
                            "ok": True,
                            "command": "search",
                            "tool_name": "search",
                            "query": "needle",
                            "helper_path": helper_path,
                            "result": {"results": [], "pagination": {"offset": 0, "total_results": 0}},
                            "execution_stage": "tools/call",
                            "execution_stage_status": "ok",
                        },
                        "stdout_excerpt": "batched helper stdout",
                        "command": '/bin/bash -lc \'"$CURE_CHUNKHOUND_HELPER" search "needle" && "$CURE_CHUNKHOUND_HELPER" research "cross-file question"\'',
                    },
                    {
                        "payload": {
                            "ok": True,
                            "command": "research",
                            "tool_name": "code_research",
                            "query": "cross-file question",
                            "helper_path": helper_path,
                            "result": {"summary": "grounded answer"},
                            "execution_stage": "tools/call",
                            "execution_stage_status": "ok",
                        },
                        "stdout_excerpt": "batched helper stdout",
                        "command": '/bin/bash -lc \'"$CURE_CHUNKHOUND_HELPER" search "needle" && "$CURE_CHUNKHOUND_HELPER" research "cross-file question"\'',
                    },
                ],
            },
        )

        self.assertIsNotNone(report)
        assert report is not None
        self.assertTrue(report["valid"])
        self.assertEqual(report["observed_successful_calls"], ["search", "code_research"])

    def test_validate_chunkhound_tool_proof_claude_missing_helper_path_fails_closed(self) -> None:
        report = rf.validate_chunkhound_tool_proof(
            provider="claude",
            review_stage="singlepass_review",
            prompt_template_name="mrereview_gh_local.md",
            adapter_meta={
                "provider": "claude",
                "chunkhound_tool_proof_entries": [
                    {
                        "payload": {
                            "ok": True,
                            "command": "search",
                            "tool_name": "search",
                            "query": "needle",
                            "helper_path": "/tmp/cure/work/bin/cure-chunkhound",
                            "result": {"results": [], "pagination": {"offset": 0, "total_results": 0}},
                        },
                        "stdout_excerpt": "helper payload",
                    },
                    {
                        "payload": {
                            "ok": True,
                            "command": "research",
                            "tool_name": "code_research",
                            "query": "cross-file question",
                            "helper_path": "/tmp/cure/work/bin/cure-chunkhound",
                            "result": {"summary": "grounded answer"},
                        },
                        "stdout_excerpt": "helper payload",
                    },
                ],
            },
        )

        self.assertIsNotNone(report)
        assert report is not None
        self.assertFalse(report["valid"])
        self.assertIn("missing staged helper path", str(report["failure_reason"]))

    def test_validate_chunkhound_tool_proof_rejected_claude_entries_remain_visible_when_valid(self) -> None:
        helper_path = "/tmp/cure/work/bin/cure-chunkhound"
        report = rf.validate_chunkhound_tool_proof(
            provider="claude",
            review_stage="singlepass_review",
            prompt_template_name="mrereview_gh_local.md",
            adapter_meta=self._claude_helper_adapter_meta(
                helper_path=helper_path,
                payloads=[
                    {
                        "ok": True,
                        "command": "search",
                        "tool_name": "search",
                        "query": "needle",
                        "helper_path": helper_path,
                        "result": {"results": [], "pagination": {"offset": 0, "total_results": 0}},
                        "execution_stage": "tools/call",
                        "execution_stage_status": "ok",
                    },
                    {
                        "ok": True,
                        "command": "search",
                        "tool_name": "search",
                        "query": "needle",
                        "helper_path": "/tmp/other/cure-chunkhound",
                        "result": {"results": [], "pagination": {"offset": 0, "total_results": 0}},
                        "execution_stage": "tools/call",
                        "execution_stage_status": "ok",
                    },
                    {
                        "ok": True,
                        "command": "research",
                        "tool_name": "code_research",
                        "query": "cross-file question",
                        "helper_path": helper_path,
                        "result": {"summary": "grounded answer"},
                        "execution_stage": "tools/call",
                        "execution_stage_status": "ok",
                    },
                ],
            ),
        )

        self.assertIsNotNone(report)
        assert report is not None
        self.assertTrue(report["valid"])
        self.assertEqual(report["observed_successful_calls"], ["search", "code_research"])
        self.assertTrue(
            any(detail["tool_name"] == "search" for detail in report["observed_failed_call_details"])
        )
        self.assertTrue(
            any("path mismatch" in str(detail.get("detail") or "") for detail in report["observed_failed_call_details"])
        )

    def test_validate_and_record_chunkhound_tool_proof_mixed_provider_report_uses_latest_provider(self) -> None:
        root = ROOT / ".tmp_test_chunkhound_tool_proof_mixed_provider_report"
        helper_path = "/tmp/cure/work/bin/cure-chunkhound"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            work_dir = root / "work"
            work_dir.mkdir(parents=True, exist_ok=True)
            meta: dict[str, object] = {"chunkhound": {"base_config_path": "/tmp/base.json"}}

            first = rf.validate_and_record_chunkhound_tool_proof(
                meta=meta,
                work_dir=work_dir,
                provider="codex",
                review_stage="singlepass_review",
                prompt_template_name="mrereview_gh_local.md",
                adapter_meta=self._write_codex_events(root=root, tool_names=["search", "code_research"]),
            )
            second = rf.validate_and_record_chunkhound_tool_proof(
                meta=meta,
                work_dir=work_dir,
                provider="claude",
                review_stage="singlepass_review",
                prompt_template_name="mrereview_gh_local.md",
                adapter_meta=self._claude_helper_adapter_meta(
                    helper_path=helper_path,
                    payloads=[
                        {
                            "ok": True,
                            "command": "search",
                            "tool_name": "search",
                            "query": "needle",
                            "helper_path": helper_path,
                            "result": {"results": [], "pagination": {"offset": 0, "total_results": 0}},
                            "execution_stage": "tools/call",
                            "execution_stage_status": "ok",
                        },
                        {
                            "ok": True,
                            "command": "research",
                            "tool_name": "code_research",
                            "query": "cross-file question",
                            "helper_path": helper_path,
                            "result": {"summary": "grounded answer"},
                            "execution_stage": "tools/call",
                            "execution_stage_status": "ok",
                        },
                    ],
                ),
            )

            persisted = json.loads((work_dir / "chunkhound_tool_validation.json").read_text(encoding="utf-8"))
            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            self.assertEqual(persisted["schema_version"], 2)
            self.assertEqual(persisted["provider"], "claude")
            self.assertEqual([run["provider"] for run in persisted["runs"]], ["codex", "claude"])
            self.assertEqual(meta["chunkhound"]["tool_validation"]["provider"], "claude")
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
                        "aggregated_output": (
                            payload if isinstance(payload, str) else json.dumps(payload, indent=2)
                        ),
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
        extra_cli_args: list[str] | None = None,
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
        cli_args = [
            "pr",
            "https://github.com/acme/repo/pull/14",
            "--if-reviewed",
            "new",
            "--ui",
            "off",
            "--quiet",
            "--no-stream",
        ]
        if extra_cli_args:
            cli_args.extend(extra_cli_args)
        args = rf.build_parser().parse_args(cli_args)
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
                            "- Input lacks validation. Sources: `src/app.py:2`",
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
            elif output_path.name in {"review.md", "review.candidate.md"}:
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
            self.assertIn("review generated with [CURe]", review_md)
            self.assertIn("multi-stage - stages: 1", review_md)
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
            self.assertIn("review generated with [CURe]", review_md)
            self.assertIn("single-stage", review_md)
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
            helper_path = "/tmp/cure/work/bin/cure-chunkhound"
            search_payload = {
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
            }
            research_payload = {
                "ok": True,
                "command": "research",
                "tool_name": "code_research",
                "query": "cross-file question",
                "helper_path": helper_path,
                "result": {"summary": "grounded answer"},
                "execution_stage": "tools/call",
                "execution_stage_status": "ok",
            }
            adapter_meta = self._write_helper_command_events(
                work_dir=work_dir,
                commands=["search", "research"],
                raw_outputs={
                    "search": "\n".join(
                        [
                            "preflight stage=initialize status=ok",
                            "preflight stage=tools/list status=ok",
                            json.dumps(search_payload, indent=2),
                        ]
                    ),
                    "research": "\n".join(
                        [
                            "preflight stage=initialize status=ok",
                            "preflight stage=notifications/initialized status=ok",
                            "preflight stage=tools/list status=ok",
                            json.dumps(research_payload, indent=2),
                        ]
                    ),
                },
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
            self.assertIn("review generated with [CURe]", review_md)
            self.assertIn("multi-stage - stages: 0", review_md)
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
                            "- Input lacks validation. Sources: `src/app.py:2`",
                            "",
                            "### Suggested actions",
                            "- Add checks",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                commands = ["search"]
            elif output_path.name in {"review.md", "review.candidate.md"}:
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
                            "- Input lacks validation. Sources: `src/app.py:2`",
                            "",
                            "### Suggested actions",
                            "- Add checks",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                adapter_meta = self._write_helper_command_events(work_dir=work_dir, commands=["search"])
            elif output_path.name in {"review.md", "review.candidate.md"}:
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
            },
            llm_resolved_override={
                "provider": "codex",
                "preset": "test-codex",
                "model": "gpt-5.4",
                "reasoning_effort": "medium",
                "capabilities": {"supports_resume": True},
            },
            llm_resolution_meta_override={
                "resolved": {
                    "model_source": "cli",
                    "reasoning_effort_source": "cli",
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
            self.assertIsNone(stage_invocations["review.plan.md"]["plan_reasoning_effort"])
            self.assertEqual(stage_invocations["review.plan.md"]["reasoning_effort_source"], "reasoning_effort:cli")
            self.assertEqual(stage_invocations["review.step-01.md"]["reasoning_effort"], "medium")
            self.assertEqual(stage_invocations["review.step-01.md"]["reasoning_effort_source"], "reasoning_effort:cli")
            self.assertIn('model_reasoning_effort="medium"', stage_invocations["review.step-01.md"]["codex_flags"])
            self.assertEqual(stage_invocations["review.md"]["reasoning_effort"], "medium")
            self.assertEqual(stage_invocations["review.md"]["reasoning_effort_source"], "reasoning_effort:cli")
            self.assertIn('model_reasoning_effort="medium"', stage_invocations["review.md"]["codex_flags"])
            self.assertEqual(meta["llm"]["reasoning_effort"], "medium")
            self.assertEqual(meta["multipass"]["llm"]["stages"]["plan"]["effective_reasoning_effort"], "medium")
            self.assertEqual(meta["multipass"]["llm"]["stages"]["step"]["effective_reasoning_effort"], "medium")
            self.assertEqual(meta["multipass"]["llm"]["stages"]["synth"]["effective_reasoning_effort"], "medium")
            self.assertEqual(meta["multipass"]["llm"]["review_artifact_stage"], "synth")
            self.assertEqual(
                meta["multipass"]["llm"]["review_artifact_llm"]["effective_reasoning_effort"],
                "medium",
            )
            self.assertEqual(meta["multipass"]["runs"][0]["llm"]["effective_reasoning_effort"], "medium")
            self.assertIn("review generated with [CURe]", review_md)
            self.assertIn("multi-stage - stages: 1", review_md)
            self.assertIn("model gpt-5.4/medium", review_md)
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
            elif output_path.name in {"review.md", "review.candidate.md"}:
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
                            "- Input lacks validation. Sources: `src/app.py:2`",
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
            elif output_path.name in {"review.md", "review.candidate.md"}:
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

    def test_pr_flow_dry_run_chunkhound_marks_session_metadata_and_keeps_tool_proof(self) -> None:
        root = ROOT / ".tmp_test_codex_tool_proof_dry_run"

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

        runtime_policy = self._codex_runtime_policy()
        runtime_policy["env"] = {
            "CURE_CHUNKHOUND_HELPER": "/tmp/cure/work/bin/cure-chunkhound",
            "CURE_CHUNKHOUND_DRY_RUN": "1",
        }
        runtime_policy["metadata"] = {
            "provider": "codex",
            "chunkhound_access_mode": "cli_helper_daemon",
            "chunkhound_dry_run": True,
        }
        runtime_policy["staged_paths"] = {
            "chunkhound_helper": "/tmp/cure/work/bin/cure-chunkhound",
        }

        root, calls = self._run_pr_flow_for_tool_proof(
            root=root,
            profile_resolved="normal",
            multipass_enabled=False,
            llm_side_effect=llm_side_effect,
            runtime_policy_override=runtime_policy,
            extra_cli_args=["--dry-run-chunkhound"],
        )
        try:
            session_dir = next((root / "sandboxes").iterdir())
            meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            report = json.loads((session_dir / "work" / "chunkhound_tool_validation.json").read_text(encoding="utf-8"))
            self.assertEqual(calls, ["review.md"])
            self.assertTrue(meta["notes"]["dry_run_chunkhound"])
            self.assertTrue(meta["options"]["dry_run_chunkhound"])
            self.assertTrue(meta["chunkhound"]["dry_run"])
            self.assertTrue(meta["agent_runtime"]["chunkhound_dry_run"])
            self.assertEqual(meta["codex"]["env"]["CURE_CHUNKHOUND_DRY_RUN"], "1")
            self.assertEqual(report["runs"][0]["observed_successful_calls"], ["search", "code_research"])
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
            self.assertIn("review generated with [CURe]", followup_md)
            self.assertIn("single-stage", followup_md)
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
            rf.validate_and_record_chunkhound_tool_proof(
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
                                "capabilities": {"supports_resume": True},
                            },
                            {
                                "resolved": {
                                    "model_source": "cli",
                                    "reasoning_effort_source": "cli",
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
                            },
                            {
                                "multipass": {
                                    "enabled": True,
                                    "max_steps": 20,
                                    "grounding_mode": "strict",
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
                                "- Input lacks validation. Sources: `src/app.py:2`",
                                "",
                                "### Suggested actions",
                                "- Add checks",
                                "",
                            ]
                        ),
                        encoding="utf-8",
                    )
                    adapter_meta = self._write_helper_command_events(work_dir=work_dir, commands=["search"])
                elif output_path.name in {"review.md", "review.candidate.md"}:
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
                                "capabilities": {"supports_resume": True},
                            },
                            {
                                "resolved": {
                                    "model_source": "cli",
                                    "reasoning_effort_source": "cli",
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
                            },
                            {
                                "multipass": {
                                    "enabled": True,
                                    "max_steps": 20,
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
            report = json.loads((work_dir / "chunkhound_tool_validation.json").read_text(encoding="utf-8"))
            review_md_text = review_md.read_text(encoding="utf-8")
            self.assertEqual(rc, 0)
            self.assertEqual(calls, ["review.step-01.md", "review.md"])
            self.assertEqual(refreshed["status"], "done")
            self.assertTrue(refreshed["chunkhound"]["tool_validation"]["valid"])
            self.assertEqual(refreshed["chunkhound"]["tool_validation"]["evidence_sources"], ["cli_helper_command_execution"])
            self.assertEqual([run["review_stage"] for run in report["runs"]], ["multipass_step", "multipass_synth"])
            self.assertEqual(stage_invocations["review.step-01.md"]["reasoning_effort"], "medium")
            self.assertEqual(stage_invocations["review.step-01.md"]["reasoning_effort_source"], "reasoning_effort:cli")
            self.assertEqual(stage_invocations["review.md"]["reasoning_effort"], "medium")
            self.assertEqual(stage_invocations["review.md"]["reasoning_effort_source"], "reasoning_effort:cli")
            self.assertEqual(refreshed["llm"]["reasoning_effort"], "medium")
            self.assertEqual(refreshed["multipass"]["llm"]["stages"]["step"]["effective_reasoning_effort"], "medium")
            self.assertEqual(refreshed["multipass"]["llm"]["stages"]["synth"]["effective_reasoning_effort"], "medium")
            self.assertEqual(
                refreshed["multipass"]["llm"]["review_artifact_llm"]["effective_reasoning_effort"],
                "medium",
            )
            self.assertEqual(review_md_text.count("<!-- CURE_REVIEW_FOOTER_START -->"), 1)
            self.assertIn("review generated with [CURe]", review_md_text)
            self.assertIn("multi-stage - stages: 1", review_md_text)
            self.assertIn("model gpt-5.4/medium", review_md_text)
            self.assertIn("session session-1", review_md_text)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_resume_flow_completed_multipass_latest_head_noop_refreshes_footer(self) -> None:
        root = ROOT / ".tmp_test_resume_incremental_noop_footer"
        cfg = root / "reviewflow.toml"
        head_sha = "1111111111111111111111111111111111111111"
        review_body = _sectioned_review_markdown(business="APPROVE", technical="APPROVE")
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
            plan_json = work_dir / "review_plan.json"
            plan_json.write_text(
                json.dumps(
                    {
                        "abort": False,
                        "abort_reason": None,
                        "jira_keys": ["ABC-1"],
                        "steps": [{"id": "01", "title": "API review", "focus": "api"}],
                    }
                ),
                encoding="utf-8",
            )
            review_md = session_dir / "review.md"
            review_md.write_text(review_body, encoding="utf-8")
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
                "base_ref": "main",
                "base_ref_for_review": "cure_base__main",
                "head_sha": head_sha,
                "review_head_sha": head_sha,
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
                    "validation": {"mode": "strict", "invalid_artifacts": [], "has_invalid_artifacts": False},
                },
            }
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
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "_utc_now_iso",
                        side_effect=["2026-03-10T01:00:00+00:00", "2026-03-10T01:00:05+00:00"],
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "_update_resume_session_repo_for_incremental_review",
                        return_value=(head_sha, head_sha),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "run_llm_exec",
                        side_effect=AssertionError("latest-head no-op resume should not rerun review generation"),
                    )
                )
                rc = rf.resume_flow(args, paths=paths, config_path=cfg, codex_base_config_path=cfg)

            refreshed = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            review_md_text = review_md.read_text(encoding="utf-8")
            self.assertEqual(rc, 0)
            self.assertEqual(refreshed["status"], "done")
            self.assertEqual(review_md_text.count("<!-- CURE_REVIEW_FOOTER_START -->"), 1)
            self.assertIn("review generated with [CURe]", review_md_text)
            self.assertIn("multi-stage - stages: 1", review_md_text)
            self.assertIn(" · 5s_", review_md_text)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_resume_flow_completed_noop_refreshes_footer(self) -> None:
        root = ROOT / ".tmp_test_resume_completed_noop_footer"
        cfg = root / "reviewflow.toml"
        review_body = _sectioned_review_markdown(business="APPROVE", technical="APPROVE")
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
            review_md.write_text(review_body, encoding="utf-8")
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
                "review_head_sha": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
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
            }
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
                                "capabilities": {"supports_resume": True},
                            },
                            {
                                "resolved": {
                                    "model_source": "cli",
                                    "reasoning_effort_source": "cli",
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
                stack.enter_context(mock.patch.object(rf, "_run_chunkhound_access_preflight"))
                stack.enter_context(mock.patch.object(rf, "_run_review_intelligence_preflight"))
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "run_llm_exec",
                        side_effect=AssertionError("completed no-op resume should not rerun review generation"),
                    )
                )
                rc = rf.resume_flow(args, paths=paths, config_path=cfg, codex_base_config_path=cfg)

            refreshed = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            review_md_text = review_md.read_text(encoding="utf-8")
            self.assertEqual(rc, 0)
            self.assertEqual(refreshed["status"], "done")
            self.assertEqual(review_md_text.count("<!-- CURE_REVIEW_FOOTER_START -->"), 1)
            self.assertIn("review generated with [CURe]", review_md_text)
            self.assertIn("single-stage", review_md_text)
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
                "- Input lacks validation. Sources: `src/app.py:2`",
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
            self.assertEqual(stage_invocations["review.md"]["reasoning_effort"], "medium")
            self.assertEqual(stage_invocations["review.md"]["reasoning_effort_source"], "reasoning_effort:cli")
            self.assertEqual(refreshed["multipass"]["llm"]["stages"]["plan"]["effective_reasoning_effort"], "high")
            self.assertEqual(refreshed["multipass"]["llm"]["stages"]["step"]["effective_reasoning_effort"], "medium")
            self.assertEqual(refreshed["multipass"]["llm"]["stages"]["synth"]["effective_reasoning_effort"], "medium")
            self.assertEqual(refreshed["multipass"]["llm"]["review_artifact_stage"], "synth")
            self.assertEqual(
                refreshed["multipass"]["llm"]["review_artifact_llm"]["effective_reasoning_effort"],
                "medium",
            )
            self.assertIn("model gpt-5.4/medium", review_md_text)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_resume_flow_completed_multipass_uses_incremental_synth_only_when_resume_planner_says_so(self) -> None:
        root = ROOT / ".tmp_test_resume_incremental_synth_only"
        cfg = root / "reviewflow.toml"
        old_head = "1111111111111111111111111111111111111111"
        new_head = "2222222222222222222222222222222222222222"
        valid_step_markdown = "\n".join(
            [
                "### Step Result: 01 — API review",
                "**Focus**: api",
                "",
                "### Steps taken",
                "- checked repo",
                "",
                "### Findings",
                "- Existing validation looks stable. Sources: `src/app.py:2`",
                "",
                "### Suggested actions",
                "- None.",
                "",
            ]
        )
        valid_synth_markdown = "\n".join(
            [
                "### Steps taken",
                "- Reviewed latest diff",
                "",
                "**Summary**: incremental resume is happy",
                "",
                "## Business / Product Assessment",
                "**Verdict**: APPROVE",
                "",
                "### Strengths",
                "- Cosmetic changes remain aligned. Sources: `src/app.py:2`",
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
                "- Previous concerns appear resolved. Sources: `src/app.py:2`",
                "",
                "### In Scope Issues",
                "- None.",
                "",
                "### Out of Scope Issues",
                "- None.",
                "",
                "### Reusability",
                "- Existing review context remained useful. Sources: `src/app.py:2`",
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
                        "steps": [{"id": "01", "title": "API review", "focus": "api"}],
                    }
                ),
                encoding="utf-8",
            )
            step_output = session_dir / "review.step-01.md"
            step_output.write_text(valid_step_markdown, encoding="utf-8")
            review_md = session_dir / "review.md"
            review_md.write_text(valid_synth_markdown, encoding="utf-8")
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
                "base_ref": "main",
                "base_ref_for_review": "cure_base__main",
                "head_sha": old_head,
                "review_head_sha": old_head,
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
                    "validation": {"mode": "strict", "invalid_artifacts": [], "has_invalid_artifacts": False},
                },
            }
            (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

            calls: list[str] = []

            def fake_run_llm_exec(**kwargs: object) -> rf.LlmRunResult:
                output_path = Path(str(kwargs["output_path"]))
                calls.append(output_path.name)
                if output_path.name == "review.resume-plan.md":
                    output_path.write_text(
                        "\n".join(
                            [
                                "### Steps taken",
                                "- Read prior review",
                                "",
                                "### Resume Strategy",
                                "- Cosmetic-only delta",
                                "",
                                "### Resume Strategy JSON",
                                "```json",
                                json.dumps(
                                    {
                                        "decision": "synth_only",
                                        "reason": "The delta is cosmetic and the previous review context is sufficient.",
                                        "reopen_step_ids": [],
                                        "new_steps": [],
                                    },
                                    indent=2,
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
                elif output_path.name in {"review.md", "review.candidate.md"}:
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
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "_update_resume_session_repo_for_incremental_review",
                        return_value=(old_head, new_head),
                    )
                )
                stack.enter_context(mock.patch.object(rf, "run_llm_exec", side_effect=fake_run_llm_exec))
                rc = rf.resume_flow(args, paths=paths, config_path=cfg, codex_base_config_path=cfg)

            refreshed = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(rc, 0)
            self.assertEqual(calls, ["review.resume-plan.md", "review.md"])
            self.assertEqual(refreshed["review_head_sha"], new_head)
            self.assertEqual(refreshed["head_sha"], new_head)
            self.assertEqual(refreshed["multipass"]["resume"]["decision"], "synth_only")
            self.assertEqual(refreshed["multipass"]["resume"]["previous_review_head_sha"], old_head)
            self.assertEqual(refreshed["multipass"]["resume"]["current_review_head_sha"], new_head)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_resume_flow_completed_multipass_finalizes_noncritical_incremental_synth_grounding_issues(self) -> None:
        root = ROOT / ".tmp_test_resume_incremental_synth_grounding_failure"
        cfg = root / "reviewflow.toml"
        old_head = "1111111111111111111111111111111111111111"
        new_head = "2222222222222222222222222222222222222222"
        valid_step_markdown = "\n".join(
            [
                "### Step Result: 01 — API review",
                "**Focus**: api",
                "",
                "### Steps taken",
                "- checked repo",
                "",
                "### Findings",
                "- Existing validation looks stable. Sources: `src/app.py:2`",
                "",
                "### Suggested actions",
                "- None.",
                "",
            ]
        )
        invalid_synth_markdown = "\n".join(
            [
                "### Steps taken",
                "- Reviewed latest diff",
                "",
                "**Summary**: incremental resume needs direct evidence",
                "",
                "## Business / Product Assessment",
                "**Verdict**: APPROVE",
                "",
                "### Strengths",
                "- Cosmetic changes remain aligned. Sources: `review.step-01.md:8`",
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
                "- Previous concerns appear resolved. Sources: `review.step-01.md:8`",
                "",
                "### In Scope Issues",
                "- None.",
                "",
                "### Out of Scope Issues",
                "- None.",
                "",
                "### Reusability",
                "- Existing review context remained useful. Sources: `review.step-01.md:8`",
                "",
            ]
        )
        valid_synth_markdown = "\n".join(
            [
                "### Steps taken",
                "- Reviewed latest diff",
                "",
                "**Summary**: incremental resume is happy",
                "",
                "## Business / Product Assessment",
                "**Verdict**: APPROVE",
                "",
                "### Strengths",
                "- Cosmetic changes remain aligned. Sources: `src/app.py:2`",
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
                "- Previous concerns appear resolved. Sources: `src/app.py:2`",
                "",
                "### In Scope Issues",
                "- None.",
                "",
                "### Out of Scope Issues",
                "- None.",
                "",
                "### Reusability",
                "- Existing review context remained useful. Sources: `src/app.py:2`",
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
                        "steps": [{"id": "01", "title": "API review", "focus": "api"}],
                    }
                ),
                encoding="utf-8",
            )
            step_output = session_dir / "review.step-01.md"
            step_output.write_text(valid_step_markdown, encoding="utf-8")
            review_md = session_dir / "review.md"
            review_md.write_text(valid_synth_markdown, encoding="utf-8")
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
                "base_ref": "main",
                "base_ref_for_review": "cure_base__main",
                "head_sha": old_head,
                "review_head_sha": old_head,
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
                    "validation": {"mode": "strict", "invalid_artifacts": [], "has_invalid_artifacts": False},
                },
            }
            (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

            calls: list[str] = []

            def fake_run_llm_exec(**kwargs: object) -> rf.LlmRunResult:
                output_path = Path(str(kwargs["output_path"]))
                calls.append(output_path.name)
                if output_path.name == "review.resume-plan.md":
                    output_path.write_text(
                        "\n".join(
                            [
                                "### Steps taken",
                                "- Read prior review",
                                "",
                                "### Resume Strategy",
                                "- Cosmetic-only delta",
                                "",
                                "### Resume Strategy JSON",
                                "```json",
                                json.dumps(
                                    {
                                        "decision": "synth_only",
                                        "reason": "The delta is cosmetic and the previous review context is sufficient.",
                                        "reopen_step_ids": [],
                                        "new_steps": [],
                                    },
                                    indent=2,
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
                elif output_path.name in {"review.md", "review.candidate.md"}:
                    output_path.write_text(invalid_synth_markdown, encoding="utf-8")
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
            messages: list[str] = []

            def capture(*args: object) -> None:
                messages.append(" ".join(str(arg) for arg in args))

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
                        "_update_resume_session_repo_for_incremental_review",
                        return_value=(old_head, new_head),
                    )
                )
                stack.enter_context(mock.patch.object(rf, "_eprint", side_effect=capture))
                stack.enter_context(mock.patch.object(rf, "run_llm_exec", side_effect=fake_run_llm_exec))
                rc = rf.resume_flow(args, paths=paths, config_path=cfg, codex_base_config_path=cfg)

            refreshed = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            report = json.loads((session_dir / "work" / "grounding_report.json").read_text(encoding="utf-8"))
            rewritten_review = review_md.read_text(encoding="utf-8")
            playbook = "\n".join(messages)
            self.assertEqual(rc, 0)
            self.assertEqual(calls, ["review.resume-plan.md", "review.md"])
            self.assertEqual(refreshed["status"], "done")
            self.assertEqual(report["invalid_artifacts"], [])
            self.assertEqual(playbook, "")
            self.assertIn("## Grounding omission summary", rewritten_review)
            self.assertIn("[non-critical]", rewritten_review)
            self.assertIn("- None.", rewritten_review)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_resume_flow_completed_multipass_can_reopen_existing_steps_and_add_new_step(self) -> None:
        root = ROOT / ".tmp_test_resume_incremental_targeted"
        cfg = root / "reviewflow.toml"
        old_head = "1111111111111111111111111111111111111111"
        new_head = "3333333333333333333333333333333333333333"
        original_step_markdown = "\n".join(
            [
                "### Step Result: 01 — API review",
                "**Focus**: api",
                "",
                "### Steps taken",
                "- checked repo",
                "",
                "### Findings",
                "- Existing validation looks stable. Sources: `src/app.py:2`",
                "",
                "### Suggested actions",
                "- None.",
                "",
            ]
        )
        valid_synth_markdown = "\n".join(
            [
                "### Steps taken",
                "- Combined resumed steps",
                "",
                "**Summary**: targeted resume covered the new delta",
                "",
                "## Business / Product Assessment",
                "**Verdict**: APPROVE",
                "",
                "### Strengths",
                "- Delta remains within scope. Sources: `src/app.py:2`",
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
                "- Reopened and new analysis converged. Sources: `src/app.py:2`",
                "",
                "### In Scope Issues",
                "- None.",
                "",
                "### Out of Scope Issues",
                "- None.",
                "",
                "### Reusability",
                "- Targeted resume stayed efficient. Sources: `src/app.py:2`",
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
                        "steps": [{"id": "01", "title": "API review", "focus": "api"}],
                    }
                ),
                encoding="utf-8",
            )
            step_output = session_dir / "review.step-01.md"
            step_output.write_text(original_step_markdown, encoding="utf-8")
            review_md = session_dir / "review.md"
            review_md.write_text(valid_synth_markdown, encoding="utf-8")
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
                "base_ref": "main",
                "base_ref_for_review": "cure_base__main",
                "head_sha": old_head,
                "review_head_sha": old_head,
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
                    "validation": {"mode": "strict", "invalid_artifacts": [], "has_invalid_artifacts": False},
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
                    "reasoning_effort_source": ((resolution_meta.get("resolved") or {}).get("reasoning_effort_source")),
                }
                if output_path.name == "review.resume-plan.md":
                    output_path.write_text(
                        "\n".join(
                            [
                                "### Steps taken",
                                "- Read prior review",
                                "",
                                "### Resume Strategy",
                                "- Reopen API and add delta pass",
                                "",
                                "### Resume Strategy JSON",
                                "```json",
                                json.dumps(
                                    {
                                        "decision": "targeted",
                                        "reason": "The new delta changes API behavior and introduces a new surface worth a fresh targeted pass.",
                                        "reopen_step_ids": ["01"],
                                        "new_steps": [
                                            {
                                                "id": "02",
                                                "title": "Delta review",
                                                "focus": "new behavior since the last reviewed head",
                                            }
                                        ],
                                    },
                                    indent=2,
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
                                "**Focus**: api",
                                "",
                                "### Steps taken",
                                "- Re-read changed files",
                                "",
                                "### Findings",
                                "- The updated API path is now coherent. Sources: `src/app.py:2`",
                                "",
                                "### Suggested actions",
                                "- None.",
                                "",
                            ]
                        ),
                        encoding="utf-8",
                    )
                    adapter_meta = self._write_helper_command_events(work_dir=work_dir, commands=["search"])
                elif output_path.name == "review.step-02.md":
                    output_path.write_text(
                        "\n".join(
                            [
                                "### Step Result: 02 — Delta review",
                                "**Focus**: new behavior since the last reviewed head",
                                "",
                                "### Steps taken",
                                "- Examined incremental diff",
                                "",
                                "### Findings",
                                "- The new delta remains cosmetic in effect. Sources: `src/app.py:2`",
                                "",
                                "### Suggested actions",
                                "- None.",
                                "",
                            ]
                        ),
                        encoding="utf-8",
                    )
                    adapter_meta = self._write_helper_command_events(work_dir=work_dir, commands=["search"])
                elif output_path.name in {"review.md", "review.candidate.md"}:
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
                                "step_workers": 1,
                                "grounding_mode": "strict",
                            },
                            {
                                "multipass": {
                                    "enabled": True,
                                    "max_steps": 20,
                                    "step_workers": 1,
                                    "grounding_mode": "strict",
                                }
                            },
                        ),
                    )
                )
                stack.enter_context(mock.patch.object(rf, "_run_review_intelligence_preflight"))
                stack.enter_context(
                    mock.patch.object(
                        rf,
                        "_update_resume_session_repo_for_incremental_review",
                        return_value=(old_head, new_head),
                    )
                )
                stack.enter_context(mock.patch.object(rf, "run_llm_exec", side_effect=fake_run_llm_exec))
                rc = rf.resume_flow(args, paths=paths, config_path=cfg, codex_base_config_path=cfg)

            refreshed = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            updated_plan = json.loads(plan_json.read_text(encoding="utf-8"))
            self.assertEqual(rc, 0)
            self.assertEqual(calls, ["review.resume-plan.md", "review.step-01.md", "review.step-02.md", "review.md"])
            self.assertEqual(updated_plan["steps"][1]["id"], "02")
            self.assertEqual(refreshed["review_head_sha"], new_head)
            self.assertEqual(refreshed["multipass"]["resume"]["decision"], "targeted")
            self.assertEqual(
                refreshed["multipass"]["artifacts"]["step_outputs"],
                [str(session_dir / "review.step-01.md"), str(session_dir / "review.step-02.md")],
            )
            self.assertEqual([item["status"] for item in refreshed["multipass"]["step_states"]], ["completed", "completed"])
            self.assertEqual(stage_invocations["review.step-01.md"]["reasoning_effort"], "medium")
            self.assertEqual(stage_invocations["review.step-02.md"]["reasoning_effort"], "medium")
            self.assertEqual(stage_invocations["review.md"]["reasoning_effort"], "medium")
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_resume_flow_completed_multipass_rejects_unknown_reopened_step_ids(self) -> None:
        root = ROOT / ".tmp_test_resume_incremental_unknown_reopen_step"
        cfg = root / "reviewflow.toml"
        old_head = "1111111111111111111111111111111111111111"
        new_head = "4444444444444444444444444444444444444444"
        valid_synth_markdown = "\n".join(
            [
                "### Steps taken",
                "- Combined resumed steps",
                "",
                "**Summary**: targeted resume covered the new delta",
                "",
                "## Business / Product Assessment",
                "**Verdict**: APPROVE",
                "",
                "### Strengths",
                "- Delta remains within scope. Sources: `src/app.py:2`",
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
                "- Reopened and new analysis converged. Sources: `src/app.py:2`",
                "",
                "### In Scope Issues",
                "- None.",
                "",
                "### Out of Scope Issues",
                "- None.",
                "",
                "### Reusability",
                "- Targeted resume stayed efficient. Sources: `src/app.py:2`",
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
                        "steps": [{"id": "01", "title": "API review", "focus": "api"}],
                    }
                ),
                encoding="utf-8",
            )
            (session_dir / "review.step-01.md").write_text(
                "\n".join(
                    [
                        "### Step Result: 01 — API review",
                        "**Focus**: api",
                        "",
                        "### Steps taken",
                        "- checked repo",
                        "",
                        "### Findings",
                        "- Existing validation looks stable. Sources: `src/app.py:2`",
                        "",
                        "### Suggested actions",
                        "- None.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            review_md = session_dir / "review.md"
            review_md.write_text(valid_synth_markdown, encoding="utf-8")
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
                "base_ref": "main",
                "base_ref_for_review": "cure_base__main",
                "head_sha": old_head,
                "review_head_sha": old_head,
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
                    "validation": {"mode": "strict", "invalid_artifacts": [], "has_invalid_artifacts": False},
                },
            }
            (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

            calls: list[str] = []

            def fake_run_llm_exec(**kwargs: object) -> rf.LlmRunResult:
                output_path = Path(str(kwargs["output_path"]))
                calls.append(output_path.name)
                if output_path.name != "review.resume-plan.md":
                    raise AssertionError(f"unexpected output path: {output_path}")
                output_path.write_text(
                    "\n".join(
                        [
                            "### Steps taken",
                            "- Read prior review",
                            "",
                            "### Resume Strategy",
                            "- Planner asked to reopen a nonexistent step",
                            "",
                            "### Resume Strategy JSON",
                            "```json",
                            json.dumps(
                                {
                                    "decision": "targeted",
                                    "reason": "The new delta supposedly reopens prior work, but the requested step id is not present in the persisted plan.",
                                    "reopen_step_ids": ["99"],
                                    "new_steps": [],
                                },
                                indent=2,
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
                                "step_workers": 1,
                                "grounding_mode": "strict",
                                "step_reasoning_effort": "low",
                                "synth_reasoning_effort": "xhigh",
                            },
                            {
                                "multipass": {
                                    "enabled": True,
                                    "max_steps": 20,
                                    "step_workers": 1,
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
                        "_update_resume_session_repo_for_incremental_review",
                        return_value=(old_head, new_head),
                    )
                )
                stack.enter_context(mock.patch.object(rf, "run_llm_exec", side_effect=fake_run_llm_exec))
                with self.assertRaisesRegex(rf.ReviewflowError, "unknown reopen_step_ids"):
                    rf.resume_flow(args, paths=paths, config_path=cfg, codex_base_config_path=cfg)

            refreshed = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(calls, ["review.resume-plan.md"])
            self.assertEqual(refreshed["status"], "error")
            self.assertEqual(refreshed["multipass"]["resume"]["decision"], "targeted")
            self.assertEqual(refreshed["multipass"]["resume"]["reopen_step_ids"], ["99"])
            self.assertFalse((session_dir / "review.step-02.md").exists())
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
                        "- API concern. Sources: `src/app.py:2`",
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
                                "- Test concern. Sources: `src/app.py:3`",
                                "",
                            ]
                        ),
                        encoding="utf-8",
                    )
                    adapter_meta = self._write_helper_command_events(work_dir=work_dir, commands=["search"])
                elif output_path.name in {"review.md", "review.candidate.md"}:
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
        ) as pr_flow, mock.patch(
            "cure_commands.ensure_chunkhound_bootstrap_ready",
            return_value=False,
        ):
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


class MultipassGroundingRecoveryUnitTests(unittest.TestCase):
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

    def test_apply_synth_severity_finalization_drops_only_targeted_duplicate_bullet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_dir = root / "repo"
            work_dir = root / "work"
            repo_dir.mkdir()
            work_dir.mkdir()
            (repo_dir / "pkg").mkdir()
            (repo_dir / "pkg" / "module.py").write_text("a\nb\nc\n", encoding="utf-8")
            review_md = root / "review.md"
            review_md.write_text(
                "\n".join(
                    [
                        "### Steps taken",
                        "- Read repo",
                        "",
                        "**Summary**: ok",
                        "",
                        "## Business / Product Assessment",
                        "**Verdict**: APPROVE",
                        "",
                        "### Strengths",
                        "- Shared duplicate bullet. Sources: `pkg/module.py:2`",
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
                        "- Shared duplicate bullet. Sources: `pkg/module.py:2`",
                        "",
                        "### In Scope Issues",
                        "- Grounded issue. Sources: `pkg/module.py:3`",
                        "",
                        "### Out of Scope Issues",
                        "- None.",
                        "",
                        "### Reusability",
                        "- Reusable note. Sources: `pkg/module.py:1`",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            finalized, _, dropped = rf._apply_synth_severity_finalization(
                meta={},
                work_dir=work_dir,
                grounding_mode="strict",
                artifact_path=review_md,
                step_outputs=[],
                repo_dir=repo_dir,
                validation={
                    "valid": False,
                    "invalid_bullets": [
                        {
                            "section": "Strengths",
                            "section_label": "'### Strengths' under '## Business / Product Assessment' (line 9)",
                            "section_line": 9,
                            "section_key": "Business / Product Assessment|Strengths|9",
                            "parent": "Business / Product Assessment",
                            "bullet_index": 1,
                            "bullet_text": "- Shared duplicate bullet. Sources: `pkg/module.py:2`",
                            "critical": False,
                            "reason": "bad cite",
                        }
                    ],
                },
                ui_enabled=False,
                allow_critical_omission=False,
            )

            self.assertTrue(finalized)
            self.assertEqual(len(dropped), 1)
            rewritten = review_md.read_text(encoding="utf-8")
            self.assertIn("## Grounding omission summary", rewritten)
            self.assertIn("## Business / Product Assessment\n**Verdict**: APPROVE\n\n### Strengths\n- None.", rewritten)
            self.assertIn(
                "## Technical Assessment\n**Verdict**: REQUEST CHANGES\n\n### Strengths\n- Shared duplicate bullet. Sources: `pkg/module.py:2`",
                rewritten,
            )

    def test_execute_multipass_synth_stage_retries_with_codex_effort_override_in_tty_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta_path = root / "meta.json"
            progress = rf.SessionProgress(meta_path, quiet=True)
            progress.init({"session_id": "session-1", "multipass": {"runs": []}, "llm": {}, "codex": {}})
            review_md = root / "review.md"
            invalid_validation = {"valid": False, "errors": ["missing citation"], "invalid_bullets": []}
            valid_validation = {"valid": True, "errors": [], "invalid_bullets": []}
            llm_result = rf.LlmRunResult(
                adapter_meta={"usage": {"input_tokens": 1, "output_tokens": 1}},
                resume=None,
            )
            synth_llm = {
                "resolved": {"provider": "codex", "model": "gpt-5.4", "reasoning_effort": "medium"},
                "resolution_meta": {
                    "resolved": {
                        "model": "gpt-5.4",
                        "reasoning_effort": "medium",
                        "reasoning_effort_source": "cli",
                        "reasoning_effort_source_detail": "cli",
                    }
                },
                "meta": {"provider": "codex", "effective_reasoning_effort": "medium"},
            }
            run_invocations: list[dict[str, Any]] = []

            def capture_run_llm_exec(**kwargs: Any) -> rf.LlmRunResult:
                runtime_policy = kwargs["runtime_policy"] if isinstance(kwargs.get("runtime_policy"), dict) else {}
                resolution_meta = kwargs["resolution_meta"] if isinstance(kwargs.get("resolution_meta"), dict) else {}
                run_invocations.append(
                    {
                        "resolved": dict(kwargs["resolved"]) if isinstance(kwargs.get("resolved"), dict) else {},
                        "resolution_meta": dict(resolution_meta),
                        "codex_flags": list(runtime_policy.get("codex_flags") or []),
                    }
                )
                return llm_result

            with (
                mock.patch.object(rf, "run_llm_exec", side_effect=capture_run_llm_exec) as run_mock,
                mock.patch.object(
                    rf,
                    "_validate_or_reuse_synth_artifact",
                    side_effect=[(False, invalid_validation), (True, valid_validation)],
                ) as validate_mock,
                mock.patch.object(
                    rf,
                    "_apply_synth_severity_finalization",
                    return_value=(False, invalid_validation, []),
                ) as finalize_mock,
                mock.patch.object(rf, "prompt_synth_grounding_retry_choice", return_value="retry") as retry_prompt,
                mock.patch.object(rf, "prompt_grounding_retry_effort", return_value="high") as effort_prompt,
                mock.patch.object(rf, "_enforce_chunkhound_tool_proof") as proof_mock,
            ):
                success_resume_command = rf._execute_multipass_synth_stage(
                    progress=progress,
                    repo_dir=root / "repo",
                    work_dir=root / "work",
                    session_id="session-1",
                    review_md_path=review_md,
                    synth_prompt="prompt",
                    synth_llm=synth_llm,
                    synth_runtime_policy={
                        "codex_flags": ['model_reasoning_effort="medium"'],
                        "codex_config_overrides": [],
                        "sandbox_mode": "workspace-write",
                        "approval_policy": "never",
                    },
                    synth_step_outputs=[],
                    grounding_mode="strict",
                    env={},
                    stream=False,
                    add_dirs=[],
                    codex_meta=None,
                    ui_enabled=True,
                    prompt_template_name="mrereview_gh_local_big_resume_synth.md",
                    run_kind="resume_synth",
                    review_stage="multipass_resume_synth",
                    stage_label="multipass resume synth",
                    failure_message="resume synth failed",
                    multipass_cfg={},
                )

            self.assertIsNone(success_resume_command)
            self.assertEqual(run_mock.call_count, 2)
            self.assertEqual(validate_mock.call_count, 2)
            self.assertEqual(finalize_mock.call_count, 1)
            retry_prompt.assert_called_once()
            effort_prompt.assert_called_once()
            proof_mock.assert_called()
            self.assertEqual(synth_llm["resolved"]["reasoning_effort"], "high")
            self.assertIn('model_reasoning_effort="medium"', run_invocations[0]["codex_flags"])
            self.assertIn('model_reasoning_effort="high"', run_invocations[1]["codex_flags"])
            self.assertEqual(
                (run_invocations[1]["resolution_meta"].get("resolved") or {}).get("reasoning_effort_source"),
                "tty_prompt",
            )
            self.assertEqual(
                progress.meta["multipass"]["llm"]["stages"]["synth"]["effective_reasoning_effort"],
                "high",
            )
            self.assertEqual(
                progress.meta["multipass"]["llm"]["review_artifact_llm"]["effective_reasoning_effort"],
                "high",
            )
            run_entry = progress.meta["multipass"]["runs"][0]
            self.assertEqual(run_entry["llm"]["effective_reasoning_effort"], "high")
            self.assertTrue(run_entry["grounding_retried"])
            self.assertEqual(len(run_entry["grounding_attempts"]), 1)
            self.assertEqual(run_entry["first_grounding_failure_validation"]["errors"], ["missing citation"])

    def test_rewrite_review_md_dropping_bullets_keeps_single_existing_none_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_md = Path(tmp) / "review.md"
            review_md.write_text(
                "\n".join(
                    [
                        "## Business / Product Assessment",
                        "**Verdict**: APPROVE",
                        "",
                        "### Strengths",
                        "- None.",
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
                        "- Drop me. Sources: `pkg/module.py:2`",
                        "",
                        "### In Scope Issues",
                        "- Grounded issue. Sources: `pkg/module.py:3`",
                        "",
                        "### Out of Scope Issues",
                        "- None.",
                        "",
                        "### Reusability",
                        "- Reusable note. Sources: `pkg/module.py:1`",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            rf._rewrite_review_md_dropping_bullets(
                review_md_path=review_md,
                dropped=[
                    {
                        "section_key": "Technical Assessment|Strengths|16",
                        "bullet_index": 1,
                        "section_label": "'### Strengths' under '## Technical Assessment' (line 16)",
                        "bullet_text": "- Drop me. Sources: `pkg/module.py:2`",
                        "critical": False,
                        "reason": "bad cite",
                    }
                ],
            )

            rewritten = review_md.read_text(encoding="utf-8")

        self.assertNotIn("### Strengths\n- None.\n- None.\n", rewritten)
        self.assertIn("## Business / Product Assessment\n**Verdict**: APPROVE\n\n### Strengths\n- None.\n", rewritten)

    def test_rewrite_review_md_dropping_bullets_removes_continuation_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_md = Path(tmp) / "review.md"
            review_md.write_text(
                "\n".join(
                    [
                        "## Technical Assessment",
                        "**Verdict**: REQUEST CHANGES",
                        "",
                        "### Strengths",
                        "- Drop me. Sources: `pkg/module.py:2`",
                        "  continuation that should disappear with the dropped bullet",
                        "",
                        "### In Scope Issues",
                        "- None.",
                        "",
                        "### Out of Scope Issues",
                        "- None.",
                        "",
                        "### Reusability",
                        "- None.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            rf._rewrite_review_md_dropping_bullets(
                review_md_path=review_md,
                dropped=[
                    {
                        "section_key": "Technical Assessment|Strengths|4",
                        "bullet_index": 1,
                        "section_label": "'### Strengths' under '## Technical Assessment' (line 4)",
                        "bullet_text": "- Drop me. Sources: `pkg/module.py:2`",
                        "critical": False,
                        "reason": "bad cite",
                    }
                ],
            )

            rewritten = review_md.read_text(encoding="utf-8")

        body, _, footer = rewritten.partition(rf._SYNTH_OMISSION_FOOTER_HEADING)
        self.assertNotIn("continuation that should disappear", body)
        self.assertIn("### Strengths\n- None.\n", body)
        self.assertIn("dropped bullet text: Drop me.", footer)

    def test_step_grounding_validation_error_carries_payload(self) -> None:
        err = rf.StepGroundingValidationError(
            "bad grounding",
            step_validation={"valid": False, "errors": ["missing citation"]},
        )

        self.assertEqual(str(err), "bad grounding")
        self.assertEqual(err.step_validation, {"valid": False, "errors": ["missing citation"]})

    def test_execute_multipass_step_stage_retries_grounding_once_in_non_tty_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta_path = root / "meta.json"
            progress = rf.SessionProgress(meta_path, quiet=True)
            entry = rf.MultipassStepEntry(
                index=1,
                step_id="01",
                step_title="API review",
                step_focus="grounding",
                output_path=root / "review.step-01.md",
                prompt="step prompt",
                should_run=True,
            )
            progress.init({"session_id": "session-1", "multipass": {"step_workers": 1, "runs": []}})
            rf._ensure_multipass_run_entry(
                progress.meta,
                kind="step",
                step_index=1,
                step_id=entry.step_id,
                step_title=entry.step_title,
                output_path=entry.output_path,
                template_id="builtin:step",
                prompt=entry.prompt,
                stage_llm_meta={"provider": "openai"},
            )
            raw_result = rf.MultipassStepRunResult(
                entry=entry,
                llm_result=rf.LlmRunResult(resume=None),
                duration_seconds=1.25,
            )

            with (
                mock.patch.object(rf, "_run_multipass_step_llm", side_effect=[raw_result, raw_result]) as run_mock,
                mock.patch.object(
                    rf,
                    "_finalize_multipass_step_result",
                    side_effect=[
                        rf.StepGroundingValidationError(
                            "bad grounding",
                            step_validation={"valid": False, "errors": ["missing citation"]},
                        ),
                        None,
                    ],
                ) as finalize_mock,
            ):
                resume_command, skipped = rf._execute_multipass_step_stage(
                    progress=progress,
                    work_dir=root / "work",
                    repo_dir=root / "repo",
                    session_id="session-1",
                    grounding_mode="strict",
                    step_entries=[entry],
                    step_worker_count=1,
                    llm_resolved={"provider": "openai"},
                    llm_resolution_meta={},
                    env={},
                    stream=False,
                    add_dirs=[],
                    runtime_policy={},
                    templates={"step": "mrereview_gh_local_big_step.md"},
                    codex_meta=None,
                    quiet=True,
                    ui_enabled=False,
                )

            self.assertIsNone(resume_command)
            self.assertEqual(skipped, [])
            self.assertEqual(run_mock.call_count, 2)
            self.assertEqual(finalize_mock.call_count, 2)
            state = progress.meta["multipass"]["step_states"][0]
            run_entry = progress.meta["multipass"]["runs"][0]
            self.assertEqual(state["status"], "completed")
            self.assertTrue(state["grounding_retried"])
            self.assertEqual(len(state["grounding_attempts"]), 1)
            self.assertTrue(run_entry["grounding_retried"])
            self.assertEqual(run_entry["first_grounding_failure_validation"]["errors"], ["missing citation"])

    def test_execute_multipass_step_stage_retries_with_codex_effort_override_in_tty_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta_path = root / "meta.json"
            progress = rf.SessionProgress(meta_path, quiet=True)
            entry = rf.MultipassStepEntry(
                index=1,
                step_id="01",
                step_title="API review",
                step_focus="grounding",
                output_path=root / "review.step-01.md",
                prompt="step prompt",
                should_run=True,
            )
            progress.init({"session_id": "session-1", "multipass": {"step_workers": 1, "runs": []}, "llm": {}, "codex": {}})
            rf._ensure_multipass_run_entry(
                progress.meta,
                kind="step",
                step_index=1,
                step_id=entry.step_id,
                step_title=entry.step_title,
                output_path=entry.output_path,
                template_id="builtin:step",
                prompt=entry.prompt,
                stage_llm_meta={"provider": "codex", "effective_reasoning_effort": "medium"},
            )
            raw_result = rf.MultipassStepRunResult(
                entry=entry,
                llm_result=rf.LlmRunResult(resume=None),
                duration_seconds=1.25,
            )
            run_invocations: list[dict[str, Any]] = []
            retry_state_snapshots: list[dict[str, Any]] = []

            def capture_step_run(**kwargs: Any) -> rf.MultipassStepRunResult:
                runtime_policy = kwargs["runtime_policy"] if isinstance(kwargs.get("runtime_policy"), dict) else {}
                resolution_meta = kwargs["llm_resolution_meta"] if isinstance(kwargs.get("llm_resolution_meta"), dict) else {}
                run_invocations.append(
                    {
                        "resolved": dict(kwargs["llm_resolved"]) if isinstance(kwargs.get("llm_resolved"), dict) else {},
                        "resolution_meta": dict(resolution_meta),
                        "codex_flags": list(runtime_policy.get("codex_flags") or []),
                    }
                )
                if len(run_invocations) == 2:
                    retry_state_snapshots.append(
                        {
                            "state": dict(progress.meta["multipass"]["step_states"][0]),
                            "run_entry": dict(progress.meta["multipass"]["runs"][0]),
                        }
                    )
                return raw_result

            with (
                mock.patch.object(rf, "_run_multipass_step_llm", side_effect=capture_step_run) as run_mock,
                mock.patch.object(
                    rf,
                    "_finalize_multipass_step_result",
                    side_effect=[
                        rf.StepGroundingValidationError(
                            "bad grounding",
                            step_validation={"valid": False, "errors": ["missing citation"]},
                        ),
                        None,
                    ],
                ) as finalize_mock,
                mock.patch.object(rf, "prompt_grounding_retry_skip", return_value="retry") as retry_prompt,
                mock.patch.object(rf, "prompt_grounding_retry_effort", return_value="high") as effort_prompt,
            ):
                resume_command, skipped = rf._execute_multipass_step_stage(
                    progress=progress,
                    work_dir=root / "work",
                    repo_dir=root / "repo",
                    session_id="session-1",
                    grounding_mode="strict",
                    step_entries=[entry],
                    step_worker_count=1,
                    llm_resolved={"provider": "codex", "model": "gpt-5.4", "reasoning_effort": "medium"},
                    llm_resolution_meta={
                        "resolved": {
                            "model": "gpt-5.4",
                            "reasoning_effort": "medium",
                            "reasoning_effort_source": "cli",
                            "reasoning_effort_source_detail": "cli",
                        }
                    },
                    env={},
                    stream=False,
                    add_dirs=[],
                    runtime_policy={
                        "codex_flags": ['model_reasoning_effort="medium"'],
                        "codex_config_overrides": [],
                        "sandbox_mode": "workspace-write",
                        "approval_policy": "never",
                    },
                    templates={"step": "mrereview_gh_local_big_step.md"},
                    codex_meta=None,
                    quiet=True,
                    ui_enabled=True,
                    multipass_cfg={},
                )

            self.assertIsNone(resume_command)
            self.assertEqual(skipped, [])
            self.assertEqual(run_mock.call_count, 2)
            self.assertEqual(finalize_mock.call_count, 2)
            retry_prompt.assert_called_once()
            effort_prompt.assert_called_once()
            self.assertIn('model_reasoning_effort="medium"', run_invocations[0]["codex_flags"])
            self.assertIn('model_reasoning_effort="high"', run_invocations[1]["codex_flags"])
            self.assertEqual(
                (run_invocations[1]["resolution_meta"].get("resolved") or {}).get("reasoning_effort_source"),
                "tty_prompt",
            )
            state = progress.meta["multipass"]["step_states"][0]
            run_entry = progress.meta["multipass"]["runs"][0]
            self.assertEqual(state["status"], "completed")
            self.assertTrue(state["grounding_retried"])
            self.assertEqual(
                progress.meta["multipass"]["llm"]["stages"]["step"]["effective_reasoning_effort"],
                "high",
            )
            self.assertEqual(run_entry["llm"]["effective_reasoning_effort"], "high")
            self.assertEqual(len(retry_state_snapshots), 1)
            self.assertEqual(retry_state_snapshots[0]["state"]["status"], "retrying_grounding")
            self.assertTrue(retry_state_snapshots[0]["run_entry"]["grounding_retried"])
            self.assertEqual(len(retry_state_snapshots[0]["run_entry"]["grounding_attempts"]), 1)
            self.assertEqual(
                retry_state_snapshots[0]["run_entry"]["first_grounding_failure_validation"]["errors"],
                ["missing citation"],
            )

    def test_execute_multipass_step_stage_ui_retry_loop_enforces_ui_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta_path = root / "meta.json"
            progress = rf.SessionProgress(meta_path, quiet=True)
            entry = rf.MultipassStepEntry(
                index=1,
                step_id="01",
                step_title="API review",
                step_focus="grounding",
                output_path=root / "review.step-01.md",
                prompt="step prompt",
                should_run=True,
            )
            progress.init({"session_id": "session-cap", "multipass": {"step_workers": 1, "runs": []}})
            rf._ensure_multipass_run_entry(
                progress.meta,
                kind="step",
                step_index=1,
                step_id=entry.step_id,
                step_title=entry.step_title,
                output_path=entry.output_path,
                template_id="builtin:step",
                prompt=entry.prompt,
                stage_llm_meta={"provider": "openai"},
            )
            raw_result = rf.MultipassStepRunResult(
                entry=entry,
                llm_result=rf.LlmRunResult(resume=None),
                duration_seconds=1.25,
            )
            cap = rf._MULTIPASS_STEP_GROUNDING_UI_MAX_RETRIES

            with (
                mock.patch.object(
                    rf,
                    "_run_multipass_step_llm",
                    return_value=raw_result,
                ) as run_mock,
                mock.patch.object(
                    rf,
                    "_finalize_multipass_step_result",
                    side_effect=rf.StepGroundingValidationError(
                        "bad grounding",
                        step_validation={"valid": False, "errors": ["missing citation"]},
                    ),
                ),
                mock.patch.object(rf, "prompt_grounding_retry_skip", return_value="retry") as retry_prompt,
                mock.patch.object(rf, "prompt_grounding_retry_effort", return_value=None) as effort_prompt,
            ):
                resume_command, skipped = rf._execute_multipass_step_stage(
                    progress=progress,
                    work_dir=root / "work",
                    repo_dir=root / "repo",
                    session_id="session-cap",
                    grounding_mode="strict",
                    step_entries=[entry],
                    step_worker_count=1,
                    llm_resolved={"provider": "openai"},
                    llm_resolution_meta={},
                    env={},
                    stream=False,
                    add_dirs=[],
                    runtime_policy={},
                    templates={"step": "mrereview_gh_local_big_step.md"},
                    codex_meta=None,
                    quiet=True,
                    ui_enabled=True,
                    multipass_cfg={},
                )

            self.assertIsNone(resume_command)
            self.assertEqual(run_mock.call_count, cap + 1)
            self.assertEqual(retry_prompt.call_count, cap)
            self.assertEqual(effort_prompt.call_count, cap)
            self.assertEqual(
                skipped,
                [{"step_index": 1, "step_id": "01", "step_title": "API review", "reason": "missing citation"}],
            )
            state = progress.meta["multipass"]["step_states"][0]
            run_entry = progress.meta["multipass"]["runs"][0]
            self.assertEqual(state["status"], "grounding_skipped")
            self.assertTrue(run_entry["grounding_retried"])
            self.assertEqual(len(run_entry["grounding_attempts"]), cap + 1)

    def test_execute_multipass_step_stage_tty_loss_skips_instead_of_retrying(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta_path = root / "meta.json"
            progress = rf.SessionProgress(meta_path, quiet=True)
            entry = rf.MultipassStepEntry(
                index=1,
                step_id="01",
                step_title="API review",
                step_focus="grounding",
                output_path=root / "review.step-01.md",
                prompt="step prompt",
                should_run=True,
            )
            progress.init({"session_id": "session-tty-loss", "multipass": {"step_workers": 1, "runs": []}})
            rf._ensure_multipass_run_entry(
                progress.meta,
                kind="step",
                step_index=1,
                step_id=entry.step_id,
                step_title=entry.step_title,
                output_path=entry.output_path,
                template_id="builtin:step",
                prompt=entry.prompt,
                stage_llm_meta={"provider": "openai"},
            )
            raw_result = rf.MultipassStepRunResult(
                entry=entry,
                llm_result=rf.LlmRunResult(resume=None),
                duration_seconds=1.25,
            )

            with (
                mock.patch.object(rf, "_run_multipass_step_llm", return_value=raw_result) as run_mock,
                mock.patch.object(
                    rf,
                    "_finalize_multipass_step_result",
                    side_effect=rf.StepGroundingValidationError(
                        "bad grounding",
                        step_validation={"valid": False, "errors": ["missing citation"]},
                    ),
                ),
                mock.patch.object(rf, "prompt_grounding_retry_skip", return_value=None) as retry_prompt,
                mock.patch.object(rf, "prompt_grounding_retry_effort") as effort_prompt,
            ):
                resume_command, skipped = rf._execute_multipass_step_stage(
                    progress=progress,
                    work_dir=root / "work",
                    repo_dir=root / "repo",
                    session_id="session-tty-loss",
                    grounding_mode="strict",
                    step_entries=[entry],
                    step_worker_count=1,
                    llm_resolved={"provider": "openai"},
                    llm_resolution_meta={},
                    env={},
                    stream=False,
                    add_dirs=[],
                    runtime_policy={},
                    templates={"step": "mrereview_gh_local_big_step.md"},
                    codex_meta=None,
                    quiet=True,
                    ui_enabled=True,
                    multipass_cfg={},
                )

            self.assertIsNone(resume_command)
            self.assertEqual(run_mock.call_count, 1)
            retry_prompt.assert_called_once()
            effort_prompt.assert_not_called()
            self.assertEqual(
                skipped,
                [{"step_index": 1, "step_id": "01", "step_title": "API review", "reason": "missing citation"}],
            )
            state = progress.meta["multipass"]["step_states"][0]
            self.assertEqual(state["status"], "grounding_skipped")

    def test_execute_multipass_step_stage_skips_after_retry_exhaustion_in_non_tty_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta_path = root / "meta.json"
            progress = rf.SessionProgress(meta_path, quiet=True)
            entry = rf.MultipassStepEntry(
                index=1,
                step_id="01",
                step_title="API review",
                step_focus="grounding",
                output_path=root / "review.step-01.md",
                prompt="step prompt",
                should_run=True,
            )
            progress.init({"session_id": "session-1", "multipass": {"step_workers": 1, "runs": []}})
            rf._ensure_multipass_run_entry(
                progress.meta,
                kind="step",
                step_index=1,
                step_id=entry.step_id,
                step_title=entry.step_title,
                output_path=entry.output_path,
                template_id="builtin:step",
                prompt=entry.prompt,
                stage_llm_meta={"provider": "openai"},
            )
            raw_result = rf.MultipassStepRunResult(
                entry=entry,
                llm_result=rf.LlmRunResult(resume=None),
                duration_seconds=1.25,
            )
            first = rf.StepGroundingValidationError(
                "bad grounding",
                step_validation={"valid": False, "errors": ["missing citation"]},
            )
            second = rf.StepGroundingValidationError(
                "bad grounding again",
                step_validation={"valid": False, "errors": ["wrong line ref"]},
            )

            with (
                mock.patch.object(rf, "_run_multipass_step_llm", side_effect=[raw_result, raw_result]) as run_mock,
                mock.patch.object(rf, "_finalize_multipass_step_result", side_effect=[first, second]),
            ):
                resume_command, skipped = rf._execute_multipass_step_stage(
                    progress=progress,
                    work_dir=root / "work",
                    repo_dir=root / "repo",
                    session_id="session-1",
                    grounding_mode="strict",
                    step_entries=[entry],
                    step_worker_count=1,
                    llm_resolved={"provider": "openai"},
                    llm_resolution_meta={},
                    env={},
                    stream=False,
                    add_dirs=[],
                    runtime_policy={},
                    templates={"step": "mrereview_gh_local_big_step.md"},
                    codex_meta=None,
                    quiet=True,
                    ui_enabled=False,
                )

            self.assertIsNone(resume_command)
            self.assertEqual(run_mock.call_count, 2)
            self.assertEqual(
                skipped,
                [{"step_index": 1, "step_id": "01", "step_title": "API review", "reason": "missing citation"}],
            )
            state = progress.meta["multipass"]["step_states"][0]
            run_entry = progress.meta["multipass"]["runs"][0]
            self.assertEqual(progress.meta["multipass"]["status"], "steps_ready")
            self.assertEqual(state["status"], "grounding_skipped")
            self.assertEqual(state["grounding_reason"], "missing citation")
            self.assertTrue(run_entry["grounding_skipped"])
            self.assertEqual(len(run_entry["grounding_attempts"]), 2)

    def test_execute_multipass_step_stage_uses_prompt_when_ui_auto_resolves_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta_path = root / "meta.json"
            progress = rf.SessionProgress(meta_path, quiet=True)
            entry = rf.MultipassStepEntry(
                index=1,
                step_id="01",
                step_title="API review",
                step_focus="grounding",
                output_path=root / "review.step-01.md",
                prompt="step prompt",
                should_run=True,
            )
            progress.init({"session_id": "session-1", "multipass": {"step_workers": 1, "runs": []}})
            rf._ensure_multipass_run_entry(
                progress.meta,
                kind="step",
                step_index=1,
                step_id=entry.step_id,
                step_title=entry.step_title,
                output_path=entry.output_path,
                template_id="builtin:step",
                prompt=entry.prompt,
                stage_llm_meta={"provider": "openai"},
            )
            raw_result = rf.MultipassStepRunResult(
                entry=entry,
                llm_result=rf.LlmRunResult(resume=None),
                duration_seconds=1.25,
            )

            with (
                mock.patch.object(sys, "stderr") as stderr_mock,
                mock.patch.dict(os.environ, {"TERM": "xterm-256color"}, clear=False),
                mock.patch.object(stderr_mock, "isatty", return_value=True),
                mock.patch.object(rf, "_run_multipass_step_llm", return_value=raw_result) as run_mock,
                mock.patch.object(
                    rf,
                    "_finalize_multipass_step_result",
                    side_effect=rf.StepGroundingValidationError(
                        "bad grounding",
                        step_validation={"valid": False, "errors": ["missing citation"]},
                    ),
                ),
                mock.patch.object(rf, "prompt_grounding_retry_skip", return_value="skip") as prompt_mock,
            ):
                ui_enabled = rf.resolve_ui_enabled(
                    argparse.Namespace(ui="auto", quiet=False),
                    verbosity=rf.Verbosity.normal,
                )
                _, skipped = rf._execute_multipass_step_stage(
                    progress=progress,
                    work_dir=root / "work",
                    repo_dir=root / "repo",
                    session_id="session-1",
                    grounding_mode="strict",
                    step_entries=[entry],
                    step_worker_count=1,
                    llm_resolved={"provider": "openai"},
                    llm_resolution_meta={},
                    env={},
                    stream=False,
                    add_dirs=[],
                    runtime_policy={},
                    templates={"step": "mrereview_gh_local_big_step.md"},
                    codex_meta=None,
                    quiet=True,
                    ui_enabled=ui_enabled,
                )

            self.assertTrue(ui_enabled)
            prompt_mock.assert_called_once()
            self.assertEqual(run_mock.call_count, 1)
            self.assertEqual(skipped[0]["reason"], "missing citation")

    def test_grounding_prompt_helper_repompts_until_valid_choice(self) -> None:
        class _KeepOpenStringIO(StringIO):
            def close(self) -> None:
                pass

        reader = StringIO("nope\nretry\n")
        writer = _KeepOpenStringIO()
        with mock.patch.object(cure_output, "_open_prompt_tty", return_value=(reader, writer)):
            choice = cure_output.prompt_grounding_retry_skip(
                step_id="01",
                step_title="API review",
                attempt_count=2,
                validation={"errors": ["missing citation", "bad line reference"]},
            )

        rendered = writer.getvalue()
        self.assertEqual(choice, "retry")
        self.assertIn(
            "Step output generated successfully; strict grounding rejected the format.",
            rendered,
        )
        self.assertIn("Invalid choice. Enter one of: retry, skip.", rendered)

    def test_pr_picker_rejects_invalid_numbered_model_selection(self) -> None:
        class _KeepOpenStringIO(StringIO):
            def close(self) -> None:
                pass

        reader = StringIO("99\n")
        writer = _KeepOpenStringIO()
        with mock.patch.object(cure_output, "_open_prompt_tty", return_value=(reader, writer)):
            with self.assertRaises(rf.ReviewflowError) as ctx:
                cure_output.prompt_pr_model_and_effort_picker(
                    provider="claude",
                    default_model="claude-sonnet-4-6",
                    default_effort="high",
                    model_options=[("Sonnet 4.6", "claude-sonnet-4-6")],
                    effort_options=["low", "medium", "high", "max"],
                    prompt_for_model=True,
                    prompt_for_effort=False,
                )
        self.assertIn("invalid model selection", str(ctx.exception).lower())

    def test_pr_picker_aborts_on_eof_during_effort_selection(self) -> None:
        class _KeepOpenStringIO(StringIO):
            def close(self) -> None:
                pass

        reader = StringIO("")
        writer = _KeepOpenStringIO()
        with mock.patch.object(cure_output, "_open_prompt_tty", return_value=(reader, writer)):
            with self.assertRaises(rf.ReviewflowError) as ctx:
                cure_output.prompt_pr_model_and_effort_picker(
                    provider="claude",
                    default_model="claude-sonnet-4-6",
                    default_effort="high",
                    model_options=[("Sonnet 4.6", "claude-sonnet-4-6")],
                    effort_options=["low", "medium", "high", "max"],
                    prompt_for_model=False,
                    prompt_for_effort=True,
                )
        self.assertIn("closed before effort selection", str(ctx.exception))

    def test_pr_picker_accepts_codex_freeform_model_and_effort(self) -> None:
        class _KeepOpenStringIO(StringIO):
            def close(self) -> None:
                pass

        reader = StringIO("gpt-5.4\n4\n")
        writer = _KeepOpenStringIO()
        with mock.patch.object(cure_output, "_open_prompt_tty", return_value=(reader, writer)):
            result = cure_output.prompt_pr_model_and_effort_picker(
                provider="codex",
                default_model="gpt-5.3-codex",
                default_effort="high",
                model_options=[],
                effort_options=["minimal", "low", "medium", "high", "xhigh"],
                prompt_for_model=True,
                prompt_for_effort=True,
            )
        self.assertEqual(result, {"model": "gpt-5.4", "reasoning_effort": "high"})

    def test_pr_picker_accepts_named_effort_selection(self) -> None:
        class _KeepOpenStringIO(StringIO):
            def close(self) -> None:
                pass

        reader = StringIO("max\n")
        writer = _KeepOpenStringIO()
        with mock.patch.object(cure_output, "_open_prompt_tty", return_value=(reader, writer)):
            result = cure_output.prompt_pr_model_and_effort_picker(
                provider="claude",
                default_model="claude-sonnet-4-6",
                default_effort="high",
                model_options=[("Sonnet 4.6", "claude-sonnet-4-6")],
                effort_options=["low", "medium", "high", "max"],
                prompt_for_model=False,
                prompt_for_effort=True,
            )

        self.assertEqual(result, {"reasoning_effort": "max"})
        self.assertIn("Select effort number or name:", writer.getvalue())

    def test_grounding_retry_effort_returns_none_when_effort_is_kept(self) -> None:
        class _KeepOpenStringIO(StringIO):
            def close(self) -> None:
                pass

        reader = StringIO("\n")
        writer = _KeepOpenStringIO()
        with mock.patch.object(cure_output, "_open_prompt_tty", return_value=(reader, writer)):
            result = cure_output.prompt_grounding_retry_effort(
                provider="claude",
                default_effort="high",
                effort_options=["low", "medium", "high", "max"],
                stage_label="multipass step 08",
            )

        self.assertIsNone(result)

    def test_synth_grounding_retry_prompt_finalize_text_mentions_issue_bullet_omission(self) -> None:
        class _KeepOpenStringIO(StringIO):
            def close(self) -> None:
                pass

        reader = StringIO("finalize\n")
        writer = _KeepOpenStringIO()
        with mock.patch.object(cure_output, "_open_prompt_tty", return_value=(reader, writer)):
            result = cure_output.prompt_synth_grounding_retry_choice(
                attempt_count=2,
                validation={"errors": ["missing citation", "bad line reference"]},
            )

        rendered = writer.getvalue()
        self.assertEqual(result, "finalize")
        self.assertIn("drop invalid bullets", rendered)
        self.assertIn("issue bullets if the section keeps another grounded bullet", rendered)

    def test_provider_model_options_include_codex_models(self) -> None:
        values = [value for _, value in rf._provider_model_options("codex")]
        self.assertIn("gpt-5.4", values)

    def test_pr_picker_skips_explicit_preset_overrides(self) -> None:
        llm_resolved = {
            "provider": "claude",
            "model": "claude-opus-4-6",
            "reasoning_effort": "high",
        }
        llm_resolution_meta = {
            "resolved": {
                "model_source": "preset",
                "model_source_detail": "preset_explicit",
                "reasoning_effort_source": "preset",
                "reasoning_effort_source_detail": "preset_explicit",
            }
        }

        with mock.patch.object(rf, "prompt_pr_model_and_effort_picker", side_effect=AssertionError("picker should not run")):
            resolved, meta = rf._maybe_apply_pr_llm_picker(
                llm_resolved=llm_resolved,
                llm_resolution_meta=llm_resolution_meta,
            )

        self.assertEqual(resolved, llm_resolved)
        self.assertEqual(meta, llm_resolution_meta)

    def test_pr_picker_still_prompts_for_builtin_preset_defaults(self) -> None:
        llm_resolved = {
            "provider": "claude",
            "model": "claude-sonnet-4-6",
            "reasoning_effort": "high",
        }
        llm_resolution_meta = {
            "resolved": {
                "model_source": "preset",
                "model_source_detail": "preset_builtin",
                "reasoning_effort_source": "preset",
                "reasoning_effort_source_detail": "preset_builtin",
            }
        }

        with mock.patch.object(
            rf,
            "prompt_pr_model_and_effort_picker",
            return_value={"model": "claude-opus-4-6"},
        ) as picker:
            resolved, meta = rf._maybe_apply_pr_llm_picker(
                llm_resolved=llm_resolved,
                llm_resolution_meta=llm_resolution_meta,
            )

        picker.assert_called_once()
        self.assertEqual(resolved["model"], "claude-opus-4-6")
        self.assertEqual(meta["resolved"]["model_source"], "tty_prompt")

    def test_persist_grounding_summary_keeps_full_catalog_and_filtered_synth_outputs(self) -> None:
        root = Path("/tmp/session-grounding-summary")
        entries = [
            rf.MultipassStepEntry(
                index=1,
                step_id="01",
                step_title="Skipped",
                step_focus="focus",
                output_path=root / "review.step-01.md",
                prompt="a",
                should_run=False,
            ),
            rf.MultipassStepEntry(
                index=2,
                step_id="02",
                step_title="Kept",
                step_focus="focus",
                output_path=root / "review.step-02.md",
                prompt="b",
                should_run=False,
            ),
        ]
        meta = {
            "multipass": {
                "step_states": [
                    {"step_id": "01", "step_title": "Skipped", "status": "grounding_skipped", "grounding_reason": "bad cite"},
                    {"step_id": "02", "step_title": "Kept", "status": "completed"},
                ]
            }
        }

        synth_outputs = rf._persist_grounding_summary(meta=meta, step_entries=entries)

        self.assertEqual(synth_outputs, [str(root / "review.step-02.md")])
        self.assertEqual(
            meta["multipass"]["artifacts"]["step_outputs"],
            [str(root / "review.step-01.md"), str(root / "review.step-02.md")],
        )
        self.assertEqual(meta["multipass"]["artifacts"]["synth_step_outputs"], [str(root / "review.step-02.md")])
        self.assertTrue(meta["multipass"]["grounding_partial_synthesis"])
        self.assertEqual(meta["multipass"]["grounding_skipped_steps"][0]["reason"], "bad cite")

    def test_resume_grounding_skip_choice_is_prompted_only_when_ui_enabled(self) -> None:
        entry = rf.MultipassStepEntry(
            index=1,
            step_id="01",
            step_title="Skipped",
            step_focus="focus",
            output_path=Path("/tmp/review.step-01.md"),
            prompt="a",
            should_run=False,
        )
        meta = {
            "multipass": {
                "grounding_skipped_steps": [
                    {"step_id": "01", "step_title": "Skipped", "reason": "bad cite"}
                ]
            }
        }

        self.assertEqual(
            rf._resolve_resume_grounding_skip_choice(meta=meta, step_entries=[entry], ui_enabled=False),
            "rerun",
        )
        with mock.patch.object(rf, "prompt_resume_grounding_skipped_steps", return_value="keep"):
            self.assertEqual(
                rf._resolve_resume_grounding_skip_choice(meta=meta, step_entries=[entry], ui_enabled=True),
                "keep",
            )

    def test_resume_grounding_skip_choice_uses_prompt_when_ui_auto_resolves_enabled(self) -> None:
        entry = rf.MultipassStepEntry(
            index=1,
            step_id="01",
            step_title="Skipped",
            step_focus="focus",
            output_path=Path("/tmp/review.step-01.md"),
            prompt="a",
            should_run=False,
        )
        meta = {
            "multipass": {
                "grounding_skipped_steps": [
                    {"step_id": "01", "step_title": "Skipped", "reason": "bad cite"}
                ]
            }
        }

        with (
            mock.patch.object(sys, "stderr") as stderr_mock,
            mock.patch.dict(os.environ, {"TERM": "xterm-256color"}, clear=False),
            mock.patch.object(stderr_mock, "isatty", return_value=True),
            mock.patch.object(rf, "prompt_resume_grounding_skipped_steps", return_value="keep") as prompt_mock,
        ):
            ui_enabled = rf.resolve_ui_enabled(
                argparse.Namespace(ui="auto", quiet=False),
                verbosity=rf.Verbosity.normal,
            )
            choice = rf._resolve_resume_grounding_skip_choice(
                meta=meta,
                step_entries=[entry],
                ui_enabled=ui_enabled,
            )

        self.assertTrue(ui_enabled)
        prompt_mock.assert_called_once()
        self.assertEqual(choice, "keep")

    def test_resume_flow_from_synth_keeps_grounding_skipped_steps_in_non_tty_mode(self) -> None:
        root = ROOT / ".tmp_test_resume_from_synth_keeps_skipped_steps"
        cfg = root / "reviewflow.toml"
        valid_step_markdown = "\n".join(
            [
                "### Step Result: 02 — Tests review",
                "**Focus**: tests",
                "",
                "### Steps taken",
                "- checked repo",
                "",
                "### Findings",
                "- Grounded finding. Sources: `src/app.py:2`",
                "",
            ]
        )
        valid_synth_markdown = self._valid_synth_markdown(primary_citation="src/app.py:2")
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
            (session_dir / "review.step-02.md").write_text(valid_step_markdown, encoding="utf-8")
            review_md = session_dir / "review.md"
            meta = {
                "session_id": "session-1",
                "status": "error",
                "failed_at": "2026-03-10T01:00:00+00:00",
                "created_at": "2026-03-10T00:00:00+00:00",
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
                    "step_states": [
                        {
                            "step_index": 1,
                            "step_id": "01",
                            "step_title": "API review",
                            "status": "completed",
                        },
                        {
                            "step_index": 2,
                            "step_id": "02",
                            "step_title": "Tests review",
                            "status": "completed",
                        },
                    ],
                    "grounding_skipped_steps": [
                        {"step_id": "01", "step_title": "API review", "reason": "bad cite"}
                    ],
                    "validation": {"mode": "strict", "invalid_artifacts": [], "has_invalid_artifacts": False},
                },
            }
            (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

            calls: list[str] = []

            def fake_run_llm_exec(**kwargs: object) -> rf.LlmRunResult:
                output_path = Path(str(kwargs["output_path"]))
                calls.append(output_path.name)
                if output_path.name != "review.md":
                    raise AssertionError(f"unexpected rerun during synth-only resume: {output_path.name}")
                output_path.write_text(valid_synth_markdown, encoding="utf-8")
                return rf.LlmRunResult(resume=None, adapter_meta={"usage": {"input_tokens": 1, "output_tokens": 1}})

            args = argparse.Namespace(
                session_id="session-1",
                from_phase="synth",
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
                stack.enter_context(mock.patch.object(rf, "_run_chunkhound_access_preflight"))
                stack.enter_context(mock.patch.object(rf, "_run_review_intelligence_preflight"))
                stack.enter_context(mock.patch.object(rf, "_enforce_chunkhound_tool_proof", return_value={}))
                stack.enter_context(mock.patch.object(rf, "run_llm_exec", side_effect=fake_run_llm_exec))
                rc = rf.resume_flow(args, paths=paths, config_path=cfg, codex_base_config_path=cfg)

            refreshed = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(rc, 0)
            self.assertEqual(calls, ["review.md"])
            self.assertEqual(
                refreshed["multipass"]["artifacts"]["synth_step_outputs"],
                [str(session_dir / "review.step-02.md")],
            )
            self.assertNotIn(
                "grounding_skipped_override",
                refreshed["multipass"].get("resume", {}),
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_prepare_synth_inputs_returns_outputs_and_skipped_text_when_valid_steps_remain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_dir = root / "session"
            session_dir.mkdir()
            work_dir = root / "work"
            work_dir.mkdir()
            review_md_path = session_dir / "review.md"
            (root / "review.step-02.md").write_text("grounded step output\n", encoding="utf-8")
            entries = [
                rf.MultipassStepEntry(
                    index=1,
                    step_id="01",
                    step_title="Safety",
                    step_focus="f",
                    output_path=root / "review.step-01.md",
                    prompt="p",
                    should_run=True,
                ),
                rf.MultipassStepEntry(
                    index=2,
                    step_id="02",
                    step_title="Perf",
                    step_focus="f",
                    output_path=root / "review.step-02.md",
                    prompt="p",
                    should_run=True,
                ),
            ]
            meta: dict[str, Any] = {
                "session_id": "test-session",
                "multipass": {
                    "grounding_skipped_steps": [
                        {"step_id": "01", "step_title": "Safety", "reason": "no cite"}
                    ],
                },
            }

            synth_outputs, skipped_text = rf._prepare_synth_inputs(
                meta=meta,
                step_entries=entries,
                session_id="test-session",
                session_dir=session_dir,
                work_dir=work_dir,
                review_md_path=review_md_path,
            )

            self.assertEqual(synth_outputs, [str(root / "review.step-02.md")])
            self.assertIn("01", skipped_text)
            self.assertIn("Safety", skipped_text)
            self.assertIn("no cite", skipped_text)

    def test_prepare_synth_inputs_raises_and_emits_playbook_when_all_steps_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_dir = root / "session"
            session_dir.mkdir()
            work_dir = root / "work"
            work_dir.mkdir()
            review_md_path = session_dir / "review.md"
            entry = rf.MultipassStepEntry(
                index=1,
                step_id="01",
                step_title="Safety",
                step_focus="f",
                output_path=root / "review.step-01.md",
                prompt="p",
                should_run=True,
            )
            meta: dict[str, Any] = {
                "session_id": "test-session",
                "multipass": {
                    "grounding_skipped_steps": [
                        {"step_id": "01", "step_title": "Safety", "reason": "no cite"}
                    ],
                },
            }
            emitted_playbook: list[str] = []

            def capture_playbook(**kwargs: Any) -> None:
                emitted_playbook.append(str(kwargs.get("validation") or ""))

            with (
                mock.patch.object(rf, "_emit_multipass_grounding_failure_playbook", side_effect=capture_playbook),
                self.assertRaises(rf.ReviewflowError),
            ):
                rf._prepare_synth_inputs(
                    meta=meta,
                    step_entries=[entry],
                    session_id="test-session",
                    session_dir=session_dir,
                    work_dir=work_dir,
                    review_md_path=review_md_path,
                )

            self.assertTrue(emitted_playbook, "Expected grounding failure playbook to be emitted")
            self.assertEqual(meta["status"], "error")
            self.assertEqual(meta["multipass"]["status"], "step_failed")

    def test_prepare_synth_inputs_raises_when_non_skipped_step_output_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_dir = root / "session"
            session_dir.mkdir()
            work_dir = root / "work"
            work_dir.mkdir()
            review_md_path = session_dir / "review.md"
            missing_output = root / "review.step-01.md"
            entry = rf.MultipassStepEntry(
                index=1,
                step_id="01",
                step_title="Safety",
                step_focus="f",
                output_path=missing_output,
                prompt="p",
                should_run=False,
            )
            meta: dict[str, Any] = {"session_id": "test-session", "multipass": {}}
            emitted_playbook: list[dict[str, Any]] = []

            def capture_playbook(**kwargs: Any) -> None:
                emitted_playbook.append(dict(kwargs))

            with (
                mock.patch.object(rf, "_emit_multipass_grounding_failure_playbook", side_effect=capture_playbook),
                self.assertRaisesRegex(
                    rf.ReviewflowError,
                    "Missing synth input artifacts prevent review synthesis from continuing",
                ),
            ):
                rf._prepare_synth_inputs(
                    meta=meta,
                    step_entries=[entry],
                    session_id="test-session",
                    session_dir=session_dir,
                    work_dir=work_dir,
                    review_md_path=review_md_path,
                )

            self.assertTrue(emitted_playbook, "Expected grounding failure playbook to be emitted")
            self.assertEqual(meta["status"], "error")
            self.assertEqual(meta["multipass"]["status"], "step_failed")
            validation = emitted_playbook[0]["validation"]
            self.assertIn("Missing synth input artifacts", "\n".join(validation["errors"]))
            self.assertEqual(meta["multipass"]["artifacts"]["synth_step_outputs"], [str(missing_output)])

    def test_persist_grounding_summary_prefers_current_step_state_over_stale_persisted_skip(self) -> None:
        entry = rf.MultipassStepEntry(
            index=1,
            step_id="01",
            step_title="Recovered",
            step_focus="focus",
            output_path=Path("/tmp/review.step-01.md"),
            prompt="a",
            should_run=False,
        )
        meta = {
            "multipass": {
                "step_states": [
                    {"step_id": "01", "step_title": "Recovered", "status": "completed"},
                ],
                "grounding_skipped_steps": [
                    {"step_id": "01", "step_title": "Recovered", "reason": "old failure"},
                ],
            }
        }

        synth_outputs = rf._persist_grounding_summary(meta=meta, step_entries=[entry])

        self.assertEqual(synth_outputs, ["/tmp/review.step-01.md"])
        self.assertEqual(meta["multipass"]["grounding_skipped_steps"], [])

    def test_strip_existing_synth_omission_footer_handles_offset_zero_heading(self) -> None:
        heading = rf._SYNTH_OMISSION_FOOTER_HEADING
        text = f"{heading}\n\nstub\n"

        stripped = rf._strip_existing_synth_omission_footer(text)

        self.assertEqual(stripped, "")

    def test_strip_existing_synth_omission_footer_ignores_heading_inside_fenced_code(self) -> None:
        heading = rf._SYNTH_OMISSION_FOOTER_HEADING
        text = "\n".join(
            [
                "## Technical Assessment",
                "**Verdict**: APPROVE",
                "",
                "```md",
                heading,
                "quoted inside fence",
                "```",
                "",
                "### Reusability",
                "- Still here. Sources: `pkg/module.py:1`",
                "",
            ]
        )

        stripped = rf._strip_existing_synth_omission_footer(text)

        self.assertEqual(stripped, text)

    def test_strip_existing_synth_omission_footer_is_idempotent_across_successive_rewrites(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_md = Path(tmp) / "review.md"
            review_md.write_text(
                "\n".join(
                    [
                        "## Business / Product Assessment",
                        "**Verdict**: APPROVE",
                        "",
                        "### Strengths",
                        "- Drop me. Sources: `pkg/module.py:2`",
                        "",
                        "### In Scope Issues",
                        "- None.",
                        "",
                        "### Out of Scope Issues",
                        "- None.",
                        "",
                        "### Reusability",
                        "- None.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            dropped = [
                {
                    "section_key": "Business / Product Assessment|Strengths|4",
                    "bullet_index": 1,
                    "section_label": "'### Strengths' under '## Business / Product Assessment' (line 4)",
                    "bullet_text": "- Drop me. Sources: `pkg/module.py:2`",
                    "critical": False,
                    "reason": "bad cite",
                }
            ]

            rf._rewrite_review_md_dropping_bullets(review_md_path=review_md, dropped=dropped)
            rf._rewrite_review_md_dropping_bullets(review_md_path=review_md, dropped=dropped)

            rewritten = review_md.read_text(encoding="utf-8")

        self.assertEqual(rewritten.count(rf._SYNTH_OMISSION_FOOTER_HEADING), 1)

    def test_rewrite_and_footer_agree_on_filtered_omission_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_md = Path(tmp) / "review.md"
            review_md.write_text(
                "\n".join(
                    [
                        "## Business / Product Assessment",
                        "**Verdict**: APPROVE",
                        "",
                        "### Strengths",
                        "- Drop me. Sources: `pkg/module.py:2`",
                        "",
                        "### In Scope Issues",
                        "- None.",
                        "",
                        "### Out of Scope Issues",
                        "- None.",
                        "",
                        "### Reusability",
                        "- Reusable note. Sources: `pkg/module.py:1`",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            dropped = [
                {
                    "section_key": "Business / Product Assessment|Strengths|4",
                    "bullet_index": 1,
                    "section_label": "'### Strengths' under '## Business / Product Assessment' (line 4)",
                    "bullet_text": "- Drop me. Sources: `pkg/module.py:2`",
                    "critical": False,
                    "reason": "bad cite",
                },
                {
                    "section_key": "",
                    "bullet_index": 0,
                    "section_label": "unattributed phantom",
                    "bullet_text": "- phantom bullet",
                    "critical": False,
                    "reason": "should not appear",
                },
            ]

            rf._rewrite_review_md_dropping_bullets(review_md_path=review_md, dropped=dropped)
            rewritten = review_md.read_text(encoding="utf-8")
            footer = rf._format_synth_omission_footer(dropped)

        self.assertIn(rf._SYNTH_OMISSION_FOOTER_HEADING, rewritten)
        self.assertNotIn("phantom bullet", rewritten)
        self.assertNotIn("unattributed phantom", rewritten)
        self.assertIn("bullet #1", footer)
        self.assertNotIn("bullet #0", footer)
        self.assertNotIn("unattributed phantom", footer)

    def test_rewrite_ignores_indented_markdown_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_md = Path(tmp) / "review.md"
            review_md.write_text(
                "\n".join(
                    [
                        "## Business / Product Assessment",
                        "**Verdict**: APPROVE",
                        "",
                        "### Strengths",
                        "- Drop me. Sources: `pkg/module.py:2`",
                        "",
                        "    ## Indented heading inside a code/quote block",
                        "    - Not a section bullet. Sources: `pkg/module.py:9`",
                        "",
                        "### In Scope Issues",
                        "- None.",
                        "",
                        "### Out of Scope Issues",
                        "- None.",
                        "",
                        "### Reusability",
                        "- None.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            dropped = [
                {
                    "section_key": "Business / Product Assessment|Strengths|4",
                    "bullet_index": 1,
                    "section_label": "'### Strengths' under '## Business / Product Assessment' (line 4)",
                    "bullet_text": "- Drop me. Sources: `pkg/module.py:2`",
                    "critical": False,
                    "reason": "bad cite",
                }
            ]

            rf._rewrite_review_md_dropping_bullets(review_md_path=review_md, dropped=dropped)
            rewritten = review_md.read_text(encoding="utf-8")

        body, _, footer = rewritten.partition(rf._SYNTH_OMISSION_FOOTER_HEADING)
        self.assertNotIn("- Drop me.", body)
        self.assertIn("    ## Indented heading inside a code/quote block", body)
        self.assertIn("    - Not a section bullet.", body)
        self.assertIn("dropped bullet text: Drop me.", footer)

    def test_synth_grounding_error_list_uses_specific_citation_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_dir = root / "repo"
            work_dir = root / "work"
            repo_dir.mkdir()
            work_dir.mkdir()
            (repo_dir / "src").mkdir()
            (repo_dir / "src" / "app.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
            review_md = root / "review.md"
            review_md.write_text(
                "\n".join(
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
                        "- Business value is clear. Sources: `src/app.py:99`",
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
                ),
                encoding="utf-8",
            )

            validation = rf.validate_multipass_synth_grounding(
                artifact_path=review_md,
                step_outputs=[],
                repo_dir=repo_dir,
                work_dir=work_dir,
            )

        self.assertFalse(validation["valid"])
        joined_errors = "\n".join(validation["errors"])
        self.assertIn("cites missing source line", joined_errors)
        self.assertNotIn(
            "must cite at least one valid primary-evidence line",
            "\n".join(
                e
                for e in validation["errors"]
                if "cites missing source line" not in e and "cites unsupported synth source" not in e
            ),
        )

    def test_apply_synth_severity_finalization_refuses_when_all_critical_would_empty_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_dir = root / "repo"
            work_dir = root / "work"
            repo_dir.mkdir()
            work_dir.mkdir()
            (repo_dir / "pkg").mkdir()
            (repo_dir / "pkg" / "module.py").write_text("a\nb\nc\n", encoding="utf-8")
            review_md = root / "review.md"
            review_md.write_text(
                "\n".join(
                    [
                        "## Business / Product Assessment",
                        "**Verdict**: REQUEST CHANGES",
                        "",
                        "### Strengths",
                        "- Good. Sources: `pkg/module.py:2`",
                        "",
                        "### In Scope Issues",
                        "- Sole critical issue bullet. Sources: `pkg/module.py:99`",
                        "",
                        "### Out of Scope Issues",
                        "- None.",
                        "",
                        "### Reusability",
                        "- Good. Sources: `pkg/module.py:1`",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            original_text = review_md.read_text(encoding="utf-8")
            invalid_bullet = {
                "section": "In Scope Issues",
                "section_label": "'### In Scope Issues' under '## Business / Product Assessment' (line 7)",
                "section_line": 7,
                "section_key": "Business / Product Assessment|In Scope Issues|7",
                "parent": "Business / Product Assessment",
                "bullet_index": 1,
                "bullet_text": "- Sole critical issue bullet. Sources: `pkg/module.py:99`",
                "critical": True,
                "reason": "cites missing source line",
            }

            finalized, result, dropped = rf._apply_synth_severity_finalization(
                meta={},
                work_dir=work_dir,
                grounding_mode="strict",
                artifact_path=review_md,
                step_outputs=[],
                repo_dir=repo_dir,
                validation={"valid": False, "invalid_bullets": [invalid_bullet]},
                ui_enabled=True,
                allow_critical_omission=True,
            )

            self.assertFalse(finalized)
            self.assertEqual(dropped, [])
            self.assertEqual(review_md.read_text(encoding="utf-8"), original_text)

    def test_synth_section_surviving_bullet_counts_ignores_indented_pseudo_bullets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_md = root / "review.md"
            review_md.write_text(
                "\n".join(
                    [
                        "## Business / Product Assessment",
                        "**Verdict**: REQUEST CHANGES",
                        "",
                        "### In Scope Issues",
                        "- Real issue bullet. Sources: `pkg/module.py:2`",
                        "    - Indented pseudo-bullet. Sources: `pkg/module.py:2`",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            counts = rf._synth_section_surviving_bullet_counts(
                artifact_path=review_md,
                drop_keys={("Business / Product Assessment|In Scope Issues|4", 1)},
            )

        self.assertEqual(counts["Business / Product Assessment|In Scope Issues|4"], 0)

    def test_ui_synth_retry_loop_enforces_ui_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta_path = root / "meta.json"
            progress = rf.SessionProgress(meta_path, quiet=True)
            progress.init({"session_id": "session-cap", "multipass": {"runs": []}, "llm": {}, "codex": {}})
            review_md = root / "review.md"
            invalid_validation = {"valid": False, "errors": ["missing citation"], "invalid_bullets": []}
            llm_result = rf.LlmRunResult(adapter_meta={"usage": {}}, resume=None)
            synth_llm = {
                "resolved": {"provider": "openai", "model": "gpt-5", "reasoning_effort": "medium"},
                "resolution_meta": {
                    "resolved": {
                        "model": "gpt-5",
                        "reasoning_effort": "medium",
                        "reasoning_effort_source": "cli",
                        "reasoning_effort_source_detail": "cli",
                    }
                },
                "meta": {"provider": "openai", "effective_reasoning_effort": "medium"},
            }
            cap = rf._MULTIPASS_SYNTH_GROUNDING_UI_MAX_RETRIES

            with (
                mock.patch.object(rf, "run_llm_exec", return_value=llm_result) as run_mock,
                mock.patch.object(
                    rf,
                    "_validate_or_reuse_synth_artifact",
                    return_value=(False, invalid_validation),
                ),
                mock.patch.object(
                    rf,
                    "_apply_synth_severity_finalization",
                    return_value=(False, invalid_validation, []),
                ),
                mock.patch.object(
                    rf,
                    "prompt_synth_grounding_retry_choice",
                    side_effect=["retry"] * (cap + 1) + ["abort"],
                ) as retry_prompt,
                mock.patch.object(rf, "prompt_grounding_retry_effort", return_value=None),
                mock.patch.object(rf, "_enforce_chunkhound_tool_proof"),
                mock.patch.object(rf, "_emit_multipass_grounding_failure_playbook") as playbook_mock,
            ):
                with self.assertRaises(rf.ReviewflowError):
                    rf._execute_multipass_synth_stage(
                        progress=progress,
                        repo_dir=root / "repo",
                        work_dir=root / "work",
                        session_id="session-cap",
                        review_md_path=review_md,
                        synth_prompt="prompt",
                        synth_llm=synth_llm,
                        synth_runtime_policy={
                            "codex_flags": [],
                            "codex_config_overrides": [],
                            "sandbox_mode": "workspace-write",
                            "approval_policy": "never",
                        },
                        synth_step_outputs=[],
                        grounding_mode="strict",
                        env={},
                        stream=False,
                        add_dirs=[],
                        codex_meta=None,
                        ui_enabled=True,
                        prompt_template_name="mrereview_gh_local_big_synth.md",
                        run_kind="synth",
                        review_stage="multipass_synth",
                        stage_label="multipass synth",
                        failure_message="synth failed",
                        multipass_cfg={},
                    )

            self.assertEqual(run_mock.call_count, cap + 1)
            self.assertEqual(retry_prompt.call_count, cap + 2)
            last_reprompt = retry_prompt.call_args_list[-1]
            self.assertFalse(last_reprompt.kwargs.get("retry_available", True))
            playbook_mock.assert_called_once()
            run_entry = progress.meta["multipass"]["runs"][0]
            self.assertTrue(run_entry["grounding_retried"])
            self.assertEqual(len(run_entry["grounding_attempts"]), cap + 1)

    def test_ui_synth_retry_cap_still_allows_finalize_choice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta_path = root / "meta.json"
            progress = rf.SessionProgress(meta_path, quiet=True)
            progress.init({"session_id": "session-cap-finalize", "multipass": {"runs": []}, "llm": {}, "codex": {}})
            review_md = root / "review.md"
            invalid_validation = {"valid": False, "errors": ["missing citation"], "invalid_bullets": []}
            finalized_validation = {"valid": True, "errors": [], "invalid_bullets": []}
            llm_result = rf.LlmRunResult(adapter_meta={"usage": {}}, resume=None)
            synth_llm = {
                "resolved": {"provider": "openai", "model": "gpt-5", "reasoning_effort": "medium"},
                "resolution_meta": {
                    "resolved": {
                        "model": "gpt-5",
                        "reasoning_effort": "medium",
                        "reasoning_effort_source": "cli",
                        "reasoning_effort_source_detail": "cli",
                    }
                },
                "meta": {"provider": "openai", "effective_reasoning_effort": "medium"},
            }
            cap = rf._MULTIPASS_SYNTH_GROUNDING_UI_MAX_RETRIES
            prompt_choices = ["retry"] * cap + ["finalize"]

            with (
                mock.patch.object(rf, "run_llm_exec", return_value=llm_result) as run_mock,
                mock.patch.object(
                    rf,
                    "_validate_or_reuse_synth_artifact",
                    return_value=(False, invalid_validation),
                ),
                mock.patch.object(
                    rf,
                    "_apply_synth_severity_finalization",
                    side_effect=[
                        *((False, invalid_validation, []) for _ in range(cap + 1)),
                        (True, finalized_validation, [{"section_key": "k", "bullet_index": 1}]),
                    ],
                ) as finalize_mock,
                mock.patch.object(rf, "prompt_synth_grounding_retry_choice", side_effect=prompt_choices) as retry_prompt,
                mock.patch.object(rf, "prompt_grounding_retry_effort", return_value=None) as effort_prompt,
                mock.patch.object(rf, "_enforce_chunkhound_tool_proof"),
                mock.patch.object(rf, "_emit_multipass_grounding_failure_playbook") as playbook_mock,
            ):
                success_resume_command = rf._execute_multipass_synth_stage(
                    progress=progress,
                    repo_dir=root / "repo",
                    work_dir=root / "work",
                    session_id="session-cap-finalize",
                    review_md_path=review_md,
                    synth_prompt="prompt",
                    synth_llm=synth_llm,
                    synth_runtime_policy={
                        "codex_flags": [],
                        "codex_config_overrides": [],
                        "sandbox_mode": "workspace-write",
                        "approval_policy": "never",
                    },
                    synth_step_outputs=[],
                    grounding_mode="strict",
                    env={},
                    stream=False,
                    add_dirs=[],
                    codex_meta=None,
                    ui_enabled=True,
                    prompt_template_name="mrereview_gh_local_big_synth.md",
                    run_kind="synth",
                    review_stage="multipass_synth",
                    stage_label="multipass synth",
                    failure_message="synth failed",
                    multipass_cfg={},
                )

            self.assertIsNone(success_resume_command)
            self.assertEqual(run_mock.call_count, cap + 1)
            self.assertEqual(retry_prompt.call_count, cap + 1)
            self.assertEqual(effort_prompt.call_count, cap)
            self.assertTrue(finalize_mock.call_args_list[-1].kwargs["allow_critical_omission"])
            playbook_mock.assert_not_called()

    def test_synth_retry_finalize_choice_drops_critical_bullets_and_breaks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta_path = root / "meta.json"
            progress = rf.SessionProgress(meta_path, quiet=True)
            progress.init({"session_id": "session-finalize", "multipass": {"runs": []}, "llm": {}, "codex": {}})
            review_md = root / "review.md"
            invalid_validation = {"valid": False, "errors": ["missing citation"], "invalid_bullets": []}
            finalized_validation = {"valid": True, "errors": [], "invalid_bullets": []}
            llm_result = rf.LlmRunResult(adapter_meta={"usage": {}}, resume=None)
            synth_llm = {
                "resolved": {"provider": "openai", "model": "gpt-5", "reasoning_effort": "medium"},
                "resolution_meta": {
                    "resolved": {
                        "model": "gpt-5",
                        "reasoning_effort": "medium",
                        "reasoning_effort_source": "cli",
                        "reasoning_effort_source_detail": "cli",
                    }
                },
                "meta": {"provider": "openai", "effective_reasoning_effort": "medium"},
            }

            with (
                mock.patch.object(rf, "run_llm_exec", return_value=llm_result) as run_mock,
                mock.patch.object(
                    rf,
                    "_validate_or_reuse_synth_artifact",
                    return_value=(False, invalid_validation),
                ),
                mock.patch.object(
                    rf,
                    "_apply_synth_severity_finalization",
                    side_effect=[
                        # first-pass (allow_critical_omission=False) refuses
                        (False, invalid_validation, []),
                        # second-pass (allow_critical_omission=True) succeeds
                        (True, finalized_validation, [{"section_key": "k", "bullet_index": 1}]),
                    ],
                ) as finalize_mock,
                mock.patch.object(rf, "prompt_synth_grounding_retry_choice", return_value="finalize") as retry_prompt,
                mock.patch.object(rf, "prompt_grounding_retry_effort") as effort_prompt,
                mock.patch.object(rf, "_enforce_chunkhound_tool_proof"),
                mock.patch.object(rf, "_emit_multipass_grounding_failure_playbook") as playbook_mock,
            ):
                success_resume_command = rf._execute_multipass_synth_stage(
                    progress=progress,
                    repo_dir=root / "repo",
                    work_dir=root / "work",
                    session_id="session-finalize",
                    review_md_path=review_md,
                    synth_prompt="prompt",
                    synth_llm=synth_llm,
                    synth_runtime_policy={
                        "codex_flags": [],
                        "codex_config_overrides": [],
                        "sandbox_mode": "workspace-write",
                        "approval_policy": "never",
                    },
                    synth_step_outputs=[],
                    grounding_mode="strict",
                    env={},
                    stream=False,
                    add_dirs=[],
                    codex_meta=None,
                    ui_enabled=True,
                    prompt_template_name="mrereview_gh_local_big_synth.md",
                    run_kind="synth",
                    review_stage="multipass_synth",
                    stage_label="multipass synth",
                    failure_message="synth failed",
                    multipass_cfg={},
                )

            self.assertIsNone(success_resume_command)
            # Only one LLM exec: finalize path must not rerun the synth LLM.
            self.assertEqual(run_mock.call_count, 1)
            retry_prompt.assert_called_once()
            # "finalize" path must not ask for an effort override — that's a
            # retry-only prompt.
            effort_prompt.assert_not_called()
            # Two finalize calls: first-pass (non-critical-only) then
            # second-pass (allow_critical_omission=True after "finalize" choice).
            self.assertEqual(finalize_mock.call_count, 2)
            second_call_kwargs = finalize_mock.call_args_list[1].kwargs
            self.assertTrue(second_call_kwargs["allow_critical_omission"])
            # Terminal playbook must not fire on a successful finalization.
            playbook_mock.assert_not_called()

    def test_synth_retry_non_ui_auto_retries_once_then_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta_path = root / "meta.json"
            progress = rf.SessionProgress(meta_path, quiet=True)
            progress.init({"session_id": "session-non-ui", "multipass": {"runs": []}, "llm": {}, "codex": {}})
            review_md = root / "review.md"
            invalid_validation = {"valid": False, "errors": ["missing citation"], "invalid_bullets": []}
            llm_result = rf.LlmRunResult(adapter_meta={"usage": {}}, resume=None)
            synth_llm = {
                "resolved": {"provider": "openai", "model": "gpt-5", "reasoning_effort": "medium"},
                "resolution_meta": {
                    "resolved": {
                        "model": "gpt-5",
                        "reasoning_effort": "medium",
                        "reasoning_effort_source": "cli",
                        "reasoning_effort_source_detail": "cli",
                    }
                },
                "meta": {"provider": "openai", "effective_reasoning_effort": "medium"},
            }

            with (
                mock.patch.object(rf, "run_llm_exec", return_value=llm_result) as run_mock,
                mock.patch.object(
                    rf,
                    "_validate_or_reuse_synth_artifact",
                    return_value=(False, invalid_validation),
                ),
                mock.patch.object(
                    rf,
                    "_apply_synth_severity_finalization",
                    return_value=(False, invalid_validation, []),
                ),
                mock.patch.object(rf, "prompt_synth_grounding_retry_choice") as retry_prompt,
                mock.patch.object(rf, "prompt_grounding_retry_effort") as effort_prompt,
                mock.patch.object(rf, "_enforce_chunkhound_tool_proof"),
                mock.patch.object(rf, "_emit_multipass_grounding_failure_playbook") as playbook_mock,
            ):
                with self.assertRaises(rf.ReviewflowError):
                    rf._execute_multipass_synth_stage(
                        progress=progress,
                        repo_dir=root / "repo",
                        work_dir=root / "work",
                        session_id="session-non-ui",
                        review_md_path=review_md,
                        synth_prompt="prompt",
                        synth_llm=synth_llm,
                        synth_runtime_policy={
                            "codex_flags": [],
                            "codex_config_overrides": [],
                            "sandbox_mode": "workspace-write",
                            "approval_policy": "never",
                        },
                        synth_step_outputs=[],
                        grounding_mode="strict",
                        env={},
                        stream=False,
                        add_dirs=[],
                        codex_meta=None,
                        ui_enabled=False,
                        prompt_template_name="mrereview_gh_local_big_synth.md",
                        run_kind="synth",
                        review_stage="multipass_synth",
                        stage_label="multipass synth",
                        failure_message="synth failed",
                        multipass_cfg={},
                    )

            # Single auto-retry: first attempt + one retry = 2 exec calls total.
            self.assertEqual(run_mock.call_count, 2)
            # UI prompts must never fire in non-UI mode.
            retry_prompt.assert_not_called()
            effort_prompt.assert_not_called()
            playbook_mock.assert_called_once()
            run_entry = progress.meta["multipass"]["runs"][0]
            self.assertTrue(run_entry["grounding_retried"])
            self.assertEqual(len(run_entry["grounding_attempts"]), 2)

    def test_ui_synth_retry_lost_tty_uses_non_ui_auto_retry_once_then_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta_path = root / "meta.json"
            progress = rf.SessionProgress(meta_path, quiet=True)
            progress.init({"session_id": "session-ui-lost-tty", "multipass": {"runs": []}, "llm": {}, "codex": {}})
            review_md = root / "review.md"
            invalid_validation = {"valid": False, "errors": ["missing citation"], "invalid_bullets": []}
            llm_result = rf.LlmRunResult(adapter_meta={"usage": {}}, resume=None)
            synth_llm = {
                "resolved": {"provider": "openai", "model": "gpt-5", "reasoning_effort": "medium"},
                "resolution_meta": {
                    "resolved": {
                        "model": "gpt-5",
                        "reasoning_effort": "medium",
                        "reasoning_effort_source": "cli",
                        "reasoning_effort_source_detail": "cli",
                    }
                },
                "meta": {"provider": "openai", "effective_reasoning_effort": "medium"},
            }

            with (
                mock.patch.object(rf, "run_llm_exec", return_value=llm_result) as run_mock,
                mock.patch.object(
                    rf,
                    "_validate_or_reuse_synth_artifact",
                    return_value=(False, invalid_validation),
                ),
                mock.patch.object(
                    rf,
                    "_apply_synth_severity_finalization",
                    return_value=(False, invalid_validation, []),
                ),
                mock.patch.object(rf, "prompt_synth_grounding_retry_choice", return_value=None) as retry_prompt,
                mock.patch.object(rf, "prompt_grounding_retry_effort") as effort_prompt,
                mock.patch.object(rf, "_enforce_chunkhound_tool_proof"),
                mock.patch.object(rf, "_emit_multipass_grounding_failure_playbook") as playbook_mock,
            ):
                with self.assertRaises(rf.ReviewflowError):
                    rf._execute_multipass_synth_stage(
                        progress=progress,
                        repo_dir=root / "repo",
                        work_dir=root / "work",
                        session_id="session-ui-lost-tty",
                        review_md_path=review_md,
                        synth_prompt="prompt",
                        synth_llm=synth_llm,
                        synth_runtime_policy={
                            "codex_flags": [],
                            "codex_config_overrides": [],
                            "sandbox_mode": "workspace-write",
                            "approval_policy": "never",
                        },
                        synth_step_outputs=[],
                        grounding_mode="strict",
                        env={},
                        stream=False,
                        add_dirs=[],
                        codex_meta=None,
                        ui_enabled=True,
                        prompt_template_name="mrereview_gh_local_big_synth.md",
                        run_kind="synth",
                        review_stage="multipass_synth",
                        stage_label="multipass synth",
                        failure_message="synth failed",
                        multipass_cfg={},
                    )

            self.assertEqual(run_mock.call_count, 2)
            retry_prompt.assert_called_once()
            effort_prompt.assert_not_called()
            playbook_mock.assert_called_once()
            run_entry = progress.meta["multipass"]["runs"][0]
            self.assertTrue(run_entry["grounding_retried"])
            self.assertEqual(len(run_entry["grounding_attempts"]), 2)

    def test_non_ui_synth_retry_preserves_first_failed_artifact_and_validation_until_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_dir = root / "repo"
            work_dir = root / "work"
            repo_dir.mkdir()
            work_dir.mkdir()
            (repo_dir / "src").mkdir()
            (repo_dir / "src" / "app.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
            meta_path = root / "meta.json"
            progress = rf.SessionProgress(meta_path, quiet=True)
            progress.init({"session_id": "session-preserve", "multipass": {"runs": []}, "llm": {}, "codex": {}})
            review_md = root / "review.md"
            first_invalid = self._valid_synth_markdown(primary_citation="src/app.py:99").replace(
                "Business value is clear.",
                "First failed synth attempt.",
                1,
            )
            second_invalid = self._valid_synth_markdown(primary_citation="src/app.py:999").replace(
                "Business value is clear.",
                "Second failed synth attempt.",
                1,
            )
            llm_result = rf.LlmRunResult(adapter_meta={"usage": {}}, resume=None)
            attempt_outputs = [first_invalid, second_invalid]

            def fake_run_llm_exec(**kwargs: object) -> rf.LlmRunResult:
                output_path = Path(str(kwargs["output_path"]))
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(attempt_outputs.pop(0), encoding="utf-8")
                return llm_result

            with (
                mock.patch.object(rf, "run_llm_exec", side_effect=fake_run_llm_exec) as run_mock,
                mock.patch.object(rf, "_enforce_chunkhound_tool_proof"),
                mock.patch.object(rf, "_emit_multipass_grounding_failure_playbook") as playbook_mock,
            ):
                with self.assertRaisesRegex(rf.ReviewflowError, "synth failed"):
                    rf._execute_multipass_synth_stage(
                        progress=progress,
                        repo_dir=repo_dir,
                        work_dir=work_dir,
                        session_id="session-preserve",
                        review_md_path=review_md,
                        synth_prompt="prompt",
                        synth_llm={
                            "resolved": {
                                "provider": "openai",
                                "model": "gpt-5",
                                "reasoning_effort": "medium",
                            },
                            "resolution_meta": {
                                "resolved": {
                                    "model": "gpt-5",
                                    "reasoning_effort": "medium",
                                    "reasoning_effort_source": "cli",
                                    "reasoning_effort_source_detail": "cli",
                                }
                            },
                            "meta": {"provider": "openai", "effective_reasoning_effort": "medium"},
                        },
                        synth_runtime_policy={
                            "codex_flags": [],
                            "codex_config_overrides": [],
                            "sandbox_mode": "workspace-write",
                            "approval_policy": "never",
                        },
                        synth_step_outputs=[],
                        grounding_mode="strict",
                        env={},
                        stream=False,
                        add_dirs=[],
                        codex_meta=None,
                        ui_enabled=False,
                        prompt_template_name="mrereview_gh_local_big_synth.md",
                        run_kind="synth",
                        review_stage="multipass_synth",
                        stage_label="multipass synth",
                        failure_message="synth failed",
                        multipass_cfg={},
                    )

            self.assertEqual(run_mock.call_count, 2)
            playbook_mock.assert_called_once()
            review_text = review_md.read_text(encoding="utf-8")
            self.assertIn("First failed synth attempt.", review_text)
            self.assertNotIn("Second failed synth attempt.", review_text)
            synth_entry = progress.meta["multipass"]["validation"]["artifacts"]["synth"]
            self.assertEqual(synth_entry["artifact_path"], str(review_md))
            self.assertEqual(synth_entry["artifact_sha256"], rf._artifact_sha256(review_md))

    def test_synth_retry_none_effort_keeps_original_synth_llm_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta_path = root / "meta.json"
            progress = rf.SessionProgress(meta_path, quiet=True)
            progress.init({"session_id": "session-none", "multipass": {"runs": []}, "llm": {}, "codex": {}})
            review_md = root / "review.md"
            invalid_validation = {"valid": False, "errors": ["missing citation"], "invalid_bullets": []}
            valid_validation = {"valid": True, "errors": [], "invalid_bullets": []}
            llm_result = rf.LlmRunResult(adapter_meta={"usage": {}}, resume=None)
            synth_llm: dict[str, Any] = {
                "resolved": {"provider": "codex", "model": "gpt-5.4", "reasoning_effort": "medium"},
                "resolution_meta": {
                    "resolved": {
                        "model": "gpt-5.4",
                        "reasoning_effort": "medium",
                        "reasoning_effort_source": "cli",
                        "reasoning_effort_source_detail": "cli",
                    }
                },
                "meta": {"provider": "codex", "effective_reasoning_effort": "medium"},
            }
            # Snapshot the original resolved/resolution_meta/meta before the call.
            original_resolved = dict(synth_llm["resolved"])
            original_resolution_meta_resolved = dict(synth_llm["resolution_meta"]["resolved"])
            original_meta = dict(synth_llm["meta"])

            rebuild_mock = mock.MagicMock()

            with (
                mock.patch.object(rf, "run_llm_exec", return_value=llm_result) as run_mock,
                mock.patch.object(
                    rf,
                    "_validate_or_reuse_synth_artifact",
                    side_effect=[(False, invalid_validation), (True, valid_validation)],
                ),
                mock.patch.object(
                    rf,
                    "_apply_synth_severity_finalization",
                    return_value=(False, invalid_validation, []),
                ),
                mock.patch.object(rf, "prompt_synth_grounding_retry_choice", return_value="retry"),
                mock.patch.object(rf, "prompt_grounding_retry_effort", return_value=None) as effort_prompt,
                mock.patch.object(rf, "_rebuild_multipass_retry_stage_state", rebuild_mock),
                mock.patch.object(rf, "_enforce_chunkhound_tool_proof"),
            ):
                rf._execute_multipass_synth_stage(
                    progress=progress,
                    repo_dir=root / "repo",
                    work_dir=root / "work",
                    session_id="session-none",
                    review_md_path=review_md,
                    synth_prompt="prompt",
                    synth_llm=synth_llm,
                    synth_runtime_policy={
                        "codex_flags": ['model_reasoning_effort="medium"'],
                        "codex_config_overrides": [],
                        "sandbox_mode": "workspace-write",
                        "approval_policy": "never",
                    },
                    synth_step_outputs=[],
                    grounding_mode="strict",
                    env={},
                    stream=False,
                    add_dirs=[],
                    codex_meta=None,
                    ui_enabled=True,
                    prompt_template_name="mrereview_gh_local_big_synth.md",
                    run_kind="synth",
                    review_stage="multipass_synth",
                    stage_label="multipass synth",
                    failure_message="synth failed",
                    multipass_cfg={},
                )

            # Retry happened (two exec calls, one picker prompt).
            self.assertEqual(run_mock.call_count, 2)
            effort_prompt.assert_called_once()
            # None effort must NOT trigger a stage rebuild.
            rebuild_mock.assert_not_called()
            # Original synth_llm dict is untouched.
            self.assertEqual(synth_llm["resolved"], original_resolved)
            self.assertEqual(synth_llm["resolution_meta"]["resolved"], original_resolution_meta_resolved)
            self.assertEqual(synth_llm["meta"], original_meta)

    def test_apply_synth_severity_finalization_blocks_critical_incremental_finalization(self) -> None:
        """Incremental resume path: a critical-section failure must not be dropped.

        Mirrors the primary-synth critical-bullet survivor guard, covering the
        call site routed from ``_validate_or_reuse_synth_artifact`` on the
        incremental-resume path (tests/_reviewflow_unittest_grounding_impl.py's
        earlier incremental finalization coverage is non-critical only).
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_dir = root / "repo"
            work_dir = root / "work"
            repo_dir.mkdir()
            work_dir.mkdir()
            (repo_dir / "pkg").mkdir()
            (repo_dir / "pkg" / "module.py").write_text("a\nb\nc\n", encoding="utf-8")
            review_md = root / "review.md"
            review_md.write_text(
                "\n".join(
                    [
                        "## Business / Product Assessment",
                        "**Verdict**: REQUEST CHANGES",
                        "",
                        "### Strengths",
                        "- Good. Sources: `pkg/module.py:2`",
                        "- Good2. Sources: `pkg/module.py:3`",
                        "",
                        "### In Scope Issues",
                        "- Sole critical bullet. Sources: `pkg/module.py:99`",
                        "",
                        "### Out of Scope Issues",
                        "- Good. Sources: `pkg/module.py:1`",
                        "- Good2. Sources: `pkg/module.py:2`",
                        "",
                        "### Reusability",
                        "- Good. Sources: `pkg/module.py:1`",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            original_text = review_md.read_text(encoding="utf-8")
            critical_bullet = {
                "section": "In Scope Issues",
                "section_label": "'### In Scope Issues' under '## Business / Product Assessment' (line 7)",
                "section_line": 7,
                "section_key": "Business / Product Assessment|In Scope Issues|7",
                "parent": "Business / Product Assessment",
                "bullet_index": 1,
                "bullet_text": "- Sole critical bullet. Sources: `pkg/module.py:99`",
                "critical": True,
                "reason": "cites missing source line",
            }

            # Non-UI incremental finalization (allow_critical_omission defaults
            # to False): critical bullet must never be dropped — even if it is
            # the only invalid bullet.
            finalized, result, dropped = rf._apply_synth_severity_finalization(
                meta={},
                work_dir=work_dir,
                grounding_mode="strict",
                artifact_path=review_md,
                step_outputs=[],
                repo_dir=repo_dir,
                validation={"valid": False, "invalid_bullets": [critical_bullet]},
                ui_enabled=False,
                allow_critical_omission=False,
            )

            self.assertFalse(finalized)
            self.assertEqual(dropped, [])
            # Review markdown untouched.
            self.assertEqual(review_md.read_text(encoding="utf-8"), original_text)

    def test_step_grounding_retry_effort_picker_shows_last_override_as_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta_path = root / "meta.json"
            progress = rf.SessionProgress(meta_path, quiet=True)
            entry = rf.MultipassStepEntry(
                index=1,
                step_id="01",
                step_title="API review",
                step_focus="grounding",
                output_path=root / "review.step-01.md",
                prompt="step prompt",
                should_run=True,
            )
            progress.init({
                "session_id": "session-default",
                "multipass": {"step_workers": 1, "runs": []},
                "llm": {},
                "codex": {},
            })
            rf._ensure_multipass_run_entry(
                progress.meta,
                kind="step",
                step_index=1,
                step_id=entry.step_id,
                step_title=entry.step_title,
                output_path=entry.output_path,
                template_id="builtin:step",
                prompt=entry.prompt,
                stage_llm_meta={"provider": "codex", "effective_reasoning_effort": "medium"},
            )
            raw_result = rf.MultipassStepRunResult(
                entry=entry,
                llm_result=rf.LlmRunResult(resume=None),
                duration_seconds=1.25,
            )

            with (
                mock.patch.object(rf, "_run_multipass_step_llm", side_effect=[raw_result, raw_result, raw_result]),
                mock.patch.object(
                    rf,
                    "_finalize_multipass_step_result",
                    side_effect=[
                        rf.StepGroundingValidationError(
                            "bad grounding",
                            step_validation={"valid": False, "errors": ["missing citation"]},
                        ),
                        rf.StepGroundingValidationError(
                            "bad grounding again",
                            step_validation={"valid": False, "errors": ["missing citation"]},
                        ),
                        None,
                    ],
                ),
                mock.patch.object(rf, "prompt_grounding_retry_skip", return_value="retry"),
                mock.patch.object(
                    rf,
                    "prompt_grounding_retry_effort",
                    side_effect=["high", "high"],
                ) as effort_prompt,
            ):
                rf._execute_multipass_step_stage(
                    progress=progress,
                    work_dir=root / "work",
                    repo_dir=root / "repo",
                    session_id="session-default",
                    grounding_mode="strict",
                    step_entries=[entry],
                    step_worker_count=1,
                    llm_resolved={"provider": "codex", "model": "gpt-5.4", "reasoning_effort": "medium"},
                    llm_resolution_meta={
                        "resolved": {
                            "model": "gpt-5.4",
                            "reasoning_effort": "medium",
                            "reasoning_effort_source": "cli",
                            "reasoning_effort_source_detail": "cli",
                        }
                    },
                    env={},
                    stream=False,
                    add_dirs=[],
                    runtime_policy={
                        "codex_flags": ['model_reasoning_effort="medium"'],
                        "codex_config_overrides": [],
                        "sandbox_mode": "workspace-write",
                        "approval_policy": "never",
                    },
                    templates={"step": "mrereview_gh_local_big_step.md"},
                    codex_meta=None,
                    quiet=True,
                    ui_enabled=True,
                    multipass_cfg={},
                )

            self.assertEqual(effort_prompt.call_count, 2)
            first_call_default = effort_prompt.call_args_list[0].kwargs.get("default_effort")
            second_call_default = effort_prompt.call_args_list[1].kwargs.get("default_effort")
            self.assertEqual(first_call_default, "medium")
            self.assertEqual(second_call_default, "high")

    def test_first_grounding_failure_validation_captures_pre_finalization_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta_path = root / "meta.json"
            progress = rf.SessionProgress(meta_path, quiet=True)
            progress.init({"session_id": "session-pre-final", "multipass": {"runs": []}, "llm": {}, "codex": {}})
            review_md = root / "review.md"
            raw_validation = {
                "valid": False,
                "errors": ["raw pre-finalization error"],
                "invalid_bullets": [{"section_key": "k", "bullet_index": 1, "critical": False}],
            }
            post_finalization_validation = {
                "valid": False,
                "errors": ["post-finalization error after non-critical drop"],
                "invalid_bullets": [],
            }
            llm_result = rf.LlmRunResult(adapter_meta={"usage": {}}, resume=None)
            synth_llm = {
                "resolved": {"provider": "openai", "model": "gpt-5", "reasoning_effort": "medium"},
                "resolution_meta": {
                    "resolved": {
                        "model": "gpt-5",
                        "reasoning_effort": "medium",
                        "reasoning_effort_source": "cli",
                        "reasoning_effort_source_detail": "cli",
                    }
                },
                "meta": {"provider": "openai", "effective_reasoning_effort": "medium"},
            }

            with (
                mock.patch.object(rf, "run_llm_exec", return_value=llm_result),
                mock.patch.object(
                    rf,
                    "_validate_or_reuse_synth_artifact",
                    return_value=(False, raw_validation),
                ),
                mock.patch.object(
                    rf,
                    "_apply_synth_severity_finalization",
                    return_value=(False, post_finalization_validation, [{"section_key": "k", "bullet_index": 1}]),
                ),
                mock.patch.object(rf, "prompt_synth_grounding_retry_choice", return_value="abort"),
                mock.patch.object(rf, "_enforce_chunkhound_tool_proof"),
                mock.patch.object(rf, "_emit_multipass_grounding_failure_playbook"),
            ):
                with self.assertRaises(rf.ReviewflowError):
                    rf._execute_multipass_synth_stage(
                        progress=progress,
                        repo_dir=root / "repo",
                        work_dir=root / "work",
                        session_id="session-pre-final",
                        review_md_path=review_md,
                        synth_prompt="prompt",
                        synth_llm=synth_llm,
                        synth_runtime_policy={
                            "codex_flags": [],
                            "codex_config_overrides": [],
                            "sandbox_mode": "workspace-write",
                            "approval_policy": "never",
                        },
                        synth_step_outputs=[],
                        grounding_mode="strict",
                        env={},
                        stream=False,
                        add_dirs=[],
                        codex_meta=None,
                        ui_enabled=True,
                        prompt_template_name="mrereview_gh_local_big_synth.md",
                        run_kind="synth",
                        review_stage="multipass_synth",
                        stage_label="multipass synth",
                        failure_message="synth failed",
                        multipass_cfg={},
                    )

            run_entry = progress.meta["multipass"]["runs"][0]
            first_failure = run_entry["first_grounding_failure_validation"]
            self.assertIn("raw pre-finalization error", first_failure.get("errors", []))
            self.assertNotIn("post-finalization error", str(first_failure.get("errors", [])))

    def test_terminal_playbook_reports_candidate_artifact_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta_path = root / "meta.json"
            progress = rf.SessionProgress(meta_path, quiet=True)
            progress.init({
                "session_id": "session-candidate",
                "multipass": {
                    "runs": [],
                    "validation": {"valid": False},
                },
                "llm": {},
                "codex": {},
            })
            review_md = root / "review.md"
            review_md.write_text("prior synth output")
            invalid_validation = {"valid": False, "errors": ["missing citation"], "invalid_bullets": []}
            llm_result = rf.LlmRunResult(adapter_meta={"usage": {}}, resume=None)
            synth_llm = {
                "resolved": {"provider": "openai", "model": "gpt-5", "reasoning_effort": "medium"},
                "resolution_meta": {
                    "resolved": {
                        "model": "gpt-5",
                        "reasoning_effort": "medium",
                        "reasoning_effort_source": "cli",
                        "reasoning_effort_source_detail": "cli",
                    }
                },
                "meta": {"provider": "openai", "effective_reasoning_effort": "medium"},
            }

            with (
                mock.patch.object(rf, "run_llm_exec", return_value=llm_result),
                mock.patch.object(
                    rf,
                    "_validate_or_reuse_synth_artifact",
                    return_value=(False, invalid_validation),
                ),
                mock.patch.object(
                    rf,
                    "_apply_synth_severity_finalization",
                    return_value=(False, invalid_validation, []),
                ),
                mock.patch.object(rf, "_enforce_chunkhound_tool_proof"),
                mock.patch.object(rf, "_emit_multipass_grounding_failure_playbook") as playbook_mock,
            ):
                with self.assertRaises(rf.ReviewflowError):
                    rf._execute_multipass_synth_stage(
                        progress=progress,
                        repo_dir=root / "repo",
                        work_dir=root / "work",
                        session_id="session-candidate",
                        review_md_path=review_md,
                        synth_prompt="prompt",
                        synth_llm=synth_llm,
                        synth_runtime_policy={
                            "codex_flags": [],
                            "codex_config_overrides": [],
                            "sandbox_mode": "workspace-write",
                            "approval_policy": "never",
                        },
                        synth_step_outputs=[],
                        grounding_mode="strict",
                        env={},
                        stream=False,
                        add_dirs=[],
                        codex_meta=None,
                        ui_enabled=False,
                        prompt_template_name="mrereview_gh_local_big_synth.md",
                        run_kind="synth",
                        review_stage="multipass_synth",
                        stage_label="multipass synth",
                        failure_message="synth failed",
                        multipass_cfg={},
                    )

            playbook_mock.assert_called_once()
            reported_path = playbook_mock.call_args.kwargs.get("artifact_path")
            self.assertTrue(str(reported_path).endswith("review.candidate.md"))

    def test_incremental_resume_synth_only_skips_grounding_skip_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta_path = root / "meta.json"
            progress = rf.SessionProgress(meta_path, quiet=True)
            step_01_output = root / "review.step-01.md"
            step_01_output.write_text("step 01 output")
            step_02_output = root / "review.step-02.md"
            step_02_output.write_text("step 02 output")
            review_md = root / "review.md"
            review_md.write_text("old review")
            progress.init({
                "session_id": "session-synth-only",
                "pr_url": "https://github.com/x/y/pull/1",
                "number": 1,
                "multipass": {
                    "runs": [],
                    "step_states": [
                        {
                            "step_index": 1,
                            "step_id": "01",
                            "step_title": "step one",
                            "step_focus": "focus",
                            "output_path": str(step_01_output),
                            "status": "completed",
                            "reusable": True,
                        },
                        {
                            "step_index": 2,
                            "step_id": "02",
                            "step_title": "step two",
                            "step_focus": "focus",
                            "output_path": str(step_02_output),
                            "status": "completed",
                            "reusable": True,
                        },
                    ],
                    "grounding_skipped_steps": [
                        {"step_id": "01", "step_title": "step one", "reason": "skipped"},
                    ],
                    "grounding_skipped_step_count": 1,
                    "artifacts": {
                        "step_outputs": [str(step_01_output), str(step_02_output)],
                        "synth_step_outputs": [str(step_02_output)],
                    },
                },
                "llm": {},
                "codex": {},
            })
            step_entries = [
                rf.MultipassStepEntry(
                    index=1, step_id="01", step_title="step one",
                    step_focus="focus", output_path=step_01_output,
                    prompt="prompt", should_run=False,
                ),
                rf.MultipassStepEntry(
                    index=2, step_id="02", step_title="step two",
                    step_focus="focus", output_path=step_02_output,
                    prompt="prompt", should_run=False,
                ),
            ]
            skip_choice = rf._resolve_resume_grounding_skip_choice(
                meta=progress.meta,
                step_entries=step_entries,
                ui_enabled=False,
            )
            self.assertEqual(skip_choice, "rerun")
            synth_outputs, _ = rf._prepare_synth_inputs(
                meta=progress.meta,
                step_entries=step_entries,
                session_id="session-synth-only",
                session_dir=root,
                work_dir=root,
                review_md_path=review_md,
                prefer_persisted_skips=True,
            )
            self.assertEqual(synth_outputs, [str(step_02_output)])
            self.assertNotIn(str(step_01_output), synth_outputs)

    def test_grounding_skipped_step_ids_can_prefer_persisted_records(self) -> None:
        meta = {
            "multipass": {
                "step_states": [
                    {
                        "step_index": 1,
                        "step_id": "01",
                        "step_title": "step one",
                        "status": "reused",
                        "reusable": True,
                    },
                    {
                        "step_index": 2,
                        "step_id": "02",
                        "step_title": "step two",
                        "status": "reused",
                        "reusable": True,
                    },
                ],
                "grounding_skipped_steps": [
                    {"step_id": "01", "step_title": "step one", "reason": "skipped"},
                ],
            }
        }

        self.assertEqual(rf._grounding_skipped_step_ids(meta), set())
        self.assertEqual(
            rf._grounding_skipped_step_ids(meta, prefer_persisted=True),
            {"01"},
        )

    def test_incremental_completed_resume_threads_verbose_guidance_into_resume_synth_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_dir = root / "session-1"
            repo_dir = session_dir / "repo"
            work_dir = session_dir / "work"
            session_dir.mkdir(parents=True, exist_ok=True)
            repo_dir.mkdir(parents=True, exist_ok=True)
            work_dir.mkdir(parents=True, exist_ok=True)
            review_md = session_dir / "review.md"
            review_md.write_text("previous final review\n", encoding="utf-8")
            previous_review = root / "previous-review.md"
            previous_review.write_text("previous snapshot\n", encoding="utf-8")
            existing_plan = work_dir / "review_plan.json"
            existing_plan.write_text(
                json.dumps({"steps": [{"id": "01", "title": "step one", "focus": "focus"}]}),
                encoding="utf-8",
            )
            step_output = session_dir / "review.step-01.md"
            step_output.write_text("step output\n", encoding="utf-8")
            meta_path = session_dir / "meta.json"
            progress = rf.SessionProgress(meta_path, quiet=True)
            progress.init(
                {
                    "session_id": "session-1",
                    "pr_url": "https://github.com/acme/repo/pull/1",
                    "number": 1,
                    "multipass": {
                        "runs": [],
                        "plan_json_path": str(existing_plan),
                        "resume": {},
                        "artifacts": {},
                    },
                    "llm": {},
                    "codex": {},
                }
            )

            captured: dict[str, str] = {}

            def fake_execute_multipass_synth_stage(**kwargs: Any) -> None:
                captured["prompt"] = str(kwargs["synth_prompt"])
                return None

            llm_result = rf.LlmRunResult(adapter_meta={"usage": {}}, resume=None)
            stage_llm = {
                "resolved": {"provider": "openai", "model": "gpt-5", "reasoning_effort": "medium"},
                "resolution_meta": {"resolved": {"reasoning_effort": "medium"}},
                "meta": {"provider": "openai", "effective_reasoning_effort": "medium"},
            }
            step_entries = [
                rf.MultipassStepEntry(
                    index=1,
                    step_id="01",
                    step_title="step one",
                    step_focus="focus",
                    output_path=step_output,
                    prompt="step prompt",
                    should_run=False,
                )
            ]

            with (
                mock.patch.object(rf, "run_llm_exec", return_value=llm_result),
                mock.patch.object(
                    rf,
                    "parse_incremental_resume_plan_json",
                    return_value={"decision": "synth_only", "reason": "small delta", "reopen_step_ids": [], "new_steps": []},
                ),
                mock.patch.object(rf, "_record_multipass_stage_llm"),
                mock.patch.object(rf, "record_llm_usage"),
                mock.patch.object(rf, "record_llm_resume", return_value=None),
                mock.patch.object(rf, "_enforce_chunkhound_tool_proof"),
                mock.patch.object(rf, "_build_incremental_resume_step_entries", return_value=step_entries),
                mock.patch.object(rf, "_prepare_synth_inputs", return_value=([str(step_output)], "- None.")),
                mock.patch.object(rf, "_execute_multipass_synth_stage", side_effect=fake_execute_multipass_synth_stage),
            ):
                rf._run_incremental_completed_multipass_resume(
                    progress=progress,
                    session_id="session-1",
                    session_dir=session_dir,
                    repo_dir=repo_dir,
                    work_dir=work_dir,
                    review_md_path=review_md,
                    meta=progress.meta,
                    pr=rf.parse_pr_url("https://github.com/acme/repo/pull/1"),
                    base_ref_for_review="cure_base__main",
                    agent_desc="",
                    review_intelligence_cfg=_review_intelligence_cfg(),
                    review_intelligence_capabilities=None,
                    plan_llm=stage_llm,
                    step_llm=stage_llm,
                    synth_llm=stage_llm,
                    plan_runtime_policy={},
                    step_runtime_policy={},
                    synth_runtime_policy={},
                    multipass_cfg={},
                    env={},
                    stream=False,
                    add_dirs=[],
                    grounding_mode="off",
                    codex_meta=None,
                    quiet=True,
                    ui_enabled=False,
                    previous_review_point=rf.SessionReviewPoint(
                        kind="complete",
                        artifact_path=previous_review,
                        head_sha="deadbeef",
                        completed_at="2026-04-20T00:00:00+00:00",
                    ),
                    current_review_head_sha="feedface",
                    wtf_enabled=True,
                )

            prompt = captured["prompt"]
            self.assertNotIn("$VERBOSE_FINDING_MODE_GUIDANCE", prompt)
            self.assertIn("Severity/Impact: Critical | High | Medium | Low | Info", prompt)
