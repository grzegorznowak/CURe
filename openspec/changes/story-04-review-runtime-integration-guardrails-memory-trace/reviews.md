# Reviews: story-04-review-runtime-integration-guardrails-memory-trace

> Implementation review artifact migrated from legacy `agent_coordination` during the 2026-06-12 OpenSpec-format rewrite.
> Canonical story contract: `story.md`. Legacy source remains under `/workspaces/cure_workspace/agent_coordination/epics/cure-subsequent-pr-review/`.

## Review Log

- 2026-06-15T15:29:26Z A19/FB-043 footer-provenance hardening follow-up review
  - Feedback IDs: FB-043
  - Decision: approve
  - Approval gate: pass
  - Product verdict: approve
  - Technical verdict: approve
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Status transition: unchanged: 🔵 IN PR -> 🔵 IN PR
  - Sections reviewed: A19/FB-043 footer-provenance hardening diff; `cure_subsequent_review/prior_corpus.py`, `decision.py`, `runtime.py`, `control_plane.py`, `github_history.py`, `cure.py`; focused prior-corpus/decision/runtime-packaging/PR-flow tests; Story 04 OpenSpec A19/FB-043 docs.
  - Risk lenses reviewed: official footer authenticity versus PR/session/head provenance, independent footer SHA and pull-review event-head checks, author/login independence for compatible official footers, generic/body-only rejection, pre-corpus exclusion before extraction/source-verification/disposition/final carry-forward, and runtime/governor audit surface for ignored foreign footers.
  - Evidence quality: direct source/test/doc inspection, two independent child reviews, focused architecture/code-research helper saved to `notebook:story04-a19-footer-provenance-flow-2026-06-15`, and local command execution.
  - Checks run: `git diff --check` ✅; `python -m pytest tests/_subsequent_review_unit_decision_unittest.py tests/_subsequent_review_unit_prior_corpus_unittest.py tests/_subsequent_review_unit_runtime_packaging_unittest.py tests/_subsequent_review_integration_pr_flow_unittest.py -q` ✅ 40 passed, 8 subtests; commit-prep full suite `git diff --check && ruff check . && mypy && python -m pytest -q` ✅ 774 passed, 50 subtests.
  - Key findings:
    - None blocking. The previous footer-current/event-foreign pull-review blocker is fixed: `_assess_remote_cure_footer_provenance()` now evaluates `footer_reviewed_head` and `event_reviewed_head` as separate signals and rejects/audits the review when any present head signal mismatches the current run (`cure_subsequent_review/prior_corpus.py:147-166`). Decision enablement now counts only compatible official remote markers (`cure_subsequent_review/decision.py:183-198`), while corpus construction admits only compatible entries and records ignored foreign-footer audit metadata before prior-finding extraction (`cure_subsequent_review/prior_corpus.py:278-320`). Runtime context/governor packaging surfaces official, foreign, and body-only counts plus foreign audit reasons (`cure_subsequent_review/runtime.py:180-212`, `cure_subsequent_review/runtime.py:550-570`).
  - Debt Friction: none
  - Next action: proceed with the remaining Story 04 PR-stage/live-output proof gates; no local A19/FB-043 implementation blocker remains.

- 2026-06-15T15:04:08Z A19 footer-provenance hardening implementation review
  - Feedback IDs: FB-043
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Status transition: unchanged: 🔵 IN PR -> 🔵 IN PR
  - Sections reviewed: A19/TAP-20 footer-provenance hardening diff; `cure_subsequent_review/prior_corpus.py`, `decision.py`, `runtime.py`, `control_plane.py`, `cure.py`; focused prior-corpus/decision/runtime-packaging/PR-flow tests; Story 04 OpenSpec A19/FB-043 docs.
  - Risk lenses reviewed: official footer authenticity versus PR/session/head provenance, author/login independence for compatible official footers, generic/body-only rejection, pre-corpus exclusion before extraction/source-verification/disposition/final carry-forward, and runtime/governor audit surface for ignored foreign footers.
  - Evidence quality: direct source/test/doc inspection, independent child review, focused command execution, and a synthetic pull-review mismatch repro against the current worktree.
  - Checks run: `git diff --check` ✅; `python -m pytest tests/_subsequent_review_unit_prior_corpus_unittest.py tests/_subsequent_review_unit_decision_unittest.py tests/_subsequent_review_unit_runtime_packaging_unittest.py tests/_subsequent_review_integration_pr_flow_unittest.py -q` ✅ 38 passed, 8 subtests; synthetic repro for pull-review event head mismatch ❌ reproduced blocker (`entries ['pr_review:901']`, entry reviewed head `e305f826...`, no ignored audit row).
  - Key findings:
    - A19/FB-043 is incomplete for pull-review event head provenance. `_assess_remote_cure_footer_provenance()` collapses footer SHA and event `reviewed_head` with `metadata.get("reviewed_head") or event_reviewed_head` (`cure_subsequent_review/prior_corpus.py:135`), so an official footer that claims the current PR/head masks a foreign pull-review `commit_id`/`reviewed_head`. The accepted path then admits the event to the prior corpus (`cure_subsequent_review/prior_corpus.py:277-289`) and decision intake counts it as an accepted remote CURe marker (`cure_subsequent_review/decision.py:90-100`, `cure_subsequent_review/decision.py:186-198`). Repro: current PR18 head `c3f81e8...`, pull-review event `reviewed_head=e305f826...`, footer `sha c3f81e8 · session grzegorznowak-cure-pr18-...`; `build_prior_review_corpus(..., current_head=c3f81e8...)` admits `pr_review:901` with `reviewed_head=e305f826...` instead of auditing/ignoring it as `foreign_cure_footer_provenance`.
  - Debt Friction: none; fix should treat footer head and pull-review event head as independent provenance signals, require each present head to be compatible with the current run, audit any mismatch, and add red regressions for footer-current/event-foreign pull-review decision and corpus exclusion.
  - Next action: `/openspec-story-resume cure-subsequent-pr-review story-04-review-runtime-integration-guardrails-memory-trace` to fix the pull-review event-head provenance gap, then rerun the A19 focused suites and static checks.

- 2026-06-14T12:12:38Z PR #22 intake/cache live-audit feedback absorbed
  - Source: `notebook:pr22-live-audit-intake-performance`; latest sandbox `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260614-110911-a3ae`
  - Feedback IDs: FB-039, FB-040, FB-041, FB-042
  - Source IDs: `manual:sha256-dcb21b8fd912:1`, `manual:sha256-cf4ddeb66c3f:2`, `manual:sha256-87ad2bcd8fe8:3`, `manual:sha256-fad0ed1ade59:4`
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Multipass review: not_triggered
  - Prior review concerns: source-verification cache persistence/replay and runtime performance remain open
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Initiative contract drift: present after absorption; Story 04 contract now carries A20/TAP-21
  - Status transition: unchanged: 🔵 IN PR -> 🔵 IN PR
  - Sections reviewed: PR #22 source-verification/review-memory artifacts and run telemetry; Story 04 Purpose, Triggering Need, Scope, Scenarios / Behavior Examples, Acceptance, Verification, Surface / Branch Proof Matrix, Input Boundary Shape Risk, Fail-open Checks, Risk Lens Inventory, Discovery Notes, Critical Files, Implementation Notes, and Locked Decisions.
  - Original intent checked: Story 04 runtime memory-store/source-verification cache responsibilities and prior PR #22 hardening feedback; no separate product ticket found.
  - Traceability: forward gaps before absorption; backward complete after A20/TAP-21 amendment to Story 04.
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: sandbox artifacts `work/subsequent/source_verification.json`, `work/subsequent/disposition_ledger.json`, `work/subsequent/run_manifest.json`, `work/logs/cure.log`, shared `cure_memory.json` behavior summary; planned owners `cure_subsequent_review/runtime.py`, `memory_store.py`, `semantic_pipeline.py`, and focused memory/runtime/semantic/PR-flow tests.
  - Risk / miss category: persistence/resource lifecycle/performance/finding-identity
  - Risk lenses reviewed: intake-time memory lifecycle, stable cache identity, safe non-source-proof replay, cache hit/miss telemetry, verifier fan-out/timing observability, and bounded future parallelism/cheaper verifier policy work.
  - Finding closure required: contract revalidation plus red-first implementation proof for A20/TAP-21; fresh PR #22 live audit must show repeated historical claims no longer trigger linear verifier storms.
  - Evidence quality: confirmed live-audit findings from notebook/sandbox summary; inferred implementation owners from current Story 04 runtime architecture; unknown exact code changes until story resumes; provisional fresh live proof pending.
  - Files reviewed: `notebook:pr22-live-audit-intake-performance`, latest sandbox path above, `story.md` amended sections.
  - Hypothesis triage:
    - suspicious surface: source-verification cache lifecycle and identity; tentative issue: verifier work is lost or missed when memory persists only after final review and lookup depends on ordinal group layout; next proof target: intake-completion memory write, stable identity replay, terminal-disposition replay matrix, and telemetry regressions.
  - Key findings:
    - FB-039: source-verification memory writes happen only after review completion, so failed or still-running runs can repeat expensive verifier work instead of reusing successful intake/source-verification rows.
    - FB-040: cache replay is limited to same-head `resolved_from_source`; dropped/not-relevant/non-reportable terminal outcomes still consume verifier calls unless safe replay with `not_source_proof` is modeled.
    - FB-041: cache lookup is too fragile when ordinal `group_id` is sufficient; replay must key on stable finding identity/fingerprint/source-reference identity, with ordinal group IDs retained only as metadata.
    - FB-042: the latest intake showed 30 serial verifier LLM calls and lacked cache hit/miss reason telemetry or fan-out timing sufficient to prove cache effectiveness.
  - Debt Friction: none
  - Next action: `/openspec-story-plan-review cure-subsequent-pr-review story-04-review-runtime-integration-guardrails-memory-trace`

- 2026-06-13T10:05:45Z Latest PR #22 live-audit ingestion from sandbox `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260613-080828-d739`
  - Decision: request_changes overall; Story 04 prior closure gates mostly pass; fresh hardening feedback was initially staged in synthetic Story 05, then remapped on 2026-06-14 into Stories 01/03/04
  - Approval gate: partial/pass for previous Story 04 gates, fail for new hardening findings
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Status transition: unchanged: 🔵 IN PR -> 🔵 IN PR
  - Sections reviewed: final `review.md`, `meta.json`, `work/grounding_report.json`, `work/logs/cure.log`, `work/subsequent/report_governor_result.json`, `governor_brief.md`, `source_verification.json`, `disposition_ledger.json`, `run_manifest.json`, and shared `cure_memory.json` summary.
  - Evidence quality: live sandbox artifact audit at PR head `372b4a753099c4b6e077d98551da51039222a16b`; no product source edits in this ingestion pass.
  - Finding closure:
    - Strict multipass `### Step Result:` regression from sandbox `...-050345-4d51` is resolved: all five step artifacts begin with `### Step Result:`, strict grounding has zero skipped steps and no invalid artifacts.
    - A17 passes live: post-review report governor runs in strict mode, records `status=success` / awareness `demonstrated`, and does not block publication.
    - A19/`DA-0006` passes live: `DA-0006` is `out-of-scope` / `move_out_of_scope` with FB-026 official-footer policy provenance, not `carried-forward/re_report`.
    - FB-028 is resolved for the original malformed-linker-abort shape: artifacts cite malformed linker output degrading instead of aborting semantic artifact creation.
    - FB-029 is resolved only narrowly: cache replay rejects same ordinal groups with different `finding_ids`, but the latest review reports a broader repeated-display-ID/origin/fingerprint variant.
  - Computed-vs-carried note: the five `### Prior Review Issue History` clusters are historical prior issue identities carried from prior corpus/comments/sessions, but current statuses were recomputed in this run via 14 `llm_finding_verifier` source-verification rows plus one FB-026 policy override; no `memory_cache` provenance was found for those status computations.
  - Key findings ingested as live-audit feedback and later remapped to existing story owners:
    - FB-030/A1: `### Internal DA coverage` is audit/provenance output and should be removed/demoted from ordinary consumer-facing `review.md` while preserving complete audit coverage.
    - FB-031/A2: memory replay needs stable origin/fingerprint/source-reference identity beyond ordinal `group_id` plus display `finding_ids`.
    - FB-032/A3: untrusted comment body text must not escalate discussion authority.
    - FB-033/A4: zip/source artifact selection must constrain metadata paths to the owning session boundary.
    - FB-034/A5: cached discussion linker results must validate current reconciliation group identity.
    - FB-035/A6: verifier citations must be constrained to inspected source contexts.
    - FB-036/A7: discussion linker LLM calls must use the prepared runtime policy/config/add-dir environment.
    - FB-037/A8: supported concise generated reviews must not disappear from prior-finding identity.
    - FB-038/A9: multipass planner abort must not bypass prior-review final-output/governor guardrails.
  - Remap note: the Story 05 OpenSpec files have been removed after remap. Active follow-up owners are Story 04 for runtime/report/memory/linker guardrails, Story 01 for artifact-path and concise-parser support, and Story 03 for authority/source-truth invariants. Next proof step is a fresh PR #22 live audit after the already-pushed hardening commits.

- 2026-06-13T04:51:44Z Review run by fresh maintainer session
  - Decision: approve
  - Approval gate: pass
  - Product verdict: approve
  - Technical verdict: approve
  - Multipass review: completed
  - Prior review concerns: resolved
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Initiative contract drift: none
  - Status transition: unchanged: 🔵 IN PR -> 🔵 IN PR
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: initiative/story/proposal/design/tasks/progress/reviews; PR #22 state via `gh pr view 22`; latest sandbox `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424`; dependency invariants from Stories 01-03 for official-footer policy, source/discussion separation, and limited arbiter actions
  - Traceability: forward complete for local FB-027/A16, FB-028, and FB-029 implementation fixes; backward complete from changed runtime/linker/signals/memory/prompt/test/fixture surfaces to A16/A17/A19/A12/A8 and prior feedback closure
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: `git diff --stat`; `runtime.py` issue-history/governor audit helpers; `discussion_linker.py` malformed output boundary; `discussion_signals.py` degraded signal ledger; `memory_store.py` resolved replay gate; `source_truth.py` memory callsite; all eleven subsequent-aware prompt templates; focused report-governor/linker/memory/prompt tests; A19 source/disposition/governor regression tests; public wrapper
  - Risk lenses reviewed: prompt/template fail-open and final-output ordering; stable issue-cluster/status preservation; internal DA coverage; official-footer policy vs body-only PR-comment cluster status; LLM JSON/malformed linker fail-open; persisted memory identity/staleness; source-vs-discussion separation; PR-stage/live-output handoff
  - Finding closure: FB-027/A16 resolved locally by prompt override and deterministic governor audit: prompts require final output to begin with `### Prior Review Issue History` and include `### Internal DA coverage`, while report-governor parses stable issue titles/statuses from `governor_brief.md` and degrades when issue history is not first or required clusters are missing (`prompts/default.md:17`, `cure_subsequent_review/runtime.py:642`, `cure_subsequent_review/runtime.py:675`, `tests/_subsequent_review_unit_report_governor_unittest.py:214`). Stable cluster/status proof preserves body-only PR-comments as `carried-forward/re_report` and official-footer policy as `out-of-scope` (`tests/_subsequent_review_unit_report_governor_unittest.py:144-159`). FB-028 resolved locally by catching malformed/failed linker output and emitting degraded no-link discussion signals instead of aborting (`cure_subsequent_review/discussion_linker.py:119`, `cure_subsequent_review/discussion_signals.py:106`, `tests/_subsequent_review_unit_discussion_linker_unittest.py:63`). FB-029 resolved locally by requiring cached finding IDs to match current finding IDs before replaying same-ordinal memory (`cure_subsequent_review/memory_store.py:42`, `cure_subsequent_review/memory_store.py:217`, `tests/_subsequent_review_unit_memory_store_unittest.py:126`). A17 warn-only and A19/DA-0006 behavior are preserved by focused regressions and latest sandbox evidence (`/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424/work/subsequent/disposition_ledger.json:123`, `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424/work/subsequent/source_verification.json:344`).
  - Evidence quality: confirmed direct source/test/sandbox reads and local command execution; inferred none material; unknown live output after these uncommitted local changes until PR #22 is synced and rerun; provisional only the external PR-stage live rerun/done gate, not the local implementation review
  - Files reviewed: `cure_subsequent_review/runtime.py`, `cure_subsequent_review/discussion_linker.py`, `cure_subsequent_review/discussion_signals.py`, `cure_subsequent_review/memory_store.py`, `cure_subsequent_review/source_truth.py`, `prompts/default.md`, all subsequent-aware `prompts/mrereview_*.md` templates in the diff, `tests/_reviewflow_unittest_prompt_session_impl.py`, `tests/_subsequent_review_unit_report_governor_unittest.py`, `tests/_subsequent_review_unit_discussion_linker_unittest.py`, `tests/_subsequent_review_unit_memory_store_unittest.py`, `tests/fixtures/subsequent_review/landmark_trace/artifacts/review.md`, latest sandbox artifacts, and OpenSpec coordination files
  - Hypothesis triage:
    - suspicious surface: final output ordering/cluster preservation; tentative issue: live review could start with other sections or omit stable governor issue clusters; next proof target: prompt overrides plus deterministic report-governor audit and focused test `test_post_review_issue_history_must_be_first_and_match_brief_clusters`
    - suspicious surface: LLM discussion linker JSON boundary; tentative issue: malformed classifier output aborts semantic artifacts; next proof target: `LlmDiscussionLinker.__call__()` exception handling plus resolver degraded ledger regression
    - suspicious surface: shared PR memory replay; tentative issue: ordinal `G-*` reuse confirms a different finding at the same head; next proof target: `ReviewMemoryStore.synthesize_resolved_source_row()` identity guard plus mismatched finding-id regression
    - suspicious surface: A19 footer policy preservation; tentative issue: official-footer policy item regresses to `carried-forward/re_report`; next proof target: source/disposition/governor regression suite and latest sandbox `DA-0006` evidence
  - Key findings:
    - None.
  - Debt Friction: none
  - Next action: commit/push the local approved diff to PR #22, rerun/audit live PR #22 output, and only then move Story 04 from 🔵 IN PR to ✅ DONE if A16 issue history leads final output and `DA-0006` remains non-carried-forward.

- 2026-06-13T04:34:15Z Feedback absorption review entry from latest PR #22 live sandbox `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424`
  - Feedback IDs: FB-027, FB-028, FB-029
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Status transition: unchanged: 🔵 IN PR -> 🔵 IN PR
  - Sections reviewed: latest sandbox final `review.md`, `work/pr_context.json`, `meta.json`, `work/subsequent/source_verification.json`, `work/subsequent/disposition_ledger.json`, `work/subsequent/report_governor_result.json`, `work/subsequent/run_manifest.json`, `work/subsequent/subsequent_review_context.md`, and `work/logs/cure.log`.
  - Risk lenses reviewed: A16 human issue-history output ordering, stable issue-cluster preservation, internal DA coverage, official-footer policy propagation, report-governor warn-only behavior, malformed LLM linker degradation, memory replay/finding identity stability.
  - Evidence quality: live sandbox artifact audit from PR head `5d5b2c1e431659ab52c17b3453031e05b8d421ac`; no product source edits in this absorption pass.
  - Key findings:
    - A16 remains partial/failing in the latest live output: final `review.md` contains a human-readable `### Prior Review Issue History`, but it starts with `### Steps taken` instead of leading with the issue history, and the report governor records partial awareness/degraded status. Sources: `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424/review.md:1`, `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424/review.md:12`, `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424/work/subsequent/report_governor_result.json:2`, `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424/work/subsequent/report_governor_result.json:4`, `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424/work/subsequent/report_governor_result.json:19`.
    - A16 also drops/renames required prior-review awareness: report governor notes no DA-by-DA internal coverage and a missing required carried-forward cluster for body-only PR comments (`PR comments can be admitted as prior CURe reviews based on body text alone`). Sources: `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424/work/subsequent/report_governor_result.json:9`, `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424/work/subsequent/report_governor_result.json:10`.
    - A19/DA-0006 passes in the latest live artifacts: `G-0006` is present, `SV-0006` records `policy_override=official_footer_marker_acceptance` and `source_state=resolved_from_source`, and `DA-0006` is `move_out_of_scope` rather than `re_report` / `carried-forward/re_report`. Sources: `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424/work/subsequent/reconciled_findings.json:221`, `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424/work/subsequent/source_verification.json:344`, `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424/work/subsequent/source_verification.json:348-349`, `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424/work/subsequent/disposition_ledger.json:123`, `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424/work/subsequent/disposition_ledger.json:148-149`.
    - A17 warn-only report-governor behavior passes: final `review.md` was published, sandbox status is done, post-review governor completed, and degraded report-governor status is recorded rather than blocking output. Sources: `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424/review.md:109-111`, `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424/meta.json:911`, `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424/work/logs/cure.log:41-44`, `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424/work/subsequent/run_manifest.json:38-48`, `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424/meta.json:967-977`.
    - The latest CURe review also reports malformed LLM discussion-linker output can abort semantic artifacts instead of degrading. Source: `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424/review.md:31-42`.
    - The latest CURe review also reports source-verification memory replay can confirm the wrong finding when ordinal group IDs shift. Source: `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424/review.md:52-63`.
  - Finding closure:
    - Previous DA-0006 carried-forward blocker is closed in live artifacts.
    - A16 live-output proof remains open.
    - New implementation review findings FB-028 and FB-029 remain open.
  - Next action: `/openspec-story-resume cure-subsequent-pr-review story-04-review-runtime-integration-guardrails-memory-trace` to fix A16 final-output ordering/cluster/internal-coverage behavior plus FB-028 malformed-linker degradation and FB-029 memory replay identity stability, then rerun PR #22 live output.

- 2026-06-12T14:31:00Z Review run by fresh maintainer child session
  - Decision: approve locally; live-output gate still pending
  - Approval gate: pass for local A19/TAP-20 fix; not final DONE until PR #22 is rerun live
  - Product verdict: approve locally
  - Technical verdict: approve locally
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Status transition: unchanged: 🔄 IN PROGRESS -> 🔄 IN PROGRESS. Rationale: current story convention requires the A19 fix to be committed/pushed and proven in a PR #22 live rerun before moving out of in-progress.
  - Sections reviewed: latest PR #22 audit notebook/artifacts for `G-0006` / `SV-0006` / `DA-0006`, A19 source/test diff, Acceptance A19/TAP-20 proof, Session Handoff, MASTER tracker.
  - Code surfaces searched: `cure_subsequent_review/source_truth.py`, `cure_subsequent_review/disposition.py`, `cure_subsequent_review/runtime.py` governor-map behavior, source/disposition/governor/prior-corpus tests.
  - Risk lenses reviewed: exact live footer-auth false-positive matching, FB-026 official-footer policy override, generic/body-only CURe-looking text rejection, source-vs-discussion separation, disposition-map/governor status rendering.
  - Evidence quality: direct source/test inspection, exact replay of latest live `G-0006` reconciliation/discussion inputs through local source-truth/disposition/governor-map code, focused and wrapper tests, static checks.
  - Checks run: focused A19 suite `python -m pytest tests/_subsequent_review_unit_source_truth_unittest.py tests/_subsequent_review_unit_disposition_arbiter_unittest.py tests/_subsequent_review_unit_report_governor_unittest.py -q` ✅ 18 passed, 15 subtests; public wrapper `python -m pytest tests/test_subsequent_review.py -q` ✅ 112 passed, 29 subtests; prior-corpus/decision footer policy suite `python -m pytest tests/_subsequent_review_unit_decision_unittest.py tests/_subsequent_review_unit_prior_corpus_unittest.py -q` ✅ 10 passed, 8 subtests; `ruff check . && git diff --check && mypy` ✅; exact live-input replay ✅ `SV-0006=resolved_from_source`, `policy_override=official_footer_marker_acceptance`, `DA-0006=move_out_of_scope`, governor brief has `DA-0006: out-of-scope` and not `DA-0006: carried-forward/re_report`.
  - Key findings:
    - None blocking locally. The local A19 fix satisfies the PR #22 live-output blocker shape: official-footer/authorship false-positive no longer remains `still_open` + `re_report` / `carried-forward`; generic/body-only CURe-looking text remains rejected/on the normal verifier path.
  - Debt Friction: no product blocker found; live evidence is still stale because latest pushed PR #22 head is `da1c1ce` and does not include the local A19 fix.
  - Next action: commit/push the A19 fix to PR #22 head branch, rerun PR #22 review, and audit `source_verification.json`, `disposition_ledger.json`, `governor_brief.md`, and `review.md` for `DA-0006: out-of-scope` (or another allowed non-carried-forward status) and no `carried-forward/re_report`.

- 2026-06-12T14:06:00Z Live-output audit follow-up recorded from PR #22 sandbox `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-132229-cfad`
  - Decision: request_changes / partial approval
  - Approval gate: fail for A19/TAP-20 only
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Status transition: 🔵 IN PR -> 🔄 IN PROGRESS
  - Sections reviewed: latest live artifacts (`review_context_package.json`, `subsequent_review_context.md`, `prior_review_corpus.json`, `source_verification.json`, `disposition_ledger.json`, `governor_brief.md`, `review.md`, `report_governor_result.json`) plus A15-A19 proof rows and Session Handoff
  - Risk lenses reviewed: runtime status consistency, disposition-map completeness, report-governor warn-only behavior, stale duplicate source binding, FB-026 official-footer policy propagation, semantic/disposition classification of policy-approved prior findings
  - Evidence quality: live artifact audit, not product-code inspection in this coordination-doc pass
  - Key findings:
    - A15-A18 pass in live output.
    - A19 remains incomplete: runtime artifacts propagate FB-026 and final `review.md` does not substantively re-report official-footer acceptance as spoofing, but `G-0006` / `SV-0006` / `DA-0006` is still carried forward (`source_state=still_open`, `action=re_report`, map status `carried-forward/re_report`) and appears in `governor_brief.md` Still Open with footer-policy citations.
  - Next action: `/epic-story-resume cure-subsequent-pr-review 04` to add the A19 semantic/disposition/governor regression, fix classification to an allowed non-carried-forward status, rerun focused tests and PR #22 review output, then confirm `DA-0006` no longer maps to `carried-forward/re_report`.

- 2026-06-12T13:12:47Z Review run by fresh maintainer child session
  - Decision: approve
  - Approval gate: pass
  - Product verdict: approve
  - Technical verdict: approve
  - Multipass review: completed via manual focused-pass substitute (child agent cannot spawn further children)
  - Prior review concerns: resolved. The previous A18/TAP-19 blocker is fixed for the actual `cure.py` shape: stale duplicate `cure.py:12953` is shadowed by active parenthesized multi-line `from cure_sessions import (...)` around `cure.py:15741-15760`, and the verifier now degrades the stale ref without invoking the LLM.
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Status transition: 🔄 IN PROGRESS -> ✅ DONE
  - Sections reviewed: Acceptance A15-A19, TAP-16-TAP-20, Acceptance Proof Matrix A15-A19, Progress Log, Session Handoff, MASTER tracker, changed product source/tests
  - Code surfaces searched: `cure_subsequent_review/runtime.py`, `cure_subsequent_review/llm_verifier.py`, `_pr_flow_impl` finalization/post-review path in `cure.py`, `cure.py` stale duplicate/re-export area, focused follow-up tests, landmark golden
  - Risk lenses reviewed: final runtime package/status refresh, mandatory DA disposition-map coverage, warn-only report-governor awareness gaps, inactive/dead duplicate source references, Story 02/FB-026 footer-policy propagation, A1-A14 regression surfaces sampled through focused suites
  - Evidence quality: confirmed by direct source/test reads, exact actual-shape A18 probe, and local command execution; live PR #21 not exercised (optional/manual only)
  - Checks run: targeted A18 regression `python -m pytest tests/_subsequent_review_unit_llm_verifier_unittest.py::SubsequentReviewLlmVerifierTests::test_verifier_degrades_parenthesized_multiline_reexport_refs_instead_of_calling_llm -q` ✅ 1 passed; actual A18 probe ✅ `source_state=not_verifiable`, `unavailable_reasons=inactive_source_reference_active_binding:_resolve_session_relative_path:cure_sessions.py`, `llm_calls=0`; focused follow-up suites ✅ 63 passed, 23 subtests; `python -m pytest tests/test_subsequent_review.py -q` ✅ 109 passed, 29 subtests; `ruff check . && git diff --check && mypy` ✅
  - Hypothesis triage:
    - suspicious surface: `llm_verifier._inactive_binding_reason`; result: parenthesized multi-line import parsing covers the production re-export form and the actual probe no longer reaches the LLM
    - suspicious surface: runtime package/status finalization; result: `finalize_review_runtime_context()` and PR-flow final refresh are covered by focused runtime packaging/control/memory tests
    - suspicious surface: final output DA map/report governor; result: governor brief/prompt/audit map coverage and degraded/warn-only outcomes are covered by focused report-governor tests and landmark golden heading
    - suspicious surface: footer-marker policy propagation; result: package/governor tests carry official-footer accepted provenance and body-only rejection into runtime context/audit prompts
  - Key findings:
    - None. A15-A19 follow-up acceptance is locally covered; the prior A18 request-change blocker is verified resolved; focused/broad verification passed.
  - Debt Friction: none
  - Next action: Story 04 is complete locally. Synchronize/push the locally approved follow-up implementation to PR #22 and refresh PR status if desired.

- 2026-06-12T12:59:16Z Review run by fresh maintainer child session
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Multipass review: completed via manual focused-pass substitute (child agent cannot spawn further children)
  - Prior review concerns: PR #22 follow-up A15-A19 reviewed; A15/A16/A17/A19 looked covered in sampled source/tests, but A18 fails against the actual `cure.py` binding shape that motivated the follow-up
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Status transition: 🔄 IN PROGRESS -> 🔄 IN PROGRESS
  - Sections reviewed: Purpose, Acceptance, Acceptance Proof Matrix A15-A19, Progress Log, Session Handoff, MASTER tracker, changed product source/tests
  - Code surfaces searched: `cure_subsequent_review/runtime.py`, `cure_subsequent_review/llm_verifier.py`, `_pr_flow_impl` finalization path in `cure.py`, focused follow-up tests, actual stale duplicate/re-export area in `cure.py`
  - Risk lenses reviewed: stale runtime-status snapshots, final DA disposition map, warn-only report-governor gaps, inactive/dead source references, FB-026 footer-policy propagation, A1-A14 regression surfaces sampled via focused suites
  - Checks run: `python -m pytest tests/_subsequent_review_unit_runtime_packaging_unittest.py tests/_subsequent_review_unit_runtime_memory_unittest.py tests/_subsequent_review_functional_control_plane_unittest.py tests/_subsequent_review_unit_report_governor_unittest.py tests/_subsequent_review_unit_llm_verifier_unittest.py tests/_subsequent_review_unit_prior_corpus_unittest.py tests/_subsequent_review_unit_decision_unittest.py tests/_subsequent_review_integration_pr_flow_unittest.py tests/_subsequent_review_unit_source_truth_unittest.py tests/_subsequent_review_unit_disposition_arbiter_unittest.py tests/_subsequent_review_acceptance_landmark_trace_unittest.py -q` ✅ 62 passed, 23 subtests; `python -m pytest tests/test_subsequent_review.py -q` ✅ 108 passed, 29 subtests; `ruff check . && git diff --check` ✅; `mypy` ✅; targeted A18 probe ✅ reproduced blocker
  - Hypothesis triage:
    - suspicious surface: `llm_verifier._inactive_binding_reason`; tentative issue: implementation only parses one-line import statements; next proof target: actual multi-line `from cure_sessions import (...)` re-export in `cure.py`
  - Key findings:
    - A18/TAP-19 is not satisfied for the real stale duplicate `cure.py` source-reference shape. Sources: `cure_subsequent_review/llm_verifier.py:91-108`, `cure.py:12953`, `cure.py:15741-15760`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** The PR #22 audit specifically called out stale duplicate `cure.py` symbols shadowed by active imports/re-exports. The follow-up detector only matches one-line `from module import name`, but `cure.py` re-exports from `cure_sessions` with a parenthesized multi-line import. As a result, verifier evidence pointing at the stale duplicate definition is still sent to the LLM and can be treated as active still-open source evidence.

      **Assumptions / Preconditions:** A prior finding cites one of the duplicated `cure.py` definitions that is later shadowed by the multi-line `from cure_sessions import (...)` re-export.

      **Downgrade Factors:** If implementation resolves the active binding and verifies `cure_sessions.py`, or degrades the duplicate as `inactive_source_reference*`, the acceptance row can pass. A regression should use the parenthesized multi-line re-export form, not only the current one-line fixture.

      **Code Trail:** `_inactive_binding_reason()` scans following lines with `^\s*from module import (?P<names>.+)$` and splits the same-line names. For the real `from cure_sessions import (` line, `names` is only `(`, so `_resolve_session_relative_path` on later lines is never recognized. The current A18 test uses `from cure_sessions import resolve_completed_review` on one line and does not cover the production import shape.

      **Reproduction:** Targeted probe in the product worktree with `source_evidence_snippets=('cure.py:12953 stale duplicate _resolve_session_relative_path',)` returned `source_state=still_open`, `unavailable_reasons=[]`, `llm_calls=1`; expected `not_verifiable` with an `inactive_source_reference*` reason and no LLM call.

      </details>
  - Debt Friction: none
  - Next action: `/epic-story-resume cure-subsequent-pr-review 04` to add a red regression for the actual multi-line re-export and fix active-binding/dead-reference handling, then rerun focused verifier/source-truth/runtime suites plus public wrapper/static checks.

- 2026-06-11T16:57:39Z Review run by fresh maintainer child session
  - Decision: approve
  - Approval gate: pass
  - Product verdict: approve
  - Technical verdict: approve
  - Multipass review: completed via manual focused-pass substitute (child agent cannot spawn further children)
  - Prior review concerns: resolved (A1-A14 proof matrix finalized; strict/warn/off governor citation-ledger behavior hardened; A12/A13 linker no-link fallback fixed; A8 top-level-head memory staleness fixed)
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Epic contract drift: none (no CONTRACT.md present)
  - Status transition: 🔄 IN PROGRESS -> ✅ DONE
  - Sections reviewed: Purpose, Scope, Acceptance, Verification, Acceptance Proof Matrix, Surface / Branch Proof Matrix, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes, Progress Log, Session Handoff, MASTER tracker
  - Original intent checked: epic MASTER roadmap/constraints/FB-007/FB-010 and dependency Story 03 source-vs-discussion invariants; no external ticket/CONTRACT.md present
  - Traceability: forward trace complete for A1-A14; backward trace from changed runtime/control/prompt/memory/linker/verifier/test surfaces maps to Story 04 acceptance; no orphan surfaces found in sampled review
  - Code surfaces searched: `cure_subsequent_review/{runtime.py,memory_store.py,degraded_runtime.py,discussion_linker.py,llm_verifier.py,semantic_pipeline.py,source_truth.py,discussion_signals.py,control_plane.py,decision.py,contracts.py,landmark_trace.py}`, `cure.py` PR-flow callsites, `cure_runtime.py` config parser, prompt templates, Story 04 focused tests and public wrappers
  - Risk lenses reviewed: proof maturity, strict governor fail-open behavior, source-vs-discussion authority separation, linker no-link semantics, memory staleness/persistence, prompt fail-open, degraded fetch/retry, decision/intake single-fetch, LLM verifier/linker JSON normalization, config default/invalid behavior, landmark/golden drift, DDD module sizing
  - Finding closure: all previously blocking findings verified resolved by source inspection, regression tests, and targeted probes
  - Evidence quality: confirmed direct source/test reads and local command execution; inferred no external ticket intent beyond epic/story logs; unknown live PR #21 (optional/manual only)
  - Files reviewed: product worktree `/home/vscode/add-worktrees/CURe-cure-subsequent-pr-review-story-04-review-runtime-integration-guardrails-memory-trace`, plus coordination story/MASTER
  - Checks run: `python -m pytest tests/_subsequent_review_unit_runtime_packaging_unittest.py tests/_subsequent_review_unit_discussion_signals_unittest.py tests/_subsequent_review_unit_memory_store_unittest.py -q` ✅ 11 passed; focused Story 04 suites ✅ 35 passed, 5 subtests; `python -m pytest tests/test_subsequent_review.py tests/test_reviewflow_config_runtime_unittest.py tests/test_reviewflow_prompts_unittest.py -q` ✅ 286 passed, 28 subtests; `ruff check . && git diff --check && mypy` ✅; targeted strict-governor/no-link/memory probes ✅
  - Hypothesis triage:
    - suspicious surface: `Acceptance Proof Matrix`; result: no A1-A14 provisional rows remain and rows cite concrete source/test/check proof
    - suspicious surface: `prepare_review_runtime_pre_prompt`; result: strict validation rejects missing/malformed source/discussion citation ledgers and absent referenced rows before `governor_brief.md`, warn continues, off skips governor
    - suspicious surface: `discussion_signals.resolve_discussion_signals`; result: injected empty `group_ids` stays unlinked and carries linker rationale
    - suspicious surface: `ReviewMemoryStore.synthesize_resolved_source_row`; result: stale historical `heads[current_head]` replay is blocked unless top-level `last_seen_head` also matches current head
  - Key findings:
    - None. All fourteen acceptance criteria are covered by final proof rows, previous request-change items are resolved, and targeted/broad verification passed in the current tree.
  - Debt Friction: none
  - Next action: Story is complete locally. Run `/epic-story-pr cure-subsequent-pr-review 04` only if a GitHub PR stage is desired; otherwise proceed to epic wrap-up/next coordination.

- 2026-06-11T14:39:02Z Review run by fresh maintainer child session
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Multipass review: completed via manual focused-pass substitute (child agent cannot spawn further children)
  - Prior review concerns: resolved (prior plan blockers B1/B2/M3/M4 verified addressed in plan body and implementation seams)
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Epic contract drift: none (no CONTRACT.md present)
  - Status transition: 🔄 IN PROGRESS -> 🔄 IN PROGRESS
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes, Progress Log, Session Handoff, MASTER tracker
  - Original intent checked: epic MASTER roadmap/constraints/FB-007/FB-010; dependency Story 03 review log/source-vs-discussion invariants; no external ticket/CONTRACT.md present
  - Traceability: forward gaps (A8/A12/A13); backward complete for changed surfaces sampled
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: `cure_subsequent_review/{runtime.py,memory_store.py,degraded_runtime.py,discussion_linker.py,llm_verifier.py,semantic_pipeline.py,source_truth.py,discussion_signals.py,control_plane.py,decision.py,contracts.py,landmark_trace.py}`, `cure.py` PR-flow callsites, `cure_runtime.py` config parser, prompt templates, Story 04 test suites and wrapper
  - Risk lenses reviewed: source-vs-discussion authority separation, memory staleness/persistence, prompt fail-open, degraded fetch/retry, decision/intake single-fetch, LLM JSON normalization/fallbacks, config invalid/default behavior, landmark/golden drift, DDD module sizing
  - Finding closure: prior plan concerns checked as resolved; new implementation findings below
  - Evidence quality: confirmed direct source/test reads and two targeted reproductions; inferred no external ticket intent beyond epic/story logs; unknown live PR #21 (optional/manual only); provisional remaining broad runtime behavior beyond targeted tests
  - Files reviewed: product worktree `/home/vscode/add-worktrees/CURe-cure-subsequent-pr-review-story-04-review-runtime-integration-guardrails-memory-trace`, plus coordination story/MASTER
  - Checks run: `python -m pytest tests/test_subsequent_review.py tests/test_reviewflow_config_runtime_unittest.py tests/test_reviewflow_prompts_unittest.py -q` ✅ 282 passed, 28 subtests; `ruff check .` ✅; `mypy` ✅; `git diff --check` ✅; targeted Python reproductions for findings ✅ reproduced
  - Hypothesis triage:
    - suspicious surface: `discussion_signals.resolve_discussion_signals`; tentative issue: LLM `group_id:null` may be re-linked by legacy text fallback; next proof target: resolver code and targeted reproduction
    - suspicious surface: `ReviewMemoryStore.synthesize_resolved_source_row`; tentative issue: previous-head cache can replay despite `last_seen_head != current_head`; next proof target: memory-store code and targeted reproduction
    - suspicious surface: `prepare_review_runtime_pre_prompt`; tentative issue: strict governor may not validate every missing citation/ledger variant; next proof target: resume hardening after blocking A12/A8 fixes
  - Key findings:
    - Low-confidence LLM linker `group_id:null` is not preserved; resolver re-links by text fallback and can drive verifier skipping. Sources: `cure_subsequent_review/discussion_signals.py:106-110`, `story-04-review-runtime-integration-guardrails-memory-trace.md:136-137`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** A12/S15 require topical low-confidence matches to return no finding group. Current resolver treats an empty LLM `group_ids` result the same as no linker output and falls back to `_text_link_groups()`, so a by-design/pushback comment mentioning a title or path can become linked and satisfy the A13 skip matrix even though the LLM explicitly declined a confident finding ID.

      **Assumptions / Preconditions:** Production or tests supply an LLM linker that returns `group_ids: null`/empty with a skip-class signal and the comment text/path matches a finding by the legacy heuristic.

      **Downgrade Factors:** If implementation changes the linker result type to distinguish `no confident match` from `no linker available`, impact is removed.

      **Code Trail:** `LlmDiscussionLinker` normalizes null/empty group IDs to `()`; `resolve_discussion_signals()` then computes `linked_groups = link_result.group_ids or _text_link_groups(...)`; linked skip-class/untrusted rows are later consumed by the source verifier filter.

      **Reproduction:** Targeted script returned `DiscussionLinkResult(group_ids=(), signal_class=BY_DESIGN)` for body `This Parser null check is by design`; resolver emitted `group_ids=('G-0001',)`.

      </details>
    - Memory gate can replay an older resolved head even when top-level `last_seen_head` is different, violating the matching-head skip contract. Sources: `cure_subsequent_review/memory_store.py:198-209`, `story-04-review-runtime-integration-guardrails-memory-trace.md:132`

      <details open>
      <summary><b>Medium</b> severity · <b>Medium</b> likelihood</summary>

      **Why:** A8/S10/Locked Decisions say verifier skipping occurs only when `last_seen_head == current_head AND source_state == resolved_from_source`; entries from different heads must trigger full re-verification. The implementation consults the historical `heads[current_head]` map and will synthesize a memory-cache resolved row even when the current top-level `last_seen_head` records a later different head.

      **Assumptions / Preconditions:** A PR is reviewed at head A as resolved, later at head B as still open or otherwise different, then reviewed again with `current_head` equal to A (or a preserved historical head entry).

      **Downgrade Factors:** If the intended contract is changed to permit per-head historical replay, the story must update A8/S10/Locked Decisions and add proof for that behavior.

      **Code Trail:** `synthesize_resolved_source_row()` selects `candidate = heads.get(head)` before checking `last_seen_head`; the guard at line 207 only rejects when no historical candidate was selected.

      **Reproduction:** Targeted script updated memory at `head-a` with `resolved_from_source`, then `head-b` with `still_open`; querying `current_head='head-a'` returned a synthesized `resolved_from_source` memory-cache row despite top-level `last_seen_head='head-b'`.

      </details>
  - Debt Friction: none
  - Next action: `/epic-story-resume cure-subsequent-pr-review 04` to fix A12/A13 linker-null fallback and A8 memory-gate staleness, then rerun focused tests plus public wrapper/ruff/mypy.

- 2026-06-11T14:54:24Z Review run by fresh maintainer child session
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Multipass review: completed via manual focused-pass substitute (child agent cannot spawn further children)
  - Prior review concerns: resolved (A12/A13 linker no-link fallback and A8 top-level-head memory staleness fixed in source and covered by regressions)
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Epic contract drift: none (no CONTRACT.md present)
  - Status transition: 🔄 IN PROGRESS -> 🔄 IN PROGRESS
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes, Progress Log, Session Handoff, MASTER tracker
  - Original intent checked: epic MASTER roadmap/constraints/FB-007/FB-010, dependency Story 03 source-vs-discussion invariants; no external ticket/CONTRACT.md present
  - Traceability: forward gaps (proof matrix still provisional; A5 strict-governor citation completeness); backward complete for changed surfaces sampled
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: `cure_subsequent_review/{runtime.py,memory_store.py,degraded_runtime.py,discussion_linker.py,llm_verifier.py,semantic_pipeline.py,source_truth.py,discussion_signals.py,control_plane.py,decision.py,contracts.py,landmark_trace.py}`, `cure.py` PR-flow callsites, `cure_runtime.py` config parser, prompt templates, Story 04 tests and wrapper
  - Risk lenses reviewed: source-vs-discussion authority separation, memory staleness/persistence, prompt fail-open, degraded fetch/retry, decision/intake single-fetch, LLM JSON normalization/fallbacks, config invalid/default behavior, landmark/golden drift, DDD module sizing
  - Finding closure: previous blockers checked as resolved; source now honors injected empty linker `group_ids`, and memory replay now requires top-level `last_seen_head == current_head`; targeted regressions passed
  - Evidence quality: confirmed direct source/test reads plus focused/broad test reruns; inferred no external ticket intent beyond epic/story logs; unknown live PR #21 (optional/manual only); provisional proof-matrix maturity remains blocking
  - Files reviewed: product worktree `/home/vscode/add-worktrees/CURe-cure-subsequent-pr-review-story-04-review-runtime-integration-guardrails-memory-trace`, coordination story/MASTER
  - Checks run: `python -m pytest tests/_subsequent_review_unit_discussion_signals_unittest.py tests/_subsequent_review_unit_memory_store_unittest.py -q` ✅ 7 passed; `python -m pytest tests/_subsequent_review_unit_discussion_linker_unittest.py tests/_subsequent_review_unit_semantic_pipeline_unittest.py tests/_subsequent_review_unit_source_truth_unittest.py tests/_subsequent_review_unit_runtime_memory_unittest.py tests/_subsequent_review_unit_llm_verifier_unittest.py tests/_subsequent_review_unit_report_governor_unittest.py tests/_subsequent_review_unit_degraded_runtime_unittest.py tests/_subsequent_review_unit_runtime_packaging_unittest.py tests/_subsequent_review_acceptance_landmark_trace_unittest.py -q` ✅ 26 passed, 5 subtests; `python -m pytest tests/test_subsequent_review.py tests/test_reviewflow_config_runtime_unittest.py tests/test_reviewflow_prompts_unittest.py -q` ✅ 284 passed, 28 subtests; `ruff check .` ✅; `git diff --check` ✅; `mypy` ✅; targeted strict-governor reproduction ✅ reproduced
  - Hypothesis triage:
    - suspicious surface: `discussion_signals.resolve_discussion_signals`; tentative issue: explicit LLM no-link could fall back to text linking; next proof target: resolver code and no-link regression
    - suspicious surface: `ReviewMemoryStore.synthesize_resolved_source_row`; tentative issue: older per-head cache could replay despite advanced top-level head; next proof target: memory-store code and stale-head regression
    - suspicious surface: `Acceptance Proof Matrix`; tentative issue: all implementation proof rows remain provisional at review time; next proof target: story proof table
    - suspicious surface: `prepare_review_runtime_pre_prompt`; tentative issue: strict governor accepts missing source/discussion citation inputs; next proof target: runtime code and targeted reproduction
  - Key findings:
    - Acceptance Proof Matrix rows A1-A14 are still marked `provisional`, so the review proof contract is not final. Sources: `story-04-review-runtime-integration-guardrails-memory-trace.md:180`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** Story review approval requires final proof rows. The implementation may be substantially present, but the story still records every A1-A14 proof row as provisional, leaving the reviewer-facing proof contract unresolved.

      **Assumptions / Preconditions:** None.

      **Downgrade Factors:** Updating the matrix rows to `final` with actual evidence/commands, or recording explicit exclusions where applicable, resolves this gate issue.

      **Code Trail:** The Acceptance Proof Matrix table under `## Verification` still has `provisional` in the Proof Maturity column for A1 through A14.

      **Reproduction:** `rg -n "\\| A[0-9]+ \\| provisional" agent_coordination/epics/cure-subsequent-pr-review/story-04-review-runtime-integration-guardrails-memory-trace.md` returns all fourteen acceptance rows.

      </details>
    - Strict pre-review governor does not fail closed on missing citation ledgers; it can produce a success brief with `source citation unavailable`. Sources: `cure_subsequent_review/runtime.py:624`

      <details open>
      <summary><b>High</b> severity · <b>Medium</b> likelihood</summary>

      **Why:** A3/A5 require every governor row to cite source/discussion provenance, and `strict` mode must raise before prompt rendering when required ledgers/citations are missing. Current code checks only for `disposition_ledger.json`; missing `source_verification.json` / `discussion_signals.json` or missing row IDs become placeholder prose and a successful report-governor record, allowing incomplete prior-review context into the LLM prompt.

      **Assumptions / Preconditions:** A subsequent-review run has a disposition ledger but one of the cited source/discussion ledgers or row IDs is missing/malformed.

      **Downgrade Factors:** If the intended strict contract is narrowed to require only a disposition ledger, the story acceptance/TAP/proof matrix must be updated before approval.

      **Code Trail:** `prepare_review_runtime_pre_prompt()` raises in strict mode only when `disposition_ledger.json` is absent, then calls `build_governor_brief()`; `_citation_text()` returns `source citation unavailable` for missing citation rows, and the governor module is marked success whenever the brief is non-empty.

      **Reproduction:** A targeted script with only a minimal `disposition_ledger.json` and no `source_verification.json`/`discussion_signals.json` returned a `### Still Open` brief containing `Source: source citation unavailable` and records `[('review_context_packager', 'success'), ('report_governor', 'success')]` instead of raising.

      </details>
  - Debt Friction: none
  - Next action: `/epic-story-resume cure-subsequent-pr-review 04` to finalize the proof matrix and harden strict report-governor citation/ledger validation, then rerun focused governor/runtime tests plus the public wrapper/ruff/mypy.


- 2026-06-14T14:14:26Z Review run by fresh maintainer session
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Multipass review: completed
  - Prior review concerns: still_open
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Initiative contract drift: present
  - Status transition: unchanged: 🔵 IN PR -> 🔵 IN PR
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: initiative.md, feedback-log.md FB-039..FB-042, PR #22 metadata via `gh pr view 22` (`headRefOid=e305f826f3c0ece63be708f7df4b4f54c38b7658`, OPEN), dependency Story 01/02/03 contracts for stable identity, official-footer policy, and source/discussion separation
  - Traceability: forward gaps; backward gaps from untracked SVG and incomplete A20 proof surfaces
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: `git diff --stat/numstat`, `cure_subsequent_review/{control_plane.py,memory_store.py,runtime.py,source_truth.py,semantic_pipeline.py,disposition.py,llm_verifier.py}`, focused memory/runtime/report-governor/source/disposition/PR-flow tests, Story 04 OpenSpec artifacts, initiative feedback log, dependency story contracts
  - Risk lenses reviewed: persistence/staleness, source/discussion authority separation, official-footer policy provenance, prompt/report fail-open behavior, runtime cache/performance growth, manifest/log observability, input-boundary shape, dirty-main-tree/orphan artifact hygiene
  - Finding closure: prior A20 live-audit concerns are only partially closed locally; intake-time persistence and cache hit/miss telemetry now have focused proof, but policy-provenance replay, manifest/log verifier fan-out timing, proof/task finalization, and fresh PR #22 live audit remain open. A19 live proof regresses under same-head memory replay because policy provenance is dropped.
  - Evidence quality: confirmed by direct source/test/OpenSpec reads, focused-pass reviews, local reproductions for A19/A16, `gh pr view 22`, focused A20 tests (`31 passed`), public wrapper (`121 passed, 29 subtests`), regression subsets (`54 passed, 15 subtests`; public/config/prompt wrappers `305 passed, 29 subtests`), `ruff check .`, `git diff --check`, and `mypy`; inferred branch-name/remap friction from current branch/status; unknown fresh live PR #22 output after local A20 changes; provisional evidence is not used for approval
  - Files reviewed: `openspec/initiatives/cure-subsequent-pr-review/initiative.md`, `openspec/initiatives/cure-subsequent-pr-review/feedback-log.md`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,proposal.md,design.md,tasks.md,progress.md,reviews.md}`, dependency story files for Stories 01-03, `cure_subsequent_review/control_plane.py`, `cure_subsequent_review/memory_store.py`, `cure_subsequent_review/runtime.py`, `cure_subsequent_review/source_truth.py`, `cure_subsequent_review/semantic_pipeline.py`, `cure_subsequent_review/disposition.py`, `cure_subsequent_review/llm_verifier.py`, `tests/_subsequent_review_unit_memory_store_unittest.py`, `tests/_subsequent_review_unit_runtime_memory_unittest.py`, `tests/_subsequent_review_unit_report_governor_unittest.py`, `tests/_subsequent_review_unit_source_truth_unittest.py`, `tests/_subsequent_review_unit_disposition_arbiter_unittest.py`, `tests/_subsequent_review_integration_pr_flow_unittest.py`
  - Hypothesis triage:
    - suspicious surface: same-head source-verification memory replay; tentative issue: cached official-footer policy row may replay without FB-026 policy provenance and change disposition semantics; next proof target: `ReviewMemoryStore.synthesize_source_row()` provenance plus `arbitrate_dispositions()` policy override branch
    - suspicious surface: report-governor final-output demotion; tentative issue: `### Internal DA coverage (audit only)` can remain a top-level ordinary review section without warning; next proof target: `_demote_plain_internal_da_coverage_sections()` and `_disposition_map_warnings()`
    - suspicious surface: A20 proof contract and TAP-21 telemetry; tentative issue: local slice does not expose verifier fan-out timing/call count or finalize A20 tasks/proof rows; next proof target: manifest/log schema and A20 tasks/APM
    - suspicious surface: dirty main tree; tentative issue: untracked SVG is unrelated to the recorded main-tree target implementation; next proof target: `git status --short` and story out-of-scope clauses
  - Key findings:
    - A20/FB-042 proof contract remains unresolved: A20 is still `provisional`, all FB-039..FB-042 task rows are unchecked, progress records remaining policy-provenance/fan-out/live-audit work, and no manifest/log verifier call-count or timing surface was found. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:187`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/tasks.md:35`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/progress.md:92`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** Story review approval requires every proof row to be final and every named A20 variant/proof surface to be covered. The local slice covers useful cache behavior, but the story still records A20 as provisional and explicitly leaves verifier fan-out timing/observability and policy-provenance replay open.

      **Assumptions / Preconditions:** None.

      **Downgrade Factors:** If A20 is intentionally scoped to a smaller local slice, the story contract/tasks/proof matrix must be narrowed before approval; otherwise implementation must add the missing proof and mark rows complete/final.

      **Code Trail:** A20 requires hit/miss/bypass reasons plus verifier call count/timing in persisted surfaces; focused search found per-row cache telemetry but no manifest/log call-count or timing field, while the OpenSpec artifacts still list the work as pending.

      **Reproduction:** `rg -n "A20|FB-039|FB-040|FB-041|FB-042|verifier.*(count|timing)|fan"` shows `story.md` A20 provisional, unchecked A20 tasks, progress remaining work, and no implemented verifier fan-out/timing field.

      </details>
    - Same-head memory replay drops FB-026 official-footer policy provenance and changes `DA-0006`-style disposition semantics from `move_out_of_scope` to `confirm_resolved`. Sources: `cure_subsequent_review/source_truth.py:295`, `cure_subsequent_review/memory_store.py:391`, `cure_subsequent_review/disposition.py:31`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** A19 requires official-footer policy provenance to remain visible through source/disposition/governor artifacts so intended footer acceptance is not re-reported or misclassified. The cache hit reconstructs provenance without the cached `policy_override`, so downstream disposition no longer recognizes the policy-approved footer case.

      **Assumptions / Preconditions:** A prior same-head run stores an official-footer policy-approved source row in `cure_memory.json`, then a later run replays that row from memory.

      **Downgrade Factors:** Copying the cached policy provenance into replayed rows, or bypassing cache replay for footer-policy rows until provenance can be preserved, would remove this blocker.

      **Code Trail:** `verify_source_truth()` asks memory for a cached row before the fresh footer-policy branch. `ReviewMemoryStore.synthesize_source_row()` returns `provenance={source:"memory_cache", cache_status:"hit", ...}` without copying cached `policy_override`. `arbitrate_dispositions()` only moves the row out of scope when `source.provenance["policy_override"] == "official_footer_marker_acceptance"`.

      **Reproduction:** Local script: fresh footer-policy verification produced `resolved_from_source`, `policy_override=official_footer_marker_acceptance`, disposition `move_out_of_scope`; after storing and replaying from `ReviewMemoryStore`, the cached row was `resolved_from_source`, `policy_override=None`, `cache_status=hit`, disposition `confirm_resolved`.

      </details>
    - A16/FB-030 demotion can be bypassed by a top-level `### Internal DA coverage (audit only)` section, leaving raw DA rows in the visible report with no warning. Sources: `cure_subsequent_review/runtime.py:689`, `cure_subsequent_review/runtime.py:747`, `openspec/initiatives/cure-subsequent-pr-review/initiative.md:53`

      <details open>
      <summary><b>Medium</b> severity · <b>High</b> likelihood</summary>

      **Why:** The story and initiative require DA IDs/paths to be internal provenance, optional details, machine-readable metadata, comments, or an audit-only collapsible/appendix surface rather than ordinary reader-facing report text. The current demotion only catches the exact plain heading, while the warning check exempts headings containing `audit`.

      **Assumptions / Preconditions:** The review LLM emits a top-level `### Internal DA coverage (audit only)` section in final `review.md`.

      **Downgrade Factors:** If a top-level audit-only heading is considered an acceptable appendix by product decision, record that explicitly in the story; otherwise demote the heading to details/appendix or warn/degrade.

      **Code Trail:** `_demote_plain_internal_da_coverage_sections()` matches only `^### Internal DA coverage$`. `_disposition_map_warnings()` adds `prominent_internal_da_coverage` only when the heading lacks the word `audit`, so `### Internal DA coverage (audit only)` is neither demoted nor warned.

      **Reproduction:** Local script with a final `review.md` beginning with issue history followed by `### Internal DA coverage (audit only)` left that heading in place after `audit_review_report_after_review()` and wrote `warnings=[]`.

      </details>
    - The review target includes an unrelated untracked `docs/examples/subsequent-pr-run-flow.svg`, while the initiative/story explicitly keep SVG polish/redesign out of scope. Sources: `openspec/initiatives/cure-subsequent-pr-review/initiative.md:48`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:67`

      <details open>
      <summary><b>Low</b> severity · <b>High</b> likelihood</summary>

      **Why:** Review can proceed on a dirty main tree only when the dirty state is the implementation under review or explicitly recorded. The untracked SVG is not part of the recorded A20 cache-hardening slice and is out of scope for this story.

      **Assumptions / Preconditions:** The untracked SVG remains in the review target when PR sync or further review happens.

      **Downgrade Factors:** Operator confirmation that the SVG is intentionally unrelated and should remain untracked, or explicit removal/cleanup by the operator, reduces review risk. Do not remove it without operator approval.

      **Code Trail:** Initiative/story out-of-scope clauses exclude SVG polish/redesign; `git status --short` reports `?? docs/examples/subsequent-pr-run-flow.svg` outside the claimed product/test/OpenSpec A20 files.

      **Reproduction:** `git status --short -- docs/examples/subsequent-pr-run-flow.svg` returns the untracked file.

      </details>
    - Initiative tracker status is stale: `initiative.md` still lists Story 04 plan lane as `🟠 PLAN CHANGES REQUESTED` even though `story.md` and the plan-review log record `🟢 PLAN APPROVED`. Sources: `openspec/initiatives/cure-subsequent-pr-review/initiative.md:27`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:3`

      <details open>
      <summary><b>Info</b> severity · <b>High</b> likelihood</summary>

      **Why:** Review readiness depends on accurate coordination state. The story itself is reviewable because its local `Plan:` header is approved, but the initiative table can mislead the next operator or PR-stage command about whether planning is still blocked.

      **Assumptions / Preconditions:** Operators consult `initiative.md` as the initiative-level tracker before choosing the next command.

      **Downgrade Factors:** If the initiative table is intentionally stale and no command consumes it, this is coordination-only; otherwise synchronize it during the next resume/coordination pass.

      **Code Trail:** `story.md` is the authoritative status header for review, while `initiative.md` is the initiative candidate table used for context and story selection.

      **Reproduction:** `rg -n "story-04-review-runtime|Plan:" openspec/initiatives/cure-subsequent-pr-review/initiative.md openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md` shows the mismatch.

      </details>
  - Debt Friction: none
  - Next action: `/openspec-story-resume cure-subsequent-pr-review story-04-review-runtime-integration-guardrails-memory-trace` to fix A19 cache replay policy provenance, A16 DA demotion bypass, A20 fan-out/timing/proof-task gaps, synchronize initiative status, and explicitly handle the unrelated SVG before re-review.

## Live-audit remap review note

- 2026-06-14T10:46:40Z OpenSpec provenance repair: synthetic Story 05 is superseded/remapped and its OpenSpec files have been removed. Review Story 04 for FB-030 (consumer DA coverage demotion), FB-031 (memory replay identity), FB-034 (linker cache group identity), runtime-FB-035 (verifier citation enforcement), FB-036 (linker runtime policy/add-dir/config), and FB-038 (planner-abort prior-review guardrails). Story 04 remains `🔵 IN PR`; implementation is on PR #22, but fresh live proof is still pending.

- 2026-06-14T15:25:11Z Review run by fresh maintainer session
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Multipass review: completed
  - Prior review concerns: still_open
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Initiative contract drift: present
  - Status transition: unchanged: 🔄 IN PROGRESS -> 🔄 IN PROGRESS
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: initiative.md, Story 04 story/proposal/design/tasks/progress/reviews, PR #22 via `gh pr view 22` (`headRefOid=e305f826f3c0ece63be708f7df4b4f54c38b7658`, OPEN/CLEAN), dependency Story 02 footer-policy context, dependency Story 03 source/discussion separation and five-action arbiter contract; no separate Jira/ticket found beyond PR #22/initiative feedback.
  - Traceability: forward gaps; backward gaps
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: `git status --short`, `git diff --numstat`, `cure_subsequent_review/{contracts.py,control_plane.py,memory_store.py,runtime.py,semantic_pipeline.py,source_truth.py,disposition.py}`, prompt templates `prompts/default.md` and `prompts/mrereview_gh_local*.md`, focused source/memory/report-governor/runtime/control-plane/PR-flow tests, Story 02/03 dependency story anchors, PR #22 metadata.
  - Risk lenses reviewed: prompt/template fail-open and reader-facing report shape; source/discussion authority separation; official-footer policy provenance; persistence/staleness and source-verification cache replay; verifier fan-out observability; dirty main-tree/out-of-scope artifact hygiene; PR/live-audit proof boundary.
  - Finding closure: prior A19 same-head memory-replay provenance loss is resolved for cached rows by preserving `policy_override` and focused regressions, but a fresh/non-cache official-footer path with untrusted skip-class discussion still bypasses the policy override; prior A16 exact/audit-only demotion is resolved in runtime, but prompt templates still request the over-prominent DA heading; prior A20/FB-042 telemetry is locally supported by source-ledger/manifest/summary observability, but FB-040 matrix and final proof rows remain open; unrelated untracked SVG remains untouched/out-of-scope.
  - Evidence quality: confirmed direct source/story/test/PR reads, focused multipass children verified against primary anchors, targeted official-footer discussion-skip reproduction, focused pytest subsets (`24 passed, 5 subtests`; `26 passed`), `gh pr view 22`; inferred none material; unknown fresh PR #22 live output after local dirty repairs; provisional A16/A20 live-proof rows still affect approval.
  - Files reviewed: `openspec/initiatives/cure-subsequent-pr-review/initiative.md`, dependency `openspec/changes/story-02-auto-infer-subsequent-review-mode/story.md`/Story 03 anchors, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,proposal.md,design.md,tasks.md,progress.md,reviews.md}`, `cure_subsequent_review/contracts.py`, `cure_subsequent_review/control_plane.py`, `cure_subsequent_review/memory_store.py`, `cure_subsequent_review/runtime.py`, `cure_subsequent_review/semantic_pipeline.py`, `cure_subsequent_review/source_truth.py`, `cure_subsequent_review/disposition.py`, `prompts/default.md`, `prompts/mrereview_gh_local*.md`, `tests/_subsequent_review_unit_source_truth_unittest.py`, `tests/_subsequent_review_unit_memory_store_unittest.py`, `tests/_subsequent_review_unit_report_governor_unittest.py`, `tests/_subsequent_review_unit_runtime_memory_unittest.py`, `tests/_subsequent_review_functional_control_plane_unittest.py`, `tests/_subsequent_review_integration_pr_flow_unittest.py`.
  - Hypothesis triage:
    - suspicious surface: source-truth official-footer policy branch with linked discussion signals; tentative issue: untrusted skip-class discussion can preempt the policy override and re-report the footer-authorship false positive; next proof target: `verify_source_truth()` branch order plus minimal `PUSHBACK` reproduction.
    - suspicious surface: final-output prompt templates; tentative issue: templates still require top-level `### Internal DA coverage` before normal sections, fighting the FB-030 demotion model; next proof target: prompt lines and report-governor demotion tests.
    - suspicious surface: A20 terminal non-reportable replay matrix; tentative issue: local cache slice covers duplicate/out-of-scope-style replay but not the full named outcome matrix; next proof target: `tasks.md` FB-040 row, safe-terminal whitelist, memory-store tests.
    - suspicious surface: dirty main tree; tentative issue: untracked SVG could be accidentally staged even though SVG polish/redesign is out of scope; next proof target: `git status --short` and story/initiative out-of-scope clauses.
  - Key findings:
    - Fresh official-footer policy findings linked only to untrusted skip-class discussion bypass the FB-026 policy override and still re-report. Sources: `cure_subsequent_review/source_truth.py:348`, `cure_subsequent_review/source_truth.py:382`, `cure_subsequent_review/disposition.py:36`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** A19 requires official CURe footer acceptance to remain policy-approved regardless of author/login, and Story 03 keeps discussion separate from source truth. The current non-cache path checks the untrusted discussion skip before the footer-policy branch, so a footer-authorship false positive linked to `PUSHBACK`/`BY_DESIGN`-style untrusted discussion becomes `still_open` with no `policy_override` and the arbiter emits `re_report`.

      **Assumptions / Preconditions:** A prior footer-authorship false-positive group has linked discussion rows where all signals are untrusted skip classes, and the row is not already served by memory cache.

      **Downgrade Factors:** If the story explicitly excludes discussion-linked footer-policy groups from A19, or if a prior phase guarantees these groups never receive skip-class discussion rows, impact would narrow; no such exclusion/guarantee is recorded.

      **Code Trail:** `verify_source_truth()` appends `_skipped_by_discussion_row()` and `continue`s when `_discussion_skips_source_verifier()` is true, before calling `_footer_marker_authorship_policy_finding()`. `arbitrate_dispositions()` only uses `MOVE_OUT_OF_SCOPE` for official-footer policy when `source.provenance["policy_override"] == "official_footer_marker_acceptance"`; otherwise a still-open source row falls through to `RE_REPORT`.

      **Reproduction:** A minimal in-memory probe with the same footer-authorship title/evidence as the A19 regression plus one untrusted `PUSHBACK` discussion row produced `provider_calls=0`, `source_state=still_open`, `policy_override=None`, `unavailable_reasons=('source_verification_skipped_by_discussion_signals',)`, and disposition `re_report`; expected `resolved_from_source` with `policy_override=official_footer_marker_acceptance` and `move_out_of_scope`.

      </details>
    - Final PR-review prompt templates still instruct the model to emit prominent top-level `### Internal DA coverage` before normal review sections. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:56`, `prompts/default.md:20`, `prompts/mrereview_gh_local.md:18`

      <details open>
      <summary><b>Medium</b> severity · <b>High</b> likelihood</summary>

      **Why:** FB-030/A16 says raw DA rows must be internal/provenance-only and removed from ordinary visible body or demoted to an audit-only surface. Runtime demotion now catches exact/audit-only headings after generation, but the final prompt still asks the LLM to produce exactly the over-prominent top-level heading that the story says is too consumer-facing.

      **Assumptions / Preconditions:** A subsequent-aware final/synthesis prompt includes a prior-review brief with the required issue-history marker.

      **Downgrade Factors:** If post-generation demotion is the intended sole control, the story should record that prompt guidance may still ask for top-level DA coverage; otherwise the prompt should request a collapsible/audit appendix directly.

      **Code Trail:** Story A16/FB-030 requires DA demotion; `runtime.py` demotes matching headings post hoc and tests pass, but `default.md` and the maintained PR templates still say `Include ### Internal DA coverage with every DA-* status before the normal review sections`.

      **Reproduction:** `rg -n "Include `### Internal DA coverage`" prompts/default.md prompts/mrereview_gh_local*.md` returns the maintained final/synthesis prompt lines while `tests/_subsequent_review_unit_report_governor_unittest.py` proves runtime has to demote that generated shape afterward.

      </details>
    - FB-040 terminal non-reportable replay matrix is still incomplete, leaving A20 approval proof unresolved. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/tasks.md:36`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:120`, `cure_subsequent_review/memory_store.py:25`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** A20/TAP-21 names a matrix across `resolved_from_source`, duplicate, out-of-scope, dropped/not-relevant, still-open, source-unknown, and not-verifiable outcomes. The task row remains unchecked and explicitly says the broader literal matrix remains unchecked; code currently safe-replays only `suppress_duplicate` and `move_out_of_scope`, and focused tests do not cover the full named matrix.

      **Assumptions / Preconditions:** None.

      **Downgrade Factors:** If the team intentionally narrows A20 to duplicate/out-of-scope only, update the story/tasks/proof rows with explicit exclusions before approval.

      **Code Trail:** The story requires terminal replay to be proven or explicitly excluded for each named outcome. `tasks.md` keeps FB-040 open; `_SAFE_TERMINAL_NON_REPORTABLE_DISPOSITIONS` contains only two action categories, and the focused memory tests prove duplicate terminal replay plus policy-source replay but not dropped/not-relevant, source-unknown, not-verifiable, or a literal out-of-scope matrix case.

      **Reproduction:** `rg -n "FB-040|_SAFE_TERMINAL_NON_REPORTABLE_DISPOSITIONS|source-unknown|not-verifiable|dropped" tasks.md story.md cure_subsequent_review/memory_store.py tests/_subsequent_review_unit_memory_store_unittest.py` shows the unchecked FB-040 row and no full literal matrix coverage.

      </details>
    - Dirty main tree still includes an unrelated untracked SVG that is explicitly out of scope. Sources: `openspec/initiatives/cure-subsequent-pr-review/initiative.md:48`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:67`

      <details open>
      <summary><b>Low</b> severity · <b>High</b> likelihood</summary>

      **Why:** Review can proceed on the dirty main tree because Story 04 implementation changes are there, but broad staging/PR-sync would risk accidentally including an unrelated SVG. The initiative and story both exclude SVG polish/redesign.

      **Assumptions / Preconditions:** The untracked file remains present during future commit or PR-sync work.

      **Downgrade Factors:** Operator confirmation that the SVG should remain untracked, or explicit cleanup/staging discipline during the next resume/PR step, reduces this to hygiene only.

      **Code Trail:** `git status --short` reports `?? docs/examples/subsequent-pr-run-flow.svg`; initiative/story scope excludes SVG polish/redesign; progress also says the SVG is unrelated and untouched.

      **Reproduction:** `git status --short -- docs/examples/subsequent-pr-run-flow.svg` returns the untracked SVG.

      </details>
  - Debt Friction: none
  - Next action: `/openspec-story-resume cure-subsequent-pr-review story-04-review-runtime-integration-guardrails-memory-trace` to fix the A19 branch-order regression, align final prompt guidance with A16/FB-030 demotion, complete or explicitly narrow FB-040/A20 matrix proof, and keep/exclude the unrelated SVG from any future staging.

- 2026-06-14T16:05:21Z Review run by fresh maintainer session
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Multipass review: completed
  - Prior review concerns: resolved
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Initiative contract drift: none
  - Status transition: 🔄 IN PROGRESS -> 🔄 IN PROGRESS
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: initiative/story/proposal/design/tasks/progress/reviews, dependency Story 02/03 contracts, and PR #22 metadata/live-audit context from the completed multipass review; no separate Jira/ticket source found.
  - Traceability: forward gaps; backward gaps
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: `git status --short`, `git diff --numstat`, `cure_subsequent_review/{runtime.py,control_plane.py,source_truth.py,disposition.py,memory_store.py,semantic_pipeline.py,contracts.py}`, prompt templates `prompts/default.md` and `prompts/mrereview_gh_local*.md`, focused source/memory/report-governor/runtime/control-plane/PR-flow tests, OpenSpec artifacts, dependency story anchors, PR metadata.
  - Risk lenses reviewed: prompt/template fail-open, report-governor audit fail-open, module override/disabled path, persistence/cache lifecycle, source/discussion separation, verifier fan-out/cache observability, dirty-tree hygiene; fresh PR #22 live audit remains outside this local approval proof.
  - Finding closure: prior 15:25 A19 official-footer/discussion-skip concern is resolved locally by branch-order/source-truth tests; prior A16 prompt wording concern is resolved locally by audit/provenance-only prompt guidance; prior A20/FB-040 matrix concern is locally represented by checked task rows, memory tests, and telemetry/fan-out surfaces. A16/A20 proof rows remain provisional only for a fresh PR #22 live audit, and are not used as the approval basis while the two new local blockers below remain open.
  - Evidence quality: confirmed direct story/source/test reads, focused multipass child results checked against primary anchors, parent reproductions for both blockers, and focused test/static-check reports from the completed review; inferred none material; unknown fresh PR #22 live audit after local changes; provisional A16/A20 live-proof rows noted but not used for approval.
  - Files reviewed: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,proposal.md,design.md,tasks.md,progress.md,reviews.md}`, `openspec/initiatives/cure-subsequent-pr-review/initiative.md`, dependency Story 02/03 anchors, `cure_subsequent_review/{runtime.py,control_plane.py,source_truth.py,disposition.py,memory_store.py,semantic_pipeline.py,contracts.py}`, `prompts/default.md`, `prompts/mrereview_gh_local*.md`, `tests/_subsequent_review_unit_report_governor_unittest.py`, `tests/_subsequent_review_unit_memory_store_unittest.py`, `tests/_subsequent_review_unit_runtime_memory_unittest.py`, `tests/_subsequent_review_functional_control_plane_unittest.py`, `tests/_subsequent_review_unit_source_truth_unittest.py`, `tests/_subsequent_review_integration_pr_flow_unittest.py`.
  - Hypothesis triage:
    - suspicious surface: report-governor internal DA coverage audit; tentative issue: expected/actual `DA-*` maps are parsed but never compared, so omissions/contradictions can publish cleanly; next proof target: `_disposition_map_warnings()` and `tests/_subsequent_review_unit_report_governor_unittest.py` gap assertions/reproduction.
    - suspicious surface: intake-time review-memory persistence; tentative issue: `review_memory_store` writes artifacts even when the module override disables that module; next proof target: `SubsequentReviewConfig.module_enabled()` versus the unconditional `update_review_memory_after_intake()` call path.
    - suspicious surface: dirty main tree hygiene; tentative issue: unrelated untracked SVG could be accidentally staged even though SVG polish is out of scope; next proof target: `git status --short` and story/initiative out-of-scope clauses.
  - Key findings:
    - A17 internal DA coverage and contradiction detection is missing from the post-review governor. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:116`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:117`, `cure_subsequent_review/runtime.py:624`, `cure_subsequent_review/runtime.py:669`, `cure_subsequent_review/runtime.py:747`, `tests/_subsequent_review_unit_report_governor_unittest.py:296`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** A16/A17 require the governor to account for every internal `DA-*` row and warn/degrade on missing or contradicted DA coverage without blocking publication. The current governor can accept a final report that omits one DA row and contradicts another with no DA-specific warnings, so the provenance/audit contract can fail open.

      **Assumptions / Preconditions:** The run has a disposition ledger with `DA-*` rows and the final review includes enough prior-issue-history text for the human-awareness check to pass while its internal DA appendix/details omit or contradict one or more rows.

      **Downgrade Factors:** If the story is explicitly changed to make internal DA row comparison out of scope, impact would become contract drift instead of an implementation blocker; no such exclusion is recorded.

      **Code Trail:** `_expected_disposition_map()` reads expected `DA-*` statuses from `disposition_ledger.json`, and `_actual_disposition_map()` can parse statuses from `review.md`, but `_disposition_map_warnings()` only delegates issue-history warnings and flags a prominent top-level `### Internal DA coverage` heading. It never compares the two maps for missing rows or status contradictions. The current unit test cements the gap by asserting `missing_internal_da_coverage:DA-0002` and `contradicted_internal_da_coverage:DA-0001` are absent.

      **Reproduction:** A temp post-review audit with a valid leading `### Prior Review Issue History`, collapsible DA details that omit `DA-0002` and contradict `DA-0001`, and an auditor returning demonstrated awareness wrote `report_governor_result.json` with `status=success` and `warnings=[]`; expected degraded/warnings for the missing and contradicted DA rows.

      </details>
    - A1/A11 module override support is broken for `review_memory_store`. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:101`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:111`, `cure_subsequent_review/control_plane.py:44`, `cure_subsequent_review/control_plane.py:242`, `cure_subsequent_review/control_plane.py:246`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** A1 makes module overrides part of the first-class runtime contract, and A11 requires disabled-module behavior to remain artifact-free/backward compatible. Intake currently writes review-memory artifacts whenever a memory-store object is passed, even if `REVIEW_MEMORY_STORE` is explicitly disabled, so operators cannot rely on the disabled path.

      **Assumptions / Preconditions:** Subsequent review is enabled overall, a caller supplies a memory-store object with `update_findings`/`path`, and `module_overrides` sets `SubsequentReviewModule.REVIEW_MEMORY_STORE` to `ModuleStatus.DISABLED`.

      **Downgrade Factors:** If callers never pass `memory_store` when the module override is disabled, the observed failure narrows to a defensive-contract gap; the story nevertheless requires module override support and disabled handling at the runtime boundary.

      **Code Trail:** `SubsequentReviewConfig.module_enabled()` correctly returns `False` for an explicit disabled override, and manifest defaults use that helper. But after `run_semantic_pipeline()`, `run_subsequent_review_intake()` checks only whether `memory_store` has `update_findings` and `path`, then unconditionally calls `update_review_memory_after_intake()` and records `REVIEW_MEMORY_STORE` with the returned status. The disabled override is not consulted at this persistence boundary.

      **Reproduction:** A focused intake reproduction with `module_overrides={SubsequentReviewModule.REVIEW_MEMORY_STORE: ModuleStatus.DISABLED}` still produced manifest `review_memory_store.status = success`, `artifact_path = .../cure_memory.json`, and wrote the memory file; expected `disabled` status and no memory artifact.

      </details>
  - Debt Friction: none
  - Next action: `/openspec-story-resume cure-subsequent-pr-review story-04-review-runtime-integration-guardrails-memory-trace` to add failing regressions and fixes for A17 DA coverage/contradiction detection and `REVIEW_MEMORY_STORE` module override handling, then rerun focused report-governor/control-plane suites, the public subsequent-review wrapper, `ruff check .`, `git diff --check`, and `mypy`.

- 2026-06-14T17:23:48Z Review run by fresh maintainer session
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Multipass review: completed
  - Prior review concerns: resolved
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Initiative contract drift: none
  - Status transition: 🔄 IN PROGRESS -> 🔄 IN PROGRESS
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: initiative/story/proposal/design/tasks/progress/reviews, dependency Story 02/03 contracts, and PR #22 live-audit context from prior review artifacts; no separate Jira/ticket source found.
  - Traceability: forward gaps; backward gaps
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: `git status --short`, `git diff --stat`, `cure_subsequent_review/{degraded_runtime.py,github_history.py,decision.py,runtime.py,memory_store.py,semantic_pipeline.py,source_truth.py,control_plane.py}`, `_pr_flow_impl` call sites in `cure.py`, `cure_flows.py`, `prompts/mrereview_gh_local_followup.md`, focused runtime/memory/governor/prompt tests, and OpenSpec proof rows.
  - Risk lenses reviewed: degraded API/operator gating, decision/intake single-fetch reuse, prompt/template fail-open behavior, strict/warn governor citation fail-open behavior, stable cache identity and replay persistence, source/discussion separation, dirty-tree hygiene, and pending PR #22 live-audit evidence.
  - Finding closure: prior 16:05 A17 DA-coverage/contradiction and A1/A11 `review_memory_store` override blockers are resolved in the current local tree by source/test evidence and focused regression suites. New blockers below remain open; A16/A20 live proof rows are still provisional and not used as the sole failure basis.
  - Evidence quality: confirmed direct source/story/test reads, source-anchor grep, parent reproductions for all four blockers, completed focused-pass reports, and focused/broad command results; inferred none material; unknown fresh PR #22 live audit after current local changes; provisional A16/A20 live-proof rows remain at `story.md:183` and `story.md:187`.
  - Files reviewed: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,proposal.md,design.md,tasks.md,progress.md,reviews.md}`, `openspec/initiatives/cure-subsequent-pr-review/initiative.md`, `cure_subsequent_review/{degraded_runtime.py,github_history.py,decision.py,runtime.py,memory_store.py,semantic_pipeline.py,source_truth.py,control_plane.py}`, `cure.py`, `cure_flows.py`, `prompts/mrereview_gh_local_followup.md`, `tests/_subsequent_review_unit_runtime_packaging_unittest.py`, focused Story 04 runtime/memory/governor/prompt tests, and prior PR #22 live-audit artifacts/notebook findings.
  - Hypothesis triage:
    - suspicious surface: degraded discussion fetch controller; tentative issue: metadata-only `thread_state_unavailable` degradation can prompt skip and erase valid official-footer review signals; next proof target: controller degraded predicate, `_skipped_discussion()`, and decision remote-marker handling.
    - suspicious surface: review-memory stable identity replay; tentative issue: synthesized cache rows persist their identity nested under provenance and poison later stable-identity lookups; next proof target: `_stable_identity_from_row()`, `update_findings()`, and synthesized replay provenance.
    - suspicious surface: report-governor pre-prompt citation validation; tentative issue: strict/warn mode accepts disposition rows with omitted source/discussion row ids and emits unavailable citations as a successful brief; next proof target: `_strict_governor_validate_citation_ledgers()`, `_citation_text()`, and pre-prompt success records.
    - suspicious surface: follow-up/resume prompt rendering; tentative issue: supported subsequent-review prompt paths omit or clear `$PRIOR_REVIEW_BRIEF`, bypassing issue-history/footer-policy guardrails; next proof target: `_pr_flow_impl` follow-up/resume extra-vars and `cure_flows.render_prompt()` placeholder cleanup.
  - Key findings:
    - A7/A9 degraded discussion control over-gates metadata-only `thread_state_unavailable`, and skip can erase valid official-footer signals. Sources: `cure_subsequent_review/degraded_runtime.py:108`, `cure_subsequent_review/github_history.py:146`, `cure_subsequent_review/decision.py:88`, `cure_subsequent_review/decision.py:161-181`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** A7 only requires operator retry/skip/abort for real degraded discussion availability/payload failures, and A9 requires the accepted discussion evidence to be reused consistently. A metadata-only thread-state gap can currently trigger the controller, and a skip replaces the artifact with zero events, so a valid official-footer prior CURe review can disappear and subsequent-review intake can be disabled.

      **Assumptions / Preconditions:** The fetched PR discussion contains an official-footer CURe review marker, the only degraded reason is `thread_state_unavailable`, and the operator/noninteractive controller chooses the skip path with no completed-session fallback evidence.

      **Downgrade Factors:** If `thread_state_unavailable` is intentionally reclassified as a blocking availability degradation, or skipped artifacts preserve the original positive events for decision/intake, the impact would narrow. The current Story 04/Story 02 contract treats thread state as metadata and official footers as valid provenance.

      **Code Trail:** GitHub normalization emits `thread_state_unavailable` for missing thread metadata, while the decision layer separately lists that reason as non-enabling metadata. The controller nevertheless treats any `ModuleStatus.DEGRADED` artifact as dialog-worthy. `_skipped_discussion()` then returns a degraded artifact with empty events, and `decide_subsequent_review()` disables when `operator_skipped_degraded_discussion` is present and `remote_cure_markers == 0`.

      **Reproduction:** Parent reproduction with one official-footer issue comment and only `thread_state_unavailable`: calling `decide_subsequent_review()` directly enabled with `cure_pr_discussion_found`; routing through the controller noninteractive skip produced zero events and then disabled with `no_prior_review_signals`.

      </details>
    - A20 stable-identity cache replay can self-poison after replay persistence. Sources: `cure_subsequent_review/memory_store.py:56`, `cure_subsequent_review/memory_store.py:118`, `cure_subsequent_review/memory_store.py:222`, `cure_subsequent_review/memory_store.py:401`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** A20's cache-hardening goal is to prevent repeated verifier storms by replaying same-head rows through stable finding identity/fingerprint/source references. A cache hit that is persisted again can lose that identity, making the next identical same-head run miss and re-run verification.

      **Assumptions / Preconditions:** A same-head source-verification row is replayed from memory and then passed back through memory update/persistence for the same PR/head.

      **Downgrade Factors:** If production never persists synthesized replay rows, the self-poisoning path narrows; the runtime stores memory after intake/review and the memory store API accepts the synthesized `SourceVerificationRow`, so the contract needs this path safe.

      **Code Trail:** `group_identity_for_cache()` builds the current stable identity from the reconciliation group. `update_findings()` recomputes stable identity from each serialized source row via `_stable_identity_from_row()`, which only reads top-level `provenance["fingerprint"]`, `inspected_source_refs`, and `current_source_citations`. Synthesized replay rows store the current identity under nested `provenance["stable_identity"]`; after persistence, the head entry can therefore contain empty fingerprint/digests and fail the next `_stable_identity_matches()` check.

      **Reproduction:** Parent reproduction: fresh row with fingerprint `fp1` produced a replay hit; persisting the replayed row overwrote the stored stable identity to empty fingerprint/digests; the next same-head lookup for the same finding returned `None` instead of a cache hit.

      </details>
    - A3/A5/A6 strict/warn governor citation handling fails open when disposition rows omit source or discussion row ids. Sources: `cure_subsequent_review/runtime.py:318`, `cure_subsequent_review/runtime.py:348-366`, `cure_subsequent_review/runtime.py:1058-1077`, `tests/_subsequent_review_unit_runtime_packaging_unittest.py:213-231`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** A3/A6 require every governor row to carry disposition plus source/discussion provenance, and A5 strict mode must fail closed on incomplete pre-review ledgers before prompt rendering. If a disposition row omits the row ids, strict mode currently has nothing to validate and still renders a non-empty successful brief with unavailable citations.

      **Assumptions / Preconditions:** The disposition ledger has one or more reportable rows whose `source_verification_row_id` is blank/missing and whose `discussion_signal_row_ids` is empty/missing, rather than referencing missing concrete rows.

      **Downgrade Factors:** If the story is explicitly narrowed to permit provenance-free disposition rows in strict mode, this becomes a contract gap rather than implementation blocker. Current acceptance text says every row cites disposition plus source/discussion provenance and strict mode raises on missing required inputs.

      **Code Trail:** `_strict_governor_validate_citation_ledgers()` discards empty source row ids and only validates discussion ids that are present, so omitted ids skip validation entirely. `_citation_text()` falls back to `source citation unavailable`, `_discussion_text()` renders `none`, and `prepare_review_runtime_pre_prompt()` records `report_governor` success as long as the brief string is non-empty. The warn-mode test suite currently codifies the same unavailable-citation success path.

      **Reproduction:** Parent reproduction in strict mode with a `re_report` disposition row whose `source_verification_row_id` was blank and with no discussion ids succeeded and emitted `Source: source citation unavailable. Discussion: none.`; expected strict pre-prompt failure (or at least a degraded/warn-only path outside strict).

      </details>
    - A3/A16/A19 follow-up and resume prompt paths can silently drop `$PRIOR_REVIEW_BRIEF`. Sources: `cure.py:6565`, `cure.py:11235-11240`, `cure.py:11529-11535`, `cure.py:12780-12784`, `cure_flows.py:1489`, `prompts/mrereview_gh_local_followup.md:24-28`

      <details open>
      <summary><b>High</b> severity · <b>Medium</b> likelihood</summary>

      **Why:** Story 04 requires the governor brief to reach all subsequent-aware PR review prompt paths so prior-review issue history, DA audit coverage, and official-footer policy context influence follow-up/resume output. Several supported follow-up/resume render paths either hard-code an empty brief or omit the variable, and the prompt renderer silently strips unresolved placeholders, so these guardrails can vanish without an operator-visible failure.

      **Assumptions / Preconditions:** A subsequent-aware run enters a completed-review resume step, resume plan/synthesis, or follow-up path after pre-prompt runtime has produced a non-empty prior-review brief.

      **Downgrade Factors:** If those paths are explicitly moved out of subsequent-aware support, the product impact narrows; the story currently lists follow-up/resume templates and paths as supported prompt-injection surfaces.

      **Code Trail:** One completed resume step passes `"PRIOR_REVIEW_BRIEF": ""` even though a prior brief can exist. Resume plan, resume synthesis, and follow-up `extra_vars` include previous-review/head/output paths but no `PRIOR_REVIEW_BRIEF`. `render_prompt()` then removes any leftover `$PRIOR_REVIEW_BRIEF` token. The maintained follow-up template contains the brief placeholder and its issue-history/final-output override guidance, but missing/empty vars make that section disappear.

      **Reproduction:** Rendering the follow-up/resume paths with a non-empty runtime brief available but no `PRIOR_REVIEW_BRIEF` extra var produces prompts without the prior-review brief or output override; no error is raised because `cure_flows.render_prompt()` clears the placeholder.

      </details>
  - Debt Friction: none
  - Next action: `/openspec-story-resume cure-subsequent-pr-review story-04-review-runtime-integration-guardrails-memory-trace` to add red regressions/fixes for the four blockers above, keep the unrelated `docs/examples/subsequent-pr-run-flow.svg` out of scope, then rerun focused runtime/memory/governor/prompt suites, the public subsequent-review wrapper, `ruff check .`, `git diff --check`, and `mypy`.

- 2026-06-14T18:04:59Z Review run by fresh maintainer session
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Multipass review: completed
  - Prior review concerns: still_open
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Initiative contract drift: none
  - Status transition: 🔄 IN PROGRESS -> 🔄 IN PROGRESS
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: initiative/story/proposal/design/tasks/progress/reviews and PR #22 live-audit context recorded in story/progress; no separate Jira/ticket source found.
  - Traceability: forward gaps; backward gaps
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: `git status --short`, `git diff --stat`, OpenSpec proof rows/tasks/progress/reviews, `cure_subsequent_review/{degraded_runtime.py,decision.py,control_plane.py,runtime.py,memory_store.py,semantic_pipeline.py,source_truth.py}`, `_pr_flow_impl` in `cure.py`, prompt propagation callsites/templates, and focused Story 04 runtime/memory/governor/degraded/prompt tests.
  - Risk lenses reviewed: module override disabled-path fail-open, post-review persistence lifecycle, proof-maturity/live-audit gate, degraded discussion operator gating, stable cache identity, governor citation fail-closed/warn behavior, prompt/template fail-open, DA coverage audit, dirty-tree hygiene.
  - Finding closure: latest 17:23 blockers for metadata-only degraded discussion gating, stable-identity replay persistence, omitted governor citation IDs, and `$PRIOR_REVIEW_BRIEF` follow-up/resume propagation appear locally resolved by direct source/test anchors. Prior 16:05 A17 DA coverage/contradiction detection appears locally resolved. Prior 16:05 `review_memory_store` disabled override is only partially resolved: intake skips the write, but the post-review memory refresh path still overwrites a disabled manifest row and writes shared memory.
  - Evidence quality: confirmed direct source/test/OpenSpec reads, focused child pass outputs verified against primary anchors, and a parent temp-dir reproduction of the post-review disabled-memory fail-open; inferred none material; unknown fresh PR #22 live audit after current local changes; provisional A16/A20 live-proof rows remain.
  - Files reviewed: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,proposal.md,design.md,tasks.md,progress.md,reviews.md}`, `openspec/initiatives/cure-subsequent-pr-review/initiative.md`, `cure_subsequent_review/{degraded_runtime.py,decision.py,control_plane.py,runtime.py,memory_store.py,semantic_pipeline.py,source_truth.py}`, `cure.py`, relevant prompt templates, `tests/_subsequent_review_unit_{degraded_runtime,memory_store,runtime_memory,runtime_packaging,report_governor,source_truth}_unittest.py`, `tests/_subsequent_review_functional_control_plane_unittest.py`, `tests/_reviewflow_unittest_{prompt_session_impl,grounding_impl}.py`.
  - Hypothesis triage:
    - suspicious surface: post-review review-memory refresh; tentative issue: disabled `review_memory_store` manifest/config state is ignored after final `review.md`, causing artifact writes and success status; next proof target: `update_review_memory_after_review()` and `_pr_flow_impl` post-review callsite with a disabled manifest row.
    - suspicious surface: A16/A20 proof matrix; tentative issue: local approval would ignore `provisional` live-audit rows; next proof target: story proof rows and `/openspec-story-review` proof-maturity readiness rule.
    - suspicious surface: 17:23 local blocker repairs; tentative issue: latest fixes might only cover tests, not runtime callsites; next proof target: degraded predicate, stable identity serializer, strict/warn citation validator, and prompt extra-vars callsites.
  - Key findings:
    - A1/A11 `review_memory_store` module override remains fail-open in the post-review memory refresh path. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:168`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:178`, `cure_subsequent_review/runtime.py:1197`, `cure_subsequent_review/runtime.py:1205`, `cure_subsequent_review/runtime.py:1301`, `cure.py:11082`, `tests/_subsequent_review_unit_runtime_memory_unittest.py:65`, `tests/_subsequent_review_unit_runtime_memory_unittest.py:78`, `tests/_subsequent_review_unit_runtime_memory_unittest.py:87`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** Story A1/A11 requires disabled module overrides, including `review_memory_store`, to remain artifact-free/backward-compatible. The latest fix handles the intake persistence point, but the post-review helper still writes `cure_memory.json`, returns success, and overwrites an existing disabled manifest row. Operators can therefore disable review memory and still get a shared-memory write after final review publication.

      **Assumptions / Preconditions:** Subsequent review is enabled, semantic ledgers exist, a `ReviewMemoryStore` object is available, and `run_manifest.json` already records `review_memory_store` as `disabled` from a module override or equivalent disabled path before post-review refresh runs.

      **Downgrade Factors:** If the story explicitly narrows disabled module override support to intake-only and allows post-review refresh to ignore disabled state, this becomes a contract drift issue instead of an implementation blocker. The current A1/A11 proof rows do not record that narrowing.

      **Code Trail:** `run_subsequent_review_intake()` now checks the disabled override before calling `update_review_memory_after_intake()`, but `update_review_memory_after_review()` delegates to `update_review_memory_after_intake()` without checking a disabled manifest/config state. Its `finish()` helper unconditionally assigns `modules["review_memory_store"] = record.to_json()`, and `_pr_flow_impl` calls the post-review helper after a successful review whenever a subsequent artifact dir exists. The existing runtime-memory test creates a manifest with `review_memory_store.status = disabled` and asserts the post-review update changes it to `success` with an artifact path.

      **Reproduction:** Parent temp-dir probe with `source_verification.json`, `disposition_ledger.json`, and `run_manifest.json` containing `"review_memory_store": {"status": "disabled"}` called `update_review_memory_after_review(...)`; it printed `record.status=success`, `record.artifact_path_present=True`, `memory_file_exists=True`, and `manifest.status=success`. Expected disabled status preservation and no shared-memory write.

      </details>
    - A16/A20 proof maturity still blocks approval under the story-review gate. Sources: `/home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md:102`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:8`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:183`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:187`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/tasks.md:30`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/progress.md:118`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** `/openspec-story-review` approval is not allowed while any proof row remains `provisional`. Story 04 still records A16 and A20 as provisional pending fresh PR #22 live-output/performance audit, and the story header/progress explicitly say PR/live status remains request-changes until that audit runs at current PR #22 head or later.

      **Assumptions / Preconditions:** None.

      **Downgrade Factors:** If the story is intentionally split into local-only approval plus separate PR-stage proof, the proof matrix and status policy must be updated to mark local proof rows final and move live audit to a distinct PR-stage gate before approval can rely on that distinction.

      **Code Trail:** A16 and A20 proof rows remain `provisional`; the story gate states a fresh PR #22 live audit is required; the review skill readiness rule explicitly treats any provisional proof row as not approval-ready.

      **Reproduction:** `rg -n "A16 \| provisional|A20 \| provisional|any proof row is still" story.md /home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md` returns the provisional rows and readiness rule.

      </details>
  - Debt Friction: none
  - Next action: `/openspec-story-resume cure-subsequent-pr-review story-04-review-runtime-integration-guardrails-memory-trace` to preserve `review_memory_store=disabled` through the post-review refresh path (or explicitly narrow the A1/A11 contract), then rerun focused runtime-memory/control-plane suites plus public wrapper/static checks; after local blockers are closed, run the required fresh PR #22 live audit and finalize A16/A20 proof rows before seeking approval.

- 2026-06-15T07:24:24Z Review run by fresh maintainer session
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Multipass review: completed
  - Prior review concerns: still_open
  - Plan lane at review time: 🟢 PLAN APPROVED
  - Initiative contract drift: none
  - Status transition: 🔄 IN PROGRESS -> 🔄 IN PROGRESS
  - Sections reviewed: Purpose, Actors, Triggering Need, Expected Prerequisites, Scope, Out of Scope, Scenarios / Behavior Examples, Acceptance, Verification, Critical Files, Implementation Notes, Locked Decisions, Discovery Notes
  - Original intent checked: initiative/story/proposal/design/tasks/progress/reviews, PR #22 context recorded in story/progress, and dependency/sibling ownership from the initiative table; no separate Jira/ticket source found.
  - Traceability: forward gaps; backward complete for reviewed local changes
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: `git status --short`, `git diff --stat`, `git diff --numstat`, OpenSpec proof/tasks/progress/reviews, `cure_subsequent_review/{runtime.py,memory_store.py,degraded_runtime.py,semantic_pipeline.py,source_truth.py,discussion_linker.py,llm_verifier.py,control_plane.py}`, `_pr_flow_impl` prompt/runtime callsites in `cure.py`, prompt propagation tests, runtime-memory/control-plane tests, report-governor tests, degraded-runtime tests, semantic/source/linker/verifier tests, public subsequent-review wrapper.
  - Risk lenses reviewed: proof-maturity/live-audit gate, module override disabled-path, post-review persistence lifecycle, cache identity/replay staleness, degraded discussion operator gating, prompt/template fail-open propagation, report-governor citation/DA coverage fail-open, source/discussion authority separation, dirty-tree hygiene.
  - Finding closure: A1/A11 post-review `review_memory_store` disabled override blocker from 2026-06-14T18:04:59Z is resolved locally by `runtime.py` guard/test evidence and current focused tests; prior 17:23 blockers and 16:05 A17 blocker remain resolved by focused pass evidence; A16/A20 proof-maturity concern remains still open because fresh PR #22 live audit is not recorded and both proof rows remain provisional.
  - Evidence quality: confirmed direct OpenSpec/source/test reads, focused multipass child passes checked against primary anchors, targeted runtime-memory/control-plane test rerun (`11 passed`), public subsequent-review wrapper rerun (`132 passed, 36 subtests`), `ruff check .`, and `mypy`; inferred none material; unknown fresh PR #22 live-audit result after current local changes; provisional A16/A20 live-proof rows remain.
  - Files reviewed: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,proposal.md,design.md,tasks.md,progress.md,reviews.md}`, `openspec/initiatives/cure-subsequent-pr-review/initiative.md`, `/home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md`, `cure_subsequent_review/{runtime.py,memory_store.py,degraded_runtime.py,semantic_pipeline.py,source_truth.py,discussion_linker.py,llm_verifier.py,control_plane.py}`, `cure.py`, `tests/_subsequent_review_unit_runtime_memory_unittest.py`, `tests/_subsequent_review_functional_control_plane_unittest.py`, `tests/_subsequent_review_unit_memory_store_unittest.py`, `tests/_subsequent_review_unit_degraded_runtime_unittest.py`, `tests/_subsequent_review_unit_runtime_packaging_unittest.py`, `tests/_subsequent_review_unit_report_governor_unittest.py`, `tests/_reviewflow_unittest_prompt_session_impl.py`, `tests/_reviewflow_unittest_grounding_impl.py`, `tests/test_subsequent_review.py`.
  - Hypothesis triage:
    - suspicious surface: post-review review-memory refresh; tentative issue: disabled manifest row might still be overwritten after final review; next proof target: `_disabled_review_memory_record_from_manifest()`, `update_review_memory_after_intake()`, and `test_post_review_preserves_disabled_review_memory_store_override`.
    - suspicious surface: A16/A20 proof matrix; tentative issue: local approval would ignore provisional proof rows and pending live PR #22 audit; next proof target: story proof rows, tasks live-audit checkbox, progress handoff/PR state, and story-review readiness rule.
    - suspicious surface: prior 17:23 blocker repairs; tentative issue: fixes might cover unit tests but not runtime callsites; next proof target: degraded predicate, stable identity serializer, strict/warn citation validator, and `$PRIOR_REVIEW_BRIEF` extra-vars callsites.
  - Key findings:
    - A16/A20 proof maturity still blocks approval under the story-review gate. Sources: `/home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md:102`, `/home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md:450`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:8`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:183`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:187`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/tasks.md:31`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/progress.md:126`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/progress.md:134`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/progress.md:146`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** The review skill forbids approval while any proof row is still provisional, and Story 04 still records A16 and A20 as provisional pending a fresh PR #22 live audit. Local code blockers are now resolved, but the story contract still requires live-output/performance proof before approval or done transition.

      **Assumptions / Preconditions:** None.

      **Downgrade Factors:** If the story is intentionally split into a local-only completion gate plus separate PR-stage live audit, the proof matrix and status/progress contract must be updated first so A16/A20 no longer remain provisional approval blockers.

      **Code Trail:** The story header says PR #22 remains gated until a fresh live audit at head `e305f826f3c0ece63be708f7df4b4f54c38b7658` or later closes runtime/A20 hardening; A16 and A20 proof rows remain `provisional`; the live-audit task remains unchecked; progress says PR/live status remains request-changes until the fresh audit; the review skill readiness and approval-gate rules require every proof row to be final before approval.

      **Reproduction:** `rg -n "A16 \\| provisional|A20 \\| provisional|Run and audit a fresh PR #22|fresh PR #22 live audit|any proof row is still|every proof row is final" openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,tasks.md,progress.md} /home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md` returns the provisional rows, pending task/progress statements, and review gate.

      </details>
  - Debt Friction: none
  - Next action: run and record the required fresh PR #22 live audit at head `e305f826f3c0ece63be708f7df4b4f54c38b7658` or later, then finalize or explicitly re-scope the A16/A20 proof rows before seeking approval again.
