# Design: story-03-evidence-semantics-disposition-engine

## Architecture Overview
See `story.md` for the canonical story contract. Critical files/surfaces for this change:

| File | Role |
|---|---|
| `projects/CURe/cure_subsequent_review/contracts.py` | Extend typed contracts with source verification rows, discussion signal rows, disposition action rows, schema serialization, and constrained enums. |
| `projects/CURe/cure_subsequent_review/control_plane.py` | Call the Story 03 semantic pipeline after reconciliation, update manifest statuses, and preserve disabled/degraded behavior. |
| `projects/CURe/cure_subsequent_review/semantic_pipeline.py` (new) | Data-driven `MODULE_REGISTRY` orchestrator for Source Truth Verifier, Discussion Signal Resolver, and Disposition Arbiter; owns dependency checks and artifact writes. |
| `projects/CURe/cure_subsequent_review/prior_findings.py` | Source-evidence input shape consumed by Source Truth Verifier; existing invalid/prose evidence protections must remain. |
| `projects/CURe/cure_subsequent_review/finding_identity.py` | Reconciliation/group/supersedes input for duplicate suppression and canonical disposition decisions. |
| `projects/CURe/cure_subsequent_review/github_history.py` | Discussion event/thread metadata input consumed by Discussion Signal Resolver; thread status remains metadata only. |
| `projects/CURe/cure_subsequent_review/source_truth.py` (new) | Focused Source Truth Verifier module; delegates current-source assessment to injected `FindingVerifier` provider and never treats discussion as proof. |
| `projects/CURe/cure_subsequent_review/discussion_signals.py` (new) | Focused Discussion Signal Resolver module. |
| `projects/CURe/cure_subsequent_review/disposition.py` (new) | Focused Disposition Arbiter module. |
| `projects/CURe/tests/_subsequent_review_unit_source_truth_unittest.py` (new) | Unit tests for source states, source-only proof, and source input boundary safety. |
| `projects/CURe/tests/_subsequent_review_unit_discussion_signals_unittest.py` (new) | Unit tests for discussion linking, authority/scope classification, evidence-policy values, and degraded discussion. |
| `projects/CURe/tests/_subsequent_review_unit_disposition_arbiter_unittest.py` (new) | Unit tests for action selection, provenance, source/discussion conflicts, and conservative degraded handling. |
| `projects/CURe/tests/_subsequent_review_functional_control_plane_unittest.py` | Extend artifact/manifest/control-plane tests for Story 03 modules and disabled/degraded branches. |
| `projects/CURe/tests/_subsequent_review_integration_pr_flow_unittest.py` | Extend runtime routing proof so enabled subsequent-review runs produce semantic ledgers and disabled/historical exits do not. |
| `projects/CURe/tests/fixtures/subsequent_review/` | Existing simulation fixtures/goldens; add Story 03 golden expectations derived from the simulation landmark. |

## Technical Decisions
- Story number 03 is used because actual Story 02 became Auto-infer Subsequent Review Mode; this story implements the original roadmap's Evidence Semantics and Disposition Engine as the next delivery slice.
- Evidence policy remains exactly `trusted` and `untrusted`; no third policy or semantic confidence mode is introduced.
- Only Source Truth Verifier may emit source-state labels such as `resolved_from_source`.
- Discussion Signal Resolver may classify scope, authority, retargeting, duplicate/superseded, resolved-thread hints, and claims, but discussion never proves source resolution.
- Disposition actions are limited to `confirm_resolved`, `re_report`, `suppress_duplicate`, `move_out_of_scope`, and `reword_partial`. Every source-open finding without a trusted discussion override becomes `re_report` with provenance. The downstream Report Governor decides formatting and severity emphasis. Degraded findings are listed in a separate `degraded_findings` section, not assigned a pseudo-action.
- Disabled/degraded/missing modules must be visible in manifest/artifacts and force conservative downstream behavior.
- FB-007 final report surfacing is deferred; Story 03 creates the provenance-bearing semantic ledgers that a later packager/report-governor story can surface.
- FB-010 decision-vs-intake discussion evidence reproducibility is deferred; Story 03 consumes persisted intake ledgers and records degraded/missing provenance rather than reusing remote decision fetches.

## Implementation Strategy
Recommended red-first sequence:

1. Add contract tests for allowed source-state/action values, schema-versioned JSON, module manifest records, and evidence-policy separation.
2. Implement Source Truth Verifier behind an injectable `FindingVerifier` callable so unit tests can prove source-only states from provider-returned current-source evidence without live GitHub or prompt execution.
3. Implement Discussion Signal Resolver with the same injectable-callable pattern plus heuristic authority defaults; unknown or incomplete authority must be untrusted/degraded rather than accepted as suppression authority.
4. Implement Disposition Arbiter as pure logic over typed ledgers and module statuses, with exhaustive action tests before control-plane integration.
5. Add `cure_subsequent_review/semantic_pipeline.py` as the delegated `MODULE_REGISTRY` orchestrator and call it from `run_subsequent_review_intake` after reconciliation when enabled and module overrides permit.
6. Add simulation-derived golden coverage for the expected A/B/C/S landmark outcomes without requiring live PR #21.
7. Run focused semantic tests, existing subsequent-review wrapper, adjacent prior-ledger tests, `ruff`, and `mypy`.

Keep source/discussion/arbiter logic in small `cure_subsequent_review` modules. If the injected verifier/provider contract cannot produce auditable current-source states at this story size, implementation must stop and return to planning with a narrowed provider contract rather than substituting comments or prompt conventions for source truth.

## Risks & Mitigations
- `projects/CURe/cure_subsequent_review/contracts.py:1-5` explicitly says Story 01 defines all module contracts but has no source-state or disposition labels yet.
- `projects/CURe/cure_subsequent_review/contracts.py:15-43` already defines `EvidencePolicy`, `ModuleStatus`, and enum entries for `SOURCE_TRUTH_VERIFIER`, `DISCUSSION_SIGNAL_RESOLVER`, and `DISPOSITION_ARBITER`.
- `projects/CURe/cure_subsequent_review/control_plane.py:24-43` currently limits `SubsequentReviewConfig.module_enabled()` to Story 01 modules, so Story 03 must deliberately make modules 6-8 runnable/toggleable.
- `projects/CURe/cure_subsequent_review/control_plane.py:99-189` writes Story 01 artifacts and manifest; Story 03 should extend this focused control-plane package rather than expanding `cure.py`.
- `projects/CURe/cure_subsequent_review/github_history.py:149-226` normalizes PR discussion events; thread state is available as metadata and must remain a hint, not source truth.
- `projects/CURe/cure_subsequent_review/prior_findings.py:56-128` parses prior findings and rejects non-source evidence; Story 03 should preserve that boundary when verifying source truth.
- `projects/CURe/cure_subsequent_review/finding_identity.py:95-223` owns reconciliation groups, supersedes edges, and ambiguity; the arbiter should consume this ledger instead of rematching findings from scratch.
- `projects/CURe/docs/examples/subsequent-review-simulation.md:133-154` names the intended source-verification, comment-resolution, and disposition artifacts; this story chooses JSON machine ledgers under the existing `work/subsequent/` directory while leaving human-readable final summaries to a later story.
- Existing public test entrypoint `projects/CURe/tests/test_subsequent_review.py:1-13` imports split private subsequent-review suites; new Story 03 tests should join that wrapper so focused and public commands stay aligned.


## Live-audit remap design addendum

- Discussion authority (FB-032) remains metadata/config-driven. Body text may explain a claim but cannot authenticate product/security/maintainer authority.
- Source truth (FB-035) remains inspected-current-source-driven. LLM citations are candidate references only until constrained to repo-local inspected context; unsupported citations must degrade or remain unverifiable.
