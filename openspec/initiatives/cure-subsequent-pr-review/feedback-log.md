# Feedback Log: CURe Subsequent PR Review Workflow

> Migrated from legacy `agent_coordination` during the 2026-06-12 OpenSpec-format rewrite. The clean initiative file keeps only current story/decision context; this sidecar preserves the feedback audit trail.

## Feedback-Derived Story Candidates

### FB-001 - Auto-infer subsequent review mode
- Source: manual:2026-06-04T11:34:52Z:1
- Origin: Story 01 local PR #22 run analysis / operator feedback
- Reason: Story 01 implemented an explicit opt-in switch for subsequent-review intake, but the operator should not have to know whether a run is subsequent; CURe can infer that from PR/session state. This changes command-decision behavior for a completed story and should be planned as a follow-up rather than rewriting the done Story 01 contract.
- Proposed story: Make `cure pr <PR_URL>` use a two-state subsequent-review decision surface where default `auto` infers whether intake should run from PR/session evidence, and explicit `disabled` opts out.
- Acceptance sketch:
  - Default `cure pr <PR_URL>` records `subsequent_review.mode = "auto"` and an explicit enabled/disabled inference decision with reasons.
  - `--no-subsequent-review` records `mode = "disabled"`, `enabled = false`, and never runs intake.
  - No force-enable CLI state is introduced; later stories consume the recorded auto/disabled decision consistently.
- Recommended next command: `/epic-story-plan EPIC="cure-subsequent-pr-review"` and reference `FB-001` during the interview
- Planning outcome: scaffolded as Story 02 (`story-02-auto-infer-subsequent-review-mode.md`) for plan review.

### FB-007 - Surface subsequent-review intake provenance in final reports
- Source: manual:2026-06-04T13:12:11Z:6
- Origin: PR #22 local run `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260604-122432-f8ac`
- Reason: The final generated `review.md` acknowledged subsequent-review artifacts only generically and did not cite the run's decision, manifest, prior-corpus, degraded GitHub discussion, or prior-finding ledger. Story 01/02 own intake and decision mechanics; final prompt/context packaging and report-governor behavior are explicitly later-story scope.
- Proposed story: Package subsequent-review decision and intake ledgers into review context and require final reports to surface enabled/disabled decisions, prior-finding memory, and degraded intake caveats with citeable provenance.
- Acceptance sketch:
  - Enabled subsequent-review runs expose decision reasons/counts and module degraded statuses to the final review context/report.
  - Final report guardrails prevent prior-ledger findings or degraded intake warnings from disappearing without explicit cited rationale.
- Recommended next command: `/epic-story-plan EPIC="cure-subsequent-pr-review"` and reference `FB-007` during the interview
- Planning outcome: Story 03 creates provenance-bearing semantic ledgers that downstream reports can cite, but final report surfacing/guardrails remain deferred to the later Review Context Packager / Report Governor story.

### FB-010 - Reuse or persist auto-decision PR discussion evidence
- Source: local-review:grzegorznowak-cure-pr22-20260605-161159-7efb
- Origin: PR #22 local review `/home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260605-161159-7efb/review.md`
- Reason: Auto-mode decision can fetch PR discussion to enable intake, then Story 01 intake fetches discussion again and persists only the second result. Remote discussion may change or fail between those calls, so `decision.json` evidence and `work/subsequent/pr_discussion.json` can diverge.
- Proposed story: Make decision/intake discussion evidence reproducible by reusing the decision `DiscussionArtifact`, persisting the decision evidence artifact separately, or explicitly modeling advisory decision reasons with a cited caveat.
- Acceptance sketch:
  - Remote-enabled auto decisions have persisted/reused evidence matching the intake corpus inputs, or the final artifacts explicitly identify the decision evidence as advisory and non-identical.
  - A regression simulates first-fetch marker / second-fetch empty-or-failed behavior and proves artifacts do not silently contradict each other.
- Recommended next command: `/epic-story-plan EPIC="cure-subsequent-pr-review"` and reference `FB-010` during the interview
- Planning outcome: deferred from Story 03. Story 03 consumes persisted intake ledgers and records missing/degraded provenance, while decision-vs-intake discussion evidence reproducibility remains a runtime/packaging consistency candidate.

### FB-030 - Demote Internal DA coverage from ordinary review body
- Source: local-review:grzegorznowak-cure-pr22-20260613-080828-d739
- Origin: PR #22 live audit at head `372b4a753099c4b6e077d98551da51039222a16b`
- Reason: A16/TAP-17 says the human issue summary is reader-facing and DA rows are internal/audit provenance. The live final `review.md` prominently shows `### Internal DA coverage` near the top, which overexposes internal rows to ordinary consumers.
- Proposed story: Move/demote DA row coverage to an audit artifact, appendix, metadata/comment, or hidden/collapsible audit-only block while preserving report-governor completeness.
- Remap outcome: amended Story 04 (FB-030 / final-output and report-governor surface). Synthetic Story 05 A1 is historical only.

### FB-031 - Strengthen memory replay identity beyond display finding IDs
- Source: local-review:grzegorznowak-cure-pr22-20260613-080828-d739
- Origin: PR #22 live audit final review
- Reason: The narrow same-ordinal/different-finding-IDs regression is fixed, but same display IDs under different origins can still replay a cached resolved row without fingerprint/origin/source-reference validation.
- Proposed story: Require stable identity proof for source-verification memory replay.
- Remap outcome: amended Story 04 primary (memory replay identity) with Story 01 supporting stable prior-finding identity. Synthetic Story 05 A2 is historical only.

### FB-032 - Prevent untrusted discussion body text from escalating authority
- Source: local-review:grzegorznowak-cure-pr22-20260613-080828-d739
- Origin: PR #22 live audit final review
- Reason: Authority classification can trust role words such as product/maintainer/security when they appear in untrusted comment bodies.
- Proposed story: Derive trusted authority from authenticated metadata/config, not untrusted body text.
- Remap outcome: amended Story 03 (discussion authority metadata/body-text separation). Synthetic Story 05 A3 is historical only.

### FB-033 - Enforce session boundary for zip/source artifact paths
- Source: local-review:grzegorznowak-cure-pr22-20260613-080828-d739
- Origin: PR #22 live audit final review
- Reason: Historical metadata paths used by zip/source selection can resolve outside the owning session boundary.
- Proposed story: Reject/degrade absolute or traversal paths outside the session directory for artifact selection.
- Remap outcome: amended Story 01 primary (session-bound artifact paths) with Story 04 runtime support. Synthetic Story 05 A4 is historical only.

### FB-034 - Validate cached linker results against current group identity
- Source: local-review:grzegorznowak-cure-pr22-20260613-080828-d739
- Origin: PR #22 live audit final review
- Reason: Cached discussion linker results can replay stale ordinal group IDs after reconciliation layout changes.
- Proposed story: Bind linker cache entries to stable current-group identity or discard them.
- Remap outcome: amended Story 04 primary (linker cache group identity) with Story 01 supporting stable identity. Synthetic Story 05 A5 is historical only.

### FB-035 - Constrain verifier citations to inspected source contexts
- Source: local-review:grzegorznowak-cure-pr22-20260613-080828-d739
- Origin: PR #22 live audit final review
- Reason: LLM verifier citations are accepted from arbitrary returned paths/lines rather than being constrained to inspected repo-local contexts before confirming source resolution.
- Proposed story: Code-enforce citation membership in inspected source contexts before `resolved_from_source`.
- Remap outcome: amended Story 03 source-truth invariant plus Story 04 runtime verifier enforcement. Synthetic Story 05 A6 is historical only.

### FB-036 - Route discussion linker through prepared runtime policy
- Source: local-review:grzegorznowak-cure-pr22-20260613-080828-d739
- Origin: PR #22 live audit final review
- Reason: Discussion linker LLM calls can run outside the prepared runtime policy/add-dir/config environment used by sibling calls.
- Proposed story: Share prepared runtime policy and environment constraints with linker calls.
- Remap outcome: amended Story 04 (discussion-linker prepared runtime policy/add-dir/config). Synthetic Story 05 A7 is historical only.

### FB-037 - Preserve prior-finding identity for concise generated reviews
- Source: local-review:grzegorznowak-cure-pr22-20260613-080828-d739
- Origin: PR #22 live audit final review
- Reason: Supported concise `--wtf off` generated reviews with source-backed bullets can disappear because the parser expects verbose-card severity markup.
- Proposed story: Parse supported concise issue bullets or degrade missing severity with provenance instead of dropping identity.
- Remap outcome: amended Story 01 (concise generated-review prior-finding parsing). Synthetic Story 05 A8 is historical only.

### FB-038 - Preserve prior-review guardrails on multipass planner abort
- Source: local-review:grzegorznowak-cure-pr22-20260613-080828-d739
- Origin: PR #22 live audit final review
- Reason: Multipass planner abort can write synthetic review output and return before the prior-review final-output guardrail/governor audit runs.
- Proposed story: Ensure abort paths with prior-review briefs emit required issue-history context or fail/degrade before publication.
- Remap outcome: amended Story 04 (multipass planner-abort prior-review guardrails). Synthetic Story 05 A9 is historical only.

## Feedback Absorption Log

| ID | Source Type | Source ID | Source URL | Created | Updated | Disposition | Target | Changed | Status |
|---|---|---|---|---|---|---|---|---|---|
| FB-001 | manual | manual:2026-06-04T11:34:52Z:1 | n/a | 2026-06-04T11:34:52Z | 2026-06-04T11:34:52Z | planned-as-story | story-02-auto-infer-subsequent-review-mode.md | Candidate; miss-category=other/design decision surface; scaffolded Story 02 | absorbed |
| FB-002 | manual | manual:2026-06-04T13:12:11Z:1 | n/a | 2026-06-04T13:12:11Z | 2026-06-04T13:12:11Z | resume-current-story | story-02-auto-infer-subsequent-review-mode.md | Review Log; miss-category=security/semantic invariant naming | absorbed |
| FB-003 | manual | manual:2026-06-04T13:12:11Z:2 | n/a | 2026-06-04T13:12:11Z | 2026-06-04T13:12:11Z | resume-current-story | story-02-auto-infer-subsequent-review-mode.md | Review Log; miss-category=persistence/resource lifecycle | absorbed |
| FB-004 | manual | manual:2026-06-04T13:12:11Z:3 | n/a | 2026-06-04T13:12:11Z | 2026-06-04T13:12:11Z | resume-current-story | story-01-subsequent-review-intake.md | Review Log; miss-category=persistence | absorbed |
| FB-005 | manual | manual:2026-06-04T13:12:11Z:4 | n/a | 2026-06-04T13:12:11Z | 2026-06-04T13:12:11Z | resume-current-story | story-01-subsequent-review-intake.md | Review Log; miss-category=platform/API failure | absorbed |
| FB-006 | manual | manual:2026-06-04T13:12:11Z:5 | n/a | 2026-06-04T13:12:11Z | 2026-06-04T13:12:11Z | resume-current-story | story-01-subsequent-review-intake.md | Review Log; miss-category=behavior-vs-mechanics proof | absorbed |
| FB-007 | manual | manual:2026-06-04T13:12:11Z:6 | n/a | 2026-06-04T13:12:11Z | 2026-06-04T13:12:11Z | new-story-candidate | MASTER.md | Candidate; miss-category=behavior-vs-mechanics proof | absorbed |
| FB-008 | local-review | grzegorznowak-cure-pr22-20260605-154022-f750 | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260605-154022-f750/review.md | 2026-06-05T16:02:16Z | 2026-06-05T16:02:16Z | resume-current-story | story-01-subsequent-review-intake.md | Pull review bodies that can enable auto mode are now in the trusted prior corpus; miss-category=cross-module consistency | absorbed |
| FB-009 | local-review | grzegorznowak-cure-pr22-20260605-161159-7efb | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260605-161159-7efb/review.md | 2026-06-05T16:27:17Z | 2026-06-05T16:27:17Z | resume-current-story | story-01-subsequent-review-intake.md | Remote-only trusted PR comment/review corpora no longer carry stale `no_prior_reviews` degradation; miss-category=status semantics | absorbed |
| FB-010 | local-review | grzegorznowak-cure-pr22-20260605-161159-7efb | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260605-161159-7efb/review.md | 2026-06-05T16:27:17Z | 2026-06-05T16:27:17Z | new-story-candidate | MASTER.md | Candidate for decision/intake discussion-evidence reproducibility; miss-category=cross-module consistency/resource lifecycle | absorbed |
| FB-011 | github_issue_comment | IC_kwDORnlli88AAAABE3bdKQ | https://github.com/grzegorznowak/CURe/pull/22#issuecomment-4621524265 | 2026-06-04T11:01:24Z | 2026-06-04T11:01:24Z | resume-current-story | story-01-subsequent-review-intake.md | Review Log; miss-category=security/persistence | absorbed |
| FB-012 | local-review | grzegorznowak-cure-pr22-20260606-050435-5864:business-1 | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260606-050435-5864/review.md | 2026-06-06T05:23:46Z | 2026-06-06T05:23:46Z | resume-current-story | story-02-auto-infer-subsequent-review-mode.md | Review Log; review comments must not be positive auto-enable markers when excluded from prior corpus; miss-category=cross-module consistency | absorbed |
| FB-013 | local-review | grzegorznowak-cure-pr22-20260606-050435-5864:business-2 | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260606-050435-5864/review.md | 2026-06-06T05:23:46Z | 2026-06-06T05:23:46Z | resume-current-story | story-01-subsequent-review-intake.md | Review Log; generated-review malformed sibling findings need degraded provenance; miss-category=parsing/malformed input | absorbed |
| FB-014 | local-review | grzegorznowak-cure-pr22-20260606-050435-5864:technical-1 | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260606-050435-5864/review.md | 2026-06-06T05:23:46Z | 2026-06-06T05:23:46Z | resume-current-story | story-01-subsequent-review-intake.md | Review Log; symlinked session directories must not escape sandbox containment; miss-category=security/persistence | absorbed |
| FB-015 | local-review | grzegorznowak-cure-pr22-20260606-050435-5864:technical-2 | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260606-050435-5864/review.md | 2026-06-06T05:23:46Z | 2026-06-06T05:23:46Z | resume-current-story | story-02-auto-infer-subsequent-review-mode.md | Review Log; CURe remote marker authorship must not be spoofable by broad login/body regex; miss-category=security/authority | absorbed |
| FB-016 | local-review | grzegorznowak-cure-pr22-20260606-050435-5864:technical-3 | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260606-050435-5864/review.md | 2026-06-06T05:23:46Z | 2026-06-06T05:23:46Z | resume-current-story | story-01-subsequent-review-intake.md | Review Log; same-entry duplicate finding IDs must preserve all provenance; miss-category=finding-identity/provenance | absorbed |
| FB-017 | local-review | grzegorznowak-cure-pr22-20260606-061114-59e0:product-1 | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260606-061114-59e0/review.md | 2026-06-06T06:30:24Z | 2026-06-06T07:12:40Z | resume-current-story | story-01-subsequent-review-intake.md | Review Log; degraded PR discussion history must remain visible in downstream status/manifest; miss-category=status semantics/cross-module consistency | absorbed |
| FB-018 | local-review | grzegorznowak-cure-pr22-20260606-061114-59e0:technical-1 | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260606-061114-59e0/review.md | 2026-06-06T06:30:24Z | 2026-06-06T07:12:40Z | resume-current-story | story-01-subsequent-review-intake.md | Review Log; heading-style prior findings should inherit surrounding section when `Section:` is absent; miss-category=parsing/metadata preservation | absorbed |
| FB-019 | local-review | grzegorznowak-cure-pr22-20260606-061114-59e0:technical-2 | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260606-061114-59e0/review.md | 2026-06-06T06:30:24Z | 2026-06-06T07:12:40Z | resume-current-story | story-01-subsequent-review-intake.md | Review Log; ambiguous or missing `Supersedes` links must degrade reconciler status with explicit reasons; miss-category=finding-identity/status semantics | absorbed |
| FB-020 | local-review | grzegorznowak-cure-pr22-20260606-061114-59e0:technical-3 | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260606-061114-59e0/review.md | 2026-06-06T06:30:24Z | 2026-06-06T07:12:40Z | resume-current-story | story-01-subsequent-review-intake.md | Review Log; persisted Story 01 module artifacts need additive top-level `schema_version`; miss-category=persistence/schema contract | absorbed |
| FB-021 | local-review | grzegorznowak-cure-pr22-20260606-074120-095b:product-1 | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260606-074120-095b/review.md | 2026-06-06T08:20:39Z | 2026-06-06T08:20:39Z | resume-current-story | story-01-subsequent-review-intake.md | Review Log; malformed historical `paths.review_md` resolve failures must degrade prior-review context instead of aborting intake; miss-category=security/persistence/platform failure | absorbed |
| FB-022 | local-review | grzegorznowak-cure-pr22-20260606-074120-095b:product-2 | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260606-074120-095b/review.md | 2026-06-06T08:20:39Z | 2026-06-06T08:20:39Z | resume-current-story | story-01-subsequent-review-intake.md | Review Log; generated-review severity bullets without valid `Sources:` must degrade with provenance, not become source-empty success findings; miss-category=parsing/evidence contract | absorbed |
| FB-023 | local-review | grzegorznowak-cure-pr22-20260606-074120-095b:technical-1 | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260606-074120-095b/review.md | 2026-06-06T08:20:39Z | 2026-06-06T08:20:39Z | resume-current-story | story-01-subsequent-review-intake.md | Review Log; symlinked `meta.json` must not escape session boundary before metadata ingestion; miss-category=security/persistence | absorbed |
| FB-024 | local-review | grzegorznowak-cure-pr22-20260606-074120-095b:technical-2 | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260606-074120-095b/review.md | 2026-06-06T08:20:39Z | 2026-06-06T08:20:39Z | resume-current-story | story-01-subsequent-review-intake.md | Review Log; malformed authored finding statuses must retain provenance/scanned evidence for audit; miss-category=parsing/provenance | absorbed |
| FB-025 | local-review | grzegorznowak-cure-pr22-20260606-074120-095b:technical-3 | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260606-074120-095b/review.md | 2026-06-06T08:20:39Z | 2026-06-06T08:20:39Z | resume-current-story | story-01-subsequent-review-intake.md | Review Log; pull-review corpus entries must preserve reviewed-head/commit provenance; miss-category=remote provenance/schema | absorbed |
| FB-026 | manual | manual:2026-06-12T09:39:53Z:1 | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-083747-6b5c | 2026-06-12T09:39:53Z | 2026-06-12T09:39:53Z | resume-current-story | story-02-auto-infer-subsequent-review-mode.md | Review Log + Plan lane invalidation; official CURe footer alone should identify prior remote CURe reviews for decision/corpus; miss-category=remote marker policy/cross-module consistency | absorbed |
| FB-027 | manual | manual:sha256-aa91ef4810b6:1 | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424 | 2026-06-13T04:34:15Z | 2026-06-13T04:34:15Z | resume-current-story | story-04-review-runtime-integration-guardrails-memory-trace | Reviews.md entry; latest live run leaves A16 partial/failing while A19/DA-0006 and A17 pass; miss-category=behavior-vs-mechanics proof/output contract | absorbed |
| FB-028 | manual | manual:sha256-61c9fda061a2:2 | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424/review.md | 2026-06-13T04:34:15Z | 2026-06-13T04:34:15Z | resume-current-story | story-04-review-runtime-integration-guardrails-memory-trace | Reviews.md entry; malformed LLM discussion-linker output must degrade instead of aborting semantic artifacts; miss-category=platform/API failure/degraded behavior | absorbed |
| FB-029 | manual | manual:sha256-451b683eda28:3 | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260612-181530-f424/review.md | 2026-06-13T04:34:15Z | 2026-06-13T04:34:15Z | resume-current-story | story-04-review-runtime-integration-guardrails-memory-trace | Reviews.md entry; source-verification memory replay can confirm the wrong finding when ordinal group IDs shift; miss-category=persistence/finding-identity | absorbed |
| FB-030 | local-review | grzegorznowak-cure-pr22-20260613-080828-d739:internal-da-coverage | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260613-080828-d739/review.md | 2026-06-13T10:05:45Z | 2026-06-14T10:46:40Z | amend-existing-story | story-04-review-runtime-integration-guardrails-memory-trace | Remapped to Story 04; remove/demote `### Internal DA coverage` from ordinary consumer-facing `review.md` while retaining audit coverage; miss-category=output-contract/UX | absorbed |
| FB-031 | local-review | grzegorznowak-cure-pr22-20260613-080828-d739:memory-origin | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260613-080828-d739/review.md | 2026-06-13T10:05:45Z | 2026-06-14T10:46:40Z | amend-existing-story | story-04-review-runtime-integration-guardrails-memory-trace; story-01-subsequent-review-intake | Remapped to Story 04 primary with Story 01 identity support; strengthen memory replay identity with origin/fingerprint/source-reference proof; miss-category=persistence/finding-identity | absorbed |
| FB-032 | local-review | grzegorznowak-cure-pr22-20260613-080828-d739:discussion-authority | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260613-080828-d739/review.md | 2026-06-13T10:05:45Z | 2026-06-14T10:46:40Z | amend-existing-story | story-03-evidence-semantics-disposition-engine | Remapped to Story 03; untrusted body text cannot grant trusted authority; miss-category=security/authority | absorbed |
| FB-033 | local-review | grzegorznowak-cure-pr22-20260613-080828-d739:zip-path-boundary | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260613-080828-d739/review.md | 2026-06-13T10:05:45Z | 2026-06-14T10:46:40Z | amend-existing-story | story-01-subsequent-review-intake; story-04-review-runtime-integration-guardrails-memory-trace | Remapped to Story 01 primary with Story 04 runtime support; constrain zip/source artifact metadata paths to session boundary; miss-category=security/persistence | absorbed |
| FB-034 | local-review | grzegorznowak-cure-pr22-20260613-080828-d739:linker-cache-identity | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260613-080828-d739/review.md | 2026-06-13T10:05:45Z | 2026-06-14T10:46:40Z | amend-existing-story | story-04-review-runtime-integration-guardrails-memory-trace; story-01-subsequent-review-intake | Remapped to Story 04 primary with Story 01 identity support; validate cached linker group IDs against current reconciliation identity; miss-category=persistence/finding-identity | absorbed |
| FB-035 | local-review | grzegorznowak-cure-pr22-20260613-080828-d739:verifier-citations | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260613-080828-d739/review.md | 2026-06-13T10:05:45Z | 2026-06-14T10:46:40Z | amend-existing-story | story-03-evidence-semantics-disposition-engine; story-04-review-runtime-integration-guardrails-memory-trace | Remapped to Story 03 source-truth invariant plus Story 04 runtime verifier enforcement; constrain verifier citations to inspected source contexts; miss-category=source-truth/evidence-contract | absorbed |
| FB-036 | local-review | grzegorznowak-cure-pr22-20260613-080828-d739:linker-runtime-policy | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260613-080828-d739/review.md | 2026-06-13T10:05:45Z | 2026-06-14T10:46:40Z | amend-existing-story | story-04-review-runtime-integration-guardrails-memory-trace | Remapped to Story 04; route discussion linker through prepared runtime policy/add-dir/config; miss-category=runtime-policy | absorbed |
| FB-037 | local-review | grzegorznowak-cure-pr22-20260613-080828-d739:concise-prior-findings | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260613-080828-d739/review.md | 2026-06-13T10:05:45Z | 2026-06-14T10:46:40Z | amend-existing-story | story-01-subsequent-review-intake | Remapped to Story 01; preserve prior-finding identity for supported concise generated reviews; miss-category=parsing/output-mode | absorbed |
| FB-038 | local-review | grzegorznowak-cure-pr22-20260613-080828-d739:planner-abort-guardrail | /home/vscode/.local/state/cure/sandboxes/grzegorznowak-cure-pr22-20260613-080828-d739/review.md | 2026-06-13T10:05:45Z | 2026-06-14T10:46:40Z | amend-existing-story | story-04-review-runtime-integration-guardrails-memory-trace | Remapped to Story 04; planner-abort output cannot bypass prior-review guardrails/governor; miss-category=runtime/control-flow | absorbed |
