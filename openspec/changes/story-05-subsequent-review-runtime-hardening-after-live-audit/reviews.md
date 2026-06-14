# Reviews: story-05-subsequent-review-runtime-hardening-after-live-audit

## Review Log

- 2026-06-13T10:05:45Z Ingestion note
  - Decision: not reviewed yet
  - Plan lane: 🟡 PLAN DRAFT
  - Status: ⚪ TODO
  - Evidence source: latest PR #22 live audit sandbox `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260613-080828-d739` at head `372b4a753099c4b6e077d98551da51039222a16b`.
  - Summary: Story 05 captures follow-up hardening points that should receive fresh plan review before implementation.

- 2026-06-13T10:19:08Z Plan review
  - Decision: APPROVED
  - Plan lane: 🟢 PLAN APPROVED
  - Status: ⚪ TODO
  - Evidence reviewed: `story.md`, `proposal.md`, `design.md`, `tasks.md`, `progress.md`, `reviews.md`, initiative tracker, feedback log FB-030..FB-038, notebook `pr22-live-audit-story05-ingestion`, and fresh code architecture validation saved in notebook `openspec-plan-research-cure-subsequent-pr-review-story-05-subsequent-review-runtime-hardening-after-live-audit`.
  - Risk lenses activated: consumer-facing output/provenance separation; memory/cache identity; untrusted discussion authority; path traversal/session containment; verifier citation trust boundary; runtime policy wiring; prior finding parsing; multipass abort guardrails; TAP/proof adequacy; test feasibility/overbreadth.
  - Rationale: A1-A9 directly absorb the live-audit findings and keep source truth separate from discussion/memory truth. TAP-1..TAP-8 provide feasible focused proof slices across prompt/governor, memory/reconciliation, discussion/linker, artifact path handling, verifier/source truth, prior-finding parsing, and multipass abort paths. Critical files and verification commands align with verified runtime seams, and no implementation work has started.
  - Required implementation guardrails: add red-first tests for A1-A9, preserve Story 04 proven gates (strict multipass step schema, A17 warn-only governor, A19/DA-0006, FB-028 malformed-linker degradation), and keep live PR #22 rerun as manual/file-read proof rather than routine CI dependency.

- 2026-06-14T09:14:55Z Resume live-audit pass
  - Decision: NOT READY FOR REVIEW
  - Plan lane: 🟢 PLAN APPROVED
  - Status at review time: 🔄 IN PROGRESS (historical; superseded/remapped on 2026-06-14)
  - Evidence reviewed: fresh PR #22 sandbox `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260614-083232-dd7e`, `review.md`, `work/subsequent/report_governor_result.json`, `source_verification.json`, `disposition_ledger.json`, `discussion_signals.json`, `meta.json`, and memory artifact `/home/vscode/.local/state/cure/pr/github.com/grzegorznowak/cure/22/cure_memory.json`.
  - Findings: live `review.md` still contains a prominent raw `### Internal DA coverage` section and re-reports Story 05 hardening issues; report governor is degraded with `prominent_internal_da_coverage`. The sandbox checkout is PR head `372b4a7` and lacks the local uncommitted Story 05 implementation, so this live run does not prove the implemented changes on PR #22.
  - Follow-up performed: added deterministic A1 demotion of plain Internal DA coverage sections to an audit/provenance `<details>` block before report-governor audit; focused report-governor/prompt tests now pass (56 passed), `tests/test_subsequent_review.py` passes (116 passed, 29 subtests), plus targeted ruff, `git diff --check`, and `mypy`.
  - Required next review input: rerun a fresh live audit after the Story 05 worktree changes are present in the live PR target; do not advance to 🟣 IN REVIEW until that run no longer re-reports A1-A9 or explicitly accounts for any remaining findings.


## Superseded remap review note

- 2026-06-14T10:46:40Z OpenSpec provenance repair: Story 05 is superseded/remapped rather than reviewed as an independent delivery story. Reviewers should evaluate the live-audit follow-up against Story 01 (FB-033, FB-037), Story 03 (FB-032, source-truth side of FB-035), and Story 04 (FB-030, FB-031, FB-034, runtime side of FB-035, FB-036, FB-038). The old Story 05 acceptance list is historical intake evidence only.
