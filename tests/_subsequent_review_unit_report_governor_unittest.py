# ruff: noqa: F403, F405
from _subsequent_review_test_support import *  # noqa: F401, F403


class SubsequentReviewReportGovernorTests(SubsequentReviewTestCase):
    def _write_governor_inputs(self, artifact_dir: Path, *, brief: str) -> Path:
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "governor_brief.md").write_text(brief, encoding="utf-8")
        manifest_path = artifact_dir / "run_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "modules": {
                        "report_governor": {
                            "status": "success",
                            "artifact_path": str(artifact_dir / "governor_brief.md"),
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        return manifest_path

    def test_post_review_sanitization_audits_nonempty_brief_and_records_json_result(self) -> None:
        from cure_subsequent_review.runtime import audit_review_report_after_review

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "work" / "subsequent"
            manifest_path = self._write_governor_inputs(
                artifact_dir,
                brief="### Still Open\n- D-0002 — 🟡 MEDIUM A-02: Retry gap.\n",
            )
            review_path = Path(tmp) / "review.md"
            review_path.write_text("# Review\n\nA-02 remains a retry concern.\n", encoding="utf-8")
            prompts: list[str] = []

            def fake_auditor(prompt: str) -> str:
                prompts.append(prompt)
                return json.dumps(
                    {
                        "awareness": "demonstrated",
                        "judgment": "The final review explicitly carries forward A-02.",
                        "evidence": ["A-02 remains a retry concern"],
                    }
                )

            record = audit_review_report_after_review(
                artifact_dir=artifact_dir,
                review_path=review_path,
                governor_mode="strict",
                auditor=fake_auditor,
                manifest_path=manifest_path,
            )

            self.assertEqual(record.module.value, "report_governor")
            self.assertEqual(record.status.value, "success")
            self.assertEqual(len(prompts), 1)
            self.assertIn("Does this review demonstrate awareness of the prior review context?", prompts[0])
            self.assertIn("### Still Open", prompts[0])
            self.assertIn("A-02 remains a retry concern", prompts[0])
            result = json.loads((artifact_dir / "report_governor_result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["awareness"], "demonstrated")
            self.assertEqual(result["judgment"], "The final review explicitly carries forward A-02.")
            self.assertEqual(result["evidence"], ["A-02 remains a retry concern"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["modules"]["report_governor"]["status"], "success")
            self.assertEqual(
                manifest["modules"]["report_governor"]["artifact_path"],
                str(artifact_dir / "report_governor_result.json"),
            )

    def test_governor_brief_requires_prior_review_disposition_map_for_every_da_row(self) -> None:
        from cure_subsequent_review.runtime import build_governor_brief

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "work" / "subsequent"
            artifact_dir.mkdir(parents=True)
            (artifact_dir / "disposition_ledger.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "success",
                        "status_reasons": [],
                        "dispositions": [
                            {
                                "row_id": "DA-0001",
                                "group_id": "G-0001",
                                "finding_ids": ["A-01"],
                                "action": "confirm_resolved",
                                "source_verification_row_id": "SV-0001",
                            },
                            {
                                "row_id": "DA-0002",
                                "group_id": "G-0002",
                                "finding_ids": ["A-02"],
                                "action": "re_report",
                                "source_verification_row_id": "SV-0002",
                            },
                            {
                                "row_id": "DA-0006",
                                "group_id": "G-0006",
                                "finding_ids": ["CURE-001"],
                                "action": "move_out_of_scope",
                                "source_verification_row_id": "SV-0006",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            brief = build_governor_brief(artifact_dir=artifact_dir)

            self.assertIn("Prior Review Disposition Map", brief)
            self.assertIn("DA-0001: confirmed-resolved", brief)
            self.assertIn("DA-0002: carried-forward/re_report", brief)
            self.assertIn("DA-0006: out-of-scope", brief)
            self.assertNotIn("DA-0006: carried-forward/re_report", brief)
            self.assertIn("confirmed-resolved | carried-forward/re_report | degraded | out-of-scope | contradicted-with-evidence", brief)

    def test_post_review_disposition_map_gaps_degrade_without_blocking(self) -> None:
        from cure_subsequent_review.runtime import audit_review_report_after_review

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "work" / "subsequent"
            manifest_path = self._write_governor_inputs(
                artifact_dir,
                brief="### Prior Review Disposition Map (required final output)\n- DA-0001: confirmed-resolved\n- DA-0002: carried-forward/re_report\n",
            )
            (artifact_dir / "disposition_ledger.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "success",
                        "dispositions": [
                            {"row_id": "DA-0001", "action": "confirm_resolved"},
                            {"row_id": "DA-0002", "action": "re_report"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            review_path = Path(tmp) / "review.md"
            review_path.write_text(
                "# Review\n\n## Prior Review Disposition Map\n- DA-0001: carried-forward/re_report\n",
                encoding="utf-8",
            )

            record = audit_review_report_after_review(
                artifact_dir=artifact_dir,
                review_path=review_path,
                governor_mode="strict",
                auditor=lambda _prompt: json.dumps(
                    {"awareness": "partial", "judgment": "only one DA row mentioned", "evidence": ["DA-0001"]}
                ),
                manifest_path=manifest_path,
            )

            self.assertEqual(record.status.value, "degraded")
            result = json.loads((artifact_dir / "report_governor_result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "degraded")
            self.assertEqual(result["awareness"], "partial")
            self.assertIn("missing_disposition_map_rows:DA-0002", result["warnings"])
            self.assertIn("contradicted_disposition_map_rows:DA-0001", result["warnings"])
            self.assertEqual(json.loads(manifest_path.read_text(encoding="utf-8"))["modules"]["report_governor"]["status"], "degraded")

    def test_post_review_sanitization_skips_when_brief_empty_or_governor_off(self) -> None:
        from cure_subsequent_review.runtime import audit_review_report_after_review

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "work" / "subsequent"
            manifest_path = self._write_governor_inputs(artifact_dir, brief="\n")
            review_path = Path(tmp) / "review.md"
            review_path.write_text("# Review\n", encoding="utf-8")
            calls: list[str] = []

            record = audit_review_report_after_review(
                artifact_dir=artifact_dir,
                review_path=review_path,
                governor_mode="strict",
                auditor=calls.append,
                manifest_path=manifest_path,
            )

            self.assertEqual(record.status.value, "disabled")
            self.assertEqual(record.reasons, ("empty_governor_brief",))
            self.assertEqual(calls, [])
            self.assertFalse((artifact_dir / "report_governor_result.json").exists())

            off_record = audit_review_report_after_review(
                artifact_dir=artifact_dir,
                review_path=review_path,
                governor_mode="off",
                auditor=calls.append,
                manifest_path=manifest_path,
            )
            self.assertEqual(off_record.status.value, "disabled")
            self.assertEqual(off_record.reasons, ("governor_mode_off",))
            self.assertEqual(calls, [])

    def test_post_review_sanitization_is_warn_only_when_auditor_fails(self) -> None:
        from cure_subsequent_review.runtime import audit_review_report_after_review

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "work" / "subsequent"
            manifest_path = self._write_governor_inputs(artifact_dir, brief="### Still Open\n- D-0002.\n")
            review_path = Path(tmp) / "review.md"
            review_path.write_text("# Review\n", encoding="utf-8")

            def failing_auditor(_prompt: str) -> str:
                raise RuntimeError("model unavailable")

            record = audit_review_report_after_review(
                artifact_dir=artifact_dir,
                review_path=review_path,
                governor_mode="warn",
                auditor=failing_auditor,
                manifest_path=manifest_path,
            )

            self.assertEqual(record.status.value, "degraded")
            self.assertEqual(record.reasons, ("sanitization_auditor_failed",))
            result = json.loads((artifact_dir / "report_governor_result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "degraded")
            self.assertIn("model unavailable", result["warnings"][0])


__all__ = ["SubsequentReviewReportGovernorTests"]
