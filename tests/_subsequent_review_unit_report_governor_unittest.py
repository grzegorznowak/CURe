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
            self.assertIn("human-readable Prior Review Issue History", prompts[0])
            self.assertIn("Raw DA-* row IDs are internal provenance anchors only", prompts[0])
            self.assertIn("Reader-facing label", prompts[0])
            self.assertIn("prior review follow-up; still open after re-verification", prompts[0])
            self.assertIn("Complete DA-* row coverage remains mandatory in audit/provenance artifacts", prompts[0])
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

    def test_post_review_sanitization_demotes_plain_internal_da_section_before_audit(self) -> None:
        from cure_subsequent_review.runtime import audit_review_report_after_review

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "work" / "subsequent"
            manifest_path = self._write_governor_inputs(
                artifact_dir,
                brief=(
                    "### Prior Review Issue History (required final output)\n"
                    "- Retry gap — status: carried-forward/re_report. Reason: still open. Internal rows: DA-0001\n"
                    "### Internal DA coverage (audit only)\n"
                    "- DA-0001: carried-forward/re_report\n"
                ),
            )
            review_path = Path(tmp) / "review.md"
            review_path.write_text(
                "### Prior Review Issue History\n"
                "- Retry gap — status: carried-forward/re_report. Reason: still open.\n\n"
                "### Internal DA coverage\n"
                "- DA-0001: carried-forward/re_report\n\n"
                "### Steps taken\n- Reviewed the diff.\n",
                encoding="utf-8",
            )
            prompts: list[str] = []

            record = audit_review_report_after_review(
                artifact_dir=artifact_dir,
                review_path=review_path,
                governor_mode="strict",
                auditor=lambda prompt: prompts.append(prompt)
                or json.dumps({"awareness": "demonstrated", "judgment": "ok", "evidence": ["Retry gap"]}),
                manifest_path=manifest_path,
            )

            self.assertEqual(record.status.value, "success")
            sanitized = review_path.read_text(encoding="utf-8")
            self.assertNotIn("### Internal DA coverage\n", sanitized)
            self.assertIn("<summary>Internal DA coverage (audit/provenance only)</summary>", sanitized)
            self.assertIn("- DA-0001: carried-forward/re_report", sanitized)
            self.assertIn("<details>", prompts[0])
            result = json.loads((artifact_dir / "report_governor_result.json").read_text(encoding="utf-8"))
            self.assertNotIn("prominent_internal_da_coverage", result["warnings"])
            self.assertIn("internal_da_coverage_demoted_to_audit_details", result["warnings"])

    def test_post_review_sanitization_demotes_audit_only_internal_da_heading_before_audit(self) -> None:
        from cure_subsequent_review.runtime import audit_review_report_after_review

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "work" / "subsequent"
            manifest_path = self._write_governor_inputs(
                artifact_dir,
                brief=(
                    "### Prior Review Issue History (required final output)\n"
                    "- Retry gap — status: carried-forward/re_report. Reason: still open. Internal rows: DA-0001\n"
                    "### Internal DA coverage (audit only)\n"
                    "- DA-0001: carried-forward/re_report\n"
                ),
            )
            review_path = Path(tmp) / "review.md"
            review_path.write_text(
                "### Prior Review Issue History\n"
                "- Retry gap — status: carried-forward/re_report. Reason: still open.\n\n"
                "### Internal DA coverage (audit only)\n"
                "- DA-0001: carried-forward/re_report\n\n"
                "### Steps taken\n- Reviewed the diff.\n",
                encoding="utf-8",
            )
            prompts: list[str] = []

            record = audit_review_report_after_review(
                artifact_dir=artifact_dir,
                review_path=review_path,
                governor_mode="strict",
                auditor=lambda prompt: prompts.append(prompt)
                or json.dumps({"awareness": "demonstrated", "judgment": "ok", "evidence": ["Retry gap"]}),
                manifest_path=manifest_path,
            )

            self.assertEqual(record.status.value, "success")
            sanitized = review_path.read_text(encoding="utf-8")
            self.assertNotIn("### Internal DA coverage", sanitized)
            self.assertIn("<summary>Internal DA coverage (audit/provenance only)</summary>", sanitized)
            self.assertIn("- DA-0001: carried-forward/re_report", sanitized)
            self.assertIn("<details>", prompts[0])
            result = json.loads((artifact_dir / "report_governor_result.json").read_text(encoding="utf-8"))
            self.assertNotIn("prominent_internal_da_coverage", result["warnings"])
            self.assertIn("internal_da_coverage_demoted_to_audit_details", result["warnings"])

    def test_governor_brief_requires_human_issue_history_with_internal_da_coverage(self) -> None:
        from cure_subsequent_review.runtime import build_governor_brief

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "work" / "subsequent"
            artifact_dir.mkdir(parents=True)
            (artifact_dir / "prior_findings.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "success",
                        "findings": [
                            {"finding_id": "A-01", "title": "Retry gap", "severity": "medium"},
                            {"finding_id": "A-02", "title": "Retry gap", "severity": "medium"},
                            {"finding_id": "CURE-001", "title": "Official footer policy", "severity": "low"},
                            {
                                "finding_id": "CURE-002",
                                "title": "PR comments can be admitted as prior CURe reviews based on body text alone",
                                "severity": "medium",
                            },
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
                            {
                                "row_id": "DA-0007",
                                "group_id": "G-0007",
                                "finding_ids": ["CURE-002"],
                                "action": "re_report",
                                "source_verification_row_id": "SV-0007",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            brief = build_governor_brief(artifact_dir=artifact_dir)

            self.assertIn("Prior Review Issue History", brief)
            self.assertIn("Raw DA IDs are internal provenance anchors", brief)
            self.assertIn("- Retry gap — status: carried-forward/re_report", brief)
            self.assertIn("Reader-facing label: (prior review follow-up; still open after re-verification)", brief)
            self.assertIn("Internal rows: DA-0001, DA-0002", brief)
            self.assertEqual(brief.count("- Retry gap — status:"), 1)
            self.assertIn("- Official footer policy — status: out-of-scope", brief)
            self.assertIn(
                "- PR comments can be admitted as prior CURe reviews based on body text alone — status: carried-forward/re_report",
                brief,
            )
            self.assertIn("Internal DA coverage", brief)
            self.assertIn("DA-0006: out-of-scope", brief)
            self.assertIn("DA-0007: carried-forward/re_report", brief)
            self.assertNotIn("DA-0006: carried-forward/re_report", brief)
            self.assertIn("confirmed-resolved | carried-forward/re_report | degraded | out-of-scope | contradicted-with-evidence", brief)

    def test_post_review_disposition_map_gaps_degrade_without_blocking(self) -> None:
        from cure_subsequent_review.runtime import audit_review_report_after_review

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "work" / "subsequent"
            manifest_path = self._write_governor_inputs(
                artifact_dir,
                brief=(
                    "### Prior Review Issue History (required final output)\n"
                    "- Retry gap — status: carried-forward/re_report. Reason: still open. Internal rows: DA-0001, DA-0002\n"
                    "### Internal DA coverage (audit only)\n- DA-0001: confirmed-resolved\n- DA-0002: carried-forward/re_report\n"
                ),
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
                "### Prior Review Issue History\n"
                "- Retry gap — status: carried-forward/re_report. Reason: still open.\n\n"
                "<details>\n"
                "<summary>Internal DA coverage (audit/provenance only)</summary>\n\n"
                "- DA-0001: carried-forward/re_report\n"
                "</details>\n",
                encoding="utf-8",
            )

            record = audit_review_report_after_review(
                artifact_dir=artifact_dir,
                review_path=review_path,
                governor_mode="strict",
                auditor=lambda _prompt: json.dumps(
                    {"awareness": "demonstrated", "judgment": "issue history mentioned", "evidence": ["Retry gap"]}
                ),
                manifest_path=manifest_path,
            )

            self.assertEqual(record.status.value, "degraded")
            result = json.loads((artifact_dir / "report_governor_result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "degraded")
            self.assertEqual(result["awareness"], "demonstrated")
            self.assertIn("missing_internal_da_coverage:DA-0002", result["warnings"])
            self.assertIn("contradicted_internal_da_coverage:DA-0001:expected=confirmed-resolved:actual=carried-forward/re_report", result["warnings"])
            self.assertNotIn("missing_prior_review_issue_history", result["warnings"])
            self.assertEqual(json.loads(manifest_path.read_text(encoding="utf-8"))["modules"]["report_governor"]["status"], "degraded")

    def test_post_review_issue_history_must_be_first_and_match_brief_clusters(self) -> None:
        from cure_subsequent_review.runtime import audit_review_report_after_review

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "work" / "subsequent"
            manifest_path = self._write_governor_inputs(
                artifact_dir,
                brief=(
                    "### Prior Review Issue History (required final output)\n"
                    "- PR comments can be admitted as prior CURe reviews based on body text alone — "
                    "status: carried-forward/re_report. Reason: still open. Internal rows: DA-0007\n"
                    "- Official footer policy — status: out-of-scope. Reason: policy-approved. Internal rows: DA-0006\n"
                    "### Internal DA coverage (audit only)\n"
                    "- DA-0006: out-of-scope\n"
                    "- DA-0007: carried-forward/re_report\n"
                ),
            )
            review_path = Path(tmp) / "review.md"
            review_path.write_text(
                "### Steps taken\n- Read files\n\n"
                "### Prior Review Issue History\n"
                "- Official footer policy — status: out-of-scope. Reason: policy-approved.\n\n"
                "### Internal DA coverage\n"
                "- DA-0006: out-of-scope\n"
                "- DA-0007: carried-forward/re_report\n",
                encoding="utf-8",
            )

            record = audit_review_report_after_review(
                artifact_dir=artifact_dir,
                review_path=review_path,
                governor_mode="strict",
                auditor=lambda _prompt: json.dumps(
                    {"awareness": "demonstrated", "judgment": "mentions issue history", "evidence": ["issue history"]}
                ),
                manifest_path=manifest_path,
            )

            self.assertEqual(record.status.value, "degraded")
            result = json.loads((artifact_dir / "report_governor_result.json").read_text(encoding="utf-8"))
            self.assertIn("prior_review_issue_history_not_first", result["warnings"])
            self.assertIn(
                "missing_prior_review_issue_clusters:PR comments can be admitted as prior CURe reviews based on body text alone",
                result["warnings"],
            )

    def test_post_review_issue_history_requires_plain_english_reason_from_brief(self) -> None:
        from cure_subsequent_review.runtime import audit_review_report_after_review

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "work" / "subsequent"
            manifest_path = self._write_governor_inputs(
                artifact_dir,
                brief=(
                    "### Prior Review Issue History (required final output)\n"
                    "- Retry gap — status: carried-forward/re_report. Reason: still open after re-verification. "
                    "Internal rows: DA-0001\n"
                ),
            )
            review_path = Path(tmp) / "review.md"
            review_path.write_text(
                "### Prior Review Issue History\n"
                "- Retry gap — status: carried-forward/re_report.\n",
                encoding="utf-8",
            )

            record = audit_review_report_after_review(
                artifact_dir=artifact_dir,
                review_path=review_path,
                governor_mode="strict",
                auditor=lambda _prompt: json.dumps(
                    {"awareness": "demonstrated", "judgment": "issue history present", "evidence": ["Retry gap"]}
                ),
                manifest_path=manifest_path,
            )

            self.assertEqual(record.status.value, "degraded")
            result = json.loads((artifact_dir / "report_governor_result.json").read_text(encoding="utf-8"))
            self.assertIn("missing_prior_review_issue_history_reason:Retry gap", result["warnings"])

    def test_post_review_issue_history_title_status_reason_passes(self) -> None:
        from cure_subsequent_review.runtime import audit_review_report_after_review

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "work" / "subsequent"
            manifest_path = self._write_governor_inputs(
                artifact_dir,
                brief=(
                    "### Prior Review Issue History (required final output)\n"
                    "- Retry gap — status: carried-forward/re_report. Reason: still open after re-verification. "
                    "Internal rows: DA-0001\n"
                ),
            )
            review_path = Path(tmp) / "review.md"
            review_path.write_text(
                "### Prior Review Issue History\n"
                "- Retry gap — status: carried-forward/re_report. Reason: still open after re-verification.\n",
                encoding="utf-8",
            )

            record = audit_review_report_after_review(
                artifact_dir=artifact_dir,
                review_path=review_path,
                governor_mode="strict",
                auditor=lambda _prompt: json.dumps(
                    {"awareness": "demonstrated", "judgment": "issue history present", "evidence": ["Retry gap"]}
                ),
                manifest_path=manifest_path,
            )

            self.assertEqual(record.status.value, "success")
            result = json.loads((artifact_dir / "report_governor_result.json").read_text(encoding="utf-8"))
            self.assertNotIn("missing_prior_review_issue_history_reason:Retry gap", result["warnings"])

    def test_post_review_footer_provenance_note_missing_degrades(self) -> None:
        from cure_subsequent_review.runtime import audit_review_report_after_review

        audit_reason = (
            "Ignored remote CURe comment 4707013049: official footer belongs to PR22/session "
            "grzegorznowak-cure-pr22-20260614-110911-a3ae at sha e305f82, while this run is "
            "reviewing PR18 at sha c3f81e8, so it was not used as PR18 prior-review provenance."
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "work" / "subsequent"
            manifest_path = self._write_governor_inputs(
                artifact_dir,
                brief=(
                    "### Footer Marker Policy\n"
                    "- Story 02/FB-026 policy: official CURe footer markers are accepted as prior-review provenance "
                    "regardless of author/login only when their PR/session/head provenance is compatible with the current run; "
                    "generic/body-only CURe-looking text and foreign official footers remain rejected. Accepted official-footer "
                    "remote entries: 0; foreign official-footer ignored comments: 1; body-only/generic rejected comments: 0.\n"
                    f"- {audit_reason}\n"
                ),
            )
            review_path = Path(tmp) / "review.md"
            review_path.write_text("### Review\nNo carried-forward PR22 findings.\n", encoding="utf-8")

            record = audit_review_report_after_review(
                artifact_dir=artifact_dir,
                review_path=review_path,
                governor_mode="strict",
                auditor=lambda _prompt: json.dumps(
                    {"awareness": "demonstrated", "judgment": "mentions no foreign details", "evidence": []}
                ),
                manifest_path=manifest_path,
            )

            self.assertEqual(record.status.value, "degraded")
            result = json.loads((artifact_dir / "report_governor_result.json").read_text(encoding="utf-8"))
            self.assertIn("missing_footer_marker_policy_audit_note", result["warnings"])

    def test_post_review_footer_provenance_note_contradiction_degrades(self) -> None:
        from cure_subsequent_review.runtime import audit_review_report_after_review

        audit_reason = (
            "Ignored remote CURe comment 4707013049: official footer belongs to PR22/session "
            "grzegorznowak-cure-pr22-20260614-110911-a3ae at sha e305f82, while this run is "
            "reviewing PR18 at sha c3f81e8, so it was not used as PR18 prior-review provenance."
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "work" / "subsequent"
            manifest_path = self._write_governor_inputs(
                artifact_dir,
                brief=(
                    "### Footer Marker Policy\n"
                    "- Story 02/FB-026 policy: official CURe footer markers are accepted as prior-review provenance "
                    "regardless of author/login only when their PR/session/head provenance is compatible with the current run; "
                    "generic/body-only CURe-looking text and foreign official footers remain rejected. Accepted official-footer "
                    "remote entries: 0; foreign official-footer ignored comments: 1; body-only/generic rejected comments: 0.\n"
                    f"- {audit_reason}\n"
                ),
            )
            review_path = Path(tmp) / "review.md"
            review_path.write_text(
                "### Prior Review Provenance Audit\n"
                "- Included 1 foreign official CURe footer comment from PR22/session "
                "grzegorznowak-cure-pr22-20260614-110911-a3ae at sha e305f82 while reviewing PR18 "
                "at sha c3f81e8; the foreign findings were carried forward into this review.\n",
                encoding="utf-8",
            )

            record = audit_review_report_after_review(
                artifact_dir=artifact_dir,
                review_path=review_path,
                governor_mode="strict",
                auditor=lambda _prompt: json.dumps(
                    {"awareness": "demonstrated", "judgment": "mentions footer tokens", "evidence": ["Included 1"]}
                ),
                manifest_path=manifest_path,
            )

            self.assertEqual(record.status.value, "degraded")
            result = json.loads((artifact_dir / "report_governor_result.json").read_text(encoding="utf-8"))
            self.assertIn("contradicted_footer_marker_policy_audit_note", result["warnings"])

    def test_post_review_positive_foreign_official_footer_actions_degrade_even_when_findings_excluded(self) -> None:
        from cure_subsequent_review.runtime import audit_review_report_after_review

        audit_reason = (
            "Ignored remote CURe comment 4707013049: official footer belongs to PR22/session "
            "grzegorznowak-cure-pr22-20260614-110911-a3ae at sha e305f82, while this run is "
            "reviewing PR18 at sha c3f81e8, so it was not used as PR18 prior-review provenance."
        )
        cases = (
            "Admitted 1 foreign official CURe footer comment from PR22/session grzegorznowak-cure-pr22-20260614-110911-a3ae "
            "at sha e305f82 while reviewing PR18 at sha c3f81e8; foreign findings were excluded.",
            "Carried forward 1 foreign official CURe footer comment from PR22/session grzegorznowak-cure-pr22-20260614-110911-a3ae "
            "at sha e305f82 while reviewing PR18 at sha c3f81e8; foreign findings were excluded.",
        )
        for note in cases:
            with self.subTest(note=note), tempfile.TemporaryDirectory() as tmp:
                artifact_dir = Path(tmp) / "work" / "subsequent"
                manifest_path = self._write_governor_inputs(
                    artifact_dir,
                    brief=(
                        "### Footer Marker Policy\n"
                        "- Story 02/FB-026 policy: official CURe footer markers are accepted as prior-review provenance "
                        "regardless of author/login only when their PR/session/head provenance is compatible with the current run; "
                        "generic/body-only CURe-looking text and foreign official footers remain rejected. Accepted official-footer "
                        "remote entries: 0; foreign official-footer ignored comments: 1; body-only/generic rejected comments: 0.\n"
                        f"- {audit_reason}\n"
                    ),
                )
                review_path = Path(tmp) / "review.md"
                review_path.write_text(f"### Prior Review Provenance Audit\n- {note}\n", encoding="utf-8")

                record = audit_review_report_after_review(
                    artifact_dir=artifact_dir,
                    review_path=review_path,
                    governor_mode="strict",
                    auditor=lambda _prompt: json.dumps(
                        {"awareness": "demonstrated", "judgment": "mentions footer tokens", "evidence": ["foreign official"]}
                    ),
                    manifest_path=manifest_path,
                )

                self.assertEqual(record.status.value, "degraded")
                result = json.loads((artifact_dir / "report_governor_result.json").read_text(encoding="utf-8"))
                self.assertIn("contradicted_footer_marker_policy_audit_note", result["warnings"])

    def test_post_review_footer_provenance_note_with_negated_exclusion_phrasing_passes(self) -> None:
        from cure_subsequent_review.runtime import audit_review_report_after_review

        audit_reason = (
            "Ignored remote CURe comment 4707013049: official footer belongs to PR22/session "
            "grzegorznowak-cure-pr22-20260614-110911-a3ae at sha e305f82, while this run is "
            "reviewing PR18 at sha c3f81e8, so it was not used as PR18 prior-review provenance."
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "work" / "subsequent"
            manifest_path = self._write_governor_inputs(
                artifact_dir,
                brief=(
                    "### Footer Marker Policy\n"
                    "- Story 02/FB-026 policy: official CURe footer markers are accepted as prior-review provenance "
                    "regardless of author/login only when their PR/session/head provenance is compatible with the current run; "
                    "generic/body-only CURe-looking text and foreign official footers remain rejected. Accepted official-footer "
                    "remote entries: 0; foreign official-footer ignored comments: 1; body-only/generic rejected comments: 0.\n"
                    f"- {audit_reason}\n"
                ),
            )
            review_path = Path(tmp) / "review.md"
            review_path.write_text(
                "### Prior Review Provenance Audit\n"
                "- Ignored 1 foreign official CURe footer comment: official footer belongs to PR22/session "
                "grzegorznowak-cure-pr22-20260614-110911-a3ae at sha e305f82, while this run is reviewing PR18 "
                "at sha c3f81e8; foreign findings were not included in prior-review provenance and were not carried "
                "forward into this review.\n",
                encoding="utf-8",
            )

            record = audit_review_report_after_review(
                artifact_dir=artifact_dir,
                review_path=review_path,
                governor_mode="strict",
                auditor=lambda _prompt: json.dumps(
                    {"awareness": "demonstrated", "judgment": "mentions ignored footer", "evidence": ["Ignored 1"]}
                ),
                manifest_path=manifest_path,
            )

            self.assertEqual(record.status.value, "success")
            result = json.loads((artifact_dir / "report_governor_result.json").read_text(encoding="utf-8"))
            self.assertNotIn("missing_footer_marker_policy_audit_note", result["warnings"])
            self.assertNotIn("contradicted_footer_marker_policy_audit_note", result["warnings"])

    def test_post_review_footer_provenance_note_with_copied_policy_summary_passes(self) -> None:
        from cure_subsequent_review.runtime import audit_review_report_after_review

        audit_reason = (
            "Ignored remote CURe comment 4707013049: official footer belongs to PR22/session "
            "grzegorznowak-cure-pr22-20260614-110911-a3ae at sha e305f82, while this run is "
            "reviewing PR18 at sha c3f81e8, so it was not used as PR18 prior-review provenance."
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "work" / "subsequent"
            manifest_path = self._write_governor_inputs(
                artifact_dir,
                brief=(
                    "### Footer Marker Policy\n"
                    "- Story 02/FB-026 policy: official CURe footer markers are accepted as prior-review provenance "
                    "regardless of author/login only when their PR/session/head provenance is compatible with the current run; "
                    "generic/body-only CURe-looking text and foreign official footers remain rejected. Accepted official-footer "
                    "remote entries: 0; foreign official-footer ignored comments: 1; body-only/generic rejected comments: 0.\n"
                    f"- {audit_reason}\n"
                ),
            )
            review_path = Path(tmp) / "review.md"
            review_path.write_text(
                "### Prior Review Provenance Audit\n"
                "- Accepted official-footer remote entries: 0; foreign official-footer ignored comments: 1. "
                "Ignored 1 foreign official CURe footer comment: official footer belongs to PR22/session "
                "grzegorznowak-cure-pr22-20260614-110911-a3ae at sha e305f82, while this run is reviewing PR18 "
                "at sha c3f81e8; foreign findings were excluded from prior-review provenance and were not carried "
                "forward into this review.\n",
                encoding="utf-8",
            )

            record = audit_review_report_after_review(
                artifact_dir=artifact_dir,
                review_path=review_path,
                governor_mode="strict",
                auditor=lambda _prompt: json.dumps(
                    {"awareness": "demonstrated", "judgment": "mentions ignored footer", "evidence": ["foreign official-footer ignored comments: 1"]}
                ),
                manifest_path=manifest_path,
            )

            self.assertEqual(record.status.value, "success")
            result = json.loads((artifact_dir / "report_governor_result.json").read_text(encoding="utf-8"))
            self.assertNotIn("missing_footer_marker_policy_audit_note", result["warnings"])
            self.assertNotIn("contradicted_footer_marker_policy_audit_note", result["warnings"])

    def test_post_review_footer_provenance_note_with_copied_policy_summary_only_count_passes(self) -> None:
        from cure_subsequent_review.runtime import audit_review_report_after_review

        audit_reason = (
            "Ignored remote CURe comment 4707013049: official footer belongs to PR22/session "
            "grzegorznowak-cure-pr22-20260614-110911-a3ae at sha e305f82, while this run is "
            "reviewing PR18 at sha c3f81e8, so it was not used as PR18 prior-review provenance."
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "work" / "subsequent"
            manifest_path = self._write_governor_inputs(
                artifact_dir,
                brief=(
                    "### Footer Marker Policy\n"
                    "- Story 02/FB-026 policy: official CURe footer markers are accepted as prior-review provenance "
                    "regardless of author/login only when their PR/session/head provenance is compatible with the current run; "
                    "generic/body-only CURe-looking text and foreign official footers remain rejected. Accepted official-footer "
                    "remote entries: 0; foreign official-footer ignored comments: 1; body-only/generic rejected comments: 0.\n"
                    f"- {audit_reason}\n"
                ),
            )
            review_path = Path(tmp) / "review.md"
            review_path.write_text(
                "### Prior Review Provenance Audit\n"
                "- Accepted official-footer remote entries: 0; foreign official-footer ignored comments: 1. "
                "Official footer belongs to PR22/session grzegorznowak-cure-pr22-20260614-110911-a3ae "
                "at sha e305f82, while this run is reviewing PR18 at sha c3f81e8; foreign findings "
                "were excluded from prior-review provenance and were not carried forward into this review.\n",
                encoding="utf-8",
            )

            record = audit_review_report_after_review(
                artifact_dir=artifact_dir,
                review_path=review_path,
                governor_mode="strict",
                auditor=lambda _prompt: json.dumps(
                    {"awareness": "demonstrated", "judgment": "mentions ignored footer", "evidence": ["foreign official-footer ignored comments: 1"]}
                ),
                manifest_path=manifest_path,
            )

            self.assertEqual(record.status.value, "success")
            result = json.loads((artifact_dir / "report_governor_result.json").read_text(encoding="utf-8"))
            self.assertNotIn("missing_footer_marker_policy_audit_note", result["warnings"])
            self.assertNotIn("contradicted_footer_marker_policy_audit_note", result["warnings"])

    def test_post_review_footer_provenance_note_with_no_foreign_findings_carried_forward_passes(self) -> None:
        from cure_subsequent_review.runtime import audit_review_report_after_review

        audit_reason = (
            "Ignored remote CURe comment 4707013049: official footer belongs to PR22/session "
            "grzegorznowak-cure-pr22-20260614-110911-a3ae at sha e305f82, while this run is "
            "reviewing PR18 at sha c3f81e8, so it was not used as PR18 prior-review provenance."
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "work" / "subsequent"
            manifest_path = self._write_governor_inputs(
                artifact_dir,
                brief=(
                    "### Footer Marker Policy\n"
                    "- Story 02/FB-026 policy: official CURe footer markers are accepted as prior-review provenance "
                    "regardless of author/login only when their PR/session/head provenance is compatible with the current run; "
                    "generic/body-only CURe-looking text and foreign official footers remain rejected. Accepted official-footer "
                    "remote entries: 0; foreign official-footer ignored comments: 1; body-only/generic rejected comments: 0.\n"
                    f"- {audit_reason}\n"
                ),
            )
            review_path = Path(tmp) / "review.md"
            review_path.write_text(
                "### Prior Review Provenance Audit\n"
                "- Accepted official-footer remote entries: 0; foreign official-footer ignored comments: 1. "
                "Official footer belongs to PR22/session grzegorznowak-cure-pr22-20260614-110911-a3ae "
                "at sha e305f82, while this run is reviewing PR18 at sha c3f81e8; no foreign findings "
                "were carried forward from that foreign footer, and the foreign official footer was excluded "
                "from prior-review provenance.\n",
                encoding="utf-8",
            )

            record = audit_review_report_after_review(
                artifact_dir=artifact_dir,
                review_path=review_path,
                governor_mode="strict",
                auditor=lambda _prompt: json.dumps(
                    {
                        "awareness": "demonstrated",
                        "judgment": "mentions ignored footer",
                        "evidence": ["no foreign findings were carried forward"],
                    }
                ),
                manifest_path=manifest_path,
            )

            self.assertEqual(record.status.value, "success")
            result = json.loads((artifact_dir / "report_governor_result.json").read_text(encoding="utf-8"))
            self.assertNotIn("missing_footer_marker_policy_audit_note", result["warnings"])
            self.assertNotIn("contradicted_footer_marker_policy_audit_note", result["warnings"])

    def test_post_review_positive_foreign_findings_carried_forward_degrades(self) -> None:
        from cure_subsequent_review.runtime import audit_review_report_after_review

        audit_reason = (
            "Ignored remote CURe comment 4707013049: official footer belongs to PR22/session "
            "grzegorznowak-cure-pr22-20260614-110911-a3ae at sha e305f82, while this run is "
            "reviewing PR18 at sha c3f81e8, so it was not used as PR18 prior-review provenance."
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "work" / "subsequent"
            manifest_path = self._write_governor_inputs(
                artifact_dir,
                brief=(
                    "### Footer Marker Policy\n"
                    "- Story 02/FB-026 policy: official CURe footer markers are accepted as prior-review provenance "
                    "regardless of author/login only when their PR/session/head provenance is compatible with the current run; "
                    "generic/body-only CURe-looking text and foreign official footers remain rejected. Accepted official-footer "
                    "remote entries: 0; foreign official-footer ignored comments: 1; body-only/generic rejected comments: 0.\n"
                    f"- {audit_reason}\n"
                ),
            )
            review_path = Path(tmp) / "review.md"
            review_path.write_text(
                "### Prior Review Provenance Audit\n"
                "- Accepted official-footer remote entries: 0; foreign official-footer ignored comments: 1. "
                "Official footer belongs to PR22/session grzegorznowak-cure-pr22-20260614-110911-a3ae "
                "at sha e305f82, while this run is reviewing PR18 at sha c3f81e8; foreign findings "
                "were carried forward from that foreign footer even though the footer was excluded.\n",
                encoding="utf-8",
            )

            record = audit_review_report_after_review(
                artifact_dir=artifact_dir,
                review_path=review_path,
                governor_mode="strict",
                auditor=lambda _prompt: json.dumps(
                    {
                        "awareness": "demonstrated",
                        "judgment": "mentions carried-forward foreign finding",
                        "evidence": ["foreign findings were carried forward"],
                    }
                ),
                manifest_path=manifest_path,
            )

            self.assertEqual(record.status.value, "degraded")
            result = json.loads((artifact_dir / "report_governor_result.json").read_text(encoding="utf-8"))
            self.assertIn("contradicted_footer_marker_policy_audit_note", result["warnings"])

    def test_post_review_footer_provenance_note_with_count_and_reason_passes(self) -> None:
        from cure_subsequent_review.runtime import audit_review_report_after_review

        audit_reason = (
            "Ignored remote CURe comment 4707013049: official footer belongs to PR22/session "
            "grzegorznowak-cure-pr22-20260614-110911-a3ae at sha e305f82, while this run is "
            "reviewing PR18 at sha c3f81e8, so it was not used as PR18 prior-review provenance."
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "work" / "subsequent"
            manifest_path = self._write_governor_inputs(
                artifact_dir,
                brief=(
                    "### Footer Marker Policy\n"
                    "- Story 02/FB-026 policy: official CURe footer markers are accepted as prior-review provenance "
                    "regardless of author/login only when their PR/session/head provenance is compatible with the current run; "
                    "generic/body-only CURe-looking text and foreign official footers remain rejected. Accepted official-footer "
                    "remote entries: 0; foreign official-footer ignored comments: 1; body-only/generic rejected comments: 0.\n"
                    f"- {audit_reason}\n"
                ),
            )
            review_path = Path(tmp) / "review.md"
            review_path.write_text(
                "### Prior Review Provenance Audit\n"
                "- Ignored 1 foreign official CURe footer comment: official footer belongs to PR22/session "
                "grzegorznowak-cure-pr22-20260614-110911-a3ae at sha e305f82, while this run is reviewing PR18 "
                "at sha c3f81e8; foreign findings were excluded from prior-review provenance.\n",
                encoding="utf-8",
            )

            record = audit_review_report_after_review(
                artifact_dir=artifact_dir,
                review_path=review_path,
                governor_mode="strict",
                auditor=lambda _prompt: json.dumps(
                    {"awareness": "demonstrated", "judgment": "mentions ignored footer", "evidence": ["Ignored 1"]}
                ),
                manifest_path=manifest_path,
            )

            self.assertEqual(record.status.value, "success")
            result = json.loads((artifact_dir / "report_governor_result.json").read_text(encoding="utf-8"))
            self.assertNotIn("missing_footer_marker_policy_audit_note", result["warnings"])

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
