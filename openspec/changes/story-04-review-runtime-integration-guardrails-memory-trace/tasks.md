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
- [ ] Rerun/audit live PR #22 review output and confirm `DA-0006` is no longer `carried-forward/re_report` before marking Story 04 done.

## Integration & Cleanup
- [x] Update OpenSpec story/progress/review artifacts with final local state.
- [ ] After the live PR #22 gate passes, update `story.md`, `progress.md`, and initiative tracker from `🔵 IN PR` to `✅ DONE`.
