# Proposal: story-02-auto-infer-subsequent-review-mode

## Goal / Context
Make fresh `cure pr <PR_URL>` runs decide subsequent-review intake automatically instead of requiring the operator to know whether the PR is subsequent. The command surface has exactly two states: default `auto`, which infers whether Story 01 intake should run from PR/session evidence and records the decision, and explicit `disabled`, which opts out and never runs intake. No force-enable state is introduced.

## Story Candidates
Single story — this change workspace is the full scope. See `story.md` for actors, acceptance, verification, and proof contract.

## Decisions & Constraints
Inherits initiative-level decisions from `../../initiatives/cure-subsequent-pr-review/initiative.md`.

- Subsequent-review command mode has exactly two states: `auto` and `disabled`.
- Omitted flag means `auto`.
- `--no-subsequent-review` is the only explicit command-mode override and means disabled.
- No force-enable state is introduced; `--subsequent-review` must not silently force intake.
- Auto-disabled and explicit-disabled new-sandbox runs must write explicit decision metadata/artifact.
- Auto does not alter the evidence policy model; evidence policy remains exactly `trusted` or `untrusted`.
- True remote probe unavailability, exceptions, or enabling fetch/pagination failures are conservative degraded-enabled; metadata-only `discussion_incomplete` / `thread_state_unavailable` with zero official-footer markers are non-enabling degraded reasons that may auto-disable with `no_prior_review_signals` while remaining visible.
- Official CURe review footer blocks (`<!-- CURE_REVIEW_FOOTER_START -->` ... `<!-- CURE_REVIEW_FOOTER_END -->`) in GitHub issue comments or pull review bodies are sufficient positive prior-CURe-review evidence for auto-decision and prior-corpus ingestion regardless of author/login.
- Generic/untrusted GitHub discussion, CURe-looking body text without the official footer, spoofed or allowlisted author/login text without the footer, review-comment line comments, and thread-state metadata/missing metadata are not positive prior-CURe-review evidence.
- Post-session-init decision/intake failures must leave `meta.json.status = "error"`, not `running`.

## External Resources
- Initiative: `../../initiatives/cure-subsequent-pr-review/initiative.md`
- Legacy coordination source: `/workspaces/cure_workspace/agent_coordination/epics/cure-subsequent-pr-review/story-02-auto-infer-subsequent-review-mode.md`
