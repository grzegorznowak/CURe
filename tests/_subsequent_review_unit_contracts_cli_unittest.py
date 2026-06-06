# ruff: noqa: F403, F405
from _subsequent_review_test_support import *  # noqa: F401, F403


class SubsequentReviewContractsCliTests(SubsequentReviewTestCase):
    def test_contracts_expose_story_modules_and_two_policy_modes(self) -> None:
        self.assertEqual(len(SubsequentReviewModule), 13)
        self.assertEqual([item.value for item in EvidencePolicy], ["trusted", "untrusted"])
        self.assertEqual(ModuleStatus.DISABLED.value, "disabled")
        self.assertIn(SubsequentReviewModule.PRIOR_FINDING_EXTRACTOR, set(SubsequentReviewModule))

    def test_parser_defaults_to_auto_opt_out_disables_and_force_enable_is_rejected(self) -> None:
        parser = rf.build_parser()
        default_args = parser.parse_args(["pr", "https://github.com/acme/repo/pull/14"])
        self.assertEqual(rf._subsequent_review_command_mode(default_args), "auto")
        self.assertEqual(rf._subsequent_review_evidence_policy(default_args), "untrusted")

        disabled_args = parser.parse_args(["pr", "https://github.com/acme/repo/pull/14", "--no-subsequent-review"])
        self.assertEqual(rf._subsequent_review_command_mode(disabled_args), "disabled")

        with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr, self.assertRaises(SystemExit):
            parser.parse_args(["pr", "https://github.com/acme/repo/pull/14", "--subsequent-review"])
        self.assertIn("omit --subsequent-review", stderr.getvalue())
        self.assertIn("--no-subsequent-review", stderr.getvalue())

    def test_command_catalog_documents_auto_default_and_opt_out_without_force_enable(self) -> None:
        payload = rf.build_commands_catalog_payload()
        pr_entry = next(command for command in payload["commands"] if command["name"] == "pr")
        text = json.dumps(pr_entry)
        self.assertIn("automatic", text)
        self.assertIn("--no-subsequent-review", text)
        self.assertNotIn("--subsequent-review ", text)

    def test_fixture_pack_contains_story_01_raw_ids_without_later_dispositions(self) -> None:
        root = Path(__file__).parent / "fixtures" / "subsequent_review"
        fixture = json.loads((root / "simulation_raw.json").read_text(encoding="utf-8"))
        self.assertEqual(fixture["pr"]["number"], 9999)
        self.assertEqual({item["id"] for item in fixture["prior_review_a"]}, {"A-01", "A-02", "A-03", "A-04", "A-05"})
        self.assertEqual({item["id"] for item in fixture["prior_review_b"]}, {"B-01", "B-02", "B-03", "B-04", "B-05", "B-06"})
        self.assertEqual({item["id"] for item in fixture["discussion"]}, {f"C-{index:02d}" for index in range(1, 11)})
        self.assertTrue(all(item.get("body") for item in fixture["discussion"]))
        self.assertEqual({item["id"] for item in fixture["source_facts"]}, {f"S-{index:02d}" for index in range(1, 9)})
        self.assertTrue(all(item.get("raw") for item in fixture["source_facts"]))
        self.assertIn("- [A-01][Medium]", fixture["raw_prior_reviews"]["session_a_review_md"])
        self.assertIn("  Evidence:", fixture["raw_prior_reviews"]["session_b_review_md"])
        self.assertIn("parse_degraded_prior_artifact_md", fixture["raw_prior_reviews"])
        self.assertIn("discussion_incomplete", fixture["degraded_inputs"])
        self.assertNotIn("dispositions", fixture)


__all__ = ["SubsequentReviewContractsCliTests"]
