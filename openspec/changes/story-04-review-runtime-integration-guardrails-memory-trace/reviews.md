# Reviews: story-04-review-runtime-integration-guardrails-memory-trace

> Implementation review artifact migrated from legacy `agent_coordination` during the 2026-06-12 OpenSpec-format rewrite.
> Canonical story contract: `story.md`. Legacy source remains under `/workspaces/cure_workspace/agent_coordination/epics/cure-subsequent-pr-review/`.

## Review Log

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
