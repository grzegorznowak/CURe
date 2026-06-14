# Proposal: story-05-subsequent-review-runtime-hardening-after-live-audit

## Goal / Context

Harden CURe subsequent-review runtime after the latest PR #22 live audit. The immediate user-visible goal is to keep final reviews human-first: prior-review state should be understandable through issue titles/statuses/reasons, while raw DA coverage remains audit/provenance output rather than prominent consumer-facing content. The story also captures the latest REQUEST CHANGES findings around memory/linker identity, discussion authority, artifact path containment, verifier citation constraints, concise prior-review parsing, and multipass abort guardrails.

## Story Candidates

Single follow-up story — this change is the feedback-derived hardening scope after Story 04's live audit. It is intentionally separate from Story 04 because the initiative says new feedback-derived changes should be planned as fresh OpenSpec stories rather than re-expanding completed contracts.

## Decisions & Constraints

- Keep complete internal DA coverage as an audit/governor/provenance requirement.
- Remove or demote `### Internal DA coverage` from the ordinary visible `review.md` body; use artifact, metadata, appendix, hidden/collapsible block, or explicitly audit-only surface instead.
- Preserve Story 04 successes: strict multipass step schemas, A17 warn-only governor behavior, A19/DA-0006 footer-policy disposition, and the narrow FB-028/FB-029 regressions.
- Memory and linker caches are optimizations only; if stable identity cannot be proven, re-run verifier/linker work rather than replaying cached truth.
- Discussion body text cannot grant authority; trust comes from authenticated author/role metadata or configured policy.
- Source truth remains separate from discussion and memory truth.

## External Resources

- Canonical PR: https://github.com/grzegorznowak/CURe/pull/22
- Live audit sandbox: `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260613-080828-d739`
- Prior story: `openspec/changes/story-04-review-runtime-integration-guardrails-memory-trace/`
- Feedback records: FB-030 through FB-038 in `openspec/initiatives/cure-subsequent-pr-review/feedback-log.md`


## Superseded proposal note

This proposal is superseded. The live-audit feedback remains accepted, but it amends existing Stories 01, 03, and 04 instead of creating a new authoritative Story 05. The Story 05 workspace stays only as an audit trail for how FB-030 through FB-038 were first ingested.
