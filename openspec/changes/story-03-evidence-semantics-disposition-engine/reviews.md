# Reviews: story-03-evidence-semantics-disposition-engine

> Implementation review artifact migrated from legacy `agent_coordination` during the 2026-06-12 OpenSpec-format rewrite.
> Canonical story contract: `story.md`. Legacy source remains under `/workspaces/cure_workspace/agent_coordination/epics/cure-subsequent-pr-review/`.

## Review Log

- 2026-06-08T05:10:00Z Corrective implementation review — degraded dependency re-check
  - Decision: approve
  - Approval gate: pass
  - Product verdict: approve
  - Technical verdict: approve
  - Status transition: `🟣 IN REVIEW` -> `✅ DONE`
  - Files reviewed: `projects/CURe/cure_subsequent_review/contracts.py`, `control_plane.py`, `source_truth.py`, `discussion_signals.py`, `disposition.py`, `semantic_pipeline.py`, focused Story 03 unit/control-plane tests, public wrapper, Story 03/MASTER coordination docs.
  - Checks run: `python -m pytest tests/_subsequent_review_unit_source_truth_unittest.py tests/_subsequent_review_unit_discussion_signals_unittest.py tests/_subsequent_review_unit_disposition_arbiter_unittest.py -q` ✅ (12 passed, 15 subtests); `python -m pytest tests/test_subsequent_review.py -q` ✅ (67 passed, 28 subtests); `python -m pytest tests/_subsequent_review_functional_control_plane_unittest.py tests/_subsequent_review_integration_pr_flow_unittest.py -q` ✅ (17 passed); `ruff check .` ✅; `mypy` ✅ (20 source files); `git diff --check` ✅; targeted degraded-partial-row probe ✅ verified degraded source rows block `confirm_resolved`, degraded trusted duplicate rows block `suppress_duplicate`, degraded trusted scope rows block `move_out_of_scope`, and all emit `degraded_findings` with no `action`.
  - Risk lenses reviewed: degraded upstream dependency semantics with partial rows, source-vs-discussion separation, exact `trusted|untrusted` evidence policy, five-action vocabulary, absence of `ask_human`/`escalate`, `degraded_findings` action absence, disabled/degraded module propagation, final prompt/report/runtime-memory/guardrail non-scope, untracked SVG preservation.
  - Key findings:
    - [approve] Corrective blocker is fixed. `arbitrate_dispositions()` now treats any degraded source or discussion ledger as a blocking upstream dependency regardless of partial rows, returning a degraded disposition ledger with per-group `degraded_findings` and no disposition actions.
    - [approve] Regression coverage now includes degraded source ledgers with rows and degraded trusted discussion ledgers with rows. The manual probe additionally covered trusted out-of-scope rows so no degraded partial row can emit `confirm_resolved`, `suppress_duplicate`, or `move_out_of_scope`.
    - [approve] Semantic contract invariants hold: `EvidencePolicy` remains exactly `trusted|untrusted`; `DispositionAction` remains exactly `confirm_resolved`, `reword_partial`, `suppress_duplicate`, `move_out_of_scope`, `re_report`; `DegradedFinding.to_json()` has no `action` key; no `ask_human` or `escalate_or_keep_visible` action path exists in product semantic code.
  - Non-findings: no final prompt/report/runtime-memory/guardrail surfaces were added; conservative default verifier still degrades as `source_unknown`/`verifier_provider_not_configured`; existing untracked `projects/CURe/docs/examples/subsequent-pr-run-flow.svg` remains untracked/preserved.
  - Debt Friction: none.

- 2026-06-08T00:00:00Z Implementation review — risk-lens pass
  - Decision: request_changes
  - Approval gate: fail
  - Product verdict: request_changes
  - Technical verdict: request_changes
  - Status transition: unchanged: `🟣 IN REVIEW` -> `🟣 IN REVIEW`
  - Files reviewed: `projects/CURe/cure_subsequent_review/contracts.py`, `control_plane.py`, `source_truth.py`, `discussion_signals.py`, `disposition.py`, `semantic_pipeline.py`, focused Story 03 unit/control-plane tests, `tests/test_subsequent_review.py`, Story 03/MASTER coordination docs.
  - Checks run: `python -m pytest tests/_subsequent_review_unit_source_truth_unittest.py tests/_subsequent_review_unit_discussion_signals_unittest.py tests/_subsequent_review_unit_disposition_arbiter_unittest.py -q` ✅ (10 passed, 15 subtests); `python -m pytest tests/test_subsequent_review.py -q` ✅ (65 passed, 28 subtests); `python -m pytest tests/_subsequent_review_functional_control_plane_unittest.py tests/_subsequent_review_integration_pr_flow_unittest.py -q` ✅ (17 passed); `git diff --check` ✅; targeted degraded-discussion runtime probe ❌ reproduced a contract violation.
  - Risk lenses reviewed: source-vs-discussion separation, conservative default verifier degradation, exact `trusted|untrusted` and five-action vocabulary, no hidden `ask_human`/`escalate`, disabled/degraded dependency behavior, final prompt/report/runtime-memory/guardrail non-scope, untracked SVG preservation.
  - Key finding:
    - [request_changes] `arbitrate_dispositions()` only blocks a degraded discussion ledger when it has zero rows; a degraded ledger with a linked trusted duplicate/out-of-scope row can still emit `suppress_duplicate`/`move_out_of_scope`. Story 03 Grilling Session and Acceptance A7 require degraded/missing dependencies to block conservative downstream behavior and place affected findings in `degraded_findings`, with no action. Reproduction: construct `DiscussionSignalLedger(status=DEGRADED, status_reasons=("discussion_incomplete",), rows=(trusted duplicate row linked to G-0001,))` plus `SourceState.STILL_OPEN`; `arbitrate_dispositions()` returns status `success` and action `suppress_duplicate`, not a degraded finding. Source: `projects/CURe/cure_subsequent_review/disposition.py:55-63` checks `status is DEGRADED and not rows`, then `_action_for()` trusts rows at `disposition.py:37-45`.
  - Non-findings: `EvidencePolicy` remains exactly `trusted|untrusted`; `DispositionAction` remains exactly five values with no `ask_human`/`escalate_or_keep_visible`; default source verifier conservatively returns `source_unknown`/`verifier_provider_not_configured`; `degraded_findings` schema has no `action`; no final prompt/report/runtime-memory/guardrail surfaces were added; existing untracked `projects/CURe/docs/examples/subsequent-pr-run-flow.svg` remains untracked/preserved.
  - Debt Friction: add focused regression proof for degraded source/discussion ledgers that include partial rows; current tests only cover degraded source with zero rows and do not cover degraded discussion with rows.


## Live-audit remap review note

- 2026-06-14T10:46:40Z Provenance repair review note: PR #22 live-audit feedback FB-032 and the source-truth side of FB-035 should be reviewed against Story 03 evidence-semantics invariants, not as an active Story 05. The change is documentation/provenance-only; implementation evidence remains in PR #22 commits `f96e7ad` and `ee7410a`.
