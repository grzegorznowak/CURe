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
- [x] Audit latest PR #18 benchmark sandbox `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr18-20260615-095138-9664`: runner used label fix `e130543` against PR #18 head `c3f81e8`; prior history appears first, carried-forward reader-facing findings get the follow-up label, raw `DA-*` IDs remain audit-only, duplicate lineage dedupes coherently, empty successful discussion signals no longer fail strict governor, and module statuses agree across runtime artifacts.

## Integration & Cleanup
- [x] Update OpenSpec story/progress/review artifacts with final local state.
- [x] Update `story.md`, `progress.md`, and initiative tracker with the remap status. Story 04's previous `DA-0006` live gate is satisfied, but PR #22 remains request-changes overall until a fresh live audit verifies the remapped runtime hardening.


## Live-audit remap tasks

- [x] Record Story 04 ownership of FB-030, FB-031, FB-034, runtime-FB-035, FB-036, and FB-038.
- [x] Cross-reference Story 01 support for FB-031/FB-034 identity inputs and Story 03 support for FB-035 source-truth invariants.
- [x] Keep Story 04 status `🔵 IN PR`; fresh PR #22 live audit remains pending after remap.
- [ ] Run and audit a fresh PR #22 live review at head `e305f826f3c0ece63be708f7df4b4f54c38b7658` or later, confirming FB-030/031/034/runtime-FB-035/036/038 are closed or explicitly refreshed.
- [ ] A16 final-output polish: preserve the governor-supplied plain-English reason as the third element in leading `### Prior Review Issue History` bullets. Latest PR #18 benchmark warned that this reason can still be omitted there even after the label fix; treat it as reader-facing output polish rather than a label/provenance failure.
- [x] A19 footer-provenance hardening: reject remote CURe comments/reviews whose official footer or pull-review event `reviewed_head`/`commit_id` belongs to a different PR/session/head than the current review target/run; exclude them from prior corpus, prior-finding extraction, source verification, disposition, and final carry-forward surfaces; record a visible ignored-comment audit note with a plain-English reason (for example, PR #18 comment `4707013049` carrying a PR #22 footer/session/head, or a pull-review event whose footer claims the current head but whose GitHub event head is foreign). Local fixture proof added 2026-06-15.

## A20 / FB-039..FB-042 source-verification cache hardening tasks

- [x] FB-039 intake-time memory persistence: add a failing runtime-memory/control-plane test where enabled intake writes `source_verification.json` and `disposition_ledger.json`, then review publication fails or remains running before final `review.md`; implement an intake-completion memory persist point so the next same-head run finds current memory and avoids repeating verifier work for eligible rows.
- [x] FB-040 terminal non-reportable replay matrix: cover `resolved_from_source`, duplicate, out-of-scope, dropped/not-relevant, still-open, source-unknown, and not-verifiable outcomes; replay only safe terminal non-reportable categories whose stable identity, source-reference, discussion/disposition fingerprints, and policy provenance match; emit `not_source_proof: true` where replay is non-source-proof and never emit `resolved_from_source` unless the cached source row was source-resolved. Local proof now covers the literal matrix: `resolved_from_source` source rows replay; duplicate, out-of-scope, and dropped/not-relevant rows replay only through safe non-reportable dispositions; still-open reportable, source-unknown, and not-verifiable rows miss and invoke fresh verifier logic without source-proof escalation; ordinal-only identity remains insufficient.
- [x] FB-041 stable identity miss/regression coverage: add reordered-group, repeated-display-ID, changed-source-reference, and ordinal-only-match cases proving `group_id` alone cannot hit the source-verification cache; store/look up stable finding identity/fingerprint/source-reference identity plus current head and record a miss when identity drifts.
- [x] FB-042 cache telemetry and verifier fan-out observability: persist per-group cache `hit|miss|bypass` reason codes in source-verification/review-memory artifacts; add verifier call count/timing to manifest/log observability; add a same-head rerun guardrail proving already-cached claims do not invoke the verifier for every historical group.
- [x] Before returning to story review, run TAP-21 focused suites (`tests/_subsequent_review_unit_memory_store_unittest.py`, `tests/_subsequent_review_unit_runtime_memory_unittest.py`, `tests/_subsequent_review_unit_semantic_pipeline_unittest.py`, `tests/_subsequent_review_integration_pr_flow_unittest.py`), the public subsequent-review wrapper, relevant config/prompt regressions, `ruff check .`, `git diff --check`, and `mypy`.
