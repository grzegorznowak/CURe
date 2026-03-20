import contextlib
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import tomllib
import unittest
from io import StringIO
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import reviewflow as rf  # noqa: E402
import cure  # noqa: E402
import cure_commands  # noqa: E402
import cure_flows  # noqa: E402
import cure_llm  # noqa: E402
import cure_output  # noqa: E402
import cure_runtime  # noqa: E402
import chunkhound_summary  # noqa: E402
import ui as rui  # noqa: E402


def _verdicts(business: str, technical: str | None = None) -> rf.ReviewVerdicts:
    return rf.ReviewVerdicts(
        business=business,
        technical=(technical if technical is not None else business),
    )


def _sectioned_review_markdown(*, business: str, technical: str) -> str:
    return "\n".join(
        [
            "**Summary**: ok",
            "",
            "## Business / Product Assessment",
            f"**Verdict**: {business}",
            "",
            "### Strengths",
            "- Business strength",
            "",
            "### In Scope Issues",
            "- None.",
            "",
            "### Out of Scope Issues",
            "- None.",
            "",
            "## Technical Assessment",
            f"**Verdict**: {technical}",
            "",
            "### Strengths",
            "- Technical strength",
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
    )


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

    def test_render_prompt_supports_review_intelligence_guidance_placeholder(self) -> None:
        template = "GUIDANCE=$REVIEW_INTELLIGENCE_GUIDANCE\n"
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
            extra_vars={"REVIEW_INTELLIGENCE_GUIDANCE": "Use MCP first.\n"},
        )
        self.assertIn("GUIDANCE=Use MCP first.", rendered)

    def test_render_prompt_keeps_review_intelligence_guidance_literal(self) -> None:
        template = "X=$X\nGUIDANCE=$REVIEW_INTELLIGENCE_GUIDANCE\n"
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
            extra_vars={
                "X": "value",
                "REVIEW_INTELLIGENCE_GUIDANCE": "Use $X literally.\n",
            },
        )
        self.assertIn("X=value", rendered)
        self.assertIn("GUIDANCE=Use $X literally.", rendered)


class ReviewIntelligenceConfigTests(unittest.TestCase):
    def test_load_review_intelligence_config_parses_toml(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_review_intelligence.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[review_intelligence]",
                        'tool_prompt_fragment = """',
                        "Preferred review-intelligence tools:",
                        "- Use GitHub MCP for PR context when available.",
                        "- Otherwise use gh CLI / gh api.",
                        "- Use any additional tools or sources that materially improve understanding of the code under review.",
                        '"""',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            review_intelligence, meta = rf.load_review_intelligence_config(config_path=cfg)
            self.assertTrue(meta.get("loaded"))
            self.assertIn("Use GitHub MCP", review_intelligence.tool_prompt_fragment)
            self.assertEqual(review_intelligence.policy_mode, "cure_first_unrestricted")
            persisted = meta["review_intelligence"]
            self.assertEqual(persisted["policy_mode"], "cure_first_unrestricted")
        finally:
            cfg.unlink(missing_ok=True)

    def test_load_review_intelligence_config_rejects_legacy_url_policy_fields(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_review_intelligence_legacy.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[review_intelligence]",
                        'tool_prompt_fragment = "Use GitHub MCP first."',
                        'allow_hosts = ["github.com"]',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.load_review_intelligence_config(config_path=cfg)
            self.assertIn("Legacy review-intelligence URL policy fields are no longer supported", str(ctx.exception))
        finally:
            cfg.unlink(missing_ok=True)

    def test_load_review_intelligence_config_rejects_deprecated_crawl_section(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_review_intelligence_crawl.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[review_intelligence]",
                        'tool_prompt_fragment = "Use GitHub MCP first."',
                        "",
                        "[crawl]",
                        'allow_hosts = ["github.com"]',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.load_review_intelligence_config(config_path=cfg)
            self.assertIn("Deprecated `[crawl]` config is no longer supported", str(ctx.exception))
        finally:
            cfg.unlink(missing_ok=True)

    def test_load_review_intelligence_config_requires_tool_prompt_fragment_for_builtin_prompts(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_review_intelligence_missing.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[review_intelligence]",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.load_review_intelligence_config(
                    config_path=cfg, require_tool_prompt_fragment=True
                )
            self.assertIn("[review_intelligence].tool_prompt_fragment", str(ctx.exception))
            self.assertIn("Use GitHub MCP for PR context when available.", str(ctx.exception))
        finally:
            cfg.unlink(missing_ok=True)

    def test_build_review_intelligence_guidance_uses_cure_first_policy(self) -> None:
        cfg = rf.ReviewIntelligenceConfig(
            tool_prompt_fragment="Use GitHub MCP first.",
            policy_mode="cure_first_unrestricted",
        )
        guidance = rf.build_review_intelligence_guidance(cfg)
        self.assertIn("Use GitHub MCP first.", guidance)
        self.assertIn("Code under review first policy", guidance)
        self.assertIn("materially improves understanding of the code under review", guidance)
        self.assertNotIn("codebase-under-review (CURe)", guidance)
        self.assertNotIn("rf-fetch-url", guidance)

    def test_review_intelligence_prompt_vars_include_guidance(self) -> None:
        cfg = rf.ReviewIntelligenceConfig(
            tool_prompt_fragment="Use GitHub MCP first.",
            policy_mode="cure_first_unrestricted",
        )

        prompt_vars = rf.review_intelligence_prompt_vars(cfg)

        self.assertIn("REVIEW_INTELLIGENCE_GUIDANCE", prompt_vars)
        self.assertIn("Use GitHub MCP first.", prompt_vars["REVIEW_INTELLIGENCE_GUIDANCE"])
        self.assertIn("Code under review first policy", prompt_vars["REVIEW_INTELLIGENCE_GUIDANCE"])


class PublicGitHubFallbackTests(unittest.TestCase):
    def _gh_auth_error(self, cmd: list[str]) -> rf.ReviewflowSubprocessError:
        return rf.ReviewflowSubprocessError(
            cmd=cmd,
            cwd=None,
            exit_code=4,
            stdout="",
            stderr="To get started with GitHub CLI, please run:  gh auth login",
        )

    def test_gh_api_json_falls_back_to_public_github_api(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(
            {
                "title": "Public PR",
                "base": {"ref": "main"},
                "head": {"sha": "abc123"},
            }
        ).encode("utf-8")
        with mock.patch.object(
            rf,
            "run_cmd",
            side_effect=self._gh_auth_error(["gh", "api", "--hostname", "github.com", "repos/acme/repo/pulls/1"]),
        ), mock.patch.object(rf.urllib.request, "urlopen", return_value=response):
            payload = rf.gh_api_json(
                host="github.com",
                path="repos/acme/repo/pulls/1",
                allow_public_fallback=True,
            )

        self.assertEqual(payload["title"], "Public PR")
        self.assertEqual(payload["base"]["ref"], "main")
        self.assertEqual(payload["head"]["sha"], "abc123")

    def test_gh_api_json_falls_back_to_public_github_api_when_gh_is_missing(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps({"title": "Public PR"}).encode("utf-8")
        with mock.patch.object(rf, "run_cmd", side_effect=FileNotFoundError("gh")), mock.patch.object(
            rf.urllib.request,
            "urlopen",
            return_value=response,
        ):
            payload = rf.gh_api_json(
                host="github.com",
                path="repos/acme/repo/pulls/1",
                allow_public_fallback=True,
            )

        self.assertEqual(payload["title"], "Public PR")

    def test_gh_api_json_does_not_fallback_for_non_github_hosts_when_gh_is_missing(self) -> None:
        with mock.patch.object(rf, "run_cmd", side_effect=FileNotFoundError("gh")):
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.gh_api_json(
                    host="ghe.example.com",
                    path="repos/acme/repo/pulls/1",
                    allow_public_fallback=True,
                )

        self.assertIn("`gh` is required for PR metadata resolution on ghe.example.com", str(ctx.exception))

    def test_clone_seed_repo_falls_back_to_public_git_clone(self) -> None:
        seed = ROOT / ".tmp_test_public_seed"
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], **_: object) -> mock.Mock:
            calls.append(cmd)
            if cmd[:3] == ["gh", "repo", "clone"]:
                raise self._gh_auth_error(cmd)
            return mock.Mock(stdout="", stderr="", exit_code=0, duration_seconds=0.0, cmd=cmd, cwd=None)

        with mock.patch.object(rf, "run_cmd", side_effect=fake_run):
            rf.clone_seed_repo(host="github.com", owner="chunkhound", repo="chunkhound", seed=seed)

        self.assertEqual(calls[0], ["gh", "repo", "clone", "chunkhound/chunkhound", str(seed)])
        self.assertEqual(
            calls[1],
            ["git", "clone", "https://github.com/chunkhound/chunkhound.git", str(seed)],
        )

    def test_clone_seed_repo_falls_back_to_public_git_clone_when_gh_is_missing(self) -> None:
        seed = ROOT / ".tmp_test_public_seed_missing_gh"
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], **_: object) -> mock.Mock:
            calls.append(cmd)
            if cmd[:3] == ["gh", "repo", "clone"]:
                raise FileNotFoundError("gh")
            return mock.Mock(stdout="", stderr="", exit_code=0, duration_seconds=0.0, cmd=cmd, cwd=None)

        with mock.patch.object(rf, "run_cmd", side_effect=fake_run):
            rf.clone_seed_repo(host="github.com", owner="chunkhound", repo="chunkhound", seed=seed)

        self.assertEqual(calls[0], ["gh", "repo", "clone", "chunkhound/chunkhound", str(seed)])
        self.assertEqual(
            calls[1],
            ["git", "clone", "https://github.com/chunkhound/chunkhound.git", str(seed)],
        )

    def test_checkout_pr_in_repo_falls_back_to_public_git_fetch(self) -> None:
        repo_dir = ROOT / ".tmp_test_public_checkout"
        pr = rf.PullRequestRef(host="github.com", owner="chunkhound", repo="chunkhound", number=219)
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], **_: object) -> mock.Mock:
            calls.append(cmd)
            if cmd[:3] == ["gh", "pr", "checkout"]:
                raise self._gh_auth_error(cmd)
            return mock.Mock(stdout="", stderr="", exit_code=0, duration_seconds=0.0, cmd=cmd, cwd=None)

        with mock.patch.object(rf, "run_cmd", side_effect=fake_run):
            rf.checkout_pr_in_repo(repo_dir=repo_dir, pr=pr)

        self.assertEqual(
            calls[0],
            ["gh", "pr", "checkout", "219", "-R", "chunkhound/chunkhound", "--force"],
        )
        self.assertEqual(
            calls[1],
            [
                "git",
                "-C",
                str(repo_dir),
                "fetch",
                "origin",
                "refs/pull/219/head:reviewflow_pr__219",
            ],
        )
        self.assertEqual(
            calls[2],
            [
                "git",
                "-C",
                str(repo_dir),
                "checkout",
                "-B",
                "reviewflow_pr__219",
                "reviewflow_pr__219",
            ],
        )

    def test_checkout_pr_in_repo_falls_back_to_public_git_fetch_when_gh_is_missing(self) -> None:
        repo_dir = ROOT / ".tmp_test_public_checkout_missing_gh"
        pr = rf.PullRequestRef(host="github.com", owner="chunkhound", repo="chunkhound", number=220)
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], **_: object) -> mock.Mock:
            calls.append(cmd)
            if cmd[:3] == ["gh", "pr", "checkout"]:
                raise FileNotFoundError("gh")
            return mock.Mock(stdout="", stderr="", exit_code=0, duration_seconds=0.0, cmd=cmd, cwd=None)

        with mock.patch.object(rf, "run_cmd", side_effect=fake_run):
            rf.checkout_pr_in_repo(repo_dir=repo_dir, pr=pr)

        self.assertEqual(
            calls[0],
            ["gh", "pr", "checkout", "220", "-R", "chunkhound/chunkhound", "--force"],
        )
        self.assertEqual(
            calls[1],
            [
                "git",
                "-C",
                str(repo_dir),
                "fetch",
                "origin",
                "refs/pull/220/head:reviewflow_pr__220",
            ],
        )


class ChunkHoundConfigTests(unittest.TestCase):
    def test_load_reviewflow_chunkhound_config_parses_toml(self) -> None:
        base_cfg = ROOT / ".tmp_test_chunkhound_base.json"
        rf_cfg = ROOT / ".tmp_test_reviewflow_chunkhound.toml"
        try:
            base_cfg.write_text(
                json.dumps(
                    {
                        "database": {"provider": "duckdb", "path": "/tmp/db"},
                        "indexing": {"exclude": ["**/.git/**"], "_include": ["**/*.py"]},
                        "research": {"algorithm": "hybrid"},
                    }
                ),
                encoding="utf-8",
            )
            rf_cfg.write_text(
                "\n".join(
                    [
                        "[chunkhound]",
                        f'base_config_path = "{base_cfg}"',
                        "",
                        "[chunkhound.indexing]",
                        'include = ["**/*.ts"]',
                        'exclude = ["**/openspec/**"]',
                        "per_file_timeout_seconds = 7",
                        "per_file_timeout_min_size_kb = 256",
                        "",
                        "[chunkhound.research]",
                        'algorithm = "semantic"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            chunkhound, meta = rf.load_reviewflow_chunkhound_config(config_path=rf_cfg)
            assert chunkhound is not None
            self.assertEqual(chunkhound.base_config_path, base_cfg)
            self.assertEqual(chunkhound.indexing_include, ("**/*.ts",))
            self.assertEqual(chunkhound.indexing_exclude, ("**/openspec/**",))
            self.assertEqual(chunkhound.per_file_timeout_seconds, 7.0)
            self.assertEqual(chunkhound.per_file_timeout_min_size_kb, 256)
            self.assertEqual(chunkhound.research_algorithm, "semantic")
            self.assertEqual(meta["chunkhound"]["base_config_path"], str(base_cfg))
            self.assertTrue(meta["chunkhound"]["base_config_fingerprint"])
        finally:
            base_cfg.unlink(missing_ok=True)
            rf_cfg.unlink(missing_ok=True)

    def test_load_reviewflow_chunkhound_config_requires_explicit_section(self) -> None:
        rf_cfg = ROOT / ".tmp_test_reviewflow_chunkhound_missing.toml"
        try:
            rf_cfg.write_text("", encoding="utf-8")
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.load_reviewflow_chunkhound_config(config_path=rf_cfg, require=True)
            self.assertIn("Missing required `[chunkhound]` section", str(ctx.exception))
            self.assertIn("base_config_path", str(ctx.exception))
        finally:
            rf_cfg.unlink(missing_ok=True)

    def test_load_reviewflow_chunkhound_config_rejects_relative_base_path(self) -> None:
        rf_cfg = ROOT / ".tmp_test_reviewflow_chunkhound_relative.toml"
        try:
            rf_cfg.write_text(
                "\n".join(
                    [
                        "[chunkhound]",
                        'base_config_path = "relative/chunkhound.json"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.load_reviewflow_chunkhound_config(config_path=rf_cfg, require=True)
            self.assertIn("must be an absolute path", str(ctx.exception))
        finally:
            rf_cfg.unlink(missing_ok=True)

    def test_resolve_chunkhound_reviewflow_config_replaces_lists(self) -> None:
        base_cfg = ROOT / ".tmp_test_chunkhound_base_replace.json"
        try:
            base_cfg.write_text(
                json.dumps(
                    {
                        "indexing": {
                            "_include": ["**/*.py"],
                            "exclude": ["**/.git/**"],
                            "per_file_timeout_seconds": 6.0,
                            "per_file_timeout_min_size_kb": 128,
                        },
                        "research": {"algorithm": "hybrid"},
                    }
                ),
                encoding="utf-8",
            )
            resolved = rf.resolve_chunkhound_reviewflow_config(
                rf.ReviewflowChunkHoundConfig(
                    base_config_path=base_cfg,
                    indexing_include=("**/*.ts",),
                    indexing_exclude=("**/openspec/**",),
                    per_file_timeout_seconds=9,
                    per_file_timeout_min_size_kb=512,
                    research_algorithm="semantic",
                )
            )
            indexing = resolved["indexing"]
            self.assertNotIn("_include", indexing)
            self.assertEqual(indexing["include"], ["**/*.ts"])
            self.assertEqual(indexing["exclude"], ["**/openspec/**"])
            self.assertEqual(indexing["per_file_timeout_seconds"], 9)
            self.assertEqual(indexing["per_file_timeout_min_size_kb"], 512)
            self.assertEqual(resolved["research"]["algorithm"], "semantic")
        finally:
            base_cfg.unlink(missing_ok=True)

    def test_materialize_chunkhound_env_config_pins_database_and_strips_embedding_api_key(self) -> None:
        output = ROOT / ".tmp_test_materialized_chunkhound.json"
        try:
            rf.materialize_chunkhound_env_config(
                resolved_config={
                    "embedding": {
                        "provider": "voyage",
                        "api_key": "secret",  # pragma: allowlist secret
                        "model": "voyage-code-3",
                    },
                    "indexing": {"exclude": ["**/.git/**"]},
                },
                output_config_path=output,
                database_provider="duckdb",
                database_path=ROOT / ".tmp_test_chunkhound_db",
            )
            materialized = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(materialized["database"]["provider"], "duckdb")
            self.assertEqual(materialized["database"]["path"], str(ROOT / ".tmp_test_chunkhound_db"))
            self.assertNotIn("api_key", materialized["embedding"])
        finally:
            output.unlink(missing_ok=True)

    def test_chunkhound_env_can_infer_embedding_key_from_explicit_base_config_path(self) -> None:
        base_cfg = ROOT / ".tmp_test_chunkhound_base_env.json"
        try:
            base_cfg.write_text(
                json.dumps(
                    {
                        "embedding": {
                            "provider": "voyage",
                            "api_key": "test-key",  # pragma: allowlist secret
                            "model": "voyage-code-3",
                        }
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {"CHUNKHOUND_EMBEDDING__API_KEY": "", "VOYAGE_API_KEY": ""},
                clear=False,
            ):
                env = rf.chunkhound_env(source_config_path=base_cfg)
            self.assertEqual(env["CHUNKHOUND_EMBEDDING__API_KEY"], "test-key")  # pragma: allowlist secret
        finally:
            base_cfg.unlink(missing_ok=True)

    def test_chunkhound_env_does_not_infer_without_explicit_base_config_path(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"CHUNKHOUND_EMBEDDING__API_KEY": "", "VOYAGE_API_KEY": ""},
            clear=False,
        ):
            env = rf.chunkhound_env()
        self.assertEqual(env, {})


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
                        'grounding_mode = "warn"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            mp, meta = rf.load_reviewflow_multipass_defaults(config_path=cfg)
            self.assertTrue(meta.get("loaded"))
            self.assertEqual(mp["enabled"], False)
            self.assertEqual(mp["max_steps"], 7)
            self.assertEqual(mp["grounding_mode"], "warn")
        finally:
            cfg.unlink(missing_ok=True)

    def test_load_reviewflow_multipass_defaults_defaults_grounding_mode_to_strict(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_multipass_default_grounding.toml"
        try:
            cfg.write_text("[multipass]\nmax_steps = 5\n", encoding="utf-8")
            mp, _ = rf.load_reviewflow_multipass_defaults(config_path=cfg)
            self.assertEqual(mp["grounding_mode"], "strict")
        finally:
            cfg.unlink(missing_ok=True)

    def test_load_reviewflow_multipass_defaults_rejects_invalid_grounding_mode(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_multipass_invalid_grounding.toml"
        try:
            cfg.write_text('[multipass]\ngrounding_mode = "broken"\n', encoding="utf-8")
            with self.assertRaises(rf.ReviewflowError):
                rf.load_reviewflow_multipass_defaults(config_path=cfg)
        finally:
            cfg.unlink(missing_ok=True)


class LlmPresetConfigTests(unittest.TestCase):
    def test_load_reviewflow_llm_config_parses_builtin_named_overrides(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_llm.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[llm]",
                        'default_preset = "fast_router"',
                        "",
                        "[llm_presets.fast_router]",
                        'preset = "openrouter-responses"',
                        'api_key = "test-openrouter-key"',  # pragma: allowlist secret
                        'model = "x-ai/grok-4.1-fast"',
                        'reasoning_effort = "high"',
                        'plan_reasoning_effort = "xhigh"',
                        "max_output_tokens = 9000",
                        'headers = { "X-Test" = "1" }',
                        'request = { "service_tier" = "flex" }',
                        "",
                        "[llm_presets.my_codex]",
                        'preset = "codex-cli"',
                        'model = "gpt-5.4"',
                        'reasoning_effort = "medium"',
                        'env = { OPENAI_API_KEY = "test-openai-key" }',  # pragma: allowlist secret
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            llm_cfg, meta = rf.load_reviewflow_llm_config(config_path=cfg)
            self.assertTrue(meta.get("loaded"))
            self.assertEqual(llm_cfg["default_preset"], "fast_router")
            self.assertEqual(llm_cfg["presets"]["fast_router"]["preset"], "openrouter-responses")
            self.assertEqual(llm_cfg["presets"]["fast_router"]["provider"], "openrouter")
            self.assertEqual(llm_cfg["presets"]["fast_router"]["headers"]["X-Test"], "1")
            self.assertEqual(llm_cfg["presets"]["fast_router"]["request"]["service_tier"], "flex")
            self.assertEqual(llm_cfg["presets"]["my_codex"]["transport"], "cli")
            self.assertEqual(llm_cfg["presets"]["my_codex"]["env"]["OPENAI_API_KEY"], "test-openai-key")  # pragma: allowlist secret
        finally:
            cfg.unlink(missing_ok=True)

    def test_load_reviewflow_llm_config_rejects_mixed_builtin_and_explicit_shape(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_llm_invalid.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[llm]",
                        'default_preset = "broken"',
                        "",
                        "[llm_presets.broken]",
                        'preset = "codex-cli"',
                        'transport = "cli"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaises(rf.ReviewflowError):
                rf.load_reviewflow_llm_config(config_path=cfg)
        finally:
            cfg.unlink(missing_ok=True)

    def test_resolve_llm_config_precedence_merges_overrides_and_legacy_codex(self) -> None:
        base = ROOT / ".tmp_test_base_codex_llm.toml"
        rf_cfg = ROOT / ".tmp_test_reviewflow_llm_precedence.toml"
        try:
            base.write_text(
                "\n".join(
                    [
                        'model = "base-codex-model"',
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
                        "[llm]",
                        'default_preset = "my_codex"',
                        "",
                        "[llm_presets.my_codex]",
                        'preset = "codex-cli"',
                        'model = "preset-model"',
                        'reasoning_effort = "medium"',
                        'plan_reasoning_effort = "high"',
                        'request = { "temperature" = 0.1 }',
                        "",
                        "[codex]",
                        'model = "legacy-model"',
                        'model_reasoning_effort = "low"',
                        'plan_mode_reasoning_effort = "medium"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            resolved, meta = rf.resolve_llm_config(
                base_codex_config_path=base,
                reviewflow_config_path=rf_cfg,
                cli_preset=None,
                cli_model="cli-model",
                cli_effort="xhigh",
                cli_plan_effort=None,
                cli_verbosity="low",
                cli_max_output_tokens=None,
                cli_request_overrides={"temperature": 0.3, "top_p": 0.9},
                cli_header_overrides={"X-Test": "2"},
                deprecated_codex_model="deprecated-model",
                deprecated_codex_effort="minimal",
                deprecated_codex_plan_effort="low",
            )
            self.assertEqual(resolved["preset"], "codex-cli")
            self.assertEqual(resolved["selected_name"], "my_codex")
            self.assertEqual(resolved["provider"], "codex")
            self.assertEqual(resolved["model"], "cli-model")
            self.assertEqual(resolved["reasoning_effort"], "xhigh")
            self.assertEqual(resolved["plan_reasoning_effort"], "low")
            self.assertEqual(resolved["text_verbosity"], "low")
            self.assertEqual(resolved["request"]["temperature"], 0.3)
            self.assertEqual(resolved["request"]["top_p"], 0.9)
            self.assertEqual(resolved["headers"]["X-Test"], "2")
            self.assertEqual(meta["resolved"]["model_source"], "cli")
            self.assertEqual(meta["resolved"]["reasoning_effort_source"], "cli")
            self.assertEqual(meta["resolved"]["plan_reasoning_effort_source"], "deprecated_codex_cli")
        finally:
            base.unlink(missing_ok=True)
            rf_cfg.unlink(missing_ok=True)

    def test_resolve_llm_config_allows_direct_builtin_preset_selection(self) -> None:
        base = ROOT / ".tmp_test_base_codex_llm_builtin.toml"
        try:
            base.write_text(
                "\n".join(
                    [
                        'model = "base-codex-model"',
                        'sandbox_mode = "danger-full-access"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            resolved, meta = rf.resolve_llm_config(
                base_codex_config_path=base,
                reviewflow_config_path=None,
                cli_preset="claude-cli",
                cli_model="claude-sonnet-4-6",
                cli_effort="high",
                cli_plan_effort="high",
                cli_verbosity=None,
                cli_max_output_tokens=None,
                cli_request_overrides={},
                cli_header_overrides={},
                deprecated_codex_model=None,
                deprecated_codex_effort=None,
                deprecated_codex_plan_effort=None,
            )
            self.assertEqual(resolved["preset"], "claude-cli")
            self.assertEqual(resolved["selected_name"], "claude-cli")
            self.assertEqual(resolved["provider"], "claude")
            self.assertEqual(meta["selected_name"], "claude-cli")
            self.assertEqual(meta["resolved_preset_id"], "claude-cli")
        finally:
            base.unlink(missing_ok=True)

    def test_load_reviewflow_llm_config_accepts_legacy_explicit_blocks_for_compatibility(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_llm_legacy_compat.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[llm]",
                        'default_preset = "legacy_router"',
                        "",
                        "[llm_presets.legacy_router]",
                        'transport = "http"',
                        'provider = "openrouter"',
                        'endpoint = "responses"',
                        'base_url = "https://openrouter.ai/api/v1"',
                        'api_key = "test-openrouter-key"',  # pragma: allowlist secret
                        'model = "x-ai/grok-4.1-fast"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            llm_cfg, meta = rf.load_reviewflow_llm_config(config_path=cfg)
            self.assertEqual(llm_cfg["presets"]["legacy_router"]["preset"], "openrouter-responses")
            self.assertEqual(meta["deprecated_explicit_presets"], ["legacy_router"])
        finally:
            cfg.unlink(missing_ok=True)

    def test_build_llm_meta_persists_env_keys_not_env_values(self) -> None:
        meta = rf.build_llm_meta(
            resolved={
                "preset": "codex-cli",
                "selected_name": "team_codex",
                "transport": "cli",
                "provider": "codex",
                "command": "codex",
                "model": "gpt-5.4",
                "reasoning_effort": "medium",
                "plan_reasoning_effort": "high",
                "text_verbosity": None,
                "max_output_tokens": None,
                "env": {"OPENAI_API_KEY": "test-openai-key"},  # pragma: allowlist secret
                "capabilities": {"supports_resume": True},
            },
            resolution_meta={"runtime_overrides": {}},
            env={},
        )
        self.assertEqual(meta["env_keys"], ["OPENAI_API_KEY"])
        self.assertNotIn("env", meta)

    def test_write_redacted_json_scrubs_secret_like_keys_case_insensitively(self) -> None:
        path = ROOT / ".tmp_test_redacted_meta.json"
        try:
            rf.write_redacted_json(
                path,
                {
                    "env": {"OPENAI_API_KEY": "test-openai-key"},  # pragma: allowlist secret
                    "headers": {
                        "Authorization": "Bearer test-openrouter-key",  # pragma: allowlist secret
                        "HTTP-Referer": "https://example.com",
                    },
                },
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["env"]["OPENAI_API_KEY"], "REDACTED")
            self.assertEqual(payload["headers"]["Authorization"], "REDACTED")
            self.assertEqual(payload["headers"]["HTTP-Referer"], "https://example.com")
        finally:
            path.unlink(missing_ok=True)


class AgentRuntimeConfigTests(unittest.TestCase):
    def test_load_reviewflow_agent_runtime_config_parses_profile_and_gemini_backend(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_agent_runtime.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[agent_runtime]",
                        'profile = "strict"',
                        "",
                        "[agent_runtime.gemini]",
                        'sandbox = "runsc"',
                        'seatbelt_profile = "strict-open"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            loaded, meta = rf.load_reviewflow_agent_runtime_config(config_path=cfg)
            self.assertEqual(loaded["profile"], "strict")
            self.assertEqual(loaded["gemini"]["sandbox"], "runsc")
            self.assertEqual(loaded["gemini"]["seatbelt_profile"], "strict-open")
            self.assertEqual(meta["agent_runtime"]["profile"], "strict")
        finally:
            cfg.unlink(missing_ok=True)

    def test_resolve_agent_runtime_profile_precedence(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_agent_runtime_precedence.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[agent_runtime]",
                        'profile = "strict"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            profile, source, loaded, _ = rf.resolve_agent_runtime_profile(
                cli_value=None,
                config_path=cfg,
                config_enabled=True,
            )
            self.assertEqual(profile, "strict")
            self.assertEqual(source, "config")
            self.assertEqual(loaded["profile"], "strict")

            with mock.patch.dict(
                os.environ,
                {"REVIEWFLOW_AGENT_RUNTIME_PROFILE": "permissive"},
                clear=False,
            ):
                profile, source, _, _ = rf.resolve_agent_runtime_profile(
                    cli_value=None,
                    config_path=cfg,
                    config_enabled=True,
                )
            self.assertEqual(profile, "permissive")
            self.assertEqual(source, "env")

            profile, source, _, _ = rf.resolve_agent_runtime_profile(
                cli_value="balanced",
                config_path=cfg,
                config_enabled=True,
            )
            self.assertEqual(profile, "balanced")
            self.assertEqual(source, "cli")

            profile, source, _, _ = rf.resolve_agent_runtime_profile(
                cli_value=None,
                config_path=cfg,
                config_enabled=False,
            )
            self.assertEqual(profile, "balanced")
            self.assertEqual(source, "default")
        finally:
            cfg.unlink(missing_ok=True)


class AgentRuntimePolicyTests(unittest.TestCase):
    def _llm_resolved(self, provider: str, *, command: str | None = None) -> dict[str, object]:
        return {
            "preset": f"{provider}-cli",
            "selected_name": f"{provider}-cli",
            "transport": "cli",
            "provider": provider,
            "command": command or provider,
            "model": f"{provider}-model",
            "reasoning_effort": "medium",
            "plan_reasoning_effort": "high",
            "text_verbosity": None,
            "max_output_tokens": None,
            "env": {},
            "capabilities": {"supports_resume": provider in {"codex", "claude"}},
        }

    def _llm_resolution_meta(self) -> dict[str, object]:
        return {
            "base_codex_config": {
                "path": "/tmp/codex.toml",
                "loaded": True,
                "model": "gpt-5.3-codex",
                "sandbox_mode": "danger-full-access",
                "web_search": "live",
                "reasoning_effort": "medium",
                "plan_reasoning_effort": "high",
            },
            "resolved": {
                "model_source": "preset",
                "reasoning_effort_source": "preset",
                "plan_reasoning_effort_source": "preset",
            },
            "runtime_overrides": {},
        }

    def _runtime_args(self, *, profile: str | None = None) -> argparse.Namespace:
        return argparse.Namespace(agent_runtime_profile=profile)

    def test_prepare_review_agent_runtime_maps_codex_profiles(self) -> None:
        root = ROOT / ".tmp_test_agent_runtime_codex"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo = root / "repo"
            session = root / "session"
            work = session / "work"
            repo.mkdir(parents=True, exist_ok=True)
            work.mkdir(parents=True, exist_ok=True)

            with (
                mock.patch.object(shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"),
                mock.patch.dict(
                    os.environ,
                    {
                        "CODEX_THREAD_ID": "thread-123",
                        "CODEX_HOME": "/tmp/codex-home",
                        "CLAUDE_CODE_SESSION": "ignore-me",
                    },
                    clear=False,
                ),
            ):
                balanced = rf.prepare_review_agent_runtime(
                    args=self._runtime_args(profile="balanced"),
                    resolved=self._llm_resolved("codex"),
                    resolution_meta=self._llm_resolution_meta(),
                    reviewflow_config_path=ROOT / ".tmp_unused_runtime_config.toml",
                    config_enabled=True,
                    repo_dir=repo,
                    session_dir=session,
                    work_dir=work,
                    base_env={"PATH": "/usr/bin"},
                    chunkhound_config_path=work / "chunkhound.json",
                    chunkhound_db_path=work / ".chunkhound.db",
                    chunkhound_cwd=work / "chunkhound",
                    enable_mcp=True,
                    interactive=False,
                    paths=rf.DEFAULT_PATHS,
                )
                self.assertEqual(balanced["profile"], "balanced")
                self.assertEqual(balanced["provider"], "codex")
                self.assertEqual(balanced["sandbox_mode"], "workspace-write")
                self.assertEqual(balanced["approval_policy"], "never")
                self.assertFalse(balanced["dangerously_bypass_approvals_and_sandbox"])
                self.assertEqual(balanced["env"]["CODEX_THREAD_ID"], "thread-123")
                self.assertEqual(balanced["env"]["CODEX_HOME"], "/tmp/codex-home")
                self.assertNotIn("CLAUDE_CODE_SESSION", balanced["env"])
                self.assertIn("CODEX_THREAD_ID", balanced["metadata"]["env_keys"])
                self.assertIn("--sandbox", balanced["codex_flags"])
                self.assertIn("workspace-write", balanced["codex_flags"])

                strict = rf.prepare_review_agent_runtime(
                    args=self._runtime_args(profile="strict"),
                    resolved=self._llm_resolved("codex"),
                    resolution_meta=self._llm_resolution_meta(),
                    reviewflow_config_path=ROOT / ".tmp_unused_runtime_config.toml",
                    config_enabled=True,
                    repo_dir=repo,
                    session_dir=session,
                    work_dir=work,
                    base_env={"PATH": "/usr/bin"},
                    chunkhound_config_path=work / "chunkhound.json",
                    chunkhound_db_path=work / ".chunkhound.db",
                    chunkhound_cwd=work / "chunkhound",
                    enable_mcp=True,
                    interactive=True,
                    paths=rf.DEFAULT_PATHS,
                )
                self.assertEqual(strict["sandbox_mode"], "read-only")
                self.assertEqual(strict["approval_policy"], "on-request")
                self.assertFalse(strict["dangerously_bypass_approvals_and_sandbox"])

                permissive = rf.prepare_review_agent_runtime(
                    args=self._runtime_args(profile="permissive"),
                    resolved=self._llm_resolved("codex"),
                    resolution_meta=self._llm_resolution_meta(),
                    reviewflow_config_path=ROOT / ".tmp_unused_runtime_config.toml",
                    config_enabled=True,
                    repo_dir=repo,
                    session_dir=session,
                    work_dir=work,
                    base_env={"PATH": "/usr/bin"},
                    chunkhound_config_path=work / "chunkhound.json",
                    chunkhound_db_path=work / ".chunkhound.db",
                    chunkhound_cwd=work / "chunkhound",
                    enable_mcp=True,
                    interactive=False,
                    paths=rf.DEFAULT_PATHS,
                )
                self.assertTrue(permissive["dangerously_bypass_approvals_and_sandbox"])
                self.assertIsNone(permissive["sandbox_mode"])
                self.assertIsNone(permissive["approval_policy"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_prepare_review_agent_runtime_maps_claude_profiles_and_stages_files(self) -> None:
        root = ROOT / ".tmp_test_agent_runtime_claude"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo = root / "repo"
            session = root / "session"
            work = session / "work"
            repo.mkdir(parents=True, exist_ok=True)
            work.mkdir(parents=True, exist_ok=True)

            with (
                mock.patch.object(shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"),
                mock.patch.dict(
                    os.environ,
                    {
                        "CLAUDE_CODE_SESSION": "claude-session-123",
                        "CLAUDE_HOME": "/tmp/claude-home",
                        "CODEX_THREAD_ID": "ignore-me",
                    },
                    clear=False,
                ),
            ):
                runtime = rf.prepare_review_agent_runtime(
                    args=self._runtime_args(profile="balanced"),
                    resolved=self._llm_resolved("claude"),
                    resolution_meta=self._llm_resolution_meta(),
                    reviewflow_config_path=ROOT / ".tmp_unused_runtime_config.toml",
                    config_enabled=True,
                    repo_dir=repo,
                    session_dir=session,
                    work_dir=work,
                    base_env={"PATH": "/usr/bin"},
                    chunkhound_config_path=work / "chunkhound.json",
                    chunkhound_db_path=work / ".chunkhound.db",
                    chunkhound_cwd=work / "chunkhound",
                    enable_mcp=True,
                    interactive=False,
                    paths=rf.DEFAULT_PATHS,
                )
            self.assertEqual(runtime["profile"], "balanced")
            self.assertEqual(runtime["permission_mode"], "dontAsk")
            self.assertFalse(runtime["dangerously_skip_permissions"])
            self.assertEqual(runtime["env"]["CLAUDE_CODE_SESSION"], "claude-session-123")
            self.assertEqual(runtime["env"]["CLAUDE_HOME"], "/tmp/claude-home")
            self.assertNotIn("CODEX_THREAD_ID", runtime["env"])
            self.assertIn("CLAUDE_CODE_SESSION", runtime["metadata"]["env_keys"])
            self.assertTrue(Path(runtime["staged_paths"]["claude_settings"]).is_file())
            self.assertTrue(Path(runtime["staged_paths"]["claude_mcp_config"]).is_file())
            cmd = rf.build_claude_exec_cmd(
                command="claude",
                model="claude-sonnet-4-6",
                prompt="hello",
                runtime_policy=runtime,
            )
            self.assertIn("--setting-sources", cmd)
            self.assertIn("user", cmd)
            self.assertIn("--settings", cmd)
            self.assertIn("--strict-mcp-config", cmd)
            self.assertIn("--permission-mode", cmd)
            self.assertIn("dontAsk", cmd)
            self.assertIn("--add-dir", cmd)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_prepare_review_agent_runtime_maps_gemini_profiles_and_stages_files(self) -> None:
        root = ROOT / ".tmp_test_agent_runtime_gemini"
        cfg = ROOT / ".tmp_test_agent_runtime_gemini.toml"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo = root / "repo"
            session = root / "session"
            work = session / "work"
            repo.mkdir(parents=True, exist_ok=True)
            work.mkdir(parents=True, exist_ok=True)
            cfg.write_text(
                "\n".join(
                    [
                        "[agent_runtime.gemini]",
                        'sandbox = "runsc"',
                        'seatbelt_profile = "strict-open"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            with mock.patch.object(shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"):
                balanced = rf.prepare_review_agent_runtime(
                    args=self._runtime_args(profile="balanced"),
                    resolved=self._llm_resolved("gemini"),
                    resolution_meta=self._llm_resolution_meta(),
                    reviewflow_config_path=cfg,
                    config_enabled=True,
                    repo_dir=repo,
                    session_dir=session,
                    work_dir=work,
                    base_env={"PATH": "/usr/bin"},
                    chunkhound_config_path=work / "chunkhound.json",
                    chunkhound_db_path=work / ".chunkhound.db",
                    chunkhound_cwd=work / "chunkhound",
                    enable_mcp=True,
                    interactive=False,
                    paths=rf.DEFAULT_PATHS,
                )
                self.assertEqual(balanced["approval_mode"], "auto_edit")
                self.assertTrue(Path(balanced["staged_paths"]["gemini_system_settings"]).is_file())
                self.assertTrue(Path(balanced["staged_paths"]["gemini_trusted_folders"]).is_file())
                self.assertEqual(balanced["env"]["GEMINI_SANDBOX"], "runsc")

                strict = rf.prepare_review_agent_runtime(
                    args=self._runtime_args(profile="strict"),
                    resolved=self._llm_resolved("gemini"),
                    resolution_meta=self._llm_resolution_meta(),
                    reviewflow_config_path=cfg,
                    config_enabled=True,
                    repo_dir=repo,
                    session_dir=session,
                    work_dir=work,
                    base_env={"PATH": "/usr/bin"},
                    chunkhound_config_path=work / "chunkhound.json",
                    chunkhound_db_path=work / ".chunkhound.db",
                    chunkhound_cwd=work / "chunkhound",
                    enable_mcp=True,
                    interactive=False,
                    paths=rf.DEFAULT_PATHS,
                )
                self.assertEqual(strict["approval_mode"], "plan")
                self.assertEqual(strict["env"]["SEATBELT_PROFILE"], "strict-open")

                permissive = rf.prepare_review_agent_runtime(
                    args=self._runtime_args(profile="permissive"),
                    resolved=self._llm_resolved("gemini"),
                    resolution_meta=self._llm_resolution_meta(),
                    reviewflow_config_path=cfg,
                    config_enabled=True,
                    repo_dir=repo,
                    session_dir=session,
                    work_dir=work,
                    base_env={"PATH": "/usr/bin"},
                    chunkhound_config_path=work / "chunkhound.json",
                    chunkhound_db_path=work / ".chunkhound.db",
                    chunkhound_cwd=work / "chunkhound",
                    enable_mcp=True,
                    interactive=False,
                    paths=rf.DEFAULT_PATHS,
                )
                self.assertEqual(permissive["approval_mode"], "yolo")
                cmd = rf.build_gemini_exec_cmd(
                    command="gemini",
                    model="gemini-2.5-pro",
                    prompt="hello",
                    runtime_policy=permissive,
                )
                self.assertIn("--approval-mode", cmd)
                self.assertIn("yolo", cmd)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_prepare_review_agent_runtime_rejects_gemini_strict_without_hardened_backend(self) -> None:
        root = ROOT / ".tmp_test_agent_runtime_gemini_strict_fail"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo = root / "repo"
            session = root / "session"
            work = session / "work"
            repo.mkdir(parents=True, exist_ok=True)
            work.mkdir(parents=True, exist_ok=True)

            with mock.patch.object(shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"):
                with self.assertRaises(rf.ReviewflowError) as ctx:
                    rf.prepare_review_agent_runtime(
                        args=self._runtime_args(profile="strict"),
                        resolved=self._llm_resolved("gemini"),
                        resolution_meta=self._llm_resolution_meta(),
                        reviewflow_config_path=ROOT / ".tmp_unused_runtime_config.toml",
                        config_enabled=True,
                        repo_dir=repo,
                        session_dir=session,
                        work_dir=work,
                        base_env={"PATH": "/usr/bin"},
                        chunkhound_config_path=work / "chunkhound.json",
                        chunkhound_db_path=work / ".chunkhound.db",
                        chunkhound_cwd=work / "chunkhound",
                        enable_mcp=True,
                        interactive=False,
                        paths=rf.DEFAULT_PATHS,
                    )
            self.assertIn("strict", str(ctx.exception))
            self.assertIn("Gemini", str(ctx.exception))
            self.assertIn("sandbox", str(ctx.exception))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_prepare_review_agent_runtime_hard_fails_when_provider_binary_missing(self) -> None:
        root = ROOT / ".tmp_test_agent_runtime_missing_binary"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo = root / "repo"
            session = root / "session"
            work = session / "work"
            repo.mkdir(parents=True, exist_ok=True)
            work.mkdir(parents=True, exist_ok=True)

            with mock.patch.object(
                shutil,
                "which",
                side_effect=lambda name: None if name == "claude" else f"/usr/bin/{name}",
            ):
                with self.assertRaises(rf.ReviewflowError) as ctx:
                    rf.prepare_review_agent_runtime(
                        args=self._runtime_args(profile="balanced"),
                        resolved=self._llm_resolved("claude"),
                        resolution_meta=self._llm_resolution_meta(),
                        reviewflow_config_path=ROOT / ".tmp_unused_runtime_config.toml",
                        config_enabled=True,
                        repo_dir=repo,
                        session_dir=session,
                        work_dir=work,
                        base_env={"PATH": "/usr/bin"},
                        chunkhound_config_path=work / "chunkhound.json",
                        chunkhound_db_path=work / ".chunkhound.db",
                        chunkhound_cwd=work / "chunkhound",
                        enable_mcp=True,
                        interactive=False,
                        paths=rf.DEFAULT_PATHS,
                    )
            self.assertIn("claude", str(ctx.exception))
            self.assertIn("not found", str(ctx.exception))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_build_http_response_request_openrouter_uses_responses_api_and_headers(self) -> None:
        request = rf.build_http_response_request(
            {
                "preset": "openrouter_grok",
                "transport": "http",
                "provider": "openrouter",
                "endpoint": "responses",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": "test-openrouter-key",  # pragma: allowlist secret
                "model": "x-ai/grok-4.1-fast",
                "reasoning_effort": "high",
                "text_verbosity": None,
                "max_output_tokens": 9000,
                "store": None,
                "include": [],
                "metadata": {},
                "headers": {
                    "HTTP-Referer": "https://example.com",
                    "X-OpenRouter-Title": "cure",
                },
                "request": {"provider": {"sort": "latency"}},
            },
            prompt="Review this PR.",
        )
        self.assertEqual(request["url"], "https://openrouter.ai/api/v1/responses")
        self.assertEqual(request["headers"]["Authorization"], "Bearer test-openrouter-key")  # pragma: allowlist secret
        self.assertEqual(request["headers"]["HTTP-Referer"], "https://example.com")
        self.assertEqual(request["headers"]["X-OpenRouter-Title"], "cure")
        self.assertEqual(request["json"]["model"], "x-ai/grok-4.1-fast")
        self.assertEqual(request["json"]["input"], "Review this PR.")
        self.assertEqual(request["json"]["reasoning"]["effort"], "high")
        self.assertEqual(request["json"]["max_output_tokens"], 9000)
        self.assertEqual(request["json"]["provider"]["sort"], "latency")


class StorageMigrationTests(unittest.TestCase):
    def test_default_paths_use_generic_home_fallbacks(self) -> None:
        home = rf.real_user_home_dir()
        self.assertEqual(rf.DEFAULT_PATHS.sandbox_root, (home / ".local/state/cure/sandboxes").resolve())
        self.assertEqual(rf.DEFAULT_PATHS.cache_root, (home / ".cache/cure").resolve())

    def test_migrate_storage_flow_is_deprecation_stub(self) -> None:
        paths = rf.ReviewflowPaths(
            sandbox_root=ROOT / ".tmp_test_storage_migration",
            cache_root=ROOT / ".tmp_test_storage_migration_cache",
        )
        with mock.patch.object(rf, "_eprint") as eprint:
            rc = rf.migrate_storage_flow(argparse.Namespace(apply=False), paths=paths)
        self.assertEqual(rc, 0)
        text = "\n".join(" ".join(str(a) for a in call.args) for call in eprint.call_args_list)
        self.assertIn("deprecated", text)
        self.assertIn("no longer performs any migration", text)

    def test_migrate_storage_apply_flag_is_tolerated_without_side_effects(self) -> None:
        paths = rf.ReviewflowPaths(
            sandbox_root=ROOT / ".tmp_test_storage_migration_apply",
            cache_root=ROOT / ".tmp_test_storage_migration_apply_cache",
        )
        with mock.patch.object(rf, "_eprint") as eprint:
            rc = rf.migrate_storage_flow(argparse.Namespace(apply=True), paths=paths)
        self.assertEqual(rc, 0)
        text = "\n".join(" ".join(str(a) for a in call.args) for call in eprint.call_args_list)
        self.assertIn("deprecated", text)


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


class StagedAuthCleanupTests(unittest.TestCase):
    def test_cleanup_sensitive_staged_paths_removes_copied_auth_material(self) -> None:
        root = ROOT / ".tmp_test_staged_auth_cleanup"
        try:
            shutil.rmtree(root, ignore_errors=True)
            (root / "gh_config").mkdir(parents=True, exist_ok=True)
            (root / "gh_config" / "hosts.yml").write_text("x", encoding="utf-8")
            (root / "jira_config").mkdir(parents=True, exist_ok=True)
            jira_cfg = root / "jira_config" / ".config.yml"
            jira_cfg.write_text("x", encoding="utf-8")
            (root / "netrc").mkdir(parents=True, exist_ok=True)
            netrc = root / "netrc" / ".netrc"
            netrc.write_text("x", encoding="utf-8")

            rf.cleanup_sensitive_staged_paths(
                {
                    "gh_config_dir": str(root / "gh_config"),
                    "jira_config_file": str(jira_cfg),
                    "netrc": str(netrc),
                }
            )

            self.assertFalse((root / "gh_config").exists())
            self.assertFalse((root / "jira_config").exists())
            self.assertFalse((root / "netrc").exists())
        finally:
            shutil.rmtree(root, ignore_errors=True)


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

    def test_review_templates_use_review_intelligence_placeholder_instead_of_hardcoded_tools(self) -> None:
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
            self.assertNotIn(".reviewflow/context", text)
            self.assertIn("$REVIEW_INTELLIGENCE_GUIDANCE", text)
            self.assertNotIn("gh pr view", text)
            self.assertNotIn("./rf-jira", text)
            self.assertNotIn("REVIEWFLOW_CRAWL_ALLOW_HOSTS", text)
            self.assertNotIn("./rf-fetch-url", text)

    def test_review_templates_use_plain_code_under_review_wording(self) -> None:
        normal = (ROOT / "prompts" / "mrereview_gh_local.md").read_text(encoding="utf-8")
        self.assertIn("Treat the sandbox checkout as the code under review", normal)
        self.assertNotIn("codebase-under-review (CURe)", normal)

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

    def test_chunkhound_prompt_contract_table_matches_story_04_matrix(self) -> None:
        expected = {
            "default.md": ("required", "required"),
            "mrereview_gh_local.md": ("required", "required"),
            "mrereview_gh_local_big.md": ("required", "required"),
            "mrereview_gh_local_big_followup.md": ("required", "required"),
            "mrereview_gh_local_big_plan.md": ("required", "required"),
            "mrereview_gh_local_followup.md": ("required", "guidance"),
            "mrereview_gh_local_big_step.md": ("required", "guidance"),
            "mrereview_gh_local_big_synth.md": ("conditional", "conditional"),
        }

        contracts = cure_flows.chunkhound_prompt_contracts()
        self.assertEqual(set(contracts), set(expected))

        for name, (search_requirement, code_research_requirement) in expected.items():
            contract = contracts[name]
            self.assertEqual(contract.search_requirement, search_requirement)
            self.assertEqual(contract.code_research_requirement, code_research_requirement)
            self.assertEqual(contract.availability_proof, "real_tool_call")
            self.assertEqual(contract.resource_discovery_rule, "neutral_expected_empty")
            self.assertEqual(cure_flows.chunkhound_prompt_contract_for_template(name), contract)

        self.assertIsNone(cure_flows.chunkhound_prompt_contract_for_template("mrereview_zip.md"))

    def test_chunkhound_backed_prompts_treat_resource_discovery_as_neutral(self) -> None:
        prompt_paths = [
            ROOT / "prompts" / "default.md",
            ROOT / "prompts" / "mrereview_gh_local.md",
            ROOT / "prompts" / "mrereview_gh_local_big.md",
            ROOT / "prompts" / "mrereview_gh_local_followup.md",
            ROOT / "prompts" / "mrereview_gh_local_big_followup.md",
            ROOT / "prompts" / "mrereview_gh_local_big_plan.md",
            ROOT / "prompts" / "mrereview_gh_local_big_step.md",
            ROOT / "prompts" / "mrereview_gh_local_big_synth.md",
        ]
        for path in prompt_paths:
            text = path.read_text(encoding="utf-8")
            self.assertIn(
                "Do not use `list_mcp_resources` or `list_mcp_resource_templates` as the ChunkHound availability check.",
                text,
            )
            self.assertIn("ChunkHound is a tools-first MCP server", text)
            self.assertIn("empty resource/template results are expected and are not an outage signal", text)
            self.assertIn(
                "Availability is proven only by a successful `search` or `code_research` tool call.",
                text,
            )

    def test_chunkhound_prompt_contract_wording_matches_per_template_requirements(self) -> None:
        prompt_texts = {
            "default.md": (ROOT / "prompts" / "default.md").read_text(encoding="utf-8"),
            "mrereview_gh_local.md": (ROOT / "prompts" / "mrereview_gh_local.md").read_text(
                encoding="utf-8"
            ),
            "mrereview_gh_local_big.md": (
                ROOT / "prompts" / "mrereview_gh_local_big.md"
            ).read_text(encoding="utf-8"),
            "mrereview_gh_local_followup.md": (
                ROOT / "prompts" / "mrereview_gh_local_followup.md"
            ).read_text(encoding="utf-8"),
            "mrereview_gh_local_big_followup.md": (
                ROOT / "prompts" / "mrereview_gh_local_big_followup.md"
            ).read_text(encoding="utf-8"),
            "mrereview_gh_local_big_plan.md": (
                ROOT / "prompts" / "mrereview_gh_local_big_plan.md"
            ).read_text(encoding="utf-8"),
            "mrereview_gh_local_big_step.md": (
                ROOT / "prompts" / "mrereview_gh_local_big_step.md"
            ).read_text(encoding="utf-8"),
            "mrereview_gh_local_big_synth.md": (
                ROOT / "prompts" / "mrereview_gh_local_big_synth.md"
            ).read_text(encoding="utf-8"),
        }

        self.assertIn(
            "Requirement: use `search` at least once; use `code_research` at least once.",
            prompt_texts["default.md"],
        )
        self.assertNotIn("if any cross-file behavior is discussed", prompt_texts["default.md"])

        self.assertIn(
            "Run at least one `code_research` query for cross-file/architecture understanding.",
            prompt_texts["mrereview_gh_local.md"],
        )
        self.assertIn(
            "Run at least one `code_research` query for cross-file/architecture understanding.",
            prompt_texts["mrereview_gh_local_big.md"],
        )
        self.assertIn(
            "Run at least one `code_research` query for cross-file/architecture understanding.",
            prompt_texts["mrereview_gh_local_big_followup.md"],
        )
        self.assertIn(
            "Run at least one `code_research` query for cross-file/architecture understanding.",
            prompt_texts["mrereview_gh_local_big_plan.md"],
        )
        self.assertIn(
            "Use `code_research` for cross-file/architecture understanding when needed.",
            prompt_texts["mrereview_gh_local_followup.md"],
        )
        self.assertIn(
            "If this step is cross-file/architectural, also run a `code_research` query.",
            prompt_texts["mrereview_gh_local_big_step.md"],
        )
        self.assertIn(
            "If you still need to confirm anything before deciding, use ChunkHound MCP tools (`search` / `code_research`) rather than guessing.",
            prompt_texts["mrereview_gh_local_big_synth.md"],
        )
        self.assertNotIn("Run at least one `search` query", prompt_texts["mrereview_gh_local_big_synth.md"])

    def test_zip_template_discourages_file_writes_and_fenced_output(self) -> None:
        zip_template = (ROOT / "prompts" / "mrereview_zip.md").read_text(encoding="utf-8")
        self.assertIn("Do not create, edit, or move any files.", zip_template)
        self.assertIn("CURe will save your final response", zip_template)
        self.assertIn("Do not wrap the response in a fenced code block.", zip_template)
        self.assertNotIn("Write the final result to:", zip_template)
        self.assertNotIn("```markdown", zip_template)
        self.assertIn("## Business / Product Assessment", zip_template)
        self.assertIn("## Technical Assessment", zip_template)
        self.assertNotIn("**Decision**:", zip_template)

    def test_review_templates_keep_abort_gate_tool_neutral(self) -> None:
        prompt_paths = [
            ROOT / "prompts" / "mrereview_gh_local.md",
            ROOT / "prompts" / "mrereview_gh_local_big.md",
            ROOT / "prompts" / "mrereview_gh_local_followup.md",
            ROOT / "prompts" / "mrereview_gh_local_big_followup.md",
            ROOT / "prompts" / "mrereview_gh_local_big_plan.md",
        ]
        for path in prompt_paths:
            text = path.read_text(encoding="utf-8")
            self.assertIn("required intelligence read fails", text)
            self.assertIn("$REVIEW_INTELLIGENCE_GUIDANCE", text)
            self.assertNotIn("`gh`/`jira`", text)
            self.assertNotIn("Jira key", text)

    def test_review_templates_use_generic_sandbox_guardrail(self) -> None:
        prompt_paths = [
            ROOT / "prompts" / "mrereview_gh_local.md",
            ROOT / "prompts" / "mrereview_gh_local_big.md",
            ROOT / "prompts" / "mrereview_gh_local_followup.md",
            ROOT / "prompts" / "mrereview_gh_local_big_followup.md",
            ROOT / "prompts" / "mrereview_gh_local_big_plan.md",
            ROOT / "prompts" / "mrereview_gh_local_big_step.md",
            ROOT / "prompts" / "mrereview_gh_local_big_synth.md",
        ]
        for path in prompt_paths:
            text = path.read_text(encoding="utf-8")
            self.assertIn("outside the sandbox checkout", text)
            self.assertIn("$REVIEWFLOW_WORK_DIR", text)

    def test_multipass_grounding_prompts_require_parseable_citation_suffixes(self) -> None:
        step_text = (ROOT / "prompts" / "mrereview_gh_local_big_step.md").read_text(encoding="utf-8")
        synth_text = (ROOT / "prompts" / "mrereview_gh_local_big_synth.md").read_text(encoding="utf-8")
        self.assertIn("Evidence:", step_text)
        self.assertIn("relative/path:line", step_text)
        self.assertIn("Sources:", synth_text)
        self.assertIn("review.step-XX.md:line", synth_text)

    def test_review_templates_emit_dual_axis_scope_split_format(self) -> None:
        prompt_paths = [
            ROOT / "prompts" / "default.md",
            ROOT / "prompts" / "mrereview_gh_local.md",
            ROOT / "prompts" / "mrereview_gh_local_big.md",
            ROOT / "prompts" / "mrereview_gh_local_followup.md",
            ROOT / "prompts" / "mrereview_gh_local_big_followup.md",
            ROOT / "prompts" / "mrereview_gh_local_big_synth.md",
            ROOT / "prompts" / "mrereview_zip.md",
        ]
        for path in prompt_paths:
            text = path.read_text(encoding="utf-8")
            self.assertIn("Business / Product Assessment", text)
            self.assertIn("Technical Assessment", text)
            self.assertIn("**Verdict**:", text)
            self.assertIn("### Strengths", text)
            self.assertIn("### In Scope Issues", text)
            self.assertIn("### Out of Scope Issues", text)
            self.assertIn("### Reusability", text)
            self.assertNotIn("**Strengths**:", text)
            self.assertNotIn("**Decision**:", text)

    def test_abort_review_markdown_uses_heading_sections(self) -> None:
        text = rf.build_abort_review_markdown(reason="bad auth")
        self.assertIn("### Strengths", text)
        self.assertIn("### In Scope Issues", text)
        self.assertIn("### Out of Scope Issues", text)
        self.assertIn("### Reusability", text)
        self.assertNotIn("**Strengths**:", text)

    def test_review_templates_define_scope_per_assessment_axis(self) -> None:
        prompt_paths = [
            ROOT / "prompts" / "default.md",
            ROOT / "prompts" / "mrereview_gh_local.md",
            ROOT / "prompts" / "mrereview_gh_local_big.md",
            ROOT / "prompts" / "mrereview_gh_local_followup.md",
            ROOT / "prompts" / "mrereview_gh_local_big_followup.md",
            ROOT / "prompts" / "mrereview_gh_local_big_synth.md",
            ROOT / "prompts" / "mrereview_zip.md",
        ]
        for path in prompt_paths:
            text = path.read_text(encoding="utf-8")
            self.assertIn("For `Business / Product Assessment`, `In Scope` means", text)
            self.assertIn("For `Technical Assessment`, `In Scope` means", text)
            self.assertIn(
                "The same issue may be `In Scope` for business/product and `Out of Scope` for technical",
                text,
            )
            self.assertNotIn("`In Scope` means the PR directly owns the behavior/code in question.", text)

    def test_review_docs_explain_section_relative_scope(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("uses product/ticket scope", readme)
        self.assertIn("uses implementation scope", readme)


class PromptResourceTests(unittest.TestCase):
    def test_load_builtin_prompt_text_works_outside_repo_root(self) -> None:
        old_cwd = Path.cwd()
        try:
            os.chdir("/")
            text = rf.load_builtin_prompt_text("mrereview_gh_local.md")
        finally:
            os.chdir(old_cwd)
        self.assertIn("$REVIEW_INTELLIGENCE_GUIDANCE", text)
        self.assertIn("ChunkHound MCP", text)


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

    def test_parse_multipass_plan_json_accepts_ticket_keys_alias(self) -> None:
        text = "\n".join(
            [
                "```json",
                json.dumps(
                    {
                        "abort": False,
                        "abort_reason": None,
                        "ticket_keys": ["ABC-1"],
                        "steps": [
                            {"id": "01", "title": "T", "focus": "F"},
                        ],
                    }
                ),
                "```",
            ]
        )
        plan = rf.parse_multipass_plan_json(text)
        self.assertEqual(plan["jira_keys"], ["ABC-1"])

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


class MultipassGroundingValidationTests(unittest.TestCase):
    def test_validate_multipass_step_grounding_accepts_valid_repo_citation(self) -> None:
        root = ROOT / ".tmp_test_step_grounding_valid"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_dir = root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            (repo_dir / "pkg").mkdir(parents=True, exist_ok=True)
            (repo_dir / "pkg" / "module.py").write_text("a\nb\nc\n", encoding="utf-8")
            artifact = root / "review.step-01.md"
            artifact.write_text(
                "\n".join(
                    [
                        "### Step Result: 01 — API review",
                        "**Focus**: grounding",
                        "",
                        "### Steps taken",
                        "- checked module",
                        "",
                        "### Findings",
                        "- Input is unchecked. Evidence: `pkg/module.py:2`",
                        "",
                        "### Suggested actions",
                        "- Add validation",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            result = rf.validate_multipass_step_grounding(
                artifact_path=artifact,
                repo_dir=repo_dir,
                step_index=1,
            )
            self.assertTrue(result["valid"])
            self.assertEqual(result["errors"], [])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_multipass_step_grounding_rejects_missing_repo_citation(self) -> None:
        root = ROOT / ".tmp_test_step_grounding_invalid"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo_dir = root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            artifact = root / "review.step-01.md"
            artifact.write_text(
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
            result = rf.validate_multipass_step_grounding(
                artifact_path=artifact,
                repo_dir=repo_dir,
                step_index=1,
            )
            self.assertFalse(result["valid"])
            self.assertIn("missing a repo citation", "\n".join(result["errors"]))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validate_multipass_synth_grounding_accepts_step_artifact_sources(self) -> None:
        root = ROOT / ".tmp_test_synth_grounding_valid"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            step_output = root / "review.step-01.md"
            step_output.write_text(
                "\n".join(
                    [
                        "### Step Result: 01 — API review",
                        "**Focus**: grounding",
                        "",
                        "### Findings",
                        "- Something important. Evidence: `pkg/module.py:2`",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
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
                        "- Business value is clear. Sources: `review.step-01.md:5`",
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
                        "- Technical read happened. Sources: `review.step-01.md:5`",
                        "",
                        "### In Scope Issues",
                        "- Provenance is present. Sources: `review.step-01.md:5`",
                        "",
                        "### Out of Scope Issues",
                        "- None.",
                        "",
                        "### Reusability",
                        "- Artifact stays inspectable. Sources: `review.step-01.md:5`",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            result = rf.validate_multipass_synth_grounding(
                artifact_path=review_md,
                step_outputs=[step_output],
            )
            self.assertTrue(result["valid"])
            self.assertEqual(result["errors"], [])
        finally:
            shutil.rmtree(root, ignore_errors=True)


class HistoricalReviewsTests(unittest.TestCase):
    class _FakeTty(StringIO):
        def isatty(self) -> bool:
            return True

    def test_extract_review_verdicts_from_markdown_reads_two_sections(self) -> None:
        md = _sectioned_review_markdown(business="APPROVE", technical="REQUEST CHANGES")
        verdicts = rf.extract_review_verdicts_from_markdown(md)
        self.assertEqual(verdicts, _verdicts("APPROVE", "REQUEST CHANGES"))

    def test_extract_review_verdicts_from_markdown_falls_back_to_legacy_decision(self) -> None:
        md = "**Summary**: x\n**Decision**: [approve]\n"
        verdicts = rf.extract_review_verdicts_from_markdown(md)
        self.assertEqual(verdicts, _verdicts("APPROVE"))

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

    def test_resolve_codex_summary_prefers_resolved_model_and_effort(self) -> None:
        summary = rf.resolve_codex_summary(
            {
                "codex": {
                    "config": {
                        "resolved": {
                            "model": "gpt-5.3-codex",
                            "model_reasoning_effort": "high",
                            "plan_mode_reasoning_effort": "xhigh",
                        }
                    }
                }
            }
        )
        self.assertEqual(summary, "llm=legacy_codex/gpt-5.3-codex/high")

    def test_resolve_codex_summary_falls_back_to_flags(self) -> None:
        summary = rf.resolve_codex_summary(
            {
                "codex": {
                    "flags": [
                        "-m",
                        "gpt-5.3-codex-spark",
                        "-c",
                        'model_reasoning_effort="medium"',
                    ]
                }
            }
        )
        self.assertEqual(summary, "llm=legacy_codex/gpt-5.3-codex-spark/medium")

    def test_scan_completed_sessions_for_pr_filters_and_sorts(self) -> None:
        root = ROOT / ".tmp_test_review_sandboxes"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)

            pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=1)

            s1 = root / "s1"
            s1.mkdir()
            (s1 / "review.md").write_text(_sectioned_review_markdown(business="REJECT", technical="REJECT"), encoding="utf-8")
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
                        "codex": {
                            "flags": [
                                "-m",
                                "gpt-5.2",
                                "-c",
                                'model_reasoning_effort="medium"',
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )

            s2 = root / "s2"
            s2.mkdir()
            (s2 / "review.md").write_text(
                _sectioned_review_markdown(business="APPROVE", technical="REQUEST CHANGES"),
                encoding="utf-8",
            )
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
                        "codex": {
                            "config": {
                                "resolved": {
                                    "model": "gpt-5.3-codex",
                                    "model_reasoning_effort": "high",
                                }
                            }
                        },
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
            self.assertEqual(sessions[0].verdicts, _verdicts("APPROVE", "REQUEST CHANGES"))
            self.assertEqual(sessions[1].verdicts, _verdicts("REJECT"))
            self.assertEqual(sessions[0].codex_summary, "llm=legacy_codex/gpt-5.3-codex/high")
            self.assertEqual(sessions[1].codex_summary, "llm=legacy_codex/gpt-5.2/medium")
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
                verdicts=_verdicts("APPROVE", "REQUEST CHANGES"),
                codex_summary="codex=gpt-5.3-codex/high",
                review_head_sha="2222222222222222222222222222222222222222",
            )
        ]
        stdout = StringIO()
        with mock.patch("sys.stdout", stdout):
            rf._print_historical_sessions(sessions)
        rendered = stdout.getvalue()
        self.assertIn(
            "01  2026-03-04T01:00:00+00:00  biz=APPROVE tech=REQUEST CHANGES  codex=gpt-5.3-codex/high  s2",
            rendered,
        )
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
                verdicts=_verdicts("APPROVE", "REQUEST CHANGES"),
                codex_summary="codex=gpt-5.3-codex/high",
                review_head_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            ),
            rf.HistoricalReviewSession(
                session_id="older-a",
                session_dir=ROOT / "older-a",
                review_md_path=ROOT / "older-a" / "review.md",
                created_at="2026-03-04T00:00:00+00:00",
                completed_at="2026-03-04T01:00:00+00:00",
                verdicts=_verdicts("REJECT"),
                codex_summary="codex=gpt-5.2/medium",
                review_head_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            ),
            rf.HistoricalReviewSession(
                session_id="only-b",
                session_dir=ROOT / "only-b",
                review_md_path=ROOT / "only-b" / "review.md",
                created_at="2026-03-03T00:00:00+00:00",
                completed_at="2026-03-03T01:00:00+00:00",
                verdicts=_verdicts("REQUEST CHANGES", "APPROVE"),
                codex_summary="codex=gpt-5.1/low",
                review_head_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            ),
            rf.HistoricalReviewSession(
                session_id="unknown",
                session_dir=ROOT / "unknown",
                review_md_path=ROOT / "unknown" / "review.md",
                created_at="2026-03-02T00:00:00+00:00",
                completed_at="2026-03-02T01:00:00+00:00",
                verdicts=_verdicts("APPROVE"),
                codex_summary="codex=?",
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
        self.assertIn(
            "  1) 2026-03-05T01:00:00+00:00  biz=APPROVE tech=REQUEST CHANGES  codex=gpt-5.3-codex/high",
            rendered,
        )
        self.assertIn(
            "  2) 2026-03-04T01:00:00+00:00  biz=REJECT tech=REJECT  codex=gpt-5.2/medium",
            rendered,
        )
        self.assertIn(
            "  3) 2026-03-03T01:00:00+00:00  biz=REQUEST CHANGES tech=APPROVE  codex=gpt-5.1/low",
            rendered,
        )
        self.assertIn("  4) 2026-03-02T01:00:00+00:00  biz=APPROVE tech=APPROVE  codex=?", rendered)
        self.assertNotIn("\x1b[", rendered)

    def test_choose_historical_session_tty_colorizes_group_headers_when_enabled(self) -> None:
        sessions = [
            rf.HistoricalReviewSession(
                session_id="s1",
                session_dir=ROOT / "s1",
                review_md_path=ROOT / "s1" / "review.md",
                created_at="2026-03-05T00:00:00+00:00",
                completed_at="2026-03-05T01:00:00+00:00",
                verdicts=_verdicts("APPROVE"),
                codex_summary="codex=gpt-5.3-codex/high",
                review_head_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            ),
            rf.HistoricalReviewSession(
                session_id="s2",
                session_dir=ROOT / "s2",
                review_md_path=ROOT / "s2" / "review.md",
                created_at="2026-03-04T00:00:00+00:00",
                completed_at="2026-03-04T01:00:00+00:00",
                verdicts=_verdicts("REJECT"),
                codex_summary="codex=gpt-5.2/medium",
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
                verdicts=_verdicts("APPROVE"),
                codex_summary="codex=gpt-5.3-codex/high",
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
                        "codex": {
                            "resume": {"command": "cd /tmp/s1 && codex resume s1"},
                            "config": {
                                "resolved": {
                                    "model": "gpt-5.2",
                                    "model_reasoning_effort": "medium",
                                }
                            },
                        },
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
                        "codex": {
                            "resume": {"command": "cd /tmp/s2 && codex resume s2"},
                            "config": {
                                "resolved": {
                                    "model": "gpt-5.3-codex",
                                    "model_reasoning_effort": "high",
                                }
                            },
                        },
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
            self.assertEqual([s.session_id for s in sessions], ["s3", "s2", "s1"])
            self.assertFalse(sessions[0].supports_resume)
            self.assertEqual(sessions[1].repo_slug, "beta/app#7")
            self.assertEqual(sessions[1].resume_command, "cd /tmp/s2 && codex resume s2")
            self.assertEqual(sessions[1].codex_summary, "llm=legacy_codex/gpt-5.3-codex/high")
            self.assertEqual(sessions[2].codex_summary, "llm=legacy_codex/gpt-5.2/medium")
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
                        "codex": {
                            "resume": {"command": "cd /tmp/s1 && codex resume s1", "session_id": "s1"},
                            "config": {
                                "resolved": {
                                    "model": "gpt-5.3-codex",
                                    "model_reasoning_effort": "high",
                                }
                            },
                        },
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
                mock.patch.object(rf, "ensure_review_config"),
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(base_config_path=cfg),
                        {"chunkhound": {"base_config_path": str(cfg)}},
                        {},
                    ),
                ),
                mock.patch.object(
                    rf,
                    "chunkhound_env",
                    return_value={"CHUNKHOUND_EMBEDDING__API_KEY": "test-key"},  # pragma: allowlist secret
                ),
                mock.patch.object(
                    rf,
                    "prepare_review_agent_runtime",
                    return_value={"env": {"CHUNKHOUND_EMBEDDING__API_KEY": "test-key"}, "metadata": {"provider": "codex"}},  # pragma: allowlist secret
                ),
                mock.patch.object(rf, "run_interactive_resume_command", return_value=7) as runner,
            ):
                rc = rf.interactive_flow(argparse.Namespace(), paths=paths, stdin=stdin, stderr=stderr)

            self.assertEqual(rc, 7)
            runner.assert_called_once()
            self.assertIn("codex resume", runner.call_args.args[0])
            self.assertIn("s1", runner.call_args.args[0])
            self.assertNotIn(f"--add-dir {root}", runner.call_args.args[0])
            self.assertEqual(runner.call_args.kwargs["env"]["CHUNKHOUND_EMBEDDING__API_KEY"], "test-key")  # pragma: allowlist secret
            self.assertIn("llm=legacy_codex/gpt-5.3-codex/high", stderr.getvalue())
            self.assertIn(str(s1 / "review.md"), stderr.getvalue())
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_interactive_flow_recovers_when_only_llm_resume_metadata_exists(self) -> None:
        root = ROOT / ".tmp_test_interactive_flow_llm_resume_root"
        cfg = ROOT / ".tmp_test_interactive_flow_llm_resume_cfg.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text("{}", encoding="utf-8")

            s1 = root / "s1"
            s1.mkdir()
            (s1 / "repo").mkdir()
            (s1 / "work").mkdir()
            review_md = s1 / "review.md"
            review_md.write_text("**Decision**: APPROVE\n", encoding="utf-8")
            meta_path = s1 / "meta.json"
            meta_path.write_text(
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
                        "llm": {
                            "provider": "codex",
                            "capabilities": {"supports_resume": True},
                            "resume": {
                                "command": "cd /tmp/s1 && codex resume s1",
                                "session_id": "s1",
                                "cwd": str(s1 / "repo"),
                            },
                        },
                        "codex": {
                            "config": {
                                "resolved": {
                                    "model": "gpt-5.3-codex",
                                    "model_reasoning_effort": "high",
                                }
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            paths = rf.ReviewflowPaths(
                sandbox_root=root,
                cache_root=ROOT / ".tmp_test_interactive_flow_llm_resume_cache",
                review_chunkhound_config=cfg,
                main_chunkhound_config=cfg,
            )
            stdin = self._FakeTty("1\n")
            stderr = self._FakeTty()

            with (
                mock.patch.object(rf, "ensure_review_config"),
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(base_config_path=cfg),
                        {"chunkhound": {"base_config_path": str(cfg)}},
                        {},
                    ),
                ),
                mock.patch.object(
                    rf,
                    "chunkhound_env",
                    return_value={"CHUNKHOUND_EMBEDDING__API_KEY": "test-key"},  # pragma: allowlist secret
                ),
                mock.patch.object(
                    rf,
                    "prepare_review_agent_runtime",
                    return_value={"env": {"CHUNKHOUND_EMBEDDING__API_KEY": "test-key"}, "metadata": {"provider": "codex"}},  # pragma: allowlist secret
                ),
                mock.patch.object(rf, "run_interactive_resume_command", return_value=0) as runner,
            ):
                rc = rf.interactive_flow(argparse.Namespace(), paths=paths, stdin=stdin, stderr=stderr)

            self.assertEqual(rc, 0)
            runner.assert_called_once()
            self.assertIn("codex resume", runner.call_args.args[0])
            repaired = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(repaired["codex"]["resume"]["session_id"], "s1")
            self.assertIn("codex resume", repaired["codex"]["resume"]["command"])
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_interactive_flow_repairs_saved_subagent_resume_to_parent_session(self) -> None:
        root = ROOT / ".tmp_test_interactive_subagent_resume_root"
        cfg = ROOT / ".tmp_test_interactive_subagent_resume_cfg.json"
        fake_home = ROOT / ".tmp_test_interactive_subagent_resume_home"
        try:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(fake_home, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text("{}", encoding="utf-8")
            day_dir = fake_home / ".codex" / "sessions" / "2026" / "03" / "10"
            day_dir.mkdir(parents=True, exist_ok=True)

            s1 = root / "s1"
            s1.mkdir()
            (s1 / "repo").mkdir()
            (s1 / "work").mkdir()
            review_md = s1 / "review.md"
            review_md.write_text("**Decision**: APPROVE\n", encoding="utf-8")
            meta_path = s1 / "meta.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "session_id": "s1",
                        "status": "done",
                        "host": "github.com",
                        "owner": "example-org",
                        "repo": "example-repo",
                        "number": 78,
                        "created_at": "2026-03-10T10:05:13+00:00",
                        "completed_at": "2026-03-10T10:21:57+00:00",
                        "paths": {
                            "repo_dir": str(s1 / "repo"),
                            "work_dir": str(s1 / "work"),
                            "review_md": str(review_md),
                        },
                        "codex": {
                            "resume": {
                                "command": "cd /tmp/s1 && codex resume child-session",
                                "session_id": "child-session",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            (day_dir / "rollout-parent.jsonl").write_text(
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {
                            "id": "parent-session",
                            "timestamp": "2026-03-10T10:05:32+00:00",
                            "cwd": str((s1 / "repo").resolve()),
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
                            "cwd": str((s1 / "repo").resolve()),
                            "originator": "codex_exec",
                            "source": {"subagent": {"thread_spawn": {"parent_thread_id": "parent-session"}}},
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            paths = rf.ReviewflowPaths(
                sandbox_root=root,
                cache_root=ROOT / ".tmp_test_interactive_subagent_resume_cache",
                review_chunkhound_config=cfg,
                main_chunkhound_config=cfg,
            )
            stdin = self._FakeTty("1\n")
            stderr = self._FakeTty()

            with (
                mock.patch.object(rf, "ensure_review_config"),
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(base_config_path=cfg),
                        {"chunkhound": {"base_config_path": str(cfg)}},
                        {},
                    ),
                ),
                mock.patch.object(
                    rf,
                    "chunkhound_env",
                    return_value={"CHUNKHOUND_EMBEDDING__API_KEY": "test-key"},  # pragma: allowlist secret
                ),
                mock.patch.object(rf, "real_user_home_dir", return_value=fake_home),
                mock.patch.object(
                    rf,
                    "prepare_review_agent_runtime",
                    return_value={"env": {"CHUNKHOUND_EMBEDDING__API_KEY": "test-key"}, "metadata": {"provider": "codex"}},  # pragma: allowlist secret
                ),
                mock.patch.object(rf, "run_interactive_resume_command", return_value=0) as runner,
            ):
                rc = rf.interactive_flow(
                    argparse.Namespace(target="https://github.com/example-org/example-repo/pull/78"),
                    paths=paths,
                    stdin=stdin,
                    stderr=stderr,
                )

            self.assertEqual(rc, 0)
            runner.assert_called_once()
            self.assertIn("parent-session", runner.call_args.args[0])
            self.assertNotIn("child-session", runner.call_args.args[0])
            repaired = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(repaired["codex"]["resume"]["session_id"], "parent-session")
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(fake_home, ignore_errors=True)
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
                        "owner": "example-org",
                        "repo": "example-repo",
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
                        "owner": "example-org",
                        "repo": "example-repo",
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
            args = argparse.Namespace(target="https://github.com/example-org/example-repo/pull/86")

            with (
                mock.patch.object(rf, "ensure_review_config"),
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(base_config_path=cfg),
                        {"chunkhound": {"base_config_path": str(cfg)}},
                        {},
                    ),
                ),
                mock.patch.object(
                    rf,
                    "chunkhound_env",
                    return_value={"CHUNKHOUND_EMBEDDING__API_KEY": "test-key"},  # pragma: allowlist secret
                ),
                mock.patch.object(
                    rf,
                    "prepare_review_agent_runtime",
                    return_value={"env": {"CHUNKHOUND_EMBEDDING__API_KEY": "test-key"}, "metadata": {"provider": "codex"}},  # pragma: allowlist secret
                ),
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
                mock.patch.object(rf, "ensure_review_config"),
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(base_config_path=cfg),
                        {"chunkhound": {"base_config_path": str(cfg)}},
                        {},
                    ),
                ),
                mock.patch.object(
                    rf,
                    "chunkhound_env",
                    return_value={"CHUNKHOUND_EMBEDDING__API_KEY": "test-key"},  # pragma: allowlist secret
                ),
                mock.patch.object(
                    rf,
                    "prepare_review_agent_runtime",
                    return_value={"env": {"CHUNKHOUND_EMBEDDING__API_KEY": "test-key"}, "metadata": {"provider": "codex"}},  # pragma: allowlist secret
                ),
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
                        "owner": "example-org",
                        "repo": "example-repo",
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
                mock.patch.object(rf, "ensure_review_config"),
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(base_config_path=cfg),
                        {"chunkhound": {"base_config_path": str(cfg)}},
                        {},
                    ),
                ),
                mock.patch.object(
                    rf,
                    "chunkhound_env",
                    return_value={"CHUNKHOUND_EMBEDDING__API_KEY": "test-key"},  # pragma: allowlist secret
                ),
                mock.patch.object(rf, "real_user_home_dir", return_value=fake_home),
                mock.patch.object(
                    rf,
                    "prepare_review_agent_runtime",
                    return_value={"env": {"CHUNKHOUND_EMBEDDING__API_KEY": "test-key"}, "metadata": {"provider": "codex"}},  # pragma: allowlist secret
                ),
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
                mock.patch.object(rf, "ensure_review_config"),
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(base_config_path=cfg),
                        {"chunkhound": {"base_config_path": str(cfg)}},
                        {},
                    ),
                ),
                mock.patch.object(
                    rf,
                    "chunkhound_env",
                    return_value={"CHUNKHOUND_EMBEDDING__API_KEY": "test-key"},  # pragma: allowlist secret
                ),
                mock.patch.object(rf, "real_user_home_dir", return_value=fake_home),
                mock.patch.object(
                    rf,
                    "prepare_review_agent_runtime",
                    return_value={"env": {"CHUNKHOUND_EMBEDDING__API_KEY": "test-key"}, "metadata": {"provider": "codex"}},  # pragma: allowlist secret
                ),
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
                "verdicts": {"business": "APPROVE", "technical": "REQUEST CHANGES"},
                "target_head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            }
        ]
        plain = rf.build_zip_input_display_lines(inputs_meta=inputs)
        markdown = rf.build_zip_input_display_lines(inputs_meta=inputs, markdown=True)
        self.assertEqual(
            plain,
            [
                "- s1 [review] biz=APPROVE tech=REQUEST CHANGES 2026-03-04T01:00:00+00:00 head bbbbbbbbbbbb /tmp/s1/review.md"
            ],
        )
        self.assertEqual(
            markdown,
            [
                "- `s1` • `review` • biz=APPROVE tech=REQUEST CHANGES • 2026-03-04T01:00:00+00:00 • head `bbbbbbbbbbbb` • `/tmp/s1/review.md`"
            ],
        )

    def test_append_zip_inputs_provenance_appends_section(self) -> None:
        md = ROOT / ".tmp_test_zip_append.md"
        try:
            md.write_text(
                _sectioned_review_markdown(business="APPROVE", technical="REQUEST CHANGES"),
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
                        "verdicts": {"business": "APPROVE", "technical": "REQUEST CHANGES"},
                        "target_head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    }
                ],
            )
            text = md.read_text(encoding="utf-8")
            self.assertIn("## Inputs Processed", text)
            self.assertIn("`s1`", text)
            self.assertIn("biz=APPROVE tech=REQUEST CHANGES", text)
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

            # Session s4: done, review targets head_sha but newer followup is REJECT => review should still be selected.
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
                                "head_sha_after": head_sha,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            # Session s5: done, only matching artifact is REJECT => excluded entirely.
            s5 = root / "s5"
            s5.mkdir()
            (s5 / "review.md").write_text("**Decision**: REJECT\n", encoding="utf-8")
            (s5 / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s5",
                        "status": "done",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 9,
                        "head_sha": head_sha,
                        "created_at": "2026-03-07T00:00:00+00:00",
                        "completed_at": "2026-03-07T00:10:00+00:00",
                        "paths": {"review_md": str(s5 / "review.md")},
                    }
                ),
                encoding="utf-8",
            )

            sources = rf.select_zip_sources_for_pr_head(sandbox_root=root, pr=pr, head_sha=head_sha)
            self.assertEqual([s.session_id for s in sources], ["s4", "s3", "s2"])
            self.assertEqual(sources[0].kind, "review")
            self.assertEqual(sources[1].kind, "followup")
            self.assertEqual(sources[1].verdicts, _verdicts("APPROVE"))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_select_zip_sources_for_pr_head_skips_dual_axis_reject_artifacts(self) -> None:
        root = ROOT / ".tmp_test_zip_reject_root"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)

            pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=9)
            head_sha = "cccccccccccccccccccccccccccccccccccccccc"

            s1 = root / "s1"
            s1.mkdir()
            review_md = s1 / "review.md"
            review_md.write_text(
                _sectioned_review_markdown(business="APPROVE", technical="REJECT"),
                encoding="utf-8",
            )
            (s1 / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s1",
                        "status": "done",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 9,
                        "head_sha": head_sha,
                        "created_at": "2026-03-08T00:00:00+00:00",
                        "completed_at": "2026-03-08T00:10:00+00:00",
                        "paths": {"review_md": str(review_md)},
                    }
                ),
                encoding="utf-8",
            )

            sources = rf.select_zip_sources_for_pr_head(sandbox_root=root, pr=pr, head_sha=head_sha)
            self.assertEqual(sources, [])
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
                    verdicts=_verdicts("APPROVE", "REQUEST CHANGES"),
                    target_head_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                ),
                rf.ZipSourceArtifact(
                    session_id="other-session",
                    session_dir=other_session,
                    kind="followup",
                    artifact_path=other_artifact,
                    completed_at="2026-03-05T01:00:00+00:00",
                    verdicts=_verdicts("REQUEST CHANGES", "REJECT"),
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

            def fake_run_codex_exec(**kwargs: object) -> rf.CodexRunResult:
                prompt = kwargs["prompt"]
                assert isinstance(prompt, str)
                prompts.append(prompt)
                output_path = kwargs["output_path"]
                assert isinstance(output_path, Path)
                output_path.write_text(
                    "```markdown\n" + _sectioned_review_markdown(
                        business="APPROVE",
                        technical="REQUEST CHANGES",
                    ) + "```\n",
                    encoding="utf-8",
                )
                return rf.CodexRunResult(resume=None)

            with (
                mock.patch.object(
                    rf,
                    "gh_api_json",
                    return_value={
                        "head": {"sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
                        "title": "Zip PR",
                    },
                ) as gh_api_json,
                mock.patch.object(rf, "require_gh_auth", side_effect=AssertionError("zip should use shared metadata helper")),
                mock.patch.object(rf, "select_zip_sources_for_pr_head", return_value=sources),
                mock.patch.object(rf, "resolve_codex_flags", return_value=([], {"resolved": {}})),
                mock.patch.object(rf, "codex_mcp_overrides_for_reviewflow", return_value=[]),
                mock.patch.object(
                    rf,
                    "prepare_review_agent_runtime",
                    return_value={
                        "env": {},
                        "metadata": {"provider": "codex"},
                        "codex_flags": [],
                        "dangerously_bypass_approvals_and_sandbox": False,
                        "add_dirs": [],
                    },
                ),
                mock.patch.object(rf, "run_codex_exec", side_effect=fake_run_codex_exec),
                mock.patch("sys.stdout", stdout),
                mock.patch("sys.stderr", stderr),
            ):
                rc = rf.zip_flow(args, paths=paths)

            self.assertEqual(rc, 0)
            gh_api_json.assert_called_once_with(
                host="github.com",
                path="repos/acme/repo/pulls/9",
                allow_public_fallback=True,
            )
            self.assertIn("zip selected 2 input artifact(s) for HEAD bbbbbbbbbbbb", stderr.getvalue())
            self.assertIn(
                "zip input host-session [review] biz=APPROVE tech=REQUEST CHANGES 2026-03-04T01:00:00+00:00 head bbbbbbbbbbbb",
                stderr.getvalue(),
            )
            self.assertIn(
                "zip input other-session [followup] biz=REQUEST CHANGES tech=REJECT 2026-03-05T01:00:00+00:00 head bbbbbbbbbbbb",
                stderr.getvalue(),
            )
            self.assertEqual(len(prompts), 1)
            self.assertIn("Do not create, edit, or move any files.", prompts[0])
            self.assertIn("Do not wrap the response in a fenced code block.", prompts[0])
            self.assertNotIn("Write the final result to:", prompts[0])
            self.assertNotIn("```markdown", prompts[0])
            self.assertIn("## Business / Product Assessment", prompts[0])
            self.assertIn("## Technical Assessment", prompts[0])

            output_md = Path(stdout.getvalue().strip())
            text = output_md.read_text(encoding="utf-8")
            self.assertFalse(text.startswith("```markdown"))
            self.assertIn("## Inputs Processed", text)
            self.assertIn("`host-session`", text)
            self.assertIn("`other-session`", text)
            self.assertIn("biz=APPROVE tech=REQUEST CHANGES", text)
            self.assertIn("head `bbbbbbbbbbbb`", text)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_zip_flow_non_github_host_still_fails_via_shared_metadata_contract(self) -> None:
        args = argparse.Namespace(
            pr_url="https://ghe.example.com/acme/repo/pull/9",
            codex_model=None,
            codex_effort=None,
            codex_plan_effort=None,
            ui="off",
            verbosity="normal",
            no_stream=False,
        )
        paths = rf.ReviewflowPaths(
            sandbox_root=ROOT,
            cache_root=ROOT,
            review_chunkhound_config=ROOT / ".tmp_cfg",
            main_chunkhound_config=ROOT / ".tmp_cfg2",
        )
        with (
            mock.patch.object(
                rf,
                "gh_api_json",
                side_effect=rf.ReviewflowError("`gh` is not authenticated for ghe.example.com."),
            ) as gh_api_json,
            mock.patch.object(rf, "require_gh_auth", side_effect=AssertionError("zip should not preflight gh auth")),
        ):
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.zip_flow(args, paths=paths)

        gh_api_json.assert_called_once_with(
            host="ghe.example.com",
            path="repos/acme/repo/pulls/9",
            allow_public_fallback=True,
        )
        self.assertIn("ghe.example.com", str(ctx.exception))


class FollowupAndResumeAuthPolicyTests(unittest.TestCase):
    def _write_session_meta(
        self,
        root: Path,
        *,
        session_id: str,
        host: str = "github.com",
        supports_resume: bool = True,
    ) -> Path:
        session_dir = root / session_id
        repo_dir = session_dir / "repo"
        work_dir = session_dir / "work"
        chunkhound_dir = work_dir / "chunkhound"
        repo_dir.mkdir(parents=True, exist_ok=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        chunkhound_dir.mkdir(parents=True, exist_ok=True)
        (chunkhound_dir / ".chunkhound.db").write_text("db", encoding="utf-8")
        (session_dir / "meta.json").write_text(
            json.dumps(
                {
                    "session_id": session_id,
                    "status": "error",
                    "host": host,
                    "owner": "acme",
                    "repo": "repo",
                    "number": 9,
                    "pr_url": f"https://{host}/acme/repo/pull/9",
                    "title": "Session PR",
                    "base_ref": "main",
                    "base_ref_for_review": "reviewflow_base__main",
                    "created_at": "2026-03-10T00:00:00+00:00",
                    "failed_at": "2026-03-10T00:05:00+00:00",
                    "llm": {
                        "provider": "codex",
                        "capabilities": {"supports_resume": supports_resume},
                    },
                    "notes": {"no_index": False},
                    "paths": {
                        "repo_dir": str(repo_dir),
                        "work_dir": str(work_dir),
                        "chunkhound_cwd": str(chunkhound_dir),
                        "chunkhound_db": str(chunkhound_dir / ".chunkhound.db"),
                        "chunkhound_config": str(chunkhound_dir / "chunkhound.json"),
                    },
                }
            ),
            encoding="utf-8",
        )
        return session_dir

    def test_resume_flow_does_not_require_gh_auth_before_local_resume_setup(self) -> None:
        root = ROOT / ".tmp_test_resume_public_auth_root"
        cfg = ROOT / ".tmp_test_resume_public_auth_cfg.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text("{}", encoding="utf-8")
            self._write_session_meta(root, session_id="resume-public")
            args = argparse.Namespace(
                session_id="resume-public",
                from_phase="plan",
                no_index=False,
                codex_model=None,
                codex_effort=None,
                codex_plan_effort=None,
                quiet=False,
                no_stream=True,
                ui="off",
                verbosity="normal",
            )
            paths = rf.ReviewflowPaths(
                sandbox_root=root,
                cache_root=ROOT / ".tmp_test_resume_public_auth_cache",
                review_chunkhound_config=cfg,
                main_chunkhound_config=cfg,
            )

            with (
                mock.patch.object(rf, "require_gh_auth", side_effect=AssertionError("resume should not preflight gh auth")),
                mock.patch.object(rf, "ensure_review_config", side_effect=RuntimeError("resume reached local setup")),
            ):
                with self.assertRaisesRegex(RuntimeError, "resume reached local setup"):
                    rf.resume_flow(args, paths=paths, config_path=cfg, codex_base_config_path=cfg)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_followup_no_update_does_not_require_gh_auth_before_local_setup(self) -> None:
        root = ROOT / ".tmp_test_followup_no_update_auth_root"
        cfg = ROOT / ".tmp_test_followup_no_update_auth_cfg.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text("{}", encoding="utf-8")
            self._write_session_meta(root, session_id="followup-no-update")
            args = argparse.Namespace(
                session_id="followup-no-update",
                no_update=True,
                codex_model=None,
                codex_effort=None,
                codex_plan_effort=None,
                quiet=False,
                no_stream=True,
                ui="off",
                verbosity="normal",
            )
            paths = rf.ReviewflowPaths(
                sandbox_root=root,
                cache_root=ROOT / ".tmp_test_followup_no_update_auth_cache",
                review_chunkhound_config=cfg,
                main_chunkhound_config=cfg,
            )

            with (
                mock.patch.object(rf, "require_gh_auth", side_effect=AssertionError("followup --no-update should not preflight gh auth")),
                mock.patch.object(rf, "ensure_review_config", side_effect=RuntimeError("followup reached local setup")),
            ):
                with self.assertRaisesRegex(RuntimeError, "followup reached local setup"):
                    rf.followup_flow(args, paths=paths, config_path=cfg, codex_base_config_path=cfg)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_followup_update_uses_checkout_helper_without_preflight_auth(self) -> None:
        root = ROOT / ".tmp_test_followup_update_checkout_root"
        cfg = ROOT / ".tmp_test_followup_update_checkout_cfg.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text("{}", encoding="utf-8")
            session_dir = self._write_session_meta(root, session_id="followup-update")
            args = argparse.Namespace(
                session_id="followup-update",
                no_update=False,
                codex_model=None,
                codex_effort=None,
                codex_plan_effort=None,
                quiet=False,
                no_stream=True,
                ui="off",
                verbosity="normal",
            )
            paths = rf.ReviewflowPaths(
                sandbox_root=root,
                cache_root=ROOT / ".tmp_test_followup_update_checkout_cache",
                review_chunkhound_config=cfg,
                main_chunkhound_config=cfg,
            )

            def fake_run_cmd(cmd: list[str], **_: object) -> mock.Mock:
                if cmd[:4] == ["git", "-C", str((session_dir / "repo").resolve()), "rev-parse"]:
                    return mock.Mock(stdout="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n")
                if cmd[:6] == ["git", "-C", str((session_dir / "repo").resolve()), "fetch", "--prune", "origin"]:
                    return mock.Mock(stdout="")
                raise AssertionError(f"unexpected command: {cmd}")

            with (
                mock.patch.object(rf, "require_gh_auth", side_effect=AssertionError("followup update should not preflight gh auth")),
                mock.patch.object(rf, "ensure_review_config"),
                mock.patch.object(
                    rf,
                    "load_chunkhound_runtime_config",
                    return_value=(
                        rf.ReviewflowChunkHoundConfig(base_config_path=cfg),
                        {"chunkhound": {"base_config_path": str(cfg)}},
                        {},
                    ),
                ),
                mock.patch.object(rf, "materialize_chunkhound_env_config"),
                mock.patch.object(
                    rf,
                    "load_review_intelligence_config",
                    return_value=(
                        rf.ReviewIntelligenceConfig(
                            tool_prompt_fragment="Use GitHub MCP first.",
                            policy_mode="cure_first_unrestricted",
                        ),
                        {"review_intelligence": {"tool_prompt_fragment": "Use GitHub MCP first."}},
                    ),
                ),
                mock.patch.object(rf, "require_builtin_review_intelligence"),
                mock.patch.object(rf, "resolve_llm_config_from_args", return_value=({"provider": "openai"}, {})),
                mock.patch.object(
                    rf,
                    "prepare_review_agent_runtime",
                    return_value={"env": {}, "codex_flags": [], "codex_config_overrides": []},
                ),
                mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd),
                mock.patch.object(
                    rf,
                    "checkout_pr_in_repo",
                    side_effect=RuntimeError("followup reached checkout helper"),
                ) as checkout_pr_in_repo,
            ):
                with self.assertRaisesRegex(RuntimeError, "followup reached checkout helper"):
                    rf.followup_flow(args, paths=paths, config_path=cfg, codex_base_config_path=cfg)

            checkout_pr_in_repo.assert_called_once()
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
                        "llm": {"capabilities": {"supports_resume": True}},
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

    def test_resolve_resume_target_ignores_newer_execution_only_session(self) -> None:
        root = ROOT / ".tmp_test_resume_target_exec_only_root"
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

            s_exec = root / "s_exec"
            s_exec.mkdir()
            (s_exec / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s_exec",
                        "status": "error",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 4,
                        "created_at": "2026-03-04T00:00:00+00:00",
                        "failed_at": "2026-03-04T01:00:00+00:00",
                        "multipass": {"enabled": True},
                        "llm": {"capabilities": {"supports_resume": False}},
                        "notes": {"no_index": False},
                        "paths": {"session_dir": str(s_exec)},
                    }
                ),
                encoding="utf-8",
            )

            sid, action = rf.resolve_resume_target(
                "https://github.com/acme/repo/pull/4",
                sandbox_root=root,
                from_phase="auto",
            )
            self.assertEqual(sid, "s_done")
            self.assertEqual(action, "followup")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_resolve_resume_target_treats_done_session_with_invalid_grounding_as_resumable(self) -> None:
        root = ROOT / ".tmp_test_resume_target_invalid_grounding_root"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)

            session_dir = root / "s_invalid"
            session_dir.mkdir()
            (session_dir / "review.md").write_text("**Decision**: APPROVE\n", encoding="utf-8")
            (session_dir / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s_invalid",
                        "status": "done",
                        "host": "github.com",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 4,
                        "created_at": "2026-03-05T00:00:00+00:00",
                        "completed_at": "2026-03-05T01:00:00+00:00",
                        "multipass": {
                            "enabled": True,
                            "validation": {
                                "mode": "warn",
                                "invalid_artifacts": ["step-01"],
                                "has_invalid_artifacts": True,
                            },
                        },
                        "llm": {"capabilities": {"supports_resume": True}},
                        "notes": {"no_index": False},
                        "paths": {"review_md": str(session_dir / "review.md")},
                    }
                ),
                encoding="utf-8",
            )

            sid, action = rf.resolve_resume_target(
                "https://github.com/acme/repo/pull/4",
                sandbox_root=root,
                from_phase="auto",
            )
            self.assertEqual(sid, "s_invalid")
            self.assertEqual(action, "resume")
        finally:
            shutil.rmtree(root, ignore_errors=True)


class ListSessionsTests(unittest.TestCase):
    def test_list_sessions_includes_codex_summary(self) -> None:
        root = ROOT / ".tmp_test_list_sessions_root"
        cfg = ROOT / ".tmp_test_list_sessions_cfg.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text("{}", encoding="utf-8")

            s1 = root / "s1"
            s1.mkdir()
            (s1 / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s1",
                        "owner": "acme",
                        "repo": "repo",
                        "number": 7,
                        "created_at": "2026-03-04T01:00:00+00:00",
                        "codex": {
                            "config": {
                                "resolved": {
                                    "model": "gpt-5.3-codex",
                                    "model_reasoning_effort": "high",
                                }
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            s2 = root / "s2"
            s2.mkdir()
            (s2 / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "s2",
                        "owner": "beta",
                        "repo": "app",
                        "number": 9,
                        "created_at": "2026-03-05T01:00:00+00:00",
                        "codex": {
                            "flags": [
                                "-m",
                                "gpt-5.2",
                                "-c",
                                'model_reasoning_effort="medium"',
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )

            stdout = StringIO()
            paths = rf.ReviewflowPaths(
                sandbox_root=root,
                cache_root=ROOT / ".tmp_test_list_sessions_cache",
                review_chunkhound_config=cfg,
                main_chunkhound_config=cfg,
            )
            with mock.patch("sys.stdout", stdout):
                rc = rf.list_sessions(paths=paths)

            self.assertEqual(rc, 0)
            rendered = stdout.getvalue()
            self.assertIn("s1  acme/repo#7  2026-03-04T01:00:00+00:00  llm=legacy_codex/gpt-5.3-codex/high", rendered)
            self.assertIn("s2  beta/app#9  2026-03-05T01:00:00+00:00  llm=legacy_codex/gpt-5.2/medium", rendered)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)


class CleanFlowTests(unittest.TestCase):
    class _FakeTty(StringIO):
        def isatty(self) -> bool:
            return True

    def test_read_cleanup_key_maps_standard_arrow_sequences(self) -> None:
        self.assertEqual(rf._read_cleanup_key(StringIO("\x1b[A")), "UP")
        self.assertEqual(rf._read_cleanup_key(StringIO("\x1b[B")), "DOWN")
        self.assertEqual(rf._read_cleanup_key(StringIO("\x1b[C")), "RIGHT")
        self.assertEqual(rf._read_cleanup_key(StringIO("\x1b[D")), "LEFT")

    def test_read_cleanup_key_maps_application_arrow_sequences(self) -> None:
        self.assertEqual(rf._read_cleanup_key(StringIO("\x1bOA")), "UP")
        self.assertEqual(rf._read_cleanup_key(StringIO("\x1bOB")), "DOWN")
        self.assertEqual(rf._read_cleanup_key(StringIO("\x1bOC")), "RIGHT")
        self.assertEqual(rf._read_cleanup_key(StringIO("\x1bOD")), "LEFT")

    def test_read_cleanup_key_maps_application_arrow_sequences_from_fd_stream(self) -> None:
        read_fd, write_fd = os.pipe()
        try:
            os.write(write_fd, b"\x1bOB")
            os.close(write_fd)
            with os.fdopen(read_fd, "r", encoding="utf-8", newline="") as stream:
                self.assertEqual(rf._read_cleanup_key(stream), "DOWN")
        finally:
            try:
                os.close(write_fd)
            except OSError:
                pass

    def _write_cleanup_session(
        self,
        *,
        root: Path,
        session_id: str,
        status: str,
        created_at: str,
        completed_at: str | None = None,
        failed_at: str | None = None,
        host: str = "github.com",
        owner: str = "acme",
        repo: str = "repo",
        number: int = 1,
        title: str = "Title",
        review_md: str | None = None,
    ) -> Path:
        session_dir = root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "repo").mkdir(exist_ok=True)
        if review_md is not None:
            (session_dir / "review.md").write_text(review_md, encoding="utf-8")
        meta = {
            "session_id": session_id,
            "status": status,
            "host": host,
            "owner": owner,
            "repo": repo,
            "number": number,
            "title": title,
            "created_at": created_at,
            "paths": {
                "repo_dir": str(session_dir / "repo"),
                "review_md": str(session_dir / "review.md"),
            },
        }
        if completed_at is not None:
            meta["completed_at"] = completed_at
        if failed_at is not None:
            meta["failed_at"] = failed_at
        (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        return session_dir

    def test_scan_cleanup_sessions_includes_risk_and_size(self) -> None:
        root = ROOT / ".tmp_test_cleanup_scan_root"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            s1 = self._write_cleanup_session(
                root=root,
                session_id="s1",
                status="done",
                created_at="2026-03-01T00:00:00+00:00",
                completed_at="2026-03-01T01:00:00+00:00",
                owner="acme",
                repo="repo",
                number=10,
                review_md=_sectioned_review_markdown(business="APPROVE", technical="REQUEST CHANGES"),
            )
            (s1 / "blob.bin").write_bytes(b"x" * 32)
            self._write_cleanup_session(
                root=root,
                session_id="s2",
                status="running",
                created_at="2026-03-10T11:30:00+00:00",
                owner="beta",
                repo="app",
                number=11,
                review_md="",
            )

            with mock.patch.object(
                rf,
                "_cleanup_now",
                return_value=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
            ):
                sessions = rf.scan_cleanup_sessions(sandbox_root=root)

            self.assertEqual([s.session_id for s in sessions], ["s2", "s1"])
            self.assertTrue(sessions[0].is_running)
            self.assertTrue(sessions[0].is_risky)
            self.assertFalse(sessions[1].is_running)
            self.assertFalse(sessions[1].is_risky)
            self.assertEqual(sessions[1].repo_slug, "acme/repo#10")
            self.assertEqual(sessions[1].host, "github.com")
            self.assertEqual(sessions[1].owner, "acme")
            self.assertEqual(sessions[1].repo, "repo")
            self.assertEqual(sessions[1].number, 10)
            self.assertGreater(sessions[1].size_bytes, 0)
            self.assertEqual(sessions[1].verdicts, _verdicts("APPROVE", "REQUEST CHANGES"))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_clean_selection_helpers_apply_only_to_visible_sessions(self) -> None:
        sessions = [
            rf.CleanupSession(
                session_id="done-old",
                session_dir=ROOT / "done-old",
                host="github.com",
                owner="acme",
                repo="repo",
                number=1,
                repo_slug="acme/repo#1",
                title="Old",
                status="done",
                created_at="2026-03-01T00:00:00+00:00",
                completed_at="2026-03-01T01:00:00+00:00",
                failed_at=None,
                verdicts=_verdicts("APPROVE"),
                codex_summary="codex=?",
                size_bytes=10,
                path_display=str(ROOT / "done-old"),
                is_running=False,
                is_recent=False,
                is_risky=False,
            ),
            rf.CleanupSession(
                session_id="running-new",
                session_dir=ROOT / "running-new",
                host="github.com",
                owner="acme",
                repo="repo",
                number=2,
                repo_slug="acme/repo#2",
                title="New",
                status="running",
                created_at="2026-03-10T11:30:00+00:00",
                completed_at=None,
                failed_at=None,
                verdicts=None,
                codex_summary="codex=?",
                size_bytes=11,
                path_display=str(ROOT / "running-new"),
                is_running=True,
                is_recent=True,
                is_risky=True,
            ),
        ]
        state = rf.CleanupUiState(sessions=sessions)
        state.preset = "done_older_24h"
        state.select_all_visible()
        self.assertEqual(state.selected_ids, {"done-old"})
        state.invert_visible_selection()
        self.assertEqual(state.selected_ids, set())
        state.preset = "all"
        state.select_all_visible()
        self.assertEqual(state.selected_ids, {"done-old", "running-new"})
        state.clear_selection()
        self.assertEqual(state.selected_ids, set())

    def test_interactive_clean_flow_requires_tty_when_no_session_id(self) -> None:
        root = ROOT / ".tmp_test_cleanup_tty_root"
        cfg = ROOT / ".tmp_test_cleanup_tty_cfg.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text("{}", encoding="utf-8")
            paths = rf.ReviewflowPaths(
                sandbox_root=root,
                cache_root=ROOT / ".tmp_test_cleanup_tty_cache",
                review_chunkhound_config=cfg,
                main_chunkhound_config=cfg,
            )
            with self.assertRaises(rf.ReviewflowError):
                rf.clean_flow(
                    argparse.Namespace(session_id=None),
                    paths=paths,
                    stdin=StringIO(),
                    stderr=StringIO(),
                )
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_clean_flow_with_session_id_keeps_exact_delete_behavior(self) -> None:
        root = ROOT / ".tmp_test_cleanup_exact_root"
        cfg = ROOT / ".tmp_test_cleanup_exact_cfg.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text("{}", encoding="utf-8")
            self._write_cleanup_session(
                root=root,
                session_id="exact-session",
                status="done",
                created_at="2026-03-01T00:00:00+00:00",
                completed_at="2026-03-01T01:00:00+00:00",
                review_md="**Decision**: APPROVE\n",
            )
            paths = rf.ReviewflowPaths(
                sandbox_root=root,
                cache_root=ROOT / ".tmp_test_cleanup_exact_cache",
                review_chunkhound_config=cfg,
                main_chunkhound_config=cfg,
            )
            rc = rf.clean_flow(argparse.Namespace(session_id="exact-session"), paths=paths)
            self.assertEqual(rc, 0)
            self.assertFalse((root / "exact-session").exists())
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_clean_flow_rejects_invalid_agent_flag_combinations(self) -> None:
        root = ROOT / ".tmp_test_cleanup_invalid_flags_root"
        cfg = ROOT / ".tmp_test_cleanup_invalid_flags_cfg.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text("{}", encoding="utf-8")
            self._write_cleanup_session(
                root=root,
                session_id="exact-session",
                status="done",
                created_at="2026-03-01T00:00:00+00:00",
                completed_at="2026-03-01T01:00:00+00:00",
                review_md="**Decision**: APPROVE\n",
            )
            paths = rf.ReviewflowPaths(
                sandbox_root=root,
                cache_root=ROOT / ".tmp_test_cleanup_invalid_flags_cache",
                review_chunkhound_config=cfg,
                main_chunkhound_config=cfg,
            )

            with self.assertRaises(rf.ReviewflowError):
                rf.clean_flow(
                    argparse.Namespace(session_id=None, yes=True, json_output=False),
                    paths=paths,
                    stdin=StringIO(),
                    stderr=StringIO(),
                )
            with self.assertRaises(rf.ReviewflowError):
                rf.clean_flow(
                    argparse.Namespace(session_id=None, yes=False, json_output=True),
                    paths=paths,
                    stdin=StringIO(),
                    stderr=StringIO(),
                )
            with self.assertRaises(rf.ReviewflowError):
                rf.clean_flow(
                    argparse.Namespace(session_id="exact-session", yes=True, json_output=False),
                    paths=paths,
                    stdin=StringIO(),
                    stderr=StringIO(),
                )
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_clean_session_json_returns_structured_result(self) -> None:
        root = ROOT / ".tmp_test_cleanup_exact_json_root"
        cfg = ROOT / ".tmp_test_cleanup_exact_json_cfg.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text("{}", encoding="utf-8")
            self._write_cleanup_session(
                root=root,
                session_id="exact-session",
                status="done",
                created_at="2026-03-01T00:00:00+00:00",
                completed_at="2026-03-01T01:00:00+00:00",
                number=22,
                review_md="**Decision**: APPROVE\n",
            )
            paths = rf.ReviewflowPaths(
                sandbox_root=root,
                cache_root=ROOT / ".tmp_test_cleanup_exact_json_cache",
                review_chunkhound_config=cfg,
                main_chunkhound_config=cfg,
            )
            stdout = StringIO()
            rc = rf.clean_flow(
                argparse.Namespace(session_id="exact-session", yes=False, json_output=True),
                paths=paths,
                stdout=stdout,
            )
            payload = json.loads(stdout.getvalue())

            self.assertEqual(rc, 0)
            self.assertFalse((root / "exact-session").exists())
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["kind"], "reviewflow.clean.result")
            self.assertEqual(payload["requested_target"], "exact-session")
            self.assertEqual(len(payload["matched"]), 1)
            self.assertEqual(len(payload["deleted"]), 1)
            self.assertEqual(payload["deleted"][0]["session_id"], "exact-session")
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_interactive_clean_flow_bulk_deletes_visible_safe_sessions(self) -> None:
        root = ROOT / ".tmp_test_cleanup_safe_root"
        cfg = ROOT / ".tmp_test_cleanup_safe_cfg.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text("{}", encoding="utf-8")
            self._write_cleanup_session(
                root=root,
                session_id="old-done-1",
                status="done",
                created_at="2026-03-01T00:00:00+00:00",
                completed_at="2026-03-01T01:00:00+00:00",
                owner="acme",
                repo="repo",
                number=1,
                review_md="**Decision**: APPROVE\n",
            )
            self._write_cleanup_session(
                root=root,
                session_id="old-done-2",
                status="done",
                created_at="2026-03-02T00:00:00+00:00",
                completed_at="2026-03-02T01:00:00+00:00",
                owner="acme",
                repo="repo",
                number=2,
                review_md="**Decision**: REQUEST CHANGES\n",
            )
            self._write_cleanup_session(
                root=root,
                session_id="running-now",
                status="running",
                created_at="2026-03-10T11:30:00+00:00",
                owner="acme",
                repo="repo",
                number=3,
                review_md="",
            )
            paths = rf.ReviewflowPaths(
                sandbox_root=root,
                cache_root=ROOT / ".tmp_test_cleanup_safe_cache",
                review_chunkhound_config=cfg,
                main_chunkhound_config=cfg,
            )
            stdin = self._FakeTty("5adyq")
            stderr = self._FakeTty()
            with mock.patch.object(
                rf,
                "_cleanup_now",
                return_value=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
            ):
                rc = rf.clean_flow(argparse.Namespace(session_id=None), paths=paths, stdin=stdin, stderr=stderr)

            self.assertEqual(rc, 0)
            self.assertFalse((root / "old-done-1").exists())
            self.assertFalse((root / "old-done-2").exists())
            self.assertTrue((root / "running-now").exists())
            self.assertIn("Delete 2 session(s)", stderr.getvalue())
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_resolve_cleanup_pr_states_groups_by_pr_and_marks_closed(self) -> None:
        sessions = [
            rf.CleanupSession(
                session_id="s1",
                session_dir=ROOT / "s1",
                host="github.com",
                owner="acme",
                repo="repo",
                number=7,
                repo_slug="acme/repo#7",
                title="One",
                status="done",
                created_at="2026-03-01T00:00:00+00:00",
                completed_at="2026-03-01T01:00:00+00:00",
                failed_at=None,
            ),
            rf.CleanupSession(
                session_id="s2",
                session_dir=ROOT / "s2",
                host="github.com",
                owner="acme",
                repo="repo",
                number=7,
                repo_slug="acme/repo#7",
                title="Two",
                status="done",
                created_at="2026-03-01T00:00:00+00:00",
                completed_at="2026-03-01T01:00:00+00:00",
                failed_at=None,
            ),
            rf.CleanupSession(
                session_id="s3",
                session_dir=ROOT / "s3",
                host="github.com",
                owner="acme",
                repo="repo",
                number=8,
                repo_slug="acme/repo#8",
                title="Three",
                status="done",
                created_at="2026-03-01T00:00:00+00:00",
                completed_at="2026-03-01T01:00:00+00:00",
                failed_at=None,
            ),
        ]

        calls: list[list[str]] = []

        def fake_run(cmd: list[str], **_: object):
            calls.append(cmd)
            endpoint = cmd[-1]
            if endpoint.endswith("/pulls/7"):
                return mock.Mock(stdout=json.dumps({"state": "closed", "merged_at": "2026-03-01T00:00:00Z"}))
            return mock.Mock(stdout=json.dumps({"state": "open", "merged_at": None}))

        with mock.patch.object(rf, "require_gh_auth"), mock.patch.object(rf, "run_cmd", side_effect=fake_run):
            states, skipped = rf.resolve_cleanup_pr_states(sessions=sessions)

        self.assertEqual(len(calls), 2)
        self.assertEqual(states[("github.com", "acme", "repo", 7)], "merged")
        self.assertEqual(states[("github.com", "acme", "repo", 8)], "open")
        self.assertEqual(skipped, {})

    def test_resolve_cleanup_pr_states_reports_progress_for_unique_prs(self) -> None:
        sessions = [
            rf.CleanupSession(
                session_id="s1",
                session_dir=ROOT / "s1",
                host="github.com",
                owner="acme",
                repo="repo",
                number=7,
                repo_slug="acme/repo#7",
                title="One",
                status="done",
                created_at="2026-03-01T00:00:00+00:00",
                completed_at="2026-03-01T01:00:00+00:00",
                failed_at=None,
            ),
            rf.CleanupSession(
                session_id="s2",
                session_dir=ROOT / "s2",
                host="github.com",
                owner="acme",
                repo="repo",
                number=7,
                repo_slug="acme/repo#7",
                title="Two",
                status="done",
                created_at="2026-03-01T00:00:00+00:00",
                completed_at="2026-03-01T01:00:00+00:00",
                failed_at=None,
            ),
            rf.CleanupSession(
                session_id="s3",
                session_dir=ROOT / "s3",
                host="github.com",
                owner="beta",
                repo="app",
                number=8,
                repo_slug="beta/app#8",
                title="Three",
                status="done",
                created_at="2026-03-01T00:00:00+00:00",
                completed_at="2026-03-01T01:00:00+00:00",
                failed_at=None,
            ),
        ]
        seen: list[tuple[int, int, tuple[str, str, str, int]]] = []

        with mock.patch.object(rf, "require_gh_auth"), mock.patch.object(
            rf,
            "run_cmd",
            side_effect=[
                mock.Mock(stdout=json.dumps({"state": "closed", "merged_at": None})),
                mock.Mock(stdout=json.dumps({"state": "open", "merged_at": None})),
            ],
        ):
            rf.resolve_cleanup_pr_states(sessions=sessions, on_progress=lambda i, t, k: seen.append((i, t, k)))

        self.assertEqual(
            seen,
            [
                (1, 2, ("github.com", "acme", "repo", 7)),
                (2, 2, ("github.com", "beta", "app", 8)),
            ],
        )

    def test_clean_flow_with_closed_target_dispatches_to_clean_closed_flow(self) -> None:
        paths = rf.ReviewflowPaths(
            sandbox_root=ROOT,
            cache_root=ROOT,
            review_chunkhound_config=ROOT / ".tmp_cfg",
            main_chunkhound_config=ROOT / ".tmp_cfg2",
        )
        with mock.patch.object(rf, "clean_closed_flow", return_value=0) as closed_flow:
            rc = rf.clean_flow(argparse.Namespace(session_id="closed"), paths=paths, stdin=StringIO(), stderr=StringIO())
        self.assertEqual(rc, 0)
        self.assertEqual(closed_flow.call_count, 1)

    def test_clean_closed_flow_requires_tty(self) -> None:
        paths = rf.ReviewflowPaths(
            sandbox_root=ROOT,
            cache_root=ROOT,
            review_chunkhound_config=ROOT / ".tmp_cfg",
            main_chunkhound_config=ROOT / ".tmp_cfg2",
        )
        with self.assertRaises(rf.ReviewflowError):
            rf.clean_closed_flow(argparse.Namespace(), paths=paths, stdin=StringIO(), stderr=StringIO())

    def test_clean_closed_flow_deletes_closed_and_skips_open_unknown(self) -> None:
        root = ROOT / ".tmp_test_cleanup_closed_root"
        cfg = ROOT / ".tmp_test_cleanup_closed_cfg.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text("{}", encoding="utf-8")
            self._write_cleanup_session(
                root=root,
                session_id="merged-pr",
                status="done",
                created_at="2026-03-01T00:00:00+00:00",
                completed_at="2026-03-01T01:00:00+00:00",
                number=1,
                review_md="**Decision**: APPROVE\n",
            )
            self._write_cleanup_session(
                root=root,
                session_id="closed-pr",
                status="done",
                created_at="2026-03-02T00:00:00+00:00",
                completed_at="2026-03-02T01:00:00+00:00",
                number=2,
                review_md="**Decision**: REQUEST CHANGES\n",
            )
            self._write_cleanup_session(
                root=root,
                session_id="open-pr",
                status="done",
                created_at="2026-03-03T00:00:00+00:00",
                completed_at="2026-03-03T01:00:00+00:00",
                number=3,
                review_md="**Decision**: APPROVE\n",
            )
            self._write_cleanup_session(
                root=root,
                session_id="unknown-pr",
                status="done",
                created_at="2026-03-04T00:00:00+00:00",
                completed_at="2026-03-04T01:00:00+00:00",
                number=4,
                review_md="**Decision**: APPROVE\n",
            )
            paths = rf.ReviewflowPaths(
                sandbox_root=root,
                cache_root=ROOT / ".tmp_test_cleanup_closed_cache",
                review_chunkhound_config=cfg,
                main_chunkhound_config=cfg,
            )
            stdin = self._FakeTty("y")
            stderr = self._FakeTty()
            with mock.patch.object(
                rf,
                "resolve_cleanup_pr_states",
                return_value=(
                    {
                        ("github.com", "acme", "repo", 1): "merged",
                        ("github.com", "acme", "repo", 2): "closed",
                        ("github.com", "acme", "repo", 3): "open",
                        ("github.com", "acme", "repo", 4): "unknown",
                    },
                    {("github.com", "acme", "repo", 4): "404"},
                ),
            ), mock.patch.object(
                rf,
                "_cleanup_now",
                return_value=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
            ):
                rc = rf.clean_closed_flow(argparse.Namespace(), paths=paths, stdin=stdin, stderr=stderr)

            self.assertEqual(rc, 0)
            self.assertFalse((root / "merged-pr").exists())
            self.assertFalse((root / "closed-pr").exists())
            self.assertTrue((root / "open-pr").exists())
            self.assertTrue((root / "unknown-pr").exists())
            out = stderr.getvalue()
            self.assertIn("Delete 2 session(s) for closed or merged PRs?", out)
            self.assertIn("Skipped 1 session(s) with unknown PR state.", out)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_clean_closed_flow_prints_progress_while_resolving(self) -> None:
        root = ROOT / ".tmp_test_cleanup_closed_progress_root"
        cfg = ROOT / ".tmp_test_cleanup_closed_progress_cfg.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text("{}", encoding="utf-8")
            self._write_cleanup_session(
                root=root,
                session_id="closed-pr",
                status="done",
                created_at="2026-03-01T00:00:00+00:00",
                completed_at="2026-03-01T01:00:00+00:00",
                number=12,
                review_md="**Decision**: APPROVE\n",
            )
            paths = rf.ReviewflowPaths(
                sandbox_root=root,
                cache_root=ROOT / ".tmp_test_cleanup_closed_progress_cache",
                review_chunkhound_config=cfg,
                main_chunkhound_config=cfg,
            )
            stdin = self._FakeTty("y\n")
            stderr = self._FakeTty()
            with mock.patch.object(rf, "require_gh_auth"), mock.patch.object(
                rf,
                "run_cmd",
                return_value=mock.Mock(stdout=json.dumps({"state": "closed", "merged_at": None})),
            ), mock.patch.object(
                rf,
                "_cleanup_now",
                return_value=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
            ):
                rc = rf.clean_closed_flow(argparse.Namespace(), paths=paths, stdin=stdin, stderr=stderr)

            self.assertEqual(rc, 0)
            self.assertIn("Resolving PR states [", stderr.getvalue())
            self.assertFalse((root / "closed-pr").exists())
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_clean_closed_flow_requires_delete_word_for_risky_matches(self) -> None:
        root = ROOT / ".tmp_test_cleanup_closed_risky_root"
        cfg = ROOT / ".tmp_test_cleanup_closed_risky_cfg.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text("{}", encoding="utf-8")
            self._write_cleanup_session(
                root=root,
                session_id="running-closed",
                status="running",
                created_at="2026-03-10T11:30:00+00:00",
                number=9,
                review_md="",
            )
            paths = rf.ReviewflowPaths(
                sandbox_root=root,
                cache_root=ROOT / ".tmp_test_cleanup_closed_risky_cache",
                review_chunkhound_config=cfg,
                main_chunkhound_config=cfg,
            )
            stdin = self._FakeTty("DELETE\n")
            stderr = self._FakeTty()
            with mock.patch.object(
                rf,
                "resolve_cleanup_pr_states",
                return_value=({("github.com", "acme", "repo", 9): "closed"}, {}),
            ), mock.patch.object(
                rf,
                "_cleanup_now",
                return_value=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
            ):
                rc = rf.clean_closed_flow(argparse.Namespace(), paths=paths, stdin=stdin, stderr=stderr)

            self.assertEqual(rc, 0)
            self.assertFalse((root / "running-closed").exists())
            self.assertIn("Type DELETE to confirm risky session removal:", stderr.getvalue())
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_clean_closed_json_preview_and_execute_use_structured_payloads(self) -> None:
        root = ROOT / ".tmp_test_cleanup_closed_json_root"
        cfg = ROOT / ".tmp_test_cleanup_closed_json_cfg.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text("{}", encoding="utf-8")
            self._write_cleanup_session(
                root=root,
                session_id="closed-pr",
                status="done",
                created_at="2026-03-01T00:00:00+00:00",
                completed_at="2026-03-01T01:00:00+00:00",
                number=1,
                review_md="**Decision**: APPROVE\n",
            )
            self._write_cleanup_session(
                root=root,
                session_id="open-pr",
                status="done",
                created_at="2026-03-02T00:00:00+00:00",
                completed_at="2026-03-02T01:00:00+00:00",
                number=2,
                review_md="**Decision**: APPROVE\n",
            )
            paths = rf.ReviewflowPaths(
                sandbox_root=root,
                cache_root=ROOT / ".tmp_test_cleanup_closed_json_cache",
                review_chunkhound_config=cfg,
                main_chunkhound_config=cfg,
            )

            with mock.patch.object(
                rf,
                "resolve_cleanup_pr_states",
                return_value=(
                    {("github.com", "acme", "repo", 1): "closed", ("github.com", "acme", "repo", 2): "open"},
                    {},
                ),
            ), mock.patch.object(
                rf,
                "_cleanup_now",
                return_value=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
            ):
                preview_stdout = StringIO()
                preview_stderr = StringIO()
                preview_rc = rf.clean_flow(
                    argparse.Namespace(session_id="closed", yes=False, json_output=True),
                    paths=paths,
                    stdout=preview_stdout,
                    stderr=preview_stderr,
                )
                preview = json.loads(preview_stdout.getvalue())

                self.assertEqual(preview_rc, 0)
                self.assertTrue((root / "closed-pr").exists())
                self.assertEqual(preview["schema_version"], 1)
                self.assertEqual(preview["kind"], "reviewflow.clean.preview")
                self.assertEqual([item["session_id"] for item in preview["matched"]], ["closed-pr"])
                self.assertEqual(preview["deleted"], [])

                execute_stdout = StringIO()
                execute_stderr = StringIO()
                execute_rc = rf.clean_flow(
                    argparse.Namespace(session_id="closed", yes=True, json_output=True),
                    paths=paths,
                    stdout=execute_stdout,
                    stderr=execute_stderr,
                )
                result = json.loads(execute_stdout.getvalue())

            self.assertEqual(execute_rc, 0)
            self.assertFalse((root / "closed-pr").exists())
            self.assertTrue((root / "open-pr").exists())
            self.assertEqual(result["schema_version"], 1)
            self.assertEqual(result["kind"], "reviewflow.clean.result")
            self.assertEqual([item["session_id"] for item in result["deleted"]], ["closed-pr"])
            self.assertEqual(result["summary"]["deleted"], 1)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_interactive_clean_flow_requires_delete_word_for_risky_selection(self) -> None:
        root = ROOT / ".tmp_test_cleanup_risky_root"
        cfg = ROOT / ".tmp_test_cleanup_risky_cfg.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text("{}", encoding="utf-8")
            self._write_cleanup_session(
                root=root,
                session_id="running-now",
                status="running",
                created_at="2026-03-10T11:30:00+00:00",
                owner="acme",
                repo="repo",
                number=3,
                review_md="",
            )
            paths = rf.ReviewflowPaths(
                sandbox_root=root,
                cache_root=ROOT / ".tmp_test_cleanup_risky_cache",
                review_chunkhound_config=cfg,
                main_chunkhound_config=cfg,
            )
            stdin = self._FakeTty(" dDELETE\nq")
            stderr = self._FakeTty()
            with mock.patch.object(
                rf,
                "_cleanup_now",
                return_value=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
            ):
                rc = rf.clean_flow(argparse.Namespace(session_id=None), paths=paths, stdin=stdin, stderr=stderr)

            self.assertEqual(rc, 0)
            self.assertFalse((root / "running-now").exists())
            self.assertIn("Type DELETE to confirm", stderr.getvalue())
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)


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


class WorkflowContractTests(unittest.TestCase):
    def _make_paths(self, root: Path, *, suffix: str) -> tuple[rf.ReviewflowPaths, Path]:
        cfg = ROOT / f".tmp_test_workflow_contract_{suffix}.json"
        cfg.write_text("{}", encoding="utf-8")
        paths = rf.ReviewflowPaths(
            sandbox_root=root,
            cache_root=ROOT / f".tmp_test_workflow_contract_cache_{suffix}",
            review_chunkhound_config=cfg,
            main_chunkhound_config=cfg,
        )
        return paths, cfg

    def _write_session(
        self,
        *,
        root: Path,
        session_id: str,
        status: str,
        created_at: str,
        completed_at: str | None = None,
        resumed_at: str | None = None,
        host: str = "github.com",
        owner: str = "acme",
        repo: str = "repo",
        number: int = 1,
        phase: str = "review",
        phases: dict[str, object] | None = None,
        llm: dict[str, object] | None = None,
        agent_runtime: dict[str, object] | None = None,
        error: dict[str, object] | None = None,
        followup_name: str | None = None,
    ) -> Path:
        session_dir = root / session_id
        repo_dir = session_dir / "repo"
        work_dir = session_dir / "work"
        logs_dir = work_dir / "logs"
        followups_dir = session_dir / "followups"
        repo_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        review_md = session_dir / "review.md"
        review_md.write_text(_sectioned_review_markdown(business="APPROVE", technical="REQUEST CHANGES"), encoding="utf-8")
        for name in ("reviewflow.log", "chunkhound.log", "codex.log"):
            (logs_dir / name).write_text(f"{name}\n", encoding="utf-8")

        followups: list[dict[str, object]] = []
        if followup_name:
            followups_dir.mkdir(parents=True, exist_ok=True)
            followup_path = followups_dir / followup_name
            followup_path.write_text("# Followup\n", encoding="utf-8")
            followups.append(
                {
                    "completed_at": "2026-03-10T12:05:00+00:00",
                    "output_path": str(followup_path),
                }
            )

        meta: dict[str, object] = {
            "session_id": session_id,
            "status": status,
            "phase": phase,
            "phases": phases
            or {
                "init": {"status": "done", "started_at": created_at, "finished_at": created_at},
                phase: {"status": status if status in {"done", "error"} else "running", "started_at": created_at},
            },
            "host": host,
            "owner": owner,
            "repo": repo,
            "number": number,
            "title": "Story 26 test session",
            "created_at": created_at,
            "paths": {
                "repo_dir": str(repo_dir),
                "work_dir": str(work_dir),
                "logs_dir": str(logs_dir),
                "review_md": str(review_md),
            },
            "logs": {
                "reviewflow": str(logs_dir / "reviewflow.log"),
                "chunkhound": str(logs_dir / "chunkhound.log"),
                "codex": str(logs_dir / "codex.log"),
            },
        }
        if completed_at is not None:
            meta["completed_at"] = completed_at
        if resumed_at is not None:
            meta["resumed_at"] = resumed_at
        if llm is not None:
            meta["llm"] = llm
        if agent_runtime is not None:
            meta["agent_runtime"] = agent_runtime
        if error is not None:
            meta["error"] = error
        if followups:
            meta["followups"] = followups

        (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        return session_dir

    def test_commands_flow_json_returns_curated_agent_catalog(self) -> None:
        stdout = StringIO()
        rc = rf.commands_flow(argparse.Namespace(json_output=True), stdout=stdout)
        payload = json.loads(stdout.getvalue())

        self.assertEqual(rc, 0)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["kind"], "reviewflow.commands")
        names = [entry["name"] for entry in payload["commands"]]
        self.assertEqual(names, ["pr", "followup", "resume", "zip", "clean", "status", "watch"])
        pr_entry = next(entry for entry in payload["commands"] if entry["name"] == "pr")
        self.assertEqual(pr_entry["recommended_invocation"], "cure pr <PR_URL> --if-reviewed new")
        self.assertIn("variants", pr_entry)
        self.assertNotIn("deprecated_alias", {item["name"] for item in pr_entry["variants"]})
        self.assertNotIn("interactive", names)

    def test_commands_flow_human_output_lists_curated_recommended_invocations(self) -> None:
        stdout = StringIO()
        rc = rf.commands_flow(argparse.Namespace(json_output=False), stdout=stdout)
        rendered = stdout.getvalue()

        self.assertEqual(rc, 0)
        self.assertIn("pr: Create a new review session for a PR.", rendered)
        self.assertIn("cure clean closed --json", rendered)
        self.assertIn("cure status <session_id|PR_URL> --json", rendered)
        self.assertIn("cure watch <session_id|PR_URL>", rendered)
        self.assertNotIn("reviewflow", rendered)
        self.assertNotIn("interactive", rendered)

    def test_reviewflow_reexports_active_extracted_module_surfaces(self) -> None:
        self.assertIs(rf.init_flow, cure_commands.init_flow)
        self.assertIs(rf.render_prompt, cure_flows.render_prompt)
        self.assertIs(rf.run_llm_exec, cure_llm.run_llm_exec)
        self.assertIs(rf.commands_flow, cure_commands.commands_flow)
        self.assertIs(rf.status_flow, cure_commands.status_flow)
        self.assertIs(rf.watch_flow, cure_commands.watch_flow)
        self.assertIs(rf.doctor_flow, cure_commands.doctor_flow)
        self.assertIs(rf.pr_flow, cure_commands.pr_flow)
        self.assertIs(rf.resume_flow, cure_commands.resume_flow)
        self.assertIs(rf.followup_flow, cure_commands.followup_flow)
        self.assertIs(rf.zip_flow, cure_commands.zip_flow)
        self.assertIs(rf.interactive_flow, cure_commands.interactive_flow)
        self.assertIs(rf.clean_flow, cure_commands.clean_flow)
        self.assertFalse(hasattr(rf, "jira_smoke_flow"))
        self.assertFalse(hasattr(rf, "_clean_flow_impl"))

    def test_main_dispatches_pr_through_runtime_and_command_surfaces(self) -> None:
        args = argparse.Namespace(cmd="pr")
        parser = mock.Mock()
        parser.parse_args.return_value = args
        runtime = argparse.Namespace(
            paths=mock.sentinel.paths,
            config_path=Path("/tmp/reviewflow.toml"),
            codex_base_config_path=Path("/tmp/codex.toml"),
        )
        with mock.patch.object(rf, "build_parser", return_value=parser), mock.patch.object(
            cure_runtime, "resolve_runtime", return_value=runtime
        ) as resolve_runtime_mock, mock.patch.object(
            cure_commands, "pr_flow", return_value=17
        ) as pr_flow_mock:
            rc = rf.main(["pr", "https://github.com/acme/repo/pull/1"])

        self.assertEqual(rc, 17)
        resolve_runtime_mock.assert_called_once_with(args)
        pr_flow_mock.assert_called_once_with(
            args,
            paths=mock.sentinel.paths,
            config_path=Path("/tmp/reviewflow.toml"),
            codex_base_config_path=Path("/tmp/codex.toml"),
        )

    def test_main_dispatches_status_through_command_surface(self) -> None:
        args = argparse.Namespace(cmd="status")
        parser = mock.Mock()
        parser.parse_args.return_value = args
        runtime = argparse.Namespace(
            paths=mock.sentinel.paths,
            config_path=Path("/tmp/reviewflow.toml"),
            codex_base_config_path=Path("/tmp/codex.toml"),
        )
        with mock.patch.object(rf, "build_parser", return_value=parser), mock.patch.object(
            cure_runtime, "resolve_runtime", return_value=runtime
        ) as resolve_runtime_mock, mock.patch.object(
            cure_commands, "status_flow", return_value=3
        ) as status_flow_mock:
            rc = rf.main(["status", "session-123"])

        self.assertEqual(rc, 3)
        resolve_runtime_mock.assert_called_once_with(args)
        status_flow_mock.assert_called_once_with(args, paths=mock.sentinel.paths)

    def test_main_dispatches_heavy_commands_through_command_surface(self) -> None:
        runtime = argparse.Namespace(
            paths=mock.sentinel.paths,
            config_path=Path("/tmp/reviewflow.toml"),
            codex_base_config_path=Path("/tmp/codex.toml"),
        )
        cases = (
            (
                "pr",
                "pr_flow",
                {
                    "paths": mock.sentinel.paths,
                    "config_path": Path("/tmp/reviewflow.toml"),
                    "codex_base_config_path": Path("/tmp/codex.toml"),
                },
            ),
            (
                "resume",
                "resume_flow",
                {
                    "paths": mock.sentinel.paths,
                    "config_path": Path("/tmp/reviewflow.toml"),
                    "codex_base_config_path": Path("/tmp/codex.toml"),
                },
            ),
            (
                "followup",
                "followup_flow",
                {
                    "paths": mock.sentinel.paths,
                    "config_path": Path("/tmp/reviewflow.toml"),
                    "codex_base_config_path": Path("/tmp/codex.toml"),
                },
            ),
            (
                "zip",
                "zip_flow",
                {
                    "paths": mock.sentinel.paths,
                    "config_path": Path("/tmp/reviewflow.toml"),
                    "codex_base_config_path": Path("/tmp/codex.toml"),
                },
            ),
            (
                "interactive",
                "interactive_flow",
                {
                    "paths": mock.sentinel.paths,
                    "config_path": Path("/tmp/reviewflow.toml"),
                },
            ),
            (
                "clean",
                "clean_flow",
                {
                    "paths": mock.sentinel.paths,
                },
            ),
        )

        for command_name, flow_name, expected_kwargs in cases:
            args = argparse.Namespace(cmd=command_name)
            parser = mock.Mock()
            parser.parse_args.return_value = args
            with self.subTest(command=command_name), mock.patch.object(
                rf, "build_parser", return_value=parser
            ), mock.patch.object(
                cure_runtime, "resolve_runtime", return_value=runtime
            ) as resolve_runtime_mock, mock.patch.object(
                cure_commands, flow_name, return_value=29
            ) as flow_mock:
                rc = rf.main([command_name])

            self.assertEqual(rc, 29)
            resolve_runtime_mock.assert_called_once_with(args)
            flow_mock.assert_called_once_with(args, **expected_kwargs)

    def test_review_intelligence_preflight_skips_when_jira_is_not_in_play(self) -> None:
        cfg = rf.ReviewIntelligenceConfig(tool_prompt_fragment="Use GitHub only.")
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            repo_dir.mkdir()
            helper = repo_dir / "rf-jira"
            helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            helper.chmod(0o755)
            with mock.patch.object(rf, "run_cmd") as run_cmd, mock.patch.object(
                rf, "active_output", return_value=None
            ):
                rf._run_review_intelligence_preflight(
                    repo_dir=repo_dir,
                    env={},
                    runtime_policy={"staged_paths": {"rf_jira": str(helper)}},
                    review_intelligence_cfg=cfg,
                    stream=False,
                )
        run_cmd.assert_not_called()

    def test_review_intelligence_preflight_fails_fast_when_jira_is_required_without_config(self) -> None:
        cfg = rf.ReviewIntelligenceConfig(tool_prompt_fragment="Use Jira ticket context first.")
        with self.assertRaises(rf.ReviewflowError) as ctx:
            rf._run_review_intelligence_preflight(
                repo_dir=Path("/tmp/repo"),
                env={},
                runtime_policy={"staged_paths": {}},
                review_intelligence_cfg=cfg,
                stream=False,
            )
        self.assertIn("JIRA_CONFIG_FILE", str(ctx.exception))

    def test_review_intelligence_preflight_runs_rf_jira_me_before_review(self) -> None:
        cfg = rf.ReviewIntelligenceConfig(tool_prompt_fragment="Use Jira when available.")
        progress = mock.Mock()
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            repo_dir.mkdir()
            helper = repo_dir / "rf-jira"
            helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            helper.chmod(0o755)
            with mock.patch.object(rf, "run_cmd") as run_cmd, mock.patch.object(
                rf, "active_output", return_value=None
            ):
                rf._run_review_intelligence_preflight(
                    repo_dir=repo_dir,
                    env={"JIRA_CONFIG_FILE": str(repo_dir / "jira.yml")},
                    runtime_policy={"staged_paths": {"rf_jira": str(helper)}},
                    review_intelligence_cfg=cfg,
                    stream=True,
                    progress=progress,
                )
        progress.record_cmd.assert_called_once_with([str(helper), "me"])
        run_cmd.assert_called_once_with(
            [str(helper), "me"],
            cwd=repo_dir,
            env={"JIRA_CONFIG_FILE": str(repo_dir / "jira.yml")},
            check=True,
            stream=True,
            stream_label="jira",
        )

    def test_reviewflow_output_accepts_jira_stream_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = rf.ReviewflowOutput(
                ui_enabled=False,
                no_stream=False,
                stderr=StringIO(),
                meta_path=Path(tmp) / "meta.json",
                logs_dir=Path(tmp) / "logs",
                verbosity=rui.Verbosity.normal,
            )
            try:
                self.assertIs(out.stream_sink("jira"), out.chunkhound_sink)
            finally:
                out.stop()

    def test_status_flow_exact_session_human_output_uses_exact_resolution(self) -> None:
        root = ROOT / ".tmp_test_status_exact_root"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            paths, cfg = self._make_paths(root, suffix="status_exact")
            self._write_session(
                root=root,
                session_id="exact-session",
                status="done",
                created_at="2026-03-10T10:00:00+00:00",
                completed_at="2026-03-10T10:10:00+00:00",
                number=29,
                llm={
                    "preset": "codex-cli",
                    "transport": "cli",
                    "provider": "codex",
                    "model": "gpt-5.4",
                    "reasoning_effort": "medium",
                    "capabilities": {"supports_resume": True},
                },
            )

            stdout = StringIO()
            rc = rf.status_flow(
                argparse.Namespace(target="exact-session", json_output=False),
                paths=paths,
                stdout=stdout,
            )

            rendered = stdout.getvalue()
            self.assertEqual(rc, 0)
            self.assertIn("session=exact-session", rendered)
            self.assertIn("repo=acme/repo#29", rendered)
            self.assertIn("status=done", rendered)
            self.assertIn("phase=review", rendered)
            self.assertIn("llm=codex-cli/gpt-5.4/medium", rendered)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_status_flow_json_prefers_newest_running_session_for_pr_url(self) -> None:
        root = ROOT / ".tmp_test_status_running_root"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            paths, cfg = self._make_paths(root, suffix="status_running")
            self._write_session(
                root=root,
                session_id="done-older",
                status="done",
                created_at="2026-03-10T10:00:00+00:00",
                completed_at="2026-03-10T10:10:00+00:00",
                number=26,
            )
            self._write_session(
                root=root,
                session_id="running-newer",
                status="running",
                created_at="2026-03-10T11:00:00+00:00",
                resumed_at="2026-03-10T11:05:00+00:00",
                number=26,
                llm={
                    "preset": "claude-cli",
                    "transport": "cli",
                    "provider": "claude",
                    "model": "claude-sonnet-4-6",
                    "reasoning_effort": "high",
                    "capabilities": {"supports_resume": True},
                },
                agent_runtime={"profile": "balanced", "provider": "claude", "permission_mode": "dontAsk"},
                followup_name="followup-1.md",
            )

            stdout = StringIO()
            rc = rf.status_flow(
                argparse.Namespace(
                    target="https://github.com/acme/repo/pull/26",
                    json_output=True,
                ),
                paths=paths,
                stdout=stdout,
            )
            payload = json.loads(stdout.getvalue())

            self.assertEqual(rc, 0)
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["kind"], "reviewflow.status")
            self.assertEqual(payload["requested_target"]["kind"], "pr_url")
            self.assertEqual(payload["resolved_target"]["session_id"], "running-newer")
            self.assertEqual(payload["resolution_strategy"], "newest_running")
            self.assertEqual(payload["pr"]["pr_url"], "https://github.com/acme/repo/pull/26")
            self.assertEqual(payload["status"], "running")
            self.assertEqual(payload["phase"], "review")
            self.assertTrue(payload["paths"]["logs_dir"].endswith("/work/logs"))
            self.assertTrue(payload["logs"]["codex"].endswith("/work/logs/codex.log"))
            self.assertEqual(payload["latest_artifact"]["path"].rsplit("/", 1)[-1], "followup-1.md")
            self.assertEqual(payload["llm"]["summary"], "llm=claude-cli/claude-sonnet-4-6/high")
            self.assertEqual(payload["agent_runtime"]["profile"], "balanced")
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_status_flow_json_uses_newest_resumed_or_created_when_no_session_running(self) -> None:
        root = ROOT / ".tmp_test_status_fallback_root"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            paths, cfg = self._make_paths(root, suffix="status_fallback")
            self._write_session(
                root=root,
                session_id="created-later",
                status="done",
                created_at="2026-03-10T11:00:00+00:00",
                completed_at="2026-03-10T11:10:00+00:00",
                number=27,
            )
            self._write_session(
                root=root,
                session_id="resumed-newest",
                status="error",
                created_at="2026-03-10T09:00:00+00:00",
                resumed_at="2026-03-10T12:00:00+00:00",
                number=27,
                error={"type": "exception", "message": "boom"},
            )

            stdout = StringIO()
            rc = rf.status_flow(
                argparse.Namespace(
                    target="https://github.com/acme/repo/pull/27",
                    json_output=True,
                ),
                paths=paths,
                stdout=stdout,
            )
            payload = json.loads(stdout.getvalue())

            self.assertEqual(rc, 0)
            self.assertEqual(payload["resolved_target"]["session_id"], "resumed-newest")
            self.assertEqual(payload["resolution_strategy"], "newest_activity")
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["error"]["message"], "boom")
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_status_flow_rejects_invalid_or_missing_targets(self) -> None:
        root = ROOT / ".tmp_test_status_negative_root"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            paths, cfg = self._make_paths(root, suffix="status_negative")

            with self.assertRaises(rf.ReviewflowError):
                rf.status_flow(
                    argparse.Namespace(target="/tmp/not-a-session", json_output=True),
                    paths=paths,
                    stdout=StringIO(),
                )

            with self.assertRaises(rf.ReviewflowError):
                rf.status_flow(
                    argparse.Namespace(target="missing-session", json_output=True),
                    paths=paths,
                    stdout=StringIO(),
                )

            corrupt_dir = root / "corrupt-session"
            corrupt_dir.mkdir(parents=True, exist_ok=True)
            (corrupt_dir / "meta.json").write_text("{not-json", encoding="utf-8")
            with self.assertRaises(rf.ReviewflowError):
                rf.status_flow(
                    argparse.Namespace(target="corrupt-session", json_output=True),
                    paths=paths,
                    stdout=StringIO(),
                )

            with self.assertRaises(rf.ReviewflowError):
                rf.status_flow(
                    argparse.Namespace(
                        target="https://github.com/acme/repo/pull/404",
                        json_output=True,
                    ),
                    paths=paths,
                    stdout=StringIO(),
                )
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_status_flow_rejects_empty_target(self) -> None:
        paths = rf.ReviewflowPaths(
            sandbox_root=ROOT / ".tmp_status_empty_root",
            cache_root=ROOT / ".tmp_status_empty_cache",
            review_chunkhound_config=ROOT / ".tmp_status_empty_cfg",
            main_chunkhound_config=ROOT / ".tmp_status_empty_cfg2",
        )
        with self.assertRaises(rf.ReviewflowError):
            rf.status_flow(argparse.Namespace(target="", json_output=True), paths=paths, stdout=StringIO())

    def test_watch_flow_non_tty_prints_plain_status_and_uses_terminal_exit_codes(self) -> None:
        root = ROOT / ".tmp_test_watch_error_root"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            paths, cfg = self._make_paths(root, suffix="watch_error")
            self._write_session(
                root=root,
                session_id="watch-error",
                status="error",
                created_at="2026-03-10T09:00:00+00:00",
                number=28,
                error={"type": "exception", "message": "bad"},
            )

            stdout = StringIO()
            rc = rf.watch_flow(
                argparse.Namespace(
                    target="watch-error",
                    interval=0.0,
                    verbosity="quiet",
                    no_color=True,
                ),
                paths=paths,
                stdout=stdout,
                stderr=StringIO(),
            )

            rendered = stdout.getvalue()
            self.assertEqual(rc, 1)
            self.assertIn("session=watch-error", rendered)
            self.assertIn("status=error", rendered)
            self.assertIn("phase=review", rendered)
            self.assertNotIn("\x1b[", rendered)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)

    def test_watch_flow_non_tty_returns_zero_for_done(self) -> None:
        root = ROOT / ".tmp_test_watch_done_root"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            paths, cfg = self._make_paths(root, suffix="watch_done")
            self._write_session(
                root=root,
                session_id="watch-done",
                status="done",
                created_at="2026-03-10T09:00:00+00:00",
                completed_at="2026-03-10T09:05:00+00:00",
                number=30,
            )

            stdout = StringIO()
            rc = rf.watch_flow(
                argparse.Namespace(
                    target="watch-done",
                    interval=0.0,
                    verbosity="quiet",
                    no_color=True,
                ),
                paths=paths,
                stdout=stdout,
                stderr=StringIO(),
            )

            rendered = stdout.getvalue()
            self.assertEqual(rc, 0)
            self.assertIn("session=watch-done", rendered)
            self.assertIn("status=done", rendered)
            self.assertNotIn("\x1b[", rendered)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            cfg.unlink(missing_ok=True)


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

    def test_build_codex_exec_cmd_does_not_duplicate_approval_flag(self) -> None:
        cmd = rf.build_codex_exec_cmd(
            repo_dir=ROOT,
            codex_flags=["--sandbox", "workspace-write", "-a", "never"],
            codex_config_overrides=[],
            review_md_path=ROOT / ".tmp_test_review.md",
            prompt="hello",
            approval_policy="never",
            dangerously_bypass_approvals_and_sandbox=False,
        )
        self.assertEqual(cmd.count("-a"), 1)

    def test_build_codex_exec_cmd_can_enable_json_events(self) -> None:
        cmd = rf.build_codex_exec_cmd(
            repo_dir=ROOT,
            codex_flags=["-m", "gpt-5.2"],
            codex_config_overrides=[],
            review_md_path=ROOT / ".tmp_test_review.md",
            prompt="hello",
            json_output=True,
        )
        self.assertIn("--json", cmd)
        self.assertLess(cmd.index("--json"), cmd.index("--output-last-message"))

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
        ch_env_entry = next(o for o in overrides if o.startswith("mcp_servers.chunkhound.env_vars="))
        ch_env_vars = json.loads(ch_env_entry.split("=", 1)[1])
        self.assertNotIn("--exclude", ch_args)
        self.assertNotIn("--db", ch_args)
        self.assertNotIn("--database-provider", ch_args)
        self.assertIn("--config", ch_args)
        self.assertIn(str(ch_cfg), ch_args)
        self.assertIn("CHUNKHOUND_LLM_API_KEY", ch_env_vars)
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
        self.assertIn(str(repo), joined)
        self.assertNotIn("--no-daemon", joined)


class CodexJsonProgressTests(unittest.TestCase):
    def test_codex_review_artifact_heuristic_prefers_real_review_markdown(self) -> None:
        review_text = "\n".join(
            [
                "### Steps taken",
                "- inspected diff",
                "",
                "**Summary**: Found two regressions.",
                "",
                "## Business / Product Assessment",
                "**Verdict**: REQUEST CHANGES",
                "",
                "## Technical Assessment",
                "**Verdict**: REQUEST CHANGES",
            ]
        )
        self.assertTrue(cure_llm._looks_like_codex_review_artifact(review_text))
        self.assertFalse(
            cure_llm._looks_like_codex_review_artifact(
                "Subagent shutdown notifications received; the review findings and verdicts above are unchanged."
            )
        )

    def test_codex_json_event_sink_preserves_raw_events_and_emits_readable_progress(self) -> None:
        raw = StringIO()
        display = StringIO()
        tail = rui.TailBuffer(max_lines=10)
        events: list[dict[str, object]] = []
        long_message = "Checking changed files " + ("and narrowing scope " * 20)
        sink = cure_output.CodexJsonEventSink(
            raw_file=raw,
            display_file=display,
            tail=tail,
            on_event=events.append,
        )

        sink.write('{"type":"thread.started","thread_id":"abc"}\n')
        sink.write(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"id": "item_1", "type": "agent_message", "text": long_message},
                }
            )
            + "\n"
        )
        sink.flush()

        self.assertIn('"type":"thread.started"', raw.getvalue())
        self.assertIn("Codex session started.", display.getvalue())
        self.assertIn("Checking changed files", display.getvalue())
        self.assertEqual(events[-1]["type"], "agent_message")
        self.assertEqual(events[-1]["raw_text"], long_message)
        self.assertEqual(events[-1]["text"], cure_output._compact_codex_text(long_message))
        self.assertEqual(tail.tail(2)[-1], cure_output._compact_codex_text(long_message))

    def test_watch_line_for_payload_appends_live_progress_summary(self) -> None:
        payload = {
            "session_id": "session-123",
            "status": "running",
            "phase": "codex_review",
            "pr": {"owner": "acme", "repo": "repo", "number": 12},
            "llm": {"summary": "llm=default/gpt-5/?"},
            "live_progress": {
                "current": {"type": "agent_message", "text": "Checking changed files and narrowing scope"},
            },
        }
        line = cure_commands._watch_line_for_payload(payload)
        self.assertIn("current=Checking changed files and narrowing scope", line)

    def test_run_codex_exec_json_mode_keeps_review_artifact_when_final_message_is_status_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            output_path = Path(tmp) / "review.md"
            review_text = "\n".join(
                [
                    "### Steps taken",
                    "- inspected diff",
                    "",
                    "**Summary**: Found two regressions.",
                    "",
                    "## Business / Product Assessment",
                    "**Verdict**: REQUEST CHANGES",
                    "",
                    "## Technical Assessment",
                    "**Verdict**: REQUEST CHANGES",
                ]
            )

            class _DummyProgress:
                def __init__(self, root: Path) -> None:
                    self.meta = {
                        "logs": {"codex_events": str(root / "codex.events.jsonl")},
                        "live_progress": {},
                    }

                def record_cmd(self, cmd: list[str]) -> None:
                    self.last_cmd = list(cmd)

                def flush(self) -> None:
                    return None

            progress = _DummyProgress(Path(tmp))
            out = mock.Mock()
            out.ui_enabled = True

            def fake_run_logged_cmd(*args: object, **kwargs: object) -> None:
                callback = kwargs["codex_event_callback"]
                assert callback is not None
                callback({"type": "agent_message", "text": review_text, "ts": "2026-03-17T07:35:02+00:00"})
                callback(
                    {
                        "type": "agent_message",
                        "text": "Subagent shutdown notifications received; the review findings and verdicts above are unchanged.",
                        "ts": "2026-03-17T07:35:18+00:00",
                    }
                )
                output_path.write_text(
                    "Subagent shutdown notifications received; the review findings and verdicts above are unchanged.\n",
                    encoding="utf-8",
                )

            out.run_logged_cmd.side_effect = fake_run_logged_cmd

            with mock.patch.object(cure_llm, "active_output", return_value=out), mock.patch.object(
                cure_llm, "find_codex_resume_info", return_value=None
            ):
                rf.run_codex_exec(
                    repo_dir=repo_dir,
                    codex_flags=["-m", "gpt-5.2"],
                    codex_config_overrides=[],
                    output_path=output_path,
                    prompt="hello",
                    env={},
                    stream=True,
                    progress=progress,
                )

            rendered = output_path.read_text(encoding="utf-8")
            self.assertIn("**Summary**: Found two regressions.", rendered)
            self.assertNotIn("Subagent shutdown notifications received", rendered)

    def test_run_codex_exec_json_mode_uses_raw_review_text_for_artifact_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            output_path = Path(tmp) / "review.md"
            review_text = "\n".join(
                [
                    "### Steps taken",
                    "- inspected diff",
                    "",
                    "**Summary**: Found two regressions and one follow-up risk.",
                    "",
                    "## Business / Product Assessment",
                    "**Verdict**: APPROVE",
                    "",
                    "### Strengths",
                    "- " + " ".join(["Business strength"] * 20),
                    "",
                    "## Technical Assessment",
                    "**Verdict**: REQUEST CHANGES",
                    "",
                    "### In Scope Issues",
                    "- " + " ".join(["Technical issue"] * 20),
                ]
            )
            compact_preview = cure_output._compact_codex_text(review_text)

            class _DummyProgress:
                def __init__(self, root: Path) -> None:
                    self.meta = {
                        "logs": {"codex_events": str(root / "codex.events.jsonl")},
                        "live_progress": {},
                    }

                def record_cmd(self, cmd: list[str]) -> None:
                    self.last_cmd = list(cmd)

                def flush(self) -> None:
                    return None

            progress = _DummyProgress(Path(tmp))
            out = mock.Mock()
            out.ui_enabled = True

            def fake_run_logged_cmd(*args: object, **kwargs: object) -> None:
                callback = kwargs["codex_event_callback"]
                assert callback is not None
                callback(
                    {
                        "type": "agent_message",
                        "text": compact_preview,
                        "raw_text": review_text,
                        "ts": "2026-03-17T08:08:41+00:00",
                    }
                )
                output_path.write_text(review_text + "\n", encoding="utf-8")

            out.run_logged_cmd.side_effect = fake_run_logged_cmd

            with mock.patch.object(cure_llm, "active_output", return_value=out), mock.patch.object(
                cure_llm, "find_codex_resume_info", return_value=None
            ):
                rf.run_codex_exec(
                    repo_dir=repo_dir,
                    codex_flags=["-m", "gpt-5.2"],
                    codex_config_overrides=[],
                    output_path=output_path,
                    prompt="hello",
                    env={},
                    stream=True,
                    progress=progress,
                )

            rendered = output_path.read_text(encoding="utf-8")
            self.assertEqual(rendered, review_text + "\n")
            self.assertNotEqual(rendered, compact_preview + "\n")
            verdicts = rf.extract_review_verdicts_from_markdown(rendered)
            assert verdicts is not None
            self.assertEqual(verdicts.business, "APPROVE")
            self.assertEqual(verdicts.technical, "REQUEST CHANGES")

    def test_build_status_payload_includes_live_progress_and_codex_events_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_dir = root / "session-123"
            repo_dir = session_dir / "repo"
            logs_dir = session_dir / "work" / "logs"
            review_md = session_dir / "review.md"
            repo_dir.mkdir(parents=True, exist_ok=True)
            logs_dir.mkdir(parents=True, exist_ok=True)
            review_md.write_text("# Review\n", encoding="utf-8")
            for name in ("reviewflow.log", "chunkhound.log", "codex.log", "codex.events.jsonl"):
                (logs_dir / name).write_text(name + "\n", encoding="utf-8")
            meta = {
                "session_id": "session-123",
                "status": "running",
                "phase": "codex_review",
                "phases": {"codex_review": {"status": "running"}},
                "host": "github.com",
                "owner": "acme",
                "repo": "repo",
                "number": 12,
                "created_at": "2026-03-17T12:00:00+00:00",
                "paths": {
                    "repo_dir": str(repo_dir),
                    "work_dir": str(session_dir / "work"),
                    "logs_dir": str(logs_dir),
                    "review_md": str(review_md),
                },
                "logs": {
                    "reviewflow": str(logs_dir / "reviewflow.log"),
                    "chunkhound": str(logs_dir / "chunkhound.log"),
                    "codex": str(logs_dir / "codex.log"),
                    "codex_events": str(logs_dir / "codex.events.jsonl"),
                },
                "live_progress": {
                    "source": "codex_exec_json",
                    "provider": "codex",
                    "current": {"type": "agent_message", "text": "Checking changed files"},
                },
            }
            (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

            payload = rf.build_status_payload("session-123", sandbox_root=root)

        self.assertIn("live_progress", payload)
        self.assertIn("codex_events", payload["logs"])

    def test_build_status_payload_includes_chunkhound_last_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_dir = root / "session-idx"
            repo_dir = session_dir / "repo"
            logs_dir = session_dir / "work" / "logs"
            review_md = session_dir / "review.md"
            repo_dir.mkdir(parents=True, exist_ok=True)
            logs_dir.mkdir(parents=True, exist_ok=True)
            review_md.write_text("# Review\n", encoding="utf-8")
            for name in ("reviewflow.log", "chunkhound.log", "codex.log"):
                (logs_dir / name).write_text(name + "\n", encoding="utf-8")
            meta = {
                "session_id": "session-idx",
                "status": "running",
                "phase": "index_topup",
                "phases": {"index_topup": {"status": "running"}},
                "host": "github.com",
                "owner": "acme",
                "repo": "repo",
                "number": 12,
                "created_at": "2026-03-17T12:00:00+00:00",
                "paths": {
                    "repo_dir": str(repo_dir),
                    "work_dir": str(session_dir / "work"),
                    "logs_dir": str(logs_dir),
                    "review_md": str(review_md),
                },
                "logs": {
                    "reviewflow": str(logs_dir / "reviewflow.log"),
                    "chunkhound": str(logs_dir / "chunkhound.log"),
                    "codex": str(logs_dir / "codex.log"),
                },
                "chunkhound": {
                    "last_index": {
                        "scope": "topup",
                        "processed_files": 4,
                        "skipped_files": 1,
                        "error_files": 0,
                        "total_chunks": 84,
                        "embeddings": 84,
                        "duration_text": "17.23s",
                    }
                },
            }
            (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

            payload = rf.build_status_payload("session-idx", sandbox_root=root)

        self.assertIn("chunkhound", payload)
        self.assertEqual(payload["chunkhound"]["last_index"]["embeddings"], 84)


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
    def test_parse_chunkhound_index_summary_extracts_full_run_metrics(self) -> None:
        summary = chunkhound_summary.parse_chunkhound_index_summary(
            "\n".join(
                [
                    "Initial stats: 0 files, 0 chunks, 0 embeddings",
                    "Processing Complete",
                    "Processed: 1 files",
                    "Skipped: 0 files",
                    "Errors: 0 files",
                    "Total chunks: 1",
                    "Embeddings: 0",
                    "Time: 0.07s",
                ]
            ),
            scope="topup",
        )
        assert summary is not None
        self.assertEqual(summary["scope"], "topup")
        self.assertEqual(summary["initial_files"], 0)
        self.assertEqual(summary["processed_files"], 1)
        self.assertEqual(summary["total_chunks"], 1)
        self.assertEqual(summary["embeddings"], 0)
        self.assertEqual(summary["duration_text"], "0.07s")

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

        args4 = p.parse_args(["clean"])
        self.assertIsNone(args4.session_id)

        args5 = p.parse_args(["clean", "session-123"])
        self.assertEqual(args5.session_id, "session-123")

        args6 = p.parse_args(["commands", "--json"])
        self.assertTrue(args6.json_output)

        args7 = p.parse_args(["status", "session-123", "--json"])
        self.assertEqual(args7.target, "session-123")
        self.assertTrue(args7.json_output)

        args8 = p.parse_args(
            [
                "watch",
                "https://github.com/acme/repo/pull/1",
                "--interval",
                "5",
                "--verbosity",
                "quiet",
                "--no-color",
            ]
        )
        self.assertEqual(args8.target, "https://github.com/acme/repo/pull/1")
        self.assertEqual(args8.interval, 5.0)
        self.assertEqual(args8.verbosity, "quiet")
        self.assertTrue(args8.no_color)

        args9 = p.parse_args(["clean", "closed", "--yes", "--json"])
        self.assertEqual(args9.session_id, "closed")
        self.assertTrue(args9.yes)
        self.assertTrue(args9.json_output)

    def test_parser_help_marks_pr_no_index_as_advanced_and_hides_resume_no_index(self) -> None:
        parser = rf.build_parser()
        subparsers = next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))
        pr_help = subparsers.choices["pr"].format_help()
        resume_help = subparsers.choices["resume"].format_help()

        self.assertIn("--no-index", pr_help)
        self.assertIn("Advanced opt-out for custom prompt flows", pr_help)
        self.assertRegex(pr_help, r"not\s+recommended")
        self.assertNotIn("--no-index", resume_help)

        resume_args = parser.parse_args(["resume", "session-123", "--no-index"])
        self.assertTrue(resume_args.no_index)

    def test_parser_accepts_runtime_overrides_before_and_after_subcommand(self) -> None:
        p = rf.build_parser()
        args = p.parse_args(["--config", "/tmp/reviewflow.toml", "doctor"])
        self.assertEqual(args.config_path, "/tmp/reviewflow.toml")

        args2 = p.parse_args(
            [
                "doctor",
                "--config",
                "/tmp/reviewflow.toml",
                "--agent-runtime-profile",
                "strict",
                "--sandbox-root",
                "/tmp/sandboxes",
                "--cache-root",
                "/tmp/cache",
                "--codex-config",
                "/tmp/codex.toml",
            ]
        )
        self.assertEqual(args2.config_path, "/tmp/reviewflow.toml")
        self.assertFalse(args2.no_config)
        self.assertEqual(args2.agent_runtime_profile, "strict")
        self.assertEqual(args2.sandbox_root, "/tmp/sandboxes")
        self.assertEqual(args2.cache_root, "/tmp/cache")
        self.assertEqual(args2.codex_config_path, "/tmp/codex.toml")
        args3 = p.parse_args(["doctor", "--no-config", "--json"])
        self.assertTrue(args3.no_config)
        self.assertTrue(args3.json_output)
        args4 = p.parse_args(["doctor", "--pr-url", "https://github.com/acme/repo/pull/1", "--json"])
        self.assertEqual(args4.pr_url, "https://github.com/acme/repo/pull/1")
        self.assertTrue(args4.json_output)
        args5 = p.parse_args(["init", "--config", "/tmp/cure.toml", "--sandbox-root", "/tmp/sandboxes", "--force"])
        self.assertEqual(args5.config_path, "/tmp/cure.toml")
        self.assertEqual(args5.sandbox_root, "/tmp/sandboxes")
        self.assertTrue(args5.force)

    def test_parser_accepts_install_command(self) -> None:
        p = rf.build_parser()
        self.assertEqual(p.prog, "cure")
        args = p.parse_args(["install", "--chunkhound-source", "git-main"])
        self.assertEqual(args.chunkhound_source, "git-main")

    def test_deprecated_alias_warning_targets_stderr_only(self) -> None:
        stderr = StringIO()
        rf.maybe_warn_deprecated_cli_alias("reviewflow", stderr=stderr)
        self.assertIn("Use `cure` instead.", stderr.getvalue())

        quiet = StringIO()
        rf.maybe_warn_deprecated_cli_alias("cure", stderr=quiet)
        self.assertEqual(quiet.getvalue(), "")

    def test_console_main_warns_for_deprecated_alias_and_dispatches(self) -> None:
        stderr = StringIO()
        with mock.patch.object(rf.sys, "argv", ["reviewflow", "commands"]), mock.patch.object(
            rf, "main", return_value=9
        ) as main_mock, contextlib.redirect_stderr(stderr):
            rc = rf.console_main()

        self.assertEqual(rc, 9)
        self.assertIn("Use `cure` instead.", stderr.getvalue())
        main_mock.assert_called_once_with(["commands"], prog="cure")

    def test_parser_accepts_zip_flags(self) -> None:
        p = rf.build_parser()
        args = p.parse_args(
            [
                "zip",
                "https://github.com/acme/repo/pull/9",
                "--llm-preset",
                "openrouter_grok",
                "--llm-model",
                "x-ai/grok-4.1-fast",
                "--llm-effort",
                "high",
                "--llm-plan-effort",
                "xhigh",
                "--llm-verbosity",
                "low",
                "--llm-max-output-tokens",
                "9000",
                "--llm-set",
                "top_p=0.9",
                "--llm-header",
                "HTTP-Referer=https://example.com",
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
        self.assertEqual(args.llm_preset, "openrouter_grok")
        self.assertEqual(args.llm_model, "x-ai/grok-4.1-fast")
        self.assertEqual(args.llm_effort, "high")
        self.assertEqual(args.llm_plan_effort, "xhigh")
        self.assertEqual(args.llm_verbosity, "low")
        self.assertEqual(args.llm_max_output_tokens, 9000)
        self.assertEqual(args.llm_set, ["top_p=0.9"])
        self.assertEqual(args.llm_header, ["HTTP-Referer=https://example.com"])
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


class RuntimeResolutionTests(unittest.TestCase):
    def _runtime_args(self, **overrides: object) -> argparse.Namespace:
        payload = {
            "config_path": None,
            "no_config": False,
            "agent_runtime_profile": None,
            "sandbox_root": None,
            "cache_root": None,
            "codex_config_path": None,
        }
        payload.update(overrides)
        return argparse.Namespace(**payload)

    def test_resolve_reviewflow_config_path_prefers_cli_then_env(self) -> None:
        args = self._runtime_args(config_path="/tmp/cli.toml")
        with mock.patch.dict(
            os.environ,
            {
                "CURE_CONFIG": "/tmp/cure-env.toml",
                "REVIEWFLOW_CONFIG": "/tmp/legacy-env.toml",
            },
            clear=False,
        ):
            self.assertEqual(
                rf.resolve_reviewflow_config_path(args),
                (Path("/tmp/cli.toml"), "cli", True),
            )
        args = self._runtime_args()
        with mock.patch.dict(
            os.environ,
            {
                "CURE_CONFIG": "/tmp/cure-env.toml",
                "REVIEWFLOW_CONFIG": "/tmp/legacy-env.toml",
            },
            clear=False,
        ):
            self.assertEqual(
                rf.resolve_reviewflow_config_path(args),
                (Path("/tmp/cure-env.toml"), "env", True),
            )

    def test_resolve_reviewflow_config_path_uses_xdg_default(self) -> None:
        args = self._runtime_args()
        with mock.patch.dict(
            os.environ,
            {
                "CURE_CONFIG": "",
                "REVIEWFLOW_CONFIG": "",
                "XDG_CONFIG_HOME": "/tmp/xdg-config",
            },
            clear=False,
        ):
            self.assertEqual(
                rf.resolve_reviewflow_config_path(args),
                (Path("/tmp/xdg-config/cure/cure.toml"), "default", True),
            )

    def test_resolve_reviewflow_config_path_marks_selected_file_disabled(self) -> None:
        args = self._runtime_args(config_path="/tmp/cli.toml", no_config=True)
        self.assertEqual(
            rf.resolve_reviewflow_config_path(args),
            (Path("/tmp/cli.toml"), "cli", False),
        )

    def test_resolve_reviewflow_config_path_falls_back_to_legacy_env(self) -> None:
        args = self._runtime_args()
        with mock.patch.dict(
            os.environ,
            {
                "CURE_CONFIG": "",
                "REVIEWFLOW_CONFIG": "/tmp/legacy-env.toml",
            },
            clear=False,
        ):
            self.assertEqual(
                rf.resolve_reviewflow_config_path(args),
                (Path("/tmp/legacy-env.toml"), "legacy-env", True),
            )

    def test_resolve_reviewflow_config_path_falls_back_to_legacy_default_if_present(self) -> None:
        root = ROOT / ".tmp_test_legacy_config_default"
        cure_cfg = root / "cure" / "cure.toml"
        legacy_cfg = root / "reviewflow" / "reviewflow.toml"
        try:
            shutil.rmtree(root, ignore_errors=True)
            legacy_cfg.parent.mkdir(parents=True, exist_ok=True)
            legacy_cfg.write_text("", encoding="utf-8")
            args = self._runtime_args()
            with mock.patch.object(rf, "default_reviewflow_config_path", return_value=cure_cfg), mock.patch.object(
                rf,
                "legacy_default_reviewflow_config_path",
                return_value=legacy_cfg,
                create=True,
            ):
                self.assertEqual(
                    rf.resolve_reviewflow_config_path(args),
                    (legacy_cfg, "legacy-default", True),
                )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_resolve_runtime_uses_xdg_defaults_when_unset(self) -> None:
        args = self._runtime_args()
        with mock.patch.object(
            rf,
            "default_codex_base_config_path",
            return_value=Path("/home/tester/.codex/config.toml"),
        ), mock.patch.dict(
            os.environ,
            {
                "CURE_CONFIG": "",
                "CURE_SANDBOX_ROOT": "",
                "CURE_CACHE_ROOT": "",
                "CURE_CODEX_CONFIG": "",
                "REVIEWFLOW_CONFIG": "",
                "REVIEWFLOW_SANDBOX_ROOT": "",
                "REVIEWFLOW_CACHE_ROOT": "",
                "REVIEWFLOW_CODEX_CONFIG": "",
                "XDG_CONFIG_HOME": "/tmp/xdg-config",
                "XDG_STATE_HOME": "/tmp/xdg-state",
                "XDG_CACHE_HOME": "/tmp/xdg-cache",
            },
            clear=False,
        ):
            runtime = rf.resolve_runtime(args)
        self.assertEqual(runtime.config_path, Path("/tmp/xdg-config/cure/cure.toml"))
        self.assertEqual(runtime.config_source, "default")
        self.assertTrue(runtime.config_enabled)
        self.assertEqual(runtime.paths.sandbox_root, Path("/tmp/xdg-state/cure/sandboxes"))
        self.assertEqual(runtime.sandbox_root_source, "default")
        self.assertEqual(runtime.paths.cache_root, Path("/tmp/xdg-cache/cure"))
        self.assertEqual(runtime.cache_root_source, "default")
        self.assertEqual(runtime.codex_base_config_path, Path("/home/tester/.codex/config.toml"))
        self.assertEqual(runtime.codex_base_config_source, "default")

    def test_resolve_runtime_prefers_cure_env_over_legacy_env(self) -> None:
        args = self._runtime_args()
        with mock.patch.object(
            rf,
            "default_codex_base_config_path",
            return_value=Path("/home/tester/.codex/config.toml"),
        ), mock.patch.dict(
            os.environ,
            {
                "CURE_CONFIG": "/tmp/cure-env.toml",
                "CURE_SANDBOX_ROOT": "/tmp/cure-sandboxes",
                "CURE_CACHE_ROOT": "/tmp/cure-cache",
                "CURE_CODEX_CONFIG": "/tmp/cure-codex.toml",
                "REVIEWFLOW_CONFIG": "/tmp/legacy-env.toml",
                "REVIEWFLOW_SANDBOX_ROOT": "/tmp/legacy-sandboxes",
                "REVIEWFLOW_CACHE_ROOT": "/tmp/legacy-cache",
                "REVIEWFLOW_CODEX_CONFIG": "/tmp/legacy-codex.toml",
            },
            clear=False,
        ):
            runtime = rf.resolve_runtime(args)
        self.assertEqual(runtime.config_path, Path("/tmp/cure-env.toml"))
        self.assertEqual(runtime.config_source, "env")
        self.assertEqual(runtime.paths.sandbox_root, Path("/tmp/cure-sandboxes"))
        self.assertEqual(runtime.sandbox_root_source, "env")
        self.assertEqual(runtime.paths.cache_root, Path("/tmp/cure-cache"))
        self.assertEqual(runtime.cache_root_source, "env")
        self.assertEqual(runtime.codex_base_config_path, Path("/tmp/cure-codex.toml"))
        self.assertEqual(runtime.codex_base_config_source, "env")


class CanonicalShellOwnershipTests(RuntimeResolutionTests):
    def test_cure_is_the_canonical_shell_surface(self) -> None:
        self.assertIs(cure.init_flow, cure_commands.init_flow)
        self.assertIs(cure.render_prompt, cure_flows.render_prompt)
        self.assertIs(cure.run_llm_exec, cure_llm.run_llm_exec)
        self.assertIs(cure.commands_flow, cure_commands.commands_flow)
        self.assertIs(cure.status_flow, cure_commands.status_flow)
        self.assertIs(cure.watch_flow, cure_commands.watch_flow)

    def test_reviewflow_reexports_active_extracted_owners(self) -> None:
        self.assertIs(rf.resolve_runtime, cure_runtime.resolve_runtime)
        self.assertIs(rf.init_flow, cure_commands.init_flow)
        self.assertIs(rf.render_prompt, cure_flows.render_prompt)
        self.assertIs(rf.run_llm_exec, cure_llm.run_llm_exec)
        self.assertIs(rf.commands_flow, cure_commands.commands_flow)
        self.assertIs(rf.status_flow, cure_commands.status_flow)
        self.assertIs(rf.watch_flow, cure_commands.watch_flow)

    def test_cure_main_uses_canonical_build_parser(self) -> None:
        args = argparse.Namespace(cmd="commands", json_output=True)
        parser = mock.Mock()
        parser.parse_args.return_value = args
        runtime = self._runtime()
        with mock.patch.object(cure, "build_parser", return_value=parser) as build_parser, mock.patch.object(
            cure_runtime, "resolve_runtime", return_value=runtime
        ) as resolve_runtime, mock.patch.object(
            cure_commands, "commands_flow", return_value=13
        ) as commands_flow:
            rc = cure.main(["commands", "--json"])

        self.assertEqual(rc, 13)
        build_parser.assert_called_once_with(prog="cure")
        resolve_runtime.assert_called_once_with(args)
        commands_flow.assert_called_once_with(args)

    def test_reviewflow_main_forwards_to_cure_main(self) -> None:
        with mock.patch.object(cure, "main", return_value=19) as cure_main:
            rc = rf.main(["commands", "--json"])

        self.assertEqual(rc, 19)
        cure_main.assert_called_once()
        self.assertEqual(cure_main.call_args.args[0], ["commands", "--json"])
        self.assertEqual(cure_main.call_args.kwargs["prog"], "cure")
        self.assertIs(cure_main.call_args.kwargs["_shell_module"], rf)

    def test_pyproject_points_public_package_to_cure_console_main(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(pyproject["project"]["name"], "cureview")
        self.assertEqual(pyproject["project"]["scripts"]["cure"], "cure:console_main")
        self.assertNotIn("reviewflow", pyproject["project"]["scripts"])
        self.assertIn("cure", pyproject["tool"]["setuptools"]["py-modules"])

    def _runtime(self) -> rf.ReviewflowRuntime:
        return rf.ReviewflowRuntime(
            config_path=Path("/tmp/reviewflow.toml"),
            config_source="cli",
            config_enabled=True,
            paths=rf.ReviewflowPaths(
                sandbox_root=Path("/tmp/sandboxes"),
                cache_root=Path("/tmp/cache"),
            ),
            sandbox_root_source="cli",
            cache_root_source="cli",
            codex_base_config_path=Path("/tmp/codex.toml"),
            codex_base_config_source="cli",
        )

    def test_main_dispatches_pr_via_cure_runtime_and_cure_commands(self) -> None:
        runtime = self._runtime()
        with mock.patch.object(cure_runtime, "resolve_runtime", return_value=runtime) as resolve_runtime, mock.patch.object(
            cure_commands, "pr_flow", return_value=17
        ) as pr_flow:
            rc = rf.main(["pr", "https://github.com/acme/repo/pull/1"])

        self.assertEqual(rc, 17)
        resolve_runtime.assert_called_once()
        pr_flow.assert_called_once()

    def test_main_dispatches_status_via_cure_runtime_and_cure_commands(self) -> None:
        runtime = self._runtime()
        with mock.patch.object(cure_runtime, "resolve_runtime", return_value=runtime) as resolve_runtime, mock.patch.object(
            cure_commands, "status_flow", return_value=3
        ) as status_flow:
            rc = rf.main(["status", "session-123"])

        self.assertEqual(rc, 3)
        resolve_runtime.assert_called_once()
        status_flow.assert_called_once()

    def test_main_dispatches_doctor_via_cure_runtime_and_cure_commands(self) -> None:
        runtime = self._runtime()
        with mock.patch.object(cure_runtime, "resolve_runtime", return_value=runtime) as resolve_runtime, mock.patch.object(
            cure_commands, "doctor_flow", return_value=5
        ) as doctor_flow:
            rc = rf.main(["doctor"])

        self.assertEqual(rc, 5)
        resolve_runtime.assert_called_once()
        doctor_flow.assert_called_once_with(mock.ANY, runtime=runtime)

    def test_main_dispatches_init_via_cure_runtime_and_cure_commands(self) -> None:
        runtime = self._runtime()
        with mock.patch.object(cure_runtime, "resolve_runtime", return_value=runtime) as resolve_runtime, mock.patch.object(
            cure_commands, "init_flow", return_value=7
        ) as init_flow:
            rc = rf.main(["init", "--force"])

        self.assertEqual(rc, 7)
        resolve_runtime.assert_called_once()
        self.assertEqual(init_flow.call_count, 1)
        self.assertTrue(init_flow.call_args.args[0].force)
        self.assertIs(init_flow.call_args.kwargs["runtime"], runtime)

    def test_console_main_warns_for_reviewflow_alias_and_dispatches_to_main(self) -> None:
        stderr = StringIO()
        with mock.patch.object(sys, "argv", ["reviewflow", "commands", "--json"]), contextlib.redirect_stderr(
            stderr
        ), mock.patch.object(rf, "main", return_value=9) as main_mock:
            rc = rf.console_main()

        self.assertEqual(rc, 9)
        self.assertIn("Use `cure` instead.", stderr.getvalue())
        main_mock.assert_called_once_with(["commands", "--json"], prog="cure")

    def test_resolve_runtime_ignores_relative_xdg_roots(self) -> None:
        args = self._runtime_args()
        with mock.patch.object(
            rf,
            "default_codex_base_config_path",
            return_value=Path("/home/tester/.codex/config.toml"),
        ), mock.patch.dict(
            os.environ,
            {
                "CURE_CONFIG": "",
                "CURE_SANDBOX_ROOT": "",
                "CURE_CACHE_ROOT": "",
                "CURE_CODEX_CONFIG": "",
                "REVIEWFLOW_CONFIG": "",
                "REVIEWFLOW_SANDBOX_ROOT": "",
                "REVIEWFLOW_CACHE_ROOT": "",
                "REVIEWFLOW_CODEX_CONFIG": "",
                "XDG_CONFIG_HOME": "relative-config",
                "XDG_STATE_HOME": "relative-state",
                "XDG_CACHE_HOME": "relative-cache",
            },
            clear=False,
        ), mock.patch.object(rf, "default_reviewflow_config_path", return_value=Path("/home/tester/.config/cure/cure.toml")), mock.patch.object(
            rf,
            "legacy_default_reviewflow_config_path",
            return_value=Path("/home/tester/.config/reviewflow/reviewflow.toml"),
            create=True,
        ), mock.patch.object(
            rf,
            "default_sandbox_root",
            return_value=Path("/home/tester/.local/state/cure/sandboxes"),
        ), mock.patch.object(
            rf,
            "legacy_default_sandbox_root",
            return_value=Path("/home/tester/.local/state/reviewflow/sandboxes"),
            create=True,
        ), mock.patch.object(
            rf,
            "default_cache_root",
            return_value=Path("/home/tester/.cache/cure"),
        ), mock.patch.object(
            rf,
            "legacy_default_cache_root",
            return_value=Path("/home/tester/.cache/reviewflow"),
            create=True,
        ):
            runtime = rf.resolve_runtime(args)
        self.assertEqual(runtime.config_path, Path("/home/tester/.config/cure/cure.toml"))
        self.assertEqual(runtime.paths.sandbox_root, Path("/home/tester/.local/state/cure/sandboxes"))
        self.assertEqual(runtime.paths.cache_root, Path("/home/tester/.cache/cure"))

    def test_resolve_runtime_prefers_cli_over_env_and_config(self) -> None:
        root = ROOT / ".tmp_test_runtime_resolution_cli"
        cfg = root / "reviewflow.toml"
        codex_cfg = root / "codex.toml"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            codex_cfg.write_text("", encoding="utf-8")
            cfg.write_text(
                "\n".join(
                    [
                        "[paths]",
                        'sandbox_root = "cfg-sandboxes"',
                        'cache_root = "cfg-cache"',
                        "",
                        "[codex]",
                        'base_config_path = "codex.toml"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            args = self._runtime_args(
                config_path=str(cfg),
                sandbox_root=str(root / "cli-sandboxes"),
                cache_root=str(root / "cli-cache"),
                codex_config_path=str(root / "cli-codex.toml"),
            )
            runtime = rf.resolve_runtime(args)
            self.assertEqual(runtime.config_path, cfg)
            self.assertEqual(runtime.config_source, "cli")
            self.assertEqual(runtime.paths.sandbox_root, (root / "cli-sandboxes").resolve())
            self.assertEqual(runtime.sandbox_root_source, "cli")
            self.assertEqual(runtime.paths.cache_root, (root / "cli-cache").resolve())
            self.assertEqual(runtime.cache_root_source, "cli")
            self.assertEqual(runtime.codex_base_config_path, (root / "cli-codex.toml").resolve())
            self.assertEqual(runtime.codex_base_config_source, "cli")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_resolve_runtime_prefers_env_over_config_for_paths(self) -> None:
        root = ROOT / ".tmp_test_runtime_resolution_env"
        cfg = root / "reviewflow.toml"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text(
                "\n".join(
                    [
                        "[paths]",
                        'sandbox_root = "cfg-sandboxes"',
                        'cache_root = "cfg-cache"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            args = self._runtime_args(config_path=str(cfg))
            with mock.patch.dict(
                os.environ,
                {
                    "CURE_SANDBOX_ROOT": str(root / "env-sandboxes"),
                    "CURE_CACHE_ROOT": str(root / "env-cache"),
                    "REVIEWFLOW_SANDBOX_ROOT": str(root / "legacy-sandboxes"),
                    "REVIEWFLOW_CACHE_ROOT": str(root / "legacy-cache"),
                },
                clear=False,
            ):
                runtime = rf.resolve_runtime(args)
            self.assertEqual(runtime.paths.sandbox_root, (root / "env-sandboxes").resolve())
            self.assertEqual(runtime.sandbox_root_source, "env")
            self.assertEqual(runtime.paths.cache_root, (root / "env-cache").resolve())
            self.assertEqual(runtime.cache_root_source, "env")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_resolve_runtime_no_config_ignores_reviewflow_toml(self) -> None:
        root = ROOT / ".tmp_test_runtime_resolution_no_config"
        cfg = root / "reviewflow.toml"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            cfg.write_text(
                "\n".join(
                    [
                        "[paths]",
                        'sandbox_root = "cfg-sandboxes"',
                        'cache_root = "cfg-cache"',
                        "",
                        "[codex]",
                        'base_config_path = "cfg-codex.toml"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            args = self._runtime_args(config_path=str(cfg), no_config=True)
            with mock.patch.object(rf, "default_sandbox_root", return_value=root / "default-sandboxes"), mock.patch.object(
                rf,
                "legacy_default_sandbox_root",
                return_value=root / "legacy-sandboxes",
                create=True,
            ), mock.patch.object(
                rf,
                "default_cache_root",
                return_value=root / "default-cache",
            ), mock.patch.object(
                rf,
                "legacy_default_cache_root",
                return_value=root / "legacy-cache",
                create=True,
            ), mock.patch.object(
                rf,
                "default_codex_base_config_path",
                return_value=root / "default-codex.toml",
            ):
                runtime = rf.resolve_runtime(args)
            self.assertFalse(runtime.config_enabled)
            self.assertEqual(runtime.config_path, cfg)
            self.assertEqual(runtime.paths.sandbox_root, (root / "default-sandboxes").resolve())
            self.assertEqual(runtime.paths.cache_root, (root / "default-cache").resolve())
            self.assertEqual(runtime.codex_base_config_path, (root / "default-codex.toml").resolve())
        finally:
            shutil.rmtree(root, ignore_errors=True)


class InstallAndDoctorTests(unittest.TestCase):
    def _runtime_args(self, **overrides: object) -> argparse.Namespace:
        payload = {
            "config_path": None,
            "no_config": False,
            "agent_runtime_profile": None,
            "sandbox_root": None,
            "cache_root": None,
            "codex_config_path": None,
        }
        payload.update(overrides)
        return argparse.Namespace(**payload)

    def test_build_chunkhound_install_command_uses_expected_specs(self) -> None:
        with mock.patch.object(rf, "_running_in_uv_tool_environment", return_value=False), mock.patch.object(
            rf.importlib.util, "find_spec", return_value=object()
        ):
            self.assertEqual(
                rf.build_chunkhound_install_command(chunkhound_source="release"),
                [sys.executable, "-m", "pip", "install", "--upgrade", "chunkhound"],
            )
            self.assertEqual(
                rf.build_chunkhound_install_command(chunkhound_source="git-main"),
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "git+https://github.com/chunkhound/chunkhound@main",
                ],
            )

    def test_build_chunkhound_install_command_uses_uv_tool_when_running_inside_uv_tool(self) -> None:
        with mock.patch.object(rf, "_running_in_uv_tool_environment", return_value=True), mock.patch.object(
            shutil, "which", return_value="/usr/bin/uv"
        ):
            cmd = rf.build_chunkhound_install_command(chunkhound_source="git-main")
        self.assertEqual(
            cmd,
            [
                "/usr/bin/uv",
                "tool",
                "install",
                "--force",
                "git+https://github.com/chunkhound/chunkhound@main",
            ],
        )

    def test_running_in_uv_tool_environment_detects_uv_tool_python_without_resolving_symlink(self) -> None:
        with mock.patch.object(rf, "_uv_tool_dir", return_value=Path("/home/vscode/.local/share/uv/tools")), mock.patch.object(
            rf.sys,
            "executable",
            "/home/vscode/.local/share/uv/tools/reviewflow/bin/python",
        ), mock.patch.object(
            rf.sys,
            "prefix",
            "/home/vscode/.local/share/uv/tools/reviewflow",
        ):
            self.assertTrue(rf._running_in_uv_tool_environment(uv_path="/usr/bin/uv"))

    def test_build_chunkhound_install_command_falls_back_to_uv_pip_when_pip_missing_outside_uv_tool(self) -> None:
        with mock.patch.object(rf, "_running_in_uv_tool_environment", return_value=False), mock.patch.object(
            rf.importlib.util, "find_spec", return_value=None
        ), mock.patch.object(shutil, "which", return_value="/usr/bin/uv"):
            cmd = rf.build_chunkhound_install_command(chunkhound_source="git-main")
        self.assertEqual(
            cmd,
            [
                "/usr/bin/uv",
                "pip",
                "install",
                "--python",
                sys.executable,
                "--upgrade",
                "git+https://github.com/chunkhound/chunkhound@main",
            ],
        )

    def test_readme_documents_uv_tool_install_flow(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("What CURe Is For", readme)
        self.assertIn("Quickstart", readme)
        self.assertIn("Agent Bootstrap From That Prompt", readme)
        self.assertIn("Advanced / Pre-Provisioned Environments", readme)
        self.assertIn("Minimal Config", readme)
        self.assertIn("Core Commands", readme)
        self.assertIn("What CURe Produces", readme)
        self.assertIn("Practical Premise", readme)
        self.assertIn("use <CURE_REPO_URL> to review <PR_URL>", readme)
        self.assertIn("use https://github.com/grzegorznowak/CURe to review https://github.com/chunkhound/chunkhound/pull/220", readme)
        self.assertIn("start with [SKILL.md](SKILL.md)", readme)
        self.assertIn("uv tool install cureview", readme)
        self.assertIn("uvx --from cureview cure init", readme)
        self.assertIn("Secondary Standalone Install", readme)
        self.assertIn("Use the standalone GitHub Release assets only when the package path is unavailable or inconvenient.", readme)
        self.assertIn("curl -fsSL https://raw.githubusercontent.com/grzegorznowak/CURe/main/install-cure.sh | sh", readme)
        self.assertIn("curl -fsSL https://raw.githubusercontent.com/grzegorznowak/CURe/main/install-cure.sh | sh -s -- --version v0.1.2", readme)
        self.assertIn("cure init", readme)
        self.assertIn("cure doctor --pr-url <PR_URL> --json", readme)
        self.assertIn("cure commands --json", readme)
        self.assertIn("cure status <session_id|PR_URL> --json", readme)
        self.assertIn("cure watch <session_id|PR_URL>", readme)
        self.assertIn("cure pr <PR_URL> --if-reviewed new", readme)
        self.assertIn("The operator should not need to provide a local checkout path", readme)
        self.assertIn("It should not do a manual review outside CURe.", readme)
        self.assertIn("XDG_CONFIG_HOME", readme)
        self.assertIn("XDG_STATE_HOME", readme)
        self.assertIn("XDG_CACHE_HOME", readme)
        self.assertIn("~/.config/cure/cure.toml", readme)
        self.assertIn("~/.config/cure/chunkhound-base.json", readme)
        self.assertIn("VOYAGE_API_KEY", readme)
        self.assertIn("OPENAI_API_KEY", readme)
        self.assertIn("the project checkout stays untouched", readme)
        self.assertIn("./selftest.sh", readme)
        self.assertLess(readme.index("## Quickstart"), readme.index("## What CURe Is For"))
        self.assertIn("Hard Rule", skill)
        self.assertIn("When To Use CURe", skill)
        self.assertIn("Primary Inputs", skill)
        self.assertIn("Bootstrap From A Pristine Environment", skill)
        self.assertIn("What Success Looks Like", skill)
        self.assertIn("When To Stop And Ask", skill)
        self.assertIn("Canonical Agent Prompt", skill)
        self.assertIn("Use CURe from <CURE_REPO_URL> to review <PR_URL>.", skill)
        self.assertIn("If the operator asked to use CURe, do not perform a manual review outside CURe.", skill)
        self.assertIn("curl -LsSf https://astral.sh/uv/install.sh | sh", skill)
        self.assertIn("https://docs.astral.sh/uv/getting-started/installation/", skill)
        self.assertIn("uv tool install cureview", skill)
        self.assertIn("uvx --from cureview cure --help", skill)
        self.assertIn("uvx --from cureview cure init", skill)
        self.assertIn("Secondary standalone fallback only when the package path is unavailable:", skill)
        self.assertIn("curl -fsSL https://raw.githubusercontent.com/grzegorznowak/CURe/main/install-cure.sh | sh", skill)
        self.assertIn("curl -fsSL https://raw.githubusercontent.com/grzegorznowak/CURe/main/install-cure.sh | sh -s -- --version v0.1.2", skill)
        self.assertIn("The standalone path is a secondary fallback for Linux x86_64, macOS x86_64, and macOS arm64 only.", skill)
        self.assertIn("uv tool install /path/to/cure", skill)
        self.assertIn("uv tool install --editable /path/to/cure", skill)
        self.assertIn("--config /tmp/cure-public/cure.toml", skill)
        self.assertIn("XDG_CONFIG_HOME", skill)
        self.assertIn("cure install", skill)
        self.assertIn("`cure install` provisions ChunkHound only", skill)
        self.assertIn("Run `cure init` before `cure install` or `cure doctor`.", skill)
        self.assertIn("If `VOYAGE_API_KEY` exists, `cure init` writes:", skill)
        self.assertIn("If `VOYAGE_API_KEY` is missing but `OPENAI_API_KEY` exists, `cure init` writes:", skill)
        self.assertIn("If a required embedding secret is still missing", skill)
        self.assertNotIn("pip install", readme)

    def test_skill_documents_proactive_secret_and_config_remediation(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("cure.toml", skill)
        self.assertIn("chunkhound-base.json", skill)
        self.assertIn("Bootstrap everything non-secret before you stop:", skill)
        self.assertIn("run `cure init`", skill)
        self.assertIn("create `~/.config/cure/cure.toml` only when `cure init` is unavailable", skill)
        self.assertIn("create `~/.config/cure/chunkhound-base.json` only when `cure init` is unavailable", skill)
        self.assertIn("auto-wire embeddings if `VOYAGE_API_KEY` or `OPENAI_API_KEY` already exists", skill)
        self.assertIn("prefer a current-shell export for the immediate retry", skill)
        self.assertIn("shell profile or existing local secret manager for persistence", skill)
        self.assertIn("VOYAGE_API_KEY", skill)
        self.assertIn("OPENAI_API_KEY", skill)
        self.assertIn("never ask the operator to paste a secret into chat", skill)
        self.assertIn("If `chunkhound index ...` or `cure doctor --pr-url <PR_URL> --json` fails because neither `VOYAGE_API_KEY` nor `OPENAI_API_KEY` is present", skill)
        self.assertIn("I checked ~/.config/cure/cure.toml", skill)
        self.assertIn("\"provider\": \"voyage\"", skill)
        self.assertIn("\"model\": \"voyage-code-3\"", skill)
        self.assertIn("rerun `cure init --force`", skill)
        self.assertIn("\"provider\": \"openai\"", skill)
        self.assertIn("\"model\": \"text-embedding-3-small\"", skill)
        self.assertIn("cure pr <PR_URL> --if-reviewed new", skill)

    def test_docs_mark_no_index_as_advanced_opt_out(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("That indexed ChunkHound-backed path is the default and recommended public review workflow.", readme)
        self.assertIn("Once the first run is active, continue the same indexed session with `cure resume <session_id|PR_URL>`.", readme)
        self.assertIn("`cure pr --no-index` remains available only as an advanced opt-out", readme)
        self.assertIn("It is not the normal or recommended path.", readme)
        self.assertLess(readme.index("cure doctor --pr-url <PR_URL> --json"), readme.index("cure pr <PR_URL> --if-reviewed new"))
        self.assertLess(readme.index("cure pr <PR_URL> --if-reviewed new"), readme.index("cure resume <session_id|PR_URL>"))

        self.assertIn("That indexed ChunkHound-backed path is the default and recommended review workflow:", skill)
        self.assertIn("`cure pr --no-index` remains available only as an advanced opt-out", skill)
        self.assertIn("It is not the normal or recommended path.", skill)
        self.assertLess(skill.index("cure doctor --pr-url <PR_URL> --json"), skill.index("cure pr <PR_URL> --if-reviewed new"))
        self.assertLess(skill.index("cure pr <PR_URL> --if-reviewed new"), skill.index("cure resume <session_id|PR_URL>"))

    def test_docs_explain_chunkhound_tools_first_discovery_behavior(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        for text in (readme, skill):
            self.assertIn("tools-first MCP server", text)
            self.assertIn("`list_mcp_resources`", text)
            self.assertIn("`list_mcp_resource_templates`", text)
            self.assertIn("not an outage signal", text)
            self.assertIn("`search` or `code_research`", text)
            self.assertIn("Treat availability as proven only when a real", text)

    def test_init_flow_writes_public_bootstrap_files(self) -> None:
        root = ROOT / ".tmp_test_cure_init"
        config_path = root / "config" / "cure.toml"
        base_path = root / "config" / "chunkhound-base.json"
        runtime = rf.ReviewflowRuntime(
            config_path=config_path,
            config_source="cli",
            config_enabled=True,
            paths=rf.ReviewflowPaths(
                sandbox_root=root / "state" / "sandboxes",
                cache_root=root / "cache",
            ),
            sandbox_root_source="cli",
            cache_root_source="cli",
            codex_base_config_path=root / ".codex" / "config.toml",
            codex_base_config_source="default",
        )
        stdout = StringIO()
        try:
            shutil.rmtree(root, ignore_errors=True)
            with mock.patch.dict(os.environ, {"VOYAGE_API_KEY": "test-voyage"}, clear=False), contextlib.redirect_stdout(  # pragma: allowlist secret
                stdout
            ):
                rc = rf.init_flow(argparse.Namespace(force=False), runtime=runtime)

            self.assertEqual(rc, 0)
            self.assertTrue(config_path.is_file())
            self.assertTrue(base_path.is_file())
            config_text = config_path.read_text(encoding="utf-8")
            self.assertIn(str(runtime.paths.sandbox_root), config_text)
            self.assertIn(str(runtime.paths.cache_root), config_text)
            self.assertIn(str(base_path), config_text)
            self.assertIn("[review_intelligence]", config_text)
            base_payload = json.loads(base_path.read_text(encoding="utf-8"))
            self.assertEqual(base_payload["embedding"]["provider"], "voyage")
            self.assertEqual(base_payload["embedding"]["model"], "voyage-code-3")
            output = stdout.getvalue()
            self.assertIn("Wrote CURe config", output)
            self.assertIn("Wrote ChunkHound base config", output)
            self.assertIn("Next: cure install", output)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_user_facing_contract_text_has_no_workspace_hardcoding(self) -> None:
        reviewflow_src = (ROOT / "reviewflow.py").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        selftest = (ROOT / "selftest.sh").read_text(encoding="utf-8")
        for text in (reviewflow_src, readme, selftest):
            self.assertNotIn("reviewflow.py jira-smoke", text)
            self.assertNotIn("reviewflow.py clean", text)
            self.assertNotIn("reviewflow.py list", text)

    def test_install_flow_runs_constructed_command(self) -> None:
        with mock.patch.object(rf, "run_cmd") as run_cmd, mock.patch.object(
            shutil, "which", return_value="/usr/bin/chunkhound"
        ):
            rc = rf.install_flow(argparse.Namespace(chunkhound_source="git-main"))
        self.assertEqual(rc, 0)
        self.assertEqual(
            run_cmd.call_args.args[0],
            rf.build_chunkhound_install_command(chunkhound_source="git-main"),
        )

    def test_install_flow_errors_when_chunkhound_still_missing_from_path(self) -> None:
        calls: list[list[str]] = []

        def fake_run_cmd(cmd, **kwargs):  # type: ignore[no-untyped-def]
            calls.append(list(cmd))
            if cmd[:3] == ["/usr/bin/uv", "tool", "dir"]:
                stdout = "/home/vscode/.local/share/uv/tools\n"
            elif cmd[:4] == ["/usr/bin/uv", "tool", "dir", "--bin"]:
                stdout = "/home/vscode/.local/bin\n"
            else:
                stdout = ""
            return mock.Mock(stdout=stdout, stderr="", exit_code=0)

        with mock.patch.object(rf, "run_cmd", side_effect=fake_run_cmd), mock.patch.object(
            shutil,
            "which",
            side_effect=lambda name: "/usr/bin/uv" if name == "uv" else None,
        ), mock.patch.object(
            rf,
            "_running_in_uv_tool_environment",
            return_value=True,
        ), mock.patch.object(
            rf,
            "_uv_tool_dir",
            side_effect=[
                Path("/home/vscode/.local/share/uv/tools"),
                Path("/home/vscode/.local/bin"),
            ],
        ), mock.patch.object(
            rf.importlib.util,
            "find_spec",
            return_value=None,
        ), mock.patch.object(
            rf.sys,
            "executable",
            "/home/vscode/.local/share/uv/tools/reviewflow/bin/python",
        ):
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.install_flow(argparse.Namespace(chunkhound_source="release"))
        self.assertIn("still not available on PATH", str(ctx.exception))
        self.assertIn("uv tool bin dir", str(ctx.exception))
        self.assertIn(["/usr/bin/uv", "tool", "install", "--force", "chunkhound"], calls)

    def test_doctor_runtime_checks_report_healthy_state(self) -> None:
        root = ROOT / ".tmp_test_doctor_ok"
        cfg = root / "reviewflow.toml"
        base_cfg = root / "chunkhound.json"
        codex_cfg = root / "codex.toml"
        jira_cfg = root / ".jira.yml"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            (root / "sandboxes").mkdir()
            (root / "cache").mkdir()
            base_cfg.write_text("{}", encoding="utf-8")
            codex_cfg.write_text("", encoding="utf-8")
            jira_cfg.write_text("endpoint: https://example.atlassian.net\n", encoding="utf-8")
            cfg.write_text(
                "\n".join(
                    [
                        "[paths]",
                        f'sandbox_root = "{root / "sandboxes"}"',
                        f'cache_root = "{root / "cache"}"',
                        "",
                        "[chunkhound]",
                        f'base_config_path = "{base_cfg}"',
                        "",
                        "[codex]",
                        f'base_config_path = "{codex_cfg}"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            runtime = rf.resolve_runtime(self._runtime_args(config_path=str(cfg)))
            with mock.patch.dict(os.environ, {"JIRA_CONFIG_FILE": str(jira_cfg)}, clear=False), mock.patch.object(
                shutil,
                "which",
                side_effect=lambda name: f"/usr/bin/{name}",
            ), mock.patch.object(cure_runtime, "run_cmd", return_value=mock.Mock(stdout="", stderr="", exit_code=0)):
                checks = rf._doctor_runtime_checks(runtime)
            by_name = {item.name: item for item in checks}
            self.assertEqual(by_name["reviewflow-config"].status, "ok")
            self.assertEqual(by_name["chunkhound-config"].status, "ok")
            self.assertEqual(by_name["jira-config"].status, "ok")
            self.assertEqual(by_name["codex-config"].status, "ok")
            self.assertEqual(by_name["gh-auth"].status, "ok")
            self.assertEqual(by_name["chunkhound"].status, "ok")
            self.assertIn("source=cli", by_name["reviewflow-config"].detail)
            self.assertIn("source=config", by_name["chunkhound-config"].detail)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_doctor_flow_reports_missing_state(self) -> None:
        runtime = rf.ReviewflowRuntime(
            config_path=ROOT / ".tmp_missing_reviewflow.toml",
            config_source="default",
            config_enabled=True,
            paths=rf.DEFAULT_PATHS,
            sandbox_root_source="default",
            cache_root_source="default",
            codex_base_config_path=ROOT / ".tmp_missing_codex.toml",
            codex_base_config_source="default",
        )
        stdout = StringIO()
        with mock.patch.object(shutil, "which", return_value=None), mock.patch.object(
            rf,
            "_default_jira_config_path",
            return_value=ROOT / ".tmp_missing_jira.yml",
        ), mock.patch("sys.stdout", stdout):
            rc = rf.doctor_flow(argparse.Namespace(), runtime=runtime)
        self.assertEqual(rc, 1)
        text = stdout.getvalue()
        self.assertIn("[fail] reviewflow-config", text)
        self.assertIn("[fail] chunkhound", text)
        self.assertIn("[warn] jira-config", text)
        self.assertIn("[warn] codex-config", text)

    def test_doctor_flow_json_reports_sources(self) -> None:
        root = ROOT / ".tmp_test_doctor_json"
        cfg = root / "reviewflow.toml"
        base_cfg = root / "chunkhound.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            (root / "sandboxes").mkdir()
            (root / "cache").mkdir()
            base_cfg.write_text("{}", encoding="utf-8")
            cfg.write_text(
                "\n".join(
                    [
                        "[paths]",
                        f'sandbox_root = "{root / "sandboxes"}"',
                        f'cache_root = "{root / "cache"}"',
                        "",
                        "[chunkhound]",
                        f'base_config_path = "{base_cfg}"',
                        "",
                        "[agent_runtime]",
                        'profile = "strict"',
                        "",
                        "[llm]",
                        'default_preset = "claude_default"',
                        "",
                        "[llm_presets.claude_default]",
                        'preset = "claude-cli"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            runtime = rf.resolve_runtime(self._runtime_args(config_path=str(cfg)))
            stdout = StringIO()
            with mock.patch.object(shutil, "which", return_value=None), mock.patch.object(
                rf,
                "_default_jira_config_path",
                return_value=root / ".tmp_missing_jira.yml",
            ), mock.patch("sys.stdout", stdout):
                rc = rf.doctor_flow(argparse.Namespace(json_output=True), runtime=runtime)
            self.assertEqual(rc, 1)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["reviewflow_config"]["source"], "cli")
            self.assertTrue(payload["reviewflow_config"]["exists"])
            self.assertEqual(payload["chunkhound_base_config"]["source"], "config")
            self.assertEqual(payload["sandbox_root"]["source"], "config")
            self.assertEqual(payload["agent_runtime"]["profile"], "strict")
            self.assertEqual(payload["agent_runtime"]["provider"], "claude")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_doctor_runtime_checks_warn_when_config_disabled(self) -> None:
        root = ROOT / ".tmp_test_doctor_no_config"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            runtime = rf.resolve_runtime(self._runtime_args(config_path=str(root / "reviewflow.toml"), no_config=True))
            checks = rf._doctor_runtime_checks(runtime)
            by_name = {item.name: item for item in checks}
            self.assertEqual(by_name["reviewflow-config"].status, "warn")
            self.assertEqual(by_name["chunkhound-config"].status, "warn")
            self.assertIn("disabled by --no-config", by_name["reviewflow-config"].detail)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_doctor_flow_public_pr_allows_missing_gh_auth_and_jira(self) -> None:
        root = ROOT / ".tmp_test_doctor_public_pr"
        cfg = root / "reviewflow.toml"
        base_cfg = root / "chunkhound.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            (root / "sandboxes").mkdir()
            (root / "cache").mkdir()
            base_cfg.write_text("{}", encoding="utf-8")
            cfg.write_text(
                "\n".join(
                    [
                        "[paths]",
                        f'sandbox_root = "{root / "sandboxes"}"',
                        f'cache_root = "{root / "cache"}"',
                        "",
                        "[chunkhound]",
                        f'base_config_path = "{base_cfg}"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            runtime = rf.resolve_runtime(self._runtime_args(config_path=str(cfg)))
            stdout = StringIO()
            response = mock.MagicMock()
            response.__enter__.return_value = response
            response.read.return_value = json.dumps({"title": "Public PR"}).encode("utf-8")

            def fake_which(name: str) -> str | None:
                return {
                    "chunkhound": "/usr/bin/chunkhound",
                    "codex": "/usr/bin/codex",
                    "git": "/usr/bin/git",
                }.get(name)

            with mock.patch.object(shutil, "which", side_effect=fake_which), mock.patch.object(
                rf,
                "_default_jira_config_path",
                return_value=root / ".tmp_missing_jira.yml",
            ), mock.patch.object(rf.urllib.request, "urlopen", return_value=response), mock.patch(
                "sys.stdout",
                stdout,
            ):
                rc = rf.doctor_flow(
                    argparse.Namespace(
                        json_output=True,
                        pr_url="https://github.com/acme/repo/pull/1",
                    ),
                    runtime=runtime,
                )

            self.assertEqual(rc, 0)
            payload = json.loads(stdout.getvalue())
            by_name = {item["name"]: item for item in payload["checks"]}
            self.assertEqual(by_name["gh"]["status"], "ok")
            self.assertEqual(by_name["gh-auth"]["status"], "ok")
            self.assertEqual(by_name["jira-config"]["status"], "warn")
            self.assertEqual(by_name["jira"]["status"], "warn")
            self.assertEqual(by_name["git"]["status"], "ok")
            self.assertEqual(by_name["github-pr-access"]["status"], "ok")
            self.assertEqual(payload["summary"]["fail"], 0)
            self.assertTrue(payload["target"]["public_pr_metadata_reachable"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_doctor_flow_private_host_still_requires_authenticated_gh(self) -> None:
        root = ROOT / ".tmp_test_doctor_private_host"
        cfg = root / "reviewflow.toml"
        base_cfg = root / "chunkhound.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True, exist_ok=True)
            (root / "sandboxes").mkdir()
            (root / "cache").mkdir()
            base_cfg.write_text("{}", encoding="utf-8")
            cfg.write_text(
                "\n".join(
                    [
                        "[paths]",
                        f'sandbox_root = "{root / "sandboxes"}"',
                        f'cache_root = "{root / "cache"}"',
                        "",
                        "[chunkhound]",
                        f'base_config_path = "{base_cfg}"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            runtime = rf.resolve_runtime(self._runtime_args(config_path=str(cfg)))
            stdout = StringIO()

            def fake_which(name: str) -> str | None:
                return {
                    "chunkhound": "/usr/bin/chunkhound",
                    "codex": "/usr/bin/codex",
                    "git": "/usr/bin/git",
                }.get(name)

            with mock.patch.object(shutil, "which", side_effect=fake_which), mock.patch.object(
                rf,
                "_default_jira_config_path",
                return_value=root / ".tmp_missing_jira.yml",
            ), mock.patch("sys.stdout", stdout):
                rc = rf.doctor_flow(
                    argparse.Namespace(
                        json_output=True,
                        pr_url="https://git.example.com/acme/repo/pull/1",
                    ),
                    runtime=runtime,
                )

            self.assertEqual(rc, 1)
            payload = json.loads(stdout.getvalue())
            by_name = {item["name"]: item for item in payload["checks"]}
            self.assertEqual(by_name["gh"]["status"], "fail")
            self.assertEqual(by_name["gh-auth"]["status"], "fail")
            self.assertEqual(by_name["github-pr-access"]["status"], "fail")
        finally:
            shutil.rmtree(root, ignore_errors=True)

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
            "head_sha": "0000000000000000000000000000000000000000",
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
            self.assertIn("phase 1/1: Checkout PR", bar)
            if w < 100:
                self.assertNotIn("v:normal", bar)
            else:
                self.assertIn("v:normal", bar)

    def test_dashboard_narrow_header_moves_verdicts_to_context(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "s",
            "created_at": "2026-03-04T00:00:00+00:00",
            "status": "done",
            "completed_at": "2026-03-04T00:05:00+00:00",
            "phase": "codex_review",
            "phases": {"codex_review": {"status": "done", "duration_seconds": 10.0}},
            "verdicts": {"business": "REQUEST CHANGES", "technical": "REQUEST CHANGES"},
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=[],
            codex_tail=[],
            no_stream=False,
            width=90,
            height=25,
        )
        self.assertNotIn("biz=REQUEST CHANGES", lines[0])
        self.assertNotIn("v:normal", lines[0])
        self.assertIn("phase 1/1: Generate review", lines[0])
        joined = "\n".join(lines)
        self.assertIn("Verdict: biz=REQUEST CHANGES tech=REQUEST CHANGES", joined)

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
            "head_sha": "0000000000000000000000000000000000000000",
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

    def test_dashboard_error_current_phase_uses_error_marker_and_failure_summary(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "s",
            "created_at": "",
            "status": "error",
            "phase": "review_intelligence_preflight",
            "phases": {"review_intelligence_preflight": {"status": "error", "duration_seconds": 0.1}},
            "error": {"message": "Jira context is expected but JIRA_CONFIG_FILE is unavailable."},
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=["jira me failed"],
            codex_tail=[],
            no_stream=False,
            width=120,
            height=30,
        )
        joined = "\n".join(lines)
        self.assertIn("✖ Context preflight", joined)
        self.assertIn("Failure:", joined)
        self.assertIn("JIRA_CONF", joined)
        self.assertIn("Preflight:", joined)
        self.assertIn("Failure Detail", joined)

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
            "head_sha": "0000000000000000000000000000000000000000",
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
                    "- host-session [review] biz=APPROVE tech=REQUEST CHANGES 2026-03-04T01:00:00+00:00 head bbbbbbbbbbbb /tmp/host/review.md",
                    "- other-session [followup] biz=REQUEST CHANGES tech=REJECT 2026-03-05T01:00:00+00:00 head bbbbbbbbbbbb /tmp/other/followup.md",
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
            width=160,
            height=35,
            color=False,
        )
        joined = "\n".join(lines)
        self.assertIn("Zip:", joined)
        self.assertIn("Inputs:", joined)
        self.assertIn("host-session [review] biz=APPROVE tech=REQUEST CHANGES", joined)
        self.assertIn("other-session [followup] biz=REQUEST CHANGES tech=REJECT", joined)

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
            "head_sha": "0000000000000000000000000000000000000000",
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        ch_tail = [f"ch-{i}" for i in range(1, 201)]
        cx_tail = [f"cx-{i}" for i in range(1, 401)]
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.debug, show_help=False),
            chunkhound_tail=ch_tail,
            codex_tail=cx_tail,
            no_stream=False,
            width=160,
            height=80,
            color=False,
        )
        joined = "\n".join(lines)
        m1 = re.search(r"Support \(last (\d+)\):", joined)
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
        self.assertIn("─ Activity", joined)
        self.assertIn("cx-400", joined)

    def test_dashboard_empty_logs_render_stream_specific_placeholder(self) -> None:
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
            chunkhound_tail=[],
            codex_tail=[],
            no_stream=False,
            width=120,
            height=20,
        )
        joined = "\n".join(lines)
        self.assertIn("─ Activity", joined)
        self.assertIn("(agent is working)", joined)

    def test_dashboard_context_summarizes_support_signals(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "s",
            "created_at": "",
            "status": "running",
            "phase": "codex_review",
            "phases": {"codex_review": {"status": "running"}},
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=[
                "Processed: 4 files",
                "Skipped: 1 files",
                "Errors: 0 files",
                "Total chunks: 84",
                "Embeddings: 84",
                "Time: 17.23s",
                "greg@academypl.us",
            ],
            codex_tail=["mcp: chunkhound ready"],
            no_stream=False,
            width=140,
            height=30,
            color=False,
        )
        joined = "\n".join(lines)
        self.assertIn("Index", joined)
        self.assertIn("Run: 4 proc · 1 skip · 0 err", joined)
        self.assertIn("Output: 84 chunks · 84 emb · 17.23s", joined)
        self.assertIn("Preflight: Jira OK as greg@academypl.us", joined)
        self.assertIn("─ Activity", joined)
        self.assertIn("mcp: chunkhound ready", joined)

    def test_dashboard_context_prefers_structured_chunkhound_summary(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "s",
            "created_at": "",
            "status": "running",
            "phase": "codex_review",
            "phases": {"codex_review": {"status": "running"}},
            "chunkhound": {
                "last_index": {
                    "scope": "followup",
                    "initial_files": 120,
                    "initial_chunks": 4091,
                    "initial_embeddings": 4091,
                    "processed_files": 4,
                    "skipped_files": 1,
                    "error_files": 0,
                    "total_chunks": 84,
                    "embeddings": 84,
                    "duration_text": "17.23s",
                }
            },
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=[],
            codex_tail=["mcp: chunkhound ready"],
            no_stream=False,
            width=140,
            height=30,
            color=False,
        )
        joined = "\n".join(lines)
        self.assertIn("Index: follow-up", joined)
        self.assertIn("Run: 4 proc · 1 skip · 0 err", joined)
        self.assertIn("Output: 84 chunks · 84 emb · 17.23s", joined)
        self.assertIn("Before: 120 files · 4091 chunks · 4091 emb", joined)

    def test_dashboard_running_prefers_structured_live_progress_over_raw_activity(self) -> None:
        meta = {
            "host": "github.com",
            "owner": "acme",
            "repo": "repo",
            "number": 1,
            "title": "Test PR",
            "session_id": "s",
            "created_at": "",
            "status": "running",
            "phase": "codex_review",
            "phases": {"codex_review": {"status": "running"}},
            "live_progress": {
                "current": {
                    "type": "agent_message",
                    "text": "Checking changed files",
                    "ts": "2026-03-17T12:00:02+00:00",
                },
                "timeline": [
                    {
                        "type": "thread_started",
                        "text": "Codex session started.",
                        "ts": "2026-03-17T12:00:00+00:00",
                    },
                    {
                        "type": "turn_started",
                        "text": "Review turn started.",
                        "ts": "2026-03-17T12:00:01+00:00",
                    },
                    {
                        "type": "agent_message",
                        "text": "Checking changed files",
                        "ts": "2026-03-17T12:00:02+00:00",
                    },
                ],
            },
            "paths": {"session_dir": "/tmp/review", "review_md": "/tmp/review/review.md"},
        }
        lines = rui.build_dashboard_lines(
            meta=meta,
            snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
            chunkhound_tail=[],
            codex_tail=["raw-codex-tail"],
            no_stream=False,
            width=140,
            height=30,
            color=False,
        )
        joined = "\n".join(lines)
        self.assertIn("─ Live Progress", joined)
        self.assertIn("Phase: Generate review", joined)
        self.assertIn("Now: Checking changed files", joined)
        self.assertIn("[12:00:00] Codex session started.", joined)
        self.assertNotIn("─ Activity", joined)

    def test_dashboard_done_uses_review_snapshot_in_primary_pane(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_md = Path(tmp) / "review.md"
            review_md.write_text(
                "\n".join(
                    [
                        "### Steps taken",
                        "- inspected diff",
                        "",
                        "**Summary**: Ticket ABAU-1026 aligns with the empty-state wording update.",
                        "",
                        "## Business / Product Assessment",
                        "**Verdict**: REQUEST CHANGES",
                        "### In Scope Issues",
                        "- CTA copy is inconsistent with the approved wording.",
                        "",
                        "## Technical Assessment",
                        "**Verdict**: APPROVE",
                        "### In Scope Issues",
                        "- None.",
                        "####",
                    ]
                ),
                encoding="utf-8",
            )
            meta = {
                "host": "github.com",
                "owner": "acme",
                "repo": "repo",
                "number": 1,
                "title": "Test PR",
                "session_id": "s",
                "created_at": "",
                "status": "done",
                "completed_at": "2026-03-04T00:05:00+00:00",
                "phase": "codex_review",
                "phases": {"codex_review": {"status": "done", "duration_seconds": 10.0}},
                "paths": {"session_dir": tmp, "review_md": str(review_md)},
            }
            lines = rui.build_dashboard_lines(
                meta=meta,
                snapshot=rui.UiSnapshot(verbosity=rui.Verbosity.normal, show_help=False),
                chunkhound_tail=[],
                codex_tail=["### In Scope Issues", "- stale tail"],
                no_stream=False,
                width=140,
                height=30,
                color=False,
            )
        joined = "\n".join(lines)
        self.assertIn("─ Review Snapshot", joined)
        self.assertIn("Summary: Ticket ABAU-1026 aligns with the empty-state wording update.", joined)
        self.assertIn("Business: REQUEST CHANGES", joined)
        self.assertIn("Business issue: CTA copy is inconsistent with the approved wording.", joined)


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
                env={"REVIEWFLOW_WORK_DIR": str(repo_dir.parent / "work")},
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
                "base_ref_for_review": "reviewflow_base__release_1_2",
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
                "base_ref_for_review": "reviewflow_base__release_1_2",
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
                "base_ref_for_review": "reviewflow_base__release_1_2",
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
        mutate_config: Any | None = None,
    ) -> tuple[Path, Path]:
        db_path = repo_root / db_rel
        db_path.mkdir(parents=True, exist_ok=True)
        (db_path / "chunks.db").write_text("db", encoding="utf-8")
        config = json.loads(json.dumps(resolved_runtime_config))
        if mutate_config is not None:
            mutate_config(config)
        config["database"] = {"provider": "duckdb", "path": db_rel}
        config_path = repo_root / ".chunkhound.json"
        config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return config_path, db_path

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
            self.assertTrue((session_dir / "work" / "logs" / "reviewflow.log").is_file())
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
                            rf.ReviewIntelligenceConfig(
                                tool_prompt_fragment="Use GitHub MCP first.",
                                policy_mode="cure_first_unrestricted",
                            ),
                            {"review_intelligence": {"tool_prompt_fragment": "Use GitHub MCP first."}},
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

            self.assertIn("Use GitHub MCP first.", captured["prompt"])
            self.assertIn("Code under review first policy", captured["prompt"])
            self.assertIn("Context: ", captured["prompt"])
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

    def _valid_synth_markdown(self) -> str:
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
                        rf.ReviewIntelligenceConfig(
                            tool_prompt_fragment="Use GitHub MCP first.",
                            policy_mode="cure_first_unrestricted",
                        ),
                        {"review_intelligence": {"tool_prompt_fragment": "Use GitHub MCP first."}},
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
            review_md.write_text(self._valid_synth_markdown(), encoding="utf-8")
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
                "base_ref_for_review": "reviewflow_base__main",
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
                    output_path.write_text(self._valid_synth_markdown(), encoding="utf-8")
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
                            rf.ReviewIntelligenceConfig(
                                tool_prompt_fragment="Use GitHub MCP first.",
                                policy_mode="cure_first_unrestricted",
                            ),
                            {"review_intelligence": {"tool_prompt_fragment": "Use GitHub MCP first."}},
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

    def test_console_main_warns_and_dispatches_for_deprecated_alias(self) -> None:
        stderr = StringIO()
        with mock.patch.object(rf, "main", return_value=7) as main_mock, mock.patch.object(
            sys,
            "argv",
            ["reviewflow", "commands", "--json"],
        ), mock.patch.object(sys, "stderr", stderr):
            rc = rf.console_main()

        self.assertEqual(rc, 7)
        self.assertIn("Use `cure` instead.", stderr.getvalue())
        main_mock.assert_called_once_with(["commands", "--json"], prog="cure")


if __name__ == "__main__":
    unittest.main()
