# Proposal: story-03-evidence-semantics-disposition-engine

## Goal / Context
Turn Story 01 subsequent-review ledgers into auditable semantic dispositions before final-report packaging begins. CURe must verify prior findings against current source evidence only, classify PR discussion/scope/authority as a separate signal stream under the existing `trusted|untrusted` evidence policy, and arbitrate explicit actions that later review/report stages can cite without re-deciding whether a prior finding was resolved, duplicated, out of scope, still reportable, partially reworded, or unsafe to suppress.

## Story Candidates
Single story — this change workspace is the full scope. See `story.md` for actors, acceptance, verification, and proof contract.

## Decisions & Constraints
Inherits initiative-level decisions from `../../initiatives/cure-subsequent-pr-review/initiative.md`.

- Story number 03 is used because actual Story 02 became Auto-infer Subsequent Review Mode; this story implements the original roadmap's Evidence Semantics and Disposition Engine as the next delivery slice.
- Evidence policy remains exactly `trusted` and `untrusted`; no third policy or semantic confidence mode is introduced.
- Only Source Truth Verifier may emit source-state labels such as `resolved_from_source`.
- Discussion Signal Resolver may classify scope, authority, retargeting, duplicate/superseded, resolved-thread hints, and claims, but discussion never proves source resolution.
- Disposition actions are limited to `confirm_resolved`, `re_report`, `suppress_duplicate`, `move_out_of_scope`, and `reword_partial`. Every source-open finding without a trusted discussion override becomes `re_report` with provenance. The downstream Report Governor decides formatting and severity emphasis. Degraded findings are listed in a separate `degraded_findings` section, not assigned a pseudo-action.
- Disabled/degraded/missing modules must be visible in manifest/artifacts and force conservative downstream behavior.
- FB-007 final report surfacing is deferred; Story 03 creates the provenance-bearing semantic ledgers that a later packager/report-governor story can surface.
- FB-010 decision-vs-intake discussion evidence reproducibility is deferred; Story 03 consumes persisted intake ledgers and records degraded/missing provenance rather than reusing remote decision fetches.

## External Resources
- Initiative: `../../initiatives/cure-subsequent-pr-review/initiative.md`
- Legacy coordination source: `/workspaces/cure_workspace/agent_coordination/epics/cure-subsequent-pr-review/story-03-evidence-semantics-disposition-engine.md`
