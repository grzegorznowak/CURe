# ruff: noqa: F403, F405
from _subsequent_review_test_support import *  # noqa: F401, F403


class SubsequentReviewRuntimePackagingTests(SubsequentReviewTestCase):
    def _write_seed_runtime_artifacts(self, artifact_dir: Path) -> Path:
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "decision.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "mode": "auto",
                    "enabled": True,
                    "evidence_policy": "untrusted",
                    "reasons": ["cure_pr_discussion_found"],
                    "signal_counts": {"remote_events": 1},
                    "degraded_reasons": [],
                }
            ),
            encoding="utf-8",
        )
        (artifact_dir / "pr_discussion.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "success",
                    "status_reasons": [],
                    "events": [{"event_id": "C-01", "kind": "issue_comment", "author": "dev", "body": "fixed"}],
                    "pagination": [],
                }
            ),
            encoding="utf-8",
        )
        (artifact_dir / "prior_findings.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "success",
                    "status_reasons": [],
                    "artifact_statuses": [],
                    "findings": [
                        {"finding_id": "A-01", "severity": "high", "section": "Technical", "title": "Null crash"},
                        {"finding_id": "A-02", "severity": "medium", "section": "Technical", "title": "Retry gap"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        (artifact_dir / "source_verification.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "success",
                    "status_reasons": [],
                    "rows": [
                        {
                            "row_id": "SV-0001",
                            "group_id": "G-0001",
                            "finding_ids": ["A-01"],
                            "source_state": "resolved_from_source",
                            "current_source_citations": [{"path": "src/app.py", "start_line": 10, "summary": "guard added"}],
                            "inspected_source_refs": ["src/app.py:10"],
                            "unavailable_reasons": [],
                            "provenance": {"rationale": "fresh source"},
                        },
                        {
                            "row_id": "SV-0002",
                            "group_id": "G-0002",
                            "finding_ids": ["A-02"],
                            "source_state": "still_open",
                            "current_source_citations": [{"path": "src/retry.py", "start_line": 20, "summary": "still no retry"}],
                            "inspected_source_refs": ["src/retry.py:20"],
                            "unavailable_reasons": [],
                            "provenance": {"rationale": "fresh source"},
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        (artifact_dir / "discussion_signals.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "success",
                    "status_reasons": [],
                    "rows": [
                        {
                            "row_id": "DS-0001",
                            "event_id": "C-01",
                            "group_ids": ["G-0002"],
                            "finding_ids": ["A-02"],
                            "signal_class": "pushback",
                            "evidence_policy": "untrusted",
                            "authority": "developer",
                            "reasons": ["weak_authority"],
                            "provenance": {},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (artifact_dir / "disposition_ledger.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "success",
                    "status_reasons": [],
                    "dispositions": [
                        {
                            "row_id": "D-0001",
                            "group_id": "G-0001",
                            "finding_ids": ["A-01"],
                            "action": "confirm_resolved",
                            "source_verification_row_id": "SV-0001",
                            "discussion_signal_row_ids": [],
                            "reconciliation_group_id": "G-0001",
                            "provenance": {"rationale": "fixed in source"},
                        },
                        {
                            "row_id": "D-0002",
                            "group_id": "G-0002",
                            "finding_ids": ["A-02"],
                            "action": "re_report",
                            "source_verification_row_id": "SV-0002",
                            "discussion_signal_row_ids": ["DS-0001"],
                            "reconciliation_group_id": "G-0002",
                            "provenance": {"rationale": "still open"},
                        },
                    ],
                    "degraded_findings": [],
                }
            ),
            encoding="utf-8",
        )
        manifest_path = artifact_dir / "run_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "modules": {
                        "pr_history_collector": {"status": "success", "artifact_path": str(artifact_dir / "pr_discussion.json")},
                        "source_truth_verifier": {"status": "success", "artifact_path": str(artifact_dir / "source_verification.json")},
                        "disposition_arbiter": {"status": "success", "artifact_path": str(artifact_dir / "disposition_ledger.json")},
                    },
                }
            ),
            encoding="utf-8",
        )
        return manifest_path

    def test_pre_prompt_writes_context_package_and_governor_brief(self) -> None:
        from cure_subsequent_review.runtime import prepare_review_runtime_pre_prompt

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "work" / "subsequent"
            manifest_path = self._write_seed_runtime_artifacts(artifact_dir)
            memory_path = Path(tmp) / "pr" / "github.com" / "example" / "demo" / "9999" / "cure_memory.json"
            memory_path.parent.mkdir(parents=True)
            memory_path.write_text(json.dumps({"schema_version": 1, "findings": {"G-0001": {}}}), encoding="utf-8")

            result = prepare_review_runtime_pre_prompt(
                artifact_dir=artifact_dir,
                governor_mode="strict",
                memory_store_path=memory_path,
                manifest_path=manifest_path,
            )

            self.assertIn("### Confirmed Fixed", result.prior_review_brief)
            self.assertIn("### Still Open", result.prior_review_brief)
            self.assertIn("disposition_ledger.json#D-0002", result.prior_review_brief)
            self.assertIn("🟡 MEDIUM", result.prior_review_brief)
            self.assertIn("Authority caveat", result.prior_review_brief)
            package = json.loads((artifact_dir / "review_context_package.json").read_text(encoding="utf-8"))
            self.assertEqual(package["artifacts"]["decision"]["status"], "present")
            self.assertEqual(package["artifacts"]["cure_memory"]["status"], "present")
            self.assertTrue(package["fb_010"]["discussion_event_count_matches_decision"])
            context_md = (artifact_dir / "subsequent_review_context.md").read_text(encoding="utf-8")
            self.assertIn("review_context_package.json", context_md)
            self.assertIn("pr_history_collector: success", context_md)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["modules"]["review_context_packager"]["status"], "success")
            self.assertEqual(manifest["modules"]["report_governor"]["status"], "success")

    def test_strict_governor_fails_closed_when_citation_ledger_missing(self) -> None:
        from cure_subsequent_review.runtime import prepare_review_runtime_pre_prompt

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "missing-source" / "work" / "subsequent"
            manifest_path = self._write_seed_runtime_artifacts(artifact_dir)
            (artifact_dir / "source_verification.json").unlink()

            with self.assertRaisesRegex(ValueError, "source_verification.json"):
                prepare_review_runtime_pre_prompt(
                    artifact_dir=artifact_dir,
                    governor_mode="strict",
                    manifest_path=manifest_path,
                )

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "missing-discussion" / "work" / "subsequent"
            manifest_path = self._write_seed_runtime_artifacts(artifact_dir)
            (artifact_dir / "discussion_signals.json").unlink()

            with self.assertRaisesRegex(ValueError, "discussion_signals.json"):
                prepare_review_runtime_pre_prompt(
                    artifact_dir=artifact_dir,
                    governor_mode="strict",
                    manifest_path=manifest_path,
                )

    def test_warn_governor_continues_when_citation_ledger_missing(self) -> None:
        from cure_subsequent_review.runtime import prepare_review_runtime_pre_prompt

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "work" / "subsequent"
            manifest_path = self._write_seed_runtime_artifacts(artifact_dir)
            (artifact_dir / "source_verification.json").unlink()
            (artifact_dir / "discussion_signals.json").unlink()

            result = prepare_review_runtime_pre_prompt(
                artifact_dir=artifact_dir,
                governor_mode="warn",
                manifest_path=manifest_path,
            )

            self.assertIn("source citation unavailable", result.prior_review_brief)
            self.assertIn("Discussion: DS-0001", result.prior_review_brief)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["modules"]["report_governor"]["status"], "success")

    def test_governor_off_keeps_prior_review_brief_empty(self) -> None:
        from cure_subsequent_review.runtime import prepare_review_runtime_pre_prompt

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "work" / "subsequent"
            manifest_path = self._write_seed_runtime_artifacts(artifact_dir)

            result = prepare_review_runtime_pre_prompt(
                artifact_dir=artifact_dir,
                governor_mode="off",
                manifest_path=manifest_path,
            )

            self.assertEqual(result.prior_review_brief, "")
            self.assertFalse((artifact_dir / "governor_brief.md").exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["modules"]["review_context_packager"]["status"], "success")
            self.assertEqual(manifest["modules"]["report_governor"]["status"], "disabled")


__all__ = ["SubsequentReviewRuntimePackagingTests"]
