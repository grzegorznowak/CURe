# ruff: noqa: F403, F405
from _subsequent_review_test_support import *  # noqa: F401, F403


class SubsequentReviewPriorFindingsTests(SubsequentReviewTestCase):
    def test_simulation_bullet_prior_reviews_extract_and_degrade_partially(self) -> None:
        root = Path(__file__).parent / "fixtures" / "subsequent_review"
        fixture = json.loads((root / "simulation_raw.json").read_text(encoding="utf-8"))
        raw = fixture["raw_prior_reviews"]
        sessions = [
            Session("simulation-a", root, root / "session-a.md", review_head_sha="sha-a"),
            Session("simulation-b", root, root / "session-b.md", review_head_sha="sha-b"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            materialized: list[Session] = []
            for session, body_key in zip(sessions, ["session_a_review_md", "session_b_review_md"], strict=True):
                review_path = tmp_root / session.review_md_path.name
                review_path.write_text(raw[body_key], encoding="utf-8")
                materialized.append(
                    Session(session.session_id, tmp_root, review_path, review_head_sha=session.review_head_sha)
                )
            corpus = build_prior_review_corpus(pr=PR(), sessions=materialized)
            ledger = extract_prior_findings(corpus=corpus)
        self.assertEqual(ledger.status, ModuleStatus.DEGRADED)
        self.assertIn("parse_degraded", ledger.status_reasons)
        by_id = {item.finding_id: item for item in ledger.findings}
        self.assertEqual(set(by_id), {f"A-{index:02d}" for index in range(1, 6)} | {"B-01", "B-03", "B-04", "B-05", "B-06"})
        self.assertEqual(by_id["A-01"].severity, "medium")
        self.assertEqual(by_id["A-01"].section, "Business / Product Assessment")
        self.assertIn("cure.py:4120-4167", by_id["A-01"].source_evidence_snippets[0])
        self.assertNotIn("B-02", by_id)
        prose_status = next(status for status in ledger.artifact_statuses if status.get("finding_id") == "B-02")
        self.assertEqual(prose_status.get("reason"), "missing_source_ref")
        self.assertIn("PR discussion says GraphQL", prose_status.get("invalid_evidence_snippets", [])[0])
        self.assertEqual(by_id["B-03"].supersedes, ("A-03",))

        degraded_entry = fixture["raw_prior_reviews"]["parse_degraded_prior_artifact_md"]
        degraded = self._extract_ledger_from_body(
            degraded_entry,
            entry_id="fixture:degraded",
            reviewed_head="sha-degraded",
        )
        self.assertEqual(degraded.status, ModuleStatus.DEGRADED)
        self.assertIn("CURE-99", {item.finding_id for item in degraded.findings})
        malformed_status = next(status for status in degraded.artifact_statuses if status.get("finding_id") == "CURE-100")
        self.assertEqual(malformed_status.get("source_type"), "fixture")
        self.assertEqual(malformed_status.get("reviewed_head"), "sha-degraded")
        self.assertIn(
            "tests/fixtures/subsequent_review/simulation_raw.json:2 missing severity",
            malformed_status.get("source_evidence_snippets", []),
        )

    def test_heading_style_prior_findings_missing_evidence_degrades_artifact(self) -> None:
        ledger = self._extract_ledger_from_body(
            """## Security

### A-01: Missing evidence
Severity: Medium
Section: Security
""",
            entry_id="fixture:missing-evidence",
            reviewed_head="sha-missing-evidence",
        )

        self.assertEqual(ledger.status, ModuleStatus.DEGRADED)
        self.assertIn("parse_degraded", ledger.status_reasons)
        self.assertEqual(ledger.findings, ())
        status = ledger.artifact_statuses[0]
        self.assertEqual(status.get("finding_id"), "A-01")
        self.assertEqual(status.get("reason"), "missing_evidence")
        self.assertEqual(status.get("source_evidence_snippets"), [])

    def test_heading_style_prior_findings_inherit_surrounding_section(self) -> None:
        ledger = self._extract_ledger_from_body(
            """## Technical Assessment

### A-01: Cache issue
Severity: Medium
Evidence: cache.py:10

## A-02: H2 cache issue
Severity: Medium
Evidence: cache.py:11

### A-03: Explicit section wins
Severity: Low
Section: Reliability
Evidence: worker.py:20
""",
            entry_id="fixture:heading-section",
            reviewed_head="sha-section",
        )

        by_id = {item.finding_id: item for item in ledger.findings}
        self.assertEqual(by_id["A-01"].section, "Technical Assessment")
        self.assertEqual(by_id["A-02"].section, "Technical Assessment")
        self.assertEqual(by_id["A-03"].section, "Reliability")

    def test_heading_style_prior_findings_degrade_non_citation_evidence_field(self) -> None:
        ledger = self._extract_ledger_from_body(
            """## Business / Product Assessment

### CURE-123: Prose memory
Severity: Low
Evidence: PR discussion says GraphQL fetching moved to CURe-123.
""",
            entry_id="fixture:prose-evidence",
            reviewed_head="sha-prose",
        )

        self.assertEqual(ledger.status, ModuleStatus.DEGRADED)
        self.assertEqual(ledger.findings, ())
        status = ledger.artifact_statuses[0]
        self.assertEqual(status.get("finding_id"), "CURE-123")
        self.assertEqual(status.get("reason"), "missing_source_ref")
        self.assertEqual(status.get("source_evidence_snippets"), [])
        self.assertEqual(status.get("invalid_evidence_snippets"), ["PR discussion says GraphQL fetching moved to CURe-123."])

    def test_prior_findings_ignore_incidental_word_colon_digits_as_source_evidence(self) -> None:
        ledger = self._extract_ledger_from_body(
            """## Technical Assessment

### A-01: Incidental token
Severity: Medium
Section: Technical Assessment
This prose mentions ratio:16 and port:443 but no source location.
""",
            entry_id="fixture:incidental-source",
            reviewed_head="sha-incidental",
        )

        self.assertEqual(ledger.status, ModuleStatus.DEGRADED)
        self.assertEqual(ledger.findings, ())
        status = ledger.artifact_statuses[0]
        self.assertEqual(status.get("finding_id"), "A-01")
        self.assertEqual(status.get("reason"), "missing_evidence")
        self.assertEqual(status.get("source_evidence_snippets"), [])

    def test_generated_review_parser_accepts_mixed_legacy_and_extensionless_sources(self) -> None:
        mixed = self._extract_ledger_from_body(
            """## Technical Assessment

### A-01: Legacy finding
Severity: Medium
Evidence: cure.py:10

**Verdict**: REQUEST CHANGES

### In Scope Issues
- Generated issue cites a root file. Sources: `LICENSE:1`

  <details open>
  <summary><b>Low</b> severity · <b>Medium</b> likelihood</summary>

  **Why:** This issue is parseable alongside legacy findings.

  </details>
""",
            entry_id="real-run:mixed-legacy-generated",
            source_type="session_review",
            reviewed_head="sha-mixed",
        )

        self.assertEqual(mixed.status, ModuleStatus.SUCCESS)
        by_id = {item.finding_id: item for item in mixed.findings}
        self.assertEqual(set(by_id), {"A-01", "CURE-001"})
        self.assertEqual(by_id["CURE-001"].source_evidence_snippets, ("LICENSE:1",))

    def test_generated_review_parser_degrades_malformed_sibling_and_ignores_clean_none(self) -> None:
        mixed = self._extract_ledger_from_body(
            """## Business / Product Assessment
**Verdict**: REQUEST CHANGES

### In Scope Issues
- Well formed generated issue. Sources: `cure.py:10`

  <details open>
  <summary><b>Medium</b> severity · <b>Medium</b> likelihood</summary>

  **Why:** This issue is parseable.

  </details>

- Malformed generated issue missing severity markup. Sources: `cure.py:20`

  <details open>
  <summary><b>Medium</b> likelihood only</summary>

  **Why:** This issue should be represented as degraded provenance.

  </details>
""",
            entry_id="real-run:mixed-generated",
            source_type="session_review",
            reviewed_head="sha-real",
            artifact_path=Path("/tmp/prior/review.md"),
        )

        self.assertEqual(mixed.status, ModuleStatus.DEGRADED)
        self.assertEqual([item.finding_id for item in mixed.findings], ["CURE-001"])
        self.assertIn("parse_degraded", mixed.status_reasons)
        self.assertTrue(
            any(
                status.get("entry_id") == "real-run:mixed-generated"
                and status.get("status") == "parse_degraded"
                and status.get("reason") == "missing_generated_severity"
                and "Malformed generated issue" in str(status.get("title"))
                for status in mixed.artifact_statuses
            )
        )

        missing_sources = self._extract_ledger_from_body(
            """## Technical Assessment
**Verdict**: REQUEST CHANGES

### In Scope Issues
- Generated issue with severity but no sources.

  <details open>
  <summary><b>High</b> severity · <b>Medium</b> likelihood</summary>

  **Why:** This issue has no source references.

  </details>
""",
            entry_id="real-run:missing-sources",
            source_type="session_review",
            reviewed_head="sha-missing-sources",
            artifact_path=Path("/tmp/prior/missing-sources.md"),
        )
        self.assertEqual(missing_sources.status, ModuleStatus.DEGRADED)
        self.assertEqual(missing_sources.findings, ())
        missing_source_status = next(
            status for status in missing_sources.artifact_statuses if status.get("reason") == "missing_generated_sources"
        )
        self.assertEqual(missing_source_status.get("entry_id"), "real-run:missing-sources")
        self.assertEqual(missing_source_status.get("reviewed_head"), "sha-missing-sources")
        self.assertEqual(missing_source_status.get("artifact_path"), "/tmp/prior/missing-sources.md")
        self.assertIn("Generated issue with severity", str(missing_source_status.get("title")))

        clean_none = self._extract_ledger_from_body(
            """## Business / Product Assessment
**Verdict**: APPROVE

### In Scope Issues
- None.
""",
            entry_id="real-run:none-generated",
            source_type="session_review",
            reviewed_head="sha-real",
        )
        self.assertEqual(clean_none.status, ModuleStatus.SUCCESS)
        self.assertEqual(clean_none.findings, ())
        self.assertEqual(clean_none.artifact_statuses, ())

    def test_real_generated_review_markdown_extracts_in_scope_issues(self) -> None:
        root = Path(__file__).parent / "fixtures" / "subsequent_review"
        fixture = json.loads((root / "story_01_regression_goldens.json").read_text(encoding="utf-8"))["a22_generated_review"]
        review_body = (root / fixture["valid_review_md_fixture"]).read_text(encoding="utf-8")
        ledger = self._extract_ledger_from_body(
            review_body,
            entry_id="real-run:review-md",
            source_type="session_review",
            reviewed_head="sha-real",
            artifact_path=Path("/tmp/prior/review.md"),
        )

        self.assertEqual(ledger.status, ModuleStatus.SUCCESS)
        self.assertEqual(len(ledger.findings), fixture["expected_valid_finding_count"])
        finding = ledger.findings[0]
        self.assertEqual(finding.finding_id, "CURE-001")
        self.assertEqual(finding.severity, "medium")
        self.assertEqual(finding.section, "Business / Product Assessment")
        self.assertIn("generated review evidence", finding.title)
        self.assertIn("cure.py:7456", finding.source_evidence_snippets)
        self.assertEqual(finding.provenance.artifact_path, "/tmp/prior/review.md")

    def test_generated_review_parser_rejects_incidental_sources_tokens(self) -> None:
        root = Path(__file__).parent / "fixtures" / "subsequent_review"
        fixture = json.loads((root / "story_01_regression_goldens.json").read_text(encoding="utf-8"))["a22_generated_review"]
        review_body = (root / fixture["invalid_incidental_sources_md"]).read_text(encoding="utf-8")
        ledger = self._extract_ledger_from_body(
            review_body,
            entry_id="real-run:incidental-generated-sources",
            source_type="session_review",
            reviewed_head="sha-real",
            artifact_path=Path("/tmp/prior/review.md"),
        )

        self.assertEqual(ledger.status, ModuleStatus.DEGRADED)
        self.assertEqual(ledger.findings, ())
        status = next(status for status in ledger.artifact_statuses if status.get("reason") == fixture["expected_invalid_reason"])
        self.assertEqual(status.get("source_evidence_snippets"), [])
        self.assertIn("infrastructure numbers", str(status.get("title")))


__all__ = ["SubsequentReviewPriorFindingsTests"]
