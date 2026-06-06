# ruff: noqa: F403, F405
from _subsequent_review_test_support import *  # noqa: F401, F403


class SubsequentReviewReconciliationTests(SubsequentReviewTestCase):
    def test_corpus_extraction_and_reconciliation_preserve_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_a = root / "review-a.md"
            review_b = root / "review-b.md"
            review_a.write_text("""# Review A\n\n## Findings\n\n### A-01: SQL injection risk\nSeverity: high\nSection: Security\nEvidence: app/auth.py:42 uses string SQL\n\n### A-02: Missing cache bound\nSeverity: medium\nSection: Reliability\nEvidence: cache.py:10 unbounded map\n""", encoding="utf-8")
            review_b.write_text("""# Review B\n\n### B-01: SQL injection risk\nSeverity: high\nSection: Security\nEvidence: app/auth.py:42 still builds SQL\nSupersedes: A-01\n\n### B-02: Partial malformed finding\nSection: Reliability\nEvidence: worker.py:9 parseable but missing severity\n""", encoding="utf-8")
            sessions = [
                Session("A", root, review_a, review_head_sha="sha-a"),
                Session("B", root, review_b, review_head_sha="sha-b"),
            ]
            discussion = collect_pr_discussion(
                pr=PR(),
                fetch_json=lambda path: [
                    {"id": 900, "html_url": "comment-url", "user": {"login": "cure-bot"}, "body": "CURe Review\n### CURE-01: Comment finding\nSeverity: low\nSection: Docs\nEvidence: README.md:3 typo", "created_at": "2026-01-04T00:00:00Z"}
                ] if path.endswith("/issues/9999/comments") else [],
            )

            corpus = build_prior_review_corpus(pr=PR(), sessions=sessions, discussion=discussion)
            self.assertEqual(corpus.status, ModuleStatus.SUCCESS)
            self.assertEqual(len(corpus.entries), 3)
            self.assertTrue(any(entry.source_type == "pr_comment" for entry in corpus.entries))

            findings = extract_prior_findings(corpus=corpus)
            self.assertEqual(findings.status, ModuleStatus.DEGRADED)
            self.assertIn("parse_degraded", findings.status_reasons)
            self.assertIn("A-01", {item.finding_id for item in findings.findings})
            self.assertIn("B-01", {item.finding_id for item in findings.findings})
            self.assertTrue(any(item.reviewed_head == "sha-a" for item in findings.findings))

            ledger = reconcile_findings(findings=findings.findings)
            grouped_ids = [set(group.finding_ids) for group in ledger.groups]
            self.assertTrue(any({"A-01", "B-01"}.issubset(ids) for ids in grouped_ids))
            self.assertTrue(any("A-01" in group.supersedes for group in ledger.groups))

    def test_reconciliation_namespaces_duplicate_ids_ambiguous_and_transitive_supersedes(self) -> None:
        ledger = reconcile_findings(
            findings=(
                self._finding_candidate(
                    entry_id="session-a",
                    finding_id="CURE-01",
                    title="Cache grows forever",
                    section="Business / Product Assessment",
                    evidence="session-a.py:1",
                ),
                self._finding_candidate(
                    entry_id="session-b",
                    finding_id="CURE-01",
                    title="SQL injection risk",
                    section="Business / Product Assessment",
                    evidence="session-b.py:1",
                ),
                self._finding_candidate(
                    entry_id="session-c",
                    finding_id="CURE-02",
                    title="SQL injection still possible",
                    section="Business / Product Assessment",
                    evidence="session-c.py:1",
                    supersedes=("CURE-01",),
                ),
                self._finding_candidate(
                    entry_id="session-d",
                    finding_id="CURE-03",
                    title="SQL injection remains exploitable",
                    section="Business / Product Assessment",
                    evidence="session-d.py:1",
                    supersedes=("CURE-02",),
                ),
            )
        )

        self.assertEqual(ledger.status, ModuleStatus.DEGRADED)
        self.assertIn("ambiguous_supersedes", ledger.status_reasons)
        payload = ledger.to_json()
        all_local = [item for group in payload["groups"] for item in group["local_findings"]]
        duplicate_origins = [item["origin_key"] for item in all_local if item["finding_id"] == "CURE-01"]
        self.assertEqual(set(duplicate_origins), {"session-a:CURE-01", "session-b:CURE-01"})
        self.assertTrue(
            any(
                marker["source_origin_key"] == "session-c:CURE-02"
                and marker["target_display_id"] == "CURE-01"
                and set(marker["target_origin_keys"]) == {"session-a:CURE-01", "session-b:CURE-01"}
                for group in payload["groups"]
                for marker in group["ambiguous_supersedes"]
            )
        )
        self.assertTrue(
            any(
                {"CURE-02", "CURE-03"}.issubset(set(group["finding_ids"]))
                and any(edge["target_origin_key"] == "session-c:CURE-02" for edge in group["supersedes_edges"])
                for group in payload["groups"]
            )
        )

    def test_reconciliation_prefers_superseding_canonical_and_serializes_local_details(self) -> None:
        older = self._finding_candidate(
            entry_id="session-a",
            finding_id="A-01",
            title="Zulu vulnerability",
            severity="high",
            section="Security",
            evidence="app/auth.py:42",
            reviewed_head="sha-older",
        )
        newer = self._finding_candidate(
            entry_id="session-b",
            finding_id="A-02",
            title="Alpha vulnerability",
            severity="medium",
            section="Reliability",
            evidence="app/auth.py:99",
            reviewed_head="sha-newer",
            supersedes=("A-01",),
        )

        ledger = reconcile_findings(findings=(older, newer))

        self.assertEqual(ledger.groups[0].canonical_id, "A-02")
        local_by_id = {item["finding_id"]: item for item in ledger.to_json()["groups"][0]["local_findings"]}
        self.assertEqual(local_by_id["A-02"]["severity"], "medium")
        self.assertEqual(local_by_id["A-02"]["section"], "Reliability")
        self.assertEqual(local_by_id["A-02"]["title"], "Alpha vulnerability")
        self.assertEqual(local_by_id["A-02"]["source_evidence_snippets"], ["app/auth.py:99"])

    def test_reconciliation_degrades_missing_supersedes_target(self) -> None:
        finding = self._finding_candidate(
            finding_id="CURE-02",
            title="Missing superseded target",
            supersedes=("CURE-01",),
        )

        ledger = reconcile_findings(findings=(finding,))

        self.assertEqual(ledger.status, ModuleStatus.DEGRADED)
        self.assertIn("supersedes_target_not_found", ledger.status_reasons)
        edges = [edge for group in ledger.to_json()["groups"] for edge in group["supersedes_edges"]]
        self.assertTrue(any(edge.get("target_display_id") == "CURE-01" and edge.get("status") == "target_not_found" for edge in edges))

    def test_reconciliation_keeps_same_title_findings_with_distinct_evidence_separate(self) -> None:
        ledger = reconcile_findings(
            findings=(
                self._finding_candidate(
                    entry_id="session-a",
                    finding_id="A-01",
                    title="Shared title",
                    severity="high",
                    section="Security",
                    evidence="app/auth.py:42",
                ),
                self._finding_candidate(
                    entry_id="session-b",
                    finding_id="B-01",
                    title="Shared title",
                    severity="high",
                    section="Security",
                    evidence="app/billing.py:77",
                ),
            )
        )

        grouped_ids = [set(group.finding_ids) for group in ledger.groups]
        self.assertEqual(grouped_ids, [{"A-01"}, {"B-01"}])

    def test_reconciliation_preserves_same_entry_duplicate_finding_ids(self) -> None:
        ledger = reconcile_findings(
            findings=(
                self._finding_candidate(finding_id="CURE-01", title="Cache grows without bounds"),
                self._finding_candidate(finding_id="CURE-01", title="SQL query is constructed unsafely"),
            )
        )

        payload = ledger.to_json()
        all_local = [item for group in payload["groups"] for item in group["local_findings"]]
        self.assertEqual(ledger.status, ModuleStatus.DEGRADED)
        self.assertIn("duplicate_origin_keys", ledger.status_reasons)
        self.assertEqual(len(all_local), 2)
        self.assertEqual({item["finding_id"] for item in all_local}, {"CURE-01"})
        self.assertEqual(len({item["origin_key"] for item in all_local}), 2)
        self.assertTrue(all(item["origin_key"].startswith("session-a:CURE-01") for item in all_local))


__all__ = ["SubsequentReviewReconciliationTests"]
