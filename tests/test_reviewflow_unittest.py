import argparse
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import unittest
from io import StringIO
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import reviewflow as rf  # noqa: E402
import ui as rui  # noqa: E402


class RenderPromptTests(unittest.TestCase):
    def test_render_prompt_replaces_all_placeholders(self) -> None:
        template = "\n".join(
            [
                "PR_URL=$PR_URL",
                "PR_NUMBER=$PR_NUMBER",
                "GH_HOST=$GH_HOST",
                "GH_OWNER=$GH_OWNER",
                "GH_REPO_NAME=$GH_REPO_NAME",
                "GH_REPO=$GH_REPO",
                "BASE=$BASE_REF",
                "HEAD=$HEAD_REF",
                "DESC=$AGENT_DESC",
                "LEGACY=<base>",
            ]
        )
        rendered = rf.render_prompt(
            template,
            base_ref_for_review="reviewflow_base__develop",
            pr_url="https://github.com/acme/repo/pull/1",
            pr_number=1,
            gh_host="github.com",
            gh_owner="acme",
            gh_repo_name="repo",
            gh_repo="acme/repo",
            agent_desc="hello",
            head_ref="HEAD",
        )
        self.assertNotIn("$PR_URL", rendered)
        self.assertNotIn("$PR_NUMBER", rendered)
        self.assertNotIn("$GH_HOST", rendered)
        self.assertNotIn("$GH_OWNER", rendered)
        self.assertNotIn("$GH_REPO_NAME", rendered)
        self.assertNotIn("$GH_REPO", rendered)
        self.assertNotIn("$BASE_REF", rendered)
        self.assertNotIn("$HEAD_REF", rendered)
        self.assertNotIn("$AGENT_DESC", rendered)
        self.assertNotIn("<base>", rendered)

        self.assertIn("PR_URL=https://github.com/acme/repo/pull/1", rendered)
        self.assertIn("PR_NUMBER=1", rendered)
        self.assertIn("GH_HOST=github.com", rendered)
        self.assertIn("GH_OWNER=acme", rendered)
        self.assertIn("GH_REPO_NAME=repo", rendered)
        self.assertIn("GH_REPO=acme/repo", rendered)
        self.assertIn("BASE=reviewflow_base__develop", rendered)
        self.assertIn("DESC=hello", rendered)

    def test_render_prompt_supports_extra_vars_without_touching_agent_desc(self) -> None:
        template = "X=$X\nDESC=$AGENT_DESC\n"
        rendered = rf.render_prompt(
            template,
            base_ref_for_review="reviewflow_base__develop",
            pr_url="https://github.com/acme/repo/pull/1",
            pr_number=1,
            gh_host="github.com",
            gh_owner="acme",
            gh_repo_name="repo",
            gh_repo="acme/repo",
            agent_desc="contains $X literally",
            head_ref="HEAD",
            extra_vars={"X": "value"},
        )
        self.assertIn("X=value", rendered)
        self.assertIn("DESC=contains $X literally", rendered)


class CodexConfigTests(unittest.TestCase):
    def test_codex_flags_from_base_config(self) -> None:
        cfg = ROOT / ".tmp_test_codex_config.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        'model = "gpt-5.2"',
                        'sandbox_mode = "danger-full-access"',
                        'web_search = "live"',
                        'model_reasoning_effort = "high"',
                        'plan_mode_reasoning_effort = "xhigh"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            flags, meta = rf.codex_flags_from_base_config(base_config_path=cfg)
            self.assertTrue(meta.get("loaded"))
            self.assertIn("-m", flags)
            self.assertIn("gpt-5.2", flags)
            self.assertIn("--sandbox", flags)
            self.assertIn("danger-full-access", flags)
            self.assertIn("--search", flags)
            self.assertIn('model_reasoning_effort="high"', flags)
            self.assertIn('plan_mode_reasoning_effort="xhigh"', flags)
        finally:
            cfg.unlink(missing_ok=True)

    def test_load_reviewflow_codex_defaults_parses_toml(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_codex.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[codex]",
                        'model = "gpt-5.3-codex-spark"',
                        'model_reasoning_effort = "low"',
                        'plan_mode_reasoning_effort = "medium"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            defaults, meta = rf.load_reviewflow_codex_defaults(config_path=cfg)
            self.assertTrue(meta.get("loaded"))
            self.assertEqual(defaults["model"], "gpt-5.3-codex-spark")
            self.assertEqual(defaults["model_reasoning_effort"], "low")
            self.assertEqual(defaults["plan_mode_reasoning_effort"], "medium")
        finally:
            cfg.unlink(missing_ok=True)

    def test_resolve_codex_flags_precedence(self) -> None:
        base = ROOT / ".tmp_test_base_codex.toml"
        rf_cfg = ROOT / ".tmp_test_reviewflow_codex2.toml"
        try:
            base.write_text(
                "\n".join(
                    [
                        'model = "base-model"',
                        'sandbox_mode = "danger-full-access"',
                        'web_search = "live"',
                        'model_reasoning_effort = "high"',
                        'plan_mode_reasoning_effort = "xhigh"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            rf_cfg.write_text(
                "\n".join(
                    [
                        "[codex]",
                        'model = "rf-model"',
                        'model_reasoning_effort = "low"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            flags, meta = rf.resolve_codex_flags(
                base_config_path=base,
                reviewflow_config_path=rf_cfg,
                cli_model="cli-model",
                cli_effort=None,
                cli_plan_effort="medium",
            )
            self.assertIn("-m", flags)
            self.assertIn("cli-model", flags)
            # model_reasoning_effort should come from reviewflow.toml if CLI is unset.
            self.assertIn('model_reasoning_effort="low"', flags)
            # plan_mode_reasoning_effort should come from CLI.
            self.assertIn('plan_mode_reasoning_effort="medium"', flags)
            self.assertEqual(meta["resolved"]["model_source"], "cli")
            self.assertEqual(meta["resolved"]["model_reasoning_effort_source"], "reviewflow.toml")
            self.assertEqual(meta["resolved"]["plan_mode_reasoning_effort_source"], "cli")
        finally:
            base.unlink(missing_ok=True)
            rf_cfg.unlink(missing_ok=True)

    def test_load_reviewflow_multipass_defaults_parses_toml(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_multipass.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[multipass]",
                        "enabled = false",
                        "max_steps = 7",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            mp, meta = rf.load_reviewflow_multipass_defaults(config_path=cfg)
            self.assertTrue(meta.get("loaded"))
            self.assertEqual(mp["enabled"], False)
            self.assertEqual(mp["max_steps"], 7)
        finally:
            cfg.unlink(missing_ok=True)


class GhConfigCopyTests(unittest.TestCase):
    def test_prepare_gh_config_for_codex_copies_directory(self) -> None:
        tmp = ROOT / ".tmp_test_gh_config"
        dst_root = ROOT / ".tmp_test_dst_root"
        try:
            tmp.mkdir(parents=True, exist_ok=True)
            dst_root.mkdir(parents=True, exist_ok=True)
            (tmp / "hosts.yml").write_text("github.com:\n  user: test\n", encoding="utf-8")

            old = os.environ.get("GH_CONFIG_DIR")
            os.environ["GH_CONFIG_DIR"] = str(tmp)
            try:
                dst = rf.prepare_gh_config_for_codex(dst_root=dst_root)
            finally:
                if old is None:
                    os.environ.pop("GH_CONFIG_DIR", None)
                else:
                    os.environ["GH_CONFIG_DIR"] = old

            self.assertIsNotNone(dst)
            assert dst is not None
            self.assertTrue((dst / "hosts.yml").is_file())
        finally:
            shutil.rmtree(dst_root, ignore_errors=True)
            shutil.rmtree(tmp, ignore_errors=True)


class JiraConfigCopyTests(unittest.TestCase):
    def test_prepare_jira_config_for_codex_copies_config_file(self) -> None:
        tmp = ROOT / ".tmp_test_jira_config"
        dst_root = ROOT / ".tmp_test_repo_jira"
        try:
            tmp.mkdir(parents=True, exist_ok=True)
            dst_root.mkdir(parents=True, exist_ok=True)
            cfg = tmp / ".config.yml"
            cfg.write_text("endpoint: https://example.atlassian.net\n", encoding="utf-8")

            old = os.environ.get("JIRA_CONFIG_FILE")
            os.environ["JIRA_CONFIG_FILE"] = str(cfg)
            try:
                dst = rf.prepare_jira_config_for_codex(dst_root=dst_root)
            finally:
                if old is None:
                    os.environ.pop("JIRA_CONFIG_FILE", None)
                else:
                    os.environ["JIRA_CONFIG_FILE"] = old

            self.assertIsNotNone(dst)
            assert dst is not None
            self.assertTrue(dst.is_file())
            self.assertEqual(dst.name, ".config.yml")
        finally:
            shutil.rmtree(dst_root, ignore_errors=True)
            shutil.rmtree(tmp, ignore_errors=True)


class PromptTemplateTests(unittest.TestCase):
    def test_templates_do_not_require_tmp_writes(self) -> None:
        normal = (ROOT / "prompts" / "mrereview_gh_local.md").read_text(encoding="utf-8")
        big = (ROOT / "prompts" / "mrereview_gh_local_big.md").read_text(encoding="utf-8")
        followup = (ROOT / "prompts" / "mrereview_gh_local_followup.md").read_text(
            encoding="utf-8"
        )
        big_followup = (ROOT / "prompts" / "mrereview_gh_local_big_followup.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("mkdir -p /tmp/reviewflow_pr_", normal)
        self.assertNotIn("mkdir -p /tmp/reviewflow_pr_", big)
        self.assertNotIn("mkdir -p /tmp/reviewflow_pr_", followup)
        self.assertNotIn("mkdir -p /tmp/reviewflow_pr_", big_followup)
        self.assertNotIn('/tmp/reviewflow_pr_${PR_NUMBER}', normal)
        self.assertNotIn('/tmp/reviewflow_pr_${PR_NUMBER}', big)
        self.assertNotIn('/tmp/reviewflow_pr_${PR_NUMBER}', followup)
        self.assertNotIn('/tmp/reviewflow_pr_${PR_NUMBER}', big_followup)

    def test_templates_are_agentic_and_do_not_reference_prefetch_context(self) -> None:
        normal = (ROOT / "prompts" / "mrereview_gh_local.md").read_text(encoding="utf-8")
        big = (ROOT / "prompts" / "mrereview_gh_local_big.md").read_text(encoding="utf-8")
        followup = (ROOT / "prompts" / "mrereview_gh_local_followup.md").read_text(
            encoding="utf-8"
        )
        big_followup = (ROOT / "prompts" / "mrereview_gh_local_big_followup.md").read_text(
            encoding="utf-8"
        )
        for text in (normal, big, followup, big_followup):
            self.assertNotIn(".reviewflow/context", text)
            self.assertIn("gh pr view", text)
            self.assertIn("./rf-jira", text)
            self.assertIn("issue view", text)
            self.assertIn("REVIEWFLOW_CRAWL_ALLOW_HOSTS", text)
            self.assertIn("./rf-fetch-url", text)

    def test_templates_do_not_reference_ch_wrapper(self) -> None:
        normal = (ROOT / "prompts" / "mrereview_gh_local.md").read_text(encoding="utf-8")
        big = (ROOT / "prompts" / "mrereview_gh_local_big.md").read_text(encoding="utf-8")
        followup = (ROOT / "prompts" / "mrereview_gh_local_followup.md").read_text(
            encoding="utf-8"
        )
        big_followup = (ROOT / "prompts" / "mrereview_gh_local_big_followup.md").read_text(
            encoding="utf-8"
        )
        big_plan = (ROOT / "prompts" / "mrereview_gh_local_big_plan.md").read_text(
            encoding="utf-8"
        )
        big_step = (ROOT / "prompts" / "mrereview_gh_local_big_step.md").read_text(
            encoding="utf-8"
        )
        big_synth = (ROOT / "prompts" / "mrereview_gh_local_big_synth.md").read_text(
            encoding="utf-8"
        )
        default = (ROOT / "prompts" / "default.md").read_text(encoding="utf-8")
        for text in (normal, big, followup, big_followup, big_plan, big_step, big_synth, default):
            self.assertNotIn("`./ch", text)
            self.assertNotIn("./ch ", text)
            self.assertNotIn("fall back to `rg`", text)
            self.assertIn("ChunkHound MCP", text)
            self.assertIn("search", text)
            self.assertIn("code_research", text)
            self.assertIn("chunkhound.search", text)
            self.assertIn("chunkhound.code_research", text)

    def test_zip_template_discourages_file_writes_and_fenced_output(self) -> None:
        zip_template = (ROOT / "prompts" / "mrereview_zip.md").read_text(encoding="utf-8")
        self.assertIn("Do not create, edit, or move any files.", zip_template)
        self.assertIn("Reviewflow will save your final response", zip_template)
        self.assertIn("Do not wrap the response in a fenced code block.", zip_template)
        self.assertNotIn("Write the final result to:", zip_template)
        self.assertNotIn("```markdown", zip_template)

    def test_review_templates_treat_url_crawl_as_best_effort_enrichment(self) -> None:
        prompt_paths = [
            ROOT / "prompts" / "mrereview_gh_local.md",
            ROOT / "prompts" / "mrereview_gh_local_big.md",
            ROOT / "prompts" / "mrereview_gh_local_followup.md",
            ROOT / "prompts" / "mrereview_gh_local_big_followup.md",
            ROOT / "prompts" / "mrereview_gh_local_big_plan.md",
        ]
        for path in prompt_paths:
            text = path.read_text(encoding="utf-8")
            self.assertIn("required `gh`/`jira` read fails", text)
            self.assertIn("human-authored PR/Jira text only", text)
            self.assertIn("machine-generated metadata URLs", text)
            self.assertIn("Skip GitHub URLs that point to the current PR", text)
            self.assertIn("Do not ABORT on URL-only fetch failures", text)


class MultipassPlanParsingTests(unittest.TestCase):
    def test_parse_multipass_plan_json_accepts_steps(self) -> None:
        text = "\n".join(
            [
                "### Plan JSON",
                "```json",
                json.dumps(
                    {
                        "abort": False,
                        "abort_reason": None,
                        "jira_keys": ["ABC-1"],
                        "steps": [
                            {"id": "01", "title": "T", "focus": "F"},
                        ],
                    }
                ),
                "```",
                "",
            ]
        )
        plan = rf.parse_multipass_plan_json(text)
        self.assertFalse(plan["abort"])
        self.assertEqual(len(plan["steps"]), 1)

    def test_parse_multipass_plan_json_accepts_abort(self) -> None:
        text = "\n".join(
            [
                "```json",
                json.dumps({"abort": True, "abort_reason": "no jira", "jira_keys": []}),
                "```",
            ]
        )
        plan = rf.parse_multipass_plan_json(text)
        self.assertTrue(plan["abort"])


class HistoricalReviewsTests(unittest.TestCase):
    class _FakeTty(StringIO):
        def isatty(self) -> bool:
            return True

    def test_extract_decision_from_markdown_normalizes_common_values(self) -> None:
        md = "\n".join(
            [
                "**Summary**: x",
                "**Decision**: REQUEST CHANGES",
                "",
            ]
        )
        self.assertEqual(rf.extract_decision_from_markdown(md), "REQUEST CHANGES")

        md2 = "**Decision**: [approve]\n"
        self.assertEqual(rf.extract_decision_from_markdown(md2), "APPROVE")

    def test_scan_completed_sessions_for_pr_filters_and_sorts(self) -> None:
        root = ROOT / ".tmp_test_review_sandboxes"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)

            pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=1)

            s1 = root / "s1"
            s1.mkdir()
            (s1 / "review.md").write_text("**Decision**: REJECT\n", encoding="utf-8")
            (s1 / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s1",
                        "status": "done",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 1,
                        "created_at": "2026-03-03T00:00:00+00:00",
                        "completed_at": "2026-03-03T01:00:00+00:00",
                        "head_sha": "1111111111111111111111111111111111111111",
                        "paths": {"review_md": str(s1 / "review.md")},
                    }
                ),
                encoding="utf-8",
            )

            s2 = root / "s2"
            s2.mkdir()
            (s2 / "review.md").write_text("**Decision**: APPROVE\n", encoding="utf-8")
            (s2 / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s2",
                        "status": "done",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 1,
                        "created_at": "2026-03-04T00:00:00+00:00",
                        "completed_at": "2026-03-04T01:00:00+00:00",
                        "review_head_sha": "2222222222222222222222222222222222222222",
                        "paths": {"review_md": str(s2 / "review.md")},
                    }
                ),
                encoding="utf-8",
            )

            s3 = root / "s3"
            s3.mkdir()
            (s3 / "review.md").write_text("**Decision**: APPROVE\n", encoding="utf-8")
            (s3 / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s3",
                        "status": "running",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 1,
                        "created_at": "2026-03-05T00:00:00+00:00",
                        "paths": {"review_md": str(s3 / "review.md")},
                    }
                ),
                encoding="utf-8",
            )

            sessions = rf.scan_completed_sessions_for_pr(sandbox_root=root, pr=pr)
            self.assertEqual([s.session_id for s in sessions], ["s2", "s1"])
            self.assertEqual(sessions[0].decision, "APPROVE")
            self.assertEqual(sessions[1].decision, "REJECT")
            self.assertEqual(sessions[0].review_head_sha, "2222222222222222222222222222222222222222")
            self.assertEqual(sessions[1].review_head_sha, "1111111111111111111111111111111111111111")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_print_historical_sessions_remains_flat_and_plain(self) -> None:
        sessions = [
            rf.HistoricalReviewSession(
                session_id="s2",
                session_dir=ROOT / "s2",
                review_md_path=ROOT / "s2" / "review.md",
                created_at="2026-03-04T00:00:00+00:00",
                completed_at="2026-03-04T01:00:00+00:00",
                decision="APPROVE",
                review_head_sha="2222222222222222222222222222222222222222",
            )
        ]
        stdout = StringIO()
        with mock.patch("sys.stdout", stdout):
            rf._print_historical_sessions(sessions)
        rendered = stdout.getvalue()
        self.assertIn("01  2026-03-04T01:00:00+00:00  APPROVE  s2", rendered)
        self.assertNotIn("head ", rendered.lower())
        self.assertNotIn("\x1b[", rendered)

    def test_choose_historical_session_tty_groups_by_sha_and_preserves_global_indices(self) -> None:
        sessions = [
            rf.HistoricalReviewSession(
                session_id="newest-a",
                session_dir=ROOT / "newest-a",
                review_md_path=ROOT / "newest-a" / "review.md",
                created_at="2026-03-05T00:00:00+00:00",
                completed_at="2026-03-05T01:00:00+00:00",
                decision="APPROVE",
                review_head_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            ),
            rf.HistoricalReviewSession(
                session_id="older-a",
                session_dir=ROOT / "older-a",
                review_md_path=ROOT / "older-a" / "review.md",
                created_at="2026-03-04T00:00:00+00:00",
                completed_at="2026-03-04T01:00:00+00:00",
                decision="REJECT",
                review_head_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            ),
            rf.HistoricalReviewSession(
                session_id="only-b",
                session_dir=ROOT / "only-b",
                review_md_path=ROOT / "only-b" / "review.md",
                created_at="2026-03-03T00:00:00+00:00",
                completed_at="2026-03-03T01:00:00+00:00",
                decision="REQUEST CHANGES",
                review_head_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            ),
            rf.HistoricalReviewSession(
                session_id="unknown",
                session_dir=ROOT / "unknown",
                review_md_path=ROOT / "unknown" / "review.md",
                created_at="2026-03-02T00:00:00+00:00",
                completed_at="2026-03-02T01:00:00+00:00",
                decision="APPROVE",
                review_head_sha=None,
            ),
        ]
        stdin = self._FakeTty("3\n")
        stderr = self._FakeTty()
        with (
            mock.patch("sys.stdin", stdin),
            mock.patch("sys.stderr", stderr),
            mock.patch.dict(os.environ, {"TERM": "dumb"}, clear=False),
        ):
            selected = rf._choose_historical_session_tty(sessions)

        assert selected is not None
        self.assertEqual(selected.session_id, "only-b")
        rendered = stderr.getvalue()
        self.assertIn("head aaaaaaaaaaaa (2 review(s))", rendered)
        self.assertIn("head bbbbbbbbbbbb (1 review)", rendered)
        self.assertIn("head unknown (1 review)", rendered)
        self.assertIn("  1) 2026-03-05T01:00:00+00:00  APPROVE", rendered)
        self.assertIn("  2) 2026-03-04T01:00:00+00:00  REJECT", rendered)
        self.assertIn("  3) 2026-03-03T01:00:00+00:00  REQUEST CHANGES", rendered)
        self.assertIn("  4) 2026-03-02T01:00:00+00:00  APPROVE", rendered)
        self.assertNotIn("\x1b[", rendered)

    def test_choose_historical_session_tty_colorizes_group_headers_when_enabled(self) -> None:
        sessions = [
            rf.HistoricalReviewSession(
                session_id="s1",
                session_dir=ROOT / "s1",
                review_md_path=ROOT / "s1" / "review.md",
                created_at="2026-03-05T00:00:00+00:00",
                completed_at="2026-03-05T01:00:00+00:00",
                decision="APPROVE",
                review_head_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            ),
            rf.HistoricalReviewSession(
                session_id="s2",
                session_dir=ROOT / "s2",
                review_md_path=ROOT / "s2" / "review.md",
                created_at="2026-03-04T00:00:00+00:00",
                completed_at="2026-03-04T01:00:00+00:00",
                decision="REJECT",
                review_head_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            ),
        ]
        stdin = self._FakeTty("n\n")
        stderr = self._FakeTty()
        with (
            mock.patch("sys.stdin", stdin),
            mock.patch("sys.stderr", stderr),
            mock.patch.dict(os.environ, {"TERM": "xterm-256color"}, clear=True),
        ):
            selected = rf._choose_historical_session_tty(sessions)

        self.assertIsNone(selected)
        rendered = stderr.getvalue()
        self.assertIn("\x1b[", rendered)
        self.assertIn("head aaaaaaaaaaaa (1 review)", rendered)
        self.assertIn("head bbbbbbbbbbbb (1 review)", rendered)

    def test_choose_historical_session_tty_disables_color_when_no_color_set(self) -> None:
        sessions = [
            rf.HistoricalReviewSession(
                session_id="s1",
                session_dir=ROOT / "s1",
                review_md_path=ROOT / "s1" / "review.md",
                created_at="2026-03-05T00:00:00+00:00",
                completed_at="2026-03-05T01:00:00+00:00",
                decision="APPROVE",
                review_head_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            )
        ]
        stdin = self._FakeTty("n\n")
        stderr = self._FakeTty()
        with (
            mock.patch("sys.stdin", stdin),
            mock.patch("sys.stderr", stderr),
            mock.patch.dict(os.environ, {"TERM": "xterm-256color", "NO_COLOR": "1"}, clear=True),
        ):
            selected = rf._choose_historical_session_tty(sessions)

        self.assertIsNone(selected)
        rendered = stderr.getvalue()
        self.assertNotIn("\x1b[", rendered)
        self.assertIn("head aaaaaaaaaaaa (1 review)", rendered)

    def test_scan_interactive_review_sessions_filters_and_sorts(self) -> None:
        root = ROOT / ".tmp_test_interactive_review_sandboxes"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)

            s1 = root / "s1"
            s1.mkdir()
            (s1 / "review.md").write_text("**Decision**: REJECT\n", encoding="utf-8")
            (s1 / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s1",
                        "status": "done",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 1,
                        "created_at": "2026-03-03T00:00:00+00:00",
                        "completed_at": "2026-03-03T01:00:00+00:00",
                        "decision": "REJECT",
                        "paths": {"review_md": str(s1 / "review.md")},
                        "codex": {"resume": {"command": "cd /tmp/s1 && codex resume s1"}},
                    }
                ),
                encoding="utf-8",
            )

            s2 = root / "s2"
            s2.mkdir()
            (s2 / "review.md").write_text("**Decision**: APPROVE\n", encoding="utf-8")
            (s2 / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s2",
                        "status": "done",
                        "host": "github.com",
                        "owner": "beta",
                        "repo": "app",
                        "number": 7,
                        "created_at": "2026-03-04T00:00:00+00:00",
                        "completed_at": "2026-03-04T01:00:00+00:00",
                        "decision": "APPROVE",
                        "paths": {"review_md": str(s2 / "review.md")},
                        "codex": {"resume": {"command": "cd /tmp/s2 && codex resume s2"}},
                    }
                ),
                encoding="utf-8",
            )

            s3 = root / "s3"
            s3.mkdir()
            (s3 / "review.md").write_text("**Decision**: APPROVE\n", encoding="utf-8")
            (s3 / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s3",
                        "status": "done",
                        "host": "github.com",
                        "owner": "gamma",
                        "repo": "web",
                        "number": 9,
                        "created_at": "2026-03-05T00:00:00+00:00",
                        "completed_at": "2026-03-05T01:00:00+00:00",
                        "paths": {"review_md": str(s3 / "review.md")},
                    }
                ),
                encoding="utf-8",
            )

            s4 = root / "s4"
            s4.mkdir()
            (s4 / "review.md").write_text("**Decision**: APPROVE\n", encoding="utf-8")
            (s4 / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s4",
                        "status": "running",
                        "host": "github.com",
                        "owner": "delta",
                        "repo": "ops",
                        "number": 5,
                        "created_at": "2026-03-06T00:00:00+00:00",
                        "paths": {"review_md": str(s4 / "review.md")},
                        "codex": {"resume": {"command": "cd /tmp/s4 && codex resume s4"}},
                    }
                ),
                encoding="utf-8",
            )

            sessions = rf.scan_interactive_review_sessions(sandbox_root=root)
            self.assertEqual([s.session_id for s in sessions], ["s2", "s1"])
            self.assertEqual(sessions[0].repo_slug, "beta/app#7")
            self.assertEqual(sessions[0].resume_command, "cd /tmp/s2 && codex resume s2")
        finally:
            shutil.rmtree(root, ignore_errors=True)


class InteractiveFlowTests(unittest.TestCase):
    class _FakeTty(StringIO):
        def isatty(self) -> bool:
            return True

    def test_interactive_session_resume_is_poisoned_when_log_contains_session_dir_message(self) -> None:
        root = ROOT / ".tmp_test_interactive_poisoned_detect"
        fake_home = ROOT / ".tmp_test_interactive_poisoned_detect_home"
        try:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(fake_home, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            (fake_home / ".codex" / "sessions" / "2026" / "03" / "04").mkdir(parents=True, exist_ok=True)

            s1 = root / "s1"
            s1.mkdir()
            (s1 / "review.md").write_text("**Decision**: REQUEST CHANGES\n", encoding="utf-8")
            (s1 / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s1",
                        "status": "done",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 1,
                        "created_at": "2026-03-04T00:00:00+00:00",
                        "completed_at": "2026-03-04T01:00:00+00:00",
                        "paths": {"review_md": str(s1 / "review.md")},
                        "codex": {
                            "resume": {
                                "command": "cd /tmp/s1 && codex resume old-session",
                                "session_id": "old-session",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            session_log = (
                fake_home
                / ".codex"
                / "sessions"
                / "2026"
                / "03"
                / "04"
                / "rollout-test-old-session.jsonl"
            )
            session_log.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "session_meta",
                                "payload": {"id": "old-session", "originator": "codex_exec"},
                            }
                        ),
                        json.dumps(
                            {
                                "type": "response_item",
                                "payload": {
                                    "type": "message",
                                    "role": "user",
                                    "content": [
                                        {"type": "input_text", "text": str(s1.resolve())},
                                    ],
                                },
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            session = rf.scan_interactive_review_sessions(sandbox_root=root)[0]
            self.assertTrue(
                rf._interactive_session_resume_is_poisoned(
                    session=session,
                    codex_root=fake_home / ".codex",
                )
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(fake_home, ignore_errors=True)

    def test_interactive_flow_runs_selected_resume_command(self) -> None:
        root = ROOT / ".tmp_test_interactive_flow_root"
        cfg = ROOT / ".tmp_test_interactive_flow_cfg.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text("{}", encoding="utf-8")

            s1 = root / "s1"
            s1.mkdir()
            (s1 / "repo").mkdir()
            (s1 / "work").mkdir()
            (s1 / "review.md").write_text("**Decision**: APPROVE\n", encoding="utf-8")
            (s1 / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s1",
                        "status": "done",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 1,
                        "created_at": "2026-03-04T00:00:00+00:00",
                        "completed_at": "2026-03-04T01:00:00+00:00",
                        "decision": "APPROVE",
                        "paths": {
                            "repo_dir": str(s1 / "repo"),
                            "work_dir": str(s1 / "work"),
                            "review_md": str(s1 / "review.md"),
                        },
                        "codex": {"resume": {"command": "cd /tmp/s1 && codex resume s1", "session_id": "s1"}},
                    }
                ),
                encoding="utf-8",
            )

            paths = rf.ReviewflowPaths(
                sandbox_root=root,
                cache_root=ROOT / ".tmp_test_interactive_flow_cache",
                review_chunkhound_config=cfg,
                main_chunkhound_config=cfg,
            )
            stdin = self._FakeTty("1\n")
            stderr = self._FakeTty()

            with (
                mock.patch.object(rf, "chunkhound_env", return_value={"CHUNKHOUND_EMBEDDING__API_KEY": "test-key"}),
                mock.patch.object(rf, "run_interactive_resume_command", return_value=7) as runner,
            ):
                rc = rf.interactive_flow(argparse.Namespace(), paths=paths, stdin=stdin, stderr=stderr)

            self.assertEqual(rc, 7)
            runner.assert_called_once()
            self.assertIn("codex resume", runner.call_args.args[0])
            self.assertIn("s1", runner.call_args.args[0])
            self.assertNotIn(f"--add-dir {root}", runner.call_args.args[0])
            self.assertEqual(runner.call_args.kwargs["env"]["CHUNKHOUND_EMBEDDING__API_KEY"], "test-key")
            self.assertIn(str(s1 / "review.md"), stderr.getvalue())
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_interactive_flow_filters_sessions_by_pr_url(self) -> None:
        root = ROOT / ".tmp_test_interactive_flow_target_root"
        cfg = ROOT / ".tmp_test_interactive_flow_target_cfg.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text("{}", encoding="utf-8")

            s1 = root / "s1"
            s1.mkdir()
            (s1 / "repo").mkdir()
            (s1 / "work").mkdir()
            (s1 / "review.md").write_text("**Decision**: APPROVE\n", encoding="utf-8")
            (s1 / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s1",
                        "status": "done",
                        "host": "github.com",
                        "owner": "Academy-Plus",
                        "repo": "ssa-lms",
                        "number": 86,
                        "created_at": "2026-03-04T00:00:00+00:00",
                        "completed_at": "2026-03-04T01:00:00+00:00",
                        "decision": "APPROVE",
                        "paths": {
                            "repo_dir": str(s1 / "repo"),
                            "work_dir": str(s1 / "work"),
                            "review_md": str(s1 / "review.md"),
                        },
                        "codex": {"resume": {"command": "cd /tmp/s1 && codex resume s1", "session_id": "s1"}},
                    }
                ),
                encoding="utf-8",
            )

            s2 = root / "s2"
            s2.mkdir()
            (s2 / "repo").mkdir()
            (s2 / "work").mkdir()
            (s2 / "review.md").write_text("**Decision**: REJECT\n", encoding="utf-8")
            (s2 / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s2",
                        "status": "done",
                        "host": "github.com",
                        "owner": "Academy-Plus",
                        "repo": "ssa-lms",
                        "number": 75,
                        "created_at": "2026-03-05T00:00:00+00:00",
                        "completed_at": "2026-03-05T01:00:00+00:00",
                        "decision": "REJECT",
                        "paths": {
                            "repo_dir": str(s2 / "repo"),
                            "work_dir": str(s2 / "work"),
                            "review_md": str(s2 / "review.md"),
                        },
                        "codex": {"resume": {"command": "cd /tmp/s2 && codex resume s2", "session_id": "s2"}},
                    }
                ),
                encoding="utf-8",
            )

            paths = rf.ReviewflowPaths(
                sandbox_root=root,
                cache_root=ROOT / ".tmp_test_interactive_flow_target_cache",
                review_chunkhound_config=cfg,
                main_chunkhound_config=cfg,
            )
            stdin = self._FakeTty("1\n")
            stderr = self._FakeTty()
            args = argparse.Namespace(target="https://github.com/Academy-Plus/ssa-lms/pull/86")

            with (
                mock.patch.object(rf, "chunkhound_env", return_value={"CHUNKHOUND_EMBEDDING__API_KEY": "test-key"}),
                mock.patch.object(rf, "run_interactive_resume_command", return_value=9) as runner,
            ):
                rc = rf.interactive_flow(args, paths=paths, stdin=stdin, stderr=stderr)

            self.assertEqual(rc, 9)
            runner.assert_called_once()
            self.assertIn("codex resume", runner.call_args.args[0])
            self.assertIn("s1", runner.call_args.args[0])
            self.assertNotIn("s2", stderr.getvalue())
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_interactive_flow_prefers_latest_followup_artifact_for_preview(self) -> None:
        root = ROOT / ".tmp_test_interactive_followup_root"
        cfg = ROOT / ".tmp_test_interactive_followup_cfg.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text("{}", encoding="utf-8")

            s1 = root / "s1"
            s1.mkdir()
            (s1 / "repo").mkdir()
            (s1 / "work").mkdir()
            review_md = s1 / "review.md"
            review_md.write_text("**Decision**: REQUEST CHANGES\n", encoding="utf-8")
            followups = s1 / "followups"
            followups.mkdir(parents=True, exist_ok=True)
            latest_followup = followups / "followup-20260310-010101.md"
            latest_followup.write_text("**Decision**: APPROVE\n", encoding="utf-8")
            (s1 / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s1",
                        "status": "done",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 1,
                        "created_at": "2026-03-04T00:00:00+00:00",
                        "completed_at": "2026-03-04T01:00:00+00:00",
                        "decision": "APPROVE",
                        "paths": {
                            "repo_dir": str(s1 / "repo"),
                            "work_dir": str(s1 / "work"),
                            "review_md": str(review_md),
                        },
                        "followups": [
                            {
                                "completed_at": "2026-03-10T01:01:01+00:00",
                                "output_path": str(latest_followup),
                                "decision": "APPROVE",
                            }
                        ],
                        "codex": {"resume": {"command": "cd /tmp/s1 && codex resume s1", "session_id": "s1"}},
                    }
                ),
                encoding="utf-8",
            )

            paths = rf.ReviewflowPaths(
                sandbox_root=root,
                cache_root=ROOT / ".tmp_test_interactive_followup_cache",
                review_chunkhound_config=cfg,
                main_chunkhound_config=cfg,
            )
            stdin = self._FakeTty("1\n")
            stderr = self._FakeTty()

            with (
                mock.patch.object(rf, "chunkhound_env", return_value={"CHUNKHOUND_EMBEDDING__API_KEY": "test-key"}),
                mock.patch.object(rf, "run_interactive_resume_command", return_value=0),
            ):
                rc = rf.interactive_flow(argparse.Namespace(), paths=paths, stdin=stdin, stderr=stderr)

            self.assertEqual(rc, 0)
            self.assertIn(str(latest_followup), stderr.getvalue())
            self.assertNotIn(f"Latest review artifact: {review_md}", stderr.getvalue())
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_interactive_flow_errors_for_poisoned_resume(self) -> None:
        root = ROOT / ".tmp_test_interactive_poisoned_error_root"
        cfg = ROOT / ".tmp_test_interactive_poisoned_error_cfg.json"
        fake_home = ROOT / ".tmp_test_interactive_poisoned_error_home"
        try:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(fake_home, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text("{}", encoding="utf-8")
            (fake_home / ".codex" / "sessions" / "2026" / "03" / "04").mkdir(parents=True, exist_ok=True)

            s1 = root / "s1"
            s1.mkdir()
            (s1 / "repo").mkdir()
            (s1 / "work").mkdir()
            review_md = s1 / "review.md"
            review_md.write_text("**Decision**: REQUEST CHANGES\nArtifact body.\n", encoding="utf-8")
            (s1 / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s1",
                        "status": "done",
                        "host": "github.com",
                        "owner": "Academy-Plus",
                        "repo": "ssa-lms",
                        "number": 86,
                        "created_at": "2026-03-04T00:00:00+00:00",
                        "completed_at": "2026-03-04T01:00:00+00:00",
                        "decision": "REQUEST CHANGES",
                        "paths": {
                            "repo_dir": str(s1 / "repo"),
                            "work_dir": str(s1 / "work"),
                            "review_md": str(review_md),
                        },
                        "codex": {
                            "resume": {
                                "command": "cd /tmp/s1 && codex resume old-session",
                                "session_id": "old-session",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            session_log = (
                fake_home
                / ".codex"
                / "sessions"
                / "2026"
                / "03"
                / "04"
                / "rollout-test-old-session.jsonl"
            )
            session_log.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "session_meta",
                                "payload": {"id": "old-session", "originator": "codex_exec"},
                            }
                        ),
                        json.dumps(
                            {
                                "type": "response_item",
                                "payload": {
                                    "type": "message",
                                    "role": "user",
                                    "content": [
                                        {"type": "input_text", "text": str(s1.resolve())},
                                    ],
                                },
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            paths = rf.ReviewflowPaths(
                sandbox_root=root,
                cache_root=ROOT / ".tmp_test_interactive_poisoned_error_cache",
                review_chunkhound_config=cfg,
                main_chunkhound_config=cfg,
            )
            stdin = self._FakeTty("1\n")
            stderr = self._FakeTty()

            with (
                mock.patch.object(rf, "chunkhound_env", return_value={"CHUNKHOUND_EMBEDDING__API_KEY": "test-key"}),
                mock.patch.object(rf, "real_user_home_dir", return_value=fake_home),
                mock.patch.object(rf, "run_interactive_resume_command") as resume_runner,
            ):
                with self.assertRaises(rf.ReviewflowError) as ctx:
                    rf.interactive_flow(argparse.Namespace(), paths=paths, stdin=stdin, stderr=stderr)

            self.assertIn("saved Codex session is corrupted", str(ctx.exception))
            self.assertIn(str(review_md), str(ctx.exception))
            resume_runner.assert_not_called()
            self.assertNotIn("Continuing", stderr.getvalue())
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(fake_home, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_interactive_flow_errors_for_historically_poisoned_session_even_if_resume_id_changed(self) -> None:
        root = ROOT / ".tmp_test_interactive_historical_poison_root"
        cfg = ROOT / ".tmp_test_interactive_historical_poison_cfg.json"
        fake_home = ROOT / ".tmp_test_interactive_historical_poison_home"
        try:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(fake_home, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text("{}", encoding="utf-8")
            day_dir = fake_home / ".codex" / "sessions" / "2026" / "03" / "04"
            day_dir.mkdir(parents=True, exist_ok=True)

            s1 = root / "s1"
            s1.mkdir()
            (s1 / "repo").mkdir()
            (s1 / "work").mkdir()
            review_md = s1 / "review.md"
            review_md.write_text("**Decision**: APPROVE\n", encoding="utf-8")
            (s1 / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s1",
                        "status": "done",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 1,
                        "created_at": "2026-03-04T00:00:00+00:00",
                        "completed_at": "2026-03-04T01:00:00+00:00",
                        "decision": "APPROVE",
                        "paths": {
                            "repo_dir": str(s1 / "repo"),
                            "work_dir": str(s1 / "work"),
                            "review_md": str(review_md),
                        },
                        "codex": {
                            "resume": {
                                "command": "cd /tmp/s1 && codex resume new-session",
                                "session_id": "new-session",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            (day_dir / "rollout-old.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "session_meta",
                                "payload": {"id": "old-session", "originator": "codex_exec"},
                            }
                        ),
                        json.dumps(
                            {
                                "type": "response_item",
                                "payload": {
                                    "type": "message",
                                    "role": "user",
                                    "content": [{"type": "input_text", "text": str(s1.resolve())}],
                                },
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (day_dir / "rollout-new.jsonl").write_text(
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {"id": "new-session", "originator": "codex_cli_rs"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            paths = rf.ReviewflowPaths(
                sandbox_root=root,
                cache_root=ROOT / ".tmp_test_interactive_historical_poison_cache",
                review_chunkhound_config=cfg,
                main_chunkhound_config=cfg,
            )
            stdin = self._FakeTty("1\n")
            stderr = self._FakeTty()

            with (
                mock.patch.object(rf, "chunkhound_env", return_value={"CHUNKHOUND_EMBEDDING__API_KEY": "test-key"}),
                mock.patch.object(rf, "real_user_home_dir", return_value=fake_home),
                mock.patch.object(rf, "run_interactive_resume_command") as resume_runner,
            ):
                with self.assertRaises(rf.ReviewflowError) as ctx:
                    rf.interactive_flow(argparse.Namespace(), paths=paths, stdin=stdin, stderr=stderr)

            self.assertIn("saved Codex session is corrupted", str(ctx.exception))
            self.assertIn(str(review_md), str(ctx.exception))
            resume_runner.assert_not_called()
            self.assertNotIn("Continuing", stderr.getvalue())
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(fake_home, ignore_errors=True)
            cfg.unlink(missing_ok=True)


class ZipSelectionTests(unittest.TestCase):
    def test_build_zip_input_display_lines_formats_plain_and_markdown(self) -> None:
        inputs = [
            {
                "session_id": "s1",
                "kind": "review",
                "path": "/tmp/s1/review.md",
                "completed_at": "2026-03-04T01:00:00+00:00",
                "decision": "APPROVE",
                "target_head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            }
        ]
        plain = rf.build_zip_input_display_lines(inputs_meta=inputs)
        markdown = rf.build_zip_input_display_lines(inputs_meta=inputs, markdown=True)
        self.assertEqual(
            plain,
            ["- s1 [review] APPROVE 2026-03-04T01:00:00+00:00 head bbbbbbbbbbbb /tmp/s1/review.md"],
        )
        self.assertEqual(
            markdown,
            [
                "- `s1` • `review` • APPROVE • 2026-03-04T01:00:00+00:00 • head `bbbbbbbbbbbb` • `/tmp/s1/review.md`"
            ],
        )

    def test_append_zip_inputs_provenance_appends_section(self) -> None:
        md = ROOT / ".tmp_test_zip_append.md"
        try:
            md.write_text(
                "**Summary**: ok\n**Strengths**: x\n**Issues**:\n- **Critical**: none\n**Reusability**: none\n**Decision**: APPROVE\n",
                encoding="utf-8",
            )
            rf.append_zip_inputs_provenance(
                markdown_path=md,
                inputs_meta=[
                    {
                        "session_id": "s1",
                        "kind": "review",
                        "path": "/tmp/s1/review.md",
                        "completed_at": "2026-03-04T01:00:00+00:00",
                        "decision": "APPROVE",
                        "target_head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    }
                ],
            )
            text = md.read_text(encoding="utf-8")
            self.assertIn("## Inputs Processed", text)
            self.assertIn("`s1`", text)
            self.assertIn("head `bbbbbbbbbbbb`", text)
        finally:
            md.unlink(missing_ok=True)

    def test_select_zip_sources_for_pr_head_filters_sha_and_picks_newest_per_session(self) -> None:
        root = ROOT / ".tmp_test_zip_root"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)

            pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=9)
            head_sha = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

            # Session s1: done but targets a different head SHA => excluded.
            s1 = root / "s1"
            s1.mkdir()
            (s1 / "review.md").write_text("**Decision**: REJECT\n", encoding="utf-8")
            (s1 / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s1",
                        "status": "done",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 9,
                        "head_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                        "created_at": "2026-03-03T00:00:00+00:00",
                        "completed_at": "2026-03-03T01:00:00+00:00",
                        "paths": {"review_md": str(s1 / "review.md")},
                    }
                ),
                encoding="utf-8",
            )

            # Session s2: done, review targets head_sha => included (older).
            s2 = root / "s2"
            s2.mkdir()
            (s2 / "review.md").write_text("**Decision**: APPROVE\n", encoding="utf-8")
            (s2 / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s2",
                        "status": "done",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 9,
                        "head_sha": head_sha,
                        "created_at": "2026-03-04T00:00:00+00:00",
                        "completed_at": "2026-03-04T01:00:00+00:00",
                        "paths": {"review_md": str(s2 / "review.md")},
                    }
                ),
                encoding="utf-8",
            )

            # Session s3: done, review targets head_sha but followup targets head_sha and is newer => followup selected.
            s3 = root / "s3"
            s3.mkdir()
            (s3 / "review.md").write_text("**Decision**: REQUEST CHANGES\n", encoding="utf-8")
            followups = s3 / "followups"
            followups.mkdir(parents=True, exist_ok=True)
            fu_path = followups / "followup-20260305-000000.md"
            fu_path.write_text("**Decision**: APPROVE\n", encoding="utf-8")
            (s3 / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s3",
                        "status": "done",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 9,
                        "head_sha": head_sha,
                        "created_at": "2026-03-04T02:00:00+00:00",
                        "completed_at": "2026-03-04T02:30:00+00:00",
                        "paths": {"review_md": str(s3 / "review.md")},
                        "followups": [
                            {
                                "completed_at": "2026-03-05T00:00:00+00:00",
                                "output_path": str(fu_path),
                                "head_sha_after": head_sha,
                                "decision": "APPROVE",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            # Session s4: done, review targets head_sha but newer followup targets different SHA => review should still be selected.
            s4 = root / "s4"
            s4.mkdir()
            (s4 / "review.md").write_text("**Decision**: APPROVE\n", encoding="utf-8")
            followups4 = s4 / "followups"
            followups4.mkdir(parents=True, exist_ok=True)
            fu4_path = followups4 / "followup-20260306-000000.md"
            fu4_path.write_text("**Decision**: REJECT\n", encoding="utf-8")
            (s4 / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s4",
                        "status": "done",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 9,
                        "head_sha": head_sha,
                        "created_at": "2026-03-06T00:00:00+00:00",
                        "completed_at": "2026-03-06T00:10:00+00:00",
                        "paths": {"review_md": str(s4 / "review.md")},
                        "followups": [
                            {
                                "completed_at": "2026-03-06T01:00:00+00:00",
                                "output_path": str(fu4_path),
                                "head_sha_after": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            sources = rf.select_zip_sources_for_pr_head(sandbox_root=root, pr=pr, head_sha=head_sha)
            self.assertEqual([s.session_id for s in sources], ["s4", "s3", "s2"])
            self.assertEqual(sources[0].kind, "review")
            self.assertEqual(sources[1].kind, "followup")
            self.assertEqual(sources[1].decision, "APPROVE")
        finally:
            shutil.rmtree(root, ignore_errors=True)


class ZipFlowTests(unittest.TestCase):
    def test_zip_flow_logs_selected_inputs_and_appends_provenance(self) -> None:
        root = ROOT / ".tmp_test_zip_flow_root"
        cfg = ROOT / ".tmp_test_zip_flow_cfg.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text("{}", encoding="utf-8")

            host_session = root / "host-session"
            host_session.mkdir(parents=True, exist_ok=True)
            host_repo = host_session / "repo"
            host_repo.mkdir()
            host_work = host_session / "work"
            host_work.mkdir()
            host_review = host_session / "review.md"
            host_review.write_text("**Decision**: APPROVE\n", encoding="utf-8")
            (host_session / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "host-session",
                        "status": "done",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 9,
                        "base_ref": "main",
                        "base_ref_for_review": "reviewflow_base__main",
                        "paths": {
                            "repo_dir": str(host_repo),
                            "work_dir": str(host_work),
                            "review_md": str(host_review),
                        },
                    }
                ),
                encoding="utf-8",
            )

            other_session = root / "other-session"
            other_session.mkdir(parents=True, exist_ok=True)
            other_artifact = other_session / "followup.md"
            other_artifact.write_text("**Decision**: REQUEST CHANGES\n", encoding="utf-8")

            sources = [
                rf.ZipSourceArtifact(
                    session_id="host-session",
                    session_dir=host_session,
                    kind="review",
                    artifact_path=host_review,
                    completed_at="2026-03-04T01:00:00+00:00",
                    decision="APPROVE",
                    target_head_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                ),
                rf.ZipSourceArtifact(
                    session_id="other-session",
                    session_dir=other_session,
                    kind="followup",
                    artifact_path=other_artifact,
                    completed_at="2026-03-05T01:00:00+00:00",
                    decision="REQUEST CHANGES",
                    target_head_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                ),
            ]

            args = argparse.Namespace(
                pr_url="https://github.com/acme/repo/pull/9",
                codex_model=None,
                codex_effort=None,
                codex_plan_effort=None,
                ui="off",
                verbosity="normal",
                no_stream=False,
            )
            paths = rf.ReviewflowPaths(
                sandbox_root=root,
                cache_root=ROOT / ".tmp_test_zip_flow_cache",
                review_chunkhound_config=cfg,
                main_chunkhound_config=cfg,
            )
            stdout = StringIO()
            stderr = StringIO()
            prompts: list[str] = []

            def fake_run_cmd(cmd: list[str], **kwargs: object) -> mock.Mock:
                if cmd[:2] == ["gh", "api"]:
                    return mock.Mock(
                        stdout=json.dumps(
                            {
                                "head": {"sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
                                "title": "Zip PR",
                            }
                        )
                    )
                raise AssertionError(f"unexpected command: {cmd}")

            def fake_run_codex_exec(**kwargs: object) -> rf.CodexRunResult:
                prompt = kwargs["prompt"]
                assert isinstance(prompt, str)
                prompts.append(prompt)
                output_path = kwargs["output_path"]
                assert isinstance(output_path, Path)
                output_path.write_text(
                    "\n".join(
                        [
                            "```markdown",
                            "**Summary**: ok",
                            "**Strengths**: x",
                            "**Issues**:",
                            "- **Critical**: none",
                            "- **Major**: none",
                            "- **Minor**: none",
                            "**Reusability**: none",
                            "**Decision**: APPROVE",
                            "```",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                return rf.CodexRunResult(resume=None)

            with (
                mock.patch.object(rf, "require_gh_auth"),
                mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd),
                mock.patch.object(rf, "select_zip_sources_for_pr_head", return_value=sources),
                mock.patch.object(rf, "resolve_codex_flags", return_value=([], {"resolved": {}})),
                mock.patch.object(rf, "codex_mcp_overrides_for_reviewflow", return_value=[]),
                mock.patch.object(rf, "run_codex_exec", side_effect=fake_run_codex_exec),
                mock.patch("sys.stdout", stdout),
                mock.patch("sys.stderr", stderr),
            ):
                rc = rf.zip_flow(args, paths=paths)

            self.assertEqual(rc, 0)
            self.assertIn("zip selected 2 input artifact(s) for HEAD bbbbbbbbbbbb", stderr.getvalue())
            self.assertIn(
                "zip input host-session [review] APPROVE 2026-03-04T01:00:00+00:00 head bbbbbbbbbbbb",
                stderr.getvalue(),
            )
            self.assertIn(
                "zip input other-session [followup] REQUEST CHANGES 2026-03-05T01:00:00+00:00 head bbbbbbbbbbbb",
                stderr.getvalue(),
            )
            self.assertEqual(len(prompts), 1)
            self.assertIn("Do not create, edit, or move any files.", prompts[0])
            self.assertIn("Do not wrap the response in a fenced code block.", prompts[0])
            self.assertNotIn("Write the final result to:", prompts[0])
            self.assertNotIn("```markdown", prompts[0])

            output_md = Path(stdout.getvalue().strip())
            text = output_md.read_text(encoding="utf-8")
            self.assertFalse(text.startswith("```markdown"))
            self.assertIn("## Inputs Processed", text)
            self.assertIn("`host-session`", text)
            self.assertIn("`other-session`", text)
            self.assertIn("head `bbbbbbbbbbbb`", text)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)


class ResumeTargetResolutionTests(unittest.TestCase):
    def test_resolve_resume_target_prefers_resumable_multipass(self) -> None:
        root = ROOT / ".tmp_test_resume_target_root"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)

            s_done = root / "s_done"
            s_done.mkdir()
            (s_done / "review.md").write_text("**Decision**: APPROVE\n", encoding="utf-8")
            (s_done / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s_done",
                        "status": "done",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 4,
                        "created_at": "2026-03-03T00:00:00+00:00",
                        "completed_at": "2026-03-03T01:00:00+00:00",
                        "paths": {"review_md": str(s_done / "review.md")},
                    }
                ),
                encoding="utf-8",
            )

            s_err = root / "s_err"
            s_err.mkdir()
            (s_err / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s_err",
                        "status": "error",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 4,
                        "created_at": "2026-03-04T00:00:00+00:00",
                        "failed_at": "2026-03-04T01:00:00+00:00",
                        "multipass": {"enabled": True},
                        "notes": {"no_index": False},
                        "paths": {"session_dir": str(s_err)},
                    }
                ),
                encoding="utf-8",
            )

            pr_url = "https://github.com/acme/repo/pull/4"
            sid, action = rf.resolve_resume_target(pr_url, sandbox_root=root, from_phase="auto")
            self.assertEqual(sid, "s_err")
            self.assertEqual(action, "resume")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_resolve_resume_target_uses_followup_when_only_done_and_from_auto(self) -> None:
        root = ROOT / ".tmp_test_resume_target_root2"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)

            s_done = root / "s_done"
            s_done.mkdir()
            (s_done / "review.md").write_text("**Decision**: APPROVE\n", encoding="utf-8")
            (s_done / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s_done",
                        "status": "done",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 4,
                        "created_at": "2026-03-03T00:00:00+00:00",
                        "completed_at": "2026-03-03T01:00:00+00:00",
                        "paths": {"review_md": str(s_done / "review.md")},
                    }
                ),
                encoding="utf-8",
            )

            pr_url = "github.com/acme/repo/pull/4"
            sid, action = rf.resolve_resume_target(pr_url, sandbox_root=root, from_phase="auto")
            self.assertEqual(sid, "s_done")
            self.assertEqual(action, "followup")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_resolve_resume_target_errors_when_from_not_auto_and_only_done(self) -> None:
        root = ROOT / ".tmp_test_resume_target_root3"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)

            s_done = root / "s_done"
            s_done.mkdir()
            (s_done / "review.md").write_text("**Decision**: APPROVE\n", encoding="utf-8")
            (s_done / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s_done",
                        "status": "done",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 4,
                        "created_at": "2026-03-03T00:00:00+00:00",
                        "completed_at": "2026-03-03T01:00:00+00:00",
                        "paths": {"review_md": str(s_done / "review.md")},
                    }
                ),
                encoding="utf-8",
            )

            pr_url = "https://github.com/acme/repo/pull/4"
            with self.assertRaises(rf.ReviewflowError):
                _ = rf.resolve_resume_target(pr_url, sandbox_root=root, from_phase="steps")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_resolve_resume_target_rejects_path_like_non_pr_target(self) -> None:
        with self.assertRaises(rf.ReviewflowError):
            _ = rf.resolve_resume_target("foo/bar", sandbox_root=ROOT, from_phase="auto")


class CrawlConfigTests(unittest.TestCase):
    def test_load_crawl_config_parses_toml(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[crawl]",
                        'allow_hosts = ["github.com", "api.github.com", "academyplus.atlassian.net"]',
                        "timeout_seconds = 21",
                        "max_bytes = 12345",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            crawl, meta = rf.load_crawl_config(config_path=cfg)
            self.assertTrue(meta.get("loaded"))
            self.assertIn("academyplus.atlassian.net", crawl.allow_hosts)
            self.assertEqual(crawl.timeout_seconds, 21)
            self.assertEqual(crawl.max_bytes, 12345)
        finally:
            cfg.unlink(missing_ok=True)

    def test_load_crawl_config_defaults_when_missing(self) -> None:
        missing = ROOT / ".tmp_test_reviewflow_missing.toml"
        missing.unlink(missing_ok=True)
        crawl, meta = rf.load_crawl_config(config_path=missing)
        self.assertFalse(meta.get("loaded"))
        self.assertIn("github.com", crawl.allow_hosts)
        self.assertIn("api.github.com", crawl.allow_hosts)


class RfFetchUrlTests(unittest.TestCase):
    def _write_fake_gh(self, *, bin_dir: Path) -> Path:
        gh = bin_dir / "gh"
        gh.write_text(
            """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

log_path = os.environ.get("GH_LOG", "").strip()
if log_path:
    with Path(log_path).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(sys.argv[1:]) + "\\n")
sys.stdout.write(os.environ.get("GH_STDOUT", ""))
sys.stderr.write(os.environ.get("GH_STDERR", ""))
raise SystemExit(int(os.environ.get("GH_EXIT", "0") or "0"))
""",
            encoding="utf-8",
        )
        gh.chmod(0o755)
        return gh

    def _run_rf_fetch(
        self,
        *,
        script_path: Path,
        url: str,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        env = dict(os.environ)
        env.update(extra_env or {})
        return subprocess.run(
            [sys.executable, str(script_path), url],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=script_path.parent,
            check=False,
        )

    def test_write_rf_fetch_url_creates_executable_helper(self) -> None:
        repo = ROOT / ".tmp_test_repo_rf_fetch"
        try:
            shutil.rmtree(repo, ignore_errors=True)
            repo.mkdir(parents=True, exist_ok=True)
            cfg = rf.CrawlConfig(allow_hosts=("github.com",), timeout_seconds=20, max_bytes=2000000)
            path = rf.write_rf_fetch_url(repo_dir=repo, cfg=cfg)
            self.assertTrue(path.is_file())
            self.assertTrue(os.access(path, os.X_OK))
            text = path.read_text(encoding="utf-8")
            self.assertIn("REVIEWFLOW_CRAWL_ALLOW_HOSTS", text)
            self.assertIn("host not allowlisted", text)
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_rf_fetch_url_routes_private_github_api_urls_through_gh(self) -> None:
        repo = ROOT / ".tmp_test_repo_rf_fetch_api"
        bin_dir = ROOT / ".tmp_test_repo_rf_fetch_api_bin"
        log_path = ROOT / ".tmp_test_repo_rf_fetch_api.log"
        try:
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(bin_dir, ignore_errors=True)
            log_path.unlink(missing_ok=True)
            repo.mkdir(parents=True, exist_ok=True)
            bin_dir.mkdir(parents=True, exist_ok=True)
            cfg = rf.CrawlConfig(
                allow_hosts=("github.com", "api.github.com"),
                timeout_seconds=20,
                max_bytes=2000000,
            )
            path = rf.write_rf_fetch_url(repo_dir=repo, cfg=cfg)
            self._write_fake_gh(bin_dir=bin_dir)
            result = self._run_rf_fetch(
                script_path=path,
                url="https://api.github.com/repos/acme/repo/pulls/9",
                extra_env={
                    "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
                    "GH_CONFIG_DIR": str(repo / "gh_cfg"),
                    "GH_LOG": str(log_path),
                    "GH_STDOUT": '{"number": 9}\n',
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
            self.assertEqual(result.stdout.decode("utf-8"), '{"number": 9}\n')
            calls = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(calls, [["api", "--hostname", "github.com", "repos/acme/repo/pulls/9"]])
        finally:
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(bin_dir, ignore_errors=True)
            log_path.unlink(missing_ok=True)

    def test_rf_fetch_url_maps_github_html_urls_to_gh_api(self) -> None:
        repo = ROOT / ".tmp_test_repo_rf_fetch_html"
        bin_dir = ROOT / ".tmp_test_repo_rf_fetch_html_bin"
        log_path = ROOT / ".tmp_test_repo_rf_fetch_html.log"
        try:
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(bin_dir, ignore_errors=True)
            log_path.unlink(missing_ok=True)
            repo.mkdir(parents=True, exist_ok=True)
            bin_dir.mkdir(parents=True, exist_ok=True)
            cfg = rf.CrawlConfig(allow_hosts=("github.com",), timeout_seconds=20, max_bytes=2000000)
            path = rf.write_rf_fetch_url(repo_dir=repo, cfg=cfg)
            self._write_fake_gh(bin_dir=bin_dir)

            cases = [
                (
                    "https://github.com/acme/repo/pull/9",
                    ["api", "--hostname", "github.com", "repos/acme/repo/pulls/9"],
                ),
                (
                    "https://github.com/acme/repo/pull/9/files",
                    ["api", "--hostname", "github.com", "repos/acme/repo/pulls/9"],
                ),
                (
                    "https://github.com/acme/repo/issues/7",
                    ["api", "--hostname", "github.com", "repos/acme/repo/issues/7"],
                ),
                (
                    "https://github.com/acme/repo/pull/9#issuecomment-1234",
                    ["api", "--hostname", "github.com", "repos/acme/repo/issues/comments/1234"],
                ),
                (
                    "https://github.com/acme/repo/pull/9/files#discussion_r5678",
                    ["api", "--hostname", "github.com", "repos/acme/repo/pulls/comments/5678"],
                ),
                (
                    "https://github.com/acme/repo/pull/9#pullrequestreview-4321",
                    ["api", "--hostname", "github.com", "repos/acme/repo/pulls/9/reviews/4321"],
                ),
            ]

            for url, expected in cases:
                log_path.unlink(missing_ok=True)
                result = self._run_rf_fetch(
                    script_path=path,
                    url=url,
                    extra_env={
                        "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
                        "GH_CONFIG_DIR": str(repo / "gh_cfg"),
                        "GH_LOG": str(log_path),
                        "GH_STDOUT": '{"ok": true}\n',
                    },
                )
                self.assertEqual(result.returncode, 0, url)
                calls = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
                self.assertEqual(calls[-1], expected, url)
        finally:
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(bin_dir, ignore_errors=True)
            log_path.unlink(missing_ok=True)

    def test_rf_fetch_url_rejects_unsupported_github_url_shape(self) -> None:
        repo = ROOT / ".tmp_test_repo_rf_fetch_unsupported"
        try:
            shutil.rmtree(repo, ignore_errors=True)
            repo.mkdir(parents=True, exist_ok=True)
            cfg = rf.CrawlConfig(allow_hosts=("github.com",), timeout_seconds=20, max_bytes=2000000)
            path = rf.write_rf_fetch_url(repo_dir=repo, cfg=cfg)
            result = self._run_rf_fetch(
                script_path=path,
                url="https://github.com/acme/repo/commit/abcdef",
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn(
                "rf-fetch-url: unsupported GitHub URL shape",
                result.stderr.decode("utf-8", errors="replace"),
            )
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_rf_fetch_url_uses_direct_http_for_non_github_hosts(self) -> None:
        repo = ROOT / ".tmp_test_repo_rf_fetch_http"
        bin_dir = ROOT / ".tmp_test_repo_rf_fetch_http_bin"
        log_path = ROOT / ".tmp_test_repo_rf_fetch_http.log"
        server = None
        thread = None
        try:
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(bin_dir, ignore_errors=True)
            log_path.unlink(missing_ok=True)
            repo.mkdir(parents=True, exist_ok=True)
            bin_dir.mkdir(parents=True, exist_ok=True)
            cfg = rf.CrawlConfig(allow_hosts=("127.0.0.1",), timeout_seconds=20, max_bytes=2000000)
            path = rf.write_rf_fetch_url(repo_dir=repo, cfg=cfg)
            self._write_fake_gh(bin_dir=bin_dir)

            class Handler(http.server.BaseHTTPRequestHandler):
                def do_GET(self) -> None:  # noqa: N802
                    body = b"hello from direct fetch"
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, format: str, *args: object) -> None:
                    return

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}/doc"
            result = self._run_rf_fetch(
                script_path=path,
                url=url,
                extra_env={
                    "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
                    "GH_LOG": str(log_path),
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
            self.assertEqual(result.stdout.decode("utf-8"), "hello from direct fetch")
            self.assertFalse(log_path.exists(), "gh should not be invoked for non-GitHub hosts")
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()
            if thread is not None:
                thread.join(timeout=2)
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(bin_dir, ignore_errors=True)
            log_path.unlink(missing_ok=True)


class RfJiraTests(unittest.TestCase):
    def test_write_rf_jira_creates_executable_helper(self) -> None:
        repo = ROOT / ".tmp_test_repo_rf_jira"
        try:
            shutil.rmtree(repo, ignore_errors=True)
            repo.mkdir(parents=True, exist_ok=True)
            path = rf.write_rf_jira(repo_dir=repo)
            self.assertTrue(path.is_file())
            self.assertTrue(os.access(path, os.X_OK))
            text = path.read_text(encoding="utf-8")
            self.assertIn("JIRA_CONFIG_FILE", text)
            self.assertIn("NETRC", text)
            self.assertIn("pwd.getpwuid", text)
        finally:
            shutil.rmtree(repo, ignore_errors=True)


class CodexCommandTests(unittest.TestCase):
    def test_build_codex_exec_cmd_includes_bypass_flag(self) -> None:
        repo = ROOT
        cmd = rf.build_codex_exec_cmd(
            repo_dir=repo,
            codex_flags=["-m", "gpt-5.2"],
            codex_config_overrides=[],
            review_md_path=ROOT / ".tmp_test_review.md",
            prompt="hello",
        )
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", cmd)
        self.assertIn("shell_environment_policy.inherit=all", cmd)

    def test_build_codex_exec_cmd_injects_chunkhound_mcp_with_startup_timeout(self) -> None:
        repo = ROOT
        ch_cfg = ROOT / ".tmp_test_chunkhound_env.json"
        overrides = rf.codex_mcp_overrides_for_reviewflow(
            enable_sandbox_chunkhound=True,
            sandbox_repo_dir=repo,
            chunkhound_config_path=ch_cfg,
            paths=rf.DEFAULT_PATHS,
        )
        ch_args_entry = next(o for o in overrides if o.startswith("mcp_servers.chunkhound.args="))
        ch_args = json.loads(ch_args_entry.split("=", 1)[1])
        self.assertNotIn("--exclude", ch_args)
        self.assertNotIn("--db", ch_args)
        self.assertNotIn("--database-provider", ch_args)
        self.assertIn("--config", ch_args)
        self.assertIn(str(ch_cfg), ch_args)
        cmd = rf.build_codex_exec_cmd(
            repo_dir=repo,
            codex_flags=["-m", "gpt-5.2"],
            codex_config_overrides=overrides,
            review_md_path=ROOT / ".tmp_test_review.md",
            prompt="hello",
        )
        joined = " ".join(cmd)
        self.assertIn("mcp_servers.chunkhound.startup_timeout_sec=20", joined)
        self.assertIn("mcp_servers.chunk-hound.enabled=false", joined)
        self.assertNotIn("--no-daemon", joined)


class GitStatsTests(unittest.TestCase):
    def test_compute_pr_stats_on_tiny_repo(self) -> None:
        repo = ROOT / ".tmp_test_git_repo"
        try:
            repo.mkdir(parents=True, exist_ok=True)
            rf.run_cmd(["git", "-C", str(repo), "init"], check=True)
            rf.run_cmd(["git", "-C", str(repo), "config", "user.email", "test@example.com"])
            rf.run_cmd(["git", "-C", str(repo), "config", "user.name", "Test User"])

            (repo / "a.txt").write_text("one\n", encoding="utf-8")
            rf.run_cmd(["git", "-C", str(repo), "add", "a.txt"])
            rf.run_cmd(["git", "-C", str(repo), "commit", "-m", "base"])
            base_sha = rf.run_cmd(["git", "-C", str(repo), "rev-parse", "HEAD"]).stdout.strip()

            (repo / "a.txt").write_text("one\ntwo\n", encoding="utf-8")
            (repo / "b.txt").write_text("b\n", encoding="utf-8")
            rf.run_cmd(["git", "-C", str(repo), "add", "a.txt", "b.txt"])
            rf.run_cmd(["git", "-C", str(repo), "commit", "-m", "change"])

            stats = rf.compute_pr_stats(repo_dir=repo, base_ref=base_sha, head_ref="HEAD")
            self.assertEqual(stats["changed_files"], 2)
            self.assertGreater(stats["additions"], 0)
            self.assertGreaterEqual(stats["deletions"], 0)
            self.assertGreater(stats["changed_lines"], 0)
        finally:
            shutil.rmtree(repo, ignore_errors=True)


class TuiDashboardTests(unittest.TestCase):
    def test_parser_accepts_if_reviewed_and_followup_flags(self) -> None:
        p = rf.build_parser()
        args = p.parse_args(
            [
                "pr",
                "https://github.com/acme/repo/pull/1",
                "--if-reviewed",
                "latest",
            ]
        )
        self.assertEqual(args.if_reviewed, "latest")

        args2 = p.parse_args(["followup", "session-123", "--no-update"])
        self.assertEqual(args2.session_id, "session-123")
        self.assertTrue(args2.no_update)

        args3 = p.parse_args(["interactive", "https://github.com/acme/repo/pull/1"])
        self.assertEqual(args3.target, "https://github.com/acme/repo/pull/1")

    def test_parser_accepts_zip_flags(self) -> None:
        p = rf.build_parser()
        args = p.parse_args(
            [
                "zip",
                "https://github.com/acme/repo/pull/9",
                "--codex-model",
                "gpt-5.3-codex-spark",
                "--codex-effort",
                "low",
                "--ui",
                "off",
                "--verbosity",
                "debug",
            ]
        )
        self.assertEqual(args.pr_url, "https://github.com/acme/repo/pull/9")
        self.assertEqual(args.codex_model, "gpt-5.3-codex-spark")
        self.assertEqual(args.codex_effort, "low")
        self.assertEqual(args.ui, "off")
        self.assertEqual(args.verbosity, "debug")

    def test_parser_accepts_ui_and_verbosity_flags(self) -> None:
        p = rf.build_parser()
        args = p.parse_args(
            [
                "pr",
                "https://github.com/acme/repo/pull/1",
                "--ui",
                "off",
                "--verbosity",
                "debug",
            ]
        )
        self.assertEqual(args.ui, "off")
        self.assertEqual(args.verbosity, "debug")

        args2 = p.parse_args(["resume", "session-123", "--ui", "auto", "--verbosity", "normal"])
        self.assertEqual(args2.ui, "auto")
        self.assertEqual(args2.verbosity, "normal")

        args3 = p.parse_args(
            [
                "ui-preview",
                "session-123",
                "--watch",
                "--width",
                "100",
                "--height",
                "30",
                "--verbosity",
                "debug",
                "--no-color",
            ]
        )
        self.assertEqual(args3.session_id, "session-123")
        self.assertTrue(args3.watch)
        self.assertEqual(args3.width, 100)
        self.assertEqual(args3.height, 30)
        self.assertEqual(args3.verbosity, "debug")
        self.assertTrue(args3.no_color)

    def test_dashboard_renders_multipass_step_x_of_y(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "acme-repo-pr1-20260304-000000-abcd",
            "created_at": "2026-03-04T00:00:00+00:00",
            "status": "running",
            "phase": "codex_step_03",
            "phases": {"codex_step_03": {"status": "running"}},
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
            "multipass": {
                "enabled": True,
                "current": {
                    "stage": "step",
                    "step_index": 3,
                    "step_count": 7,
                    "step_title": "Authentication checks",
                },
            },
        }
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=["x"],
            codex_tail=["y"],
            no_stream=False,
            width=120,
            height=40,
        )
        joined = "\n".join(lines)
        self.assertIn("step 3/7", joined)
        self.assertIn("Authentication checks", joined)

    def test_dashboard_hides_tails_in_quiet(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "session_id": "s",
            "created_at": "2026-03-04T00:00:00+00:00",
            "status": "running",
            "phase": "init",
            "phases": {},
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        quiet_lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.quiet, show_help=False),
            chunkhound_tail=["x"],
            codex_tail=["y"],
            no_stream=False,
            width=120,
            height=30,
        )
        self.assertNotIn("chunkhound tail:", "\n".join(quiet_lines))

    def test_dashboard_status_bar_packs_right_side_without_ellipsis(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "s",
            "created_at": "",  # stable elapsed="?"
            "status": "running",
            "phase": "checkout_pr",
            "phases": {"checkout_pr": {"status": "running"}},
            "base_ref": "main",
            "head_sha": "0123456789abcdef0123456789abcdef01234567",
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        for w in (80, 120):
            lines = rui.build_dashboard_lines(
                meta=meta,
                snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
                chunkhound_tail=[],
                codex_tail=[],
                no_stream=False,
                width=w,
                height=25,
            )
            bar = lines[0]
            self.assertIn("RUN", bar)
            self.assertIn("checkout_pr", bar)
            self.assertIn("v:normal", bar)

    def test_dashboard_narrow_layout_uses_single_column_sections(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "s",
            "created_at": "",
            "status": "running",
            "phase": "checkout_pr",
            "phases": {"checkout_pr": {"status": "running"}},
            "base_ref": "main",
            "head_sha": "0123456789abcdef0123456789abcdef01234567",
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=[],
            codex_tail=[],
            no_stream=False,
            width=90,
            height=30,
        )
        joined = "\n".join(lines)
        self.assertIn("─ Phases", joined)
        self.assertIn("─ Context", joined)
        self.assertNotIn(" │ ", joined)

    def test_dashboard_color_mode_emits_ansi_and_preserves_width_math(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "s",
            "created_at": "2026-03-04T00:00:00+00:00",
            "status": "running",
            "phase": "checkout_pr",
            "phases": {"checkout_pr": {"status": "running"}, "resolve_pr_meta": {"status": "done"}},
            "base_ref": "main",
            "head_sha": "0123456789abcdef0123456789abcdef01234567",
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        width = 80
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=[],
            codex_tail=[],
            no_stream=False,
            width=width,
            height=25,
            color=True,
        )
        joined = "\n".join(lines)
        self.assertIn("\x1b[", joined)

        ansi = re.compile(r"\x1b\[[0-9;]*m")
        for line in lines:
            visible = ansi.sub("", line)
            self.assertLessEqual(len(visible), width)

    def test_dashboard_renders_zip_inputs_in_context(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 9,
            "title": "Zip PR",
            "session_id": "zip-run",
            "created_at": "2026-03-04T00:00:00+00:00",
            "status": "running",
            "phase": "codex_zip",
            "kind": "zip",
            "phases": {"codex_zip": {"status": "running"}},
            "head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "zip": {
                "display_inputs": [
                    "- host-session [review] APPROVE 2026-03-04T01:00:00+00:00 head bbbbbbbbbbbb /tmp/host/review.md",
                    "- other-session [followup] REQUEST CHANGES 2026-03-05T01:00:00+00:00 head bbbbbbbbbbbb /tmp/other/followup.md",
                ],
                "selected_input_count": 2,
            },
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=[],
            codex_tail=["cx-1"],
            no_stream=False,
            width=120,
            height=35,
            color=False,
        )
        joined = "\n".join(lines)
        self.assertIn("Zip:", joined)
        self.assertIn("Inputs:", joined)
        self.assertIn("host-session [review] APPROVE", joined)
        self.assertIn("other-session [followup] REQUEST CHANGES", joined)

    def test_dashboard_footer_is_dimmed_in_color_mode(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "s",
            "created_at": "",
            "status": "running",
            "phase": "checkout_pr",
            "phases": {"checkout_pr": {"status": "running"}},
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=["ch-1"],
            codex_tail=["cx-1"],
            no_stream=False,
            width=120,
            height=25,
            color=True,
        )
        # Footer/help is styled as ANSI "dim" to keep focus on logs.
        self.assertIn("\x1b[2m", lines[-1])
        # Footer uses a subtle full-width bar framing.
        self.assertIn("┄", lines[-1])

    def test_dashboard_strips_hash_delimiter_from_codex_tail(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "session_id": "s",
            "created_at": "",
            "status": "running",
            "phase": "checkout_pr",
            "phases": {"checkout_pr": {"status": "running"}},
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=[],
            codex_tail=["line-1", "####", "line-2"],
            no_stream=False,
            width=120,
            height=25,
            color=False,
        )
        joined = "\n".join(lines)
        self.assertIn("line-1", joined)
        self.assertIn("line-2", joined)
        self.assertNotIn("\n####\n", "\n" + joined + "\n")

    def test_dashboard_expands_logs_when_vertical_space_available(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "s",
            "created_at": "",
            "status": "running",
            "phase": "checkout_pr",
            "phases": {"checkout_pr": {"status": "running"}},
            "base_ref": "main",
            "head_sha": "0123456789abcdef0123456789abcdef01234567",
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        ch_tail = [f"ch-{i}" for i in range(1, 201)]
        cx_tail = [f"cx-{i}" for i in range(1, 401)]
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=ch_tail,
            codex_tail=cx_tail,
            no_stream=False,
            width=160,
            height=80,
            color=False,
        )
        joined = "\n".join(lines)
        m1 = re.search(r"ChunkHound \(last (\d+)\):", joined)
        m2 = re.search(r"Codex \(last (\d+)\):", joined)
        self.assertIsNotNone(m1)
        self.assertIsNotNone(m2)
        assert m1 is not None
        assert m2 is not None
        self.assertGreater(int(m1.group(1)), 8)
        self.assertGreater(int(m2.group(1)), 12)

    def test_dashboard_small_terminal_still_shows_log_lines(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "session_id": "s",
            "created_at": "",
            "status": "running",
            "phase": "checkout_pr",
            "phases": {"checkout_pr": {"status": "running"}},
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        ch_tail = [f"ch-{i}" for i in range(1, 201)]
        cx_tail = [f"cx-{i}" for i in range(1, 401)]
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=ch_tail,
            codex_tail=cx_tail,
            no_stream=False,
            width=160,
            height=18,
            color=False,
        )
        joined = "\n".join(lines)
        # Ensure at least one actual tail line makes it on screen at short heights.
        self.assertIn("Codex (last ", joined)
        self.assertIn("cx-400", joined)


class TuiPrintFinalMarkdownTests(unittest.TestCase):
    class _FakeTtyStderr:
        def __init__(self, *, is_tty: bool) -> None:
            self._is_tty = bool(is_tty)
            self._parts: list[str] = []

        def isatty(self) -> bool:  # pragma: no cover
            return self._is_tty

        def write(self, s: str) -> int:  # pragma: no cover
            self._parts.append(str(s))
            return len(s)

        def flush(self) -> None:  # pragma: no cover
            return None

        def getvalue(self) -> str:
            return "".join(self._parts)

    def test_maybe_print_markdown_after_tui_noop_when_ui_disabled(self) -> None:
        md = ROOT / ".tmp_test_tui_print.md"
        try:
            md.write_text("hello", encoding="utf-8")
            err = self._FakeTtyStderr(is_tty=True)
            rf.maybe_print_markdown_after_tui(ui_enabled=False, stderr=err, markdown_path=md)
            self.assertEqual(err.getvalue(), "")
        finally:
            md.unlink(missing_ok=True)

    def test_maybe_print_markdown_after_tui_prints_clear_and_full_body(self) -> None:
        md = ROOT / ".tmp_test_tui_print2.md"
        try:
            md.write_text("line1\nline2", encoding="utf-8")  # no trailing newline
            err = self._FakeTtyStderr(is_tty=True)
            rf.maybe_print_markdown_after_tui(ui_enabled=True, stderr=err, markdown_path=md)
            self.assertEqual(err.getvalue(), "\x1b[2J\x1b[H" + "line1\nline2\n")
        finally:
            md.unlink(missing_ok=True)

    def test_maybe_print_markdown_after_tui_noop_when_stderr_not_tty(self) -> None:
        md = ROOT / ".tmp_test_tui_print3.md"
        try:
            md.write_text("hello\n", encoding="utf-8")
            err = self._FakeTtyStderr(is_tty=False)
            rf.maybe_print_markdown_after_tui(ui_enabled=True, stderr=err, markdown_path=md)
            self.assertEqual(err.getvalue(), "")
        finally:
            md.unlink(missing_ok=True)


class LocalMarkdownNormalizationTests(unittest.TestCase):
    def test_normalize_markdown_local_refs_rewrites_local_links_and_paths(self) -> None:
        session_dir = ROOT / ".tmp_test_norm_session"
        repo_file = session_dir / "repo" / "resources" / "js" / "Card.vue"
        work_file = session_dir / "work" / "review_plan.json"
        followup_file = session_dir / "followups" / "followup-1.md"
        text = (
            f"See [resources/js/Card.vue:36]({repo_file}#L36) and `{work_file}#L12`.\n"
            f"Follow-up: {followup_file}\n"
            "External: https://github.com/Academy-Plus/ssa-lms/pull/75#discussion_r1\n"
            "Already plain: resources/js/Card.vue:36\n"
        )

        normalized = rf.normalize_markdown_local_refs(text, session_dir=session_dir)

        self.assertIn("resources/js/Card.vue:36", normalized)
        self.assertIn("`work/review_plan.json:12`", normalized)
        self.assertIn("followups/followup-1.md", normalized)
        self.assertIn("https://github.com/Academy-Plus/ssa-lms/pull/75#discussion_r1", normalized)
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


class CodexResumeTests(unittest.TestCase):
    def test_build_codex_resume_command_includes_env_flags_and_session_id(self) -> None:
        repo_dir = ROOT / ".tmp_test_resume_repo" / "repo"
        session_dir = repo_dir.parent
        cmd = rf.build_codex_resume_command(
            repo_dir=repo_dir,
            session_id="019cd0ef-73cd-79c2-a4b9-dbb34c9a2eed",
            env={
                "GH_CONFIG_DIR": str(session_dir / "work" / "gh_config"),
                "REVIEWFLOW_WORK_DIR": str(session_dir / "work"),
                "REVIEWFLOW_CRAWL_ALLOW_HOSTS": "github.com,api.github.com",
            },
            codex_flags=["-m", "gpt-5.2", "--search", "--sandbox", "danger-full-access"],
            codex_config_overrides=['mcp_servers.chunkhound.command="chunkhound"'],
            add_dirs=[session_dir],
        )

        self.assertIn(f"cd {repo_dir}", cmd)
        self.assertIn("env GH_CONFIG_DIR=", cmd)
        self.assertIn("REVIEWFLOW_WORK_DIR=", cmd)
        self.assertIn("codex resume", cmd)
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", cmd)
        self.assertIn("--add-dir /tmp", cmd)
        self.assertNotIn(f"--add-dir {session_dir}", cmd)
        self.assertIn("--search", cmd)
        self.assertIn("danger-full-access", cmd)
        self.assertIn('mcp_servers.chunkhound.command="chunkhound"', cmd)
        self.assertIn("019cd0ef-73cd-79c2-a4b9-dbb34c9a2eed", cmd)

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
                env={"REVIEWFLOW_WORK_DIR": str(repo_dir.parent / "work")},
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
                env={"REVIEWFLOW_WORK_DIR": str(repo_dir.parent / "work")},
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
        cfg = ROOT / ".tmp_test_chunkhound_review_fp.json"
        try:
            tmp_cache.mkdir(parents=True, exist_ok=True)
            tmp_sandbox.mkdir(parents=True, exist_ok=True)
            cfg.write_text('{"indexing":{"exclude":[]}}', encoding="utf-8")

            paths = rf.ReviewflowPaths(
                sandbox_root=tmp_sandbox,
                cache_root=tmp_cache,
                review_chunkhound_config=cfg,
                main_chunkhound_config=cfg,
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
            cfg.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
