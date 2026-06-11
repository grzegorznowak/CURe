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
