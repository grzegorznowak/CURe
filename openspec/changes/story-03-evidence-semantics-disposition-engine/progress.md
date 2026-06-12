# Progress: story-03-evidence-semantics-disposition-engine

> Runtime/progress artifact migrated from legacy `agent_coordination` during the 2026-06-12 OpenSpec-format rewrite.
> Canonical story contract: `story.md`. Legacy source remains under `/workspaces/cure_workspace/agent_coordination/epics/cure-subsequent-pr-review/`.

## Current Claim
- Claimed at: 2026-06-08T04:23:38Z
- Claimed by: pi child agent (epic-story-claim)
- Scope: Implement Story 03 Evidence Semantics and Disposition Engine only.
- Primary write surfaces: `projects/CURe/cure_subsequent_review/`, `projects/CURe/tests/_subsequent_review_*`, `projects/CURe/tests/test_subsequent_review.py`, coordination story/master files.

### Legacy Scaffold Notes
> Story scaffolded directly by `/epic-story-plan` after Story 01/02 delivered subsequent-review intake and auto-mode decision artifacts.

## Progress Timeline
- 2026-06-08T04:34:39Z Addressed implementation-review blocker for degraded partial source/discussion ledgers. Added red-first disposition arbiter regressions proving degraded source rows and degraded trusted discussion rows produce `degraded_findings` with no action, then changed arbiter dependency gating so any degraded upstream source/discussion ledger blocks disposition actions. Verification passed: focused disposition test (red first: 2 failures, then green), focused semantic unit suites (12 passed, 15 subtests), public wrapper `tests/test_subsequent_review.py -q` (67 passed, 28 subtests), functional/control-plane integration suites (17 passed), `ruff check .`, `mypy`, and product `git diff --check`. Status remains in-review for reviewer re-check. Pre-existing untracked `projects/CURe/docs/examples/subsequent-pr-run-flow.svg` preserved.
- 2026-06-08T04:23:38Z Claimed approved Story 03 and implemented semantic contracts, injected source verifier seam, discussion signal resolver, disposition arbiter, data-driven `semantic_pipeline.py`/`MODULE_REGISTRY`, control-plane artifact/manifest integration, and split semantic tests. Verified focused red-first failures then green. Verification passed: `python -m pytest tests/test_subsequent_review.py -q` (65 passed, 28 subtests), focused semantic/control-plane suites, `ruff check .`, `mypy`, and product `git diff --check`. Moved implementation status to in-review. No blockers. Pre-existing untracked `projects/CURe/docs/examples/subsequent-pr-run-flow.svg` preserved.

## Session Handoff
- None recorded.

## PR State
- Not applicable / not recorded in the legacy story.

### Grilling Session — 2026-06-07

Story 03 plan was grilled before implementation. The following decisions refine and supersede portions of the drafted spec where more precision was needed.

#### Source Truth Verifier
- Reuses the existing chunkhound+LLM research pipeline, asking targeted verification questions per prior finding.
- Architecture: injectable `FindingVerifier` callable interface. Production implementation uses a free-text LLM answer followed by a classifier pass to extract `source_state`, `current_evidence`, and `reasoning`.
- The verifier module never reads files directly. It delegates "figure out what the code does" to the injected provider.
- Source-state labels: `resolved_from_source`, `still_open`, `partially_resolved`, `source_unknown`, `not_verifiable`.

#### Discussion Signal Resolver
- Links discussion events to prior findings via LLM-based matching (same injectable-callable pattern as the verifier).
- Authority taxonomy: heuristic from GitHub collaboration roles + comment content. No config file. Unknown or unclassifiable authority → `untrusted`.
- Signal classes include: `developer_claim_fixed`, `resolved_thread_hint`, `by_design`, `addressed_elsewhere`, `duplicate_superseded`, `unresolved_thread_hint`, `pushback`, `authority_conflict`, plus any new classes discovered during implementation.

#### Disposition Arbiter
- Five actions only: `confirm_resolved`, `reword_partial`, `suppress_duplicate`, `move_out_of_scope`, `re_report`.
- `escalate_or_keep_visible` removed. Every source-open finding without a trusted discussion override (duplicate, out-of-scope, elsewhere) becomes `re_report` with discussion provenance attached. The downstream Report Governor decides formatting, severity emphasis, and escalation from the provenance.
- `reword_partial` does NOT produce a reworded title in Story 03. It emits a pointer to the source verifier row that contains the narrowed evidence. The downstream Review Context Packager handles human-readable phrasing.
- Degraded/missing dependencies block the arbiter entirely (arbiter requires both `source_verification` and `discussion_signals` present). Blocked findings go into a separate `degraded_findings` section of the disposition ledger — no `ask_human` pseudo-action.

#### Module dependency model
- Data-driven `MODULE_REGISTRY` dict declares `requires` / `produces` per module. The pipeline runner walks modules in registration order, checks upstream dependencies, and skips modules whose deps are absent, recording `disabled` with missing-dependency reasons.
- Dependency graph:
  - `source_truth_verifier` requires `reconciliation`
  - `discussion_signal_resolver` requires `discussion_artifact`, `corpus`
  - `disposition_arbiter` requires `reconciliation`, `source_verification`, `discussion_signals`

#### Output artifact conventions
- Cross-referencing by stable row IDs across the three artifacts (`source_verification.json`, `discussion_signals.json`, `disposition_ledger.json`). No inlined duplication of evidence.
- No `carry_over` boolean field — derivable from action (`re_report` and `reword_partial` are carry-over, others are not).
- Free-text `provenance.rationale` field on disposition rows for debugging; must be easily accessible.

#### Orchestration
- New `cure_subsequent_review/semantic_pipeline.py` module, called from `run_subsequent_review_intake` in `control_plane.py` with one line when Story 03 modules are enabled.

#### Golden tests
- Parametrized matrix of `(case_id, module, input_key, field, expected_value)` tuples covering the simulation's A/B/C/S matrix. Shared fixtures load once. Each tuple becomes its own named test. Full pipeline integration golden as a secondary proof.

#### Branch strategy
- Story 03 implemented on the existing product branch `cure-subsequent-pr-review/story-01-intake`, expanding PR #22.

## Unresolved Debt Friction
- None current; story status is `✅ DONE`.
