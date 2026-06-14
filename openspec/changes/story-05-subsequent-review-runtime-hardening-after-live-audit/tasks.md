# Tasks: story-05-subsequent-review-runtime-hardening-after-live-audit

## Setup & Prerequisites
- [x] Ingest latest PR #22 live-audit findings from sandbox `grzegorznowak-cure-pr22-20260613-080828-d739`.
- [x] Record decision that `### Internal DA coverage` should be removed/demoted from ordinary consumer-facing `review.md` while preserving audit coverage.
- [x] Run fresh OpenSpec plan review for Story 05 before implementation.

## Core Implementation
- [x] A1: Redesign prompt/report-governor output shape so DA coverage is audit/provenance-only and not prominent ordinary review body content.
- [x] A2: Strengthen source-verification memory replay identity beyond ordinal `group_id` plus display `finding_ids`.
- [x] A3: Prevent untrusted discussion body text from granting trusted product/security/maintainer authority.
- [x] A4: Enforce session-boundary containment for zip/source artifact paths from historical metadata.
- [x] A5: Validate cached discussion linker group IDs against current reconciliation group identity before replay.
- [x] A6: Constrain LLM verifier citations to inspected source contexts before allowing `resolved_from_source`.
- [x] A7: Route discussion linker LLM calls through prepared runtime policy/config/add-dir environment.
- [x] A8: Preserve prior-finding identity for supported concise generated reviews.
- [x] A9: Ensure multipass planner abort paths cannot bypass prior-review final-output/governor guardrails.

## Verification & Proof
- [x] Add red-first focused tests for A1-A9 before implementation.
- [x] Run focused suites listed in `story.md` Verification Commands.
- [x] Run `python -m pytest tests/test_subsequent_review.py -q`.
- [x] Run `ruff check .`, `git diff --check`, and `mypy`.
- [ ] Run and audit a fresh PR #22 live review after implementation.

## Integration & Cleanup
- [x] Update `progress.md`, `reviews.md`, and the initiative tracker after plan review.
- [x] Update PR #22 body/status with Story 05 scope if implementation proceeds on the same PR branch.
- [ ] Confirm Story 04 successful gates remain non-regressed: strict multipass schema, A17 warn-only governor, A19/DA-0006, and FB-028 malformed-linker degradation.
