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

    def test_render_prompt_expands_citation_contract_keys(self) -> None:
        import cure_citations

        template = "\n".join(
            [
                "STEP=$STEP_CITATION_CONTRACT",
                "SYNTH=$SYNTH_CITATION_CONTRACT",
                "REVIEW=$REVIEW_CITATION_CONTRACT",
                "STEP_BRACE=${STEP_CITATION_CONTRACT}",
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
        self.assertNotIn("$STEP_CITATION_CONTRACT", rendered)
        self.assertNotIn("$SYNTH_CITATION_CONTRACT", rendered)
        self.assertNotIn("$REVIEW_CITATION_CONTRACT", rendered)
        self.assertNotIn("${STEP_CITATION_CONTRACT}", rendered)
        self.assertIn(cure_citations.STEP_CITATION_CONTRACT, rendered)
        self.assertIn(cure_citations.SYNTH_CITATION_CONTRACT, rendered)
        self.assertIn(cure_citations.REVIEW_CITATION_CONTRACT, rendered)

    def test_render_prompt_contract_wins_over_colliding_extra_vars(self) -> None:
        import cure_citations

        template = "STEP=$STEP_CITATION_CONTRACT\n"
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
            extra_vars={"STEP_CITATION_CONTRACT": "INJECTED_BY_EXTRA_VARS"},
        )
        self.assertNotIn("INJECTED_BY_EXTRA_VARS", rendered)
        self.assertIn(cure_citations.STEP_CITATION_CONTRACT, rendered)

    def test_cod_hypothesis_ledger_prompt_vars_toggle_guidance(self) -> None:
        enabled = rf.cod_hypothesis_ledger_prompt_vars(enabled=True)
        disabled = rf.cod_hypothesis_ledger_prompt_vars(enabled=False)
        self.assertIn("COD_HYPOTHESIS_LEDGER_PLAN_GUIDANCE", enabled)
        self.assertIn("COD_HYPOTHESIS_LEDGER_STEP_GUIDANCE", enabled)
        self.assertIn("COD_HYPOTHESIS_LEDGER_STEP_OUTPUT_SECTION", enabled)
        self.assertIn("COD_HYPOTHESIS_LEDGER_SYNTH_GUIDANCE", enabled)
        self.assertIn("broad candidate set", enabled["COD_HYPOTHESIS_LEDGER_PLAN_GUIDANCE"])
        self.assertIn("Hypothesis Ledger", enabled["COD_HYPOTHESIS_LEDGER_STEP_GUIDANCE"])
        self.assertIn("### Hypothesis Ledger", enabled["COD_HYPOTHESIS_LEDGER_STEP_OUTPUT_SECTION"])
        self.assertIn("suspicious surface", enabled["COD_HYPOTHESIS_LEDGER_STEP_GUIDANCE"])
        self.assertIn("tentative issue", enabled["COD_HYPOTHESIS_LEDGER_STEP_GUIDANCE"])
        self.assertIn("next proof target", enabled["COD_HYPOTHESIS_LEDGER_STEP_GUIDANCE"])
        self.assertIn("Deepen only surviving candidates", enabled["COD_HYPOTHESIS_LEDGER_SYNTH_GUIDANCE"])
        self.assertEqual(
            disabled,
            {
                "COD_HYPOTHESIS_LEDGER_PLAN_GUIDANCE": "",
                "COD_HYPOTHESIS_LEDGER_STEP_GUIDANCE": "",
                "COD_HYPOTHESIS_LEDGER_STEP_OUTPUT_SECTION": "",
                "COD_HYPOTHESIS_LEDGER_SYNTH_GUIDANCE": "",
            },
        )


class CureCitationsPublicApiTests(unittest.TestCase):
    """Direct unit coverage for the five public helpers in ``cure_citations``.

    These helpers are foundational to the Story 42 grounding pipeline but had
    been exercised only indirectly through validator integration tests.
    """

    def test_trailing_sources_suffix_returns_trimmed_tail(self) -> None:
        import cure_citations as cc

        self.assertEqual(
            cc.trailing_sources_suffix("Finding. Sources: `src/a.py:12`"),
            "`src/a.py:12`",
        )
        self.assertEqual(
            cc.trailing_sources_suffix("Finding. Sources:   `src/a.py:12`  "),
            "`src/a.py:12`",
        )

    def test_trailing_sources_suffix_absent_when_marker_missing_or_empty(self) -> None:
        import cure_citations as cc

        self.assertEqual(cc.trailing_sources_suffix("Finding without marker"), "")
        self.assertEqual(cc.trailing_sources_suffix("Sources: `src/a.py:12`"), "")
        self.assertEqual(cc.trailing_sources_suffix("Finding. Sources:   "), "")

    def test_has_sources_marker_requires_head_and_tail(self) -> None:
        import cure_citations as cc

        self.assertTrue(cc.has_sources_marker("Finding. Sources: `src/a.py:12`"))
        self.assertFalse(cc.has_sources_marker("Finding without marker"))
        self.assertFalse(cc.has_sources_marker("Sources: `src/a.py:12`"))
        self.assertFalse(cc.has_sources_marker("Finding. Sources:   "))

    def test_has_path_line_citation_matches_backticked_and_bare(self) -> None:
        import cure_citations as cc

        self.assertTrue(cc.has_path_line_citation("`src/a.py:12`"))
        self.assertTrue(cc.has_path_line_citation("src/a.py:12"))
        self.assertTrue(cc.has_path_line_citation("see `src/a.py:12`, also `tests/b.py:44`"))
        self.assertFalse(cc.has_path_line_citation(""))
        self.assertFalse(cc.has_path_line_citation("src/a.py"))
        self.assertFalse(cc.has_path_line_citation("src/a.py:0"))

    def test_sources_suffix_items_preserves_backticked_and_bare_residue(self) -> None:
        import cure_citations as cc

        self.assertEqual(
            cc._sources_suffix_items("`src/a.py:12`, `tests/b.py:44`"),
            ["src/a.py:12", "tests/b.py:44"],
        )
        self.assertEqual(
            cc._sources_suffix_items("`src/a.py:12`, tests/b.py"),
            ["src/a.py:12", "tests/b.py"],
        )
        self.assertEqual(
            cc._sources_suffix_items("`src/a.py:12` tests/b.py"),
            ["src/a.py:12", "tests/b.py"],
        )

    def test_sources_suffix_items_comma_split_when_no_backticks(self) -> None:
        import cure_citations as cc

        self.assertEqual(
            cc._sources_suffix_items("src/a.py:12, tests/b.py:44"),
            ["src/a.py:12", "tests/b.py:44"],
        )
        self.assertEqual(
            cc._sources_suffix_items("src/a.py:12,  , tests/b.py:44"),
            ["src/a.py:12", "", "tests/b.py:44"],
        )

    def test_sources_suffix_items_preserves_empty_comma_slots_after_backticks(self) -> None:
        import cure_citations as cc

        self.assertEqual(
            cc._sources_suffix_items("`src/a.py:12`, ,"),
            ["src/a.py:12", "", ""],
        )

    def test_sources_suffix_items_empty_for_blank_input(self) -> None:
        import cure_citations as cc

        self.assertEqual(cc._sources_suffix_items(""), [])
        self.assertEqual(cc._sources_suffix_items("   "), [])

    def test_has_incomplete_sources_flags_file_only_tail(self) -> None:
        import cure_citations as cc

        self.assertTrue(cc.has_incomplete_sources("Finding. Sources: `src/a.py`"))
        self.assertTrue(cc.has_incomplete_sources("Finding. Sources: src/a.py"))

    def test_has_incomplete_sources_accepts_complete_tail(self) -> None:
        import cure_citations as cc

        self.assertFalse(cc.has_incomplete_sources("Finding. Sources: `src/a.py:12`"))
        self.assertFalse(
            cc.has_incomplete_sources("Finding. Sources: `src/a.py:12`, `tests/b.py:44`")
        )

    def test_has_incomplete_sources_flags_mixed_complete_and_file_only(self) -> None:
        import cure_citations as cc

        # At least one file-only citation in the tail → incomplete.
        self.assertTrue(
            cc.has_incomplete_sources("Finding. Sources: `src/a.py:12`, `src/b.py`")
        )
        self.assertTrue(
            cc.has_incomplete_sources("Finding. Sources: src/a.py:12, src/b.py")
        )
        self.assertTrue(
            cc.has_incomplete_sources("Finding. Sources: `src/a.py:12` src/b.py")
        )

    def test_has_incomplete_sources_false_when_no_marker(self) -> None:
        import cure_citations as cc

        self.assertFalse(cc.has_incomplete_sources("Finding without marker"))
        self.assertFalse(cc.has_incomplete_sources("Finding. Sources:   "))

    def test_has_incomplete_sources_flags_empty_comma_slots(self) -> None:
        import cure_citations as cc

        self.assertTrue(cc.has_incomplete_sources("Finding. Sources: ,,,"))
        self.assertTrue(cc.has_incomplete_sources("Finding. Sources: `src/a.py:12`, ,"))
        self.assertTrue(cc.has_incomplete_sources("Finding. Sources: src/a.py:12, , tests/b.py:44"))


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

    def test_materialize_chunkhound_env_config_preserves_excludes_and_injects_chunkhound_once(
        self,
    ) -> None:
        output = ROOT / ".tmp_test_materialized_chunkhound_exclude.json"
        resolved_config = {
            "indexing": {"exclude": ["**/.git/**", "**/openspec/**"]},
        }
        try:
            rf.materialize_chunkhound_env_config(
                resolved_config=resolved_config,
                output_config_path=output,
                database_provider="duckdb",
                database_path=ROOT / ".tmp_test_chunkhound_db",
            )

            materialized = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                materialized["indexing"]["exclude"],
                ["**/.git/**", "**/openspec/**", "**/.chunkhound/**"],
            )
            self.assertEqual(
                materialized["indexing"]["exclude"].count("**/.chunkhound/**"),
                1,
            )
            self.assertEqual(
                resolved_config,
                {"indexing": {"exclude": ["**/.git/**", "**/openspec/**"]}},
            )
        finally:
            output.unlink(missing_ok=True)

    def test_materialize_chunkhound_env_config_is_idempotent_and_dedupes_chunkhound_exclude(
        self,
    ) -> None:
        materializers = (
            ("cure", rf.materialize_chunkhound_env_config),
            ("cure_flows", cure_flows.materialize_chunkhound_env_config),
        )
        for route_name, materialize in materializers:
            with self.subTest(route=route_name):
                first_output = ROOT / f".tmp_test_materialized_chunkhound_{route_name}_dedup_first.json"
                second_output = ROOT / f".tmp_test_materialized_chunkhound_{route_name}_dedup_second.json"
                try:
                    materialize(
                        resolved_config={
                            "indexing": {
                                "exclude": [
                                    "**/.git/**",
                                    "**/.chunkhound/**",
                                    "**/.chunkhound/**",
                                ]
                            }
                        },
                        output_config_path=first_output,
                        database_provider="duckdb",
                        database_path=ROOT / ".tmp_test_chunkhound_db",
                    )
                    first = json.loads(first_output.read_text(encoding="utf-8"))

                    materialize(
                        resolved_config=first,
                        output_config_path=second_output,
                        database_provider="duckdb",
                        database_path=ROOT / ".tmp_test_chunkhound_db",
                    )
                    second = json.loads(second_output.read_text(encoding="utf-8"))

                    self.assertEqual(
                        first["indexing"]["exclude"],
                        ["**/.git/**", "**/.chunkhound/**"],
                    )
                    self.assertEqual(second, first)
                    self.assertEqual(second["indexing"]["exclude"].count("**/.chunkhound/**"), 1)
                finally:
                    first_output.unlink(missing_ok=True)
                    second_output.unlink(missing_ok=True)

    def test_materialize_chunkhound_env_config_adds_missing_indexing(self) -> None:
        output = ROOT / ".tmp_test_materialized_chunkhound_missing_indexing.json"
        try:
            rf.materialize_chunkhound_env_config(
                resolved_config={"research": {"algorithm": "semantic"}},
                output_config_path=output,
                database_provider="duckdb",
                database_path=ROOT / ".tmp_test_chunkhound_db",
            )

            materialized = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(materialized["indexing"], {"exclude": ["**/.chunkhound/**"]})
        finally:
            output.unlink(missing_ok=True)

    def test_materialize_chunkhound_env_config_rejects_malformed_indexing_or_exclude(
        self,
    ) -> None:
        malformed_configs = (
            ("indexing-is-null", {"indexing": None}),
            ("indexing-is-list", {"indexing": []}),
            ("indexing-is-string", {"indexing": "invalid"}),
            ("exclude-is-null", {"indexing": {"exclude": None}}),
            ("exclude-is-string", {"indexing": {"exclude": "**/.git/**"}}),
            ("exclude-is-object", {"indexing": {"exclude": {"pattern": "**/.git/**"}}}),
        )
        for case_name, resolved_config in malformed_configs:
            with self.subTest(case=case_name):
                output = ROOT / f".tmp_test_materialized_chunkhound_malformed_{case_name}.json"
                output.unlink(missing_ok=True)
                try:
                    with self.assertRaises(rf.ReviewflowError):
                        rf.materialize_chunkhound_env_config(
                            resolved_config=resolved_config,
                            output_config_path=output,
                            database_provider="duckdb",
                            database_path=ROOT / ".tmp_test_chunkhound_db",
                        )
                    self.assertFalse(output.exists())
                finally:
                    output.unlink(missing_ok=True)

    def test_materialize_chunkhound_env_config_converts_gitignore_sentinel_to_exact_exclusion(
        self,
    ) -> None:
        output = ROOT / ".tmp_test_materialized_chunkhound_legacy_sentinel.json"
        resolved_config = {"indexing": {"exclude": ".gitignore"}}
        try:
            rf.materialize_chunkhound_env_config(
                resolved_config=resolved_config,
                output_config_path=output,
                database_provider="duckdb",
                database_path=ROOT / ".tmp_test_chunkhound_db",
            )

            materialized = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                materialized["indexing"]["exclude"],
                ["**/.chunkhound/**"],
            )
            self.assertEqual(resolved_config, {"indexing": {"exclude": ".gitignore"}})
        finally:
            output.unlink(missing_ok=True)

    def test_materialize_chunkhound_env_config_preserves_gitignore_sentinel_semantics_across_modes(
        self,
    ) -> None:
        materializers = (
            ("cure", rf.materialize_chunkhound_env_config),
            ("cure_flows", cure_flows.materialize_chunkhound_env_config),
        )
        for route_name, materialize in materializers:
            for exclude_mode in (None, "combined", "config_only", "gitignore_only"):
                with self.subTest(route=route_name, exclude_mode=exclude_mode):
                    output = ROOT / (
                        f".tmp_test_materialized_chunkhound_{route_name}_gitignore_mode_"
                        f"{exclude_mode or 'unset'}.json"
                    )
                    indexing = {"exclude": ".gitignore"}
                    if exclude_mode is not None:
                        indexing["exclude_mode"] = exclude_mode
                    resolved_config = {"indexing": indexing}
                    expected_resolved_config = {"indexing": dict(indexing)}
                    try:
                        materialize(
                            resolved_config=resolved_config,
                            output_config_path=output,
                            database_provider="duckdb",
                            database_path=ROOT / ".tmp_test_chunkhound_db",
                        )

                        materialized = json.loads(output.read_text(encoding="utf-8"))
                        self.assertEqual(
                            materialized["indexing"]["exclude"],
                            ["**/.chunkhound/**"],
                        )
                        self.assertEqual(
                            materialized["indexing"]["exclude_mode"],
                            "gitignore_only",
                        )
                        self.assertEqual(resolved_config, expected_resolved_config)
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

    def test_load_reviewflow_codex_defaults_rejects_legacy_plan_mode_reasoning_effort(self) -> None:
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
            with self.assertRaisesRegex(
                rf.ReviewflowError,
                r"\[codex\]\.plan_mode_reasoning_effort is no longer supported",
            ):
                rf.load_reviewflow_codex_defaults(config_path=cfg)
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
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.resolve_codex_flags(
                    base_config_path=base,
                    reviewflow_config_path=rf_cfg,
                    cli_model="cli-model",
                    cli_effort=None,
                    cli_plan_effort="medium",
                )
            self.assertIn("--llm-plan-effort", str(ctx.exception))
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

    def test_load_reviewflow_multipass_defaults_no_longer_emits_stage_efforts(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_multipass_default_step_effort.toml"
        try:
            cfg.write_text("[multipass]\nmax_steps = 5\n", encoding="utf-8")
            mp, meta = rf.load_reviewflow_multipass_defaults(config_path=cfg)
            self.assertNotIn("step_reasoning_effort", mp)
            self.assertNotIn("step_reasoning_effort", meta["multipass"])
            self.assertNotIn("plan_reasoning_effort", mp)
            self.assertNotIn("synth_reasoning_effort", mp)
        finally:
            cfg.unlink(missing_ok=True)

    def test_load_reviewflow_multipass_defaults_rejects_stage_reasoning_efforts(self) -> None:
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
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.load_reviewflow_multipass_defaults(config_path=cfg)
            self.assertIn("[multipass].plan_reasoning_effort", str(ctx.exception))
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
        resolved = {"provider": "codex", "model": "gpt-5.4", "reasoning_effort": "xhigh"}
        resolution_meta = {
            "resolved": {
                "model_source": "preset",
                "reasoning_effort_source": "preset",
            }
        }
        multipass_cfg = {}

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
        self.assertEqual(step_resolved["reasoning_effort"], "xhigh")
        self.assertEqual(step_meta["effective_reasoning_effort"], "xhigh")
        self.assertEqual(step_resolution_meta["resolved"]["reasoning_effort_source"], "reasoning_effort:preset")
        self.assertEqual(synth_resolved["reasoning_effort"], "xhigh")
        self.assertEqual(synth_meta["effective_reasoning_effort"], "xhigh")
        self.assertEqual(synth_resolution_meta["resolved"]["reasoning_effort_source"], "reasoning_effort:preset")

    def test_resolve_multipass_stage_llm_config_preserves_single_effort_across_codex_stages(self) -> None:
        resolved = {"provider": "codex", "model": "gpt-5.4", "reasoning_effort": "medium"}
        resolution_meta = {
            "resolved": {
                "model_source": "cli",
                "reasoning_effort_source": "cli",
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
        self.assertEqual(plan_meta["applied_reasoning_effort_field"], "reasoning_effort")
        self.assertEqual(plan_meta["effective_reasoning_effort"], "medium")
        self.assertEqual(plan_meta["base_reasoning_effort_source"], "reasoning_effort:cli")
        self.assertEqual(step_resolved["reasoning_effort"], "medium")
        self.assertEqual(step_meta["effective_reasoning_effort"], "medium")
        self.assertEqual(step_meta["base_reasoning_effort_source"], "reasoning_effort:cli")
        self.assertEqual(synth_resolved["reasoning_effort"], "medium")
        self.assertEqual(synth_meta["effective_reasoning_effort"], "medium")

    def test_resolve_multipass_stage_llm_config_uses_single_effort_for_non_codex_stages(self) -> None:
        resolved = {"provider": "openai", "model": "gpt-5.4", "reasoning_effort": "medium"}
        resolution_meta = {"resolved": {"reasoning_effort_source": "preset"}}
        multipass_cfg = {}

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
        self.assertEqual(plan_meta["effective_reasoning_effort"], "medium")
        self.assertEqual(plan_meta["effective_reasoning_effort_source"], "inherited")
        self.assertEqual(plan_resolved["reasoning_effort"], "medium")
        self.assertEqual(plan_resolution_meta["resolved"]["reasoning_effort_source"], "reasoning_effort:preset")
        self.assertEqual(step_meta["effective_reasoning_effort"], "medium")
        self.assertEqual(step_resolved["reasoning_effort"], "medium")
        self.assertEqual(step_resolution_meta["resolved"]["reasoning_effort_source"], "reasoning_effort:preset")
        self.assertEqual(synth_meta["effective_reasoning_effort"], "medium")
        self.assertEqual(synth_resolved["reasoning_effort"], "medium")
        self.assertEqual(synth_resolution_meta["resolved"]["reasoning_effort_source"], "reasoning_effort:preset")

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
                        'preset = "codex-cli"',
                        'api_key = "test-codex-key"',  # pragma: allowlist secret
                        'model = "x-ai/grok-4.1-fast"',
                        'reasoning_effort = "high"',
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
            self.assertEqual(llm_cfg["presets"]["fast_router"]["preset"], "codex-cli")
            self.assertEqual(llm_cfg["presets"]["fast_router"]["provider"], "codex")
            self.assertEqual(llm_cfg["presets"]["fast_router"]["transport"], "cli")
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
                        "",
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
                cli_model="cli-model",
                cli_effort="xhigh",
                cli_plan_effort=None,
                cli_verbosity=None,
                cli_max_output_tokens=None,
                cli_request_overrides={},
                cli_header_overrides={},
                deprecated_codex_model="deprecated-model",
                deprecated_codex_effort=None,
                deprecated_codex_plan_effort=None,
            )
            self.assertEqual(resolved["preset"], "codex-cli")
            self.assertEqual(resolved["selected_name"], "my_codex")
            self.assertEqual(resolved["provider"], "codex")
            self.assertEqual(resolved["model"], "cli-model")
            self.assertEqual(resolved["reasoning_effort"], "xhigh")
            self.assertEqual(meta["resolved"]["model_source"], "cli")
            self.assertEqual(meta["resolved"]["reasoning_effort_source"], "cli")
        finally:
            base.unlink(missing_ok=True)
            rf_cfg.unlink(missing_ok=True)

    def test_resolve_llm_config_rejects_codex_ignored_cli_controls(self) -> None:
        base = ROOT / ".tmp_test_codex_ignored_cli.toml"
        try:
            base.write_text('model = "gpt-test"\n', encoding="utf-8")
            variants = (
                {"cli_verbosity": "low"},
                {"cli_max_output_tokens": 100},
                {"cli_request_overrides": {"temperature": 0.2}},
                {"cli_header_overrides": {"X-Test": "yes"}},
            )
            defaults = {
                "base_codex_config_path": base,
                "reviewflow_config_path": None,
                "cli_preset": None,
                "cli_model": None,
                "cli_effort": None,
                "cli_plan_effort": None,
                "cli_verbosity": None,
                "cli_max_output_tokens": None,
                "cli_request_overrides": {},
                "cli_header_overrides": {},
                "deprecated_codex_model": None,
                "deprecated_codex_effort": None,
                "deprecated_codex_plan_effort": None,
            }
            for override in variants:
                with self.subTest(override=override), self.assertRaisesRegex(
                    rf.ReviewflowError, "Codex.*ignored|ignored.*Codex"
                ):
                    rf.resolve_llm_config(**(defaults | override))
        finally:
            base.unlink(missing_ok=True)

    def test_resolve_llm_config_rejects_codex_ignored_preset_fields(self) -> None:
        base = ROOT / ".tmp_test_codex_ignored_preset_base.toml"
        cfg = ROOT / ".tmp_test_codex_ignored_preset.toml"
        try:
            base.write_text('model = "gpt-test"\n', encoding="utf-8")
            values = {
                "request": '{ temperature = 0.2 }',
                "metadata": '{ team = "review" }',
                "headers": '{ X_Test = "yes" }',
                "api_key": '"secret"',
                "store": "true",
                "include": '["usage"]',
                "text_verbosity": '"high"',
                "max_output_tokens": "9000",
            }
            for field, value in values.items():
                with self.subTest(field=field):
                    cfg.write_text(
                        '[llm]\ndefault_preset = "custom"\n[llm_presets.custom]\n'
                        f'preset = "codex-cli"\n{field} = {value}\n',
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(rf.ReviewflowError, field):
                        rf.resolve_llm_config(
                            base_codex_config_path=base,
                            reviewflow_config_path=cfg,
                            cli_preset=None, cli_model=None, cli_effort=None,
                            cli_plan_effort=None, cli_verbosity=None,
                            cli_max_output_tokens=None, cli_request_overrides={},
                            cli_header_overrides={}, deprecated_codex_model=None,
                            deprecated_codex_effort=None,
                            deprecated_codex_plan_effort=None,
                        )
        finally:
            base.unlink(missing_ok=True)
            cfg.unlink(missing_ok=True)

    def test_resolve_llm_config_rejects_legacy_codex_plan_mode_reasoning_effort(self) -> None:
        base = ROOT / ".tmp_test_base_codex_llm_invalid_plan.toml"
        rf_cfg = ROOT / ".tmp_test_reviewflow_llm_invalid_plan.toml"
        try:
            base.write_text('model = "base-codex-model"\n', encoding="utf-8")
            rf_cfg.write_text(
                "\n".join(
                    [
                        "[llm]",
                        'default_preset = "my_codex"',
                        "",
                        "[llm_presets.my_codex]",
                        'preset = "codex-cli"',
                        "",
                        "[codex]",
                        'plan_mode_reasoning_effort = "medium"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                rf.ReviewflowError,
                r"\[codex\]\.plan_mode_reasoning_effort is no longer supported",
            ):
                rf.resolve_llm_config(
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
            with mock.patch.dict(
                os.environ,
                {
                    "CODEX_THREAD_ID": "",
                    "CODEX_HOME": "",
                },
                clear=False,
            ):
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

    def test_resolve_llm_config_marks_builtin_defaults_as_promptable_but_explicit_overrides_as_configured(self) -> None:
        base = ROOT / ".tmp_test_base_codex_llm_promptable.toml"
        rf_cfg = ROOT / ".tmp_test_reviewflow_llm_promptable.toml"
        try:
            base.write_text("", encoding="utf-8")
            rf_cfg.write_text(
                "\n".join(
                    [
                        "[llm]",
                        'default_preset = "codex_named"',
                        "",
                        "[llm_presets.codex_named]",
                        'preset = "codex-cli"',
                        'model = "gpt-5.4"',
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
            self.assertEqual(resolved["model"], "gpt-5.4")
            self.assertEqual(meta["resolved"]["model_source"], "preset")
            self.assertEqual(meta["resolved"]["model_source_detail"], "preset_explicit")
            self.assertEqual(meta["resolved"]["reasoning_effort"], "high")
            self.assertEqual(meta["resolved"]["reasoning_effort_source"], "preset")
            self.assertEqual(meta["resolved"]["reasoning_effort_source_detail"], "preset_builtin")

            direct_resolved, direct_meta = rf.resolve_llm_config(
                base_codex_config_path=base,
                reviewflow_config_path=rf_cfg,
                cli_preset="codex-cli",
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
            self.assertIsNone(direct_resolved["model"])
            self.assertEqual(direct_meta["resolved"]["model_source_detail"], "unset")
            self.assertEqual(direct_meta["resolved"]["reasoning_effort_source_detail"], "preset_builtin")
        finally:
            base.unlink(missing_ok=True)
            rf_cfg.unlink(missing_ok=True)

    def test_resolve_llm_config_autodetects_codex_from_env_when_no_explicit_selection_exists(self) -> None:
        base = ROOT / ".tmp_test_base_codex_llm_detect_codex.toml"
        rf_cfg = ROOT / ".tmp_test_reviewflow_llm_detect_codex.toml"
        try:
            base.write_text('model = "base-codex-model"\n', encoding="utf-8")
            rf_cfg.write_text("", encoding="utf-8")
            with mock.patch.dict(
                os.environ,
                {
                    "CODEX_THREAD_ID": "thread-123",
                    "CODEX_HOME": "/tmp/codex-home",
                                    },
                clear=False,
            ):
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
            self.assertEqual(resolved["provider"], "codex")
            self.assertEqual(meta["selected_preset_source"], "detected_env")
            self.assertEqual(meta["resolved_preset_id"], "codex-cli")
        finally:
            base.unlink(missing_ok=True)
            rf_cfg.unlink(missing_ok=True)

    def test_resolve_llm_config_config_default_beats_env_autodetect(self) -> None:
        base = ROOT / ".tmp_test_base_codex_llm_detect_config_priority.toml"
        rf_cfg = ROOT / ".tmp_test_reviewflow_llm_detect_config_priority.toml"
        try:
            base.write_text('model = "base-codex-model"\n', encoding="utf-8")
            rf_cfg.write_text(
                "\n".join(
                    [
                        "[llm]",
                        'default_preset = "codex_default"',
                        "",
                        "[llm_presets.codex_default]",
                        'preset = "codex-cli"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {
                    "CODEX_THREAD_ID": "thread-123",
                    "CODEX_HOME": "/tmp/codex-home",
                },
                clear=False,
            ):
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
            self.assertEqual(resolved["provider"], "codex")
            self.assertEqual(meta["selected_preset_source"], "cure.toml")
        finally:
            base.unlink(missing_ok=True)
            rf_cfg.unlink(missing_ok=True)

    def test_resolve_llm_config_cli_preset_beats_env_autodetect(self) -> None:
        base = ROOT / ".tmp_test_base_codex_llm_detect_cli_priority.toml"
        rf_cfg = ROOT / ".tmp_test_reviewflow_llm_detect_cli_priority.toml"
        try:
            base.write_text('model = "base-codex-model"\n', encoding="utf-8")
            rf_cfg.write_text("", encoding="utf-8")
            with mock.patch.dict(
                os.environ,
                {
                    "CODEX_THREAD_ID": "thread-123",
                    "CODEX_HOME": "/tmp/codex-home",
                },
                clear=False,
            ):
                resolved, meta = rf.resolve_llm_config(
                    base_codex_config_path=base,
                    reviewflow_config_path=rf_cfg,
                    cli_preset="codex-cli",
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
            self.assertEqual(resolved["provider"], "codex")
            self.assertEqual(meta["selected_preset_source"], "cli")
        finally:
            base.unlink(missing_ok=True)
            rf_cfg.unlink(missing_ok=True)

    def test_resolve_llm_config_codex_cli_builtin_default_effort_is_high(self) -> None:
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
            self.assertEqual(resolved["reasoning_effort"], "high")
            self.assertEqual(meta["resolved"]["reasoning_effort_source"], "preset")
        finally:
            base.unlink(missing_ok=True)
            rf_cfg.unlink(missing_ok=True)

    def test_resolve_llm_config_allows_direct_builtin_preset_selection(self) -> None:
        base = ROOT / ".tmp_test_base_codex_llm_builtin.toml"
        rf_cfg = ROOT / ".tmp_test_reviewflow_llm_builtin.toml"
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
            rf_cfg.write_text("", encoding="utf-8")
            resolved, meta = rf.resolve_llm_config(
                base_codex_config_path=base,
                reviewflow_config_path=rf_cfg,
                cli_preset="codex-cli",
                cli_model="gpt-5.4",
                cli_effort="high",
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
            self.assertEqual(resolved["provider"], "codex")
            self.assertEqual(meta["selected_name"], "codex-cli")
            self.assertEqual(meta["resolved_preset_id"], "codex-cli")
        finally:
            base.unlink(missing_ok=True)
            rf_cfg.unlink(missing_ok=True)

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
                        'transport = "cli"',
                        'provider = "codex"',
                        'command = "codex"',
                        'api_key = "test-codex-key"',  # pragma: allowlist secret
                        'model = "x-ai/grok-4.1-fast"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            llm_cfg, meta = rf.load_reviewflow_llm_config(config_path=cfg)
            self.assertEqual(llm_cfg["presets"]["legacy_router"]["preset"], "codex-cli")
            self.assertEqual(meta["deprecated_explicit_presets"], ["legacy_router"])
        finally:
            cfg.unlink(missing_ok=True)

    def test_load_reviewflow_llm_config_rejects_removed_gemini_builtin_preset(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_llm_gemini_builtin.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[llm]",
                        'default_preset = "gemini_default"',
                        "",
                        "[llm_presets.gemini_default]",
                        'preset = "gemini-cli"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.load_reviewflow_llm_config(config_path=cfg)
            self.assertIn("Gemini support was removed from CURe", str(ctx.exception))
            self.assertIn("gemini_default", str(ctx.exception))
        finally:
            cfg.unlink(missing_ok=True)

    def test_load_reviewflow_llm_config_rejects_removed_gemini_explicit_provider(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_llm_gemini_explicit.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[llm]",
                        'default_preset = "legacy_gemini"',
                        "",
                        "[llm_presets.legacy_gemini]",
                        'transport = "cli"',
                        'provider = "gemini"',
                        'command = "gemini"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.load_reviewflow_llm_config(config_path=cfg)
            self.assertIn("Gemini support was removed from CURe", str(ctx.exception))
            self.assertIn("legacy_gemini", str(ctx.exception))
        finally:
            cfg.unlink(missing_ok=True)

    def test_resolve_llm_config_rejects_removed_gemini_builtin_selection(self) -> None:
        base = ROOT / ".tmp_test_base_codex_llm_removed_gemini.toml"
        rf_cfg = ROOT / ".tmp_test_reviewflow_llm_removed_gemini.toml"
        try:
            base.write_text('model = "base-codex-model"\n', encoding="utf-8")
            rf_cfg.write_text("", encoding="utf-8")
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.resolve_llm_config(
                    base_codex_config_path=base,
                    reviewflow_config_path=rf_cfg,
                    cli_preset="gemini-cli",
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
            self.assertIn("Gemini support was removed from CURe", str(ctx.exception))
            self.assertIn("gemini-cli", str(ctx.exception))
        finally:
            base.unlink(missing_ok=True)
            rf_cfg.unlink(missing_ok=True)

    def test_load_reviewflow_llm_config_rejects_removed_http_builtin_preset(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_llm_http_builtin.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[llm]",
                        'default_preset = "router_default"',
                        "",
                        "[llm_presets.router_default]",
                        'preset = "openrouter-responses"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.load_reviewflow_llm_config(config_path=cfg)
            self.assertIn("were removed from CURe", str(ctx.exception))
            self.assertIn("router_default", str(ctx.exception))
        finally:
            cfg.unlink(missing_ok=True)

    def test_load_reviewflow_llm_config_rejects_removed_http_explicit_provider(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_llm_http_explicit.toml"
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
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.load_reviewflow_llm_config(config_path=cfg)
            self.assertIn("were removed from CURe", str(ctx.exception))
            self.assertIn("legacy_router", str(ctx.exception))
        finally:
            cfg.unlink(missing_ok=True)

    def test_load_reviewflow_llm_config_rejects_removed_http_custom_provider_name(self) -> None:
        """A custom provider name with transport = \"http\" must get the same
        removal message — not be silently discarded into \"unknown preset\"."""
        cfg = ROOT / ".tmp_test_reviewflow_llm_http_custom_provider.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[llm]",
                        'default_preset = "custom_http"',
                        "",
                        "[llm_presets.custom_http]",
                        'transport = "http"',
                        'provider = "my-vendor"',
                        'endpoint = "chat"',
                        'base_url = "https://llm.example.com"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.load_reviewflow_llm_config(config_path=cfg)
            self.assertIn("were removed from CURe", str(ctx.exception))
            self.assertIn("custom_http", str(ctx.exception))
        finally:
            cfg.unlink(missing_ok=True)

    def test_resolve_llm_config_rejects_removed_http_builtin_selection(self) -> None:
        base = ROOT / ".tmp_test_base_codex_llm_removed_http.toml"
        rf_cfg = ROOT / ".tmp_test_reviewflow_llm_removed_http.toml"
        try:
            base.write_text('model = "base-codex-model"\n', encoding="utf-8")
            rf_cfg.write_text("", encoding="utf-8")
            for preset in ("openai-responses", "openrouter-responses"):
                with self.subTest(preset=preset):
                    with self.assertRaises(rf.ReviewflowError) as ctx:
                        rf.resolve_llm_config(
                            base_codex_config_path=base,
                            reviewflow_config_path=rf_cfg,
                            cli_preset=preset,
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
                    self.assertIn("were removed from CURe", str(ctx.exception))
                    self.assertIn(preset, str(ctx.exception))
        finally:
            base.unlink(missing_ok=True)
            rf_cfg.unlink(missing_ok=True)

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


class MetaJsonWriteTests(unittest.TestCase):
    def test_write_json_uses_unique_tmp_per_write(self) -> None:
        """Concurrent writers must never share a temp file: a fixed `.tmp`
        name lets one process truncate another's temp write or crash its
        os.replace with FileNotFoundError."""
        import meta as meta_mod

        path = ROOT / ".tmp_test_write_json_unique_tmp" / "meta.json"
        try:
            shutil.rmtree(path.parent, ignore_errors=True)
            path.parent.mkdir(parents=True, exist_ok=True)
            used: list[str] = []
            real_replace = meta_mod.os.replace

            def _capture_replace(src: str, dst: str) -> None:
                used.append(str(src))
                real_replace(src, dst)

            with mock.patch.object(meta_mod.os, "replace", side_effect=_capture_replace):
                meta_mod.write_json(path, {"a": 1})
                meta_mod.write_json(path, {"b": 2})
            self.assertEqual(len(used), 2)
            self.assertNotEqual(used[0], used[1])
            self.assertFalse(any(Path(u).name == "meta.json.tmp" for u in used))
            self.assertEqual(sorted(p.name for p in path.parent.iterdir()), ["meta.json"])
        finally:
            shutil.rmtree(path.parent, ignore_errors=True)


class UtilityModelConfigTests(unittest.TestCase):
    def _write_base_config(self, name: str = ".tmp_test_utility_base.toml") -> Path:
        base = ROOT / name
        base.write_text("", encoding="utf-8")
        return base

    def _resolve_main(
        self,
        *,
        base: Path,
        cfg: Path | None,
        cli_preset: str | None = None,
        cli_model: str | None = None,
        cli_effort: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        return rf.resolve_llm_config(
            base_codex_config_path=base,
            reviewflow_config_path=cfg,
            cli_preset=cli_preset,
            cli_model=cli_model,
            cli_effort=cli_effort,
            cli_plan_effort=None,
            cli_verbosity=None,
            cli_max_output_tokens=None,
            cli_request_overrides={},
            cli_header_overrides={},
            deprecated_codex_model=None,
            deprecated_codex_effort=None,
            deprecated_codex_plan_effort=None,
        )

    def _resolve_utility(
        self,
        *,
        main_resolved: dict[str, Any],
        main_meta: dict[str, Any],
        cfg: Path | None,
        utility_llm_preset: str | None = None,
        utility_llm_model: str | None = None,
        utility_llm_effort: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        return rf.resolve_utility_llm_config(
            main_resolved=main_resolved,
            main_resolution_meta=main_meta,
            reviewflow_config_path=cfg,
            utility_llm_preset=utility_llm_preset,
            utility_llm_model=utility_llm_model,
            utility_llm_effort=utility_llm_effort,
        )

    def test_utility_model_config_loads_without_changing_main_llm(self) -> None:
        base = self._write_base_config()
        cfg = ROOT / ".tmp_test_utility_llm_load.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[llm]",
                        'default_preset = "main_codex"',
                        "",
                        "[llm.utility]",
                        'preset = "utility_codex"',
                        'model = "gpt-5.4"',
                        'reasoning_effort = "low"',
                        "",
                        "[llm_presets.main_codex]",
                        'preset = "codex-cli"',
                        'model = "gpt-5.4"',
                        'reasoning_effort = "high"',
                        "",
                        "[llm_presets.utility_codex]",
                        'preset = "codex-cli"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            main_resolved, main_meta = self._resolve_main(base=base, cfg=cfg)
            utility_resolved, utility_meta = self._resolve_utility(
                main_resolved=main_resolved,
                main_meta=main_meta,
                cfg=cfg,
            )
            self.assertEqual(main_resolved["provider"], "codex")
            self.assertEqual(main_resolved["model"], "gpt-5.4")
            self.assertEqual(main_resolved["reasoning_effort"], "high")
            self.assertEqual(utility_resolved["provider"], "codex")
            self.assertEqual(utility_resolved["model"], "gpt-5.4")
            self.assertEqual(utility_resolved["reasoning_effort"], "low")
            self.assertEqual(utility_meta["resolved"]["preset_source"], "cure.toml")
        finally:
            base.unlink(missing_ok=True)
            cfg.unlink(missing_ok=True)

    def test_utility_model_inherits_main_llm_when_unset(self) -> None:
        base = self._write_base_config(".tmp_test_utility_inherit_base.toml")
        cfg = ROOT / ".tmp_test_utility_inherit.toml"
        try:
            cfg.write_text("", encoding="utf-8")
            main_resolved, main_meta = self._resolve_main(
                base=base,
                cfg=cfg,
                cli_preset="codex-cli",
                cli_model="gpt-5.4",
                cli_effort="medium",
            )
            utility_resolved, utility_meta = self._resolve_utility(
                main_resolved=main_resolved,
                main_meta=main_meta,
                cfg=cfg,
            )
            self.assertEqual(utility_resolved["provider"], main_resolved["provider"])
            self.assertEqual(utility_resolved["model"], main_resolved["model"])
            self.assertEqual(utility_resolved["reasoning_effort"], main_resolved["reasoning_effort"])
            self.assertEqual(utility_meta["resolved"]["preset_source"], "inherited")
            self.assertEqual(utility_meta["resolved"]["model_source"], "inherited")
            self.assertEqual(utility_meta["resolved"]["reasoning_effort_source"], "inherited")
        finally:
            base.unlink(missing_ok=True)

    def test_utility_model_caller_override_wins_for_utility_stage_only(self) -> None:
        base = self._write_base_config(".tmp_test_utility_override_base.toml")
        cfg = ROOT / ".tmp_test_utility_override.toml"
        try:
            cfg.write_text("[llm.utility]\nmodel = \"toml-utility-model\"\nreasoning_effort = \"low\"\n", encoding="utf-8")
            main_resolved, main_meta = self._resolve_main(
                base=base,
                cfg=cfg,
                cli_preset="codex-cli",
                cli_model="main-model",
                cli_effort="high",
            )
            utility_resolved, utility_meta = self._resolve_utility(
                main_resolved=main_resolved,
                main_meta=main_meta,
                cfg=cfg,
                utility_llm_model="caller-model",
            )
            self.assertEqual(main_resolved["model"], "main-model")
            self.assertEqual(utility_resolved["model"], "caller-model")
            self.assertEqual(utility_resolved["reasoning_effort"], "low")
            self.assertEqual(utility_meta["resolved"]["model_source"], "caller_override")
            self.assertEqual(utility_meta["resolved"]["reasoning_effort_source"], "cure.toml")
        finally:
            base.unlink(missing_ok=True)
            cfg.unlink(missing_ok=True)

    def test_utility_model_resolution_preserves_source_metadata(self) -> None:
        base = self._write_base_config(".tmp_test_utility_source_base.toml")
        cfg = ROOT / ".tmp_test_utility_source.toml"
        try:
            cfg.write_text("[llm.utility]\nmodel = \"utility-model\"\n", encoding="utf-8")
            main_resolved, main_meta = self._resolve_main(
                base=base,
                cfg=cfg,
                cli_preset="codex-cli",
                cli_model="main-model",
                cli_effort="high",
            )
            _, utility_meta = self._resolve_utility(
                main_resolved=main_resolved,
                main_meta=main_meta,
                cfg=cfg,
                utility_llm_effort="medium",
            )
            self.assertEqual(utility_meta["resolved"]["preset_source"], "inherited")
            self.assertEqual(utility_meta["resolved"]["model_source"], "cure.toml")
            self.assertEqual(utility_meta["resolved"]["reasoning_effort_source"], "caller_override")
            self.assertTrue(utility_meta["resolved"]["preset_inherited"])
            self.assertFalse(utility_meta["resolved"]["model_inherited"])
        finally:
            base.unlink(missing_ok=True)
            cfg.unlink(missing_ok=True)

    def test_invalid_utility_model_config_fails_fast(self) -> None:
        base = self._write_base_config(".tmp_test_utility_invalid_base.toml")
        cfg = ROOT / ".tmp_test_utility_invalid.toml"
        try:
            cfg.write_text("[llm.utility]\nreasoning_effort = \"not-real\"\n", encoding="utf-8")
            main_resolved, main_meta = self._resolve_main(
                base=base,
                cfg=cfg,
                cli_preset="codex-cli",
                cli_model="main-model",
                cli_effort="high",
            )
            with self.assertRaisesRegex(rf.ReviewflowError, "utility llm reasoning_effort"):
                self._resolve_utility(main_resolved=main_resolved, main_meta=main_meta, cfg=cfg)
        finally:
            base.unlink(missing_ok=True)
            cfg.unlink(missing_ok=True)

    def test_utility_model_rejects_codex_api_key_with_shared_validator(self) -> None:
        base = self._write_base_config(".tmp_test_utility_provider_base.toml")
        cfg = ROOT / ".tmp_test_utility_provider.toml"
        try:
            cfg.write_text(
                "\n".join(
                    [
                        "[llm.utility]",
                        'preset = "utility_llm"',
                        'model = "x-ai/grok-4.1-fast"',
                        'reasoning_effort = "medium"',
                        "",
                        "[llm_presets.utility_llm]",
                        'preset = "codex-cli"',
                        'api_key = "test-codex-key"',  # pragma: allowlist secret
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            main_resolved, main_meta = self._resolve_main(
                base=base,
                cfg=cfg,
                cli_preset="codex-cli",
                cli_model="gpt-5.4",
                cli_effort="high",
            )
            with self.assertRaisesRegex(rf.ReviewflowError, "Codex.*api_key"):
                self._resolve_utility(
                    main_resolved=main_resolved,
                    main_meta=main_meta,
                    cfg=cfg,
                )
        finally:
            base.unlink(missing_ok=True)
            cfg.unlink(missing_ok=True)

    def test_saved_interactive_llm_rejects_ignored_controls_instead_of_reusing_raw_meta(self) -> None:
        base = self._write_base_config(".tmp_test_saved_interactive_reject_base.toml")
        try:
            for field, value in (
                ("api_key", "test-codex-key"),  # pragma: allowlist secret
                ("text_verbosity", "high"),
                ("max_output_tokens", 9000),
            ):
                with self.subTest(field=field), self.assertRaisesRegex(
                    rf.ReviewflowError, rf"Codex.*{field}"
                ):
                    rf.resolve_saved_interactive_llm_config(
                        saved_llm_meta={
                            "preset": "codex-cli",
                            "provider": "codex",
                            "model": "gpt-5.4",
                            "reasoning_effort": "medium",
                            field: value,
                        },
                        saved_resolution_meta={},
                        base_codex_config_path=base,
                        reviewflow_config_path=None,
                    )
        finally:
            base.unlink(missing_ok=True)

    def test_saved_interactive_llm_resolves_legitimate_model_and_effort(self) -> None:
        base = self._write_base_config(".tmp_test_saved_interactive_positive_base.toml")
        try:
            resolved, resolution_meta = rf.resolve_saved_interactive_llm_config(
                saved_llm_meta={
                    "preset": "codex-cli",
                    "provider": "codex",
                    "model": "gpt-5.4",
                    "reasoning_effort": "high",
                },
                saved_resolution_meta={},
                base_codex_config_path=base,
                reviewflow_config_path=None,
            )
            self.assertEqual(resolved["model"], "gpt-5.4")
            self.assertEqual(resolved["reasoning_effort"], "high")
            self.assertEqual(resolution_meta["resolved"]["model_source"], "session_reuse")
            self.assertEqual(
                resolution_meta["resolved"]["reasoning_effort_source"], "session_reuse"
            )
        finally:
            base.unlink(missing_ok=True)

    def test_utility_model_fields_resolve_override_then_toml_then_inherited_default(self) -> None:
        base = self._write_base_config(".tmp_test_utility_precedence_base.toml")
        cfg = ROOT / ".tmp_test_utility_precedence.toml"
        try:
            cfg.write_text("[llm.utility]\nmodel = \"toml-model\"\nreasoning_effort = \"low\"\n", encoding="utf-8")
            main_resolved, main_meta = self._resolve_main(
                base=base,
                cfg=cfg,
                cli_preset="codex-cli",
                cli_model="main-model",
                cli_effort="high",
            )
            utility_resolved, utility_meta = self._resolve_utility(
                main_resolved=main_resolved,
                main_meta=main_meta,
                cfg=cfg,
                utility_llm_model="override-model",
            )
            self.assertEqual(utility_resolved["preset"], main_resolved["preset"])
            self.assertEqual(utility_resolved["model"], "override-model")
            self.assertEqual(utility_resolved["reasoning_effort"], "low")
            self.assertEqual(utility_meta["resolved"]["preset_source"], "inherited")
            self.assertEqual(utility_meta["resolved"]["model_source"], "caller_override")
            self.assertEqual(utility_meta["resolved"]["reasoning_effort_source"], "cure.toml")
        finally:
            base.unlink(missing_ok=True)
            cfg.unlink(missing_ok=True)

    def test_partial_utility_model_toml_inherits_missing_fields(self) -> None:
        base = self._write_base_config(".tmp_test_utility_partial_toml_base.toml")
        cfg = ROOT / ".tmp_test_utility_partial_toml.toml"
        try:
            cfg.write_text("[llm.utility]\nreasoning_effort = \"low\"\n", encoding="utf-8")
            main_resolved, main_meta = self._resolve_main(
                base=base,
                cfg=cfg,
                cli_preset="codex-cli",
                cli_model="main-model",
                cli_effort="high",
            )
            utility_resolved, utility_meta = self._resolve_utility(
                main_resolved=main_resolved,
                main_meta=main_meta,
                cfg=cfg,
            )
            self.assertEqual(utility_resolved["model"], "main-model")
            self.assertEqual(utility_resolved["reasoning_effort"], "low")
            self.assertEqual(utility_meta["resolved"]["model_source"], "inherited")
            self.assertEqual(utility_meta["resolved"]["reasoning_effort_source"], "cure.toml")
        finally:
            base.unlink(missing_ok=True)
            cfg.unlink(missing_ok=True)

    def test_partial_utility_model_caller_override_inherits_missing_fields(self) -> None:
        base = self._write_base_config(".tmp_test_utility_partial_override_base.toml")
        cfg = ROOT / ".tmp_test_utility_partial_override.toml"
        try:
            cfg.write_text("", encoding="utf-8")
            main_resolved, main_meta = self._resolve_main(
                base=base,
                cfg=cfg,
                cli_preset="codex-cli",
                cli_model="main-model",
                cli_effort="high",
            )
            utility_resolved, utility_meta = self._resolve_utility(
                main_resolved=main_resolved,
                main_meta=main_meta,
                cfg=cfg,
                utility_llm_effort="medium",
            )
            self.assertEqual(utility_resolved["model"], "main-model")
            self.assertEqual(utility_resolved["reasoning_effort"], "medium")
            self.assertEqual(utility_meta["resolved"]["model_source"], "inherited")
            self.assertEqual(utility_meta["resolved"]["reasoning_effort_source"], "caller_override")
        finally:
            base.unlink(missing_ok=True)

    def test_partial_utility_model_invalid_final_combination_fails_fast(self) -> None:
        base = self._write_base_config(".tmp_test_utility_invalid_combo_base.toml")
        cfg = ROOT / ".tmp_test_utility_invalid_combo.toml"
        try:
            cfg.write_text(
                "[llm.utility]\npreset = \"utility_codex\"\n\n[llm_presets.utility_codex]\npreset = \"codex-cli\"\n",
                encoding="utf-8",
            )
            main_resolved, main_meta = self._resolve_main(
                base=base,
                cfg=cfg,
                cli_preset="codex-cli",
                cli_model="main-model",
                cli_effort="xhigh",
            )
            with self.assertRaisesRegex(rf.ReviewflowError, "utility llm reasoning_effort"):
                self._resolve_utility(main_resolved=main_resolved, main_meta=main_meta, cfg=cfg)
        finally:
            base.unlink(missing_ok=True)
            cfg.unlink(missing_ok=True)


class AgentRuntimeConfigTests(unittest.TestCase):
    def test_load_reviewflow_llm_config_rejects_gemini_backend_block(self) -> None:
        cfg = ROOT / ".tmp_test_reviewflow_agent_runtime.toml"
        try:
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
            with self.assertRaises(rf.ReviewflowError) as ctx:
                rf.load_reviewflow_llm_config(config_path=cfg)
            self.assertIn("Gemini support was removed from CURe", str(ctx.exception))
            self.assertIn("[agent_runtime.gemini]", str(ctx.exception))
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
            "capabilities": {"supports_resume": provider == "codex"},
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

    def _runtime_args(self, *, dry_run_chunkhound: bool = False) -> argparse.Namespace:
        return argparse.Namespace(dry_run_chunkhound=dry_run_chunkhound)

    def test_prepare_review_agent_runtime_builds_codex_runtime(self) -> None:
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
                    },
                    clear=False,
                ),
            ):
                runtime = rf.prepare_review_agent_runtime(
                    args=self._runtime_args(),
                    resolved=self._llm_resolved("codex"),
                    resolution_meta=self._llm_resolution_meta(),
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
                self.assertEqual(runtime["provider"], "codex")
                self.assertIsNone(runtime["sandbox_mode"])
                self.assertIsNone(runtime["approval_policy"])
                self.assertTrue(runtime["dangerously_bypass_approvals_and_sandbox"])
                self.assertEqual(runtime["env"]["CODEX_THREAD_ID"], "thread-123")
                self.assertEqual(runtime["env"]["CODEX_HOME"], "/tmp/codex-home")
                self.assertIn("CODEX_THREAD_ID", runtime["metadata"]["env_keys"])
                self.assertNotIn("--sandbox", runtime["codex_flags"])
                helper_path = Path(str(runtime["staged_paths"]["chunkhound_helper"]))
                self.assertTrue(helper_path.is_file())
                self.assertEqual(helper_path.parent, work / "bin")
                self.assertEqual(runtime["env"]["CURE_CHUNKHOUND_HELPER"], str(helper_path))
                self.assertEqual(runtime["env"]["PYTHONSAFEPATH"], "1")
                self.assertEqual(runtime["metadata"]["chunkhound_access_mode"], "cli_helper_daemon")
                helper_text = helper_path.read_text(encoding="utf-8")
                self.assertIn("chunkhound mcp", helper_text)
                self.assertIn("code_research", helper_text)
                self.assertIn("DaemonDiscovery", helper_text)
                self.assertIn("chunkhound_runtime_python", helper_text)
                self.assertFalse(
                    any(
                        entry.startswith("mcp_servers.chunkhound.")
                        for entry in runtime["codex_config_overrides"]
                    )
                )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_prepare_review_agent_runtime_stages_rf_jira_outside_repo_checkout(self) -> None:
        """The read-only review flow must never write the rf-jira helper into the repo checkout."""
        root = ROOT / ".tmp_test_agent_runtime_rf_jira_outside_repo"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo = root / "repo"
            session = root / "session"
            work = session / "work"
            repo.mkdir(parents=True, exist_ok=True)
            work.mkdir(parents=True, exist_ok=True)
            pre_existing = repo / "rf-jira"
            pre_existing.write_text("pre-existing user file\n", encoding="utf-8")

            with mock.patch.object(shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"):
                runtime = rf.prepare_review_agent_runtime(
                    args=self._runtime_args(),
                    resolved=self._llm_resolved("codex"),
                    resolution_meta=self._llm_resolution_meta(),
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
            helper = Path(str(runtime["staged_paths"]["rf_jira"]))
            self.assertTrue(helper.is_file())
            self.assertTrue(os.access(helper, os.X_OK))
            auth_root = Path(str(runtime["staged_paths"]["auth_staging_dir"]))
            self.assertEqual(helper.parent, auth_root)
            self.assertNotEqual(helper, work / "rf-jira")
            # The repo checkout must be untouched: the pre-existing rf-jira file
            # survives verbatim and nothing new was written into it.
            self.assertEqual(pre_existing.read_text(encoding="utf-8"), "pre-existing user file\n")
            self.assertEqual(list(repo.iterdir()), [pre_existing])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_rf_jira_helper_preserves_pre_staged_netrc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            helper = rf.write_rf_jira(dst_dir=root)
            staged_netrc = root / "staged.netrc"
            staged_netrc.write_text("machine staged.invalid login staged\n", encoding="utf-8")
            real_home = root / "real-home"
            real_home.mkdir()
            real_netrc = real_home / ".netrc"
            real_netrc.write_text("machine real.invalid login real\n", encoding="utf-8")
            real_netrc.chmod(0)
            jira_config = root / "jira.yml"
            jira_config.write_text("server: https://jira.invalid\n", encoding="utf-8")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            jira = bin_dir / "jira"
            jira.write_text("#!/bin/sh\nprintf '%s\\n' \"$NETRC\"\n", encoding="utf-8")
            jira.chmod(0o755)

            bootstrap = f"""
import pwd
import runpy
import sys
class _Pw:
    pw_dir = {str(real_home)!r}
pwd.getpwuid = lambda uid: _Pw()
sys.argv = [{str(helper)!r}, "issue", "list"]
runpy.run_path({str(helper)!r}, run_name="__main__")
"""
            env = dict(os.environ)
            env.update(
                {
                    "JIRA_CONFIG_FILE": str(jira_config),
                    "NETRC": str(staged_netrc),
                    "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
                }
            )
            result = subprocess.run(
                [sys.executable, "-c", bootstrap],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(staged_netrc))

    def test_prepare_review_agent_runtime_uses_private_staging_dir_per_run(self) -> None:
        """Concurrent runs must never share credential directories: the prepare
        steps rmtree an existing destination before copying, so a shared dir
        would let one run delete another run's live credentials."""
        root = ROOT / ".tmp_test_agent_runtime_private_staging"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo = root / "repo"
            session = root / "session"
            work = session / "work"
            repo.mkdir(parents=True, exist_ok=True)
            work.mkdir(parents=True, exist_ok=True)

            def fake_prepare_gh(*, dst_root: Path) -> Path:
                # Mirrors the real prepare step: rmtree an existing destination,
                # then copy fresh files into it.
                dst = dst_root / "gh_config"
                if dst.exists():
                    shutil.rmtree(dst)
                dst_root.mkdir(parents=True, exist_ok=True)
                dst.mkdir(parents=True, exist_ok=True)
                (dst / "hosts.yml").write_text("github.com:\n  user: test\n", encoding="utf-8")
                return dst

            with (
                mock.patch.object(shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"),
                mock.patch("cure_llm.prepare_gh_config_for_codex", side_effect=fake_prepare_gh),
            ):
                r1 = rf.prepare_review_agent_runtime(
                    args=self._runtime_args(),
                    resolved=self._llm_resolved("codex"),
                    resolution_meta=self._llm_resolution_meta(),
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
                r2 = rf.prepare_review_agent_runtime(
                    args=self._runtime_args(),
                    resolved=self._llm_resolved("codex"),
                    resolution_meta=self._llm_resolution_meta(),
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
            p1 = Path(str(r1["staged_paths"]["gh_config_dir"]))
            p2 = Path(str(r2["staged_paths"]["gh_config_dir"]))
            rf_jira1 = Path(str(r1["staged_paths"]["rf_jira"]))
            rf_jira2 = Path(str(r2["staged_paths"]["rf_jira"]))
            # Each run stages into its own private dir under work_dir.
            self.assertNotEqual(p1.parent, p2.parent)
            self.assertEqual(p1.parent.parent, work)
            self.assertTrue(p1.parent.name.startswith(".auth-"))
            # Run 1's credentials survive run 2's staging untouched.
            self.assertTrue((p1 / "hosts.yml").is_file())
            self.assertTrue((p2 / "hosts.yml").is_file())
            self.assertNotEqual(rf_jira1, rf_jira2)
            self.assertEqual(rf_jira1.parent, p1.parent)
            self.assertEqual(rf_jira2.parent, p2.parent)
            self.assertTrue(rf_jira1.is_file())
            self.assertTrue(rf_jira2.is_file())
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_stage_review_auth_support_cleans_private_dir_on_partial_failure(self) -> None:
        """A copy that fails halfway must not leave sensitive files behind: the
        private staging dir is registered before copying, so cleanup removes
        the whole dir even when no per-key destination was recorded yet."""
        root = ROOT / ".tmp_test_stage_auth_partial_failure"
        try:
            shutil.rmtree(root, ignore_errors=True)
            work = root / "work"
            work.mkdir(parents=True, exist_ok=True)

            def fake_fail(*, dst_root: Path) -> Path:
                (dst_root / "partial").mkdir(parents=True, exist_ok=True)
                (dst_root / "partial" / "secret.yml").write_text("leaked", encoding="utf-8")
                raise OSError("copy failed halfway")

            with mock.patch("cure.prepare_gh_config_for_codex", side_effect=fake_fail):
                with self.assertRaises(OSError):
                    rf._stage_review_auth_support(work_dir=work, env={})
            self.assertEqual(list(work.iterdir()), [])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_cure_llm_stage_review_auth_support_cleans_private_dir_on_partial_failure(self) -> None:
        root = ROOT / ".tmp_test_cure_llm_stage_auth_partial_failure"
        try:
            shutil.rmtree(root, ignore_errors=True)
            work = root / "work"
            work.mkdir(parents=True, exist_ok=True)

            def fake_fail(*, dst_root: Path) -> Path:
                partial = dst_root / "partial"
                partial.mkdir(parents=True, exist_ok=True)
                (partial / "secret.yml").write_text("leaked", encoding="utf-8")
                raise OSError("copy failed halfway")

            with mock.patch.object(cure_llm, "prepare_gh_config_for_codex", side_effect=fake_fail):
                with self.assertRaisesRegex(OSError, "copy failed halfway"):
                    cure_llm._stage_review_auth_support(work_dir=work, env={})
            self.assertEqual(list(work.iterdir()), [])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_readonly_runtime_denies_mutation_and_keeps_repo_pristine(self) -> None:
        """Read-only protection end to end: a fake codex sandbox that enforces
        read-only receives the read-only flags from CURe's real exec path, an
        attempted write is denied, the denial surfaces as a run failure, and
        the repo checkout stays pristine."""
        import run as run_module
        import cure_runtime

        root = ROOT / ".tmp_test_readonly_denial"
        try:
            shutil.rmtree(root, ignore_errors=True)
            fake_bin = root / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            repo = root / "repo"
            session = root / "session"
            work = session / "work"
            logs_dir = work / "logs"
            repo.mkdir(parents=True, exist_ok=True)
            logs_dir.mkdir(parents=True, exist_ok=True)
            (repo / "existing.txt").write_text("keep me", encoding="utf-8")
            (root / "home").mkdir(parents=True, exist_ok=True)
            codex_home = root / "codex-home"
            codex_home.mkdir(parents=True, exist_ok=True)

            fake = fake_bin / "codex"
            fake.write_text(
                r"""#!/usr/bin/env python3
from __future__ import annotations
import json
import sys

argv = sys.argv[1:]
sandbox_ok = False
for index, token in enumerate(argv):
    if token == "--sandbox" and index + 1 < len(argv) and argv[index + 1] == "read-only":
        sandbox_ok = True
    if token == "-c" and index + 1 < len(argv) and argv[index + 1] == 'sandbox_mode="read-only"':
        sandbox_ok = True
if not sandbox_ok:
    print("fake-codex: read-only sandbox flag missing", file=sys.stderr)
    raise SystemExit(2)
prompt = argv[-1] if argv else ""
if "probe.txt" in prompt:
    print(
        json.dumps(
            {
                "type": "item.completed",
                "item": {"type": "error", "message": "EACCES: probe.txt: write denied by read-only sandbox"},
            }
        ),
        flush=True,
    )
    print("EACCES: probe.txt: write denied by read-only sandbox", file=sys.stderr)
    raise SystemExit(1)
print(
    json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "**Summary**: ok"}}),
    flush=True,
)
raise SystemExit(0)
""",
                encoding="utf-8",
            )
            fake.chmod(0o755)

            base_env = dict(os.environ)
            base_env["PATH"] = f"{fake_bin}{os.pathsep}{base_env.get('PATH', '')}"
            base_env["CODEX_HOME"] = str(codex_home)
            base_env["HOME"] = str(root / "home")

            meta_path = session / "meta.json"
            progress = rf.SessionProgress(meta_path, quiet=True)
            progress.init(
                {
                    "session_id": "readonly-denial",
                    "status": "running",
                    "phase": "codex_review",
                    "paths": {
                        "repo_dir": str(repo),
                        "work_dir": str(work),
                        "logs_dir": str(logs_dir),
                        "review_md": str(work / "review.md"),
                    },
                    "logs": {
                        "cure": str(logs_dir / "cure.log"),
                        "codex": str(logs_dir / "codex.log"),
                    },
                }
            )

            resolved = dict(cure_runtime.builtin_llm_presets()["codex-cli"])
            resolved["preset"] = "codex-cli"
            resolved["command"] = str(fake)
            resolution_meta: dict[str, Any] = {
                "base_codex_config": {},
                "reviewflow_defaults": {},
                "resolved": {},
            }
            runtime = rf.prepare_review_agent_runtime(
                args=argparse.Namespace(),
                resolved=resolved,
                resolution_meta=resolution_meta,
                repo_dir=repo,
                session_dir=session,
                work_dir=work,
                base_env=base_env,
                chunkhound_config_path=work / "chunkhound.json",
                chunkhound_db_path=work / ".chunkhound.db",
                chunkhound_cwd=work / "chunkhound",
                enable_mcp=False,
                interactive=False,
                paths=rf.DEFAULT_PATHS,
            )
            runtime["sandbox_mode"] = "read-only"
            runtime["dangerously_bypass_approvals_and_sandbox"] = False

            with self.assertRaises(run_module.ReviewflowSubprocessError) as ctx:
                rf.run_llm_exec(
                    repo_dir=repo,
                    session_dir=session,
                    resolved=resolved,
                    resolution_meta=resolution_meta,
                    output_path=work / "review.md",
                    prompt="Please create a file named probe.txt in the repo directory.",
                    env=runtime["env"],
                    stream=True,
                    progress=progress,
                    runtime_policy=runtime,
                    sandbox_mode="read-only",
                )
            self.assertIn("EACCES", str(ctx.exception.stderr))
            self.assertIn("--sandbox", ctx.exception.cmd)
            self.assertIn("read-only", ctx.exception.cmd)
            # The attempted mutation was denied: nothing was written into the
            # repo checkout.
            self.assertFalse((repo / "probe.txt").exists())
            self.assertEqual(sorted(p.name for p in repo.iterdir()), ["existing.txt"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_prepare_review_agent_runtime_injects_codex_model_context_window_override(self) -> None:
        root = ROOT / ".tmp_test_agent_runtime_codex_context_window"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo = root / "repo"
            session = root / "session"
            work = session / "work"
            repo.mkdir(parents=True, exist_ok=True)
            work.mkdir(parents=True, exist_ok=True)

            with mock.patch.object(shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"):
                runtime = rf.prepare_review_agent_runtime(
                    args=self._runtime_args(),
                    resolved=self._llm_resolved("codex"),
                    resolution_meta=self._llm_resolution_meta(),
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

            self.assertIn("model_context_window=1000000", runtime["codex_config_overrides"])
            self.assertIn("model_context_window=1000000", runtime["metadata"]["codex_config_overrides"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_prepare_review_agent_runtime_marks_chunkhound_dry_run_in_env_and_metadata(self) -> None:
        root = ROOT / ".tmp_test_agent_runtime_chunkhound_dry_run"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo = root / "repo"
            session = root / "session"
            work = session / "work"
            repo.mkdir(parents=True, exist_ok=True)
            work.mkdir(parents=True, exist_ok=True)

            with mock.patch.object(shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"):
                runtime = rf.prepare_review_agent_runtime(
                    args=self._runtime_args(dry_run_chunkhound=True),
                    resolved=self._llm_resolved("codex"),
                    resolution_meta=self._llm_resolution_meta(),
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

            self.assertEqual(runtime["env"]["CURE_CHUNKHOUND_DRY_RUN"], "1")
            self.assertTrue(runtime["metadata"]["chunkhound_dry_run"])
            self.assertTrue(runtime["config"]["chunkhound_dry_run"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_prepare_review_agent_runtime_rejects_removed_gemini_provider(self) -> None:
        root = ROOT / ".tmp_test_agent_runtime_gemini"
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
                        args=self._runtime_args(),
                        resolved=self._llm_resolved("gemini"),
                        resolution_meta=self._llm_resolution_meta(),
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
                self.assertIn("Gemini support was removed from CURe", str(ctx.exception))
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
                side_effect=lambda name: None if name == "codex" else f"/usr/bin/{name}",
            ):
                with self.assertRaises(rf.ReviewflowError) as ctx:
                    rf.prepare_review_agent_runtime(
                        args=self._runtime_args(),
                        resolved=self._llm_resolved("codex"),
                        resolution_meta=self._llm_resolution_meta(),
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
            self.assertIn("codex", str(ctx.exception))
            self.assertIn("not found", str(ctx.exception))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_prepare_review_agent_runtime_cleans_credentials_when_provider_binary_missing(self) -> None:
        root = ROOT / ".tmp_test_agent_runtime_missing_binary_credentials"
        try:
            shutil.rmtree(root, ignore_errors=True)
            repo = root / "repo"
            session = root / "session"
            work = session / "work"
            gh_dir = root / "gh"
            jira_dir = root / "jira"
            jira_file = jira_dir / ".config.yml"
            fake_home = root / "home"
            repo.mkdir(parents=True, exist_ok=True)
            work.mkdir(parents=True, exist_ok=True)
            gh_dir.mkdir(parents=True, exist_ok=True)
            jira_dir.mkdir(parents=True, exist_ok=True)
            fake_home.mkdir(parents=True, exist_ok=True)
            (gh_dir / "hosts.yml").write_text("github.com:\n  oauth_token: secret\n", encoding="utf-8")
            jira_file.write_text("token: secret\n", encoding="utf-8")
            (fake_home / ".netrc").write_text("machine example.test password secret\n", encoding="utf-8")

            with (
                mock.patch.dict(
                    os.environ,
                    {"GH_CONFIG_DIR": str(gh_dir), "JIRA_CONFIG_FILE": str(jira_file)},
                ),
                mock.patch.object(cure, "real_user_home_dir", return_value=fake_home),
                mock.patch.object(
                    shutil,
                    "which",
                    side_effect=lambda name: None if name == "codex" else f"/usr/bin/{name}",
                ),
            ):
                with self.assertRaises(rf.ReviewflowError):
                    rf.prepare_review_agent_runtime(
                        args=self._runtime_args(),
                        resolved=self._llm_resolved("codex"),
                        resolution_meta=self._llm_resolution_meta(),
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

            self.assertEqual(list(work.glob(".auth-*")), [])
            self.assertFalse((work / "rf-jira").exists())
            self.assertEqual(list(work.iterdir()), [])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_build_http_response_request_is_removed(self) -> None:
        self.assertFalse(hasattr(rf, "build_http_response_request"))
        self.assertFalse(hasattr(rf, "run_http_response_exec"))
        self.assertNotIn("openai-responses", rf.BUILTIN_LLM_PRESET_IDS)
        self.assertNotIn("openrouter-responses", rf.BUILTIN_LLM_PRESET_IDS)
