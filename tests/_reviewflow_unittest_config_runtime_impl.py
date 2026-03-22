# ruff: noqa: F403, F405
from _reviewflow_unittest_shared import *  # noqa: F401, F403


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
            base_ref_for_review="cure_base__develop",
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
        self.assertIn("BASE=cure_base__develop", rendered)
        self.assertIn("DESC=hello", rendered)

    def test_render_prompt_supports_extra_vars_without_touching_agent_desc(self) -> None:
        template = "X=$X\nDESC=$AGENT_DESC\n"
        rendered = rf.render_prompt(
            template,
            base_ref_for_review="cure_base__develop",
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
            base_ref_for_review="cure_base__develop",
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
            base_ref_for_review="cure_base__develop",
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
                        'notes = ["Start with staged PR context first."]',
                        "",
                        "[[review_intelligence.sources]]",
                        'name = "github"',
                        'mode = "auto"',
                        'notes = ["Prefer staged PR context first, then use gh / gh api when needed."]',
                        "",
                        "[[review_intelligence.sources]]",
                        'name = "jira"',
                        'mode = "when-referenced"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            review_intelligence, meta = rf.load_review_intelligence_config(config_path=cfg)
            self.assertTrue(meta.get("loaded"))
            self.assertEqual(review_intelligence.notes, ("Start with staged PR context first.",))
            self.assertEqual(len(review_intelligence.sources), 2)
            self.assertEqual(review_intelligence.sources[0].name, "github")
            self.assertEqual(review_intelligence.sources[0].mode, "auto")
            self.assertEqual(review_intelligence.sources[1].name, "jira")
            self.assertEqual(review_intelligence.sources[1].mode, "when-referenced")
            persisted = meta["review_intelligence"]
            self.assertEqual(persisted["notes"], ["Start with staged PR context first."])
            self.assertEqual(
                persisted["sources"],
                [
                    {
                        "name": "github",
                        "mode": "auto",
                        "notes": ["Prefer staged PR context first, then use gh / gh api when needed."],
                    },
                    {
                        "name": "jira",
                        "mode": "when-referenced",
                        "notes": [],
                    },
                ],
            )
        finally:
            cfg.unlink(missing_ok=True)

    def test_load_review_intelligence_config_rejects_legacy_free_text_fields(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_review_intelligence_legacy.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[review_intelligence]",
                        'tool_prompt_fragment = "Use gh."',
                        'policy_mode = "cure_first_unrestricted"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.load_review_intelligence_config(config_path=cfg)
            self.assertIn("Legacy review-intelligence config keys are no longer supported", str(ctx.exception))
            self.assertIn("tool_prompt_fragment", str(ctx.exception))
            self.assertIn("policy_mode", str(ctx.exception))
        finally:
            cfg.unlink(missing_ok=True)

    def test_load_review_intelligence_config_rejects_invalid_source_mode(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_review_intelligence_invalid_mode.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[review_intelligence]",
                        "",
                        "[[review_intelligence.sources]]",
                        'name = "github"',
                        'mode = "sometimes"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.load_review_intelligence_config(config_path=cfg)
            self.assertIn("Invalid review-intelligence source mode", str(ctx.exception))
        finally:
            cfg.unlink(missing_ok=True)

    def test_load_review_intelligence_config_rejects_deprecated_crawl_section(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_review_intelligence_crawl.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[review_intelligence]",
                        "",
                        "[[review_intelligence.sources]]",
                        'name = "github"',
                        'mode = "auto"',
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

    def test_load_review_intelligence_config_requires_active_source_for_builtin_prompts(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_review_intelligence_missing.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[review_intelligence]",
                        "",
                        "[[review_intelligence.sources]]",
                        'name = "github"',
                        'mode = "off"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.load_review_intelligence_config(
                    config_path=cfg, require_active_sources=True
                )
            self.assertIn("[[review_intelligence.sources]]", str(ctx.exception))
            self.assertIn('mode = "auto"', str(ctx.exception))
        finally:
            cfg.unlink(missing_ok=True)

    def test_load_review_intelligence_config_rejects_unknown_required_source(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_review_intelligence_unknown_required.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[review_intelligence]",
                        "",
                        "[[review_intelligence.sources]]",
                        'name = "confluence"',
                        'mode = "required"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.load_review_intelligence_config(config_path=cfg)
            self.assertIn("Unknown required review-intelligence source", str(ctx.exception))
        finally:
            cfg.unlink(missing_ok=True)

    def test_build_review_intelligence_guidance_uses_structured_source_registry(self) -> None:
        cfg = _review_intelligence_cfg(
            notes=("Start with staged PR context first.",),
            jira_mode="required",
        )
        guidance = rf.build_review_intelligence_guidance(cfg)
        self.assertIn("Start with the staged PR context", guidance)
        self.assertIn("Use local `git` as the authoritative source for code changes.", guidance)
        self.assertIn("`github` (`auto`, `unknown`)", guidance)
        self.assertIn("`jira` (`required`, `unknown`)", guidance)
        self.assertIn("Additional notes:", guidance)
        self.assertIn("materially improve understanding of the code under review", guidance)
        self.assertNotIn("GitHub MCP", guidance)

    def test_review_intelligence_prompt_vars_include_guidance(self) -> None:
        cfg = _review_intelligence_cfg()

        prompt_vars = rf.review_intelligence_prompt_vars(cfg)

        self.assertIn("REVIEW_INTELLIGENCE_GUIDANCE", prompt_vars)
        self.assertIn("Configured sources:", prompt_vars["REVIEW_INTELLIGENCE_GUIDANCE"])
        self.assertIn("`github` (`auto`, `unknown`)", prompt_vars["REVIEW_INTELLIGENCE_GUIDANCE"])
        self.assertIn("Use local `git` as the authoritative source", prompt_vars["REVIEW_INTELLIGENCE_GUIDANCE"])

    def test_default_review_intelligence_example_renders_compact_guidance(self) -> None:
        cfg_path = ROOT / ".tmp_test_review_intelligence_default_example.toml"
        try:
            cfg_path.write_text(rf.REVIEW_INTELLIGENCE_CONFIG_EXAMPLE, encoding="utf-8")
            cfg, _ = rf.load_review_intelligence_config(
                config_path=cfg_path,
                require_active_sources=True,
            )
            guidance = rf.build_review_intelligence_guidance(cfg)
            self.assertEqual(cfg.notes, ())
            self.assertEqual(
                [(source.name, source.mode, source.notes) for source in cfg.sources],
                [
                    ("github", "auto", ()),
                    ("jira", "when-referenced", ()),
                ],
            )
            self.assertNotIn("Additional notes:", guidance)
            self.assertEqual(guidance.count("Start with the staged PR context when it is already available."), 1)
            self.assertEqual(guidance.count("Prefer staged PR context first"), 1)
            self.assertIn("`github` (`auto`, `unknown`)", guidance)
            self.assertIn("`jira` (`when-referenced`, `unknown`)", guidance)
        finally:
            cfg_path.unlink(missing_ok=True)

    def test_resolve_review_intelligence_capabilities_uses_runtime_facts(self) -> None:
        cfg = _review_intelligence_cfg(
            jira_mode="required",
            extra_sources=(("confluence", "when-referenced"),),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pr_context = root / "pr-context.md"
            pr_context.write_text("context", encoding="utf-8")
            gh_cfg = root / "gh"
            gh_cfg.mkdir()
            jira_cfg = root / "jira.yml"
            jira_cfg.write_text("jira", encoding="utf-8")
            helper = root / "rf-jira"
            helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            helper.chmod(0o755)
            pr = rf.PullRequestRef(host="github.com", owner="acme", repo="repo", number=1)
            with mock.patch.object(
                shutil,
                "which",
                side_effect=lambda name: f"/usr/bin/{name}" if name in {"gh", "jira"} else None,
            ):
                summary = rf.resolve_review_intelligence_capabilities(
                    cfg,
                    env={
                        "GH_CONFIG_DIR": str(gh_cfg),
                        "JIRA_CONFIG_FILE": str(jira_cfg),
                    },
                    runtime_policy={"staged_paths": {"rf_jira": str(helper)}},
                    pr=pr,
                    staged_pr_context_path=pr_context,
                )

        sources = {source["name"]: source for source in summary["sources"]}
        self.assertEqual(sources["github"]["status"], "available")
        self.assertEqual(sources["jira"]["status"], "available")
        self.assertTrue(sources["jira"]["preflight_required"])
        self.assertEqual(sources["confluence"]["status"], "unknown")
        self.assertEqual(summary["status_counts"]["available"], 2)
        self.assertEqual(summary["status_counts"]["unknown"], 1)

    def test_build_review_intelligence_guidance_surfaces_capability_states(self) -> None:
        cfg = _review_intelligence_cfg(jira_mode="required")
        capability_summary = {
            "required_sources": ["jira"],
            "status_counts": {"available": 1, "unavailable": 1, "unknown": 0},
            "sources": [
                {
                    "name": "github",
                    "mode": "auto",
                    "status": "available",
                },
                {
                    "name": "jira",
                    "mode": "required",
                    "status": "unavailable",
                },
            ],
        }

        guidance = rf.build_review_intelligence_guidance(
            cfg,
            capability_summary=capability_summary,
        )

        self.assertIn("do not broad-probe optional sources up front", guidance)
        self.assertIn("`github` (`auto`, `available`)", guidance)
        self.assertIn("`jira` (`required`, `unavailable`)", guidance)


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
            # model_reasoning_effort should come from cure.toml if CLI is unset.
            self.assertIn('model_reasoning_effort="low"', flags)
            # plan_mode_reasoning_effort should come from CLI.
            self.assertIn('plan_mode_reasoning_effort="medium"', flags)
            self.assertEqual(meta["resolved"]["model_source"], "cli")
            self.assertEqual(meta["resolved"]["model_reasoning_effort_source"], "cure.toml")
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

    def test_load_reviewflow_multipass_defaults_normalizes_step_workers(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_multipass_step_workers.toml"
        try:
            cfg.write_text("[multipass]\nstep_workers = 99\n", encoding="utf-8")
            mp, _ = rf.load_reviewflow_multipass_defaults(config_path=cfg)
            self.assertEqual(mp["step_workers"], rf.MULTIPASS_STEP_WORKERS_HARD_CAP)
        finally:
            cfg.unlink(missing_ok=True)

    def test_load_reviewflow_multipass_defaults_defaults_step_workers_to_four(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_multipass_default_step_workers.toml"
        try:
            cfg.write_text("[multipass]\nmax_steps = 5\n", encoding="utf-8")
            mp, meta = rf.load_reviewflow_multipass_defaults(config_path=cfg)
            self.assertEqual(mp["step_workers"], 4)
            self.assertEqual(meta["multipass"]["step_workers"], 4)
        finally:
            cfg.unlink(missing_ok=True)

    def test_load_reviewflow_multipass_defaults_defaults_step_effort_to_medium(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_multipass_default_step_effort.toml"
        try:
            cfg.write_text("[multipass]\nmax_steps = 5\n", encoding="utf-8")
            mp, meta = rf.load_reviewflow_multipass_defaults(config_path=cfg)
            self.assertEqual(mp["step_reasoning_effort"], "medium")
            self.assertEqual(meta["multipass"]["step_reasoning_effort"], "medium")
            self.assertIsNone(mp["plan_reasoning_effort"])
            self.assertIsNone(mp["synth_reasoning_effort"])
        finally:
            cfg.unlink(missing_ok=True)

    def test_load_reviewflow_multipass_defaults_parses_stage_reasoning_efforts(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_multipass_stage_efforts.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[multipass]",
                        'plan_reasoning_effort = "high"',
                        'step_reasoning_effort = "low"',
                        'synth_reasoning_effort = "xhigh"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            mp, meta = rf.load_reviewflow_multipass_defaults(config_path=cfg)
            self.assertEqual(mp["plan_reasoning_effort"], "high")
            self.assertEqual(mp["step_reasoning_effort"], "low")
            self.assertEqual(mp["synth_reasoning_effort"], "xhigh")
            self.assertEqual(meta["multipass"]["plan_reasoning_effort"], "high")
            self.assertEqual(meta["multipass"]["step_reasoning_effort"], "low")
            self.assertEqual(meta["multipass"]["synth_reasoning_effort"], "xhigh")
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

    def test_load_reviewflow_multipass_defaults_rejects_invalid_stage_reasoning_effort(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_multipass_invalid_stage_effort.toml"
        try:
            cfg.write_text('[multipass]\nstep_reasoning_effort = "broken"\n', encoding="utf-8")
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.load_reviewflow_multipass_defaults(config_path=cfg)
            self.assertIn("[multipass].step_reasoning_effort", str(ctx.exception))
        finally:
            cfg.unlink(missing_ok=True)


class LlmPresetConfigTests(unittest.TestCase):
    def test_resolve_multipass_stage_llm_config_defaults_step_to_medium_while_synth_stays_xhigh(
        self,
    ) -> None:
        resolved = {
            "provider": "codex",
            "model": "gpt-5.4",
            "reasoning_effort": "xhigh",
            "plan_reasoning_effort": None,
        }
        resolution_meta = {
            "resolved": {
                "model_source": "preset",
                "reasoning_effort_source": "preset",
                "plan_reasoning_effort_source": "unset",
            }
        }
        multipass_cfg = {
            "step_reasoning_effort": "medium",
            "plan_reasoning_effort": None,
            "synth_reasoning_effort": None,
        }

        plan_resolved, _, plan_meta = rf.resolve_multipass_stage_llm_config(
            stage="plan",
            resolved=resolved,
            resolution_meta=resolution_meta,
            multipass_cfg=multipass_cfg,
        )
        step_resolved, step_resolution_meta, step_meta = rf.resolve_multipass_stage_llm_config(
            stage="step",
            resolved=resolved,
            resolution_meta=resolution_meta,
            multipass_cfg=multipass_cfg,
        )
        synth_resolved, synth_resolution_meta, synth_meta = rf.resolve_multipass_stage_llm_config(
            stage="synth",
            resolved=resolved,
            resolution_meta=resolution_meta,
            multipass_cfg=multipass_cfg,
        )

        self.assertEqual(plan_meta["effective_reasoning_effort"], "xhigh")
        self.assertEqual(step_resolved["reasoning_effort"], "medium")
        self.assertEqual(step_meta["effective_reasoning_effort"], "medium")
        self.assertEqual(step_resolution_meta["resolved"]["reasoning_effort_source"], "multipass_config")
        self.assertEqual(synth_resolved["reasoning_effort"], "xhigh")
        self.assertEqual(synth_meta["effective_reasoning_effort"], "xhigh")
        self.assertEqual(synth_resolution_meta["resolved"]["reasoning_effort_source"], "reasoning_effort:preset")

    def test_resolve_multipass_stage_llm_config_preserves_codex_plan_and_generic_step_synth_inheritance(self) -> None:
        resolved = {
            "provider": "codex",
            "model": "gpt-5.4",
            "reasoning_effort": "medium",
            "plan_reasoning_effort": "high",
        }
        resolution_meta = {
            "resolved": {
                "model_source": "cli",
                "reasoning_effort_source": "cli",
                "plan_reasoning_effort_source": "preset",
            }
        }
        multipass_cfg = {}

        plan_resolved, plan_resolution_meta, plan_meta = rf.resolve_multipass_stage_llm_config(
            stage="plan",
            resolved=resolved,
            resolution_meta=resolution_meta,
            multipass_cfg=multipass_cfg,
        )
        step_resolved, _, step_meta = rf.resolve_multipass_stage_llm_config(
            stage="step",
            resolved=resolved,
            resolution_meta=resolution_meta,
            multipass_cfg=multipass_cfg,
        )
        synth_resolved, _, synth_meta = rf.resolve_multipass_stage_llm_config(
            stage="synth",
            resolved=resolved,
            resolution_meta=resolution_meta,
            multipass_cfg=multipass_cfg,
        )

        self.assertEqual(plan_resolved["reasoning_effort"], "medium")
        self.assertEqual(plan_resolved["plan_reasoning_effort"], "high")
        self.assertEqual(plan_meta["applied_reasoning_effort_field"], "plan_reasoning_effort")
        self.assertEqual(plan_meta["effective_reasoning_effort"], "high")
        self.assertEqual(plan_meta["base_reasoning_effort_source"], "plan_reasoning_effort:preset")
        self.assertEqual(
            plan_resolution_meta["resolved"]["plan_reasoning_effort_source"],
            "plan_reasoning_effort:preset",
        )
        self.assertEqual(step_resolved["reasoning_effort"], "medium")
        self.assertEqual(step_meta["effective_reasoning_effort"], "medium")
        self.assertEqual(step_meta["base_reasoning_effort_source"], "reasoning_effort:cli")
        self.assertEqual(synth_resolved["reasoning_effort"], "medium")
        self.assertEqual(synth_meta["effective_reasoning_effort"], "medium")

    def test_resolve_multipass_stage_llm_config_applies_stage_overrides_and_non_codex_plan_carrier(self) -> None:
        resolved = {
            "provider": "openai",
            "model": "gpt-5.4",
            "reasoning_effort": "medium",
            "plan_reasoning_effort": "high",
        }
        resolution_meta = {
            "resolved": {
                "reasoning_effort_source": "preset",
                "plan_reasoning_effort_source": "reviewflow_defaults",
            }
        }
        multipass_cfg = {
            "plan_reasoning_effort": "minimal",
            "step_reasoning_effort": "low",
            "synth_reasoning_effort": "xhigh",
        }

        plan_resolved, plan_resolution_meta, plan_meta = rf.resolve_multipass_stage_llm_config(
            stage="plan",
            resolved=resolved,
            resolution_meta=resolution_meta,
            multipass_cfg=multipass_cfg,
        )
        step_resolved, step_resolution_meta, step_meta = rf.resolve_multipass_stage_llm_config(
            stage="step",
            resolved=resolved,
            resolution_meta=resolution_meta,
            multipass_cfg=multipass_cfg,
        )
        synth_resolved, synth_resolution_meta, synth_meta = rf.resolve_multipass_stage_llm_config(
            stage="synth",
            resolved=resolved,
            resolution_meta=resolution_meta,
            multipass_cfg=multipass_cfg,
        )

        self.assertEqual(plan_meta["applied_reasoning_effort_field"], "reasoning_effort")
        self.assertEqual(plan_meta["effective_reasoning_effort"], "minimal")
        self.assertEqual(plan_meta["effective_reasoning_effort_source"], "multipass_config")
        self.assertEqual(plan_resolved["reasoning_effort"], "minimal")
        self.assertEqual(plan_resolution_meta["resolved"]["reasoning_effort_source"], "multipass_config")
        self.assertEqual(step_meta["effective_reasoning_effort"], "low")
        self.assertEqual(step_resolved["reasoning_effort"], "low")
        self.assertEqual(step_resolution_meta["resolved"]["reasoning_effort_source"], "multipass_config")
        self.assertEqual(synth_meta["effective_reasoning_effort"], "xhigh")
        self.assertEqual(synth_resolved["reasoning_effort"], "xhigh")
        self.assertEqual(synth_resolution_meta["resolved"]["reasoning_effort_source"], "multipass_config")

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

    def test_resolve_llm_config_without_explicit_preset_uses_codex_cli_identity(self) -> None:
        base = ROOT / ".tmp_test_base_codex_llm_implicit.toml"
        rf_cfg = ROOT / ".tmp_test_reviewflow_llm_implicit.toml"
        try:
            base.write_text(
                "\n".join(
                    [
                        'model = "base-codex-model"',
                        'model_reasoning_effort = "high"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            rf_cfg.write_text(
                "\n".join(
                    [
                        "[codex]",
                        'model = "legacy-model"',
                        'model_reasoning_effort = "low"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            resolved, meta = rf.resolve_llm_config(
                base_codex_config_path=base,
                reviewflow_config_path=rf_cfg,
                cli_preset=None,
                cli_model=None,
                cli_effort=None,
                cli_plan_effort=None,
                cli_verbosity=None,
                cli_max_output_tokens=None,
                cli_request_overrides={},
                cli_header_overrides={},
                deprecated_codex_model=None,
                deprecated_codex_effort=None,
                deprecated_codex_plan_effort=None,
            )
            self.assertEqual(resolved["preset"], "codex-cli")
            self.assertEqual(resolved["selected_name"], "codex-cli")
            self.assertEqual(resolved["model"], "legacy-model")
            self.assertEqual(resolved["reasoning_effort"], "low")
            self.assertEqual(meta["selected_preset_source"], "implicit_codex_cli")
            self.assertEqual(meta["resolved_preset_id"], "codex-cli")
            self.assertEqual(meta["resolved"]["model_source"], "preset")
            self.assertEqual(meta["resolved"]["reasoning_effort_source"], "preset")
            self.assertIn("reviewflow_defaults", meta)
            self.assertNotIn("legacy_codex_defaults", meta)
        finally:
            base.unlink(missing_ok=True)
            rf_cfg.unlink(missing_ok=True)

    def test_resolve_llm_config_codex_cli_builtin_default_effort_is_xhigh(self) -> None:
        base = ROOT / ".tmp_test_base_codex_llm_builtin_default.toml"
        rf_cfg = ROOT / ".tmp_test_reviewflow_llm_builtin_default.toml"
        try:
            base.write_text('model = "base-codex-model"\n', encoding="utf-8")
            rf_cfg.write_text("", encoding="utf-8")
            resolved, meta = rf.resolve_llm_config(
                base_codex_config_path=base,
                reviewflow_config_path=rf_cfg,
                cli_preset=None,
                cli_model=None,
                cli_effort=None,
                cli_plan_effort=None,
                cli_verbosity=None,
                cli_max_output_tokens=None,
                cli_request_overrides={},
                cli_header_overrides={},
                deprecated_codex_model=None,
                deprecated_codex_effort=None,
                deprecated_codex_plan_effort=None,
            )
            self.assertEqual(resolved["preset"], "codex-cli")
            self.assertEqual(resolved["model"], "base-codex-model")
            self.assertEqual(resolved["reasoning_effort"], "xhigh")
            self.assertEqual(meta["resolved"]["reasoning_effort_source"], "preset")
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
                {"CURE_AGENT_RUNTIME_PROFILE": "permissive"},
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
                helper_path = Path(str(balanced["staged_paths"]["chunkhound_helper"]))
                self.assertTrue(helper_path.is_file())
                self.assertEqual(helper_path.parent, work / "bin")
                self.assertEqual(balanced["env"]["CURE_CHUNKHOUND_HELPER"], str(helper_path))
                self.assertEqual(balanced["env"]["PYTHONSAFEPATH"], "1")
                self.assertEqual(balanced["metadata"]["chunkhound_access_mode"], "cli_helper_daemon")
                helper_text = helper_path.read_text(encoding="utf-8")
                self.assertIn("chunkhound mcp", helper_text)
                self.assertIn("code_research", helper_text)
                self.assertIn("DaemonDiscovery", helper_text)
                self.assertIn("chunkhound_runtime_python", helper_text)
                self.assertFalse(
                    any(
                        entry.startswith("mcp_servers.chunkhound.")
                        for entry in balanced["codex_config_overrides"]
                    )
                )

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
