from __future__ import annotations

import io
import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest import mock

import cure as rf

from cure_subsequent_review.contracts import (
    EvidencePolicy,
    ModuleStatus,
    PriorReviewCorpus,
    PriorReviewCorpusEntry,
    SubsequentReviewModule,
)
from cure_subsequent_review.control_plane import SubsequentReviewConfig, run_subsequent_review_intake
from cure_subsequent_review.finding_identity import reconcile_findings
from cure_subsequent_review.github_history import collect_pr_discussion
from cure_subsequent_review.prior_corpus import build_prior_review_corpus
from cure_subsequent_review.prior_findings import extract_prior_findings


@dataclass(frozen=True)
class PR:
    host: str = "github.com"
    owner: str = "example"
    repo: str = "demo"
    number: int = 9999


@dataclass(frozen=True)
class Session:
    session_id: str
    session_dir: Path
    review_md_path: Path
    created_at: str | None = None
    completed_at: str | None = None
    review_head_sha: str | None = None


class SubsequentReviewTests(unittest.TestCase):
    def test_contracts_expose_story_modules_and_two_policy_modes(self) -> None:
        self.assertEqual(len(SubsequentReviewModule), 13)
        self.assertEqual([item.value for item in EvidencePolicy], ["trusted", "untrusted"])
        self.assertEqual(ModuleStatus.DISABLED.value, "disabled")
        self.assertIn(SubsequentReviewModule.PRIOR_FINDING_EXTRACTOR, set(SubsequentReviewModule))

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

    def test_github_history_collects_events_thread_markers_and_degraded_statuses(self) -> None:
        pr = PR()

        def fetch(path: str) -> Any:
            if path.endswith("/issues/9999/comments"):
                return [{"id": 101, "html_url": "u1", "user": {"login": "cure-bot"}, "body": "CURe review", "created_at": "2026-01-01T00:00:00Z"}]
            if path.endswith("/pulls/9999/reviews"):
                return [{"id": 201, "html_url": "u2", "user": {"login": "maintainer"}, "body": "review body", "state": "COMMENTED", "submitted_at": "2026-01-02T00:00:00Z"}]
            if path.endswith("/pulls/9999/comments"):
                return [{"id": 301, "html_url": "u3", "user": {"login": "dev"}, "body": "line note", "path": "a.py", "line": 7, "thread_state": "unresolved", "created_at": "2026-01-03T00:00:00Z"}]
            raise AssertionError(path)

        artifact = collect_pr_discussion(pr=pr, fetch_json=fetch)
        self.assertEqual(artifact.status, ModuleStatus.SUCCESS)
        self.assertEqual(len(artifact.events), 3)
        self.assertEqual({event.kind for event in artifact.events}, {"issue_comment", "review", "review_comment"})
        self.assertIn("unresolved", [event.thread_state for event in artifact.events])
        self.assertTrue(all(marker.complete for marker in artifact.pagination))

        unavailable = collect_pr_discussion(pr=pr, fetch_json=lambda _path: (_ for _ in ()).throw(RuntimeError("boom")))
        self.assertEqual(unavailable.status, ModuleStatus.DEGRADED)
        self.assertIn("discussion_unavailable", unavailable.status_reasons)

        incomplete = collect_pr_discussion(
            pr=pr,
            fetch_json=lambda _path: {"items": [], "complete": False, "status": "discussion_incomplete"},
        )
        self.assertEqual(incomplete.status, ModuleStatus.DEGRADED)
        self.assertIn("discussion_incomplete", incomplete.status_reasons)

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
        self.assertEqual(ledger.status, ModuleStatus.SUCCESS)
        by_id = {item.finding_id: item for item in ledger.findings}
        self.assertEqual(set(by_id), {f"A-{index:02d}" for index in range(1, 6)} | {f"B-{index:02d}" for index in range(1, 7)})
        self.assertEqual(by_id["A-01"].severity, "medium")
        self.assertEqual(by_id["A-01"].section, "Business / Product Assessment")
        self.assertIn("cure.py:4120-4167", by_id["A-01"].source_evidence_snippets[0])
        self.assertEqual(by_id["B-03"].supersedes, ("A-03",))

        degraded_entry = fixture["raw_prior_reviews"]["parse_degraded_prior_artifact_md"]
        degraded = extract_prior_findings(
            corpus=PriorReviewCorpus(
                status=ModuleStatus.SUCCESS,
                entries=(
                    PriorReviewCorpusEntry(
                        entry_id="fixture:degraded",
                        source_type="fixture",
                        provenance={},
                        body=degraded_entry,
                        reviewed_head="sha-degraded",
                    ),
                ),
            )
        )
        self.assertEqual(degraded.status, ModuleStatus.DEGRADED)
        self.assertIn("CURE-99", {item.finding_id for item in degraded.findings})
        self.assertTrue(any(status.get("finding_id") == "CURE-100" for status in degraded.artifact_statuses))

    def test_public_fallback_list_payload_marks_discussion_incomplete(self) -> None:
        auth_error = rf.ReviewflowSubprocessError(
            cmd=["gh", "api"],
            cwd=None,
            exit_code=1,
            stdout="",
            stderr="not authenticated; please run gh auth login",
        )
        with mock.patch.object(rf, "run_cmd", side_effect=auth_error), mock.patch.object(
            rf,
            "_github_public_api_payload",
            return_value=[{"id": 101, "user": {"login": "cure-bot"}, "body": "CURe review", "created_at": "2026-01-01T00:00:00Z"}],
        ):
            discussion = collect_pr_discussion(
                pr=PR(),
                fetch_json=lambda path: rf.gh_api_list(host="github.com", path=path, allow_public_fallback=True),
            )
        self.assertEqual(discussion.status, ModuleStatus.DEGRADED)
        self.assertIn("discussion_incomplete", discussion.status_reasons)
        self.assertTrue(discussion.events)
        self.assertTrue(all(not marker.complete for marker in discussion.pagination))

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

    def test_if_reviewed_historical_list_exits_before_sandbox_or_intake(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review = root / "prior.md"
            review.write_text("prior review\n", encoding="utf-8")
            completed = rf.HistoricalReviewSession(
                session_id="prior",
                session_dir=root,
                review_md_path=review,
                created_at="2026-01-01T00:00:00Z",
                completed_at="2026-01-02T00:00:00Z",
                verdicts=None,
            )
            args = rf.build_parser().parse_args(
                ["pr", "https://github.com/acme/repo/pull/14", "--if-reviewed", "list", "--subsequent-review"]
            )
            paths = rf.ReviewflowPaths(sandbox_root=root / "sandboxes", cache_root=root / "cache")
            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[completed]), mock.patch(
                "cure_subsequent_review.control_plane.run_subsequent_review_intake",
                side_effect=AssertionError("intake must not run for historical exits"),
            ), mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                self.assertEqual(rf._pr_flow_impl(args, paths=paths), 0)
            self.assertIn("prior", stdout.getvalue())
            self.assertFalse(paths.sandbox_root.exists())

    def test_if_reviewed_new_runs_intake_after_work_dir_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review = root / "prior.md"
            review.write_text("### A-01: Prior\nSeverity: high\nSection: Security\nEvidence: app.py:1\n", encoding="utf-8")
            completed = rf.HistoricalReviewSession(
                session_id="prior",
                session_dir=root,
                review_md_path=review,
                created_at="2026-01-01T00:00:00Z",
                completed_at="2026-01-02T00:00:00Z",
                verdicts=None,
            )
            args = rf.build_parser().parse_args(
                [
                    "pr",
                    "https://github.com/acme/repo/pull/14",
                    "--if-reviewed",
                    "new",
                    "--subsequent-review",
                    "--no-index",
                    "--no-review",
                ]
            )
            paths = rf.ReviewflowPaths(sandbox_root=root / "sandboxes", cache_root=root / "cache")
            intake_calls: list[Path] = []

            def fake_intake(**kwargs: Any) -> Any:
                work_dir = kwargs["work_dir"]
                self.assertTrue(work_dir.is_dir())
                intake_calls.append(work_dir)
                return type("Result", (), {"manifest_path": work_dir / "subsequent" / "run_manifest.json", "artifact_dir": work_dir / "subsequent"})()

            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[completed]), mock.patch.object(
                rf,
                "load_chunkhound_runtime_config",
                return_value=({}, {"chunkhound": {}}, {}),
            ), mock.patch.object(rf, "materialize_chunkhound_env_config"), mock.patch(
                "cure_subsequent_review.control_plane.run_subsequent_review_intake",
                side_effect=fake_intake,
            ):
                with self.assertRaises(rf.ReviewflowError):
                    rf._pr_flow_impl(args, paths=paths)
            self.assertEqual(len(intake_calls), 1)
            self.assertEqual(intake_calls[0].name, "work")

    def test_control_plane_writes_story_01_artifacts_only_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pr = PR()
            disabled = run_subsequent_review_intake(
                pr=pr,
                work_dir=root / "disabled" / "work",
                completed_sessions=[],
                config=SubsequentReviewConfig(enabled=False),
                fetch_json=lambda _path: [],
            )
            self.assertIsNone(disabled)
            self.assertFalse((root / "disabled" / "work" / "subsequent").exists())

            review = root / "review.md"
            review.write_text("### A-01: Prior finding\nSeverity: high\nSection: Security\nEvidence: app.py:1 example\n", encoding="utf-8")
            session = Session("s1", root, review, review_head_sha="abc123")
            summaries: list[str] = []
            result = run_subsequent_review_intake(
                pr=pr,
                work_dir=root / "enabled" / "work",
                completed_sessions=[session],
                config=SubsequentReviewConfig(enabled=True, evidence_policy=EvidencePolicy.UNTRUSTED),
                fetch_json=lambda _path: [],
                summary_writer=summaries.append,
            )
            self.assertIsNotNone(result)
            subsequent = root / "enabled" / "work" / "subsequent"
            self.assertTrue((subsequent / "run_manifest.json").is_file())
            self.assertTrue((subsequent / "pr_discussion.json").is_file())
            self.assertTrue((subsequent / "prior_review_corpus.json").is_file())
            self.assertTrue((subsequent / "prior_findings.json").is_file())
            self.assertTrue((subsequent / "reconciled_findings.json").is_file())
            manifest = json.loads((subsequent / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["evidence_policy"], "untrusted")
            self.assertEqual(manifest["modules"]["source_truth_verifier"]["status"], "disabled")
            self.assertIn("prior completed sessions: 1", summaries[0])


if __name__ == "__main__":
    unittest.main()
