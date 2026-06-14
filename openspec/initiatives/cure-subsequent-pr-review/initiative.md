# CURe Subsequent PR Review Workflow

source_of_truth: internal

## Goal / Context

CURe subsequent PR review makes a fresh `cure pr <PR_URL>` run prior-review-aware without requiring the operator to manually identify that a PR is subsequent. The workflow fetches and normalizes prior CURe findings plus PR discussion, verifies old findings against current source, interprets discussion/scope signals separately from source truth, and arbitrates final-report decisions with auditable provenance. Done means operators receive explicit confirmations, re-reports, duplicate/out-of-scope suppressions, degraded-mode warnings, human-readable prior-review issue history in final `review.md`, and persisted `work/subsequent/` ledgers that future runs can reuse. Design landmarks are `docs/examples/subsequent-review-simulation.md`, simulated PR `https://github.com/grzegorznowak/CURe/pull/21`, and `docs/examples/subsequent-pr-run-flow.svg`; implementation stories should cite which landmark stages they satisfy, but SVG polish is not implementation scope. Current delivery state: Stories 01-03 are `✅ DONE`; Story 04 is `🔵 IN PR` on PR #22 after a 2026-06-13 live audit closed the strict multipass `### Step Result:` regression, A17 warn-only governor path, and A19/`DA-0006` footer-policy disposition, but the same audit returned REQUEST CHANGES and seeded Story 05 as a fresh hardening plan draft for consumer-facing DA coverage shape plus runtime identity/trust/source-boundary findings.

### Risks / unknowns

- GitHub discussion completeness may require both REST endpoints and GraphQL review-thread state; pagination gaps and unavailable thread state must be modeled explicitly.
- Stable finding IDs/fingerprints are sensitive to prompt/template changes and historical artifact shape changes.
- Authority classification for product/security/maintainer comments is policy-sensitive and may require repo-specific configuration over time.
- Fresh `cure pr` behavior and older `resume` / follow-up / multipass paths must stay understandable while sharing subsequent-review artifacts.
- Prompt-template changes must stay covered by grounding/proof contracts so source-grounding validation does not silently become a no-op.
- Local deterministic fixtures use simulated PR `#9999`; live PR #21 is an optional/manual landmark and must not be required for routine tests.

## Story Candidates

The initiative is decomposed into the current change workspaces under `openspec/changes/`. Runtime progress/review histories live in each change workspace as `progress.md` and `reviews.md`.

| Step | Plan | Status | Deliverable | Depends | Change workspace |
|---:|---|---|---|---|---|
| 01 | 🟢 PLAN APPROVED | ✅ DONE | Subsequent Review Intake and Prior Finding Ledger | none | `openspec/changes/story-01-subsequent-review-intake/` |
| 02 | 🟢 PLAN APPROVED | ✅ DONE | Auto-infer Subsequent Review Mode | 01 | `openspec/changes/story-02-auto-infer-subsequent-review-mode/` |
| 03 | 🟢 PLAN APPROVED | ✅ DONE | Evidence Semantics and Disposition Engine | 01, 02 | `openspec/changes/story-03-evidence-semantics-disposition-engine/` |
| 04 | 🟢 PLAN APPROVED | 🔵 IN PR | Review Runtime Integration, Guardrails, Memory, and Landmark Trace | 01, 02, 03 | `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/` |
| 05 | 🟢 PLAN APPROVED | 🔄 IN PROGRESS | Subsequent Review Runtime Hardening After Live Audit | 01, 02, 03, 04 | `openspec/changes/story-05-subsequent-review-runtime-hardening-after-live-audit/` |

Functional module ownership:

- Story 01 owns modules 1-5: Subsequent Review Control Plane, PR History Collector, Prior Review Corpus Builder, Prior Finding Extractor, and Finding Reconciler.
- Story 02 owns the command decision surface: default `auto`, explicit `--no-subsequent-review` disabled state, durable decision artifacts, and official-footer marker policy intake boundaries.
- Story 03 owns modules 6-8: Source Truth Verifier, Discussion Signal Resolver, and Disposition Arbiter.
- Story 04 owns modules 9-12 plus test-only module 13: Review Context Packager, Report Governor, Review Memory Store, Degraded Runtime Manager, and Landmark Trace Runner.
- Story 05 owns post-live-audit hardening of Story 04 surfaces: consumer-facing DA coverage shape, stronger memory/linker identity, discussion authority boundaries, source/path/citation constraints, concise prior-review parsing, and multipass abort guardrails.

Legacy feedback-derived story candidates and absorption history are preserved in `feedback-log.md`. Previously open candidates FB-007 (final-report provenance surfacing) and FB-010 (decision/intake discussion evidence reuse) are represented in Story 04 scope; any new feedback-derived change should be planned as a fresh OpenSpec story rather than re-expanding completed contracts.

## Decisions & Constraints

- Keep source truth separate from discussion/scope truth: only current source evidence can set source-state labels such as `resolved_from_source`.
- PR comments, review threads, and human confirmation can retarget checks or affect report action/scope with provenance, but comments alone never prove source resolution.
- Evidence policy has exactly two modes, `trusted` and `untrusted`; do not introduce a third policy mode or standalone policy stage/card/toggle.
- Policy influences scope/reporting/arbitration thresholds, not source truth. Incomplete data, unknown authority, pagination gaps, or API/thread failures must fall back to conservative `untrusted`, ask/exit, or continue-with-caveat behavior.
- Existing `--if-reviewed prompt|new|list|latest` behavior must remain understandable and backwards compatible while subsequent-review behavior is introduced.
- Prefer DDD-style small modules/services, red-first targeted tests, and project checks (`ruff`, `mypy`, relevant unit tests) for implementation stories.
- Deterministic tests should use local synthetic fixtures/golden data; live PR #21 can inspire optional/manual integration coverage but must not be required for unit success.
- Do not polish or redesign `docs/examples/subsequent-pr-run-flow.svg` as part of this initiative unless explicitly requested.
- Do not build full external-ticket tracker integration; external references may be recorded as provenance/scope signals.
- Do not silently suppress source-open or high-severity findings based on weak discussion, resolved-thread hints, or developer claims.
- Do not make source verification a prompt-only convention without persisted auditable artifacts and validation gates.
- Story 04 context packaging is audit/debug/sanitization input; it is not mechanically injected final-report text.
- Final `review.md` should be self-contained for humans: issue titles, statuses, and reasons are the reader-facing surface; DA IDs and artifact paths are internal provenance, not primary labels. Top-level `### Internal DA coverage` row lists should be removed from ordinary consumer-facing review body or clearly demoted to an audit-only appendix/artifact/collapsible surface.

## External Resources

- Simulated/landmark PR: https://github.com/grzegorznowak/CURe/pull/21
- Canonical implementation PR: https://github.com/grzegorznowak/CURe/pull/22
- PR #22 feedback reference: https://github.com/grzegorznowak/CURe/pull/22#issuecomment-4621524265
- Local design landmark: `docs/examples/subsequent-review-simulation.md`
- Local stage-map landmark: `docs/examples/subsequent-pr-run-flow.svg`
- Legacy coordination source: `/workspaces/cure_workspace/agent_coordination/epics/cure-subsequent-pr-review/`
