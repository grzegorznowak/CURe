# Tasks: story-04-review-runtime-integration-guardrails-memory-trace

## Setup & Prerequisites
- [x] Confirm initiative context, story prerequisites, and relevant legacy coordination source.
- [x] Preserve legacy coordination history in `progress.md` / `reviews.md` sidecars.

## Core Implementation
- [x] Implement the baseline Story 04 behavior proven before the A16 human-output model was reopened.
- [x] Implement the newly modeled A16 human-friendly final-output contract from `story.md`.
- [x] Maintain backward compatibility and initiative-level constraints.

## Verification & Proof
- [x] Run focused verification commands for the previously implemented Story 04 baseline.
- [x] Run `ruff`, `mypy`, and relevant integration/regression checks for the previously implemented Story 04 baseline.
- [x] Replace/audit the reader-facing DA disposition map with a human-readable prior-review issue summary: issue clusters first, statuses/reasons second, DA IDs optional/internal only.
- [x] Add prompt/report-governor regressions for cluster-first output, complete internal DA coverage, and raw-DA-list-only negative output.
- [x] Rerun/audit live PR #22 review output and confirm `DA-0006` is no longer `carried-forward/re_report` before marking Story 04 done. Latest audit: sandbox `grzegorznowak-cure-pr22-20260613-080828-d739`, head `372b4a753099c4b6e077d98551da51039222a16b`, `DA-0006=out-of-scope` / `move_out_of_scope`.
- [x] Ingest latest live-audit REQUEST CHANGES findings into follow-up planning artifacts. Synthetic Story 05 initially captured `### Internal DA coverage` consumer shape and runtime hardening points FB-030 through FB-038.
- [x] Remap synthetic Story 05 hardening back into existing Stories 01/03/04 after operator provenance correction; Story 04 owns FB-030, FB-031, FB-034, runtime-FB-035, FB-036, and FB-038.

## Integration & Cleanup
- [x] Update OpenSpec story/progress/review artifacts with final local state.
- [x] Update `story.md`, `progress.md`, and initiative tracker with the remap status. Story 04's previous `DA-0006` live gate is satisfied, but PR #22 remains request-changes overall until a fresh live audit verifies the remapped runtime hardening.


## Live-audit remap tasks

- [x] Record Story 04 ownership of FB-030, FB-031, FB-034, runtime-FB-035, FB-036, and FB-038.
- [x] Cross-reference Story 01 support for FB-031/FB-034 identity inputs and Story 03 support for FB-035 source-truth invariants.
- [x] Keep Story 04 status `🔵 IN PR`; fresh PR #22 live audit remains pending after remap.
- [ ] Run and audit a fresh PR #22 live review at head `ee7410aeedad7e5df92caec90a89ecc28ff89de6` or later, confirming FB-030/031/034/runtime-FB-035/036/038 are closed or explicitly refreshed.
