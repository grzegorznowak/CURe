# ruff: noqa: F403, F405
from _subsequent_review_test_support import *  # noqa: F401, F403


class SubsequentReviewLlmVerifierTests(SubsequentReviewTestCase):
    def _request(self) -> Any:
        from cure_subsequent_review.source_truth import FindingVerificationRequest

        return FindingVerificationRequest(
            group_id="G-0001",
            canonical_id="A-01",
            finding_ids=("A-01",),
            title="Null auth guard",
            severity="high",
            section="Security",
            source_evidence_snippets=("app.py:25 old null-check",),
            reviewed_heads=("old-head",),
            pr_files_changed=("app.py",),
            discussion_signals=({"row_id": "DS-0001", "signal_class": "developer_claim_fixed"},),
            provenance={"fixture": True},
        )

    def test_verifier_reads_direct_source_context_and_accepts_first_pass_state(self) -> None:
        from cure_subsequent_review.contracts import SourceState
        from cure_subsequent_review.llm_verifier import LlmFindingVerifier

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            lines = [f"line {index}\n" for index in range(1, 51)]
            lines[24] = "if user is None: return forbidden\n"
            (repo / "app.py").write_text("".join(lines), encoding="utf-8")
            prompts: list[str] = []

            def llm(prompt: str) -> dict[str, Any]:
                prompts.append(prompt)
                return {
                    "source_state": "resolved_from_source",
                    "rationale": "guard is present",
                    "citations": [{"path": "app.py", "line": 25, "summary": "guard present"}],
                }

            result = LlmFindingVerifier(repo_dir=repo, llm=llm)(self._request())

            self.assertEqual(result.source_state, SourceState.RESOLVED_FROM_SOURCE)
            self.assertIn("if user is None", prompts[0])
            self.assertIn('"pr_files_changed": [', prompts[0])
            self.assertIn('"discussion_signals": [', prompts[0])
            self.assertIn("developer_claim_fixed", prompts[0])
            self.assertEqual(result.current_source_citations[0]["path"], "app.py")
            self.assertEqual(result.provenance["verifier"], "llm_finding_verifier")

    def test_verifier_runs_chunkhound_research_before_second_pass_when_more_context_needed(self) -> None:
        from cure_subsequent_review.contracts import SourceState
        from cure_subsequent_review.llm_verifier import LlmFindingVerifier

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "app.py").write_text("target line\n", encoding="utf-8")
            calls: list[str] = []
            research_queries: list[str] = []

            def llm(prompt: str) -> dict[str, Any]:
                calls.append(prompt)
                if len(calls) == 1:
                    return {"source_state": "need_more_context", "rationale": "need call graph"}
                return {
                    "source_state": "still_open",
                    "rationale": "guard still absent after research",
                    "citations": [{"path": "app.py", "line": 1, "summary": "target remains"}],
                }

            def research(query: str) -> str:
                research_queries.append(query)
                return "semantic research: no guard found"

            request = self._request().__class__(
                **{**self._request().__dict__, "source_evidence_snippets": ("app.py:1 target",)}
            )
            result = LlmFindingVerifier(repo_dir=repo, llm=llm, chunkhound_research=research)(request)

            self.assertEqual(result.source_state, SourceState.STILL_OPEN)
            self.assertEqual(len(calls), 2)
            self.assertIn("G-0001", research_queries[0])
            self.assertIn("semantic research", calls[1])
            self.assertEqual(result.provenance["chunkhound_research"], "used")

    def test_verifier_returns_not_verifiable_without_llm_when_evidence_refs_are_missing(self) -> None:
        from cure_subsequent_review.contracts import SourceState
        from cure_subsequent_review.llm_verifier import LlmFindingVerifier

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            calls: list[str] = []

            result = LlmFindingVerifier(repo_dir=repo, llm=lambda prompt: calls.append(prompt) or {})(self._request())

            self.assertEqual(result.source_state, SourceState.NOT_VERIFIABLE)
            self.assertEqual(calls, [])
            self.assertIn("evidence_reference_missing", result.unavailable_reasons)


__all__ = ["SubsequentReviewLlmVerifierTests"]
