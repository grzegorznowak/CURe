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
    FindingProvenance,
    ModuleStatus,
    PriorFindingCandidate,
    PriorReviewCorpus,
    PriorReviewCorpusEntry,
    SubsequentReviewModule,
)
from cure_subsequent_review.control_plane import SubsequentReviewConfig, run_subsequent_review_intake
from cure_subsequent_review.decision import SubsequentReviewCommandMode, decide_subsequent_review
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

    def test_decision_service_auto_modes_and_explicit_disabled(self) -> None:
        pr = PR()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review = root / "review.md"
            review.write_text("prior\n", encoding="utf-8")
            session = Session("s1", root, review)
            local = decide_subsequent_review(
                pr=pr,
                completed_sessions=[session],
                mode=SubsequentReviewCommandMode.AUTO,
                evidence_policy=EvidencePolicy.UNTRUSTED,
                fetch_json=lambda _path: (_ for _ in ()).throw(AssertionError("remote probe not needed with local sessions")),
            )
        self.assertTrue(local.enabled)
        self.assertIn("completed_sessions_found", local.reasons)
        self.assertEqual(local.signal_counts["completed_sessions"], 1)

        remote = decide_subsequent_review(
            pr=pr,
            completed_sessions=[],
            mode=SubsequentReviewCommandMode.AUTO,
            evidence_policy=EvidencePolicy.TRUSTED,
            fetch_json=lambda path: [
                {"id": 1, "user": {"login": "cure-bot"}, "body": "CURe review", "created_at": "2026-01-01T00:00:00Z"}
            ] if path.endswith("/issues/9999/comments") else [],
        )
        self.assertTrue(remote.enabled)
        self.assertIn("cure_pr_discussion_found", remote.reasons)
        self.assertEqual(remote.signal_counts["remote_cure_markers"], 1)
        self.assertEqual(remote.evidence_policy, EvidencePolicy.TRUSTED)

        first_run = decide_subsequent_review(
            pr=pr,
            completed_sessions=[],
            mode=SubsequentReviewCommandMode.AUTO,
            evidence_policy=EvidencePolicy.UNTRUSTED,
            fetch_json=lambda path: [
                {"id": 2, "user": {"login": "human"}, "body": "looks good"}
            ] if path.endswith("/issues/9999/comments") else [],
        )
        self.assertFalse(first_run.enabled)
        self.assertIn("no_prior_review_signals", first_run.reasons)

        degraded = decide_subsequent_review(
            pr=pr,
            completed_sessions=[],
            mode=SubsequentReviewCommandMode.AUTO,
            evidence_policy=EvidencePolicy.UNTRUSTED,
            fetch_json=lambda _path: (_ for _ in ()).throw(RuntimeError("offline")),
        )
        self.assertTrue(degraded.enabled)
        self.assertIn("remote_probe_degraded", degraded.reasons)
        self.assertIn("discussion_unavailable", degraded.degraded_reasons)

        explicit = decide_subsequent_review(
            pr=pr,
            completed_sessions=[object()],
            mode=SubsequentReviewCommandMode.DISABLED,
            evidence_policy=EvidencePolicy.UNTRUSTED,
            fetch_json=lambda _path: (_ for _ in ()).throw(AssertionError("disabled mode must not probe remote")),
        )
        self.assertFalse(explicit.enabled)
        self.assertEqual(explicit.reasons, ("operator_disabled",))

    def test_decision_service_rejects_false_positive_remote_markers(self) -> None:
        pr = PR()
        cases: tuple[tuple[str, dict[str, Any], bool, str], ...] = (
            (
                "human_cure_looking_issue_comment",
                {"id": 10, "user": {"login": "human"}, "body": "CURe review found this", "created_at": "2026-01-01T00:00:00Z"},
                False,
                "no_prior_review_signals",
            ),
            (
                "missing_author_cure_looking_issue_comment",
                {"id": 11, "body": "<!-- cure --> CURe review", "created_at": "2026-01-01T00:00:00Z"},
                False,
                "no_prior_review_signals",
            ),
            (
                "resolved_thread_metadata_only",
                {"id": 12, "user": {"login": "human"}, "body": "CURe review", "resolved": True, "path": "a.py", "line": 1},
                False,
                "no_prior_review_signals",
            ),
            (
                "unresolved_thread_metadata_only",
                {"id": 13, "user": {"login": "human"}, "body": "CURe review", "resolved": False, "path": "a.py", "line": 1},
                False,
                "no_prior_review_signals",
            ),
            (
                "missing_thread_state_metadata",
                {"id": 14, "user": {"login": "human"}, "body": "CURe review", "path": "a.py", "line": 1},
                True,
                "remote_probe_degraded",
            ),
        )
        for name, payload, expected_enabled, expected_reason in cases:
            with self.subTest(name=name):
                def fetch(path: str) -> Any:
                    if path.endswith("/issues/9999/comments") and "issue_comment" in name:
                        return [payload]
                    if path.endswith("/pulls/9999/comments") and "thread" in name:
                        return [payload]
                    return []

                decision = decide_subsequent_review(
                    pr=pr,
                    completed_sessions=[],
                    mode=SubsequentReviewCommandMode.AUTO,
                    evidence_policy=EvidencePolicy.UNTRUSTED,
                    fetch_json=fetch,
                )
                self.assertEqual(decision.enabled, expected_enabled)
                self.assertEqual(decision.signal_counts["remote_cure_markers"], 0)
                self.assertNotIn("cure_pr_discussion_found", decision.reasons)
                self.assertIn(expected_reason, decision.reasons)
                if name == "missing_thread_state_metadata":
                    self.assertIn("thread_state_unavailable", decision.degraded_reasons)

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

    def test_reconciliation_namespaces_duplicate_ids_ambiguous_and_transitive_supersedes(self) -> None:
        def candidate(
            *,
            entry_id: str,
            finding_id: str,
            title: str,
            supersedes: tuple[str, ...] = (),
        ) -> PriorFindingCandidate:
            return PriorFindingCandidate(
                finding_id=finding_id,
                severity="medium",
                section="Business / Product Assessment",
                title=title,
                source_evidence_snippets=(f"{entry_id}.py:1",),
                reviewed_head=f"sha-{entry_id}",
                provenance=FindingProvenance(
                    corpus_entry_id=entry_id,
                    source_type="session_review",
                    artifact_path=f"/tmp/{entry_id}/review.md",
                    reviewed_head=f"sha-{entry_id}",
                ),
                supersedes=supersedes,
            )

        ledger = reconcile_findings(
            findings=(
                candidate(entry_id="session-a", finding_id="CURE-01", title="Cache grows forever"),
                candidate(entry_id="session-b", finding_id="CURE-01", title="SQL injection risk"),
                candidate(entry_id="session-c", finding_id="CURE-02", title="SQL injection still possible", supersedes=("CURE-01",)),
                candidate(entry_id="session-d", finding_id="CURE-03", title="SQL injection remains exploitable", supersedes=("CURE-02",)),
            )
        )

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

    def test_github_list_slurp_failure_public_fallback_preserves_cause_detail(self) -> None:
        slurp_error = rf.ReviewflowSubprocessError(
            cmd=["gh", "api", "--paginate", "--slurp"],
            cwd=None,
            exit_code=1,
            stdout="",
            stderr="unknown flag: --slurp",
        )

        def public_payload(*, path: str) -> list[dict[str, Any]]:
            return [{"id": path.rsplit("/", 1)[-1], "user": {"login": "cure-bot"}, "body": "CURe review", "created_at": "2026-01-01T00:00:00Z"}]

        with mock.patch.object(rf, "run_cmd", side_effect=slurp_error), mock.patch.object(
            rf, "_github_public_api_payload", side_effect=public_payload
        ):
            discussion = collect_pr_discussion(
                pr=PR(),
                fetch_json=lambda path: rf.gh_api_list(host="github.com", path=path, allow_public_fallback=True),
            )

        self.assertEqual(discussion.status, ModuleStatus.DEGRADED)
        self.assertIn("discussion_incomplete", discussion.status_reasons)
        self.assertEqual(len(discussion.events), 3)
        marker_payloads = [marker.to_json() for marker in discussion.pagination]
        self.assertTrue(all(marker["endpoint"].endswith(("/comments", "/reviews")) for marker in marker_payloads))
        self.assertTrue(all(marker["cause"] == "cli_unsupported_flag" for marker in marker_payloads))
        self.assertTrue(all("unknown flag" in marker["stderr"] for marker in marker_payloads))

    def test_github_list_slurp_command_does_not_mask_api_rate_or_transport_failures(self) -> None:
        cases = (
            ("HTTP 500 Internal Server Error", "api_status"),
            ("API rate limit exceeded", "api_rate_limit"),
            ("connection timed out", "transport"),
        )

        def public_payload(*, path: str) -> list[dict[str, Any]]:
            return [{"id": path.rsplit("/", 1)[-1], "user": {"login": "cure-bot"}, "body": "CURe review", "created_at": "2026-01-01T00:00:00Z"}]

        for stderr, expected_cause in cases:
            with self.subTest(stderr=stderr):
                error = rf.ReviewflowSubprocessError(
                    cmd=["gh", "api", "--hostname", "github.com", "repos/example/demo/issues/9999/comments", "--paginate", "--slurp"],
                    cwd=None,
                    exit_code=1,
                    stdout="",
                    stderr=stderr,
                )
                with mock.patch.object(rf, "run_cmd", side_effect=error), mock.patch.object(
                    rf, "_github_public_api_payload", side_effect=public_payload
                ):
                    payload = rf.gh_api_list(
                        host="github.com",
                        path="repos/example/demo/issues/9999/comments",
                        allow_public_fallback=True,
                    )
                self.assertIsInstance(payload, dict)
                self.assertEqual(payload["cause"], expected_cause)
                self.assertIn("--slurp", payload["command"])

                discussion = collect_pr_discussion(pr=PR(), fetch_json=lambda _path, err=error: (_ for _ in ()).throw(err))
                marker_payloads = [marker.to_json() for marker in discussion.pagination]
                self.assertEqual({marker["cause"] for marker in marker_payloads}, {expected_cause})
                self.assertTrue(all("--slurp" in marker["command"] for marker in marker_payloads))

    def test_real_generated_review_markdown_extracts_in_scope_issues(self) -> None:
        corpus = PriorReviewCorpus(
            status=ModuleStatus.SUCCESS,
            entries=(
                PriorReviewCorpusEntry(
                    entry_id="real-run:review-md",
                    source_type="session_review",
                    provenance={},
                    body="""## Business / Product Assessment
**Verdict**: REQUEST CHANGES

### In Scope Issues
- Enabled intake can lose recoverable PR discussion evidence when `gh api` list collection fails for a non-auth reason. Sources: `cure.py:7456`, `cure_subsequent_review/github_history.py:66`

  <details open>
  <summary><b>Medium</b> severity · <b>Medium</b> likelihood</summary>

  **Why:** Story 01 is meant to preserve PR discussion history.

  **Code Trail:** `_pr_flow_impl` passes `allow_public_fallback=True` through `gh_api_list`.

  </details>
""",
                    reviewed_head="sha-real",
                    artifact_path=Path("/tmp/prior/review.md"),
                ),
            ),
        )

        ledger = extract_prior_findings(corpus=corpus)

        self.assertEqual(ledger.status, ModuleStatus.SUCCESS)
        self.assertEqual(len(ledger.findings), 1)
        finding = ledger.findings[0]
        self.assertEqual(finding.finding_id, "CURE-001")
        self.assertEqual(finding.severity, "medium")
        self.assertEqual(finding.section, "Business / Product Assessment")
        self.assertIn("gh api", finding.title)
        self.assertIn("cure.py:7456", finding.source_evidence_snippets)
        self.assertEqual(finding.provenance.artifact_path, "/tmp/prior/review.md")

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
                ["pr", "https://github.com/acme/repo/pull/14", "--if-reviewed", "list"]
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

    def test_if_reviewed_new_default_auto_writes_decision_and_runs_intake_after_work_dir_exists(self) -> None:
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
                manifest_path = work_dir / "subsequent" / "run_manifest.json"
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_path.write_text("{}\n", encoding="utf-8")
                return type("Result", (), {"manifest_path": manifest_path, "artifact_dir": work_dir / "subsequent"})()

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
            decision_path = intake_calls[0] / "subsequent" / "decision.json"
            self.assertTrue(decision_path.is_file())
            decision = json.loads(decision_path.read_text(encoding="utf-8"))
            self.assertEqual(decision["mode"], "auto")
            self.assertTrue(decision["enabled"])
            self.assertIn("completed_sessions_found", decision["reasons"])
            meta = json.loads((intake_calls[0].parent / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["paths"]["subsequent_review_decision"], str(decision_path))
            self.assertEqual(meta["paths"]["subsequent_review_manifest"], str(intake_calls[0] / "subsequent" / "run_manifest.json"))
            self.assertTrue(meta["subsequent_review"]["enabled"])
            self.assertEqual(meta["subsequent_review"]["mode"], "auto")

    def test_new_sandbox_auto_disabled_writes_decision_meta_and_skips_intake(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = rf.build_parser().parse_args(
                [
                    "pr",
                    "https://github.com/acme/repo/pull/14",
                    "--if-reviewed",
                    "new",
                    "--no-index",
                    "--no-review",
                ]
            )
            paths = rf.ReviewflowPaths(sandbox_root=root / "sandboxes", cache_root=root / "cache")
            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[]), mock.patch.object(
                rf,
                "load_chunkhound_runtime_config",
                return_value=({}, {"chunkhound": {}}, {}),
            ), mock.patch.object(rf, "materialize_chunkhound_env_config"), mock.patch.object(
                rf, "gh_api_list", return_value=[]
            ), mock.patch(
                "cure_subsequent_review.control_plane.run_subsequent_review_intake",
                side_effect=AssertionError("intake must not run for auto-disabled decisions"),
            ):
                with self.assertRaises(rf.ReviewflowError):
                    rf._pr_flow_impl(args, paths=paths)
            sessions = list(paths.sandbox_root.iterdir())
            self.assertEqual(len(sessions), 1)
            work_dir = sessions[0] / "work"
            decision_path = work_dir / "subsequent" / "decision.json"
            self.assertTrue(decision_path.is_file())
            decision = json.loads(decision_path.read_text(encoding="utf-8"))
            self.assertFalse(decision["enabled"])
            self.assertIn("no_prior_review_signals", decision["reasons"])
            self.assertFalse((work_dir / "subsequent" / "run_manifest.json").exists())
            meta = json.loads((sessions[0] / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["subsequent_review"]["mode"], "auto")
            self.assertFalse(meta["subsequent_review"]["enabled"])
            self.assertEqual(meta["subsequent_review"]["manifest_path"], None)
            self.assertEqual(meta["paths"]["subsequent_review_decision"], str(decision_path))

    def test_preflight_decision_failure_marks_meta_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = rf.build_parser().parse_args(
                [
                    "pr",
                    "https://github.com/acme/repo/pull/14",
                    "--if-reviewed",
                    "new",
                    "--no-index",
                    "--no-review",
                ]
            )
            paths = rf.ReviewflowPaths(sandbox_root=root / "sandboxes", cache_root=root / "cache")
            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[]), mock.patch.object(
                rf,
                "load_chunkhound_runtime_config",
                return_value=({}, {"chunkhound": {}}, {}),
            ), mock.patch.object(rf, "materialize_chunkhound_env_config"), mock.patch(
                "cure_subsequent_review.decision.decide_subsequent_review",
                side_effect=RuntimeError("decision boom"),
            ):
                with self.assertRaisesRegex(RuntimeError, "decision boom"):
                    rf._pr_flow_impl(args, paths=paths)
            sessions = list(paths.sandbox_root.iterdir())
            self.assertEqual(len(sessions), 1)
            meta = json.loads((sessions[0] / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["status"], "error")
            self.assertIn("decision boom", meta["error"]["message"])

    def test_preflight_decision_artifact_write_failure_marks_meta_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = rf.build_parser().parse_args(
                [
                    "pr",
                    "https://github.com/acme/repo/pull/14",
                    "--if-reviewed",
                    "new",
                    "--no-index",
                    "--no-review",
                ]
            )
            paths = rf.ReviewflowPaths(sandbox_root=root / "sandboxes", cache_root=root / "cache")
            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[]), mock.patch.object(
                rf,
                "load_chunkhound_runtime_config",
                return_value=({}, {"chunkhound": {}}, {}),
            ), mock.patch.object(rf, "materialize_chunkhound_env_config"), mock.patch.object(
                rf, "gh_api_list", return_value=[]
            ), mock.patch(
                "cure_subsequent_review.decision.write_json",
                side_effect=OSError("decision write boom"),
            ):
                with self.assertRaisesRegex(OSError, "decision write boom"):
                    rf._pr_flow_impl(args, paths=paths)
            sessions = list(paths.sandbox_root.iterdir())
            self.assertEqual(len(sessions), 1)
            meta = json.loads((sessions[0] / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["status"], "error")
            self.assertIn("decision write boom", meta["error"]["message"])

    def test_preflight_enabled_intake_failure_marks_meta_error(self) -> None:
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
                    "--no-index",
                    "--no-review",
                ]
            )
            paths = rf.ReviewflowPaths(sandbox_root=root / "sandboxes", cache_root=root / "cache")
            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[completed]), mock.patch.object(
                rf,
                "load_chunkhound_runtime_config",
                return_value=({}, {"chunkhound": {}}, {}),
            ), mock.patch.object(rf, "materialize_chunkhound_env_config"), mock.patch(
                "cure_subsequent_review.control_plane.run_subsequent_review_intake",
                side_effect=RuntimeError("intake boom"),
            ):
                with self.assertRaisesRegex(RuntimeError, "intake boom"):
                    rf._pr_flow_impl(args, paths=paths)
            sessions = list(paths.sandbox_root.iterdir())
            self.assertEqual(len(sessions), 1)
            meta = json.loads((sessions[0] / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["status"], "error")
            self.assertIn("intake boom", meta["error"]["message"])

    def test_new_sandbox_explicit_disabled_writes_decision_meta_and_skips_intake(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = rf.build_parser().parse_args(
                [
                    "pr",
                    "https://github.com/acme/repo/pull/14",
                    "--if-reviewed",
                    "new",
                    "--no-subsequent-review",
                    "--no-index",
                    "--no-review",
                ]
            )
            paths = rf.ReviewflowPaths(sandbox_root=root / "sandboxes", cache_root=root / "cache")
            with mock.patch.object(rf, "ensure_review_config"), mock.patch.object(
                rf, "gh_api_json", return_value={"base": {"ref": "main"}, "head": {"sha": "abc"}, "title": "PR"}
            ), mock.patch.object(rf, "scan_completed_sessions_for_pr", return_value=[]), mock.patch.object(
                rf,
                "load_chunkhound_runtime_config",
                return_value=({}, {"chunkhound": {}}, {}),
            ), mock.patch.object(rf, "materialize_chunkhound_env_config"), mock.patch.object(
                rf, "gh_api_list", side_effect=AssertionError("disabled mode must not probe remote")
            ), mock.patch(
                "cure_subsequent_review.control_plane.run_subsequent_review_intake",
                side_effect=AssertionError("intake must not run for explicit-disabled decisions"),
            ):
                with self.assertRaises(rf.ReviewflowError):
                    rf._pr_flow_impl(args, paths=paths)
            sessions = list(paths.sandbox_root.iterdir())
            self.assertEqual(len(sessions), 1)
            work_dir = sessions[0] / "work"
            decision_path = work_dir / "subsequent" / "decision.json"
            self.assertTrue(decision_path.is_file())
            decision = json.loads(decision_path.read_text(encoding="utf-8"))
            self.assertEqual(decision["mode"], "disabled")
            self.assertFalse(decision["enabled"])
            self.assertEqual(decision["reasons"], ["operator_disabled"])
            self.assertFalse((work_dir / "subsequent" / "run_manifest.json").exists())
            meta = json.loads((sessions[0] / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["subsequent_review"]["mode"], "disabled")
            self.assertFalse(meta["subsequent_review"]["enabled"])
            self.assertEqual(meta["subsequent_review"]["manifest_path"], None)

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
