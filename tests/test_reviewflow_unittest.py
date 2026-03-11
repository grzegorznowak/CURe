import argparse
import json
import os
import re
import shutil
import sys
import unittest
from io import StringIO
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import reviewflow as rf  # noqa: E402
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
                        "- Use any additional tools or sources that materially improve understanding of the codebase-under-review (CURe).",
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
        self.assertIn("CURe-first policy", guidance)
        self.assertIn("materially improves understanding of the codebase-under-review", guidance)
        self.assertNotIn("rf-fetch-url", guidance)


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
                    "embedding": {"provider": "voyage", "api_key": "secret", "model": "voyage-code-3"},
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
                            "api_key": "test-key",
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
                env = rf.chunkhound_env(rf.DEFAULT_PATHS, source_config_path=base_cfg)
            self.assertEqual(env["CHUNKHOUND_EMBEDDING__API_KEY"], "test-key")
        finally:
            base_cfg.unlink(missing_ok=True)


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
                        'api_key = "sk-openrouter"',
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
                        'env = { OPENAI_API_KEY = "sk-codex" }',
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
            self.assertEqual(llm_cfg["presets"]["my_codex"]["env"]["OPENAI_API_KEY"], "sk-codex")
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
                        'api_key = "sk-openrouter"',
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

    def test_build_http_response_request_openrouter_uses_responses_api_and_headers(self) -> None:
        request = rf.build_http_response_request(
            {
                "preset": "openrouter_grok",
                "transport": "http",
                "provider": "openrouter",
                "endpoint": "responses",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": "sk-openrouter",
                "model": "x-ai/grok-4.1-fast",
                "reasoning_effort": "high",
                "text_verbosity": None,
                "max_output_tokens": 9000,
                "store": None,
                "include": [],
                "metadata": {},
                "headers": {
                    "HTTP-Referer": "https://academypl.us",
                    "X-OpenRouter-Title": "reviewflow",
                },
                "request": {"provider": {"sort": "latency"}},
            },
            prompt="Review this PR.",
        )
        self.assertEqual(request["url"], "https://openrouter.ai/api/v1/responses")
        self.assertEqual(request["headers"]["Authorization"], "Bearer sk-openrouter")
        self.assertEqual(request["headers"]["HTTP-Referer"], "https://academypl.us")
        self.assertEqual(request["headers"]["X-OpenRouter-Title"], "reviewflow")
        self.assertEqual(request["json"]["model"], "x-ai/grok-4.1-fast")
        self.assertEqual(request["json"]["input"], "Review this PR.")
        self.assertEqual(request["json"]["reasoning"]["effort"], "high")
        self.assertEqual(request["json"]["max_output_tokens"], 9000)
        self.assertEqual(request["json"]["provider"]["sort"], "latency")


class StorageMigrationTests(unittest.TestCase):
    def test_default_paths_use_relocated_main_config_and_sandbox_root(self) -> None:
        self.assertEqual(rf.DEFAULT_PATHS.main_chunkhound_config, Path("/workspaces/academy+/.chunkhound.json"))
        self.assertEqual(rf.DEFAULT_PATHS.sandbox_root, Path("/workspaces/.reviewflow-sandboxes"))

    def test_rewrite_session_meta_after_move_rewrites_nested_absolute_paths(self) -> None:
        old_session = Path("/workspaces/academy+/.tmp/review-sandboxes/demo")
        new_session = Path("/workspaces/.reviewflow-sandboxes/demo")
        meta = {
            "paths": {
                "session_dir": str(old_session),
                "repo_dir": str(old_session / "repo"),
            },
            "followups": [{"output_path": str(old_session / "followups" / "f1.md")}],
            "zips": [{"output_path": str(old_session / "zips" / "z1.md")}],
            "codex": {
                "resume": {
                    "cwd": str(old_session / "repo"),
                    "command": f"cd {old_session / 'repo'} && codex resume",
                }
            },
        }
        rewritten = rf.rewrite_session_meta_after_move(
            meta=meta,
            old_session_dir=old_session,
            new_session_dir=new_session,
        )
        payload = json.dumps(rewritten)
        self.assertIn(str(new_session), payload)
        self.assertNotIn(str(old_session), payload)

    def test_migrate_storage_flow_dry_run_and_apply(self) -> None:
        root = ROOT / ".tmp_test_storage_migration"
        legacy_root = root / "legacy-sandboxes"
        new_root = root / "new-sandboxes"
        legacy_cfg = root / ".chunkhound.json"
        new_cfg = root / "academy+" / ".chunkhound.json"
        review_cfg = root / ".chunkhound.review.json"
        try:
            shutil.rmtree(root, ignore_errors=True)
            (legacy_root / "sess-1" / "repo").mkdir(parents=True, exist_ok=True)
            (legacy_root / "sess-1" / "zips").mkdir(exist_ok=True)
            (legacy_root / "sess-1" / "meta.json").write_text(
                json.dumps(
                    {
                        "session_id": "sess-1",
                        "paths": {
                            "session_dir": str(legacy_root / "sess-1"),
                            "repo_dir": str(legacy_root / "sess-1" / "repo"),
                        },
                        "codex": {
                            "resume": {
                                "cwd": str(legacy_root / "sess-1" / "repo"),
                                "command": f"cd {legacy_root / 'sess-1' / 'repo'} && codex resume",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            (legacy_root / "sess-1" / "zips" / "zip-1.meta.json").write_text(
                json.dumps({"output_path": str(legacy_root / "sess-1" / "zips" / "zip-1.md")}),
                encoding="utf-8",
            )
            legacy_cfg.write_text(json.dumps({"embedding": {"api_key": "k"}}), encoding="utf-8")
            review_cfg.write_text("{}", encoding="utf-8")
            paths = rf.ReviewflowPaths(
                sandbox_root=new_root,
                cache_root=ROOT / ".tmp_test_storage_migration_cache",
                review_chunkhound_config=review_cfg,
                main_chunkhound_config=new_cfg,
            )

            with mock.patch.object(rf, "LEGACY_SANDBOX_ROOT", legacy_root), mock.patch.object(
                rf, "LEGACY_MAIN_CHUNKHOUND_CONFIG", legacy_cfg
            ), mock.patch.object(rf, "_eprint") as eprint:
                rc = rf.migrate_storage_flow(argparse.Namespace(apply=False), paths=paths)
            self.assertEqual(rc, 0)
            self.assertTrue((legacy_root / "sess-1").exists())
            self.assertFalse(new_cfg.exists())
            dry_output = "\n".join(" ".join(str(a) for a in call.args) for call in eprint.call_args_list)
            self.assertIn("Migration dry run:", dry_output)
            self.assertIn(str(new_root / "sess-1"), dry_output)

            with mock.patch.object(rf, "LEGACY_SANDBOX_ROOT", legacy_root), mock.patch.object(
                rf, "LEGACY_MAIN_CHUNKHOUND_CONFIG", legacy_cfg
            ), mock.patch.object(rf, "_eprint"):
                rc = rf.migrate_storage_flow(argparse.Namespace(apply=True), paths=paths)
            self.assertEqual(rc, 0)
            self.assertFalse(legacy_cfg.exists())
            self.assertTrue(new_cfg.exists())
            cfg = json.loads(new_cfg.read_text(encoding="utf-8"))
            self.assertEqual(cfg["database"]["provider"], "duckdb")
            self.assertEqual(cfg["database"]["path"], str(rf.MIGRATED_MAIN_CHUNKHOUND_DB_PATH))
            migrated_meta = json.loads((new_root / "sess-1" / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(migrated_meta["paths"]["session_dir"], str(new_root / "sess-1"))
            self.assertIn(str(new_root / "sess-1"), migrated_meta["codex"]["resume"]["command"])
            migrated_zip_meta = json.loads(
                (new_root / "sess-1" / "zips" / "zip-1.meta.json").read_text(encoding="utf-8")
            )
            self.assertEqual(migrated_zip_meta["output_path"], str(new_root / "sess-1" / "zips" / "zip-1.md"))
        finally:
            shutil.rmtree(root, ignore_errors=True)


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
        master = (
            Path("/workspaces/academy+/.tmp/agent_coordination/epics/reviewflow-chunkhound-pr-sandboxes/MASTER.md")
        ).read_text(encoding="utf-8")
        for text in (readme, master):
            self.assertIn("uses product/ticket scope", text)
            self.assertIn("uses implementation scope", text)


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
            self.assertIn("llm=legacy_codex/gpt-5.3-codex/high", stderr.getvalue())
            self.assertIn(str(s1 / "review.md"), stderr.getvalue())
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
                        "owner": "Academy-Plus",
                        "repo": "ssa-lms",
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
                mock.patch.object(rf, "chunkhound_env", return_value={"CHUNKHOUND_EMBEDDING__API_KEY": "test-key"}),
                mock.patch.object(rf, "real_user_home_dir", return_value=fake_home),
                mock.patch.object(rf, "run_interactive_resume_command", return_value=0) as runner,
            ):
                rc = rf.interactive_flow(
                    argparse.Namespace(target="https://github.com/Academy-Plus/ssa-lms/pull/78"),
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
                    "```markdown\n" + _sectioned_review_markdown(
                        business="APPROVE",
                        technical="REQUEST CHANGES",
                    ) + "```\n",
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

        args4 = p.parse_args(["clean"])
        self.assertIsNone(args4.session_id)

        args5 = p.parse_args(["clean", "session-123"])
        self.assertEqual(args5.session_id, "session-123")

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
                "HTTP-Referer=https://academypl.us",
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
        self.assertEqual(args.llm_header, ["HTTP-Referer=https://academypl.us"])
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


if __name__ == "__main__":
    unittest.main()
