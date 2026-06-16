# Reviews: story-04-review-runtime-integration-guardrails-memory-trace

> Implementation review artifact migrated from legacy `agent_coordination` during the 2026-06-12 OpenSpec-format rewrite.
> Canonical story contract: `story.md`. Legacy source remains under `/workspaces/cure_workspace/agent_coordination/epics/cure-subsequent-pr-review/`.

## Review Log

- 2026-06-16T15:11:09Z Review run by fresh maintainer session
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
  - Original intent checked: workspace `AGENTS.md`; initiative/story/proposal/design/tasks/progress/reviews; PR18/PR22 live-audit intent recorded in OpenSpec artifacts. No fresh live PR18/PR22 audit was run.
  - Traceability: forward gaps; backward gaps
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: OpenSpec proof/status/tasks/progress/reviews/proposal/design; `git status --short`, `git diff --numstat`, `git diff --stat`, `git diff --check`; focused multipass passes over proof/status, discussion-linker/cache identity, report-governor/final-output/footer policy, and runtime/control-plane/degraded/memory/source replay; parent source/test searches for A12 identity drift and A17/A19 footer regressions.
  - Risk lenses reviewed: proof maturity/live-audit gate, dirty main-tree review hygiene, discussion-linker no-link cache identity drift, source-verification cache identity drift and safe terminal replay, prompt/final-output footer-governor false positives/contradictions, post-review warn-only degradation, degraded discussion artifact lifecycle, disabled-path cleanup, package/context status finalization, active duplicate-source handling, and verifier fan-out observability.
  - Finding closure: 2026-06-16T13:50 A12 same-origin no-link identity-drift blocker is resolved locally by source/test inspection and parent targeted regression run (`26 passed, 2 subtests`); prior A17/A19 copied-summary and no-subject negated-footer blockers are resolved locally by source/test inspection and parent targeted regression run; prior A1 healthy-empty discussion and A20 replay-persisted source-reference blockers remain locally resolved by focused pass evidence; A16/A17/A19/A20 proof/live-audit gate remains open.
  - Evidence quality: confirmed direct OpenSpec/source/test reads, chunkhound research saved to notebook, four focused multipass passes, parent targeted tests (`26 passed, 2 subtests`), and `git diff --check`; inferred none material; unknown fresh PR22 live-output/cache behavior because live audit intentionally not run; provisional A16/A17/A19/A20 proof rows remain.
  - Files reviewed: `AGENTS.md`; `/home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md`; `openspec/initiatives/cure-subsequent-pr-review/initiative.md`; `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,proposal.md,design.md,tasks.md,progress.md,reviews.md}`; `cure.py`; `cure_subsequent_review/contracts.py`; `cure_subsequent_review/control_plane.py`; `cure_subsequent_review/degraded_runtime.py`; `cure_subsequent_review/runtime.py`; `cure_subsequent_review/memory_store.py`; `cure_subsequent_review/source_truth.py`; `cure_subsequent_review/semantic_pipeline.py`; `cure_subsequent_review/discussion_linker.py`; `cure_subsequent_review/discussion_signals.py`; `cure_subsequent_review/llm_verifier.py`; maintained PR prompt templates; Story 04 focused tests including report-governor, discussion-linker, discussion-signals, memory-store, runtime-memory, source-truth, runtime-packaging, degraded-runtime, control-plane, PR-flow, prompt/config, and landmark-trace fixtures.
  - Hypothesis triage:
    - suspicious surface: OpenSpec proof matrix/live-audit tasks; tentative issue: local approval would ignore provisional A16/A17/A19/A20 rows and unchecked fresh PR #22 live audit; next proof target: run or explicitly rescope the PR #22 live audit and convert proof rows to final only with evidence.
    - suspicious surface: `_cached_group_identity_matches()` / `LlmDiscussionLinker` no-link replay; tentative issue: prior same-event/body/head no-link cache identity drift could suppress a fresh linker call; next proof target: checked regression for same group id + same origin + changed fingerprint/source refs.
    - suspicious surface: `_footer_marker_policy_warnings()` copied-summary and no-subject negation; tentative issue: prior valid footer audit notes could still false-degrade or positive contradictions could be missed; next proof target: checked report-governor regressions for copied count, `no foreign findings were carried forward`, and positive contradictions.
  - Key findings:
    - A16/A17/A19/A20 proof maturity and the fresh PR #22 live-audit gate still block approval. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:8`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:186`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:187`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:189`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:190`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/tasks.md:32`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/progress.md:23`, `/home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md:102`, `/home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md:446`, `/home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md:450`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** The current local code blockers checked in the latest reviews appear resolved, but the review skill still forbids approval while required proof remains unresolved. Story 04 still records A16, A17, A19, and A20 as provisional, leaves the fresh PR #22 live-audit task unchecked, and the latest progress entry explicitly says no fresh PR #22 live audit was run after the A12 fix.

      **Assumptions / Preconditions:** None.

      **Downgrade Factors:** If the team wants a local-only completion split from live PR-stage proof, the story/proof matrix must explicitly rescope those rows before review can approve.

      **Code Trail:** The story header names the pending PR #22 live-audit gate; the proof matrix marks A16/A17/A19/A20 provisional; `tasks.md` leaves the live-audit row unchecked; `progress.md` preserves the same pending state after the latest fix; the review skill requires unresolved proof contracts to fail approval and every proof row to be final.

      **Reproduction:** `rg -n "A16 \\| provisional|A17 \\| provisional|A19 \\| provisional|A20 \\| provisional|Run and audit a fresh PR #22|No fresh PR #22 live audit|Approval is not allowed|every proof row|proof row is still" openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,tasks.md,progress.md} /home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md` returns the cited provisional rows, pending task/progress statements, and approval rule.

      </details>
  - Debt Friction: none
  - Next action: Run and audit a fresh PR #22 live review at head `e305f826f3c0ece63be708f7df4b4f54c38b7658` or later, then update the A16/A17/A19/A20 proof rows/tasks from provisional/pending to final only with artifact evidence.

- 2026-06-16T13:50:51Z Review run by fresh maintainer session
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
  - Original intent checked: workspace `AGENTS.md`; initiative/story/proposal/design/tasks/progress/reviews; prior PR18/PR22 live-audit intent recorded in OpenSpec artifacts. No fresh live PR18/PR22 audit was run.
  - Traceability: forward gaps; backward gaps
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: OpenSpec proof/status/tasks/progress/reviews; `git status --short`, `git diff --numstat`, `git diff --check`; focused passes over proof/status, report-governor/final-output/footer, discussion-linker/memory/source/semantic replay, and runtime/control-plane/degraded/prompt integration; parent targeted tests and A12 stale no-link identity-drift probe.
  - Risk lenses reviewed: proof maturity/live-audit gate, dirty main-tree review hygiene, prompt/final-output footer-governor false positives/contradictions, post-review warn-only degradation, discussion-linker no-link cache staleness, current group identity drift, shared memory/source cache identity drift, non-source-proof replay, semantic pipeline ordering, degraded discussion artifact lifecycle, disabled-path cleanup, package/context status consistency, and verifier fan-out observability.
  - Finding closure: 2026-06-16T13:16 footer-governor `no foreign findings were carried forward` false-degradation is resolved locally by source/test inspection and parent targeted tests/probe; the exact stale no-link cache case where the current group set changes is resolved locally, but A12 remains open for same group-id/current-universe cache replay when fingerprint/source-reference identity changes under the same origin; A16/A17/A19/A20 proof/live-audit gate remains open.
  - Evidence quality: confirmed direct OpenSpec/source/test reads, four focused multipass passes, parent targeted tests (`25 passed, 2 subtests`), parent A12 same-origin identity-drift probe (`classifier_calls=0` stale cache replay), and `git diff --check`; inferred none material; unknown fresh PR22 live-output/cache behavior because live audit intentionally not run; provisional A16/A17/A19/A20 proof rows remain.
  - Files reviewed: `AGENTS.md`; `/home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md`; `openspec/initiatives/cure-subsequent-pr-review/initiative.md`; `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,proposal.md,design.md,tasks.md,progress.md,reviews.md}`; `cure.py`; `cure_runtime.py`; `cure_subsequent_review/contracts.py`; `cure_subsequent_review/control_plane.py`; `cure_subsequent_review/degraded_runtime.py`; `cure_subsequent_review/runtime.py`; `cure_subsequent_review/memory_store.py`; `cure_subsequent_review/source_truth.py`; `cure_subsequent_review/semantic_pipeline.py`; `cure_subsequent_review/discussion_linker.py`; `cure_subsequent_review/llm_verifier.py`; maintained PR prompt templates; Story 04 focused tests including report-governor, discussion-linker, memory-store, semantic-pipeline, source-truth, llm-verifier, runtime-packaging, degraded-runtime, control-plane, PR-flow, prompt/config, and landmark-trace suites.
  - Hypothesis triage:
    - suspicious surface: OpenSpec proof matrix/live-audit tasks; tentative issue: local approval would ignore provisional A16/A17/A19/A20 rows and unchecked fresh PR #22 live audit; next proof target: run or explicitly rescope the PR #22 live audit and convert proof rows to final only with evidence.
    - suspicious surface: `_cached_group_identity_matches()` / `LlmDiscussionLinker` no-link replay; tentative issue: same event/body/head no-link cache can replay when the group id and origin match but fingerprint/source-reference identity changed, suppressing a fresh linker call; next proof target: regression for same group id + same origin + changed fingerprint/source refs.
    - suspicious surface: `_footer_marker_policy_warnings()` copied-summary and no-subject negation; tentative issue: prior footer false-degradation blockers may still be open; next proof target: targeted report-governor tests/probe for copied count, `no foreign findings were carried forward`, and positive contradictions.
  - Key findings:
    - A16/A17/A19/A20 proof maturity and the fresh PR #22 live-audit gate still block approval. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:8`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:186`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:187`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:189`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:190`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/tasks.md:32`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/progress.md:23`, `/home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md:446`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** The review skill forbids approval while required proof remains unresolved. Story 04 still records A16, A17, A19, and A20 as provisional, leaves the fresh PR #22 live-audit task unchecked, and the latest progress entry explicitly says no fresh PR #22 live audit was run after the local fixes.

      **Assumptions / Preconditions:** None.

      **Downgrade Factors:** If the team wants a local-only approval split from live PR-stage proof, the story/proof matrix must explicitly rescope those rows before review can approve.

      **Code Trail:** The story header names the pending PR #22 live-audit gate; the proof matrix marks A16/A17/A19/A20 provisional; `tasks.md` leaves the live-audit row unchecked; `progress.md` preserves the same pending state after the latest fixes; the review skill requires every proof row to be final before approval.

      **Reproduction:** `rg -n "A16 \\| provisional|A17 \\| provisional|A19 \\| provisional|A20 \\| provisional|Run and audit a fresh PR #22|fresh PR #22 live audit|Approval is not allowed|every proof row" openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,tasks.md,progress.md} /home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md` returns the cited provisional rows, pending task/progress statements, and approval rule.

      </details>
    - A12 no-link discussion-linker cache can still replay stale results when the current group id/universe is unchanged but the current group identity changed under the same origin. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:38`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:114`, `cure_subsequent_review/discussion_linker.py:84`, `cure_subsequent_review/discussion_linker.py:91`, `cure_subsequent_review/discussion_linker.py:96`, `cure_subsequent_review/discussion_linker.py:172`, `cure_subsequent_review/discussion_linker.py:182`, `cure_subsequent_review/memory_store.py:169`, `cure_subsequent_review/memory_store.py:172`, `cure_subsequent_review/memory_store.py:173`, `cure_subsequent_review/memory_store.py:321`, `tests/_subsequent_review_unit_discussion_linker_unittest.py:148`

      <details open>
      <summary><b>Medium</b> severity · <b>Medium</b> likelihood</summary>

      **Why:** Story 04 says linker results are cached by event/body/head plus current group identities. The latest fix stores identities for no-link rows and invalidates when the current group set differs, but identity matching still falls back to `origin_digest` after fingerprint mismatch. A no-link row for `G-0001` can therefore replay when the same origin/comment produced an updated current group with a different fingerprint or source-reference digest, suppressing the classifier call that could attach the now-relevant event.

      **Assumptions / Preconditions:** Same `event_id + body_hash + head`, cached `group_ids=[]`, same current group id and same prior-corpus origin, but changed finding fingerprint and/or source references.

      **Downgrade Factors:** If origin-only identity is intentionally considered sufficient for linker no-link replay, the story/design must explicitly narrow the `current group identities` requirement and document why fingerprint/source-reference drift is safe for no-link rows.

      **Code Trail:** `group_identity_for_cache()` records canonical id, finding ids, fingerprint, source-reference digest, and origin digest. `_cached_group_identity_matches()` first accepts exact fingerprint equality, then falls back to matching origin digest. `_cached_group_universe_matches()` only checks the group-id set and that matcher; `_cached()` accepts no-link payloads when the universe matcher passes. The checked-in stale-cache regression covers a different group set, not same group id with changed fingerprint/source refs.

      **Reproduction:** Parent read-only probe seeded `cure_memory.json` with a no-link cached result for `G-0001` at `head-1` whose identity had fingerprint `old-fingerprint` and `src/parser.py:42`; it then called `LlmDiscussionLinker` with the same event/body/head and current `G-0001` from the same origin but fingerprint `new-fingerprint` and `src/parser.py:84`. Because `origin_digest` matched, the cached no-link replayed with `classifier_calls=0`, `result_group_ids=()`, and `result_signal_class=by_design`.

      </details>
  - Debt Friction: none
  - Next action: `/openspec-story-resume cure-subsequent-pr-review story-04-review-runtime-integration-guardrails-memory-trace` to fix the A12 same-origin identity-drift no-link cache replay and keep A16/A17/A19/A20 proof rows provisional until a fresh PR #22 live audit is actually run or the story is explicitly rescoped.

- 2026-06-16T13:16:40Z Review run by fresh maintainer session
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
  - Original intent checked: workspace `AGENTS.md`; initiative/story/proposal/design/tasks/progress/reviews; PR18/PR22 live-audit intent recorded in OpenSpec artifacts. No fresh live PR18/PR22 audit was run.
  - Traceability: forward gaps; backward gaps
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: OpenSpec proof/status/tasks/progress/reviews; `git status --short`, `git diff --numstat`, `git diff --stat`, `git diff --check`; focused pass over `cure.py`, `cure_subsequent_review/control_plane.py`, `degraded_runtime.py`, `runtime.py`, runtime-packaging/control-plane/degraded/PR-flow tests; focused pass over report-governor/final-output/footer policy paths and maintained prompts; focused pass over `memory_store.py`, `semantic_pipeline.py`, `source_truth.py`, `discussion_linker.py`, `llm_verifier.py`, and related tests; parent probes for `_footer_marker_policy_warnings()` and `LlmDiscussionLinker` cache replay.
  - Risk lenses reviewed: proof maturity/live-audit gate, dirty main-tree review hygiene, prompt/final-output false-positive/false-negative footer-governor behavior, post-review warn-only degradation, foreign-footer provenance final-output visibility, module-12 artifact lifecycle, disabled decision-only artifact cleanup, shared memory/cache identity drift, no-link linker cache replay, safe terminal replay categories, verifier fan-out telemetry, semantic pipeline ordering, and LLM verifier inactive-source handling.
  - Finding closure: 2026-06-16T12:06 copied-summary-only ignored-footer count blocker is resolved locally by source/test inspection, targeted test, and parent probe (`footer_valid_copied=[]`); prior A1/module-12 healthy-empty and A20 replay-persisted source-reference blockers remain locally resolved; A16/A17/A19/A20 proof/live-audit gate remains open; new local issues found for `no foreign findings were carried forward` false-degradation and A12 discussion-linker no-link cache staleness.
  - Evidence quality: confirmed direct source/OpenSpec/test reads, four focused multipass passes, parent targeted tests (`7 passed, 2 subtests`), parent `_footer_marker_policy_warnings()` probe, parent `LlmDiscussionLinker` no-link cache probe, and `git diff --check`; inferred none material; unknown fresh PR22 live-output/cache behavior because live audit intentionally not run; provisional A16/A17/A19/A20 proof rows remain.
  - Files reviewed: `AGENTS.md`; `/home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md`; `openspec/initiatives/cure-subsequent-pr-review/initiative.md`; `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,proposal.md,design.md,tasks.md,progress.md,reviews.md}`; `cure.py`; `cure_subsequent_review/contracts.py`; `cure_subsequent_review/control_plane.py`; `cure_subsequent_review/degraded_runtime.py`; `cure_subsequent_review/runtime.py`; `cure_subsequent_review/memory_store.py`; `cure_subsequent_review/source_truth.py`; `cure_subsequent_review/semantic_pipeline.py`; `cure_subsequent_review/discussion_linker.py`; `cure_subsequent_review/llm_verifier.py`; maintained PR prompt templates; `tests/_subsequent_review_unit_degraded_runtime_unittest.py`; `tests/_subsequent_review_functional_control_plane_unittest.py`; `tests/_subsequent_review_unit_runtime_packaging_unittest.py`; `tests/_subsequent_review_unit_runtime_memory_unittest.py`; `tests/_subsequent_review_integration_pr_flow_unittest.py`; `tests/_subsequent_review_unit_report_governor_unittest.py`; `tests/_subsequent_review_unit_memory_store_unittest.py`; `tests/_subsequent_review_unit_semantic_pipeline_unittest.py`; `tests/_subsequent_review_unit_discussion_linker_unittest.py`; `tests/_subsequent_review_unit_source_truth_unittest.py`; `tests/_subsequent_review_unit_llm_verifier_unittest.py`; `tests/_reviewflow_unittest_prompt_session_impl.py`.
  - Hypothesis triage:
    - suspicious surface: OpenSpec proof matrix/live-audit tasks; tentative issue: local approval would ignore provisional A16/A17/A19/A20 rows and unchecked fresh PR #22 live audit; next proof target: run or explicitly rescope the PR #22 live audit and convert proof rows to final only with evidence.
    - suspicious surface: `_footer_marker_policy_warnings()` negation handling; tentative issue: valid `no foreign findings were carried forward` wording is read as a positive contradiction; next proof target: report-governor regression for `no foreign findings were carried forward` with copied count, durable reason, and explicit exclusion.
    - suspicious surface: `LlmDiscussionLinker` cached no-link results; tentative issue: same `event_id + body_hash + head` can replay an empty `group_ids` result even when current reconciliation groups changed and now include a relevant group; next proof target: no-link cache invalidation keyed by current group identities or explicit safe scope.
    - suspicious surface: copied footer-policy summary count visibility; tentative issue: previous missing-count finding may still be open; next proof target: source/test/probe around `foreign official-footer ignored comments: 1` copied summary only.
  - Key findings:
    - A16/A17/A19/A20 proof maturity and the fresh PR #22 live-audit gate still block approval. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:8`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:186`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:187`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:189`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:190`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/tasks.md:32`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/progress.md:23`, `/home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md:446`, `/home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md:450`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** The review skill forbids approval while required proof remains unresolved. Story 04 still records A16, A17, A19, and A20 as provisional, leaves the fresh PR #22 live-audit row unchecked, and current progress explicitly says no fresh PR #22 live audit was run after the latest local fixes.

      **Assumptions / Preconditions:** None.

      **Downgrade Factors:** If the team wants a local-only approval split from live PR-stage proof, the story/proof matrix must explicitly rescope those rows before review can approve.

      **Code Trail:** The story header names the pending PR #22 live-audit gate; the proof matrix marks A16/A17/A19/A20 provisional; `tasks.md` leaves the live-audit row unchecked; `progress.md` preserves the same pending state after the latest fix; the review skill requires unresolved proof contracts to fail approval and every proof row to be final.

      **Reproduction:** `rg -n "A16 \\| provisional|A17 \\| provisional|A19 \\| provisional|A20 \\| provisional|Run and audit a fresh PR #22|fresh PR #22 live audit|Approval is not allowed|every proof row" openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,tasks.md,progress.md} /home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md` returns the cited provisional rows, pending task/progress statements, and approval rule.

      </details>
    - A17/A19 footer-governor false-degrades a valid audit note that says no foreign findings were carried forward. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:98`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:119`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:121`, `cure_subsequent_review/runtime.py:934`, `cure_subsequent_review/runtime.py:938`, `cure_subsequent_review/runtime.py:956`, `cure_subsequent_review/runtime.py:957`, `cure_subsequent_review/runtime.py:967`, `cure_subsequent_review/runtime.py:973`, `cure_subsequent_review/runtime.py:974`, `cure_subsequent_review/runtime.py:989`, `tests/_subsequent_review_unit_report_governor_unittest.py:550`, `tests/_subsequent_review_unit_report_governor_unittest.py:643`

      <details open>
      <summary><b>Medium</b> severity · <b>High</b> likelihood</summary>

      **Why:** A17/A19 require final reviews to include an ignored foreign-footer count/reason while excluding foreign findings. The copied-summary count fix is now good, but the contradiction regex only suppresses verbs immediately preceded by `not` or `never`; a natural valid sentence such as `no foreign findings were carried forward` still matches as a positive contradiction and records `contradicted_footer_marker_policy_audit_note`.

      **Assumptions / Preconditions:** `governor_brief.md` reports at least one ignored foreign official-footer comment, and final `review.md` uses the copied `foreign official-footer ignored comments: 1` summary plus durable PR/session/head reason tokens and `no foreign findings were carried forward` / foreign footer excluded wording.

      **Downgrade Factors:** Post-review governor findings are warn-only and do not block publication, so this is not a publication stop. It still weakens A17/A19 proof because valid final-output text can be falsely degraded.

      **Code Trail:** `_footer_marker_policy_warnings()` now accepts the copied summary count, but `positive_foreign_finding_action` uses only `(?<!not )(?<!never )` lookbehinds and the broad `foreign findings` patterns. Existing positive and negated tests cover `not included` / `not carried forward` and positive admitted/carried-forward wording, but not `no foreign findings were carried forward`.

      **Reproduction:** Parent probe: copied summary + PR22/session/head vs PR18 reason + `foreign findings were excluded ... were not carried forward` returned `[]`; copied summary + same durable reason + `no foreign findings were carried forward ... foreign official footer was excluded` returned `['contradicted_footer_marker_policy_audit_note']`; positive `carried forward 1 foreign official CURe footer comment` returned `['contradicted_footer_marker_policy_audit_note']`.

      </details>
    - A12 discussion-linker cache can replay stale no-link results after current group identity changes. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:38`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:91`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:114`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:182`, `cure_subsequent_review/discussion_linker.py:84`, `cure_subsequent_review/discussion_linker.py:91`, `cure_subsequent_review/discussion_linker.py:162`, `cure_subsequent_review/discussion_linker.py:167`, `cure_subsequent_review/discussion_linker.py:172`, `cure_subsequent_review/discussion_linker.py:175`, `cure_subsequent_review/discussion_linker.py:191`, `cure_subsequent_review/discussion_linker.py:197`, `cure_subsequent_review/memory_store.py:140`, `cure_subsequent_review/memory_store.py:173`, `cure_subsequent_review/memory_store.py:286`, `cure_subsequent_review/memory_store.py:321`, `cure_subsequent_review/memory_store.py:325`, `cure_subsequent_review/memory_store.py:326`, `tests/_subsequent_review_unit_discussion_linker_unittest.py:92`

      <details open>
      <summary><b>Medium</b> severity · <b>Medium</b> likelihood</summary>

      **Why:** Story 04 says linker results are cached by event/body/head plus current group identities. The current cache validation checks identities only for cached non-empty `group_ids`; a cached low-confidence/no-link result stores an empty identity map and replays without comparing the current candidate group universe. If reconciliation groups change at the same head, a stale no-link can suppress the LLM linker call and prevent a newly relevant discussion signal from attaching to a group.

      **Assumptions / Preconditions:** Same event id/body/head; an earlier run cached `group_ids=()`; a later run at the same head has different/current reconciliation groups that should be presented to the linker.

      **Downgrade Factors:** If no-link replay is intentionally allowed regardless of current group identity, the story/design should explicitly narrow the `current group identities` requirement and document the stale-no-link risk.

      **Code Trail:** `_cached()` reads a linker result by event/body/head, extracts cached `group_ids`, and validates only listed group ids against `group_identities`. When `group_ids` is empty, `valid_group_ids` is empty but the `if group_ids and not valid_group_ids` guard is false, so it returns the cached no-link result. `_store()` persists identities only for `result.group_ids`, and `update_linker_result()` accepts an empty `group_identities` map.

      **Reproduction:** Parent temp-store probe seeded `event_id=C-99`, same body/head, `group_ids=()`, `signal_class=by_design`, then called `LlmDiscussionLinker` with a current parser group and a classifier that would return `G-0001`; result replayed the cache with `calls=0`, `group_ids=()`, and rationale `cached no confident group`.

      </details>
  - Debt Friction: none
  - Next action: `/openspec-story-resume cure-subsequent-pr-review story-04-review-runtime-integration-guardrails-memory-trace` to add red regressions/fixes for the A17/A19 `no foreign findings were carried forward` false-degradation and A12 no-link cache staleness; keep A16/A17/A19/A20 proof rows provisional until a fresh PR #22 live audit is actually run or the story is explicitly rescoped.

- 2026-06-16T12:06:47Z Review run by fresh maintainer session
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
  - Original intent checked: workspace `AGENTS.md`; initiative/story/proposal/design/tasks/progress/reviews; prior PR18/PR22 live-audit intent recorded in OpenSpec artifacts. No fresh live PR18/PR22 audit was run.
  - Traceability: forward gaps; backward gaps
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: OpenSpec proof/status/tasks/progress/reviews; `git status --short`, `git diff --numstat`, `git diff --stat`, and `git diff --check`; focused pass over `cure_subsequent_review/degraded_runtime.py`, `control_plane.py`, `_pr_flow_impl`, and runtime manifest/disabled paths; focused pass over `cure_subsequent_review/runtime.py` footer-governor/final-output checks, maintained prompts, and A16/A17/A19 tests; focused pass over `cure_subsequent_review/memory_store.py`, `source_truth.py`, `semantic_pipeline.py`, `discussion_linker.py`, `llm_verifier.py`, and A20/A12-A14/A18 tests; direct parent probe of `_footer_marker_policy_warnings()` for copied-summary count visibility.
  - Risk lenses reviewed: proof maturity/live-audit gate, dirty main-tree review hygiene, prompt/final-output fail-open and false-positive footer-governor behavior, foreign-footer provenance final-output visibility, module-12 healthy-empty discussion artifact lifecycle, disabled decision-only artifact cleanup, shared memory/cache identity drift after replay persistence, safe terminal replay categories, verifier fan-out telemetry, semantic pipeline ordering, and LLM verifier inactive-source handling.
  - Finding closure: A1/module-12 healthy-empty fetch blocker resolved locally by source/test inspection and focused runtime suite (`47 passed, 4 subtests`); A20 replay-persisted changed-source-reference blocker resolved locally by source/test inspection and focused memory/semantic suites (`38 passed, 12 subtests`; PR-flow `17 passed`); A17/A19 prior contradiction-specific copied-summary false positive is partially resolved, but the copied summary still fails the required audit-note count check unless the final output repeats an extra `Ignored 1 foreign official...` phrase; A16/A17/A19/A20 proof/live-audit gate remains open.
  - Evidence quality: confirmed direct source/OpenSpec/test reads, four focused multipass passes, parent `git diff --check`, and parent `_footer_marker_policy_warnings()` reproduction; inferred none material; unknown fresh PR22 live-output/cache behavior because live audit intentionally not run; provisional A16/A17/A19/A20 proof rows remain.
  - Files reviewed: `AGENTS.md`; `/home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md`; `openspec/initiatives/cure-subsequent-pr-review/initiative.md`; `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,proposal.md,design.md,tasks.md,progress.md,reviews.md}`; `cure.py`; `cure_runtime.py`; `cure_subsequent_review/contracts.py`; `cure_subsequent_review/control_plane.py`; `cure_subsequent_review/degraded_runtime.py`; `cure_subsequent_review/runtime.py`; `cure_subsequent_review/memory_store.py`; `cure_subsequent_review/source_truth.py`; `cure_subsequent_review/semantic_pipeline.py`; `cure_subsequent_review/discussion_linker.py`; `cure_subsequent_review/llm_verifier.py`; maintained PR prompt templates; `tests/_subsequent_review_unit_degraded_runtime_unittest.py`; `tests/_subsequent_review_functional_control_plane_unittest.py`; `tests/_subsequent_review_unit_runtime_packaging_unittest.py`; `tests/_subsequent_review_unit_runtime_memory_unittest.py`; `tests/_subsequent_review_integration_pr_flow_unittest.py`; `tests/_subsequent_review_unit_report_governor_unittest.py`; `tests/_subsequent_review_unit_memory_store_unittest.py`; `tests/_subsequent_review_unit_semantic_pipeline_unittest.py`; `tests/_subsequent_review_unit_discussion_linker_unittest.py`; `tests/_subsequent_review_unit_source_truth_unittest.py`; `tests/_subsequent_review_unit_llm_verifier_unittest.py`; `tests/_reviewflow_unittest_prompt_session_impl.py`.
  - Hypothesis triage:
    - suspicious surface: OpenSpec proof matrix/live-audit tasks; tentative issue: local approval would ignore provisional A16/A17/A19/A20 rows and unchecked fresh PR #22 live audit; next proof target: run or explicitly rescope the PR #22 live audit and convert proof rows to final only with evidence.
    - suspicious surface: `_footer_marker_policy_warnings()` copied-summary path; tentative issue: the contradiction regex fix removes the policy summary phrase, but the count-visible check still requires a second `Ignored 1` / `1 foreign official` phrase; next proof target: regression for copied `Accepted official-footer remote entries: 0; foreign official-footer ignored comments: 1` plus PR/session/head reason and excluded/not-carried-forward wording without duplicate count wording.
    - suspicious surface: `DiscussionFetchController.fetch()` and `_pr_flow_impl` disabled cleanup; tentative issue: success artifacts might be missing for empty healthy fetches or leak into auto-disabled decision-only runs; next proof target: focused runtime pass and empty-success/auto-disabled regressions.
    - suspicious surface: A20 replay-persisted cache identity; tentative issue: origin digest could mask source-reference drift after replay persistence; next proof target: replay-persisted changed-source-reference regression and stable identity source-ref digest code.
  - Key findings:
    - A16/A17/A19/A20 proof maturity and the fresh PR #22 live-audit gate still block approval. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:8`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:186`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:187`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:189`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:190`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/tasks.md:32`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/progress.md:23`, `/home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md:446`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** The review skill forbids approval while required proof remains unresolved. Story 04 still records A16, A17, A19, and A20 as provisional, leaves the fresh PR #22 live-audit task unchecked, and current progress says no fresh PR #22 live audit was run after the latest local fixes.

      **Assumptions / Preconditions:** None.

      **Downgrade Factors:** If the team wants a local-only approval split from live PR-stage proof, the story/proof matrix must explicitly rescope those rows before review can approve.

      **Code Trail:** The story header names the pending PR #22 live-audit gate; the proof matrix marks A16/A17/A19/A20 provisional; `tasks.md` leaves the live-audit row unchecked; `progress.md` preserves the same pending state after the latest fixes; the review skill states every proof row must be final before approval.

      **Reproduction:** `rg -n "A16 \\| provisional|A17 \\| provisional|A19 \\| provisional|A20 \\| provisional|Run and audit a fresh PR #22|fresh PR #22 live audit|Approval is not allowed" openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,tasks.md,progress.md} /home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md` returns the cited provisional rows, pending task/progress statements, and approval rule.

      </details>
    - A17/A19 copied-summary hardening is incomplete: a valid final note that includes the copied `Accepted official-footer remote entries: 0; foreign official-footer ignored comments: 1` summary, PR/session/head reason, and excluded/not-carried-forward wording still degrades as a missing audit note unless it repeats an extra count phrase. Sources: `cure_subsequent_review/runtime.py:934`, `cure_subsequent_review/runtime.py:958`, `cure_subsequent_review/runtime.py:986`, `tests/_subsequent_review_unit_report_governor_unittest.py:620`

      <details open>
      <summary><b>Medium</b> severity · <b>High</b> likelihood</summary>

      **Why:** A17/A19 require final reviews to surface the ignored foreign-footer count and plain-English reason while excluding those foreign findings. The implementation no longer calls the copied summary a contradiction, but it still treats the same copied summary as not showing the count unless the review also says something like `Ignored 1 foreign official...`. A natural valid final note can therefore be degraded incorrectly.

      **Assumptions / Preconditions:** `governor_brief.md` has one ignored foreign official-footer comment; the final review copies the governor policy summary count and includes the durable PR/session/head reason plus exclusion/not-carried-forward wording, but does not duplicate the count in a second sentence.

      **Downgrade Factors:** If the intended final-output contract requires the exact additional `Ignored N foreign official...` wording and forbids relying on the copied summary count, the story/tests should say that explicitly. Current task text says the copied summary phrase may appear while explicitly excluding/not carrying forward foreign findings.

      **Code Trail:** `_footer_marker_policy_warnings()` parses the expected ignored count from the brief, then requires `count_visible` to match only `ignored {count}` or `{count} foreign official`. The implementation strips the copied summary phrase before contradiction scanning, but it does not let that phrase satisfy `count_visible`; the checked-in passing regression includes both the copied summary and an extra `Ignored 1 foreign official...` phrase, so it misses the valid copied-summary-only count shape.

      **Reproduction:** A read-only parent probe calling `_footer_marker_policy_warnings()` with a final note containing `Accepted official-footer remote entries: 0; foreign official-footer ignored comments: 1`, the PR22/session/head vs PR18 reason tokens, and `foreign findings were excluded ... not carried forward` returned `['missing_footer_marker_policy_audit_note']`; adding only `Ignored 1 foreign official...` changed the result to `[]`.

      </details>
  - Debt Friction: none
  - Next action: `/openspec-story-resume cure-subsequent-pr-review story-04-review-runtime-integration-guardrails-memory-trace` to add a red regression/fix for the copied-summary-only ignored-footer count visibility path; keep A16/A17/A19/A20 proof rows provisional until a fresh PR #22 live audit is actually run or the story is explicitly rescoped.

- 2026-06-16T10:29:26Z Review run by fresh maintainer session
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
  - Original intent checked: workspace `AGENTS.md`; initiative/story/proposal/design/tasks/progress/reviews; prior PR18/PR22 live-audit intent recorded in OpenSpec artifacts. No fresh live PR18/PR22 audit was run.
  - Traceability: forward gaps; backward gaps
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: OpenSpec proof/status/tasks/progress/reviews; `git status --short`, `git diff --stat`, `git diff --numstat`; `cure_subsequent_review/memory_store.py` stable identity/replay persistence; `cure_subsequent_review/source_truth.py` cache lookup; `cure_subsequent_review/control_plane.py` runtime module manifest/default status and intake paths; `cure_subsequent_review/degraded_runtime.py` controller success/degraded paths; `cure_subsequent_review/runtime.py` issue-history/footer-governor audit logic; `cure.py` PR-flow runtime callsites via focused pass; maintained final prompt templates; Story 04 focused tests in memory-store, degraded-runtime, control-plane, runtime-packaging, report-governor, PR-flow, and prompt suites.
  - Risk lenses reviewed: source-verification cache identity drift after replay persistence, prompt/template fail-open, report-governor false positives/contradictions, foreign-footer provenance final-output visibility, module-12 artifact lifecycle for successful empty discussion, runtime manifest status honesty, disabled/degraded branch coverage, dirty main-tree review hygiene, and proof-maturity/live-audit gate.
  - Finding closure: 2026-06-16T08:35:12Z A20 replay-persisted changed-source-reference blocker is resolved locally by direct source/test inspection and memory-store suite (`14 passed, 7 subtests`); A16/A17/A19/A20 live-proof gate remains open; new local blockers found for module-12 healthy empty fetch manifest/artifact recording and report-governor copied footer-summary false positives.
  - Evidence quality: confirmed direct source/OpenSpec/test reads, four focused multipass child passes, parent memory-store test `14 passed, 7 subtests`, parent `git diff --check`, parent deterministic probes for module-12 empty success and footer-governor copied-summary false positive, focused pass reported runtime unittest suite `43 tests OK`, and focused pass reported report-governor/runtime-packaging/prompt suite `158 passed, 8 subtests`; inferred none material; unknown fresh PR22 live-output/cache behavior because live audit intentionally not run; provisional A16/A17/A19/A20 live proof remains.
  - Files reviewed: `AGENTS.md`; `openspec/initiatives/cure-subsequent-pr-review/initiative.md`; `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,proposal.md,design.md,tasks.md,progress.md,reviews.md}`; `/home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md`; `cure_subsequent_review/contracts.py`; `cure_subsequent_review/control_plane.py`; `cure_subsequent_review/degraded_runtime.py`; `cure_subsequent_review/runtime.py`; `cure_subsequent_review/memory_store.py`; `cure_subsequent_review/source_truth.py`; `cure.py`; maintained prompt templates; `tests/_subsequent_review_unit_memory_store_unittest.py`; `tests/_subsequent_review_unit_degraded_runtime_unittest.py`; `tests/_subsequent_review_functional_control_plane_unittest.py`; `tests/_subsequent_review_unit_runtime_packaging_unittest.py`; `tests/_subsequent_review_unit_report_governor_unittest.py`; `tests/_subsequent_review_integration_pr_flow_unittest.py`; `tests/_reviewflow_unittest_prompt_session_impl.py`; `tests/fixtures/subsequent_review/landmark_trace/artifacts/review.md`.
  - Hypothesis triage:
    - suspicious surface: OpenSpec proof matrix/live-audit tasks; tentative issue: local approval would ignore provisional A16/A17/A19/A20 rows and unchecked fresh PR #22 live audit; next proof target: run or explicitly rescope the PR #22 live audit and convert proof rows to final only with evidence.
    - suspicious surface: `DiscussionFetchController.fetch()` success path with zero discussion events; tentative issue: module 12 can execute successfully without writing `degraded_runtime.json`, leaving the manifest row at default `enabled` instead of an observed `success`; next proof target: empty-events success regression through controller plus `run_subsequent_review_intake()`.
    - suspicious surface: `_footer_marker_policy_warnings()` positive foreign-footer regex; tentative issue: a valid final note that copies the governor policy summary can be falsely classified as a contradicted ignored-footer note; next proof target: regression for copied `Accepted official-footer remote entries: 0; foreign official-footer ignored comments: 1` summary plus excluded/not-carried-forward wording.
  - Key findings:
    - A16/A17/A19/A20 proof maturity and the fresh PR #22 live-audit gate still block approval. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:8`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:186`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:187`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:189`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:190`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/tasks.md:32`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/progress.md:23`, `/home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md:446`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** The story-review approval gate requires final proof rows. Story 04 still records A16, A17, A19, and A20 as provisional, leaves the fresh PR #22 live-audit task unchecked, and current progress says no fresh PR #22 live audit was run after the latest local A20 fix.

      **Assumptions / Preconditions:** None.

      **Downgrade Factors:** If the team wants a local-only approval split from live PR-stage proof, the story/proof matrix must explicitly rescope those rows before review can approve.

      **Code Trail:** The story header names the pending PR #22 live-audit gate; the proof matrix marks A16/A17/A19/A20 provisional; `tasks.md` leaves the live-audit row unchecked; `progress.md` preserves the same pending state after the latest local fix; the review skill says approval is allowed only when every proof row is final.

      **Reproduction:** `rg -n "A16 \\| provisional|A17 \\| provisional|A19 \\| provisional|A20 \\| provisional|Run and audit a fresh PR #22|fresh PR #22 live audit|every proof row is final" openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,tasks.md,progress.md} /home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md` returns the cited provisional rows, pending task/progress statements, and approval rule.

      </details>
    - A1/module-12 remains incomplete for a healthy empty discussion fetch: the controller succeeds without a `degraded_runtime.json`, so the manifest records only default `enabled` instead of success. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:103`, `cure_subsequent_review/degraded_runtime.py:54`, `cure_subsequent_review/degraded_runtime.py:55`, `cure_subsequent_review/degraded_runtime.py:56`, `cure_subsequent_review/control_plane.py:177`, `cure_subsequent_review/control_plane.py:179`, `cure_subsequent_review/control_plane.py:180`, `cure_subsequent_review/control_plane.py:186`, `cure_subsequent_review/control_plane.py:81`, `cure_subsequent_review/control_plane.py:86`, `cure_subsequent_review/control_plane.py:87`, `tests/_subsequent_review_unit_degraded_runtime_unittest.py:9`, `tests/_subsequent_review_functional_control_plane_unittest.py:152`

      <details open>
      <summary><b>Medium</b> severity · <b>Medium</b> likelihood</summary>

      **Why:** A1 requires modules 9-12 to be first-class runtime modules with manifest records. A successful PR-discussion fetch with zero events is still module-12 execution, especially for runs enabled by prior completed sessions rather than current PR discussion. Current code returns without writing the module-12 artifact when `events` is empty and no prior retry/choice occurred, so intake has no `degraded_runtime_path` to record and the manifest fabricates the row as merely `enabled`.

      **Assumptions / Preconditions:** Subsequent review is enabled by completed-session evidence or other prior-review state, and `collect_pr_discussion()` succeeds with no current discussion events.

      **Downgrade Factors:** If Story 04 intentionally only requires a success artifact for healthy fetches with at least one event, A1/progress should be narrowed because current wording says module records, not eventful-only records.

      **Code Trail:** `DiscussionFetchController.fetch()` writes success only when choices exist or the successful artifact has events; `run_subsequent_review_intake()` records `DEGRADED_RUNTIME_MANAGER` only when a path is passed; missing module rows default to `ModuleStatus.ENABLED` in `_manifest_json()`. Existing tests cover a healthy first fetch with an event and an intake call with a prewritten controller artifact, but not the empty successful fetch branch.

      **Reproduction:** A read-only probe using `DiscussionArtifact(status=success, events=())` returned `controller_status success events 0 artifact_exists False`; passing that prefetched discussion into `run_subsequent_review_intake()` for an enabled run produced `manifest_degraded {'status': 'enabled'}` and no `degraded_runtime.json`.

      </details>
    - A17/A19 report-governor can falsely degrade a valid ignored-foreign-footer audit note when the final review copies the governor policy summary. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:119`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:121`, `cure_subsequent_review/runtime.py:569`, `cure_subsequent_review/runtime.py:570`, `cure_subsequent_review/runtime.py:571`, `cure_subsequent_review/runtime.py:952`, `cure_subsequent_review/runtime.py:956`, `cure_subsequent_review/runtime.py:958`, `cure_subsequent_review/runtime.py:962`, `cure_subsequent_review/runtime.py:963`, `cure_subsequent_review/runtime.py:979`, `cure_subsequent_review/runtime.py:980`, `prompts/default.md:20`, `tests/_subsequent_review_unit_report_governor_unittest.py:550`

      <details open>
      <summary><b>Medium</b> severity · <b>Medium</b> likelihood</summary>

      **Why:** A17/A19 require final reviews to include a concise ignored-foreign-footer note with count and plain-English reason while excluding foreign findings. The maintained prompt asks for that note, and the governor brief itself emits the summary phrase `Accepted official-footer remote entries: 0; foreign official-footer ignored comments: 1`. If a valid final review copies that summary and then says the foreign findings were excluded/not carried forward, the deterministic checker sees `accepted` within 80 characters of `foreign official` and records `contradicted_footer_marker_policy_audit_note`.

      **Assumptions / Preconditions:** `governor_brief.md` has one or more ignored foreign official-footer comments; the final report includes the required ignored count/reason and copies or paraphrases the policy summary containing `Accepted official-footer remote entries: 0` near `foreign official-footer ignored comments`.

      **Downgrade Factors:** If final-output guidance forbids copying the governor summary phrase and requires only a narrower ignored-note wording, the impact narrows, but current prompts/tests require the count/reason surface and do not prohibit that natural wording.

      **Code Trail:** The brief builder prints `Accepted official-footer remote entries: ...; foreign official-footer ignored comments: ...`; `_footer_marker_policy_warnings()` treats accepted/admitted/included/carried-forward verbs near `foreign official`/`official footer` as a contradiction before checking count/reason/exclusion completeness. The positive contradiction and negated-exclusion tests cover simpler notes, but no test covers a valid note that includes the policy summary phrase.

      **Reproduction:** A parent probe calling `_footer_marker_policy_warnings()` with a valid final note containing `Accepted official-footer remote entries: 0; foreign official-footer ignored comments: 1... Ignored 1 foreign official CURe footer comment ... foreign findings were excluded and not carried forward` returned `['contradicted_footer_marker_policy_audit_note']`.

      </details>
  - Debt Friction: none
  - Next action: `/openspec-story-resume cure-subsequent-pr-review story-04-review-runtime-integration-guardrails-memory-trace` to add red regressions/fixes for module-12 healthy empty fetch artifact/manifest recording and the footer-governor copied-summary false positive; keep A16/A17/A19/A20 proof rows provisional until a fresh PR #22 live audit is actually run or the story is explicitly rescoped.

- 2026-06-16T08:35:12Z Review run by fresh maintainer session
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
  - Original intent checked: workspace `AGENTS.md`; initiative/story/proposal/design/tasks/progress/reviews; prior PR18/PR22 audit intent recorded in OpenSpec artifacts. No fresh live PR18/PR22 audit was run.
  - Traceability: forward gaps; backward complete for reviewed local surfaces
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: current OpenSpec proof/status/task rows; `cure_subsequent_review/memory_store.py` stable-identity/cache replay/persistence paths; `tests/_subsequent_review_unit_memory_store_unittest.py` A20 replay/miss fixtures; focused child-pass coverage over runtime/control-plane/degraded discussion, report governor/final-output packaging, semantic/source/linker/memory, and proof/status state.
  - Risk lenses reviewed: source-verification cache identity drift after replay persistence, origin-only source-reference masking, verifier fan-out/performance proof honesty, final-output proof maturity, dirty main-tree review hygiene, and live-audit readiness.
  - Finding closure: 2026-06-16T08:00:02Z local A1 module override/healthy module-12 manifest blocker is resolved by focused runtime/control-plane pass; A17/A19 positive and negated foreign-footer final-output wording blockers are resolved by focused governor/packager pass; A20 remains open through a deeper replay-persistence variant; A16/A17/A19/A20 live-proof rows remain provisional.
  - Evidence quality: confirmed direct OpenSpec/source/test reads, four focused multipass child passes, targeted suites reported `47 passed, 4 subtests`, `76 passed, 2 subtests`, and `37 passed, 7 subtests`, plus the preserved direct Python probe reproducing the A20 replay-persisted changed-source-reference cache hit; inferred none material; unknown fresh PR22 live-output/cache behavior because live audit intentionally not run; provisional A16/A17/A19/A20 live proof remains.
  - Files reviewed: `AGENTS.md`; `openspec/initiatives/cure-subsequent-pr-review/initiative.md`; `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,proposal.md,design.md,tasks.md,progress.md,reviews.md}`; `/home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md`; `cure_subsequent_review/control_plane.py`; `cure_subsequent_review/degraded_runtime.py`; `cure_subsequent_review/runtime.py`; `cure_subsequent_review/memory_store.py`; `cure_subsequent_review/source_truth.py`; `cure_subsequent_review/semantic_pipeline.py`; `cure.py`; maintained prompt templates; `tests/_subsequent_review_unit_memory_store_unittest.py`; `tests/_subsequent_review_unit_runtime_memory_unittest.py`; `tests/_subsequent_review_unit_semantic_pipeline_unittest.py`; `tests/_subsequent_review_integration_pr_flow_unittest.py`; `tests/_subsequent_review_unit_report_governor_unittest.py`; `tests/_subsequent_review_unit_runtime_packaging_unittest.py`; `tests/_subsequent_review_functional_control_plane_unittest.py`; `tests/test_subsequent_review.py`.
  - Hypothesis triage:
    - suspicious surface: `ReviewMemoryStore.synthesize_source_row()` followed by `update_findings()`; tentative issue: replayed rows persist current provenance with a same-origin digest that lets a later changed source reference hit cache; next proof target: red regression that seeds same-head source memory, persists a replay row, then changes `inspected_source_refs` and expects verifier invocation / `stable_identity_mismatch`.
    - suspicious surface: OpenSpec proof matrix/live-audit tasks; tentative issue: local approval would ignore provisional A16/A17/A19/A20 rows and an unchecked fresh PR #22 live audit; next proof target: run or explicitly rescope the PR #22 live audit and convert proof rows from provisional to final only with evidence.
  - Key findings:
    - A20 replay-persisted memory rows can mask changed source references via an origin-only stable-identity match. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:122`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:190`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/tasks.md:41`, `cure_subsequent_review/memory_store.py:56`, `cure_subsequent_review/memory_store.py:77`, `cure_subsequent_review/memory_store.py:92`, `cure_subsequent_review/memory_store.py:99`, `cure_subsequent_review/memory_store.py:129`, `cure_subsequent_review/memory_store.py:152`, `cure_subsequent_review/memory_store.py:197`, `cure_subsequent_review/memory_store.py:233`, `cure_subsequent_review/memory_store.py:347`, `cure_subsequent_review/memory_store.py:412`, `tests/_subsequent_review_unit_memory_store_unittest.py:410`, `tests/_subsequent_review_unit_memory_store_unittest.py:463`, `tests/_subsequent_review_unit_memory_store_unittest.py:502`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** A20 requires source-verification cache replay to use stable finding identity/fingerprint/source-reference identity plus current head, and to miss when source-reference identity drifts. The latest explicit repeated-display-ID and changed-source-reference tests cover fresh lookup ingredients, but not the sequence where a memory-cache replay row is itself persisted. In that sequence, a changed `app.py:44` source reference can reuse a previous `app.py:10` source-resolved row without any verifier call, so the cache can silently mask changed source evidence and undercut the PR #22 verifier-storm/performance proof.

      **Assumptions / Preconditions:** Same PR/head; a prior source-resolved memory row exists; a subsequent run replays and persists that row; a later reconciliation group has the same display/title/origin metadata but different inspected source reference or source-reference digest.

      **Downgrade Factors:** If `origin_digest` is intentionally allowed to override source-reference drift, A20/tasks must be narrowed because current text says source-reference identity drift records a miss and verifies.

      **Code Trail:** `_stable_identity_from_row()` preserves nested cached identity fields from replay provenance; `group_identity_for_cache()` computes an `origin_digest` from prior-corpus origin metadata; `_stable_identity_matches()` returns true when any one of `source_refs_digest`, `citations_digest`, or `origin_digest` matches; `synthesize_source_row()` writes the current identity into replay provenance; `update_findings()` then persists that replayed row and its nested identity. The standalone tests cover replay persistence, repeated-display-ID miss, and changed-source-reference miss separately, but no test composes replay persistence with a later changed source reference.

      **Reproduction:** Seed memory for finding `A-01` at `app.py:10`; run same-head replay and persist the replayed row; rerun with the same display/title/origin but changed source ref `app.py:44`. The direct probe observed `second_calls []`, `second_source memory_cache`, `second_cache_status hit`, and `second_cache_reason resolved_from_source_replay`; expected behavior is a fresh verifier call and a `stable_identity_mismatch` miss.

      </details>
    - A16/A17/A19/A20 proof maturity and the fresh PR #22 live-audit gate still block approval. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:8`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:186`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:187`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:189`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:190`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/tasks.md:32`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/progress.md:190`, `/home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md:449`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** The review gate allows approval only when every proof row is final. Story 04 still records A16, A17, A19, and A20 as `provisional`, leaves the fresh PR #22 live review unchecked, and says PR/live status remains request-changes until that fresh audit verifies the provisional rows. Local focused suites are useful evidence, but they do not satisfy the story's own live-output/cache closure condition.

      **Assumptions / Preconditions:** None.

      **Downgrade Factors:** If the team wants a local-only approval split from live PR-stage evidence, the story/proof matrix must explicitly rescope those rows before a review can approve.

      **Code Trail:** The story header names the pending fresh PR #22 live-audit gate, the proof matrix marks A16/A17/A19/A20 provisional, `tasks.md` leaves the live-audit task unchecked, and `progress.md` keeps PR/live status at request-changes pending the audit. The review skill's approval checklist requires every proof row to be final.

      **Reproduction:** `rg -n "A16 \\| provisional|A17 \\| provisional|A19 \\| provisional|A20 \\| provisional|Run and audit a fresh PR #22|fresh PR #22 live audit|every proof row is final" openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,tasks.md,progress.md} /home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md` returns the cited provisional rows, pending task/progress statements, and gate.

      </details>
  - Debt Friction: none
  - Next action: `/openspec-story-resume cure-subsequent-pr-review story-04-review-runtime-integration-guardrails-memory-trace` to add the replay-persisted changed-source-reference regression/fix, keep A16/A17/A19/A20 proof rows provisional until a fresh PR #22 live audit is actually run (or explicitly rescope the story), and then return for review.

- 2026-06-16T08:00:02Z Review run by fresh maintainer session
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
  - Original intent checked: workspace `AGENTS.md`; initiative/story/proposal/design/tasks/progress/reviews; local PR18/PR22 intent recorded in OpenSpec artifacts. No fresh live PR18/PR22 audit was run.
  - Traceability: forward gaps; backward gaps
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: `git status --short`, `git diff --stat`, `git diff --numstat`, acceptance/proof matrix lines, `cure_subsequent_review/runtime.py` footer-policy/report-governor paths, `control_plane.py` module override and degraded-runtime manifest paths, `degraded_runtime.py` fetch controller, `_pr_flow_impl` degraded-controller wiring, maintained final prompt templates, A16/A17/A19 report-governor tests, A19 runtime-packaging/prior-corpus/decision replay tests, A20 memory-store/source-truth/control-plane tests, and OpenSpec proof/status tasks.
  - Risk lenses reviewed: prompt/template fail-open, runtime module override/manifest ownership, degraded PR-discussion controller artifact lifecycle, post-review governor contradiction false negatives/false positives, foreign-footer provenance final-output visibility, source-verification cache identity/proof honesty, dirty main-tree review hygiene, and proof-maturity/live-audit gate.
  - Finding closure: the 2026-06-16T07:39:27Z valid negated ignored-footer false-positive is resolved for `not included` / `not carried forward`; A16 reason-preservation and A19 replay proof look locally covered; newly found A17/A19 positive `admitted` / `carried forward` foreign-official wording still passes incorrectly; A1 module override/manifest completeness is incomplete; A20 FB-041 proof wording overclaims visible tests; A16/A17/A19/A20 live proof remains provisional.
  - Evidence quality: confirmed direct OpenSpec/source/test reads, four focused multipass child passes verified against primary anchors, parent repro of `_footer_marker_policy_warnings()`, parent focused suite `24 passed`, focused children reported `192 passed, 7 subtests`, `64 passed, 5 subtests`, `38 passed, 8 subtests`, `43 passed, 12 subtests`, public wrapper `144 passed, 36 subtests`, and parent `git diff --check` clean; inferred none material; unknown fresh PR22 live-output behavior because live audit intentionally not run; provisional A16/A17/A19/A20 live proof remains.
  - Files reviewed: `AGENTS.md`; `openspec/initiatives/cure-subsequent-pr-review/initiative.md`; `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,proposal.md,design.md,tasks.md,progress.md,reviews.md}`; `/home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md`; `cure_subsequent_review/runtime.py`; `cure_subsequent_review/control_plane.py`; `cure_subsequent_review/degraded_runtime.py`; `cure_subsequent_review/memory_store.py`; `cure_subsequent_review/source_truth.py`; `cure_subsequent_review/semantic_pipeline.py`; `cure.py`; maintained prompt templates; `tests/_subsequent_review_unit_report_governor_unittest.py`; `tests/_subsequent_review_unit_runtime_packaging_unittest.py`; `tests/_subsequent_review_unit_memory_store_unittest.py`; `tests/_subsequent_review_unit_runtime_memory_unittest.py`; `tests/_subsequent_review_unit_semantic_pipeline_unittest.py`; `tests/_subsequent_review_integration_pr_flow_unittest.py`; `tests/_reviewflow_unittest_prompt_session_impl.py`.
  - Hypothesis triage:
    - suspicious surface: modules 9-12 runtime module ownership; tentative issue: module override support and healthy module-12 manifest/artifact recording are incomplete; next proof target: `SubsequentReviewConfig.module_enabled()`, `prepare_review_runtime_pre_prompt()`, `DiscussionFetchController.fetch()`, and `run_subsequent_review_intake()` manifest recording.
    - suspicious surface: `_footer_marker_policy_warnings()` contradiction detection; tentative issue: positive `admitted` / `carried forward` wording tied to `foreign official` comments is not classified as a contradicted ignored-footer audit note; next proof target: regex patterns and a positive-verb regression.
    - suspicious surface: OpenSpec proof matrix/live audit; tentative issue: local approval would ignore provisional A16/A17/A19/A20 rows and unchecked PR #22 live audit; next proof target: proof rows, live-audit task, and review-skill approval gate.
    - suspicious surface: A20 FB-041 proof wording; tentative issue: checked task claims repeated-display-ID and changed-source-reference regressions that are not visible in current tests; next proof target: memory-store test names/fixtures or narrowed OpenSpec wording.
  - Key findings:
    - A16/A17/A19/A20 proof maturity still blocks approval under the story-review gate. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:186`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:187`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:189`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:190`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/tasks.md:32`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/progress.md:181`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/progress.md:189`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** The review gate cannot approve while the story itself records provisional proof rows and an unchecked fresh PR #22 live audit. The OpenSpec state is honest, but it means Story 04 remains in progress until the live-output/cache proof is run and rows become final, or the story is explicitly rescoped.

      **Assumptions / Preconditions:** None.

      **Downgrade Factors:** If the team wants a local-only approval split from live PR-stage proof, the proof matrix/status policy must explicitly record that scope before a review can approve.

      **Code Trail:** The proof matrix marks A16, A17, A19, and A20 as `provisional`; `tasks.md` leaves the fresh PR #22 live review unchecked; `progress.md` says PR/live status remains request-changes until that audit verifies the provisional rows.

      **Reproduction:** `grep -nE "A16 \\| provisional|A17 \\| provisional|A19 \\| provisional|A20 \\| provisional|Run and audit a fresh PR #22|live audit" openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,tasks.md,progress.md}` returns the cited provisional rows and pending live-audit statements.

      </details>
    - A1 is incomplete: modules 9/10/12 do not share runtime module override support, and module 12 can execute without a healthy-run manifest/artifact record. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:103`, `cure_subsequent_review/control_plane.py:44`, `cure_subsequent_review/control_plane.py:48`, `cure_subsequent_review/runtime.py:1228`, `cure_subsequent_review/runtime.py:1248`, `cure_subsequent_review/runtime.py:1250`, `cure.py:9885`, `cure.py:9902`, `cure_subsequent_review/degraded_runtime.py:54`, `cure_subsequent_review/degraded_runtime.py:56`, `cure_subsequent_review/control_plane.py:170`, `cure_subsequent_review/control_plane.py:178`, `cure_subsequent_review/control_plane.py:242`

      <details open>
      <summary><b>Medium</b> severity · <b>High</b> likelihood</summary>

      **Why:** A1 requires modules 9-12 to be first-class runtime modules with manifest records and module override support. Current code only checks override state generically for Story 01 and semantic-registry modules, special-cases module 11, and runs modules 9/10 plus the module-12 controller without an override path. On a non-degraded discussion fetch, module 12 returns without writing `degraded_runtime.json`; `_pr_flow_impl` then passes `degraded_runtime_path=None`, and intake only records module 12 when that path exists.

      **Assumptions / Preconditions:** Enabled subsequent review with a healthy PR discussion fetch, or an operator/runtime configuration that disables one of modules 9/10/12.

      **Downgrade Factors:** If module override support is intentionally scoped only to Story 01/semantic modules plus module 11, A1 needs to be narrowed; as written, A1 names modules 9-12.

      **Code Trail:** `SubsequentReviewConfig.module_enabled()` returns enabled only for Story 01 modules and `semantic_pipeline.MODULE_REGISTRY`, not runtime modules 9/10/12. `prepare_review_runtime_pre_prompt()` has no config/override parameter and always writes the packager record before only considering governor mode `off`. `_pr_flow_impl` always constructs/fetches through `DiscussionFetchController` when subsequent-review mode is not disabled, but only retains `degraded_runtime_path` if the controller wrote an artifact. `DiscussionFetchController.fetch()` writes success only after prior degraded choices, not on a healthy first fetch. `run_subsequent_review_intake()` records module 12 only when a degraded-runtime artifact path is passed, while module 11 alone has a disabled-override special case.

      **Reproduction:** Inspect the cited call path or run an enabled healthy discussion fetch: the controller returns the artifact without writing `degraded_runtime.json`, `_pr_flow_impl` leaves `degraded_runtime_path=None`, and no `DEGRADED_RUNTIME_MANAGER` success record is added by intake.

      </details>
    - A17/A19 still miss positive ignored-footer contradictions when the final output says a foreign official footer was `admitted` or `carried forward`. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:119`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:121`, `cure_subsequent_review/runtime.py:924`, `cure_subsequent_review/runtime.py:940`, `cure_subsequent_review/runtime.py:947`, `cure_subsequent_review/runtime.py:949`, `cure_subsequent_review/runtime.py:964`, `cure_subsequent_review/runtime.py:966`, `tests/_subsequent_review_unit_report_governor_unittest.py:461`, `tests/_subsequent_review_unit_report_governor_unittest.py:485`, `tests/_subsequent_review_unit_report_governor_unittest.py:505`, `tests/_subsequent_review_unit_report_governor_unittest.py:529`

      <details open>
      <summary><b>Medium</b> severity · <b>High</b> likelihood</summary>

      **Why:** A17/A19 require final-output contradictions about ignored foreign official-footers to degrade. The latest fix correctly allows valid negated wording such as `not included` / `not carried forward`, and it degrades the existing positive `Included 1 foreign official... foreign findings were carried forward` fixture. However, the regex only applies the broad positive verb set to `foreign findings?`, while `foreign official` only checks the `include*` verb. A final review can therefore say `Admitted 1 foreign official CURe footer comment ... foreign findings were excluded` or `Carried forward 1 foreign official CURe footer comment ... foreign findings were excluded`; the deterministic checker returns success.

      **Assumptions / Preconditions:** `governor_brief.md` reports one or more ignored foreign official-footer comments and final `review.md` includes the count/reason tokens plus positive action wording attached to the foreign official footer while separately saying findings were excluded.

      **Downgrade Factors:** If the contract only wants to reject contradictions about `foreign findings` and not contradictions about the ignored `foreign official` comment itself, A17/A19 should say so. Current wording requires omitted or contradicted foreign-footer audit notes to degrade.

      **Code Trail:** `_footer_marker_policy_warnings()` treats exclusion phrases, including negated terms, as valid. It defines `positive_include` separately from a broader `positive_foreign_finding_action`; the `foreign official` regexes use only `positive_include`, while `admitted` / `carried forward` are only matched near `foreign findings?`. The function returns a contradiction only when `contradiction_visible` is true, otherwise it accepts any count/policy/reason/exclusion-visible note.

      **Reproduction:** Parent probe with the same brief shape as the tests returned `[]` for `_footer_marker_policy_warnings()` on `Admitted 1 foreign official CURe footer comment ...; foreign findings were excluded.` and `Carried forward 1 foreign official CURe footer comment ...; foreign findings were excluded.`, while the valid negated note returned `[]` and the existing included/carry-forward fixture returned `['contradicted_footer_marker_policy_audit_note']`.

      </details>
    - A20 FB-041 task/proof wording overclaims visible regression coverage for repeated-display-ID and changed-source-reference cases. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/tasks.md:41`, `tests/_subsequent_review_unit_memory_store_unittest.py:204`, `tests/_subsequent_review_unit_memory_store_unittest.py:367`, `tests/_subsequent_review_unit_memory_store_unittest.py:463`, `cure_subsequent_review/memory_store.py:63`, `cure_subsequent_review/memory_store.py:129`, `cure_subsequent_review/memory_store.py:343`

      <details open>
      <summary><b>Medium</b> severity · <b>Medium</b> likelihood</summary>

      **Why:** The task checklist says FB-041 added reordered-group, repeated-display-ID, changed-source-reference, and ordinal-only-match cases. The current tests visibly cover same-ordinal different identity, reordered group hit, and ordinal-only mismatch, and the implementation includes source-reference digest fields in stable identity. A repo-wide search did not find explicit repeated-display-ID or changed-source-reference regression cases, so the checked task and proof narrative are stronger than the available tests.

      **Assumptions / Preconditions:** The task checkbox is intended to mean each named variant has an explicit local regression, not merely that the implementation contains the source-reference digest mechanism.

      **Downgrade Factors:** If repeated-display-ID and changed-source-reference are intentionally covered by the generic stable-identity mismatch fixture, narrow the task/proof wording to that actual proof boundary.

      **Code Trail:** `tasks.md` names four FB-041 variants. The memory-store tests around the cited anchors cover different finding identity at same ordinal, stable-identity hit after reordered `group_id`, and ordinal-only mismatch. The stable identity builder does include `inspected_source_refs` digesting, but no explicit changed-source-reference regression was found in the test file.

      **Reproduction:** `rg -n "repeated|display|source.ref|source_reference|changed.*source|ordinal|group_id" tests/_subsequent_review_unit_memory_store_unittest.py cure_subsequent_review/memory_store.py openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/tasks.md` returns the task wording, stable-identity source-reference implementation, and ordinal/reordered tests, but no explicit repeated-display-ID or changed-source-reference test case.

      </details>
  - Debt Friction: none
  - Next action: `/openspec-story-resume cure-subsequent-pr-review story-04-review-runtime-integration-guardrails-memory-trace` to add/fix module override + healthy module-12 manifest support, broaden A17/A19 positive footer contradiction tests/fix, align A20 FB-041 proof wording or tests, and keep the fresh PR #22 live-audit gate pending until it is actually run.

- 2026-06-16T07:39:27Z Review run by fresh maintainer session
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
  - Original intent checked: initiative/story/proposal/design/tasks/progress/reviews and PR #22 / PR #18 intent recorded in OpenSpec artifacts; no fresh live PR18/PR22 audit run.
  - Traceability: forward gaps; backward complete for current dirty files reviewed
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: `git status --short`, `git diff --stat`, `git diff --numstat`, OpenSpec proof/status/progress/reviews, `cure_subsequent_review/runtime.py` issue-history/footer/governor paths, maintained final prompt templates, `tests/_subsequent_review_unit_report_governor_unittest.py`, `tests/_subsequent_review_unit_runtime_packaging_unittest.py`, `tests/_reviewflow_unittest_prompt_session_impl.py`, landmark review fixture, and prior-corpus/runtime replay assertions.
  - Risk lenses reviewed: prompt/template fail-open, post-review governor false positives/contradictions, foreign-footer provenance audit visibility, pre-corpus exclusion and downstream pollution, verifier fan-out proof, proof-maturity/live-audit gate, dirty main-tree review hygiene.
  - Finding closure: prior 2026-06-16T06:57:53Z positive contradicted-note blocker is fixed for included/carried-forward wording; PR18/PR22 replay now directly reads `prior_review_corpus.json` and covers an issue-comment foreign footer plus pull-review event-head mismatch; provisional live-output/live-audit proof remains still open; a new valid-note false-positive was found in the contradiction regex.
  - Evidence quality: confirmed direct OpenSpec/source/test reads, three focused multipass child passes verified against primary anchors, targeted focused tests from child passes (`23 passed`; `155 passed, 6 subtests`), and parent read-only probes of `_issue_history_warnings()` / `_footer_marker_policy_warnings()`; inferred none material; unknown fresh PR22 live-output behavior because live audit intentionally not run; provisional A16/A17/A19/A20 proof remains.
  - Files reviewed: `openspec/initiatives/cure-subsequent-pr-review/initiative.md`; `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,proposal.md,design.md,tasks.md,progress.md,reviews.md}`; `/home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md`; `cure_subsequent_review/runtime.py`; maintained prompt templates under `prompts/`; `tests/_reviewflow_unittest_prompt_session_impl.py`; `tests/_subsequent_review_unit_report_governor_unittest.py`; `tests/_subsequent_review_unit_runtime_packaging_unittest.py`; `tests/fixtures/subsequent_review/landmark_trace/artifacts/review.md`.
  - Hypothesis triage:
    - suspicious surface: `_footer_marker_policy_warnings()` contradiction detection; tentative issue: negated valid phrasing such as “foreign findings were not included” is classified as a contradicted ignored-footer note; next proof target: footer-policy regex and a valid negated-inclusion regression.
    - suspicious surface: A16 exact `Reason:` marker; tentative issue: deterministic validator accepts preserved reason text without the literal label; next proof target: A16 wording and prompt/tests. Not promoted because the story acceptance requires the reason content, not exact punctuation.
    - suspicious surface: PR18/PR22 replay fixture; tentative issue: prior proof did not inspect corpus or event-head mismatch; next proof target: runtime replay test. Resolved by direct corpus assertions and pull-review event-head mismatch coverage.
    - suspicious surface: OpenSpec proof matrix/live audit; tentative issue: local review would approve while proof rows remain provisional; next proof target: A16/A17/A19/A20 proof rows, live-audit task, and review-skill gate.
  - Key findings:
    - A16/A17/A19/A20 proof maturity still blocks approval under the story-review gate. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:8`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:186`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:187`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:189`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:190`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/tasks.md:32`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/progress.md:172`, `/home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md:102`, `/home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md:450`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** The review gate requires final proof rows before approval. Story 04 still says the local implementation remains in progress until a fresh PR #22 live audit closes the runtime-owned guardrails, and A16/A17/A19/A20 remain provisional with the fresh live audit task unchecked.

      **Assumptions / Preconditions:** None.

      **Downgrade Factors:** If the team intentionally wants a local-only approval split from the PR-stage live audit, the story/proof matrix must explicitly rescope those provisional rows before approval can rely on that distinction.

      **Code Trail:** The story header names the pending PR #22 live audit gate; the proof matrix keeps A16/A17/A19/A20 provisional; `tasks.md` leaves the fresh PR #22 live review unchecked; progress says PR/live status remains request-changes until the fresh audit verifies the provisional rows; the review skill forbids approval while proof rows remain provisional and requires every proof row to be final.

      **Reproduction:** `rg -n "A16 \\| provisional|A17 \\| provisional|A19 \\| provisional|A20 \\| provisional|Run and audit a fresh PR #22|fresh PR #22 live audit|any proof row is still|every proof row is final" openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,tasks.md,progress.md} /home/vscode/.pi/agent/skills/openspec-story-review/SKILL.md` returns the provisional rows, pending task/progress statements, and review gate.

      </details>
    - A17/A19 footer-policy checker falsely degrades a valid ignored-foreign-footer audit note that says foreign findings were “not included.” Sources: `cure_subsequent_review/runtime.py:928`, `cure_subsequent_review/runtime.py:932`, `cure_subsequent_review/runtime.py:945`, `cure_subsequent_review/runtime.py:961`, `cure_subsequent_review/runtime.py:1150`, `cure_subsequent_review/runtime.py:1158`, `tests/_subsequent_review_unit_report_governor_unittest.py:521`

      <details open>
      <summary><b>Medium</b> severity · <b>High</b> likelihood</summary>

      **Why:** A17/A19 require the final review to include a concise ignored-foreign-footer audit note while excluding foreign findings, and the current test suite expects a valid note to pass. The implementation lists “not included” / “not carried forward” as acceptable exclusion language, but the contradiction regex still matches the positive words `included` / `carried forward` inside those negated phrases and forces `contradicted_footer_marker_policy_audit_note`.

      **Assumptions / Preconditions:** `governor_brief.md` reports one or more ignored foreign official-footer comments and final `review.md` uses common negated wording such as “foreign findings were not included in prior-review provenance” while otherwise including the count and durable reason tokens.

      **Downgrade Factors:** If final-output guidance forbids negated inclusion phrasing and requires only words like “excluded,” the impact narrows; the code currently treats “not included” as an accepted exclusion phrase, so the intended boundary is inconsistent.

      **Code Trail:** `_footer_marker_policy_warnings()` computes `exclusion_visible` from phrases including `not included` and `not carried forward`, then computes `contradiction_visible` from regexes that match `foreign findings ... included` and `foreign findings ... carried forward` without excluding negation. Because `contradiction_visible` is checked first, the valid note is reported as a contradiction; `audit_review_report_after_review()` hard-degrades on that warning.

      **Reproduction:** A read-only parent probe called `_footer_marker_policy_warnings()` with a brief containing `foreign official-footer ignored comments: 1` plus the PR22/PR18 audit reason, and a final note saying `Ignored 1 foreign official CURe footer comment ... foreign findings were not included in prior-review provenance`; the function returned `['contradicted_footer_marker_policy_audit_note']`.

      </details>
  - Debt Friction: none
  - Next action: `/openspec-story-resume cure-subsequent-pr-review story-04-review-runtime-integration-guardrails-memory-trace` to add a red regression/fix for the negated ignored-footer note false positive, then run/record the required fresh PR #22 live audit (or explicitly rescope the live proof rows) before seeking approval.

- 2026-06-16T06:57:53Z Review run by fresh maintainer session
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
  - Original intent checked: initiative.md, story/proposal/design/tasks/progress/reviews, dependency Story 01/02/03 status and footer/source/discussion separation anchors, PR18 benchmark notebook orientation; no fresh live PR18/PR22 audit run.
  - Traceability: forward gaps; backward complete for reviewed changed files
  - Design trace: not applicable; rendered evidence: not applicable
  - Code surfaces searched: `git status --short`, `git diff --stat`, `git diff --numstat`, `cure_subsequent_review/runtime.py` footer-policy/issue-history/report-governor paths, maintained final prompt templates, schema-bound and zip prompt exclusions, focused report-governor/runtime-packaging/prompt/prior-corpus/decision tests, OpenSpec A16/A17/A19/A20 proof rows and tasks.
  - Risk lenses reviewed: prompt/template fail-open, final-output contradiction detection, foreign-footer provenance audit visibility, pre-corpus exclusion and downstream pollution, verifier fan-out, proof-maturity/live-audit gate, dirty main-tree review hygiene.
  - Finding closure: A16 title/status/reason reason-preservation checks look locally covered; previous A19 footer-current/event-foreign provenance blocker remains closed by prior focused tests; A17/A19 contradiction detection and mandatory replay proof remain open; A16/A17/A19/A20 live-output proof maturity remains provisional.
  - Evidence quality: confirmed direct source/test/OpenSpec reads, multipass focused child passes checked against primary anchors, local contradiction repro, targeted focused suite `154 passed, 6 subtests`, `git diff --check` clean; inferred none material; unknown fresh PR22 live-output behavior because live audit intentionally not run; provisional A16/A17/A19/A20 live proof remains.
  - Files reviewed: `openspec/initiatives/cure-subsequent-pr-review/initiative.md`; `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,proposal.md,design.md,tasks.md,progress.md,reviews.md}`; dependency story headers for Stories 01-03; `cure_subsequent_review/runtime.py`; maintained prompt templates under `prompts/`; `tests/_reviewflow_unittest_prompt_session_impl.py`; `tests/_subsequent_review_unit_report_governor_unittest.py`; `tests/_subsequent_review_unit_runtime_packaging_unittest.py`; `tests/_subsequent_review_unit_prior_corpus_unittest.py`; `tests/fixtures/subsequent_review/landmark_trace/artifacts/review.md`.
  - Hypothesis triage:
    - suspicious surface: report-governor ignored-foreign-footer audit checker; tentative issue: a final review can include the same count/tokens while saying the foreign footer was included/carried forward; next proof target: `_footer_marker_policy_warnings()` plus a contradicted-note fixture.
    - suspicious surface: mandatory PR18/PR22 replay proof; tentative issue: exact PR18/PR22 fixture can pass without proving corpus-level exclusion or generalized mismatch variants; next proof target: runtime replay's `prior_review_corpus.json` assertions and parameterized PR/session/head/footer/event-head variants.
    - suspicious surface: OpenSpec proof maturity; tentative issue: local approval would ignore provisional live-output rows; next proof target: APM A16/A17/A19/A20 rows and live-audit task state.
  - Key findings:
    - A17/A19 post-review governor accepts a contradicted ignored-foreign-footer note as success. Sources: `cure_subsequent_review/runtime.py:916`, `cure_subsequent_review/runtime.py:922`, `cure_subsequent_review/runtime.py:935`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:98`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:164`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** Story A17/A19 requires the post-review governor to degrade when the final report omits or contradicts the ignored-foreign-footer audit note. The current deterministic checker only verifies that the final report contains a visible count, “foreign official” / “official footer” wording, and durable tokens from the ignored reason; it does not require ignored/excluded semantics or reject included/carried-forward semantics.

      **Assumptions / Preconditions:** `governor_brief.md` contains `foreign official-footer ignored comments: 1` plus an `Ignored remote CURe ...` audit reason; final `review.md` includes the same count/PR/session/SHA tokens while saying the foreign footer was included or foreign findings were carried forward; the auditor JSON reports awareness demonstrated.

      **Downgrade Factors:** If contradiction detection is intentionally delegated wholly to the LLM auditor, the story contract and deterministic proof need to record that narrower boundary. Current TAP-18/TAP-20 wording requires deterministic negative/positive final-output fixtures for omitted or contradicted notes.

      **Code Trail:** `_footer_marker_policy_warnings()` derives the expected count/reason from the brief, normalizes the final review, and returns success when `count_visible`, `policy_visible`, and `reason_visible` are true. It never checks for exclusion terms or contradictory terms. The report-governor hard-degrade list only includes `missing_footer_marker_policy_audit_note`, so a contradicted note with the right tokens writes `report_governor_result.json` as success.

      **Reproduction:** A temp-artifact probe wrote a brief with `foreign official-footer ignored comments: 1` and a final review line `Included 1 foreign official CURe footer comment ... foreign findings were carried forward.` Calling `audit_review_report_after_review(..., governor_mode="strict", auditor=lambda ... awareness=demonstrated ...)` returned `record.status=success` and `warnings=[]`.

      </details>
    - A19 mandatory PR18/PR22 replay proof is still too exact and does not directly prove corpus exclusion in the replay path. Sources: `tests/_subsequent_review_unit_runtime_packaging_unittest.py:422`, `tests/_subsequent_review_unit_runtime_packaging_unittest.py:436`, `tests/_subsequent_review_unit_runtime_packaging_unittest.py:460`, `tests/_subsequent_review_unit_runtime_packaging_unittest.py:508`, `tests/_subsequent_review_unit_runtime_packaging_unittest.py:516`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:164`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:341`

      <details open>
      <summary><b>Medium</b> severity · <b>High</b> likelihood</summary>

      **Why:** The story asks for mandatory PR18/PR22-style replay coverage generalized beyond exact IDs and proving no foreign PR22 findings reach corpus, extraction, source, disposition, final output, or verifier fan-out. The main replay fixture is hard-coded to PR18/PR22/comment `4707013049` and asserts downstream `prior_findings`, `source_verification`, `disposition`, final text, and fan-out, but it does not inspect `prior_review_corpus.json` in that replay. Separate prior-corpus tests cover exact PR18/PR22 and event-head cases, but they do not close the stated end-to-end replay/matrix claim.

      **Assumptions / Preconditions:** The OpenSpec wording remains as-is: mandatory replay should prove `decision → prior corpus → extraction/source/disposition/package/governor` and generalized mismatched PR/session/head/footer-SHA or event-head invariants.

      **Downgrade Factors:** If the team accepts exact PR18/PR22 fixture coverage plus separate prior-corpus unit tests as sufficient, narrow `story.md`/`tasks.md` to that proof boundary instead of claiming generalized replay.

      **Code Trail:** `test_pr18_pr22_foreign_footer_replay_keeps_foreign_findings_out_but_surfaces_reason()` drives intake and checks `prior_findings.json`, `source_verification.json`, `disposition_ledger.json`, package/context/brief, final text, and verifier calls. It never reads `prior_review_corpus.json`; the PR numbers, heads, session ids, comment ids, and finding ids are literal PR18/PR22 values.

      **Reproduction:** `rg -n "prior_review_corpus|4707013049|PR18|PR22|CURE-22" tests/_subsequent_review_unit_runtime_packaging_unittest.py tests/_subsequent_review_unit_prior_corpus_unittest.py` shows the runtime replay’s exact fixture and absence of corpus-read assertions in that path, while corpus assertions live in separate exact unit fixtures.

      </details>
    - Full story approval remains blocked by provisional live-output proof rows. Sources: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:186`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:187`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:189`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/story.md:190`, `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/tasks.md:32`

      <details open>
      <summary><b>High</b> severity · <b>High</b> likelihood</summary>

      **Why:** `/openspec-story-review` approval requires final proof rows. Story 04 still marks A16/A17/A19/A20 as provisional and leaves the fresh PR22 live audit unchecked. This is honest and appropriate, but it means the story cannot be approved or moved done from this local review.

      **Assumptions / Preconditions:** None.

      **Downgrade Factors:** If the story is intentionally split into local-only approval plus a separate PR-stage live-audit gate, update the proof matrix/status policy first so provisional rows no longer block the local review.

      **Code Trail:** The proof matrix records A16/A17/A19/A20 as provisional pending fresh live output/performance proof, and tasks.md keeps the fresh PR22 live review unchecked.

      **Reproduction:** `rg -n "A16 \\| provisional|A17 \\| provisional|A19 \\| provisional|A20 \\| provisional|Run and audit a fresh PR #22" openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/{story.md,tasks.md}` returns the provisional rows and pending live-audit task.

      </details>
  - Debt Friction: none
  - Next action: `/openspec-story-resume cure-subsequent-pr-review story-04-review-runtime-integration-guardrails-memory-trace` to add contradicted-note governor regression/fix and either strengthen or narrow the mandatory replay proof; after local blockers are closed, run/record the pending fresh PR22 live audit before seeking final approval.

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
